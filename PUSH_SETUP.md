# Poliçem Web Push — kurulum ve doğrulama (geliştirme dalı)

Bu özellik henüz canlıya alınmadı. Gerçek iPhone/Android testleri ve
güvenlik incelemesi yapılmadan üretimde kullanmayın.

## Gereksinimler
- HTTPS erişimi olan Poliçem sunucusu (iPhone'da ana ekrana eklenmiş PWA).
- Kalıcı POLICEM_DATA dizini (SQLite veritabanı burada saklanır).
- pywebpush (requirements.txt içinde).
- Sunucuda VAPID anahtar çifti. Özel anahtarı GitHub'a yazmayın.
- Ortam değişkenleri: POLICEM_VAPID_PUBLIC_KEY,
  POLICEM_VAPID_PRIVATE_KEY, POLICEM_VAPID_SUBJECT (mailto:...).
- Sunucunun Apple/Google/Mozilla push servislerine dış HTTPS erişimi.

## Akış
1. Kullanıcı Poliçem'e giriş yapar.
2. Ana sayfadaki **Bildirimleri aç** düğmesine basar ve tarayıcı iznini verir.
3. Abonelik yalnızca oturum açmış kullanıcıya kaydedilir.
4. Windows Görev Zamanlayıcı her gün (Türkiye yerel saatiyle) `python push_job.py`
   komutunu çalıştırır. Çalışma dizini uygulamanın kurulu olduğu klasör olmalıdır.
5. İşlem 30, 15, 7, 1 gün eşiklerini kontrol eder. Gönderim başarısız olursa
   bir sonraki çalıştırmada yeniden dener (en fazla 5 deneme).
6. Kullanıcı **Bu cihazda kapat** düğmesiyle aboneliğini kaldırabilir.

## Otomatik kontroller
`python -m unittest -v test_notification_core test_push_service`
`python -m compileall -q notification_core.py push_service.py push_job.py app.py`

## Yayına çıkış engelleri
- Gerçek iPhone ve Android cihazlarında izin, kapalı uygulama, bildirim tıklama testi.
- VAPID yapılandırması ve HTTPS kurulumu.
- Görev zamanlayıcının tekrar başlatma sonrası çalıştığının doğrulanması.
- Güvenlik denetimi, gönderim uç noktası kötüye kullanım/SSRF kontrolleri.
- Kalıcı veri ve geri yükleme testi.
- Önceki Poliçem API ve kullanıcı giriş regresyon testleri.
- Yeni kullanıcı veya bildirim ayarı oluştururken gerçek müşteri verisi kullanmayın.
