# Secure login API contract

Status: **P1 contract (implemented surface will be updated in each later stage).**
Baseline: `d577d2a03a81a4f4cb79d4b39cde223ba79533e3`.
Canonical browser origin is not yet configured; cookie-backed endpoints fail closed until it is.

## Common rules

- JSON errors use `{"detail":{"code":"..."}}` for new security states; no token, PIN, password, challenge, signature, or stack trace is returned. Existing legacy auth failures retain their generic Turkish detail for compatibility.
- `Authorization: Bearer <access token>` is required for protected endpoints unless a later endpoint is explicitly described as a pre-authentication flow. Access and refresh credentials are never put in URLs.
- Only requests carrying `X-User-Interaction: 1`, set by the client after a real local click/key/touch interaction, advance server idle activity. Background requests do not extend the session. A session idle for 900 seconds is denied with HTTP 401 `SESSION_IDLE`.
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
