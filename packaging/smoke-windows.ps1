$ErrorActionPreference = "Stop"
$exe = Join-Path (Get-Location) "dist\PolicemServer\PolicemServer.exe"
if (!(Test-Path $exe)) { throw "Missing executable" }
$work = Join-Path $env:RUNNER_TEMP ("policem-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $work | Out-Null
$port = 18765
$env:POLICEM_DATA = Join-Path $work "data"
$env:POLICEM_BIND_HOST = "127.0.0.1"
$env:POLICEM_PORT = "$port"
$proc = Start-Process -FilePath $exe -PassThru -RedirectStandardOutput (Join-Path $work "stdout.log") -RedirectStandardError (Join-Path $work "stderr.log")
try {
  $ready = $false
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    if ($proc.HasExited) { break }
    try {
      $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 2
      if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
  }
  if (-not $ready) {
    Get-Content (Join-Path $work "stderr.log") -ErrorAction SilentlyContinue
    throw "Server failed HTTP smoke test"
  }
  if (!(Test-Path (Join-Path $env:POLICEM_DATA "policem.sqlite3"))) { throw "Database not initialized" }
  Write-Output "HTTP smoke test passed; SQLite created"
} finally {
  if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
  Remove-Item Env:POLICEM_DATA -ErrorAction SilentlyContinue
  Remove-Item Env:POLICEM_BIND_HOST -ErrorAction SilentlyContinue
  Remove-Item Env:POLICEM_PORT -ErrorAction SilentlyContinue
}
