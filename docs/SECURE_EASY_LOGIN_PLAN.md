# POLICEM — KOLAY GİRİŞ UYGULAMA PLANI (2026-10-27)

## Korunan temel
- Üretimdeki TEST deploy: d6350ee5a013c9f192800154971e787684419be4 (Render LIVE)
- Değiştirilmeyecek sabit dal: stable/policem-personnel-ui-working-2026-10-27
- Çalışma dalı: feature/secure-easy-login
- Push notification/service worker, personel yönetimi ve mevcut API davranışları regresyonla korunacak.
- Bu planın eklenmesi özelliklerin tamamlandığı anlamına gelmez.

## Mevcut kod incelemesi
- app.py: users.password_hash PBKDF2-HMAC-SHA256 (350000 iterasyon, rastgele salt).
- app.py: sessions(token_hash,user_id,expires); login 24 saatlik bearer oturumu oluşturuyor.
- app.py: current() bearer token doğruluyor; password değişikliği kullanıcının tüm oturumlarını siliyor.
- static/index.html: token sessionStorage['policem_token']; boot() /api/me ile doğruluyor.
- static/index.html: Ayarlar içinde şifre değiştirme mevcut; cihaz yönetimi ve giriş yöntemi ayarı yok.
- requirements.txt: WebAuthn doğrulama bağımlılığı henüz yok.
- Sadece istemci tarafında PIN kontrolü veya kalıcı bearer token saklama güvenli kabul edilmeyecek.

## Tasarım ve sıra
1. Veritabanı migration: trusted_devices, webauthn_credentials, refresh_session/device_session, auth_events; migration geriye uyumlu, mevcut oturumlar korunur.
2. Cihaz kayıt/iptal API'leri: kimlik doğrulanmış kullanıcıya ait kayıt; yeniden kimlik doğrulama; cihaz iptalinde bağlı oturumlar geçersiz.
3. Passkey/WebAuthn: challenge sunucuda tek kullanımlık ve kısa ömürlü; RP ID/origin doğrulaması; authenticatorData, signature, user verification ve sign counter kontrolü; hesap ile credential eşleşmesi.
4. PIN: yalnızca cihazda donanım/OS korumalı kimlik bilgisiyle birlikte kullanılır. Dört haneli PIN'i salt JS veya localStorage içinde saklanan gizli anahtarı çözmek için tek güvenlik katmanı olarak kullanma. Web/PWA'da OS destekleri ve cihaz PIN'inin 4 haneli olup olmayacağı değişir; uygulama içi 4 haneli PIN için ayrı güvenli cihaz bağlama ve deneme sayacı tasarımı, tehdit modeli ve test gerekir. Sunucu doğrulaması, 5 deneme sınırı, hız sınırlama, kayıtlı cihaz iptali şart.
5. Ayarlar > Güvenlik ve Giriş: kullanıcı yöntemini bir defa seçer; normal açılışta yöntem seçme menüsü gösterilmez; erişilebilir şifreye dönüş yolu bulunur.
6. Otomatik kilit: 15 dakika hareketsizlik, arka plana geçiş/geri dönüş ve oturum sonlanması senaryoları; kilit ekranı gerçek sunucu yetkisini de sınırlar.
7. Şifremi unuttum: doğrulanmış e-posta, 15 dakika tek kullanımlık sıfırlama, genel cevap ile hesap keşfini engelleme, hız sınırı; yönetici destekli akış ayrı yetki ve audit; mail sağlayıcısı seçilmeden canlıya alınmaz.
8. Test: yeni/eski cihaz, logout, password reset, revoke, 5 yanlış PIN, cihaz kaybı, WebAuthn replay/origin, Safari iOS PWA ve Android, push bildirimleri, personel rolleri.
9. Yayın: yalnızca testlerden sonra, açık onayla; Render TEST izlediği dalı değiştirmeden güvenli entegrasyon.

## Dosya sahipliği
- app.py: mevcut auth ve migration, minimal değişiklik.
- Yeni auth modülü: cihaz, challenge ve kimlik doğrulama akışları.
- static/index.html: yalnızca Ayarlar ve giriş akışı.
- tests/: kimlik doğrulama ve regresyon.
- requirements.txt: denetlenmiş ve sabitlenmiş WebAuthn bağımlılığı.
- push_service.py, service worker ve bildirim uçları: kapsam dışı, değişmeyecek.

## Kabul koşulları
- Yeni güvenilir cihaz ilk defa mevcut hesap şifresiyle doğrulanmadan kaydedilemez.
- PIN tek başına uzaktan brute-force edilemez.
- Kullanıcı giriş yöntemini Ayarlar'dan seçer; ana ekranda yöntem menüsü yok.
- Kayıp cihaz erişimi iptal edilebilir; şifre değişikliği eski erişimleri keser.
- iPhone PWA'da gerçekten çalıştığı doğrulanır; desteklenmeyen biyometrik özelliklerde güvenli şifre alternatifi.
- Bildirim sistemi, personel yönetimi, poliçe akışları bozulmaz.
