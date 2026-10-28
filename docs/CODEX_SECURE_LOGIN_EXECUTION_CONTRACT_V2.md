# POLİÇEM — CODEX EXECUTION CONTRACT V2.0
Date: 2026-10-27 | Status: SPECIFICATION ONLY, NOT IMPLEMENTED OR VERIFIED
Repo: HalilAlbay/policem12 | Work branch: feature/secure-easy-login
Known-good protected branch: stable/policem-personnel-ui-working-2026-10-27
Known-good commit: d6350ee5a013c9f192800154971e787684419be4
Test Render: policem12-push-test / srv-dbg5ak4s728c73de7j0g — DO NOT DEPLOY.
Parent task: GitHub Issue #1. This V2 contract takes precedence over earlier implementation suggestions if they conflict. Security design cannot be solved by pretending platform capabilities exist.

## 0. OBJECTIVE, BOUNDARY, NON-NEGOTIABLES
Deliver a backwards-compatible, server-verified easy login for an insurance agency PWA. First use: username + >=12-character password; user then configures ONE preferred method per browser/PWA installation under Settings > Güvenlik ve Giriş: (1) Face ID / device verification via real WebAuthn, (2) application 4-digit PIN only if protected by genuine device possession and durable online attempt controls, (3) password. On subsequent launches present preferred method automatically; provide a discreet password fallback. Include trusted device inventory, revoke, lost device, 15-minute server-enforced idle lock, five wrong PIN attempts -> strong reauthentication, secure password reset via verified email, role-scoped admin recovery, audit, and tests. No regressions to existing policies, staff, agency isolation, push.

This is NOT authorization to merge, deploy, alter Render environment, rotate VAPID, change push service worker, reset data, or remove working branches. User is iPhone-only and will conduct final manual acceptance. Codex must conduct automated tests first.

Non-negotiable: do not rewrite app.py wholesale; do not replace static/index.html wholesale; no new app framework, auth provider, external service, or database engine without documented reason and explicit approval. Do not make assumptions about undocumented roles, agency ownership, verified email, PWA origin, push lifecycle, or WebAuthn device-binding. No secrets in commits/logs. No silent security downgrade.

## 1. EXACT BASELINE / OBSERVED CODE (VERIFY AGAIN AT START)
- app.py: SQLite, FastAPI, startup init(), tx() uses LOCK; existing users/password_hash and sessions(token_hash,user_id,expires). Password hash PBKDF2-HMAC-SHA256 350k. Login creates 24h bearer token; frontend sessionStorage policem_token.
- Feature branch already has trusted_devices, device_sessions, refresh_sessions, device_pin; endpoints /api/security/devices, /api/security/devices/{id}/bind, /api/security/devices/{id}/revoke, /api/security/pin/enroll, /api/security/refresh/enroll, /api/security/refresh, /api/security/refresh/logout. These are UNVERIFIED prototypes. Review and replace unsafe logic; do not preserve merely for compatibility if insecure. Keep stable branch untouched.
- Existing /api/users/{user_id}/reset-password accepts admin-provided password: THIS IS NOT ACCEPTABLE AS FINAL VERIFIED-EMAIL RECOVERY. Audit existing authorization and tenant boundaries before modifying.
- Existing refresh endpoint derives allowed origin from request Host; do not treat untrusted Host as authoritative origin.
- Existing PIN is only salted hash + cookie; neither proves device possession. Never claim cookie+PIN is safe from theft.
- Existing JS quickLogin, saveQuickMethod, localStorage preference, and logout flow require review for UI, CSRF, race and storage safety.
- requirements.txt currently lacks WebAuthn library. Existing tests include test_device_sessions.py, test_quick_login.py and staff permissions tests. Verify exact HEAD and file hashes; don't assume summary is complete.
- Push startup background loop must work without browser session. Do not couple push scheduler to interactive auth.
- Test Render ephemeral SQLite may reset on redeploy: deployment prohibited in this task.

