from kasa_defteri import database, reports
from kasa_defteri.models import GELIR, GIDER, KAYNAK_EFATURA, KAYNAK_MANUEL, Islem


def _ekle(conn, tarih, tur, tutar, kategori=""):
    database.islem_ekle(conn, Islem(tarih=tarih, tur=tur, tutar=tutar, kategori=kategori))


def _efatura_ekle(conn, tarih, tutar, karsi_taraf, vkn_tckn="", uuid=None, tur=GIDER):
    database.islem_ekle(
        conn,
        Islem(
            tarih=tarih,
            tur=tur,
            tutar=tutar,
            karsi_taraf=karsi_taraf,
            vkn_tckn=vkn_tckn,
            kaynak=KAYNAK_EFATURA,
            efatura_uuid=uuid or f"uuid-{tarih}-{karsi_taraf}-{tutar}",
        ),
    )


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


def test_tedarikci_bazli_ozet_gruplar_ve_toplar(conn):
    _efatura_ekle(conn, "2024-01-01", 100.0, "Firma A", vkn_tckn="111")
    _efatura_ekle(conn, "2024-01-15", 150.0, "Firma A", vkn_tckn="111")
    _efatura_ekle(conn, "2024-02-01", 50.0, "Firma B", vkn_tckn="222")

    ozet = reports.tedarikci_bazli_ozet(conn)
    assert len(ozet) == 2

    firma_a = next(f for f in ozet if f["karsi_taraf"] == "Firma A")
    assert firma_a["adet"] == 2
    assert firma_a["toplam"] == 250.0
    assert firma_a["ortalama"] == 125.0
    assert firma_a["vkn_tckn"] == "111"
    assert firma_a["ilk_tarih"] == "2024-01-01"
    assert firma_a["son_tarih"] == "2024-01-15"


def test_tedarikci_bazli_ozet_fatura_adedine_gore_siralanir(conn):
    _efatura_ekle(conn, "2024-01-01", 500.0, "Az Fatura Çok Tutar")
    _efatura_ekle(conn, "2024-01-01", 10.0, "Çok Fatura Az Tutar", uuid="u1")
    _efatura_ekle(conn, "2024-01-02", 10.0, "Çok Fatura Az Tutar", uuid="u2")
    _efatura_ekle(conn, "2024-01-03", 10.0, "Çok Fatura Az Tutar", uuid="u3")

    ozet = reports.tedarikci_bazli_ozet(conn)
    assert ozet[0]["karsi_taraf"] == "Çok Fatura Az Tutar"
    assert ozet[0]["adet"] == 3


def test_tedarikci_bazli_ozet_sadece_efatura_kaynaklilari_kapsar(conn):
    _efatura_ekle(conn, "2024-01-01", 100.0, "E-Fatura Firması")
    database.islem_ekle(
        conn,
        Islem(tarih="2024-01-01", tur=GIDER, tutar=999.0, karsi_taraf="Manuel Girilen", kaynak=KAYNAK_MANUEL),
    )

    ozet = reports.tedarikci_bazli_ozet(conn)
    isimler = [f["karsi_taraf"] for f in ozet]
    assert "E-Fatura Firması" in isimler
    assert "Manuel Girilen" not in isimler


def test_tedarikci_islemleri_dogru_firmayi_filtreler(conn):
    _efatura_ekle(conn, "2024-01-01", 100.0, "Firma A", uuid="u1")
    _efatura_ekle(conn, "2024-01-02", 200.0, "Firma B", uuid="u2")

    islemler = reports.tedarikci_islemleri(conn, "Firma A")
    assert len(islemler) == 1
    assert islemler[0].tutar == 100.0
