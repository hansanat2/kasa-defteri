# Kasa Defteri

Küçük/orta ölçekli işletmeler için basit, açık kaynak bir **kasa defteri**
uygulaması. Gelir ve giderlerinizi kaydeder, kronolojik bakiye takibi yapar,
aylık ve kategori bazlı raporlar üretir; ayrıca **GİB e-Fatura** (UBL-TR)
XML dosyalarını otomatik olarak gider (veya gelir) kaydına dönüştürebilir.

İki arayüzü vardır, ikisi de aynı veritabanını ve iş mantığını kullanır:

- **Web arayüzü (önerilen)** — Flask ile, `python app.py` dedikten sonra
  tarayıcıda `http://127.0.0.1:5000` adresinde açılır. Sadece kendi
  bilgisayarınızda (localhost) çalışır, dışarıya açık değildir.
- **Masaüstü arayüzü** — Tkinter ile, `python main.py` dedikten sonra ayrı
  bir pencere açılır. (Not: bazı Mac/Linux kurulumlarında sistem Tk sürümü
  eskiyse pencere boş/beyaz açılabilir; bu durumda web arayüzünü kullanmanız
  önerilir.)

Alttaki katmanlar (`database.py`, `reports.py`, `efatura_import.py`) her iki
arayüzden de bağımsızdır — ileride farklı bir arayüze (örn. mobil, masaüstü
paketleme) taşımak da kolaydır.

## Özellikler

- **Kasa defteri görünümü**: tüm işlemleri tarih sırasına göre, her satırda
  o ana kadarki bakiyeyle birlikte listeler.
- **Manuel gelir/gider girişi**: tarih, tutar, kategori, açıklama, karşı
  taraf ve belge no alanlarıyla.
- **E-Fatura içe aktarma**: `.xml` dosyaları (tek veya çoklu seçim) ya da
  GİB portalından indirilen `.zip` paketi ile toplu içe aktarım yapılabilir.
  Aynı fatura (UUID ile) birden fazla kez eklenmez.
- **Otomatik kategori tahmini**: tedarikçi adına göre (ör. "...İLETİŞİM..."
  → İnternet/Telefon, "...YAZILIM..." → Yazılım/Abonelik) kaba bir
  kategorilendirme yapılır; kullanıcı istediği zaman değiştirebilir.
- **Raporlar**: aylık gelir/gider grafiği, kategori bazlı gider dağılımı
  (pasta grafik), açılış bakiyesi ayarı.
- **CSV dışa aktarım**: kasa defteri dökümünü Excel'de açılabilecek bir
  CSV dosyasına aktarır.
- **SQLite veritabanı**: tek dosya, kurulum gerektirmez, kolayca
  yedeklenebilir. Web ve masaüstü arayüzü aynı veritabanını
  (`~/KasaDefteri/kasa.db`) paylaşır.

## Kurulum

```bash
git clone <bu-repo-nun-adresi>
cd kasa-defteri
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> macOS'ta Homebrew Python kullanıyorsanız ("externally-managed-environment"
> hatası alırsanız) yukarıdaki venv adımları zaten bu sorunu çözer — venv
> dışında `pip install` çalıştırmayın.

## Çalıştırma — Web arayüzü (önerilen)

```bash
python app.py
```

Tarayıcı otomatik açılır (`http://127.0.0.1:5000`). Açılmazsa adresi elle
girin. Durdurmak için terminalde Ctrl+C.

## Çalıştırma — Masaüstü arayüzü

```bash
python main.py
```

Varsayılan olarak veritabanı `~/KasaDefteri/kasa.db` konumunda oluşturulur.
Farklı bir konum kullanmak için:

```bash
python main.py --db /baska/bir/yol/kasa.db
```

> **Not:** Tkinter çoğu Python kurulumunda hazır gelir. Linux'ta eksikse
> `sudo apt install python3-tk` ile kurabilirsiniz. macOS'ta sistem Python'u
> yerine güncel bir sürüm kullanmak isterseniz `brew install python-tk`
> yardımcı olur. Yine de sorun yaşarsanız web arayüzüne geçin.

