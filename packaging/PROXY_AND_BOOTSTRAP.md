# Steps 6–7 — initial admin and HTTPS reverse proxy

## Initial admin
Run the initial bootstrap offline against the intended data directory with the service stopped:
python packaging/first-admin.py --data "<ProgramData>\\Policem\\data"
This script prompts for a password and refuses to reset an existing user. Do not put passwords or setup secrets in GitHub, command arguments, service XML, or logs. The current app.py also supports POLICEM_ADMIN_PASSWORD during startup; do not set it for the installed service. Audit startup to ensure first-launch behavior matches this bootstrap before pilot release.

## HTTPS / Face ID
The server binds to 127.0.0.1:8000 by default. Use an existing, managed HTTPS reverse proxy on the same host or a protected private network path. Set POLICEM_PUBLIC_ORIGIN=https://your-real-domain.example and WEBAUTHN_RP_ID=your-real-domain.example in the Windows service environment. The real hostname must be chosen before creating passkeys. A hostname change may require users to register passkeys again.

The configuration helper configure-pilot.ps1 only writes a proposed JSON file. It does not modify the Windows service or existing proxy. Proxy configuration and certificates must be reviewed against the office's actual proxy, DNS and Windows Server version. Never automatically expose port 8000 to the internet.

## Required acceptance checks
- Admin created once; re-run refuses and cannot reset password.
- No plaintext password appears in files, process arguments or logs.
- Valid HTTPS certificate; HTTP redirects to HTTPS; secure headers and correct forwarded headers only from trusted proxy.
- Server is unreachable directly from public network.
- Test login, logout, PIN and passkeys from iPhone and Android.
- Verify remote access only after authentication and authorization review.
- Record server OS version, DNS ownership, proxy product, service identity and firewall policy.
