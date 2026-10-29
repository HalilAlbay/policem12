import 'package:local_auth/local_auth.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Local biometric gate, NOT server-side passkey authentication.
/// It only unlocks an existing server session, which is revalidated via /api/me.
class BiometricGate {
  final LocalAuthentication auth;
  final FlutterSecureStorage storage;
  static const _enabledKey = 'biometric_unlock_enabled';
  BiometricGate({LocalAuthentication? auth, FlutterSecureStorage? storage})
      : auth = auth ?? LocalAuthentication(),
        storage = storage ?? const FlutterSecureStorage();

  Future<bool> available() async {
    try {
      return (await auth.getAvailableBiometrics()).isNotEmpty;
    } catch (_) { return false; }
  }
  Future<bool> enabled() async => await storage.read(key: _enabledKey) == 'yes';
  Future<bool> verify() async {
    if (!await available()) return false;
    try {
      return await auth.authenticate(
        localizedReason: 'Poliçem oturumunu açmak için kimliğinizi doğrulayın',
        options: const AuthenticationOptions(biometricOnly: true, stickyAuth: true),
      );
    } catch (_) { return false; }
  }
  Future<bool> enroll() async {
    if (!await verify()) return false;
    await storage.write(key: _enabledKey, value: 'yes');
    return true;
  }
  Future<void> disable() => storage.delete(key: _enabledKey);
}
