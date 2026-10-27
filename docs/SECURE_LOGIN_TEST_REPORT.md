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

## P4 — selected method, switching, and device/PWA settings

| Command | Exit | Result |
|---|---:|---|
| `.venv\\Scripts\\python.exe -m pytest -q tests/test_webauthn.py tests/test_auth_session.py tests/test_device_sessions.py tests/test_quick_login.py` | 0 | **21 passed, 0 failed, 0 skipped** |
| `.venv\\Scripts\\python.exe -m py_compile app.py` | 0 | **PASSED** |
| `node --check static/pin-client.js` | 0 | **PASSED** |
| `node --check static/login-preference.js` | 0 | **PASSED** |
| `git diff --check` | 0 | **PASSED** |

P4 tests verify a selected PIN is the only quick method offered, failed passkey switching preserves the PIN selection, successful passkey switch revokes the old PIN device/key atomically, and only one inventory device is selected. Browser-level Safari PWA testing remains **NOT RUN**.

## P5 — officer reset and verified email recovery

| Command | Exit | Result |
|---|---:|---|
| `.venv\\Scripts\\python.exe -m pytest -q tests/test_account_recovery.py` | 0 | **4 passed, 0 failed, 0 skipped** |
| `.venv\\Scripts\\python.exe -m py_compile app.py` | 0 | **PASSED** |
| `node --check static/account-recovery.js` | 0 | **PASSED** |
| `git diff --check` | 0 | **PASSED** |

Coverage: same-agency officer-issued temporary password, old-session invalidation, forced first-login password change and API lockout, cross-agency denial, audit actor/target without secret, mocked TLS SMTP verification/reset link completion, generic unknown-vs-known reset responses, single-use tokens, and fail-closed missing SMTP while normal password login remains available. Real mail delivery remains **NOT RUN** because no SMTP secrets/provider are configured.

## P6 — device-scoped notification eligibility

| Command | Exit | Result |
|---|---:|---|
| `.venv\\Scripts\\python.exe -m pytest -q test_push_service.py test_push_integration.py tests/test_device_sessions.py tests/test_quick_login.py` | 0 | **23 passed, 0 failed, 0 skipped** after device-scoped cases were added. |
| `node --check static/push-client.js` | 0 | **PASSED** |
| `.venv\\Scripts\\python.exe -m py_compile app.py push_service.py push_job.py` | 0 | **PASSED** |
| `git diff --check` | 0 | **PASSED** |

Coverage includes password-only session denial, fail-closed migration of legacy subscriptions, other-user ownership isolation, current-device logout and revoke suppression, continued delivery to another active device, scheduler idempotence, renewal cancellation, and owner-transfer cancellation. Physical push delivery to an iPhone and real VAPID configuration remain **NOT RUN**; no external push was sent.

## P7 — integration and final verification

| Command | Exit | Result |
|---|---:|---|
| `.venv\\Scripts\\python.exe -m pytest -q` | 1 | **59 passed, 6 failed, 0 skipped, 41 warnings**, 31.13s. The six failures are listed below and match the pre-change failures. |
| `.venv\\Scripts\\python.exe -m compileall -q app.py push_service.py push_job.py notification_core.py tests test_push_service.py test_push_integration.py` | 0 | **PASSED** |
| `node --check static/pin-client.js` | 0 | **PASSED** |
| `node --check static/login-preference.js` | 0 | **PASSED** |
| `node --check static/account-recovery.js` | 0 | **PASSED** |
| `node --check static/push-client.js` | 0 | **PASSED** |
| `git diff --check` | 0 | **PASSED** |

Full-suite failures (also present at P0; not caused by the secure-login stages):

1. `test_app.py::test_staff_cannot_manage_users_or_see_other_staff_production` — fixture omits required staff fields; expected HTTP 200, got 400.
2. `test_app.py::test_branding_permissions_persistence_and_icon` — test expects the old default branding name.
3. `test_app.py::test_financial_reporting_is_partner_only` — stale staff creation request expects HTTP 200, got 400.
4. `test_app.py::test_atomic_pdf_owner_uploader_and_insurer_summary` — stale staff creation request expects HTTP 200, got 400.
5. `test_app.py::test_insurer_drilldown_scoped_to_own_production` — stale staff creation request expects HTTP 200, got 400.
6. `test_notification_core.py::NotificationTests::test_all_milestones` — expects a 30-day milestone while the current scheduler supports 15, 7, and 1 days.

All targeted stage suites passed, including the final P6/P7 24-test push/device suite and P5's four recovery tests. The full suite has no skipped tests. The pre-existing six failures are left unchanged because altering personnel/branding/renewal behavior is outside this specification and risks working features. Syntax checks are not represented as functional acceptance.

### iPhone acceptance checklist — pending user test

- [ ] Open the deployed canonical HTTPS origin in iPhone Safari and sign in with the existing username and account password.
- [ ] Add to Home Screen, open the installed PWA, confirm saved policy/personnel screens remain available, and enroll one method only.
- [ ] Passkey/WebAuthn: verify actual system authentication prompt and successful reopen; cancel enrollment and verify the prior method remains selected. iOS may use device passcode or a synced passkey; this does not prove physical-device-only possession.
- [ ] PIN: enter matching four-digit values twice, reopen/unlock without a Face ID prompt, verify five wrong PIN attempts keep the PIN grant locked after force-quit/reopen, then use the account password fallback.
- [ ] Leave the app idle/backgrounded for 15 minutes; confirm it locks, unsaved text/selections/files/modals clear, and saved records remain intact. Confirm ordinary idle lock alone does not suppress push.
- [ ] In Security and Login, verify selected method/device, change method with account password, revoke a lost device, and confirm its bound session/quick-login grant no longer works.
- [ ] Have an authorized same-agency officer issue a temporary password; verify forced password change and old device/session invalidation. Verify cross-agency reset is denied.
- [ ] Verify email using the real mailbox link; test password reset, generic account response, one-use link, and actual SMTP delivery.
- [ ] Explicitly enable notifications on the PWA, close the app, and confirm a real due-policy notification arrives. Log out/revoke that device and confirm it stops; confirm any other active authorized receiving device still receives. Enable a new device only after login, device enrollment, and notification permission/subscription.
- [ ] Smoke-test existing policy create/edit/PDF, staff roles/management, renewal statuses/reminders, reports, theme, and branding.

Every checkbox is **PENDING USER ACCEPTANCE**. No physical iPhone, real SMTP delivery, or real Web Push delivery was available to Codex.

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
