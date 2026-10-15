# Poliçem — Gerçek sunucu ve veritabanı başlangıcı

Bu proje önceki HTML demolarından farklı olarak FastAPI, SQLite, kullanıcı oturumları, rol yönetimi, kalıcı poliçe kayıtları, PDF metin çıkarma, yenileme bağlantısı, üretim raporları ve denetim kaydı içerir.

## Çalıştırma (MacBook / Windows / Linux)

Python 3.11+ gerekir.

```bash
cd policem_real_app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export POLICEM_ADMIN_PASSWORD='Güçlü-Ve-Benzersiz-Ilk-Sifre-2026!'
uvicorn app:app --host 127.0.0.1 --port 8000
```

Tarayıcıdan http://127.0.0.1:8000 açın. Kullanıcı adı `admin`, şifre ortam değişkeninde belirlediğiniz şifredir. Windows PowerShell'de aktivasyon `.venv\Scripts\Activate.ps1`, değişken tanımı `$env:POLICEM_ADMIN_PASSWORD='...'` biçimindedir.

**Önemli:** İlk başlatmada yönetici şifresi zorunludur. Sonraki başlatmalarda kayıtlı hesaplar korunur. Veri `data/` klasöründedir; yedekleyin.

## Hatırlatma

Günde bir kez `python reminder_job.py` çalıştırılmalıdır (cron, launchd, Task Scheduler). Hatırlatma sonuçları `reminders` tablosuna kaydedilir. SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM ortam değişkenleri varsa e-posta gönderimi denenir. SMTP yoksa sadece yerel kuyruğa kaydedilir. **Mobil push bildirimleri ve garantili e-posta teslimi henüz yoktur.**

## Sınırlar / üretime alma öncesi zorunlu işler

- Bu paket **APK değildir**; yerel sunucuda çalışan web uygulamasıdır. iOS/Android telefonlarından erişim için HTTPS'li, erişim kontrollü bir sunucuya dağıtım gerekir.
- PDF'de metin çıkarma ve örüntü tanıma vardır; taranmış PDF OCR, sigorta şirketine özel şablonlar ve yüksek doğrulukta AI ayrıştırma yoktur. İnsan kontrolü zorunludur.
- PDF dosyası kaydetme sırasında ayrı bir yükleme adımı vardır. Kayıt başarılı, belge yükleme başarısız olursa kayıt belge olmadan kalabilir; bu durum üretim öncesi tek işlem hâline getirilmelidir.
- Gerçek bildirim teslimi, teslim başarısızlığında tekrar deneme ve kullanıcı tercihleri tamamlanmadı.
- Şube/acenteler arasında veri yetki izolasyonu, istek sınırlandırma, hesap kilidi, MFA, CSRF/XSS güvenlik testi, KVKK süreçleri, şifreleme, profesyonel yedekleme, otomatik test kapsamı ve dış güvenlik denetimi tamamlanmadı. Gerçek müşteri poliçeleriyle internete açık kullanıma **uygun değildir**.
- Yönetici / personel ekranlarında üretim rakamlarının görünürlüğü kuruluş politikasına göre sunucuda sınırlandırılmalıdır. Bu ilk sürümde tüm oturum açanlar özet uç noktasını sorgulayabilir; üretimde kullanılmamalıdır.
- Mevcut poliçenin `external` işareti, takip ve kesim kaydından bağımsız olarak kullanıcı tarafından doğru seçilmelidir. Eski poliçelerin dönemi ve yeni üretimin dönemleri birbirinden ayrılmıştır.
- Dönem filtresi prim ve kesilen adet için kesim tarihine uygulanır; aktif ve yaklaşan kutuları bugünün durumunu gösterir. Bu fark UI'da daha görünür olmalıdır.

## Yönetici uygulama kimliği ayarları
Ayarlar > Uygulama kimliği bölümünde partner/manager kullanıcılar uygulama adını, kurumsal rengi ve PNG/JPEG/WebP simgesini değiştirebilir. Simge en fazla 2 MB olmalı, en az 64x64 piksel olmalı; sunucu simgeyi 512x512 PNG'ye dönüştürür. Ayarlar SQLite veritabanında saklanır. `GET /api/branding`, `PUT /api/branding`, `POST/DELETE /api/branding/icon`, `GET /manifest.webmanifest` kullanılır. Pillow bağımlılığı eklendi.