## 2. REQUIRED PRE-FLIGHT REPORT (NO CODE CHANGES UNTIL COMPLETE)
Create docs/SECURE_LOGIN_AUDIT.md with:
A. actual HEAD, git status, branch; full inventory of app.py routes, auth models, JS functions, DB schema, startup and config;
B. affected vs protected file list and specific function-level change map;
C. data flow for password login, passkey register/authenticate, PIN enroll/authenticate, session rotate/revoke, password reset, push subscription;
D. threat model (stolen cookie, XSS, CSRF, credential replay, brute force, DB compromise, multi-tab race, cross-account, lost device, shared/synced passkey, admin misuse, tenant crossover, service worker);
E. precise cryptographic proof model for PIN; show why stolen cookie + 4 digits cannot authenticate. If unavailable in target web platform, mark PIN BLOCKED, use WebAuthn or password instead; do not ship insecure PIN.
F. all unresolved product decisions / required config (public HTTPS origin, RP ID, SMTP sender, verified email, storage persistence) and safe defaults;
G. rollback SHA, baseline test commands and results, acceptance mapping.
Baseline failures must be recorded, not ignored. No arbitrary test skips.

## 3. SECURITY ARCHITECTURE / SESSION STATE MACHINE
Use explicit states: LOGGED_OUT, PASSWORD_AUTHENTICATED, DEVICE_ENROLLMENT_PENDING, DEVICE_REGISTERED, QUICK_AUTH_PENDING, AUTHENTICATED, IDLE_LOCKED, DEVICE_REVOKED, PIN_LOCKED, RECOVERY_PENDING. Only server-validated transitions may grant access. Local preference is display-only, not proof.

- Password login: existing users continue to work; maintain >=12 chars on NEW/CHANGED passwords; do not silently invalidate legacy passwords solely due to length. Rate limit failed login attempts with generic error; no username enumeration.
- Access sessions: hash random tokens at rest; short-lived, bound to user, optionally device; last_activity and 15-min idle deadline enforced on EVERY protected API. Deny access after idle even if browser JS failed to lock. Sliding update atomic and time source server-side. Do not extend idle time for background notifications, health probes, or static assets. Distinguish absolute session expiration from idle deadline.
- Remembered device grants: maximum 30 days, single-use refresh rotation, token family and replay detection, DB transaction locking/concurrency-safe behavior. Refresh alone never bypasses chosen strong unlock factor. 15-min idle lock must require new PIN/passkey/password; never silently refresh into unlocked session.
- Cookie: HttpOnly Secure SameSite as appropriate, strict path, no secrets in localStorage/sessionStorage beyond short-lived legacy access token until migration; prevent cookie CSRF with trusted configured origin and CSRF strategy. Do not base origin policy on arbitrary Host header. Browser on HTTPS; localhost dev exception only in explicit test/dev mode, never in production.
- Logout: await server invalidation, clear cookies and client state, handle offline failure without falsely claiming remote revoke. Logout all devices and password change/recovery invalidate all relevant sessions and grants. Device revoke kills sessions, refresh and device credentials tied to it; legacy unbound sessions need explicit transitional policy.
- Account deactivation, role/agency change: audit effects on sessions and tenant access; invalidate or revalidate authorization at every request. Never permit access after user deactivation.
- Password reset: revoke sessions and refresh, require passkey/PIN re-enrollment if assurance changes; document exact choice and test it.
- Logs: never include password, PIN, bearer, refresh, challenge secret, reset token or raw WebAuthn assertion. Audit only IDs and outcome; cap PII.
- Add durable DB-backed attempt counters with expiry/retention. Rate limits across workers/restarts and safe against rotating device IDs/IPs; protect against both guessing and targeted denial of service.

