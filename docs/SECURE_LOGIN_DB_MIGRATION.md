# Secure login database migration plan

Status: **P1 additive SQLite migration plan; later phases append their exact DDL before use.**
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

`auth_schema_meta` has a single-row version marker. Upgrade is additive and idempotent. If any required statement or verification fails, startup must fail closed; do not serve requests with a partially applied schema. Run migration once against (1) an empty test DB and (2) a fixture built from the baseline schema, then run startup a second time and verify columns, row counts, foreign keys, and existing password/policy rows.

## Existing data preserved

No change to `users.password_hash`, `users.role`, `users.branch_id`, policy/renewal/customer records, audit history, push subscriptions, or existing session `expires`. The `sessions` primary key and user foreign key remain unchanged. Current `trusted_devices`, `device_sessions`, `refresh_sessions`, and `device_pin` are retained while later phases add credential and activation state. No data deletion or live DB operation is permitted.

## Rollback

Application rollback is to the pre-migration source SHA; SQLite safely ignores the added column and tables, so no destructive reverse migration is needed. Do not drop migration tables/columns because a previous binary may have already written rows. When rolling back to code that predates idle enforcement, old binaries ignore `sessions.last_activity` and `auth_attempts`. Preserve a database backup according to the deployment's existing persistence procedure before any eventual production migration; no deployment is in scope here.

## Later-phase schema additions (must be specified before each change)

- P2: WebAuthn credential table keyed by credential ID and owner, single-use expiring challenge table bound to user/session/purpose/origin, indexes/unique constraints, and disabled-on-revoke state.
- P3: device possession public-key material, PIN verifier, per-user/device durable attempts and lock deadline. No private key is stored server-side. The exact proof must make a stolen refresh cookie + PIN without the device private key fail.
- P4: per-device selected login method and activation state, constrained to `password|pin|webauthn` and never both quick methods.
- P5: verified-email timestamp, one-use hashed email verification/reset tokens with 15-minute expiry, temporary-password-change-required state, and secret-free officer reset audit.
- P6: push device/subscription association and active receiving eligibility, transfer audit/state. Existing subscription rows are migrated conservatively inactive until the user activates a device; do not delete subscriptions.

For each addition: include exact SQL, foreign keys, indexes, constraints, retention, unique keys, rollback behavior, fresh/legacy fixture tests, and second-startup idempotence before applying it. Existing business tables remain additive-only.
