#Requires -RunAsAdministrator
param(
 [Parameter(Mandatory=$true)][string]$PublicHost,
 [string]$ProxyLoopbackPort = "8000"
)
$ErrorActionPreference = "Stop"
if ($PublicHost -notmatch '^[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]$' -or $PublicHost -notmatch '\.') { throw "PublicHost must be a DNS hostname, not a URL or IP address" }
if ($PublicHost -match '\.\.' -or $PublicHost.StartsWith("-")) { throw "Invalid hostname" }
$port = 0
if (-not [int]::TryParse($ProxyLoopbackPort, [ref]$port) -or $port -lt 1 -or $port -gt 65535) { throw "Invalid port" }
$root = Join-Path $env:ProgramData "Policem"
New-Item -ItemType Directory -Force -Path $root | Out-Null
$path = Join-Path $root "pilot-config.json"
if (Test-Path $path) { throw "Config exists: refusing to overwrite" }
$config = @{
  bind_host = "127.0.0.1"
  bind_port = $port
  public_origin = "https://$PublicHost"
  webauthn_rp_id = $PublicHost.ToLowerInvariant()
  data_dir = (Join-Path $root "data")
}
$config | ConvertTo-Json | Set-Content -Path $path -Encoding UTF8 -NoNewline
Write-Host "Pilot configuration saved: $path"
Write-Warning "Config is a template only. Wire it into service environment before launch. No TLS certificates or reverse proxy have been configured."
