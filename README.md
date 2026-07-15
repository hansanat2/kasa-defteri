# Kasa Defteri

Küçük/orta ölçekli işletmeler için basit, açık kaynak bir **kasa defteri**
uygulaması. Gelir ve giderlerinizi kaydeder, kronolojik bakiye takibi yapar,
aylık ve kategori bazlı raporlar üretir; ayrıca **GİB e-Fatura** (UBL-TR)
XML dosyalarını otomatik olarak gider (veya gelir) kaydına dönüştürebilir.

Şu an bir masaüstü GUI (Tkinter) olarak çalışır; alttaki katmanlar (veritabanı,
raporlama, e-fatura ayrıştırıcı) arayüzden bağımsız olduğu için ileride bir
web arayüzüne veya daha gelişmiş bir masaüstü uygulamasına (PySide/Qt,
Electron+API vb.) taşınmaya uygun şekilde tasarlanmıştır.

## Özellikler

- **Kasa defteri görünümü**: tüm işlemleri tarih sırasına göre, her satırda
  o ana kadarki bakiyeyle birlikte listeler.
- **Manuel gelir/gider girişi**: tarih, tutar, kategori, açıklama, karşı
  taraf ve belge no alanlarıyla.
- **E-Fatura içe aktarma**: tek bir `.xml` dosyası, bir klasör veya GİB
  portalından indirilen `.zip` paketi seçerek toplu içe aktarım yapılabilir.
  Aynı fatura (UUID ile) birden fazla kez eklenmez.
- **Otomatik kategori tahmini**: tedarikçi adına göre (ör. "...İLETİŞİM..."
  → İnternet/Telefon, "...YAZILIM..." → Yazılım/Abonelik) kaba bir
  kategorilendirme yapılır; kullanıcı istediği zaman değiştirebilir.
- **Raporlar**: aylık gelir/gider grafiği, kategori bazlı gider dağılımı
  (pasta grafik), açılış bakiyesi ayarı.
- **CSV dışa aktarım**: kasa defteri dökümünü Excel'de açılabilecek bir
  CSV dosyasına aktarır.
- **SQLite veritabanı**: tek dosya, kurulum gerektirmez, kolayca
  yedeklenebilir.

## Kurulum

```bash
git clone <bu-repo-nun-adresi>
cd kasa-defteri
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Çalıştırma

```bash
python main.py
```

Varsayılan olarak veritabanı `~/KasaDefteri/kasa.db` konumunda oluşturulur.
Farklı bir konum kullanmak için:

```bash
python main.py --db /baska/bir/yol/kasa.db
```

> **Not:** Tkinter çoğu Python kurulumunda hazır gelir. Linux'ta eksikse
> `sudo apt install python3-tk` ile kurabilirsiniz. macOS/Windows'ta
> python.org kurulumlarında ekstra bir şey gerekmez.

## E-Fatura içe aktarma nasıl çalışır?

"E-Fatura İçe Aktar" sekmesinden bir `.xml` dosyası, `.xml` dosyaları içeren
bir klasör ya da `.zip` arşivi seçebilirsiniz. Program her dosyadaki UBL-TR
Invoice yapısını (`cbc:ID`, `cbc:UUID`, `cbc:IssueDate`,
`cac:AccountingSupplierParty`, `cac:LegalMonetaryTotal` vb.) okuyup:

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
├── main.py                      # Uygulamayı başlatan giriş noktası
├── src/kasa_defteri/
│   ├── models.py                 # Islem veri modeli
│   ├── database.py               # SQLite şeması ve CRUD işlemleri
│   ├── efatura_import.py         # UBL-TR e-fatura XML ayrıştırıcı
│   ├── reports.py                # Gelir/gider analiz ve raporlama
│   └── gui.py                    # Tkinter masaüstü arayüzü
├── tests/                        # pytest test paketi (28 test)
│   └── fixtures/                 # Sentetik örnek e-fatura XML'leri
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
└── .github/workflows/tests.yml   # CI: her push'ta testleri çalıştırır
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
örnek XML'lerle), mükerrer fatura engellenmesini ve rapor hesaplamalarını
(aylık özet, kategori kırılımı, bakiye taşıma mantığı) kapsar.

## Yol haritası

- [ ] PyInstaller ile tek dosyalık `.exe` / `.app` paketleme
- [ ] Daha gelişmiş bir masaüstü arayüzü (PySide6/Qt) veya web arayüzü
      (aynı `database`/`reports`/`efatura_import` katmanları üzerinden)
- [ ] Excel (.xlsx) formatında dışa aktarım
- [ ] Çoklu kasa/banka hesabı desteği
- [ ] Fatura satır kalemlerinin (KDV oranı bazında) ayrı ayrı raporlanması

## Lisans

MIT — bkz. [LICENSE](LICENSE).
