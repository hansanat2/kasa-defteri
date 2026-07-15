"""GİB e-Fatura (UBL-TR Invoice-2) XML dosyalarını okuyup kasa defterine
gider kaydı olarak aktaran modül.

Desteklenen kaynaklar:
- Tek bir .xml dosyası
- İçinde .xml dosyaları bulunan bir klasör (alt klasörler dahil)
- .xml dosyaları içeren bir .zip arşivi (GİB portalından indirilen
  "Gelen Fatura" paketleri genelde bu formattadır)

Yön (gelir/gider) tespiti: Ayarlarda bir "şirket VKN"si tanımlıysa, her
faturanın satıcı ve alıcı VKN'leri bu değerle karşılaştırılır — şirketimiz
satıcı tarafındaysa (biz kestiysek) fatura **gelir**, alıcı tarafındaysa
(bize kesildiyse) fatura **gider** olarak otomatik kaydedilir. Şirket VKN'si
tanımlı değilse veya faturanın hiçbir tarafı eşleşmiyorsa, çağıranın verdiği
`varsayilan_tur` kullanılır (elle seçilen "Gelen Fatura" / "Giden Fatura").
"""

from __future__ import annotations

import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from . import database, reports
from .models import GELIR, GIDER, KAYNAK_EFATURA, Islem

NS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}

# Tedarikçi adındaki anahtar kelimelere göre otomatik kategori tahmini.
# Eşleşme yoksa "Diğer Gider" kullanılır.
KATEGORI_ANAHTAR_KELIMELER: dict[str, str] = {
    "İLETİŞİM": "İnternet/Telefon",
    "TELEKOM": "İnternet/Telefon",
    "TURKCELL": "İnternet/Telefon",
    "SUPERONLINE": "İnternet/Telefon",
    "VODAFONE": "İnternet/Telefon",
    "TTNET": "İnternet/Telefon",
    "YAZILIM": "Yazılım/Abonelik",
    "BİLİŞİM": "Yazılım/Abonelik",
    "BİLGİSAYAR": "Ofis Malzemesi",
    "ELEKTRİK": "Elektrik/Su/Doğalgaz",
    "DOĞALGAZ": "Elektrik/Su/Doğalgaz",
    "SU İDARESİ": "Elektrik/Su/Doğalgaz",
}


@dataclass
class EFaturaVerisi:
    """Bir e-fatura XML'inden ayrıştırılan alanlar."""

    invoice_id: str
    uuid: str
    issue_date: str
    invoice_type_code: str
    currency: str
    supplier_name: str
    supplier_vkn: str
    customer_name: str
    customer_vkn: str
    line_extension_amount: float
    tax_exclusive_amount: float
    tax_inclusive_amount: float
    payable_amount: float
    tax_amount: float


class EFaturaAyristirmaHatasi(Exception):
    """XML beklenen UBL-TR Invoice yapısında değilse fırlatılır."""


def _metin(el: Optional[ET.Element], varsayilan: str = "") -> str:
    if el is None or el.text is None:
        return varsayilan
    return el.text.strip()


def _sayi(el: Optional[ET.Element], varsayilan: float = 0.0) -> float:
    metin = _metin(el)
    if not metin:
        return varsayilan
    # Türkçe fatura XML'lerinde ondalık ayraç noktadır (örn. 287.40)
    try:
        return float(metin.replace(",", ""))
    except ValueError:
        return varsayilan


def _taraf_bilgisi(party_el: Optional[ET.Element]) -> tuple[str, str]:
    """AccountingSupplierParty / AccountingCustomerParty altından
    (isim, VKN/TCKN) döner."""
    if party_el is None:
        return "", ""
    isim_el = party_el.find(".//cac:PartyName/cbc:Name", NS)
    isim = _metin(isim_el)
    vkn = ""
    for pid in party_el.findall(".//cac:PartyIdentification/cbc:ID", NS):
        scheme = pid.get("schemeID", "")
        if scheme in ("VKN", "TCKN") and pid.text:
            vkn = pid.text.strip()
            break
    return isim, vkn


