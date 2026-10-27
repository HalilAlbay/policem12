# Secure login pre-flight audit (P0)

Date: 2026-10-28 (Europe/Istanbul)
Contract: `POLICEM_CODEX_NIHAI_SARTNAME.md` (user-provided final specification; supersedes conflicting V2 requirements)
Audit status: **P0 verified; P1 may proceed.**

## A. Checkout and verified baseline

- Repository: `HalilAlbay/policem12`
- Work branch: `feature/secure-easy-login`
- HEAD and P0 rollback checkpoint: `d577d2a03a81a4f4cb79d4b39cde223ba79533e3`
- Parent: `9483cdeff4405d50012da69334afcbba5bd87168`
- HEAD title/date: `Lock five final product decisions for Codex secure login V2`, 2026-10-28.
- `git status --porcelain=v1` was empty at checkout; branch was tracking `origin/feature/secure-easy-login`.
- Protected known-good SHA supplied by the contract: `d6350ee5a013c9f192800154971e787684419be4`. The protected branch was not checked out or modified.
- Test Render: `policem12-push-test` (`srv-dbg5ak4s728c73de7j0g`); no deploy or Render access performed.
- P0 files inspected: `app.py`, `customer_portal.py`, `static/index.html`, `static/push-client.js`, `static/push-sw.js`, `push_service.py`, `push_job.py`, `notification_core.py`, `requirements.txt`, all eight root/subdirectory `test*.py` files, both GitHub workflow files, and `docs/SECURE_EASY_LOGIN_PLAN.md`.

### Routes and handlers

`app.py` exposes: `GET /api/health`, `GET /`, `GET /api/setup/status`, `POST /api/setup`, `POST /api/login`, `GET /api/me`, `POST /api/logout`, `POST /api/password`; device/security routes `GET|POST /api/security/devices`, `POST /api/security/pin/enroll`, `POST /api/security/refresh/enroll`, `POST /api/security/refresh/logout`, `POST /api/security/refresh`, `POST /api/security/devices/{device_id}/bind`, `POST /api/security/devices/{device_id}/revoke`; theme/branding `POST /api/theme`, `GET|PUT /api/branding`, `POST|DELETE /api/branding/icon`, `GET /api/branding/icon`, `GET /manifest.webmanifest`; organization/personnel `GET /api/organization`, `POST /api/agencies`, `POST /api/branches`, `GET /api/users/manage`, `POST /api/users`, `PUT /api/users/{user_id}`, `POST /api/users/{user_id}/reset-password`, `DELETE /api/{kind}/{item_id}`; policies `POST /api/policies`, `GET /api/policies`, `GET /api/summary`, `GET /api/finance/summary`, `POST /api/renewals/{policy_id}`, `GET /api/transfer/staff`, `POST /api/transfer`, `GET /api/audit`, `POST /api/pdf/extract`, `POST /api/policies/with-document`, `GET /api/insurers/summary`, `POST /api/policies/{policy_id}/document`, `GET /api/policies/{policy_id}/document`, and `GET /api/reminders`.

`customer_portal.register()` adds customer registration/login/profile and quote routes in `customer_portal.py`. `push_service.build_router()` adds `GET /api/push/config`, `POST /api/push/test`, `POST /api/push/subscribe`, and `POST /api/push/unsubscribe`.

### Authentication, startup, storage, and browser inventory

