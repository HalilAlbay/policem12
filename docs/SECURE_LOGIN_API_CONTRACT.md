# Secure login API contract

Status: **P1 contract (implemented surface will be updated in each later stage).**
Baseline: `d577d2a03a81a4f4cb79d4b39cde223ba79533e3`.
Cookie-backed endpoints require `POLICEM_PUBLIC_ORIGIN` to equal the request's exact Origin; explicit local tests can use `POLICEM_DEV_MODE=1` and the two fixed localhost origins. The canonical production origin is not configured in this checkout, so production cookie/WebAuthn/recovery flows remain disabled until an owner supplies the actual value.

## Common rules

- JSON errors use `{"detail":{"code":"..."}}` for new security states; no token, PIN, password, challenge, signature, or stack trace is returned. Existing legacy auth failures retain their generic Turkish detail for compatibility.
- `Authorization: Bearer <access token>` is required for protected endpoints unless a later endpoint is explicitly described as a pre-authentication flow. Access and refresh credentials are never put in URLs.
- Only requests carrying `X-User-Interaction: 1`, set by the client after a real local click/key/touch interaction, advance server idle activity. Background requests do not extend the session. A session idle for 900 seconds is denied with HTTP 401 `SESSION_IDLE`.
- Login throttling is durable: 5 failed attempts per normalized username and 30 per source IP in a 15-minute window. Scope values are hashed before persistence; success clears the username bucket. Failure responses remain generic and identical for unknown/inactive and wrong-password accounts.
- Password step-up requires the current account password, compared server-side. Foreign device/credential IDs return 404. Mutating operations are transactional and audit outcomes without secrets.
- Once the canonical public origin is configured, cookie endpoints compare the exact `Origin` with that configured origin; arbitrary `Host` is not trusted. Cookie flows use HttpOnly, Secure, SameSite=Strict, path-scoped cookies. No wildcard origin is accepted.
- Expected statuses: 200 success; 201 resource created; 204 success with no body; 400 malformed/domain-invalid data; 401 missing/invalid/idle auth; 403 authenticated but forbidden or failed step-up; 404 unknown/foreign resource; 409 conflict/capacity/replay; 422 Pydantic validation; 429 durable rate limit; 503 security method unavailable/configuration missing. Error detail is generic.

## P1 endpoints

| Method / path | Auth and request | Response / errors | Effects and audit |
|---|---|---|---|
| `POST /api/login` | Public; `{username,password}` (bounded lengths). Username/password failures share a generic 401. | Existing `{token,user}` plus `idle_expires_at`; 429 `RATE_LIMITED`; 422 validation. | On success creates a hashed 24-hour access session with server activity timestamp; failed attempt buckets are DB-backed and committed. Never logs credentials. |
| `GET /api/me` | Bearer access; client interaction header optional. | Existing public user fields plus `idle_expires_at`; 401 `AUTH_REQUIRED` or `SESSION_IDLE`. | Reads authoritative session activity. Only genuine interaction advances it. |
| `POST /api/logout` | Bearer access. | `{ok:true}`; 401 invalid/idle. | Invalidates current access session and device-bound grants for that browser device; writes a secret-free audit event. Client waits for this result and then calls refresh logout. |
| `POST /api/security/refresh/logout` | Refresh cookie; exact configured-origin check. | `{ok:true}`; 403 `ORIGIN_DENIED`. | Idempotently invalidates the presented refresh grant and clears its cookie. |
| `POST /api/security/refresh` | Existing cookie + `{pin}` interface is disabled until P3 proves independent device possession; exact origin required. | 503 `METHOD_UNAVAILABLE` until secure P3 flow is implemented; then a fresh challenge/proof and PIN will be required. | No session is issued by the legacy cookie+PIN prototype. No silent downgrade. |
| `GET /api/security/devices` | Bearer access. | `{devices:[...]}` containing only the caller's active device inventory. | Read-only; includes ID, safe label, created/last seen, method/status in later stages. |
| `POST /api/security/devices/{id}/revoke` | Bearer + `{password}` step-up. | `{ok:true}`; 403 step-up, 404 foreign/unknown device. | Atomically revokes device and its bound sessions, refresh grants, PIN/passkey credentials. Self-revoke ends the current session. |

