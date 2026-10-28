# Prototype service registration. Requires a trusted, separately obtained WinSW executable.
# Do not expose the port publicly. TLS reverse proxy configuration is a separate gated step.
#Requires -RunAsAdministrator
param(
  [Parameter(Mandatory=$true)][string]$WinSWExe,
  [Parameter(Mandatory=$true)][string]$ServerDirectory
)
$ErrorActionPreference = "Stop"
$root = Join-Path $env:ProgramData "Policem"
foreach ($sub in @("data", "logs", "backups")) {
  New-Item -ItemType Directory -Force -Path (Join-Path $root $sub) | Out-Null
}
$server = Join-Path $ServerDirectory "PolicemServer.exe"
if (-not (Test-Path $server)) { throw "Server executable missing: $server" }
if (-not (Test-Path $WinSWExe)) { throw "WinSW executable missing" }
$target = Join-Path $ServerDirectory "PolicemService.exe"
$xml = Join-Path $ServerDirectory "PolicemService.xml"
if (Test-Path $target) { throw "Service wrapper already present; refusing overwrite" }
Copy-Item $WinSWExe $target
Copy-Item (Join-Path $PSScriptRoot "PolicemService.xml") $xml
Write-Warning "Prototype only: service identity/ACLs, backup and recovery are NOT configured. Do not use with real customer data."
& $target install
if ($LASTEXITCODE -ne 0) { throw "WinSW install failed" }
Write-Host "Service registered but not started. Configure restricted service identity and ACLs before starting."
