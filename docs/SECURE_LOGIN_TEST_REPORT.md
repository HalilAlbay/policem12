# Secure login test report

Date: 2026-10-28 (Europe/Istanbul)
Applicable specification: `POLICEM_CODEX_NIHAI_SARTNAME.md`
Baseline source: `d577d2a03a81a4f4cb79d4b39cde223ba79533e3`
P0 record commit: `6582a2ced6e3ea7d1a054579d8de49821e320a13`

## Environment and baseline

Python 3.11 did not contain pytest. A first package install attempt found no versions; a retried, uncached install succeeded in local `.venv` using Python 3.12, with repository requirements plus pytest and httpx. No environment or Render settings were changed.

| Command | Exit | Result |
|---|---:|---|
| `py -3.12 -m venv .venv; .venv\\Scripts\\python.exe -m pip install --no-cache-dir -r requirements.txt pytest httpx` | 0 | Dependencies installed. |
| `.venv\\Scripts\\python.exe -m pytest -q` | 1 | **32 passed, 7 failed, 19 warnings**, 13.28s. |
| `.venv\\Scripts\\python.exe -m compileall -q app.py customer_portal.py notification_core.py push_job.py push_service.py windows_main.py tests test_app.py test_deployment.py` | 0 | Python syntax compilation passed. |
| `node --check static/push-client.js` | 0 | Existing push client JavaScript syntax passed. |

### Baseline failures (all on unchanged source)

1. `test_app.py::test_staff_cannot_manage_users_or_see_other_staff_production`
2. `test_app.py::test_financial_reporting_is_partner_only`
3. `test_app.py::test_atomic_pdf_owner_uploader_and_insurer_summary`
4. `test_app.py::test_insurer_drilldown_scoped_to_own_production`
   - Their staff-creation requests omit `phone` and `start_date`, which current `add_user()` requires.
5. `test_app.py::test_branding_permissions_persistence_and_icon`
   - Expects the old default name `Poliçem`; current startup returns `Parantez Poliçem`.
6. `test_notification_core.py::NotificationTests::test_all_milestones`
   - Expects 30-day notification; current notification selector supports 15, 7, and 1 days.
7. `tests/test_quick_login.py::test_pin_refresh_and_lockout`
   - Secure refresh cookie is not sent by the plain HTTP TestClient, so `/api/security/refresh` correctly receives no cookie. This fixture needs an HTTPS-compatible client or explicit test-only transport setup before it can validate successful refresh.

No tests were skipped. The seven failures predate feature changes and will be distinguished from regressions on each subsequent stage.

## Acceptance status at P0

| Area | Status | Evidence / remaining work |
|---|---|---|
| Existing password login and generic errors | PARTIAL BASELINE | Existing app tests execute; see baseline failures. Add explicit authentication acceptance coverage. |
| Session idle, lock, draft clearing, logout/revoke | NOT IMPLEMENTED | No server idle timestamp or client lock exists. |
| Face ID/WebAuthn | NOT IMPLEMENTED | No WebAuthn library, challenges, credentials, or endpoints. |
| PIN device proof/lockout | SECURITY GAP | Current refresh-cookie + PIN path lacks signed device proof; do not represent as complete until resolved and tested. |
| Device and agency scope | PARTIAL | Branch-to-agency relationship exists; manager reset does not enforce agency relationship. |
| Verified email recovery | NOT IMPLEMENTED | No verified-email field or verification/reset token flow. Existing SMTP is reminders only. |
| Push recipient eligibility | GAP | Current scheduler selects user subscriptions without device activation/logout filtering. |
| Python syntax / current push JS syntax | PASSED | Commands above, exit 0. |
| Real iPhone Safari/Home Screen PWA and Face ID | PENDING USER ACCEPTANCE | No physical-device claim made. |

## Stage result rule

For each later stage, record the exact command and exit code, pass/fail/skip counts, known baseline failures, changed files, and commit SHA. Use **PASSED**, **FAILED**, or **NOT RUN** for every check. A test that cannot run is never counted as passed. Baseline failures do not stop independent work under the final specification, but critical security properties must have affirmative evidence before their feature is enabled.

## P2 — WebAuthn registration and discoverable login

| Command | Exit | Result |
|---|---:|---|
| `.venv\\Scripts\\python.exe -m py_compile app.py` | 0 | **PASSED** |
| `.venv\\Scripts\\python.exe -m pytest -q tests/test_webauthn.py tests/test_auth_session.py tests/test_device_sessions.py tests/test_quick_login.py` | 0 | **18 passed, 0 failed, 0 skipped** |
| `.venv\\Scripts\\python.exe -m pytest -q tests/test_webauthn.py::test_generated_platform_credential_registers_and_authenticates -x` | 0 | **PASSED**; generated EC2/ES256 credential registers and signs a discoverable assertion checked by the real server verifier |
| `git diff --check` | 0 | **PASSED** |

Test warnings: FastAPI `on_event` and Starlette TestClient/httpx deprecations; no P2 test failure. Physical iPhone/iOS Safari acceptance and production origin/RP configuration are **NOT RUN** (require the user’s real iPhone and target origin). The feature rejects missing/mismatched server configuration with 503.

## P3 — independent PIN plus browser-held device proof

| Command | Exit | Result |
|---|---:|---|
| `.venv\\Scripts\\python.exe -m pytest -q tests/test_webauthn.py tests/test_auth_session.py tests/test_device_sessions.py tests/test_quick_login.py` | 0 | **20 passed, 0 failed, 0 skipped** |
| `node --check static/pin-client.js` | 0 | **PASSED** |
| `.venv\\Scripts\\python.exe -m py_compile app.py` | 0 | **PASSED** |
| `git diff --check` | 0 | **PASSED** |

PIN tests prove enrollment is signed by the registered P-256 key, wrong signatures do not consume PIN guesses, five device-signed incorrect PINs lock the persisted grant, correct PIN issues a device-bound session, and revoke invalidates that session. PIN uses a WebCrypto non-extractable key in IndexedDB and never calls WebAuthn/Face ID. iOS Safari/PWA CryptoKey persistence still requires the user’s device acceptance test; if unavailable, PIN falls back to account password and must not be described as enabled on that install.

## P1 — sessions, idle lock, logout, and device revocation

| Command | Exit | Result |
|---|---:|---|
| `.venv\\Scripts\\python.exe -m pytest -q tests/test_auth_session.py tests/test_device_sessions.py tests/test_quick_login.py tests/test_staff_permissions.py` | 0 | **19 passed, 0 failed, 0 skipped, 15 warnings**, 11.82s. |
| `.venv\\Scripts\\python.exe -m pytest -q` | 1 | **40 passed, 6 failed, 0 skipped, 33 warnings**, 16.39s. Six failures remain from baseline: five `test_app.py` stale staff/branding expectations and `test_notification_core.py` 30-day milestone expectation. |
| `.venv\\Scripts\\python.exe -m compileall -q app.py tests` | 0 | Passed. |
| `node --check static/push-client.js` | 0 | Passed. |
| Extract inline script from `static/index.html`, then `node --check <temp file>` | 0 | Passed. |
| `git diff --check` | 0 | Passed. |

P1's legacy PIN prototype tests were updated to assert `METHOD_UNAVAILABLE` until a cryptographic device proof exists. The new focused tests cover the 900-second server boundary, background reads not sliding idle, actual interaction sliding, durable username throttling, generic account failures, configured-origin enforcement independent of Host, logout invalidation, additive/idempotent migration, and legacy hash preservation. P1 is complete; quick login remains disabled by design until P2/P3 provide and verify real proof.
