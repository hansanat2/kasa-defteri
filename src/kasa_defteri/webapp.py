"""Kasa Defteri web arayüzü (Flask, sadece localhost için).

Tkinter yerine tarayıcıdan kullanmak isteyenler için: `python app.py`
çalıştırıldığında http://127.0.0.1:5000 adresinde açılır. Alttaki
database/reports/efatura_import modülleri masaüstü sürümüyle birebir
aynıdır; sadece arayüz katmanı farklıdır.
"""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

from flask import (
    Flask,
    Response,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.utils import secure_filename

from . import database, efatura_import, reports
from .database import varsayilan_db_yolu
from .models import GELIR, GIDER, Islem

IZINLI_UZANTILAR = {".xml", ".zip"}


def tl_formatla(tutar: float) -> str:
    """1234.5 -> '1.234,50 TL' (Türkçe para biçimi)."""
    metin = f"{tutar:,.2f}"
    metin = metin.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{metin} TL"


def create_app(db_path: Optional[Path] = None) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "kasa-defteri-yerel-kullanim"  # sadece localhost, tek kullanıcı
    app.config["DB_PATH"] = db_path or varsayilan_db_yolu()
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB (e-fatura yüklemeleri için)

    app.jinja_env.filters["tl"] = tl_formatla

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = database.get_connection(app.config["DB_PATH"])
            database.init_db(g.db)
        return g.db

    @app.teardown_appcontext
    def close_db(exception=None) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()

    # ------------------------------------------------------------------
    # Kasa Defteri (ana sayfa)
    # ------------------------------------------------------------------
    @app.route("/")
    def index():
        conn = get_db()
        baslangic = request.args.get("baslangic") or None
        bitis = request.args.get("bitis") or None
        try:
            dokum = reports.kasa_defteri_dokumu(conn, baslangic, bitis)
        except Exception as exc:
            flash(f"Filtre uygulanamadı: {exc}", "error")
            dokum = reports.kasa_defteri_dokumu(conn)
            baslangic = bitis = None

        return render_template(
            "defter.html",
            dokum=dokum,
            baslangic=baslangic or "",
            bitis=bitis or "",
            toplam_gelir=reports.toplam_gelir(conn, baslangic, bitis),
            toplam_gider=reports.toplam_gider(conn, baslangic, bitis),
            guncel_bakiye=reports.guncel_kasa_bakiyesi(conn),
        )

    @app.route("/kayit/<int:islem_id>/sil", methods=["POST"])
    def kayit_sil(islem_id: int):
        conn = get_db()
        database.islem_sil(conn, islem_id)
        flash("Kayıt silindi.", "success")
        return redirect(url_for("index"))

    @app.route("/disa-aktar/csv")
    def csv_disa_aktar():
        conn = get_db()
        baslangic = request.args.get("baslangic") or None
        bitis = request.args.get("bitis") or None
        icerik = reports.csv_icerigi_uret(conn, baslangic, bitis)
        return Response(
            icerik,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=kasa_defteri.csv"},
        )

    # ------------------------------------------------------------------
    # Yeni Kayıt
    # ------------------------------------------------------------------
    @app.route("/yeni-kayit", methods=["GET", "POST"])
    def yeni_kayit():
        conn = get_db()

        if request.method == "POST":
            tarih = request.form.get("tarih", "").strip()
            tur = request.form.get("tur", GIDER)
            tutar_metni = request.form.get("tutar", "").strip().replace(",", ".")
            kategori = request.form.get("kategori", "").strip()
            yeni_kategori = request.form.get("yeni_kategori", "").strip()
            aciklama = request.form.get("aciklama", "").strip()
            karsi_taraf = request.form.get("karsi_taraf", "").strip()
            belge_no = request.form.get("belge_no", "").strip()

            hata = None
            try:
                date.fromisoformat(tarih)
            except ValueError:
                hata = "Tarih YYYY-AA-GG biçiminde olmalı."
            try:
                tutar = float(tutar_metni)
                if tutar <= 0:
                    raise ValueError
            except ValueError:
                hata = "Tutar pozitif bir sayı olmalı."

            if yeni_kategori:
                kategori = yeni_kategori
                database.kategori_ekle(conn, kategori, tur)

            if hata:
                flash(hata, "error")
            else:
                database.islem_ekle(
                    conn,
                    Islem(
                        tarih=tarih,
                        tur=tur,
                        tutar=tutar,
                        kategori=kategori,
                        aciklama=aciklama,
                        karsi_taraf=karsi_taraf,
                        belge_no=belge_no,
                    ),
                )
                flash("Kayıt kasa defterine eklendi.", "success")
                return redirect(url_for("index"))

        return render_template(
            "yeni_kayit.html",
            bugun=date.today().isoformat(),
            gelir_kategorileri=database.kategorileri_listele(conn, GELIR),
            gider_kategorileri=database.kategorileri_listele(conn, GIDER),
            form=request.form,
        )

    # ------------------------------------------------------------------
    # E-Fatura İçe Aktar
    # ------------------------------------------------------------------
    @app.route("/efatura", methods=["GET", "POST"])
    def efatura():
        sonuclar = []
        if request.method == "POST":
            conn = get_db()
            tur = request.form.get("tur", GIDER)
            dosyalar = request.files.getlist("dosyalar")

            with tempfile.TemporaryDirectory() as gecici:
                for dosya in dosyalar:
                    if not dosya or not dosya.filename:
                        continue
                    ad = secure_filename(dosya.filename)
                    uzanti = Path(ad).suffix.lower()
                    if uzanti not in IZINLI_UZANTILAR:
                        sonuclar.append(
                            efatura_import.IceAktarmaSonucu(
                                dosya.filename, False, "Desteklenmeyen dosya türü (.xml veya .zip olmalı)"
                            )
                        )
                        continue
                    hedef = Path(gecici) / ad
                    dosya.save(hedef)
                    if uzanti == ".zip":
                        sonuclar.extend(efatura_import.zip_ice_aktar(conn, hedef, tur))
                    else:
                        sonuclar.append(efatura_import.dosyayi_ice_aktar(conn, hedef, tur))

            if not sonuclar:
                flash("Hiçbir dosya seçilmedi.", "error")
            else:
                basarili = sum(1 for s in sonuclar if s.basarili)
                flash(f"{len(sonuclar)} dosyadan {basarili} tanesi aktarıldı.", "success")

        conn = get_db()
        return render_template(
            "efatura.html", sonuclar=sonuclar, sirket_vkn=reports.sirket_vkn_getir(conn)
        )

    @app.route("/efatura/sirket-bilgisi", methods=["POST"])
    def sirket_bilgisi_ayarla():
        conn = get_db()
        vkn = request.form.get("sirket_vkn", "").strip()
        reports.sirket_vkn_ayarla(conn, vkn)
        if vkn:
            flash("Şirket VKN'si kaydedildi. Bundan sonraki içe aktarmalarda yön otomatik belirlenecek.", "success")
        else:
            flash("Şirket VKN'si temizlendi. Yön artık yukarıda seçtiğiniz türe göre belirlenecek.", "success")
        return redirect(url_for("efatura"))

    # ------------------------------------------------------------------
    # Firmalar (e-fatura kaynaklı işlemlerin karşı tarafa göre dökümü)
    # ------------------------------------------------------------------
    @app.route("/firmalar")
    def firmalar():
        conn = get_db()
        baslangic = request.args.get("baslangic") or None
        bitis = request.args.get("bitis") or None

        ozet = reports.tedarikci_bazli_ozet(conn, GIDER, "efatura", baslangic, bitis)
        detaylar = {
            firma["karsi_taraf"]: reports.tedarikci_islemleri(
                conn, firma["karsi_taraf"], GIDER, "efatura", baslangic, bitis
            )
            for firma in ozet
        }

        return render_template(
            "firmalar.html",
            ozet=ozet,
            detaylar=detaylar,
            baslangic=baslangic or "",
            bitis=bitis or "",
        )

    # ------------------------------------------------------------------
    # Raporlar
    # ------------------------------------------------------------------
    @app.route("/raporlar")
    def raporlar():
        conn = get_db()
        aylik = reports.aylik_ozet(conn)
        kategori_gider = reports.kategori_bazli_ozet(conn, GIDER)
        return render_template(
            "raporlar.html",
            aylik=aylik,
            kategori_gider=kategori_gider,
            acilis_bakiyesi=reports.acilis_bakiyesini_getir(conn),
        )

    @app.route("/raporlar/acilis-bakiyesi", methods=["POST"])
    def acilis_bakiyesi_ayarla():
        conn = get_db()
        try:
            tutar = float(request.form.get("acilis_bakiyesi", "0").strip().replace(",", "."))
        except ValueError:
            flash("Geçerli bir tutar girin.", "error")
            return redirect(url_for("raporlar"))
        reports.acilis_bakiyesini_ayarla(conn, tutar)
        flash("Açılış bakiyesi güncellendi.", "success")
        return redirect(url_for("raporlar"))

    return app


def main() -> None:
    """`python app.py` ile çağrılan giriş noktası: sunucuyu başlatır."""
    import webbrowser
    from threading import Timer

    app = create_app()
    url = "http://127.0.0.1:5000"
    print(f"Kasa Defteri şu adreste çalışıyor: {url}")
    print("Durdurmak için bu pencerede Ctrl+C'ye basın.")
    Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
