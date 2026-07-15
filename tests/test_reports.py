from kasa_defteri import database, reports
from kasa_defteri.models import GELIR, GIDER, Islem


def _ekle(conn, tarih, tur, tutar, kategori=""):
    database.islem_ekle(conn, Islem(tarih=tarih, tur=tur, tutar=tutar, kategori=kategori))


def test_toplam_gelir_ve_gider(conn):
    _ekle(conn, "2024-01-05", GELIR, 1000.0)
    _ekle(conn, "2024-01-10", GIDER, 300.0)
    _ekle(conn, "2024-01-20", GIDER, 50.0)

    assert reports.toplam_gelir(conn) == 1000.0
    assert reports.toplam_gider(conn) == 350.0
    assert reports.donem_net_sonucu(conn) == 650.0


def test_guncel_kasa_bakiyesi_acilis_ile_birlikte(conn):
    reports.acilis_bakiyesini_ayarla(conn, 500.0)
    _ekle(conn, "2024-01-05", GELIR, 200.0)
    _ekle(conn, "2024-01-06", GIDER, 100.0)

    assert reports.guncel_kasa_bakiyesi(conn) == 600.0  # 500 + 200 - 100


def test_tarih_araligi_filtresi(conn):
    _ekle(conn, "2024-01-01", GELIR, 100.0)
    _ekle(conn, "2024-02-01", GELIR, 200.0)
    _ekle(conn, "2024-03-01", GELIR, 300.0)

    assert reports.toplam_gelir(conn, baslangic="2024-02-01") == 500.0
    assert reports.toplam_gelir(conn, bitis="2024-01-31") == 100.0
    assert reports.toplam_gelir(conn, baslangic="2024-02-01", bitis="2024-02-28") == 200.0


def test_aylik_ozet(conn):
    _ekle(conn, "2024-01-05", GELIR, 100.0)
    _ekle(conn, "2024-01-10", GIDER, 40.0)
    _ekle(conn, "2024-02-01", GELIR, 50.0)

    ozet = reports.aylik_ozet(conn)
    assert ozet == [
        {"ay": "2024-01", "gelir": 100.0, "gider": 40.0, "net": 60.0},
        {"ay": "2024-02", "gelir": 50.0, "gider": 0.0, "net": 50.0},
    ]


def test_kategori_bazli_ozet_buyukten_kucuge_siralanir(conn):
    _ekle(conn, "2024-01-01", GIDER, 50.0, kategori="Kira")
    _ekle(conn, "2024-01-02", GIDER, 200.0, kategori="Personel/Maaş")
    _ekle(conn, "2024-01-03", GIDER, 30.0, kategori="Kira")

    ozet = reports.kategori_bazli_ozet(conn, GIDER)
    assert ozet[0] == {"kategori": "Personel/Maaş", "toplam": 200.0}
    assert ozet[1] == {"kategori": "Kira", "toplam": 80.0}


def test_kasa_defteri_dokumu_bakiye_dogru_tasinir(conn):
    reports.acilis_bakiyesini_ayarla(conn, 1000.0)
    _ekle(conn, "2024-01-01", GELIR, 100.0)
    _ekle(conn, "2024-01-05", GIDER, 300.0)
    _ekle(conn, "2024-01-10", GELIR, 50.0)

    dokum = reports.kasa_defteri_dokumu(conn)
    bakiyeler = [d["bakiye"] for d in dokum]
    assert bakiyeler == [1100.0, 800.0, 850.0]


def test_kasa_defteri_dokumu_filtre_bakiyeyi_bozmaz(conn):
    reports.acilis_bakiyesini_ayarla(conn, 1000.0)
    _ekle(conn, "2024-01-01", GELIR, 100.0)  # filtre dışında ama bakiyeyi etkiler
    _ekle(conn, "2024-02-01", GIDER, 300.0)  # filtre içinde

    dokum = reports.kasa_defteri_dokumu(conn, baslangic="2024-02-01")
    assert len(dokum) == 1
    # 1000 (açılış) + 100 (ocak, görünmez) - 300 (şubat) = 800
    assert dokum[0]["bakiye"] == 800.0


def test_csv_disa_aktar(conn, tmp_path):
    _ekle(conn, "2024-01-01", GELIR, 100.0, kategori="Satış Geliri")
    _ekle(conn, "2024-01-02", GIDER, 40.0, kategori="Kira")

    hedef = tmp_path / "disa_aktarim.csv"
    reports.csv_olarak_disa_aktar(conn, hedef)

    assert hedef.exists()
    icerik = hedef.read_text(encoding="utf-8-sig")
    assert "Tarih;Açıklama" in icerik
    assert "100.00" in icerik
    assert "40.00" in icerik
