#Requires -RunAsAdministrator
param([string]$ServiceAccount = "NT AUTHORITY\LOCAL SERVICE")
$ErrorActionPreference = "Stop"
$root = Join-Path $env:ProgramData "Policem"
foreach ($folder in @($root, (Join-Path $root "data"), (Join-Path $root "data\documents"), (Join-Path $root "logs"), (Join-Path $root "backups"))) {
    New-Item -Path $folder -ItemType Directory -Force | Out-Null
}
# ACLs are intentionally explicit: administrators and SYSTEM retain control,
# service identity may modify application data/logs, not the backup directory.
& icacls.exe $root /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F'
if ($LASTEXITCODE -ne 0) { throw "Failed to secure storage root" }
foreach ($sub in @("data","logs")) {
    $path = Join-Path $root $sub
    & icacls.exe $path /grant "$($ServiceAccount):(OI)(CI)M"
    if ($LASTEXITCODE -ne 0) { throw "Failed to grant service access to $sub" }
}
Write-Host "Storage initialized: $root"
Write-Warning "Run service with the specified restricted identity; verify effective ACLs. Backups require separate privileged scheduled task."