## Later-stage endpoint additions

P2 will specify passkey registration/login begin/finish routes with challenge IDs, exact JSON shapes, single-use challenges and configured RP/origin. P3 will specify public-key device proof plus PIN unlock; the legacy refresh body will never be accepted as proof. P4 will specify preference update and device inventory fields. P5 will specify email enrollment/verification/reset and officer reset semantics. P6 will specify device/push activation and authorized transfer. These rows must be finalized before their corresponding code/schema changes; unsupported capabilities return a generic unavailable response.

## P2 WebAuthn contract (before implementation)

Configuration: `POLICEM_PUBLIC_ORIGIN` must be one exact HTTPS origin with no path/query, and `WEBAUTHN_RP_ID` must be that origin's host or a valid parent RP domain. `POLICEM_DEV_MODE=1` permits only explicit localhost HTTP for local tests. The server never derives either value from `Host`. Missing or invalid configuration returns 503 `METHOD_UNAVAILABLE` without creating a usable challenge.

| Method / path | Auth and request | Response / errors | DB/security effects |
|---|---|---|---|
| `POST /api/security/webauthn/register/options` | Bearer session + `{label,password}` fresh password step-up. | `{ceremony_id,publicKey}`; 403 step-up, 409 10-device cap, 503 config/browser method unavailable, 422 bounded data. | Generates 32 random challenge bytes, expires in 5 min, bound to exact account and current session hash. Uses `userVerification=required`, platform authenticator, resident credential, `attestation=none`; excludes that user's active credential IDs. Does not create a device yet. |
| `POST /api/security/webauthn/register/verify` | Same bearer session + `{ceremony_id,credential}`. | `{ok:true,device:{id,label,method:'webauthn'}}`; 401 expired/wrong session, 409 duplicate credential/cap, 400 generic invalid ceremony. | Atomically consumes one challenge before verification; verifies registration server-side; inserts device and public credential in one transaction; never stores private key or raw biometric. |
| `POST /api/security/webauthn/login/options` | Public; empty JSON body. | `{ceremony_id,publicKey}` with discoverable credential flow and user verification required; same-shaped generic response with no credentials if unavailable/config missing is 503. | Random single-use 5-min challenge. Does not identify an account before the authenticator response. |
| `POST /api/security/webauthn/login/verify` | Public; `{ceremony_id,credential}`. | `{token,user,idle_expires_at}`; 401 generic invalid/replay/unknown/revoked/wrong-account; 429 throttled; 503 config unavailable. | Consumes the challenge; maps only an active credential to its owner; verifies signature, challenge, client-data type, exact origin, RP ID hash, user presence/UV, sign counter and discoverable user handle; atomically updates counter/last_seen and creates a device-bound 24-hour access session. Errors disclose no account/credential existence. |

Challenges have unique opaque IDs, are bound to purpose, server-side expiry, and (for registration) exact session hash. Any verification attempt consumes its challenge even if invalid. Concurrent/replayed finishes therefore cannot issue sessions or register credentials. Browser JSON fields are size-capped before invoking the library. Library exceptions are mapped to generic client codes and never logged with assertion data.

P2 test plan: valid generated registration and assertion vectors; wrong challenge, origin, RP ID, client-data type, missing UV, forged signature, stale counter, replay, revoked credential, cross-account user handle, duplicate credential, expired challenge, and concurrent finish. The selected login label must be “Face ID / cihaz doğrulaması”; explain iOS may allow system device passcode and synced passkeys are not physical-device-only.

## Tenant and role boundaries

- A device or credential is always selected by both its ID and authenticated owner ID; mismatches return 404.
- Officer recovery in P5 uses `target user -> branch_id -> branches.agency_id` and actor's own branch/agency. Unknown/unassigned branches fail closed. Managers may reset only lower permitted staff within the same agency; partner/manager hierarchy follows current job-title rules and cannot reset equal/higher roles.
- Push recipient eligibility in P6 is checked on the server at send time using active device/subscription ownership. Logout-current-device and device revoke affect that device; user notifications stop when no active receiving device remains. Other users' subscriptions are never changed.

