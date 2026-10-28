# Windows installer acceptance gates

## What the CI build now attempts
- Run Python backup/restore unit tests on Windows 2022.
- Build frozen FastAPI server and verify it starts/responds and initializes SQLite.
- Download pinned WinSW v2.12.0 binary, compile Inno Setup installer.
- Publish unsigned TEST-ONLY setup artifact on successful workflow completion.

## Not yet certified
- GitHub Actions run success and installer artifact existence have not been independently verified.
- Inno Setup install/uninstall on a clean Windows Server machine.
- Service registration, restricted identity, startup after reboot, graceful stop, logs and restart recovery.
- Secure HTTPS proxy and WebAuthn Face ID on final domain.
- Live migration, database preservation across upgrades, off-host backup and real restore drill.
- Concurrent five-user PDF workflow.
- Code signing and malware reputation checks.

## Security and installer limitations
- Inno Setup currently stages binaries and WinSW but intentionally DOES NOT register/start the service automatically.
- Service registration requires a reviewed service account and ProgramData ACLs. Do not deploy with real policies until approved.
- Existing installations are rejected instead of upgraded in place.
- No live data is removed by the package.
- No setup passwords or TLS secrets are embedded.
- Artifact is an engineering candidate, not a production-ready setup.
