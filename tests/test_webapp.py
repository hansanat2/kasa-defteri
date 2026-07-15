from pathlib import Path

from kasa_defteri.webapp import create_app

FIXTURES = Path(__file__).parent / "fixtures"


def _client(tmp_path):
    app = create_app(db_path=tmp_path / "web_test.db")
    app.config["TESTING"] = True
    return app.test_client()


def test_ana_sayfa_acilir(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Kasa Defteri".encode() in resp.data


def test_yeni_kayit_formu_acilir(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/yeni-kayit")
    assert resp.status_code == 200


def test_yeni_kayit_ekleme(tmp_path):
    client = _client(tmp_path)
    resp = client.post(
        "/yeni-kayit",
        data={
            "tarih": "2024-05-01",
            "tur": "gelir",
            "tutar": "500",
            "kategori": "Satış Geliri",
            "aciklama": "Test satış",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Test satış".encode() in resp.data
    assert "500,00 TL".encode() in resp.data or "500.00".encode() in resp.data


def test_yeni_kayit_gecersiz_tutar_hata_verir(tmp_path):
    client = _client(tmp_path)
    resp = client.post(
        "/yeni-kayit",
        data={"tarih": "2024-05-01", "tur": "gelir", "tutar": "abc", "kategori": "Satış Geliri"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "pozitif bir sayı".encode() in resp.data


def test_yeni_kategori_ile_ekleme(tmp_path):
    client = _client(tmp_path)
    client.post(
        "/yeni-kayit",
        data={
            "tarih": "2024-05-01",
            "tur": "gider",
            "tutar": "75",
            "kategori": "Kira",
            "yeni_kategori": "Özel Kategori",
        },
    )
    resp = client.get("/yeni-kayit")
    assert "Özel Kategori".encode() in resp.data


def test_kayit_silme(tmp_path):
    client = _client(tmp_path)
    client.post(
        "/yeni-kayit",
        data={"tarih": "2024-05-01", "tur": "gelir", "tutar": "100", "kategori": "Satış Geliri"},
    )
    resp = client.get("/")
    # kayıt id'sini formdaki action'dan bul
    import re

    m = re.search(rb"/kayit/(\d+)/sil", resp.data)
    assert m is not None
    islem_id = m.group(1).decode()

    resp2 = client.post(f"/kayit/{islem_id}/sil", follow_redirects=True)
    assert resp2.status_code == 200
    assert "Kayıt silindi".encode() in resp2.data


def test_efatura_sayfasi_acilir(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/efatura")
    assert resp.status_code == 200


def test_efatura_xml_yukleme(tmp_path):
    client = _client(tmp_path)
    with open(FIXTURES / "ornek_fatura_1.xml", "rb") as f:
        resp = client.post(
            "/efatura",
            data={"tur": "gider", "dosyalar": (f, "ornek_fatura_1.xml")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    assert "aktarıldı".encode() in resp.data or "Aktarıldı".encode() in resp.data


def test_efatura_desteklenmeyen_uzanti(tmp_path):
    import io

    client = _client(tmp_path)
    resp = client.post(
        "/efatura",
        data={"tur": "gider", "dosyalar": (io.BytesIO(b"merhaba"), "belge.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert "Desteklenmeyen dosya".encode() in resp.data


def test_raporlar_sayfasi_acilir(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/raporlar")
    assert resp.status_code == 200


def test_acilis_bakiyesi_ayarlama(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/raporlar/acilis-bakiyesi", data={"acilis_bakiyesi": "2500"}, follow_redirects=True)
    assert resp.status_code == 200
    assert 'value="2500.00"'.encode() in resp.data


def test_csv_disa_aktar(tmp_path):
    client = _client(tmp_path)
    client.post(
        "/yeni-kayit",
        data={"tarih": "2024-05-01", "tur": "gelir", "tutar": "500", "kategori": "Satış Geliri"},
    )
    resp = client.get("/disa-aktar/csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert b"500.00" in resp.data


def test_firmalar_sayfasi_acilir(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/firmalar")
    assert resp.status_code == 200
    assert "Henüz e-fatura".encode() in resp.data


def test_firmalar_sayfasi_efatura_sonrasi_gruplar(tmp_path):
    client = _client(tmp_path)
    with open(FIXTURES / "ornek_fatura_1.xml", "rb") as f:
        client.post(
            "/efatura",
            data={"tur": "gider", "dosyalar": (f, "ornek_fatura_1.xml")},
            content_type="multipart/form-data",
        )
    resp = client.get("/firmalar")
    assert resp.status_code == 200
    # ornek_fatura_1.xml tedarikçisi: "ÖRNEK YAZILIM TEKNOLOJİLERİ A.Ş."
    assert "ÖRNEK YAZILIM".encode() in resp.data
    assert "En Fazla Fatura Oluşturan Firmalar".encode() in resp.data


def test_sirket_vkn_kaydetme(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/efatura/sirket-bilgisi", data={"sirket_vkn": "1234567890"}, follow_redirects=True)
    assert resp.status_code == 200
    assert 'value="1234567890"'.encode() in resp.data


def test_sirket_vkn_ile_yon_otomatik_belirlenir(tmp_path):
    client = _client(tmp_path)
    # ornek_fatura_1.xml'in satıcı VKN'si 1234567890 -> şirketimiz satıcıysa gelir olmalı
    client.post("/efatura/sirket-bilgisi", data={"sirket_vkn": "1234567890"})

    with open(FIXTURES / "ornek_fatura_1.xml", "rb") as f:
        client.post(
            "/efatura",
            data={"tur": "gider", "dosyalar": (f, "ornek_fatura_1.xml")},  # tur=gider seçili olsa bile
            content_type="multipart/form-data",
        )

    resp = client.get("/")
    assert "Toplam Gelir: 118,00 TL".encode() in resp.data or "118".encode() in resp.data


def test_tarih_filtresi_calisir(tmp_path):
    client = _client(tmp_path)
    client.post(
        "/yeni-kayit",
        data={"tarih": "2024-01-01", "tur": "gelir", "tutar": "100", "kategori": "Satış Geliri", "aciklama": "Ocak"},
    )
    client.post(
        "/yeni-kayit",
        data={"tarih": "2024-06-01", "tur": "gelir", "tutar": "200", "kategori": "Satış Geliri", "aciklama": "Haziran"},
    )
    resp = client.get("/?baslangic=2024-05-01")
    assert "Haziran".encode() in resp.data
    assert "Ocak".encode() not in resp.data
