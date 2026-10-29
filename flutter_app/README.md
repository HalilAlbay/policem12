# Poliçem Flutter migration — initial scaffold

Status: **source scaffold only**. Not compiled or tested on Android/iOS.
The production FastAPI app remains untouched on main.

## Goal
Build iOS/Android Flutter clients against the existing FastAPI API.
Keep business rules and data ownership on the server.

## Next steps (not implemented)
1. Inspect the actual login JSON request/response and cookie/session contract.
2. Implement an authenticated API client with safe mobile session storage.
3. Add login and logout integration tests; then implement dashboard and policy flows.
4. Design a native biometric unlock flow. The current WebAuthn browser passkey
   mechanism must not be assumed to work unchanged through Flutter local_auth.
5. Run flutter analyze, flutter test, Android emulator, and physical iPhone tests.

Do not deploy this scaffold to Render: it is not a backend replacement.
