# Windows 10 TEST only. Requires cloudflared from the official Cloudflare distribution.
$ErrorActionPreference = 'Stop'
$localUrl = 'http://127.0.0.1:8000'
Write-Host 'POLICEM - TELEFONDAN GUVENLI TEST' -ForegroundColor Cyan
Write-Host 'Bu mod yalnizca bu pencere acikken calisir.'
try {
  $r = Invoke-WebRequest -Uri "$localUrl/api/setup/status" -TimeoutSec 5 -UseBasicParsing
  if ($r.StatusCode -ne 200) { throw 'Server not ready' }
} catch {
  Write-Host 'Once masaustundeki Policem TEST uygulamasini acin ve giris ekraninin geldigini kontrol edin.' -ForegroundColor Red
  Read-Host 'Kapatmak icin Enter'
  exit 1
}
$cloudflared = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
if (-not $cloudflared) {
  Write-Host 'Cloudflared bulunamadi. Resmi Cloudflare aracini kurun: winget install --id Cloudflare.cloudflared -e' -ForegroundColor Yellow
  Write-Host 'Kurulumdan sonra bu pencereyi kapatip Telefon Testi kisayolunu yeniden acin.'
  Read-Host 'Kapatmak icin Enter'
  exit 1
}
$email = (Read-Host 'Telefonunuzda dogrulama kodu alacaginiz e-posta adresi').Trim()
if ($email -notmatch '^[^\s@]+@[^\s@]+\.[^\s@]+$') {
  Write-Host 'Gecerli bir e-posta adresi girilmedi. Tunel acilmadi.' -ForegroundColor Red
  Read-Host 'Kapatmak icin Enter'
  exit 1
}
Write-Host 'Ekranda https://...trycloudflare.com adresi belirdiginde telefondan acin.' -ForegroundColor Green
Write-Host 'E-posta kodu ve ardindan Policem kullanici adi/sifresi istenecek.'
Write-Host 'DURDURMAK ICIN CTRL+C. Linki baskalariyla paylasmayin.' -ForegroundColor Yellow
& $cloudflared.Source tunnel --no-autoupdate --url $localUrl --allowed-mail $email
