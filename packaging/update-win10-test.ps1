# Opt-in update of Windows 10 TEST from a published GitHub release.
# Does not delete %LOCALAPPDATA%\PolicemTest\data.
$ErrorActionPreference='Stop'
$repo='HalilAlbay/policem12'
$asset='Policem_Setup_Win10_TEST.exe'
$api="https://api.github.com/repos/$repo/releases/latest"
try {
  $release=Invoke-RestMethod -Uri $api -Headers @{ 'User-Agent'='Policem-Win10-Updater'; 'Accept'='application/vnd.github+json' } -TimeoutSec 20
  $file=@($release.assets | Where-Object { $_.name -eq $asset }) | Select-Object -First 1
  $checksum=@($release.assets | Where-Object { $_.name -eq "$asset.sha256" }) | Select-Object -First 1
  if(-not $file -or -not $checksum){ throw 'Yayinlanmis kurulum paketi veya SHA256 dogrulama dosyasi bulunamadi.' }
  $current=(Get-Content "$PSScriptRoot\installed-release.txt" -ErrorAction SilentlyContinue | Select-Object -First 1)
  if($current -eq $release.tag_name){Write-Host 'Zaten guncel surum kurulu.'; Read-Host 'Cikmak icin Enter';exit 0}
  Write-Host "Yeni surum: $($release.tag_name)"
  $confirm=Read-Host 'Indirip kurmak istiyor musunuz? (E/H)'
  if($confirm -notin @('E','e')){exit 0}
  $tmp=Join-Path $env:TEMP ('PolicemUpdate-'+[guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $tmp | Out-Null
  $exe=Join-Path $tmp $asset
  $hashFile=Join-Path $tmp "$asset.sha256"
  Invoke-WebRequest -Uri $file.browser_download_url -OutFile $exe -TimeoutSec 180
  Invoke-WebRequest -Uri $checksum.browser_download_url -OutFile $hashFile -TimeoutSec 30
  $expected=((Get-Content $hashFile -Raw).Trim() -split '\s+')[0]
  if($expected -notmatch '^[a-fA-F0-9]{64}$'){throw 'Gecersiz SHA256 dosyasi.'}
  $actual=(Get-FileHash -Path $exe -Algorithm SHA256).Hash
  if($actual -ne $expected){throw 'SHA256 uyusmazligi. Kurulum iptal edildi.'}
  Write-Host 'Indirme dogrulandi. Policem uygulamasini kapatin.'
  Read-Host 'Uygulamayi kapattiktan sonra Enter'
  Start-Process -FilePath $exe -Wait
  # Only record version after installer exits successfully; Inno may return nonzero.
  # Installer exit-code check is handled below in a future update.
  Write-Host 'Kurulum penceresi tamamlandi. Veri klasorunuz korunur.'
} catch {
  Write-Host "Guncelleme basarisiz: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host 'Mevcut uygulama ve verileriniz degistirilmedi (kurulum baslamadiysa).'
}
Read-Host 'Cikmak icin Enter'