- `app.py`: `conn()` opens SQLite with foreign keys and WAL; `tx()` serializes with a process-local `RLock`; `init()` creates core and prototype security tables and applies ad-hoc additive user columns. Startup calls `init()` and conditionally starts the expiry push background loop only for the named test Render service. `password_hash()` uses PBKDF2-HMAC-SHA256 with 350,000 rounds and a random 16-byte salt; `check_pw()` compares in constant time; `current()` accepts a bearer token, hashes it, checks expiry, active user and a revoked bound device; `require()` checks role names.
- Schema includes `agencies`, `branches`, `users`, `sessions`, `trusted_devices`, `device_sessions`, `refresh_sessions`, `device_pin`, `policies`, `renewals`, `reminders`, `branding`, and `audit`; push tables are created by push code. `users.branch_id -> branches.agency_id` supplies an agency relationship. There is no `email_verified`, auth schema version, WebAuthn credential/challenge, token-family/replay, idle-activity, reset-token, verification-token, or durable generic rate-limit table.
- Existing auth Pydantic models: `FirstAccount`, `Login`, `PasswordChange`, `DeviceRegister`, `DeviceRevoke`, `RefreshEnroll`, `PinEnroll`, `PinRefresh`, `AdminPasswordReset`; new staff password minimum is 12, but `Login.password` has no length bound and legacy hashes are accepted.
- Password login (`login`) creates a random 40-byte-url-safe token, persists SHA-256(token) with a 24-hour absolute expiry, and returns the raw bearer token. The client stores it in `sessionStorage['policem_token']`.
- Security functions: `list_trusted_devices`, `register_trusted_device`, `enroll_pin`, `enroll_refresh`, `logout_refresh`, `refresh_session`, `bind_device_session`, `revoke_trusted_device`. The UI uses `quickLogin`, `saveQuickMethod`, `loadSecurityDevices`, `revokeQuickDevice`, `logout`, `boot`, and `showPasswordLogin`. Preference and last username are in `localStorage` (`policem_quick_*`, `policem_last_username`).
- The client `api()` attaches the bearer token to protected fetches. `logout()` fires refresh invalidation without awaiting it, clears only the access token locally, and reloads. `boot()` calls `/api/me` and `/api/organization`; there is no 15-minute client lock, server idle timeout, or transient form wipe behavior.
- `push-client.js` contains `policemVapidBytes`, `policemEnablePush`, `policemDisablePush`, `policemPushControls`, `policemSyncExistingPush`; service worker is `push-sw.js`. `push_job.tick()` selects subscriptions by policy owner ID, with no active-device/logout eligibility filter. Scheduler work is separate from user session startup.
- Config observed in code: `POLICEM_DATA`, `POLICEM_ADMIN_PASSWORD`, `POLICEM_SETUP_KEY`, `RENDER_SERVICE_NAME`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_USER`, `SMTP_PASSWORD`, and `POLICEM_VAPID_PUBLIC_KEY`, `POLICEM_VAPID_PRIVATE_KEY`, `POLICEM_VAPID_SUBJECT`. No canonical public origin or WebAuthn RP ID configuration exists. Existing reminder SMTP is not verified-email recovery.
- `requirements.txt` has FastAPI, Uvicorn, multipart, PyMuPDF, Pydantic, Pillow, and pywebpush; no pytest/httpx declaration and no WebAuthn library. Pytest files are `test_app.py`, `test_deployment.py`, `test_notification_core.py`, `test_push_service.py`, `test_push_integration.py`, `tests/test_device_sessions.py`, `tests/test_quick_login.py`, and `tests/test_staff_permissions.py`. The earlier note that several root-level tests were absent was incorrect; those files exist and were discovered by full `pytest` collection.

## B. File ownership and proposed function-level map

P0 confirms the existing scope. Expected future changes are:

- `app.py`: narrowly wire startup migration and routes; patch `current`, `login`, `logout`, `change_password`, `edit_user`, `reset_staff_password`, and security functions as justified by P1/P5. Preserve unrelated policy, customer and staff behavior.
- New `auth_security.py` (or package): isolated session, challenge, WebAuthn, recovery, audit and rate-limit logic.
- `static/index.html`: only login/settings/security handlers and state transitions; preserve the rest of the single-page app.
- `requirements.txt`: only tested WebAuthn/email/test dependency changes with compatible bounds.
- `tests/test_*auth*.py` plus existing security/push/staff tests: acceptance and regression evidence.
- `docs/SECURE_LOGIN_API_CONTRACT.md`, `docs/SECURE_LOGIN_DB_MIGRATION.md`, `docs/SECURE_LOGIN_TEST_REPORT.md`, `docs/SECURE_LOGIN_HANDOFF.md`.

Protected: `push_service.py`, `push_job.py`, `static/push-client.js`, `static/push-sw.js`, manifest/assets, policy/PDF/import/export/calculation logic, Render files, and unrelated staff permission/business logic. DEC-05 expressly authorizes only a minimal targeted push-recipient eligibility change and regression coverage if implementation reaches that scope. No such change has been made.

## C. Existing data flows and known gaps

1. Password login: username + password -> active account lookup -> PBKDF2 check -> raw bearer returned; only token hash is stored. No durable rate limit, generic inactive-vs-unknown handling is mostly shared for login, no cookie access session, no idle timer.
2. Passkey: no endpoint, library, stored public credential, challenge, registration, assertion verification, RP ID, or origin allowlist exists.
3. PIN enrollment: authenticated bearer plus submitted password -> trusted-device row with random ID -> PIN PBKDF2 hash in `device_pin`. No proof that a device secret is held by the device; PIN confirm UI and independent method selection are absent.
4. PIN authentication/refresh: refresh cookie (30 days, HttpOnly/Secure/SameSite Strict, path `/api/security/refresh`) plus PIN -> verify PIN -> delete old refresh row and insert replacement plus a 24-hour bearer session. Refresh origin compares `Origin` to `https://` + request `Host`; this trusts an unconfigured Host value. Failure counter explicitly commits before raising. No token family or reuse detection.
5. Session rotation/revoke: refresh token rotates once in a transaction, but concurrent replay/family behavior is not defined. Device revoke checks password and own-device ownership, then removes bound sessions, refresh rows and PIN row. User-wide logout and password changes remove sessions; password change also removes refresh rows. No passkey/grants exist yet. User deactivation removes sessions, not refresh/device state.
6. Password reset: manager/partner route directly accepts a new password. Partner is global; manager may reset any active `staff` account without verifying same agency/subordinate relationship; it invalidates sessions but leaves refresh/device/PIN associations. No verified-email reset/verification flow exists. Staff UI submits this endpoint.
7. Push: subscription is stored against `user_id`; subscribe checks endpoint ownership and unsubscribe deletes own endpoint. Scheduled push joins owner user ID to subscription but does not consult login/device activation or logout state. DEC-05 therefore requires later targeted server-side suppression. Push loop itself runs independently of browser authentication.

