# Poliçem Flutter migration

Implemented in isolated branch `feature/flutter-migration`:
- Backend API integration: POST /api/login, GET /api/me, POST /api/logout.
- Secure local session token storage; 401/403 clears invalid tokens.
- iOS Face ID / Android biometrics via local_auth, user opt-in after password login.
- Dashboard with role-sensitive navigation: active/upcoming/offer/issued cards, policies, and partner-only financial summary.
- HTTP mock contract tests (source added, **not executed**).

## Security boundaries
Native biometric verification is **local app unlock**, not the existing WebAuthn server-side passkey flow. A valid server session is still required. Existing server 24h session expiry and idle timeout apply; when expired, user must re-enter password. Do not describe this as biometric passwordless server login.

## Build prerequisites
The repository contains Flutter Dart sources and pubspec only; it does **not yet contain generated Android/iOS runner projects**. In a machine with Flutter installed:
```sh
cd flutter_app
flutter create --platforms=android,ios --project-name policem_flutter .
flutter pub get
flutter analyze
flutter test
```
Then configure:
- iOS `ios/Runner/Info.plist`: `NSFaceIDUsageDescription` with clear user-facing explanation.
- Android `android/app/src/main/kotlin/.../MainActivity.kt`: use `FlutterFragmentActivity` for local_auth.
- Android manifest `USE_BIOMETRIC` and AppCompat-compatible launch theme as required by plugin.
- Confirm HTTPS domain, iOS bundle ID and Android application ID before signing/release.

## Acceptance checks pending
Physical iPhone Face ID; Android fingerprint/face; first login; restore; logout; session expiry; invalid password; role-based finance visibility; Flutter analyze/test/build.
Do not merge to main or deploy to Render until validated.