## 4. DEVICE REGISTRATION / BINDING
- Device enrollment requires an authenticated session plus recent password step-up (freshness <=5 minutes or password explicitly reentered).
- Merely returning random device_id or storing a device_id in localStorage does NOT prove physical device. Device-bound grant requires signed challenge using protected credential (WebAuthn/passkey) or equally sound platform-supported possession factor. Device ID is a database reference only.
- Device inventory GET returns own active devices, name, created/last_seen, current flag, method and revoke status; never other users' devices. Display labels safely escaped.
- Revoke requires recent strong step-up and must be atomic; revoke refresh, access, PIN grant and credential mappings for that device. Return 404 for foreign device IDs. Idempotent UX; server state authoritative.
- Maximum 10 active devices/user unless business requirements say otherwise; enforce transactionally. Duplicate enroll behavior must be defined and tested.
- Synced passkeys can be used on multiple devices. Do not falsely label synced passkey as strictly physical-device bound; design separate registration per browser/install or document limitation.
- Existing unbound legacy sessions: document transition and bound them only after verified reauthentication; do not silently treat them as trusted.

## 5. WEBAUTHN / BIOMETRIC (REAL, NOT MOCK)
- Use maintained Python WebAuthn verification library, pin a tested compatible version/range, inspect package/license and deployment compatibility.
- Registration options: server-generated challenge, single-use, <=5 min, account + session bound, RP ID from configured public hostname, origin allowlist, userVerification='required', no duplicate credential IDs, explicit consent.
- Verify attestation/registration server-side: challenge, origin, RP ID, clientData type, authenticatorData, UV, credential public key, ownership, credential ID, authenticator capabilities.
- Login options: challenge one-time <=5 min, account/credential scoped; verify assertion signature against stored public key, origin, RP ID hash, UV, signCount and backup state semantics, revoke/active status. Credential cannot authenticate another account.
- Protect replay, concurrent challenges, stale requests, wrong origin, wrong RP, missing UV, forged signature, cross-user credential.
- Device prompt uses OS biometric/device verification; app cannot guarantee specifically Face ID versus Touch ID or device PIN. Label 'Face ID / cihaz doğrulaması'. No raw biometric data collected.
- If unsupported iPhone PWA/browser, show clear message and password fallback. No fake success on client navigator.credentials call without server verification.
- Server issues access only after verified assertion; client receives no signing key or private key.
- Document Safari/PWA capability and synced passkey limitation; final iPhone manual verification pending.

## 6. FOUR-DIGIT APPLICATION PIN (HIGH RISK; HARD GATE)
- UI: exactly four ASCII digits, numeric keyboard, masked input, no persistence in localStorage, sessionStorage, URL or logs.
- Enrollment: verified current password + registered device proof, confirmation entry, explicit consent, transactionally store strong salted hash or equivalent appropriate key material.
- Login: possession proof bound to fresh server challenge AND PIN knowledge. A copied HttpOnly cookie plus four-digit PIN must not be sufficient. If secure possession proof requires OS verification every login, explicitly disclose UX limitation; do not misrepresent as standalone app PIN.
- Five failed PIN attempts PER registered device/user lock quick login durably, including across restarts and new cookies. Failed counter must COMMIT on failure; successful proof resets only valid scope. On lock require strong password/passkey reauthentication and deliberate re-enrollment; avoid unlimited reset via public endpoint.
- Throttle BEFORE costly PBKDF; generic errors and consistent HTTP status; ensure no user enumeration. Resist stolen cookie replay, stolen device ID, cross-user, concurrent requests and credential revocation.
- If genuine cryptographic possession binding cannot be built on Safari PWA, STOP PIN feature with BLOCKED SECURITY DECISION and preserve safe password/passkey flow. Do not invent workaround.

