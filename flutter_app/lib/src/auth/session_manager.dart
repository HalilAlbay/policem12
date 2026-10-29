import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../api/policem_api.dart';

class SessionManager {
  static const _key = 'policem_access_token';
  final PolicemApi api;
  final FlutterSecureStorage storage;
  SessionManager(this.api, {FlutterSecureStorage? storage})
      : storage = storage ?? const FlutterSecureStorage();

  Future<Map<String, dynamic>> login(String username, String password) async {
    final result = await api.login(username, password);
    final token = result['token'];
    if (token is! String || token.isEmpty || result['user'] is! Map) {
      throw const ApiException(502, 'Giriş yanıtı eksik');
    }
    await storage.write(key: _key, value: token);
    return Map<String, dynamic>.from(result['user'] as Map);
  }

  Future<Map<String, dynamic>?> restore() async {
    final token = await storage.read(key: _key);
    if (token == null) return null;
    try {
      return await api.me(token);
    } on ApiException catch (e) {
      if (e.status == 401 || e.status == 403) {
        await storage.delete(key: _key);
        return null;
      }
      rethrow; // Network/server failures must not silently destroy the session.
    }
  }

  Future<void> logout() async {
    final token = await storage.read(key: _key);
    try {
      if (token != null) await api.logout(token);
    } finally {
      await storage.delete(key: _key);
    }
  }
}