## D. Threat model (P0 assessment)

| Threat | Current control/evidence | P0 assessment / required response |
|---|---|---|
| Stolen bearer or refresh cookie | Access token hash at rest; refresh cookie HttpOnly/Secure/SameSite Strict | Bearer is exposed to same-origin JS/XSS; refresh cookie + four-digit PIN authenticates. PIN cannot be treated as secure possession. Rotate/revoke, idle deadline, CSRF/origin binding, and theft tests required. |
| XSS | HTML escapes many data labels, but app is same-origin JS | XSS can use bearer and interact with authenticated UI; do not claim storage makes it safe. Avoid introducing unsafe HTML/secret persistence. |
| CSRF / origin spoofing | Refresh checks Origin against `Host`-derived URL; other APIs use bearer | Arbitrary Host is not a trusted canonical origin. Configure origin and explicit CSRF policy before cookie-auth flows. |
| Credential replay / race | Refresh row deleted then replacement inserted; SQLite transaction and process lock | No family/reuse signal, distributed-worker lock guarantee, or concurrency test. Test duplicate concurrent refresh and stale token behavior. |
| Brute force / targeted denial | PIN has 5-failure lock persisted in `device_pin` | no login rate limit; PIN counter scoped to device ID and can be reset by re-enrollment; no cross-device/account throttle. P3 must remain blocked absent strong possession proof and durable controls. |
| Database compromise | Password/PIN PBKDF2 salted hashes; session/refresh token SHA-256 hashes | No WebAuthn private keys should ever be stored; add token hashes only, assess PIN verifier offline guessing risk, protect DB/backups. |
| Multi-tab | sessionStorage token is per-tab | logout is not broadcast and async server invalidation is not awaited; server-side revoke must be authoritative. |
| Cross-account/device | current query binds device session to same user; device queries filter owner | Existing tests cover some binding ownership. Add credential/challenge/account isolation and race coverage. |
| Lost device | revoke route checks current user/password | old-phone recovery requires new officer-issued temp password, all grant revocation, forced change; existing route lacks agency scope, refresh/device revocation. |
| Synced passkey | no implementation | WebAuthn may sync across devices; report UX as device verification, not physical-only binding; require configured RP/origin and manual iPhone acceptance. |
| Admin misuse / tenant crossover | roles are partner/manager/staff; user records link via branch to agency | partner is global; manager reset checks staff role only and not agency. Fail closed until exact same-agency subordinate rule implemented and regression-tested. |
| Service worker / push | background scheduler independent; subscription owned by user | job currently sends after logout/revoke. DEC-05 requires server recipient eligibility; keep scheduler running and subscriptions intact. |

