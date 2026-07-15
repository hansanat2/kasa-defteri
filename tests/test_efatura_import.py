import zipfile
from pathlib import Path

import pytest

from kasa_defteri import database, efatura_import
from kasa_defteri.models import GELIR, GIDER

FIXTURES = Path(__file__).parent / "fixtures"


def test_xml_dosyasini_ayristir_temel_alanlar():
    veri = efatura_import.xml_dosyasini_ayristir(FIXTURES / "ornek_fatura_1.xml")
    assert veri.invoice_id == "ORN2024000000001"
    assert veri.uuid == "11111111-1111-1111-1111-111111111111"
    assert veri.issue_date == "2024-03-15"
    assert veri.supplier_name == "ÖRNEK YAZILIM TEKNOLOJİLERİ A.Ş."
    assert veri.supplier_vkn == "1234567890"
    assert veri.customer_name == "TEST ŞİRKETİ LTD.ŞTİ."
    assert veri.payable_amount == 118.0
    assert veri.tax_amount == 18.0


def test_bozuk_xml_hata_firlatir():
    with pytest.raises(efatura_import.EFaturaAyristirmaHatasi):
        efatura_import.xml_dosyasini_ayristir(FIXTURES / "bozuk_fatura.xml")


def test_kategori_tahmini_anahtar_kelimeyle_eslesir():
    veri = efatura_import.xml_dosyasini_ayristir(FIXTURES / "ornek_fatura_2.xml")
    islem = efatura_import.efatura_verisinden_islem_olustur(veri, GIDER)
    assert islem.kategori == "Elektrik/Su/Doğalgaz"


def test_kategori_tahmini_eslesme_yoksa_diger_gider():
    # ornek_fatura_1.xml'deki tedarikçi adı "YAZILIM" içerir; eşleşme
    # olmayan bir durumu test etmek için doğrudan veri nesnesi kuruyoruz.
    veri = efatura_import.xml_dosyasini_ayristir(FIXTURES / "ornek_fatura_1.xml")
    veri.supplier_name = "ALAKASIZ TİCARET A.Ş."
    islem = efatura_import.efatura_verisinden_islem_olustur(veri, GIDER)
    assert islem.kategori == "Diğer Gider"


def test_dosyayi_ice_aktar_gider_olarak(conn):
    sonuc = efatura_import.dosyayi_ice_aktar(conn, FIXTURES / "ornek_fatura_1.xml", GIDER)
    assert sonuc.basarili
    kayitlar = database.islemleri_listele(conn)
    assert len(kayitlar) == 1
    assert kayitlar[0].tur == GIDER
    assert kayitlar[0].tutar == 118.0
    assert kayitlar[0].kaynak == "efatura"


def test_dosyayi_ice_aktar_gelir_olarak(conn):
    sonuc = efatura_import.dosyayi_ice_aktar(conn, FIXTURES / "ornek_fatura_1.xml", GELIR)
    assert sonuc.basarili
    kayitlar = database.islemleri_listele(conn)
    assert kayitlar[0].tur == GELIR
    assert kayitlar[0].karsi_taraf == "TEST ŞİRKETİ LTD.ŞTİ."  # müşteri


def test_ayni_faturayi_iki_kez_aktarma_engellenir(conn):
    ilk = efatura_import.dosyayi_ice_aktar(conn, FIXTURES / "ornek_fatura_1.xml", GIDER)
    ikinci = efatura_import.dosyayi_ice_aktar(conn, FIXTURES / "ornek_fatura_1.xml", GIDER)
    assert ilk.basarili
    assert not ikinci.basarili
    assert len(database.islemleri_listele(conn)) == 1


def test_klasoru_ice_aktar(conn):
    sonuclar = efatura_import.klasoru_ice_aktar(conn, FIXTURES, GIDER)
    dosya_adlari = {s.dosya_adi for s in sonuclar}
    assert "ornek_fatura_1.xml" in dosya_adlari
    assert "ornek_fatura_2.xml" in dosya_adlari
    # bozuk_fatura.xml da denenir ama başarısız olur
    basarisizlar = [s for s in sonuclar if not s.basarili]
    assert any("bozuk_fatura" in s.dosya_adi for s in basarisizlar)

    basarili_sayisi = sum(1 for s in sonuclar if s.basarili)
    assert basarili_sayisi == 2
    assert len(database.islemleri_listele(conn)) == 2


def test_zip_ice_aktar(conn, tmp_path):
    zip_yolu = tmp_path / "faturalar.zip"
    with zipfile.ZipFile(zip_yolu, "w") as z:
        z.write(FIXTURES / "ornek_fatura_1.xml", "ornek_fatura_1.xml")
        z.write(FIXTURES / "ornek_fatura_2.xml", "ornek_fatura_2.xml")

    sonuclar = efatura_import.zip_ice_aktar(conn, zip_yolu, GIDER)
    assert len(sonuclar) == 2
    assert all(s.basarili for s in sonuclar)
    assert len(database.islemleri_listele(conn)) == 2


def test_kaynagi_ice_aktar_otomatik_algilar(conn):
    sonuclar = efatura_import.kaynagi_ice_aktar(conn, FIXTURES / "ornek_fatura_1.xml", GIDER)
    assert len(sonuclar) == 1
    assert sonuclar[0].basarili


def test_kaynagi_ice_aktar_desteklenmeyen_uzanti(conn, tmp_path):
    dosya = tmp_path / "belge.txt"
    dosya.write_text("merhaba")
    with pytest.raises(ValueError):
        efatura_import.kaynagi_ice_aktar(conn, dosya, GIDER)