## 7. SETTINGS + LOGIN UX — EXACT BEHAVIOR
Settings > Güvenlik ve Giriş card, without disturbing existing password/theme/branding/personnel settings:
- Preferred method radio/select: 'Face ID / cihaz doğrulaması', '4 haneli PIN', 'Şifre'. Unsupported method disabled with explanation.
- Changing to Face ID: password step-up -> OS registration -> server verification -> success -> preference saved. Cancel/error leaves previous method unchanged.
- Changing to PIN: password step-up -> cryptographic device enrollment -> PIN + confirm -> server verify -> preference saved. Invalid PIN, mismatch, unavailable proof or error leaves previous method unchanged.
- Changing to Password: require reauthentication if disabling security credential; revoke quick grants as policy specifies; show success only after server success.
- Inventory: active device list, current badge, last seen, method, revoke with confirmation and password/passkey step-up; own device revoke immediately logs out.
- Normal launch: preferred method automatically shown (no three big choices); password fallback is secondary text action. On first launch/no preference show existing username/password. Changing browsers/PWA installations must not assume same local preference.
- Foreground after >15m: lock and require preferred method; API 401 idle reason, do not erase form data unnecessarily, no offline bypass. If backend unreachable show network error and keep locked; do not claim user logged out unless server says so.
- Five wrong PIN: explain 'PIN kilitlendi. Şifreyle giriş yapın.' with recovery; no account lockout beyond intended quick login.
- Multi-tab: logout/revoke/password reset in one tab invalidates others; storage events/BroadcastChannel may improve UX but server authority required.
- Never break push permission, service worker registration or push subscription when locking/unlocking/logging out unless business explicitly defines account-specific subscription migration. Push notifications should remain deliverable by server when PWA closed.
- Accessibility: labels, focus order, keyboard and VoiceOver, 44px touch targets, high contrast, non-blocking error text, no alert/prompt for sensitive production flows if accessible modal can be used.

## 8. PASSWORD RESET / VERIFIED EMAIL / ROLE SCOPE
- Forgot password on login: generic success response independent of account existence; if verified email and SMTP configured, send single-use random reset link; store token HASH, TTL 15 min, atomic consume, max attempts, rate limits. Build link only from configured trusted public origin, not request Host.
- Stored email is NOT automatically verified. Existing staff without verified email must keep password login; secure verified-email enrollment with authenticated password step-up and one-time confirmation token; do not silently lock accounts.
- Email send failure must not issue usable externally exposed reset token or leak account existence; log safe operational diagnostics.
- Manager recovery: only same agency and subordinate permitted roles; no password visibility, no password sent in plaintext. Partner/owner recovery via verified email. No universal backdoor.
- Existing /api/users/{user_id}/reset-password direct password assignment: evaluate backwards compatibility; replace/deprecate safely only after mapping current personnel UI; do not leave privilege bypass. Audit all changes without secret.
- Password reset/change invalidates access, refresh, device quick grants as designed. Expired/reused/foreign token denied. Email change re-verification required.

## 9. API CONTRACT AND ERROR HANDLING
Before implementation create docs/SECURE_LOGIN_API_CONTRACT.md: for EVERY new/changed endpoint list HTTP method/path, auth precondition, request/response JSON, cookie/CSRF, statuses 200/201/204/400/401/403/404/409/422/429, generic error body, rate limits, DB effects, idempotency and audit event. Specify account/agency boundaries and server error paths. Preserve existing /api/login, /api/me, /api/logout, /api/password contracts unless explicitly versioned; no breaking current app without tested migration.
Define errors: AUTH_REQUIRED, SESSION_IDLE, DEVICE_REVOKED, METHOD_UNAVAILABLE, PIN_LOCKED, CHALLENGE_EXPIRED, ORIGIN_DENIED, RATE_LIMITED, RECOVERY_UNAVAILABLE, NETWORK_ERROR. Map to friendly Turkish UI; no stack traces or token exposure. Decide 401 vs 403 vs 429 consistently. Use Pydantic validation with length caps and safe normalization.

## 10. DB CONTRACT + MIGRATIONS
Before changing schema create docs/SECURE_LOGIN_DB_MIGRATION.md with exact CREATE TABLE/ALTER SQL, indexes, constraints, timestamps in UTC epoch, FK behavior, retention, unique keys, and rollback strategy. Must cover trusted_devices, device_sessions, refresh token families, credentials, challenges, PIN attempt state, email verification, reset tokens, auth events, and idle timestamps. Additive migrations, schema versioned, idempotent on second startup; SQLite transactions safe, no destructive rebuild, existing password hashes and policy tables unchanged. Existing rows with no new columns get safe defaults. Verify migration on both empty DB and copy of legacy schema fixture. Never use live Render DB for tests. Fail closed on partial migration, avoid startup in inconsistent state.

