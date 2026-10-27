# Secure login test report

Date: 2026-10-28 (Europe/Istanbul)
Commit under test: `d577d2a03a81a4f4cb79d4b39cde223ba79533e3`
Phase: P0 baseline only
Status: **BLOCKED — automated test suite could not be installed or run.**

## Baseline commands

| Command | Environment | Exit | Passed | Failed | Skipped | Evidence |
|---|---|---:|---:|---:|---:|---|
| `python -m pytest -q` | Host Python 3.11 | 1 | 0 | 0 | 0 | `No module named pytest`. |
| `py -3.12 -m venv .venv; .venv\\Scripts\\python.exe -m pip install -r requirements.txt pytest httpx` | Isolated Python 3.12 venv | 1 | 0 | 1 | 0 | Package index reported `Could not find a version that satisfies the requirement pytest (from versions: none)`; requirements/test dependencies were not installed. |
| `.venv\\Scripts\\python.exe -m pytest -q` | Isolated Python 3.12 venv | 1 | 0 | 1 | 0 | `No module named pytest`. |
| `py -3.12 -m compileall -q app.py customer_portal.py notification_core.py push_job.py push_service.py windows_main.py` | Python 3.12 standard library | 0 | 1 | 0 | 0 | Syntax compilation completed with exit code 0. This is not a substitute for the tests. |

The repository contains three pytest files: `tests/test_device_sessions.py`, `tests/test_quick_login.py`, and `tests/test_staff_permissions.py`. None executed. CI also declares test commands for `test_notification_core`, `test_push_service`, and `test_push_integration`, but these test files are not present in this branch checkout. No tests were added, skipped, or represented as passed.

## Acceptance status

| Area | Status | Reason |
|---|---|---|
| AUTH-01..04 | NOT RUN | pytest unavailable; implementation not started. |
| DEV-01..02 | NOT RUN | pytest unavailable; implementation not started. |
| WEB-01 | NOT RUN | No WebAuthn implementation; implementation not started. |
| PIN-01..03 | BLOCKED / NOT RUN | Current proof is refresh cookie + PIN; no cryptographic device-possession proof. |
| UI-01..02 | NOT RUN | Browser/DOM tests unavailable; implementation not started. |
| REC-01..02 | NOT RUN | Verified-email recovery absent; SMTP recovery configuration not selected. |
| REG-01 | NOT RUN | `tests/test_staff_permissions.py` could not execute. |
| PUSH-01 | NOT RUN | Push integration test modules referenced by workflow are absent; DEC-05 behavior needs targeted work and tests. |
| MIG-01 | NOT RUN | No empty/legacy migration test run. |
| SEC-01 | NOT RUN | No automated CSRF/origin/session/rate-limit security tests run. |
| Manual iPhone acceptance | PENDING USER | Codex does not claim real iPhone Safari/PWA testing. |

## Gate decision

P0 baseline reproducibility gate is **not passed**. Do not proceed to P1 until a supported Python environment with repository dependencies and pytest/httpx can be provided and all baseline tests run with results recorded. No feature implementation or deployment has occurred.
