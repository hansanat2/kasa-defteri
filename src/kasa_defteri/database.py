"""SQLite veritabanı katmanı: bağlantı, şema ve CRUD işlemleri."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from .models import Islem

SCHEMA = """
CREATE TABLE IF NOT EXISTS kategoriler (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad TEXT NOT NULL UNIQUE,
    tur TEXT NOT NULL CHECK(tur IN ('gelir', 'gider'))
);

CREATE TABLE IF NOT EXISTS islemler (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarih TEXT NOT NULL,
    tur TEXT NOT NULL CHECK(tur IN ('gelir', 'gider')),
    tutar REAL NOT NULL CHECK(tutar >= 0),
    kategori TEXT,
    aciklama TEXT,
    karsi_taraf TEXT,
    belge_no TEXT,
    vkn_tckn TEXT,
    kaynak TEXT NOT NULL DEFAULT 'manuel' CHECK(kaynak IN ('manuel', 'efatura')),
    efatura_uuid TEXT UNIQUE,
    olusturma_zamani TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_islemler_tarih ON islemler(tarih);
CREATE INDEX IF NOT EXISTS idx_islemler_tur ON islemler(tur);
CREATE INDEX IF NOT EXISTS idx_islemler_kategori ON islemler(kategori);

CREATE TABLE IF NOT EXISTS ayarlar (
    anahtar TEXT PRIMARY KEY,
    deger TEXT
);
"""

VARSAYILAN_KATEGORILER = [
    ("Satış Geliri", "gelir"),
    ("Hizmet Geliri", "gelir"),
    ("Diğer Gelir", "gelir"),
    ("Kira", "gider"),
    ("Elektrik/Su/Doğalgaz", "gider"),
    ("İnternet/Telefon", "gider"),
    ("Yazılım/Abonelik", "gider"),
    ("Ofis Malzemesi", "gider"),
    ("Personel/Maaş", "gider"),
    ("Vergi/SGK", "gider"),
    ("Diğer Gider", "gider"),
]


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Verilen yoldaki SQLite veritabanına bağlanır (yoksa oluşturur)."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection, varsayilan_kategoriler: bool = True) -> None:
    """Şemayı oluşturur ve isteğe bağlı olarak varsayılan kategorileri ekler."""
    conn.executescript(SCHEMA)
    if varsayilan_kategoriler:
        for ad, tur in VARSAYILAN_KATEGORILER:
            conn.execute(
                "INSERT OR IGNORE INTO kategoriler (ad, tur) VALUES (?, ?)", (ad, tur)
            )
    conn.commit()


# --------------------------------------------------------------------------
# İşlemler (gelir/gider kayıtları)
# --------------------------------------------------------------------------

def islem_ekle(conn: sqlite3.Connection, islem: Islem) -> Optional[int]:
    """Yeni bir gelir/gider kaydı ekler.

    E-fatura kaynaklı kayıtlarda aynı efatura_uuid zaten varsa (mükerrer
    içe aktarma) satır eklenmez ve None döner.
    """
    try:
        cur = conn.execute(
            """
            INSERT INTO islemler
                (tarih, tur, tutar, kategori, aciklama, karsi_taraf,
                 belge_no, vkn_tckn, kaynak, efatura_uuid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                islem.tarih,
                islem.tur,
                islem.tutar,
                islem.kategori,
                islem.aciklama,
                islem.karsi_taraf,
                islem.belge_no,
                islem.vkn_tckn,
                islem.kaynak,
                islem.efatura_uuid,
            ),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        # efatura_uuid UNIQUE ihlali -> bu fatura zaten içe aktarılmış
        return None


def islem_guncelle(conn: sqlite3.Connection, islem_id: int, **alanlar) -> None:
    """Belirtilen alanları günceller. Örn: islem_guncelle(conn, 3, tutar=150.0)"""
    if not alanlar:
        return
    izinli = {
        "tarih",
        "tur",
        "tutar",
        "kategori",
        "aciklama",
        "karsi_taraf",
        "belge_no",
        "vkn_tckn",
    }
    setler = []
    degerler = []
    for k, v in alanlar.items():
        if k not in izinli:
            raise ValueError(f"Güncellenemeyen alan: {k}")
        setler.append(f"{k} = ?")
        degerler.append(v)
    degerler.append(islem_id)
    conn.execute(f"UPDATE islemler SET {', '.join(setler)} WHERE id = ?", degerler)
    conn.commit()


def islem_sil(conn: sqlite3.Connection, islem_id: int) -> None:
    conn.execute("DELETE FROM islemler WHERE id = ?", (islem_id,))
    conn.commit()


def islem_getir(conn: sqlite3.Connection, islem_id: int) -> Optional[Islem]:
    row = conn.execute("SELECT * FROM islemler WHERE id = ?", (islem_id,)).fetchone()
    return Islem.from_row(row) if row else None


def islemleri_listele(
    conn: sqlite3.Connection,
    baslangic: Optional[str] = None,
    bitis: Optional[str] = None,
    tur: Optional[str] = None,
    kategori: Optional[str] = None,
) -> list[Islem]:
    """Filtrelere uyan işlemleri tarihe göre artan sırada döner."""
    sorgu = "SELECT * FROM islemler WHERE 1=1"
    parametreler: list = []
    if baslangic:
        sorgu += " AND tarih >= ?"
        parametreler.append(baslangic)
    if bitis:
        sorgu += " AND tarih <= ?"
        parametreler.append(bitis)
    if tur:
        sorgu += " AND tur = ?"
        parametreler.append(tur)
    if kategori:
        sorgu += " AND kategori = ?"
        parametreler.append(kategori)
    sorgu += " ORDER BY tarih ASC, id ASC"
    rows = conn.execute(sorgu, parametreler).fetchall()
    return [Islem.from_row(r) for r in rows]


def efatura_uuid_var_mi(conn: sqlite3.Connection, uuid: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM islemler WHERE efatura_uuid = ?", (uuid,)
    ).fetchone()
    return row is not None


# --------------------------------------------------------------------------
# Kategoriler
# --------------------------------------------------------------------------

def kategori_ekle(conn: sqlite3.Connection, ad: str, tur: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO kategoriler (ad, tur) VALUES (?, ?)", (ad, tur)
    )
    conn.commit()


def kategorileri_listele(
    conn: sqlite3.Connection, tur: Optional[str] = None
) -> list[str]:
    if tur:
        rows = conn.execute(
            "SELECT ad FROM kategoriler WHERE tur = ? ORDER BY ad", (tur,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT ad FROM kategoriler ORDER BY ad").fetchall()
    return [r["ad"] for r in rows]


# --------------------------------------------------------------------------
# Ayarlar (örn. açılış bakiyesi)
# --------------------------------------------------------------------------

def ayar_getir(
    conn: sqlite3.Connection, anahtar: str, varsayilan: Optional[str] = None
) -> Optional[str]:
    row = conn.execute(
        "SELECT deger FROM ayarlar WHERE anahtar = ?", (anahtar,)
    ).fetchone()
    return row["deger"] if row else varsayilan


def ayar_ayarla(conn: sqlite3.Connection, anahtar: str, deger: str) -> None:
    conn.execute(
        "INSERT INTO ayarlar (anahtar, deger) VALUES (?, ?) "
        "ON CONFLICT(anahtar) DO UPDATE SET deger = excluded.deger",
        (anahtar, deger),
    )
    conn.commit()
