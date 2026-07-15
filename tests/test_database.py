from kasa_defteri import database
from kasa_defteri.models import GELIR, GIDER, Islem


def test_init_db_varsayilan_kategorileri_ekler(conn):
    kategoriler = database.kategorileri_listele(conn)
    assert "Kira" in kategoriler
    assert "Satış Geliri" in kategoriler


def test_islem_ekle_ve_listele(conn):
    islem = Islem(tarih="2024-01-10", tur=GELIR, tutar=1000.0, kategori="Satış Geliri")
    islem_id = database.islem_ekle(conn, islem)
    assert islem_id is not None

    kayitlar = database.islemleri_listele(conn)
    assert len(kayitlar) == 1
    assert kayitlar[0].tutar == 1000.0
    assert kayitlar[0].tur == GELIR


def test_islem_guncelle(conn):
    islem_id = database.islem_ekle(
        conn, Islem(tarih="2024-01-10", tur=GIDER, tutar=50.0, kategori="Ofis Malzemesi")
    )
    database.islem_guncelle(conn, islem_id, tutar=75.5, aciklama="Güncellendi")

    guncel = database.islem_getir(conn, islem_id)
    assert guncel.tutar == 75.5
    assert guncel.aciklama == "Güncellendi"


def test_islem_sil(conn):
    islem_id = database.islem_ekle(
        conn, Islem(tarih="2024-01-10", tur=GIDER, tutar=50.0)
    )
    database.islem_sil(conn, islem_id)
    assert database.islem_getir(conn, islem_id) is None


def test_islemleri_listele_filtreler(conn):
    database.islem_ekle(conn, Islem(tarih="2024-01-05", tur=GELIR, tutar=100.0))
    database.islem_ekle(conn, Islem(tarih="2024-02-05", tur=GIDER, tutar=40.0))
    database.islem_ekle(conn, Islem(tarih="2024-03-05", tur=GELIR, tutar=200.0))

    sonuc = database.islemleri_listele(conn, baslangic="2024-02-01")
    assert len(sonuc) == 2

    sonuc_gelir = database.islemleri_listele(conn, tur=GELIR)
    assert len(sonuc_gelir) == 2
    assert all(i.tur == GELIR for i in sonuc_gelir)


def test_efatura_uuid_ile_mukerrer_engellenir(conn):
    islem1 = Islem(
        tarih="2024-01-10", tur=GIDER, tutar=100.0, kaynak="efatura", efatura_uuid="abc-123"
    )
    islem2 = Islem(
        tarih="2024-01-11", tur=GIDER, tutar=999.0, kaynak="efatura", efatura_uuid="abc-123"
    )
    id1 = database.islem_ekle(conn, islem1)
    id2 = database.islem_ekle(conn, islem2)

    assert id1 is not None
    assert id2 is None  # mükerrer UUID reddedildi
    assert len(database.islemleri_listele(conn)) == 1


def test_manuel_kayitlarda_efatura_uuid_null_olabilir_ve_coklu_ekleme_calisir(conn):
    # UNIQUE(efatura_uuid) kısıtı NULL değerler için birden fazla satıra izin vermeli
    id1 = database.islem_ekle(conn, Islem(tarih="2024-01-01", tur=GIDER, tutar=10.0))
    id2 = database.islem_ekle(conn, Islem(tarih="2024-01-02", tur=GIDER, tutar=20.0))
    assert id1 is not None
    assert id2 is not None


def test_kategori_ekle_ve_listele(conn):
    database.kategori_ekle(conn, "Reklam", "gider")
    assert "Reklam" in database.kategorileri_listele(conn, tur="gider")


def test_ayar_getir_ve_ayarla(conn):
    assert database.ayar_getir(conn, "acilis_bakiyesi", "0") == "0"
    database.ayar_ayarla(conn, "acilis_bakiyesi", "1500.0")
    assert database.ayar_getir(conn, "acilis_bakiyesi") == "1500.0"

    # Var olan bir ayarı güncelleme (ON CONFLICT) doğru çalışmalı
    database.ayar_ayarla(conn, "acilis_bakiyesi", "2000.0")
    assert database.ayar_getir(conn, "acilis_bakiyesi") == "2000.0"