## 11. FILE OWNERSHIP / ALLOWED DIFF
Allowed after audit: app.py ONLY minimal route wiring and migrations; new dedicated auth module(s) (prefer auth_security.py or package), static/index.html ONLY login/settings and event handlers, requirements.txt ONLY audited dependencies, tests/test_*auth*.py, docs/*.md. Existing auth endpoints can be patched narrowly when required.
Protected by default: push_service.py, push_job.py, static/push-client.js, service worker, manifest, image/assets, policy import/export, PDF parsing, capacity/renewal calculations, staff role business logic, Render configs. Any needed protected-file change => stop, document reason, ask permission. Do not alter unrelated CSS/layout or PWA behavior. No files overwritten from scratch. One owner per file, no parallel edits to same file. Before commit inspect git diff --check, list changed paths and justify every change.

## 12. STAGED EXECUTION / STOP GATES
P0: inspect, baseline checkpoint, audit + impact map + test baseline. Gate: reports committed, baseline reproducible.
P1: auth/session/migrations/rate limits/idle/logout/device revoke. Gate: security and legacy regression tests pass.
P2: WebAuthn registration/login. Gate: signature/origin/RP/UV/replay/ownership tests pass.
P3: PIN secure possession proof and lockout. Gate: cookie theft + brute-force + race tests pass; otherwise BLOCKED, not 'done'.
P4: settings and preferred login UX, iOS PWA fallback. Gate: JS syntax/DOM/state tests pass, legacy screens intact.
P5: verified email recovery and scoped manager workflow. Gate: email/replay/tenant/role tests pass; SMTP config blocker documented.
P6: full regression + security review + delivery. Gate: all critical automated tests pass, no forbidden file diffs. No deployment.
For each phase: read relevant files -> written microplan -> smallest code patch -> test -> inspect diff -> atomic commit -> update report. Do not proceed if gate failed. Do not declare partial stage complete if blocked. Independent work may proceed only if it does not depend on blocked security foundation.

## 13. ACCEPTANCE TEST MATRIX (AUTOMATED)
AUTH-01 existing password login succeeds, invalid credentials generic failure, no account enumeration.
AUTH-02 inactive user blocked, role/agency isolation preserved, 15-min idle API returns 401 and no refresh auto-unlock.
AUTH-03 access token expiry and refresh rotation, single use, concurrent replay, stolen cookie without proof rejected.
AUTH-04 logout current/all devices and password change revoke all relevant grants, including other tabs.
DEV-01 register device with step-up and valid credential; foreign device denied; 10-device cap; revoke cuts off linked grants immediately.
DEV-02 revoked device credential/passkey cannot authenticate, last_seen correctly updated.
WEB-01 real library verifies valid test vectors; wrong origin/RP/challenge/type/UV/signature/counter/replay/cross-account rejected.
PIN-01 4 digits only, PIN confirm, wrong password cannot enroll, no PIN in browser storage/logs.
PIN-02 five wrong attempts lock durably; correct PIN after lock denied; strong recovery resets only by verified step-up.
PIN-03 stolen cookie + correct PIN but no device proof denied; concurrency/rate-limit persistent.
UI-01 selected method appears by default, password fallback works, unsupported WebAuthn handled, no multiple-method clutter.
UI-02 idle/background/foreground/offline/reload/multi-tab handling, accessible errors, no stale session unlock.
REC-01 verified email only, single-use 15min reset, replay/expired/wrong token denied, generic request responses.
REC-02 no-email legacy user not broken, SMTP absent fail closed, manager cannot reset superior/foreign agency.
REG-01 staff permission tests unchanged; policy PDF upload, renewal, agency isolation, dashboard, branding smoke tests pass.
PUSH-01 push files unchanged by git diff, existing push tests pass, scheduler startup independent of user login, no subscription wipe.
MIG-01 fresh DB and legacy fixture migrate, second startup idempotent, FK/index constraints valid.
SEC-01 CSRF/origin, cookie flags, rate limits, audit no secrets, security headers as appropriate.
Record every test: command, environment, exact exit code, passed/failed/skipped, evidence, related commit in docs/SECURE_LOGIN_TEST_REPORT.md. No fabricated runs; critical skips block completion. Browser-only behaviors require final user manual acceptance.

## 14. USER MANUAL ACCEPTANCE (NOT CODEX'S CLAIM)
Prepare an iPhone checklist: Safari and Home Screen PWA first login, passkey setup and cancellation, Face ID/device verification, PIN setup/5 wrong attempts, 15min idle while backgrounded, reopen/offline, lost device revoke, password fallback/reset, push notification while app closed, staff and policy smoke. Record as PENDING until user confirms. Android checklist if device available. Do not call browser emulation a real iPhone device test.

## 15. OUTPUT AND ROLLBACK
Deliver docs/SECURE_LOGIN_AUDIT.md, docs/SECURE_LOGIN_API_CONTRACT.md, docs/SECURE_LOGIN_DB_MIGRATION.md, docs/SECURE_LOGIN_TEST_REPORT.md, docs/SECURE_LOGIN_HANDOFF.md; minimal code commits on feature branch. Final handoff must list exact HEAD, files changed, endpoint matrix, env vars needed (names only, no secrets), pass/fail counts, limitations, security blocked decisions, protected file diff verification, rollback SHA and steps. No deploy/merge. User approval is mandatory before any Render action.
STOP and ask only if a truly blocking external decision is needed (e.g. canonical public origin, SMTP provider, impossibility of secure 4-digit PIN on target PWA). Otherwise implement safe independent work. Never replace a blocked requirement with an insecure approximation.


## 16. FINAL PRODUCT DECISIONS — USER-APPROVED, OVERRIDE ALL CONFLICTS ABOVE
These are fixed product rules. Codex must not reinterpret them or ask to choose among alternatives. Where previous sections conflict, this section prevails. Implement safe behavior; do not downgrade security to meet UX.

### DEC-01 — USER-DEFINED EASY LOGIN, NO EXTRA USER-FACING FACTORS
The user's exact product requirement is authoritative:
- First login on a new device: **username + full account password**, followed by enrollment of that device as trusted.
- Thereafter the user selects **ONE** easy-login mode: **4-digit application PIN** OR **Face ID**, never both together. Both modes retain the full account password as recovery/fallback; they are not simultaneous prompts.
- In PIN mode, opening/unlocking the app requires **only the 4-digit PIN** from the user. Do not ask for Face ID or the full password on each normal PIN login. In Face ID mode, opening/unlocking uses Face ID, not an additional PIN prompt.
- After **five incorrect PIN attempts**, disable quick PIN entry and require the full account password to restore access. Password remains available if easy login is unavailable.
- Changing easy-login mode requires full-password authentication and enrollment of the chosen mode. Do not enable both modes simultaneously.
- Implement appropriate behind-the-scenes session, rate-limit and trusted-device protections **without adding extra user-facing steps** or changing the requested login choices. Examine the current implementation and fix identified weaknesses instead of simply blocking the feature. If a specific secure implementation cannot be achieved on the target iPhone PWA, document the exact technical obstacle and stop that unsafe implementation; do not claim an insecure workaround is secure. Do not redefine the user's chosen UX as a different product requirement.

### DEC-02 — 15-MINUTE IDLE LOCK DISCARDS UNSAVED INPUT
Exactly 15 minutes (900 seconds) without user interaction in the app triggers a lock. At the same boundary server API access must be blocked until reauthentication. On lock, **discard all unsaved form edits, drafts, unsent uploads and transient data** in the current client session; do not auto-save, persist, restore, or silently submit unsaved changes. Data already successfully committed to the server before the lock MUST remain intact. Abort in-flight unsaved mutations safely where feasible; server must reject mutations after idle expiry, but an operation already committed before timeout remains committed. Close editing modals, clear transient in-memory fields, remove temporary client draft storage created by this feature, show locked screen for the preferred method with full-password fallback. Never delete existing saved policies, users, push subscriptions, or persisted business data. Timer resets only on actual authenticated user interaction, not background scheduler, push receipt, network polling or app boot.

### DEC-03 — LOST OLD PHONE: AGENCY AUTHORITY ISSUES A NEW FULL PASSWORD
If the old phone is inaccessible, there is **one recovery route**: an authorized agency officer resets the user's account and **issues a new full account password**; user then signs in on the new phone using username + new password and enrolls a new device/method. No recovery through old device, PIN, Face ID, emailed reset link, or automatic device transfer for this lost-phone scenario. Officer must be an authorized partner/manager in the SAME agency with permission over target user; no self-service elevation or cross-agency reset. The reset must revoke ALL prior sessions, refresh grants, PIN and passkey quick-login grants and trusted-device associations so old phone cannot continue. Record who initiated, whose account, timestamp and revocation outcome, without storing/logging password. Do not email plaintext passwords. Officer communicates temporary full password via a controlled out-of-band channel; enforce change of temporary password at first successful login before device enrollment. Existing /api/users/{user_id}/reset-password and personnel UI should be reused/secured rather than duplicated. If agency relationship is not represented in current schema, DO NOT assume all users belong to one agency: inspect mapping and fail closed until correct scoping is implemented. Partner/manager permissions cannot reset higher/equal roles unless existing explicit business authorization says otherwise. This officer-issued password flow is the lost-device exception to self-service email recovery.

### DEC-04 — STANDARD VERIFIED-EMAIL FLOW FOR ORDINARY PASSWORD RECOVERY
For normal 'Forgot password' (not lost-device transfer), follow standard secure industry practice: authenticated email verification on enrollment/change, send single-use verification link, do not treat an existing unverified address as verified, keep legacy password login available, generic non-enumerating reset request response, one-use random hashed reset token, 15-minute expiry, rate limit, revoke active sessions on reset. No SMTP provider chosen: implement provider-neutral configurable SMTP with secure default fail-closed; do not invent credentials or make a production claim without configured mail delivery. A user without verified email must use authorized agency officer recovery. Do not send or reveal plaintext passwords in emails. This standard email flow does not supersede DEC-03 for an inaccessible old phone.

### DEC-05 — LOGOUT / DEVICE REVOCATION STOPS PUSH UNTIL NEW DEVICE ACTIVATION OR TRANSFER
When a user **logs out** or **a device is revoked**, the user must receive **no further notifications on the affected device**, and if the action leaves no activated receiving device for that user, **no notifications are delivered for that user** until a new device is activated or the user is formally transferred/assigned to an authorized active receiving device/account. This rule applies to server-triggered renewal/expiry push even if PWA is closed and push subscriptions technically remain stored. Enforce suppression on SERVER push recipient selection (authorization/active device/subscription ownership), not merely by hiding UI or unregistering service worker. Logout current device disables that device's subscription/recipient eligibility; revocation disables the revoked device and associated subscriptions. Do not delete other users' subscriptions. If the user has another authorized activated device, that device may continue receiving notifications unless user-level logout-all/revocation explicitly disables all. Activation of a new device after verified full-password login and explicit push permission/subscription can re-enable notifications; no automatic re-enable from stale subscription. 'Transfer' requires authorized agency operation, explicit recipient reassignment, and a valid activated device; never route to a different user without permission. Keep scheduled push job running and policies intact; filter ineligible recipients at send time. Avoid changing push-service code unless required for this rule; unlike general push protection, **minimal targeted changes to push recipient selection/subscription status are now expressly permitted**, with regression tests demonstrating no push after logout/revoke and correct resumption on activation. Do not redeploy TEST.

### MANDATORY CONSISTENCY CHECK
Update docs/SECURE_LOGIN_AUDIT.md, API contract, DB migration plan, UI state machine, test matrix and handoff to match DEC-01..05. Remove conflicting behavior from earlier proposed design, especially allowing PIN+Face ID together, retaining unsaved drafts, old-phone self-service reset, treating email as already verified, and delivering push after logout. Explicitly distinguish logout-current-device vs logout-all and device-specific suppression vs no-active-device user suppression. If implementation is blocked by security/platform constraints, mark blocked rather than improvising.
