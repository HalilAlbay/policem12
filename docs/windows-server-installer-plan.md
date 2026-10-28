# POLICEM-WIN-001 — Windows Server installer plan (pilot V1)

## Goal
Build Policem_Setup.exe from the verified Face ID baseline, with no system Python prerequisite, Windows service auto-start, durable SQLite/PDF storage, backups, and controlled HTTPS access for five staff/partners.

## Frozen source
Source: stable/policem-faceid-approved-2026-10-28
Development: feature/windows-server-installer-v1
Never modify the frozen branch or deployed TEST/PROD as part of installer work.

## Ordered work items
1. [IN PROGRESS] Inventory runtime, filesystem paths, external dependencies, startup/bootstrap, background jobs, and Windows Server requirements. No functional changes.
2. Build reproducible frozen executable (PyInstaller or equivalent); bundle static assets, PyMuPDF and WebAuthn dependencies. Verify clean machine startup.
3. Implement Windows service wrapper, controlled shutdown, health check, restart/recovery, and event logs. No administrator credentials stored in code.
4. Configure data path under ProgramData with restricted ACLs; install separate directories for DB, documents, logs and backups. Ensure upgrades preserve data.
5. Implement scheduled SQLite-consistent backup plus documents backup, off-host copy, retention, and tested restore. Do not claim safety before restore test.
6. Implement secure initial admin setup; secrets and config; migration-safe first launch.
7. Detect existing reverse proxy; configure HTTPS host/origin and WebAuthn RP ID. Do not auto-open internet ports. Require admin review for firewall/TLS changes.
8. Package installer (e.g. Inno Setup) with service install/uninstall, preflight checks, rollback, and data-preserving uninstall.
9. Add signed-release plan, installer checksums, clean Windows Server install/upgrade/uninstall tests, concurrent five-user test, biometric login, PDF upload/read, reminder scheduler, backup/restore tests.
10. Pilot acceptance and release checkpoint. Only then distribute Setup.exe.

## Current source observations (not full audit)
- app.py: FastAPI, SQLite WAL, POLICEM_DATA, frozen sys._MEIPASS resource root.
- requirements.txt: FastAPI, uvicorn, PyMuPDF, Pillow, pywebpush, webauthn.
- Dockerfile: app.py, customer_portal.py, reminder_job.py, notification_core.py, push_service.py, push_job.py and static/.
- README: reminder_job.py needs daily scheduling; HTTPS is necessary for mobile access; document upload and security limitations are documented.
- No verified Windows service or installer artifact yet.

## Gates / unresolved
- Determine Windows Server edition and CPU architecture; local administrator access and proxy/TLS details.
- Inspect full imports, relative file references, scheduled jobs, tests and deployment configuration.
- Do not place real policy/customer data on internet-facing pilot before minimum security, backups and recovery verification.
- Pilot V1 remains SQLite; multi-tenant V2 database migration is separate.
