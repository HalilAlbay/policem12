# Secure login database migration plan

Status: **P1 additive SQLite migration implemented; later phases append exact DDL before use.**
Baseline schema: `app.init()` at `d577d2a03a81a4f4cb79d4b39cde223ba79533e3`.
Database path remains `POLICEM_DATA/policem.sqlite3`; no live/Render database is used.

## P1 schema changes

All time values in this document are UTC Unix seconds unless noted. Run each statement inside the existing database transaction, with `PRAGMA foreign_keys=ON`; do not rebuild or drop any business table.

```sql
ALTER TABLE sessions ADD COLUMN last_activity INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS auth_schema_meta (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  version INTEGER NOT NULL
);
INSERT OR IGNORE INTO auth_schema_meta(id,version) VALUES (1,1);

CREATE TABLE IF NOT EXISTS auth_attempts (
  scope_hash TEXT PRIMARY KEY,
  attempts INTEGER NOT NULL CHECK (attempts >= 0),
  window_started INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auth_attempts_updated
  ON auth_attempts(updated_at);
```

`ALTER TABLE` is guarded by `PRAGMA table_info(sessions)` so a second startup does not repeat it. Existing, unexpired session rows with `last_activity=0` are initialized once to the migration server time; their existing absolute `expires` value is unchanged. New password or validated quick-login sessions set both `expires` and `last_activity` explicitly. Expired session rows are not extended. Attempt keys are SHA-256 hashes of normalized scope labels (username or client IP); raw IP/username is not stored in the rate-limit table. Failed attempts commit before the generic response. Rows older than one day can be pruned transactionally.

On the first security schema initialization only (`auth_schema_meta` did not exist before migration), invalidate prototype quick-login material: mark active `trusted_devices` revoked, delete sessions bound through `device_sessions`, delete refresh grants, and delete four-digit PIN hashes. Keep unbound password sessions and all account/business records. Write a secret-free migration audit row when any active device was revoked. Password login remains available; old cookie+PIN state cannot become usable if later code enables secure quick login.

`auth_schema_meta` has a single-row version marker. Upgrade is additive and idempotent. The P1 code checks `PRAGMA table_info(sessions)` and uses a first-initialization marker before revoking legacy quick-login grants. If any required statement or verification fails, startup must fail closed; do not serve requests with a partially applied schema. The test suite runs migration against empty and legacy fixtures, then starts a second time and verifies columns, counts, and preserved password data.

## Existing data preserved

No change to `users.password_hash`, `users.role`, `users.branch_id`, policy/renewal/customer records, or push subscriptions. Existing session `expires`, primary key, and user foreign key remain unchanged. Prototype device rows remain for audit but become revoked; associated prototype PIN hashes and refresh grants are invalidated because their proof model is insufficient. New secure device credentials are added in later phases. No live DB operation is permitted.

P1 verification: `tests/test_auth_session.py::test_legacy_schema_migrates_additively_and_second_startup_is_safe` passed, including unchanged legacy password hash and active session row preservation. All current device/session tests passed.

## P2 WebAuthn schema changes

The idempotent P2 migration adds a stable random opaque `users.webauthn_user_handle` (unique where non-NULL), `webauthn_credentials`, and `webauthn_challenges`; it advances `auth_schema_meta.version` to 2. Existing users and business rows are retained. User handles contain no username/PII and are used for discoverable credentials. Credential rows contain only credential IDs, public keys, counters, backup/device metadata, and timestamps; authenticator private keys and biometric data never reach the server.

`webauthn_credentials.credential_id` is the primary key. Each row belongs to exactly one user and a trusted device. Revocation timestamps are authoritative; device revoke, account deactivation, and password change revoke the matching credential rows. Challenges have random opaque IDs, 32-byte challenges, a `register`/`login` purpose, 5-minute expiry, optional owner and access-session hash, optional device label, and a consumed timestamp. Verification consumes a matching unexpired challenge through a conditional update before parsing or cryptographic verification, so malformed attempts, races, and replays cannot retry a ceremony.

P2 migration verification: generated EC2/ES256 registration and discoverable-login ceremonies exercise the verifier end to end. A v2 metadata value is expected after migration. No live or Render database was touched.

## P3 PIN device-proof schema plan

The additive v3 migration creates `pin_device_keys` (device/user ownership, public JWK, creation/revocation timestamps) and `pin_challenges` (purpose, challenge, device/account/session binding, label, expiry, consumed timestamp). Existing `device_pin` stores only a salted scrypt hash plus persistent failures/lock time; it remains per-device. No existing account, session, policy, or notification data is removed. PIN lock state survives app restarts and is cleared only by authorized password recovery or replacement enrollment. `auth_schema_meta.version` advances to 3.

The additive v4 migration adds `trusted_devices.installation_id`, challenge installation binding, and `device_login_settings` with one selected `(installation) -> (user, device, method)` row. Existing trusted devices migrate to `installation_id=device_id` and are not automatically selected, so all existing users retain password login until they enroll/select on the current installation. Revoking or replacing a device deletes its selection in the same transaction. `auth_schema_meta.version` advances to 4.

## Rollback

Application rollback is to the pre-migration source SHA; SQLite safely ignores the added column and tables, so no destructive reverse migration is needed. Do not drop migration tables/columns because a previous binary may have already written rows. When rolling back to code that predates idle enforcement, old binaries ignore `sessions.last_activity` and `auth_attempts`. Preserve a database backup according to the deployment's existing persistence procedure before any eventual production migration; no deployment is in scope here.

## Later-phase schema additions (must be specified before each change)

- P2: WebAuthn credential table keyed by credential ID and owner, single-use expiring challenge table bound to user/session/purpose/origin, indexes/unique constraints, and disabled-on-revoke state.
- P3: device possession public-key material, PIN verifier, per-user/device durable attempts and lock deadline. No private key is stored server-side. The exact proof must make a stolen refresh cookie + PIN without the device private key fail.
- P4: per-device selected login method and activation state, constrained to `password|pin|webauthn` and never both quick methods.
- P5: verified-email timestamp, one-use hashed email verification/reset tokens with 15-minute expiry, temporary-password-change-required state, and secret-free officer reset audit.
- P6: push device/subscription association and active receiving eligibility, transfer audit/state. Existing subscription rows are migrated conservatively inactive until the user activates a device; do not delete subscriptions.

For each addition: include exact SQL, foreign keys, indexes, constraints, retention, unique keys, rollback behavior, fresh/legacy fixture tests, and second-startup idempotence before applying it. Existing business tables remain additive-only.

## P5 migration result

The additive v5 migration adds `users.must_change_password INTEGER NOT NULL DEFAULT 0`, nullable `users.email_verified_at`, nullable `users.pending_email`, and `account_tokens` with hashed token primary key, purpose constraint, owner, email, creation/expiry/consumption timestamps, and an expiry index. Existing email addresses are unverified (`email_verified_at=NULL`) and existing users retain password login. Verification links expire after 24 hours; password reset links expire after 30 minutes. Expired token rows are pruned without touching account/business records. `auth_schema_meta.version` advances to 5.