### PIN cryptographic proof conclusion

There is no device-held signing key, protected platform credential, or fresh signed challenge in this branch. `/api/security/refresh` accepts a valid refresh cookie and the four-digit PIN; `trusted_devices.id` is only a random database identifier. Therefore a copied refresh cookie plus PIN is sufficient, and the server cannot distinguish it from the original browser. The requested cryptographic possession proof is unavailable in current code. **PIN quick login is BLOCKED** under sections 6 and DEC-01 until a platform-compatible proof satisfies the contract; do not ship the current cookie+PIN flow as a secure device-bound PIN.

## E. Decisions and configuration required

Fixed by DEC-01..05: mutually exclusive PIN or WebAuthn quick method plus password fallback; idle lock at exactly 900 seconds discards all unsaved/transient input; lost phone uses same-agency authorized officer temporary full password and forces change; ordinary email recovery requires verified email and provider-neutral SMTP fail-closed; logout/revoke suppresses push for affected device and, if no active receiver remains, for the user. These decisions supersede conflicts in earlier sections.

External/runtime prerequisites not present in code: canonical HTTPS public origin; WebAuthn RP ID/origin allowlist; SMTP host/port/TLS/from/user/password and operational mail delivery; a verified-email migration/enrollment policy; durable SQLite storage/backup confirmation; iPhone Safari and Home Screen PWA capability validation. Do not infer values. Fail closed for unavailable quick methods and reset mail; preserve legacy password login. Manager recovery must be same agency, lower permitted role, and based on branch-to-agency mapping; cross-agency or unclear mapping is denied.

## F. Baseline tests, rollback, and acceptance mapping

Baseline checkpoint/rollback SHA: `d577d2a03a81a4f4cb79d4b39cde223ba79533e3`. P0 record commit: `6582a2ced6e3ea7d1a054579d8de49821e320a13`.

| Command | Environment/result |
|---|---|
| `py -3.12 -m venv .venv; .venv\\Scripts\\python.exe -m pip install --no-cache-dir -r requirements.txt pytest httpx` | Exit 0: dependencies installed in an isolated checkout-local environment after an initial transient package-index failure. |
| `.venv\\Scripts\\python.exe -m pytest -q` | Exit 1: **32 passed, 7 failed, 19 warnings** in 13.28s on unchanged source `d577d2a`. Failures: 5 `test_app.py` cases expect staff creation without currently-required phone/start_date and/or expect old branding; `test_notification_core.py::test_all_milestones` expects a 30-day notification absent from current scheduler; `tests/test_quick_login.py::test_pin_refresh_and_lockout` expects a Secure cookie over plain HTTP TestClient, so no refresh cookie reaches the endpoint. These are recorded baseline failures, not silently skipped. |
| `.venv\\Scripts\\python.exe -m compileall -q app.py customer_portal.py notification_core.py push_job.py push_service.py windows_main.py tests test_app.py test_deployment.py` | Exit 0: all Python files compiled. |
| `node --check static/push-client.js` | Exit 0: existing push client syntax passed. |

Baseline pytest is now **reproducible but has seven pre-existing failures**. Under the final specification this does not stop independent stages; each failure will be tracked and rerun after relevant work. Acceptance mapping: AUTH/DEV/WEB/PIN/UI/REC/MIG/SEC are unverified; PIN proof remains an open security investigation; REG has executable tests; PUSH tests exist and will be rerun when P6 is implemented; manual iPhone acceptance is pending user by definition. Exact command/output and counts are in `SECURE_LOGIN_TEST_REPORT.md`.

## P0 gate

The final specification's P0 inspection is complete: branch/HEAD/status, existing P0, route/schema/UI inventory, tenant relationships, push flow, threat map, affected/protected files, and reproducible baseline test outcomes are recorded. P0 commit: `6582a2ced6e3ea7d1a054579d8de49821e320a13`. Baseline failures remain open work; per the final specification they do not block P1. Do not interpret syntax checks as passing functional tests.
