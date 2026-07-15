"""Kasa defteri analiz ve rapor fonksiyonları.

Tüm tarih parametreleri "YYYY-MM-DD" formatındaki ISO tarih metinleridir ve
uçlar dahildir (>= baslangic, <= bitis).
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Optional

from . import database
from .models import GELIR, GIDER

ACILIS_BAKIYESI_ANAHTARI = "acilis_bakiyesi"


def acilis_bakiyesini_getir(conn: sqlite3.Connection) -> float:
    return float(database.ayar_getir(conn, ACILIS_BAKIYESI_ANAHTARI, "0") or "0")


def acilis_bakiyesini_ayarla(conn: sqlite3.Connection, tutar: float) -> None:
    database.ayar_ayarla(conn, ACILIS_BAKIYESI_ANAHTARI, str(tutar))


def toplam_gelir(
    conn: sqlite3.Connection, baslangic: Optional[str] = None, bitis: Optional[str] = None
) -> float:
    islemler = database.islemleri_listele(conn, baslangic, bitis, tur=GELIR)
    return round(sum(i.tutar for i in islemler), 2)


def toplam_gider(
    conn: sqlite3.Connection, baslangic: Optional[str] = None, bitis: Optional[str] = None
) -> float:
    islemler = database.islemleri_listele(conn, baslangic, bitis, tur=GIDER)
    return round(sum(i.tutar for i in islemler), 2)


def donem_net_sonucu(
    conn: sqlite3.Connection, baslangic: Optional[str] = None, bitis: Optional[str] = None
) -> float:
    """Belirtilen dönemdeki gelir - gider farkı (açılış bakiyesi hariç)."""
    return round(
        toplam_gelir(conn, baslangic, bitis) - toplam_gider(conn, baslangic, bitis), 2
    )


def guncel_kasa_bakiyesi(conn: sqlite3.Connection) -> float:
    """Açılış bakiyesi + bugüne kadarki tüm gelir/gider hareketleri."""
    return round(acilis_bakiyesini_getir(conn) + donem_net_sonucu(conn), 2)


def aylik_ozet(
    conn: sqlite3.Connection, baslangic: Optional[str] = None, bitis: Optional[str] = None
) -> list[dict]:
    """Ay bazında (YYYY-MM) gelir, gider ve net toplamları döner."""
    islemler = database.islemleri_listele(conn, baslangic, bitis)
    aylar: dict[str, dict] = {}
    for i in islemler:
        ay = i.tarih[:7] if len(i.tarih) >= 7 else i.tarih
        if ay not in aylar:
            aylar[ay] = {"ay": ay, "gelir": 0.0, "gider": 0.0}
        aylar[ay][i.tur] += i.tutar

    sonuc = []
    for ay in sorted(aylar):
        gelir = round(aylar[ay]["gelir"], 2)
        gider = round(aylar[ay]["gider"], 2)
        sonuc.append({"ay": ay, "gelir": gelir, "gider": gider, "net": round(gelir - gider, 2)})
    return sonuc


def kategori_bazli_ozet(
    conn: sqlite3.Connection,
    tur: str = GIDER,
    baslangic: Optional[str] = None,
    bitis: Optional[str] = None,
) -> list[dict]:
    """Kategoriye göre toplamları büyükten küçüğe sıralı döner."""
    islemler = database.islemleri_listele(conn, baslangic, bitis, tur=tur)
    kategoriler: dict[str, float] = {}
    for i in islemler:
        ad = i.kategori or "Kategorisiz"
        kategoriler[ad] = kategoriler.get(ad, 0.0) + i.tutar
    sonuc = [{"kategori": k, "toplam": round(v, 2)} for k, v in kategoriler.items()]
    sonuc.sort(key=lambda x: x["toplam"], reverse=True)
    return sonuc


def kasa_defteri_dokumu(
    conn: sqlite3.Connection, baslangic: Optional[str] = None, bitis: Optional[str] = None
) -> list[dict]:
    """Kronolojik kasa defteri dökümü: her satırda o ana kadarki bakiye.

    Açılış bakiyesi, filtre aralığından önceki tüm hareketlerle birlikte
    doğru şekilde taşınır; yani baslangic/bitis sadece görüntülenen
    satırları daraltır, bakiye hesabını bozmaz.
    """
    tum_islemler = database.islemleri_listele(conn)
    bakiye = acilis_bakiyesini_getir(conn)
    sonuc = []
    for i in tum_islemler:
        degisim = i.tutar if i.tur == GELIR else -i.tutar
        bakiye = round(bakiye + degisim, 2)
        if baslangic and i.tarih < baslangic:
            continue
        if bitis and i.tarih > bitis:
            continue
        sonuc.append(
            {
                "id": i.id,
                "tarih": i.tarih,
                "aciklama": i.aciklama,
                "kategori": i.kategori,
                "karsi_taraf": i.karsi_taraf,
                "belge_no": i.belge_no,
                "gelir": i.tutar if i.tur == GELIR else 0.0,
                "gider": i.tutar if i.tur == GIDER else 0.0,
                "bakiye": bakiye,
                "kaynak": i.kaynak,
            }
        )
    return sonuc


def csv_olarak_disa_aktar(
    conn: sqlite3.Connection,
    dosya_yolu: str | Path,
    baslangic: Optional[str] = None,
    bitis: Optional[str] = None,
) -> Path:
    """Kasa defteri dökümünü CSV dosyasına yazar (Excel'de açılabilir)."""
    dosya_yolu = Path(dosya_yolu)
    satirlar = kasa_defteri_dokumu(conn, baslangic, bitis)
    basliklar = [
        "Tarih",
        "Açıklama",
        "Kategori",
        "Karşı Taraf",
        "Belge No",
        "Gelir",
        "Gider",
        "Bakiye",
        "Kaynak",
    ]
    with open(dosya_yolu, "w", newline="", encoding="utf-8-sig") as f:
        yazici = csv.writer(f, delimiter=";")
        yazici.writerow(basliklar)
        for s in satirlar:
            yazici.writerow(
                [
                    s["tarih"],
                    s["aciklama"],
                    s["kategori"],
                    s["karsi_taraf"],
                    s["belge_no"],
                    f"{s['gelir']:.2f}",
                    f"{s['gider']:.2f}",
                    f"{s['bakiye']:.2f}",
                    s["kaynak"],
                ]
            )
    return dosya_yolu
