# Windows 10 TEST updater. Uses published, SHA256-verified GitHub release assets.
$ErrorActionPreference = 'Stop'
$repo = 'HalilAlbay/policem12'
$asset = 'Policem_Setup_Win10_TEST.exe'
$api = "https://api.github.com/repos/$repo/releases/latest"
$headers = @{ 'User-Agent'='Policem-Win10-Updater'; 'Accept'='application/vnd.github+json' }
try {
  $release = Invoke-RestMethod -Uri $api -Headers $headers -TimeoutSec 25
  if ($release.tag_name -notmatch '^win10-test-\d+$') { throw 'En son yayin Windows 10 TEST kanalina ait degil.' }
  $file = @($release.assets | Where-Object { $_.name -eq $asset }) | Select-Object -First 1
  $checksum = @($release.assets | Where-Object { $_.name -eq "$asset.sha256" }) | Select-Object -First 1
  if (-not $file -or -not $checksum) { throw 'Test EXE veya SHA256 dosyasi yayinda bulunamadi.' }
  $versionFile = Join-Path $PSScriptRoot 'installed-release.txt'
  $current = (Get-Content $versionFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if ($current -eq $release.tag_name) {
    Write-Host "Policem guncel: $current" -ForegroundColor Green
    Read-Host 'Kapatmak icin Enter'
    exit 0
  }
  if ($current -match '^win10-test-(\d+)$' -and $release.tag_name -match '^win10-test-(\d+)$') {
    if ([long]$Matches[1] -le [long]($current -replace '^win10-test-','')) {
      Write-Host 'Kurulu surum yayinlanan surumden daha yeni veya esit.'
      Read-Host 'Kapatmak icin Enter'
      exit 0
    }
  }
  Write-Host "Kurulu surum: $(if($current){$current}else{'eski test paketi'})"
  Write-Host "Yeni surum: $($release.tag_name)"
  $confirm = Read-Host 'Guncellemeyi indirip kurmak istiyor musunuz? (E/H)'
  if ($confirm -notin @('E','e')) { exit 0 }
  $tmp = Join-Path $env:TEMP ('PolicemUpdate-' + [guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $tmp | Out-Null
  $exe = Join-Path $tmp $asset
  $hashFile = Join-Path $tmp "$asset.sha256"
  Invoke-WebRequest -Uri $file.browser_download_url -OutFile $exe -TimeoutSec 300
  Invoke-WebRequest -Uri $checksum.browser_download_url -OutFile $hashFile -TimeoutSec 30
  $expected = ((Get-Content $hashFile -Raw).Trim() -split '\s+')[0]
  if ($expected -notmatch '^[a-fA-F0-9]{64}$') { throw 'Gecersiz SHA256.' }
  if ((Get-FileHash $exe -Algorithm SHA256).Hash -ne $expected) { throw 'SHA256 uyusmazligi; kurulum iptal.' }
  Write-Host 'Paket dogrulandi. Policem TEST pencerelerini kapatin.'
  Read-Host 'Kapattiktan sonra Enter'
  $process = Start-Process -FilePath $exe -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CLOSEAPPLICATIONS','/NORESTARTAPPLICATIONS' -Wait -PassThru
  if ($process.ExitCode -ne 0) { throw "Kurulum basarisiz (cikis kodu: $($process.ExitCode))." }
  $installed = (Get-Content $versionFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if ($installed -ne $release.tag_name) { throw "Kurulum tamamlandi ancak surum dogrulanamadi. Beklenen: $($release.tag_name), bulunan: $installed" }
  Write-Host "Guncelleme basarili: $installed" -ForegroundColor Green
  Write-Host 'Mevcut veri klasoru korunmustur.'
} catch {
  Write-Host "Guncelleme basarisiz: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host 'Veri klasorunu silmeyin. Gerekirse kurulu surumu tekrar calistirin.'
}
Read-Host 'Kapatmak icin Enter'