NOT: Mevcut telefon ana ekranı kısayollarının adı/simgesi platform önbelleği nedeniyle otomatik değişmeyebilir; yeniden ana ekrana eklemek gerekebilir. Bu özellik APK paketinin adı/simgesini çalışma sırasında değiştirmez. Kurulu native APK için ayrı paketleme gerekir.

## Finansal rapor yetkisi (2026-10-15)
- `/api/finance/summary` yalnızca `partner` rolüne açıktır (sunucu tarafında 403).
- `/api/summary`: `manager` rolüne prim toplamı verilmez ve `person_id` ile çalışan üretim raporu sorgulaması 403 döner.
- `staff` kendi prim ve adetlerini görebilir; farklı `person_id` parametresi yok sayılır.
- Arayüzde personel performans ekranı yalnızca ortak için gösterilir.
- Bu koruma finansal *özet* uç noktalarını kapsar. Poliçe listelerinde prim alanı hâlen bulunur; bütün finansal alanların gizlenmesi istenirse ayrı bir alan-bazlı yetki projesi gerekir.
- Test: `python -m pytest -q tests/test_app.py`.

## 2026-10-15 — PDF ve sigorta şirketi güncellemesi
- Çoklu PDF inceleme ekranında her PDF için ayrı **Sorumlu** seçimi bulunur; üstteki seçim yalnızca başlangıç değeridir.
- Yükleyen kimliği, oturumdan sunucu tarafında belirlenir ve tüm kayıtlarda ayrıca tutulur. Poliçe tablolarında **Sorumlu**, **Yükleyen** ve **Sigorta Şirketi** görünür.
- `POST /api/policies/with-document` PDF ve poliçeyi tek veritabanı işlemi kapsamında kaydeder; PDF okunamazsa poliçe oluşmaz. Dosya ve veritabanı ayrı depolama alanları olduğu için sistem çökmesi gibi uç durumlar için ayrıca kurtarma mekanizması gerekir.
- `GET /api/insurers/summary` dönem, poliçe türü ve (izin verilen roller için) personel filtresiyle şirket bazlı adet/prim döndürür. Personel yalnızca kendi satışlarını, ortak tüm satışları görür. Yönetici sadece adetleri görür.
- PDF tanıma motoru hâlâ sınırlıdır; OCR ve farklı şirket şablonları için ek geliştirme gereklidir.

### 2026-10-15 ekran düzeltmeleri
- Personel rolü için **Personel / Uzman Takibi** menüsü görünür; API kendi üretimiyle sınırlar. Yönetici rolü başka çalışanların finansal üretimine erişemez.
- Yönetici özeti ve uzman üretiminde sigorta şirketleri tıklanabilir kartlardır; tıklama seçili dönem/tür/personel kapsamındaki şirket poliçelerini listeler. Logo entegrasyonu henüz yoktur; doğrulanmamış marka logoları kullanılmaz.
- Poliçeleştirildi durumunda `prompt` pencereleri yerine doğrulamalı yeni poliçe formu açılır. Kaydetme, mevcut yenileme API'sini kullanır.
- Mevcut modüller ve veri modeli korunmuştur. Üretim ortamında cihaz ve kapsamlı güvenlik testleri ayrıca gereklidir.

## İlk hesap oluşturma (düzeltme)
Yeni ve boş bir kurulumda `POLICEM_ADMIN_PASSWORD` zorunlu değildir. Uygulamayı başlatıp tarayıcıdan açtığınızda **İlk Hesabı Oluştur** formu çıkar. Kullanıcı adı, ad soyad ve en az 12 karakterlik şifre girerek ilk **ortak** hesabını oluşturabilirsiniz. Sonra bu hesapla giriş yapıp diğer kullanıcıları oluşturabilirsiniz. İlk hesap oluşturulduktan sonra açık kayıt otomatik kapanır; mevcut hesaplar silinmez. `POLICEM_ADMIN_PASSWORD` ayarlanırsa eski otomatik `admin` oluşturma yöntemi de çalışır. Güvenlik nedeniyle ilk kurulumu yalnızca kendi bilgisayarınızda `127.0.0.1` adresinde yapın; uygulamayı henüz internete açmayın.
