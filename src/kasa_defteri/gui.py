"""Kasa Defteri masaüstü arayüzü (Tkinter).

Sekmeler:
    * Kasa Defteri     - kronolojik gelir/gider dökümü ve bakiye
    * Yeni Kayıt        - manuel gelir/gider girişi
    * E-Fatura İçe Aktar - GİB e-fatura XML/ZIP dosyalarından otomatik gider
    * Raporlar          - aylık ve kategori bazlı grafikler, açılış bakiyesi
"""

from __future__ import annotations

import argparse
import sqlite3
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import database, efatura_import, reports
from .models import GELIR, GIDER, Islem


def varsayilan_db_yolu() -> Path:
    """Kullanıcının ana dizininde uygulama verisi için klasör/dosya döner."""
    klasor = Path.home() / "KasaDefteri"
    klasor.mkdir(parents=True, exist_ok=True)
    return klasor / "kasa.db"


def tl_formatla(tutar: float) -> str:
    """1234.5 -> '1.234,50 TL' (Türkçe para biçimi)."""
    metin = f"{tutar:,.2f}"
    metin = metin.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{metin} TL"


class KasaDefteriApp(tk.Tk):
    def __init__(self, db_path: Path | None = None) -> None:
        super().__init__()
        self.title("Kasa Defteri")
        self.geometry("1080x680")
        self.minsize(900, 560)

        self.db_path = db_path or varsayilan_db_yolu()
        self.conn: sqlite3.Connection = database.get_connection(self.db_path)
        database.init_db(self.conn)

        self._arayuzu_kur()
        self.verileri_yenile()

    # ------------------------------------------------------------------
    # Genel arayüz iskeleti
    # ------------------------------------------------------------------
    def _arayuzu_kur(self) -> None:
        durum_cubugu = ttk.Label(
            self, text=f"Veritabanı: {self.db_path}", anchor="w", padding=(8, 2)
        )
        durum_cubugu.pack(side="bottom", fill="x")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self.defter_sekmesi = ttk.Frame(self.notebook, padding=10)
        self.yeni_kayit_sekmesi = ttk.Frame(self.notebook, padding=10)
        self.efatura_sekmesi = ttk.Frame(self.notebook, padding=10)
        self.raporlar_sekmesi = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.defter_sekmesi, text="Kasa Defteri")
        self.notebook.add(self.yeni_kayit_sekmesi, text="Yeni Kayıt")
        self.notebook.add(self.efatura_sekmesi, text="E-Fatura İçe Aktar")
        self.notebook.add(self.raporlar_sekmesi, text="Raporlar")

        self._defter_sekmesini_kur()
        self._yeni_kayit_sekmesini_kur()
        self._efatura_sekmesini_kur()
        self._raporlar_sekmesini_kur()

    def verileri_yenile(self) -> None:
        self._defteri_doldur()
        self._kategori_secimlerini_guncelle()

    # ------------------------------------------------------------------
    # Sekme 1: Kasa Defteri
    # ------------------------------------------------------------------
    def _defter_sekmesini_kur(self) -> None:
        ust = ttk.Frame(self.defter_sekmesi)
        ust.pack(fill="x", pady=(0, 8))

        ttk.Label(ust, text="Başlangıç (YYYY-AA-GG):").grid(row=0, column=0, padx=4)
        self.filtre_baslangic = ttk.Entry(ust, width=12)
        self.filtre_baslangic.grid(row=0, column=1, padx=4)

        ttk.Label(ust, text="Bitiş (YYYY-AA-GG):").grid(row=0, column=2, padx=4)
        self.filtre_bitis = ttk.Entry(ust, width=12)
        self.filtre_bitis.grid(row=0, column=3, padx=4)

        ttk.Button(ust, text="Filtrele", command=self._defteri_doldur).grid(
            row=0, column=4, padx=6
        )
        ttk.Button(ust, text="Temizle", command=self._filtreyi_temizle).grid(
            row=0, column=5, padx=4
        )
        ttk.Button(ust, text="CSV Dışa Aktar", command=self._csv_disa_aktar).grid(
            row=0, column=6, padx=4
        )
        ttk.Button(
            ust, text="Seçili Kaydı Sil", command=self._secili_kaydi_sil
        ).grid(row=0, column=7, padx=4)

        ozet = ttk.Frame(self.defter_sekmesi)
        ozet.pack(fill="x", pady=(0, 8))
        self.ozet_gelir_lbl = ttk.Label(ozet, text="Toplam Gelir: -", font=("TkDefaultFont", 10, "bold"))
        self.ozet_gider_lbl = ttk.Label(ozet, text="Toplam Gider: -", font=("TkDefaultFont", 10, "bold"))
        self.ozet_bakiye_lbl = ttk.Label(ozet, text="Güncel Bakiye: -", font=("TkDefaultFont", 10, "bold"))
        self.ozet_gelir_lbl.pack(side="left", padx=12)
        self.ozet_gider_lbl.pack(side="left", padx=12)
        self.ozet_bakiye_lbl.pack(side="left", padx=12)

        kolonlar = ("tarih", "aciklama", "kategori", "karsi_taraf", "belge_no", "gelir", "gider", "bakiye", "kaynak")
        basliklar = {
            "tarih": "Tarih",
            "aciklama": "Açıklama",
            "kategori": "Kategori",
            "karsi_taraf": "Karşı Taraf",
            "belge_no": "Belge No",
            "gelir": "Gelir",
            "gider": "Gider",
            "bakiye": "Bakiye",
            "kaynak": "Kaynak",
        }
        genislikler = {
            "tarih": 85, "aciklama": 220, "kategori": 120, "karsi_taraf": 160,
            "belge_no": 110, "gelir": 90, "gider": 90, "bakiye": 100, "kaynak": 70,
        }

        tablo_cercevesi = ttk.Frame(self.defter_sekmesi)
        tablo_cercevesi.pack(fill="both", expand=True)

        self.defter_tablosu = ttk.Treeview(
            tablo_cercevesi, columns=kolonlar, show="headings", selectmode="browse"
        )
        for k in kolonlar:
            self.defter_tablosu.heading(k, text=basliklar[k])
            self.defter_tablosu.column(k, width=genislikler[k], anchor="w")

        kaydirma = ttk.Scrollbar(
            tablo_cercevesi, orient="vertical", command=self.defter_tablosu.yview
        )
        self.defter_tablosu.configure(yscrollcommand=kaydirma.set)
        self.defter_tablosu.pack(side="left", fill="both", expand=True)
        kaydirma.pack(side="right", fill="y")

    def _filtreyi_temizle(self) -> None:
        self.filtre_baslangic.delete(0, "end")
        self.filtre_bitis.delete(0, "end")
        self._defteri_doldur()

    def _defteri_doldur(self) -> None:
        baslangic = self.filtre_baslangic.get().strip() or None
        bitis = self.filtre_bitis.get().strip() or None

        for satir in self.defter_tablosu.get_children():
            self.defter_tablosu.delete(satir)

        try:
            dokum = reports.kasa_defteri_dokumu(self.conn, baslangic, bitis)
        except Exception as exc:  # geçersiz tarih formatı vb.
            messagebox.showerror("Hata", f"Filtre uygulanamadı: {exc}")
            return

        for s in dokum:
            self.defter_tablosu.insert(
                "",
                "end",
                iid=str(s["id"]),
                values=(
                    s["tarih"],
                    s["aciklama"],
                    s["kategori"],
                    s["karsi_taraf"],
                    s["belge_no"],
                    f"{s['gelir']:.2f}" if s["gelir"] else "",
                    f"{s['gider']:.2f}" if s["gider"] else "",
                    f"{s['bakiye']:.2f}",
                    s["kaynak"],
                ),
            )

        toplam_gelir = reports.toplam_gelir(self.conn, baslangic, bitis)
        toplam_gider = reports.toplam_gider(self.conn, baslangic, bitis)
        guncel_bakiye = reports.guncel_kasa_bakiyesi(self.conn)
        self.ozet_gelir_lbl.config(text=f"Toplam Gelir: {tl_formatla(toplam_gelir)}")
        self.ozet_gider_lbl.config(text=f"Toplam Gider: {tl_formatla(toplam_gider)}")
        self.ozet_bakiye_lbl.config(text=f"Güncel Bakiye: {tl_formatla(guncel_bakiye)}")

    def _secili_kaydi_sil(self) -> None:
        secim = self.defter_tablosu.selection()
        if not secim:
            messagebox.showinfo("Bilgi", "Lütfen silinecek bir kayıt seçin.")
            return
        islem_id = int(secim[0])
        if not messagebox.askyesno("Onay", "Seçili kayıt silinsin mi?"):
            return
        database.islem_sil(self.conn, islem_id)
        self.verileri_yenile()

    def _csv_disa_aktar(self) -> None:
        hedef = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV dosyası", "*.csv")],
            initialfile="kasa_defteri.csv",
        )
        if not hedef:
            return
        baslangic = self.filtre_baslangic.get().strip() or None
        bitis = self.filtre_bitis.get().strip() or None
        reports.csv_olarak_disa_aktar(self.conn, hedef, baslangic, bitis)
        messagebox.showinfo("Tamamlandı", f"CSV dosyası kaydedildi:\n{hedef}")

    # ------------------------------------------------------------------
    # Sekme 2: Yeni Kayıt
    # ------------------------------------------------------------------
    def _yeni_kayit_sekmesini_kur(self) -> None:
        form = ttk.Frame(self.yeni_kayit_sekmesi)
        form.pack(anchor="nw", pady=10)

        ttk.Label(form, text="Tarih (YYYY-AA-GG):").grid(row=0, column=0, sticky="w", pady=4)
        self.yk_tarih = ttk.Entry(form, width=25)
        self.yk_tarih.insert(0, date.today().isoformat())
        self.yk_tarih.grid(row=0, column=1, pady=4)

        ttk.Label(form, text="Tür:").grid(row=1, column=0, sticky="w", pady=4)
        self.yk_tur = tk.StringVar(value=GIDER)
        tur_cercevesi = ttk.Frame(form)
        tur_cercevesi.grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(
            tur_cercevesi, text="Gelir", variable=self.yk_tur, value=GELIR,
            command=self._kategori_secimlerini_guncelle,
        ).pack(side="left")
        ttk.Radiobutton(
            tur_cercevesi, text="Gider", variable=self.yk_tur, value=GIDER,
            command=self._kategori_secimlerini_guncelle,
        ).pack(side="left")

        ttk.Label(form, text="Tutar (TL):").grid(row=2, column=0, sticky="w", pady=4)
        self.yk_tutar = ttk.Entry(form, width=25)
        self.yk_tutar.grid(row=2, column=1, pady=4)

        ttk.Label(form, text="Kategori:").grid(row=3, column=0, sticky="w", pady=4)
        kat_cercevesi = ttk.Frame(form)
        kat_cercevesi.grid(row=3, column=1, sticky="w")
        self.yk_kategori = ttk.Combobox(kat_cercevesi, width=22, state="readonly")
        self.yk_kategori.pack(side="left")
        ttk.Button(kat_cercevesi, text="+ Yeni", width=7, command=self._yeni_kategori_ekle).pack(
            side="left", padx=4
        )

        ttk.Label(form, text="Açıklama:").grid(row=4, column=0, sticky="w", pady=4)
        self.yk_aciklama = ttk.Entry(form, width=40)
        self.yk_aciklama.grid(row=4, column=1, pady=4, sticky="w")

        ttk.Label(form, text="Karşı Taraf:").grid(row=5, column=0, sticky="w", pady=4)
        self.yk_karsi_taraf = ttk.Entry(form, width=40)
        self.yk_karsi_taraf.grid(row=5, column=1, pady=4, sticky="w")

        ttk.Label(form, text="Belge No:").grid(row=6, column=0, sticky="w", pady=4)
        self.yk_belge_no = ttk.Entry(form, width=25)
        self.yk_belge_no.grid(row=6, column=1, pady=4, sticky="w")

        ttk.Button(form, text="Kaydet", command=self._kayit_ekle).grid(
            row=7, column=1, sticky="e", pady=12
        )

    def _yeni_kategori_ekle(self) -> None:
        ad = simpledialog.askstring("Yeni Kategori", "Kategori adı:", parent=self)
        if not ad:
            return
        database.kategori_ekle(self.conn, ad.strip(), self.yk_tur.get())
        self._kategori_secimlerini_guncelle()
        self.yk_kategori.set(ad.strip())

    def _kategori_secimlerini_guncelle(self) -> None:
        tur = self.yk_tur.get() if hasattr(self, "yk_tur") else GIDER
        kategoriler = database.kategorileri_listele(self.conn, tur)
        if hasattr(self, "yk_kategori"):
            self.yk_kategori["values"] = kategoriler
            if kategoriler and self.yk_kategori.get() not in kategoriler:
                self.yk_kategori.set(kategoriler[0])

    def _kayit_ekle(self) -> None:
        tarih = self.yk_tarih.get().strip()
        tur = self.yk_tur.get()
        tutar_metni = self.yk_tutar.get().strip().replace(",", ".")
        kategori = self.yk_kategori.get().strip()
        aciklama = self.yk_aciklama.get().strip()
        karsi_taraf = self.yk_karsi_taraf.get().strip()
        belge_no = self.yk_belge_no.get().strip()

        if not tarih:
            messagebox.showerror("Hata", "Tarih boş olamaz.")
            return
        try:
            date.fromisoformat(tarih)
        except ValueError:
            messagebox.showerror("Hata", "Tarih YYYY-AA-GG biçiminde olmalı.")
            return
        try:
            tutar = float(tutar_metni)
            if tutar <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Hata", "Tutar pozitif bir sayı olmalı.")
            return

        islem = Islem(
            tarih=tarih,
            tur=tur,
            tutar=tutar,
            kategori=kategori,
            aciklama=aciklama,
            karsi_taraf=karsi_taraf,
            belge_no=belge_no,
        )
        database.islem_ekle(self.conn, islem)

        self.yk_tutar.delete(0, "end")
        self.yk_aciklama.delete(0, "end")
        self.yk_karsi_taraf.delete(0, "end")
        self.yk_belge_no.delete(0, "end")

        self.verileri_yenile()
        self.notebook.select(self.defter_sekmesi)
        messagebox.showinfo("Kaydedildi", "Kayıt kasa defterine eklendi.")

    # ------------------------------------------------------------------
    # Sekme 3: E-Fatura İçe Aktar
    # ------------------------------------------------------------------
    def _efatura_sekmesini_kur(self) -> None:
        aciklama = (
            "GİB e-Fatura portalından indirilen UBL-TR formatındaki XML dosyalarını,\n"
            "içinde XML bulunan bir klasörü veya ZIP arşivini seçerek kasa defterine\n"
            "otomatik olarak aktarabilirsiniz. Daha önce aktarılmış faturalar (UUID ile)\n"
            "tekrar eklenmez."
        )
        ttk.Label(self.efatura_sekmesi, text=aciklama, justify="left").pack(anchor="w", pady=(0, 10))

        self.ef_tur = tk.StringVar(value=GIDER)
        tur_cercevesi = ttk.Frame(self.efatura_sekmesi)
        tur_cercevesi.pack(anchor="w", pady=(0, 10))
        ttk.Label(tur_cercevesi, text="İçe aktarma türü:").pack(side="left", padx=(0, 8))
        ttk.Radiobutton(
            tur_cercevesi, text="Gelen Fatura (Gider olarak ekle)", variable=self.ef_tur, value=GIDER
        ).pack(side="left")
        ttk.Radiobutton(
            tur_cercevesi, text="Giden Fatura (Gelir olarak ekle)", variable=self.ef_tur, value=GELIR
        ).pack(side="left")

        buton_cercevesi = ttk.Frame(self.efatura_sekmesi)
        buton_cercevesi.pack(anchor="w", pady=(0, 10))
        ttk.Button(buton_cercevesi, text="XML Dosyası Seç", command=self._efatura_dosya_sec).pack(
            side="left", padx=4
        )
        ttk.Button(buton_cercevesi, text="Klasör Seç", command=self._efatura_klasor_sec).pack(
            side="left", padx=4
        )
        ttk.Button(buton_cercevesi, text="ZIP Arşivi Seç", command=self._efatura_zip_sec).pack(
            side="left", padx=4
        )

        self.ef_log = tk.Text(self.efatura_sekmesi, height=20, wrap="word")
        self.ef_log.pack(fill="both", expand=True)
        self.ef_log.configure(state="disabled")

    def _log_yaz(self, metin: str) -> None:
        self.ef_log.configure(state="normal")
        self.ef_log.insert("end", metin + "\n")
        self.ef_log.see("end")
        self.ef_log.configure(state="disabled")

    def _efatura_sonuclarini_isle(self, sonuclar) -> None:
        basarili = sum(1 for s in sonuclar if s.basarili)
        atlanan = len(sonuclar) - basarili
        for s in sonuclar:
            isaret = "✔" if s.basarili else "•"
            self._log_yaz(f"{isaret} {s.dosya_adi}: {s.mesaj}")
        self._log_yaz(f"--- Toplam {len(sonuclar)} dosya, {basarili} aktarıldı, {atlanan} atlandı ---\n")
        self.verileri_yenile()

    def _efatura_dosya_sec(self) -> None:
        dosya = filedialog.askopenfilename(filetypes=[("e-Fatura XML", "*.xml")])
        if not dosya:
            return
        sonuc = efatura_import.dosyayi_ice_aktar(self.conn, dosya, self.ef_tur.get())
        self._efatura_sonuclarini_isle([sonuc])

    def _efatura_klasor_sec(self) -> None:
        klasor = filedialog.askdirectory()
        if not klasor:
            return
        sonuclar = efatura_import.klasoru_ice_aktar(self.conn, klasor, self.ef_tur.get())
        if not sonuclar:
            messagebox.showinfo("Bilgi", "Klasörde .xml dosyası bulunamadı.")
            return
        self._efatura_sonuclarini_isle(sonuclar)

    def _efatura_zip_sec(self) -> None:
        zip_dosyasi = filedialog.askopenfilename(filetypes=[("ZIP arşivi", "*.zip")])
        if not zip_dosyasi:
            return
        sonuclar = efatura_import.zip_ice_aktar(self.conn, zip_dosyasi, self.ef_tur.get())
        if not sonuclar:
            messagebox.showinfo("Bilgi", "ZIP içinde .xml dosyası bulunamadı.")
            return
        self._efatura_sonuclarini_isle(sonuclar)

    # ------------------------------------------------------------------
    # Sekme 4: Raporlar
    # ------------------------------------------------------------------
    def _raporlar_sekmesini_kur(self) -> None:
        ust = ttk.Frame(self.raporlar_sekmesi)
        ust.pack(fill="x", pady=(0, 10))

        ttk.Label(ust, text="Açılış Bakiyesi (TL):").pack(side="left", padx=(0, 6))
        self.rap_acilis = ttk.Entry(ust, width=15)
        self.rap_acilis.insert(0, f"{reports.acilis_bakiyesini_getir(self.conn):.2f}")
        self.rap_acilis.pack(side="left", padx=(0, 6))
        ttk.Button(ust, text="Kaydet", command=self._acilis_bakiyesi_kaydet).pack(side="left", padx=4)
        ttk.Button(ust, text="Grafikleri Yenile", command=self._grafikleri_ciz).pack(side="left", padx=12)

        self.grafik_alani = ttk.Frame(self.raporlar_sekmesi)
        self.grafik_alani.pack(fill="both", expand=True)

        self._grafikleri_ciz()

    def _acilis_bakiyesi_kaydet(self) -> None:
        try:
            tutar = float(self.rap_acilis.get().strip().replace(",", "."))
        except ValueError:
            messagebox.showerror("Hata", "Geçerli bir tutar girin.")
            return
        reports.acilis_bakiyesini_ayarla(self.conn, tutar)
        self.verileri_yenile()
        self._grafikleri_ciz()
        messagebox.showinfo("Kaydedildi", "Açılış bakiyesi güncellendi.")

    def _grafikleri_ciz(self) -> None:
        for widget in self.grafik_alani.winfo_children():
            widget.destroy()

        try:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        except ImportError:
            ttk.Label(
                self.grafik_alani,
                text="Grafikler için 'matplotlib' kurulu değil.\npip install matplotlib",
            ).pack(pady=20)
            return

        aylik = reports.aylik_ozet(self.conn)
        kategori_gider = reports.kategori_bazli_ozet(self.conn, GIDER)

        sol = ttk.Frame(self.grafik_alani)
        sag = ttk.Frame(self.grafik_alani)
        sol.pack(side="left", fill="both", expand=True)
        sag.pack(side="left", fill="both", expand=True)

        # Aylık gelir/gider bar grafiği
        fig1 = Figure(figsize=(5, 4), dpi=90)
        ax1 = fig1.add_subplot(111)
        if aylik:
            aylar = [a["ay"] for a in aylik]
            gelirler = [a["gelir"] for a in aylik]
            giderler = [a["gider"] for a in aylik]
            x = range(len(aylar))
            genislik = 0.35
            ax1.bar([i - genislik / 2 for i in x], gelirler, genislik, label="Gelir", color="#2e7d32")
            ax1.bar([i + genislik / 2 for i in x], giderler, genislik, label="Gider", color="#c62828")
            ax1.set_xticks(list(x))
            ax1.set_xticklabels(aylar, rotation=45, ha="right", fontsize=8)
            ax1.legend()
            ax1.set_title("Aylık Gelir / Gider")
        else:
            ax1.text(0.5, 0.5, "Henüz veri yok", ha="center", va="center")
        fig1.tight_layout()
        canvas1 = FigureCanvasTkAgg(fig1, master=sol)
        canvas1.draw()
        canvas1.get_tk_widget().pack(fill="both", expand=True)

        # Kategori bazlı gider pasta grafiği
        fig2 = Figure(figsize=(5, 4), dpi=90)
        ax2 = fig2.add_subplot(111)
        if kategori_gider:
            etiketler = [k["kategori"] for k in kategori_gider]
            degerler = [k["toplam"] for k in kategori_gider]
            ax2.pie(degerler, labels=etiketler, autopct="%1.0f%%", textprops={"fontsize": 8})
            ax2.set_title("Kategori Bazlı Gider Dağılımı")
        else:
            ax2.text(0.5, 0.5, "Henüz veri yok", ha="center", va="center")
        fig2.tight_layout()
        canvas2 = FigureCanvasTkAgg(fig2, master=sag)
        canvas2.draw()
        canvas2.get_tk_widget().pack(fill="both", expand=True)


def main() -> None:
    ayristirici = argparse.ArgumentParser(description="Kasa Defteri masaüstü uygulaması")
    ayristirici.add_argument(
        "--db", type=str, default=None, help="SQLite veritabanı dosya yolu (varsayılan: ~/KasaDefteri/kasa.db)"
    )
    args = ayristirici.parse_args()
    db_yolu = Path(args.db) if args.db else None

    uygulama = KasaDefteriApp(db_yolu)
    uygulama.mainloop()


if __name__ == "__main__":
    main()
