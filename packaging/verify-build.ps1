$ErrorActionPreference = "Stop"
$exe = Join-Path (Get-Location) "dist\PolicemServer\PolicemServer.exe"
if (!(Test-Path $exe)) { throw "EXE not found" }
Write-Output ("EXE SHA256: " + (Get-FileHash $exe -Algorithm SHA256).Hash)
Write-Output "Build artifact exists; runtime smoke tests still required."