## E-Fatura içe aktarma nasıl çalışır?

"E-Fatura İçe Aktar" sayfasından bir veya birden fazla `.xml` dosyası ya da
`.zip` arşivi seçebilirsiniz. Program her dosyadaki UBL-TR Invoice yapısını
(`cbc:ID`, `cbc:UUID`, `cbc:IssueDate`, `cac:AccountingSupplierParty`,
`cac:LegalMonetaryTotal` vb.) okuyup:

1. **Gelen Fatura** modunda → tedarikçiyi karşı taraf, faturayı **gider**
   kaydı olarak,
2. **Giden Fatura** modunda → müşteriyi karşı taraf, faturayı **gelir**
   kaydı olarak

kasa defterine ekler. Her faturanın `UUID`'si veritabanında benzersiz
tutulur; aynı dosya tekrar içe aktarılmaya çalışılırsa atlanır.

**Gizlilik uyarısı:** `.gitignore` dosyası, gerçek fatura XML'lerinizi ve
oluşan `kasa.db` veritabanını (finansal veri içerdikleri için) repoya dahil
etmeyecek şekilde ayarlanmıştır. Kendi faturalarınızı test etmek isterseniz
`data/` klasörüne kopyalayabilirsiniz; bu klasör Git tarafından takip
edilmez.

## Proje yapısı

```
kasa-defteri/
├── app.py                        # Web arayüzü giriş noktası (önerilen)
├── main.py                       # Masaüstü (Tkinter) giriş noktası
├── src/kasa_defteri/
│   ├── models.py                  # Islem veri modeli
│   ├── database.py                # SQLite şeması ve CRUD işlemleri
│   ├── efatura_import.py          # UBL-TR e-fatura XML ayrıştırıcı
│   ├── reports.py                 # Gelir/gider analiz ve raporlama
│   ├── gui.py                     # Tkinter masaüstü arayüzü
│   ├── webapp.py                  # Flask web arayüzü
│   └── templates/                 # Web arayüzü HTML şablonları
├── tests/                         # pytest test paketi (41 test)
│   └── fixtures/                  # Sentetik örnek e-fatura XML'leri
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
└── .github/workflows/tests.yml    # CI: her push'ta testleri çalıştırır
```

## Veritabanı şeması (özet)

- **islemler**: `tarih, tur (gelir/gider), tutar, kategori, aciklama,
  karsi_taraf, belge_no, vkn_tckn, kaynak (manuel/efatura), efatura_uuid`
- **kategoriler**: `ad, tur`
- **ayarlar**: anahtar/değer çiftleri (ör. `acilis_bakiyesi`)

## Testleri çalıştırma

```bash
pip install -r requirements-dev.txt
pytest -v
```

Testler; veritabanı CRUD işlemlerini, e-fatura ayrıştırmayı (sentetik
örnek XML'lerle), mükerrer fatura engellenmesini, rapor hesaplamalarını
(aylık özet, kategori kırılımı, bakiye taşıma mantığı) ve web arayüzünün
tüm rotalarını (Flask test client ile) kapsar.

## Yol haritası

- [ ] PyInstaller ile masaüstü sürümü için tek dosyalık `.exe` / `.app` paketleme
- [ ] Web arayüzünü Electron veya PyWebview ile masaüstü uygulamasına sarmalama
- [ ] Excel (.xlsx) formatında dışa aktarım
- [ ] Çoklu kasa/banka hesabı desteği
- [ ] Fatura satır kalemlerinin (KDV oranı bazında) ayrı ayrı raporlanması
- [ ] Kullanıcı girişi / kimlik doğrulama (web arayüzü ağ üzerinden paylaşılacaksa)

## Lisans

MIT — bkz. [LICENSE](LICENSE).