def xml_dosyasini_ayristir(dosya_yolu: str | Path) -> EFaturaVerisi:
    """Tek bir UBL-TR e-fatura XML dosyasını ayrıştırır."""
    try:
        tree = ET.parse(dosya_yolu)
    except ET.ParseError as exc:
        raise EFaturaAyristirmaHatasi(f"XML ayrıştırılamadı: {exc}") from exc

    root = tree.getroot()

    invoice_id = _metin(root.find("cbc:ID", NS))
    uuid = _metin(root.find("cbc:UUID", NS))
    if not invoice_id or not uuid:
        raise EFaturaAyristirmaHatasi(
            "Beklenen UBL-TR Invoice yapısı bulunamadı (ID/UUID eksik)"
        )

    issue_date = _metin(root.find("cbc:IssueDate", NS))
    invoice_type_code = _metin(root.find("cbc:InvoiceTypeCode", NS), "SATIS")
    currency = _metin(root.find("cbc:DocumentCurrencyCode", NS), "TRY")

    supplier_el = root.find("cac:AccountingSupplierParty/cac:Party", NS)
    customer_el = root.find("cac:AccountingCustomerParty/cac:Party", NS)
    supplier_name, supplier_vkn = _taraf_bilgisi(supplier_el)
    customer_name, customer_vkn = _taraf_bilgisi(customer_el)

    totals_el = root.find("cac:LegalMonetaryTotal", NS)
    line_extension = _sayi(totals_el.find("cbc:LineExtensionAmount", NS)) if totals_el is not None else 0.0
    tax_exclusive = _sayi(totals_el.find("cbc:TaxExclusiveAmount", NS)) if totals_el is not None else 0.0
    tax_inclusive = _sayi(totals_el.find("cbc:TaxInclusiveAmount", NS)) if totals_el is not None else 0.0
    payable = _sayi(totals_el.find("cbc:PayableAmount", NS)) if totals_el is not None else 0.0

    tax_total_el = root.find("cac:TaxTotal", NS)
    tax_amount = _sayi(tax_total_el.find("cbc:TaxAmount", NS)) if tax_total_el is not None else 0.0

    return EFaturaVerisi(
        invoice_id=invoice_id,
        uuid=uuid,
        issue_date=issue_date,
        invoice_type_code=invoice_type_code,
        currency=currency,
        supplier_name=supplier_name,
        supplier_vkn=supplier_vkn,
        customer_name=customer_name,
        customer_vkn=customer_vkn,
        line_extension_amount=line_extension,
        tax_exclusive_amount=tax_exclusive,
        tax_inclusive_amount=tax_inclusive,
        payable_amount=payable,
        tax_amount=tax_amount,
    )


def _kategori_tahmin_et(taraf_adi: str) -> str:
    ad_buyuk = taraf_adi.upper()
    for anahtar, kategori in KATEGORI_ANAHTAR_KELIMELER.items():
        if anahtar in ad_buyuk:
            return kategori
    return "Diğer Gider"


def yonu_belirle(veri: EFaturaVerisi, varsayilan_tur: str, sirket_vkn: str = "") -> str:
    """Faturanın gelir mi gider mi olduğuna karar verir.

    Şirket VKN'si tanımlıysa ve faturanın taraflarından biriyle eşleşiyorsa
    otomatik belirlenir: şirketimiz satıcıysa gelir, alıcıysa gider.
    Eşleşme yoksa (veya VKN tanımlı değilse) `varsayilan_tur` kullanılır.
    """
    sirket_vkn = (sirket_vkn or "").strip()
    if sirket_vkn:
        if veri.supplier_vkn and veri.supplier_vkn == sirket_vkn:
            return GELIR
        if veri.customer_vkn and veri.customer_vkn == sirket_vkn:
            return GIDER
    return varsayilan_tur


def efatura_verisinden_islem_olustur(
    veri: EFaturaVerisi, varsayilan_tur: str = GIDER, sirket_vkn: str = ""
) -> Islem:
    """Ayrıştırılmış e-fatura verisinden bir Islem (kasa defteri kaydı) üretir.

    Yön (gelir/gider) `yonu_belirle` ile tespit edilir: `sirket_vkn`
    faturanın satıcı tarafıyla eşleşirse gelir, alıcı tarafıyla eşleşirse
    gider olur; eşleşme yoksa `varsayilan_tur` (elle seçilen yön) kullanılır.
    """
    tur = yonu_belirle(veri, varsayilan_tur, sirket_vkn)

    if tur == GIDER:
        karsi_taraf = veri.supplier_name
        vkn = veri.supplier_vkn
        kategori = _kategori_tahmin_et(veri.supplier_name)
    else:
        karsi_taraf = veri.customer_name
        vkn = veri.customer_vkn
        kategori = "Satış Geliri"

    aciklama = f"{karsi_taraf} - Fatura No: {veri.invoice_id}"
    if veri.invoice_type_code and veri.invoice_type_code != "SATIS":
        aciklama = f"[{veri.invoice_type_code}] {aciklama}"

    tutar = veri.payable_amount or veri.tax_inclusive_amount

    return Islem(
        tarih=veri.issue_date,
        tur=tur,
        tutar=tutar,
        kategori=kategori,
        aciklama=aciklama,
        karsi_taraf=karsi_taraf,
        belge_no=veri.invoice_id,
        vkn_tckn=vkn,
        kaynak=KAYNAK_EFATURA,
        efatura_uuid=veri.uuid,
    )