## P1 microplan

1. Add additive `sessions.last_activity` and durable login attempt schema; preserve absolute expiry and legacy password hashes.
2. Enforce server-side 900-second idle deadline on every `current()` protected request. Only user-interaction-tagged requests slide activity.
3. Add client real-interaction timer, exact idle lock, unsaved input/file/modal clearing, and cross-tab lock/logout broadcast.
4. Make logout await server revocation and clear local credentials; make device revoke atomic across bound session/refresh/PIN records.
5. Disable current cookie+PIN refresh until P3 implements and tests independent device possession proof.
6. Add targeted tests for idle boundary, no background extension, lockout persistence, logout, device revoke, and durable login throttling; rerun full baseline and report existing failures separately.

## P2 implementation result

- Added `webauthn==3.0.1` (BSD-3-Clause; supported runtime is Python 3.12) and the additive schema v2 migration for opaque user handles, public credentials, counters, and one-use challenges.
- Registration requires an active bearer session and fresh account password, creates a required-UV platform/resident credential with no attestation collection, and persists nothing until server verification succeeds. Duplicate credential IDs and the ten-device limit fail without partial device registration.
- Discoverable login does not accept an account name or send account-specific allow credentials. Login verifies assertion type, challenge, exact configured origin, RP hash, UV/UP, public-key signature, counter, active owner/device, and opaque userHandle. It issues only a device-bound session after verification succeeds. Client failures remain generic.
- `POLICEM_PUBLIC_ORIGIN` and `WEBAUTHN_RP_ID` are required and checked server-side; `Host` is never used. Missing/mismatched configuration returns 503. `POLICEM_DEV_MODE=1` is limited to explicit localhost HTTP on port 8000.
- P2 UI presents “Face ID / cihaz doğrulaması”, requires password step-up to add a device, keeps password login available, and explains that iOS may use its device passcode or a synced passkey. It does not claim physical-device-only assurance.
- Device revoke, password change, and account deactivation revoke associated credentials. PIN and cookie+PIN remain disabled.
- P2 verification: `tests/test_webauthn.py` includes a generated valid P-256/ES256 registration and signed discoverable assertion through the real server verifier, config fail-closed, required UV/resident/platform options, step-up, no account selector, and consumed-invalid-challenge checks. Focused WebAuthn/session/device/legacy suite: 18 passed, 0 failed.
- Not yet proved on a real iPhone: browser/Safari passkey UX, device passcode prompt, or deployment-origin/RP configuration. Those require final environment configuration and the requested physical acceptance test; no security success is inferred from TestClient vectors alone.

## P1 implementation result

- `sessions.last_activity`, `auth_attempts`, and the version marker are additive/idempotent. First security-schema initialization revokes the unsafe prototype trusted-device state, removes bound access/refresh/PIN proof rows, preserves unbound password sessions and business data, and emits a secret-free audit event.
- Password login creates server-timed idle state, bounds inputs, uses a dummy PBKDF2 hash for unknown usernames, and applies the durable username/IP limits above. Every protected API reaches the same 900-second server check through `current()`.
- The client tracks real pointer/key/touch input, sends a throttled activity request, locks at the deadline, clears form/select/file data and modals, and broadcasts lock/logout/activity across tabs. API-originated idle denial locks even when the browser timer was suspended.
- The legacy cookie+PIN enrollment and refresh endpoints return 503 `METHOD_UNAVAILABLE`; Settings shows password-only and explicitly labels PIN unavailable. This is a fail-closed interim state until P3 device possession proof is implemented; no quick-login success is claimed.
- Focused checks: 19 passed. Full suite after P1: 40 passed, 6 failed, 33 warnings. The six failures are the baseline staff API fixture (five outdated expectations) and the existing 30-day notification test; see `SECURE_LOGIN_TEST_REPORT.md`.