@dataclass
class IceAktarmaSonucu:
    dosya_adi: str
    basarili: bool
    mesaj: str
    islem_id: Optional[int] = None


def dosyayi_ice_aktar(
    conn: sqlite3.Connection,
    dosya_yolu: str | Path,
    varsayilan_tur: str = GIDER,
    sirket_vkn: Optional[str] = None,
) -> IceAktarmaSonucu:
    """Tek bir e-fatura XML dosyasını veritabanına kaydeder.

    `sirket_vkn` verilmezse (None), ayarlarda kayıtlı şirket VKN'si
    kullanılır (bkz. `yonu_belirle`).
    """
    dosya_yolu = Path(dosya_yolu)
    if sirket_vkn is None:
        sirket_vkn = reports.sirket_vkn_getir(conn)

    try:
        veri = xml_dosyasini_ayristir(dosya_yolu)
    except EFaturaAyristirmaHatasi as exc:
        return IceAktarmaSonucu(dosya_yolu.name, False, str(exc))

    if database.efatura_uuid_var_mi(conn, veri.uuid):
        return IceAktarmaSonucu(
            dosya_yolu.name, False, "Bu fatura zaten daha önce içe aktarılmış"
        )

    islem = efatura_verisinden_islem_olustur(veri, varsayilan_tur, sirket_vkn)
    islem_id = database.islem_ekle(conn, islem)
    if islem_id is None:
        return IceAktarmaSonucu(
            dosya_yolu.name, False, "Bu fatura zaten daha önce içe aktarılmış"
        )
    yon_etiketi = "gelir" if islem.tur == GELIR else "gider"
    return IceAktarmaSonucu(
        dosya_yolu.name,
        True,
        f"Aktarıldı ({yon_etiketi}): {islem.karsi_taraf} - {islem.tutar} TRY",
        islem_id,
    )


def klasoru_ice_aktar(
    conn: sqlite3.Connection,
    klasor_yolu: str | Path,
    varsayilan_tur: str = GIDER,
    sirket_vkn: Optional[str] = None,
) -> list[IceAktarmaSonucu]:
    """Klasördeki (ve alt klasörlerdeki) tüm .xml dosyalarını içe aktarır."""
    if sirket_vkn is None:
        sirket_vkn = reports.sirket_vkn_getir(conn)
    klasor_yolu = Path(klasor_yolu)
    sonuclar = []
    for xml_dosyasi in sorted(klasor_yolu.rglob("*.xml")):
        sonuclar.append(dosyayi_ice_aktar(conn, xml_dosyasi, varsayilan_tur, sirket_vkn))
    return sonuclar


def zip_ice_aktar(
    conn: sqlite3.Connection,
    zip_yolu: str | Path,
    varsayilan_tur: str = GIDER,
    sirket_vkn: Optional[str] = None,
) -> list[IceAktarmaSonucu]:
    """Bir .zip arşivini geçici bir klasöre açıp içindeki tüm .xml
    dosyalarını içe aktarır."""
    if sirket_vkn is None:
        sirket_vkn = reports.sirket_vkn_getir(conn)
    with tempfile.TemporaryDirectory() as gecici_klasor:
        with zipfile.ZipFile(zip_yolu) as z:
            z.extractall(gecici_klasor)
        return klasoru_ice_aktar(conn, gecici_klasor, varsayilan_tur, sirket_vkn)


def kaynagi_ice_aktar(
    conn: sqlite3.Connection,
    yol: str | Path,
    varsayilan_tur: str = GIDER,
    sirket_vkn: Optional[str] = None,
) -> list[IceAktarmaSonucu]:
    """Yol; .xml dosyası, .zip arşivi veya klasör olabilir - otomatik algılar."""
    if sirket_vkn is None:
        sirket_vkn = reports.sirket_vkn_getir(conn)
    yol = Path(yol)
    if yol.is_dir():
        return klasoru_ice_aktar(conn, yol, varsayilan_tur, sirket_vkn)
    if yol.suffix.lower() == ".zip":
        return zip_ice_aktar(conn, yol, varsayilan_tur, sirket_vkn)
    if yol.suffix.lower() == ".xml":
        return [dosyayi_ice_aktar(conn, yol, varsayilan_tur, sirket_vkn)]
    raise ValueError(f"Desteklenmeyen dosya türü: {yol}")
