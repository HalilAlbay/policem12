import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiException implements Exception {
  final int status;
  final String message;
  const ApiException(this.status, this.message);
  @override String toString() => message;
}

class PolicemApi {
  static const baseUrl = String.fromEnvironment('POLICEM_API_URL',
      defaultValue: 'https://policem12-pilot.onrender.com');
  final http.Client client;
  PolicemApi({http.Client? client}) : client = client ?? http.Client();

  Future<Map<String, dynamic>> _request(String method, String path,
      {Map<String, dynamic>? body, String? token}) async {
    final uri = Uri.parse('$baseUrl$path');
    final headers = <String, String>{'Accept': 'application/json'};
    if (body != null) headers['Content-Type'] = 'application/json';
    if (token != null) headers['Authorization'] = 'Bearer $token';
    final response = method == 'POST'
        ? await client.post(uri, headers: headers, body: body == null ? null : jsonEncode(body))
        : await client.get(uri, headers: headers);
    Map<String, dynamic> data;
    try {
      data = jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    } catch (_) {
      throw ApiException(response.statusCode, 'Sunucu yanıtı geçersiz');
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw ApiException(response.statusCode, response.statusCode == 401
          ? 'Oturum geçersiz veya kullanıcı bilgileri hatalı'
          : response.statusCode == 429 ? 'Çok fazla deneme. Daha sonra tekrar deneyin.'
          : 'İşlem başarısız (HTTP ${response.statusCode})');
    }
    return data;
  }

  Future<Map<String, dynamic>> login(String username, String password) =>
      _request('POST', '/api/login', body: {'username': username, 'password': password});
  Future<Map<String, dynamic>> me(String token) =>
      _request('GET', '/api/me', token: token);
  Future<void> logout(String token) async {
    await _request('POST', '/api/logout', token: token);
  }
  Future<Map<String, dynamic>> getSummary(String token, {String period = 'month'}) =>
      _request('GET', '/api/summary?period=$period', token: token);
  Future<List<dynamic>> getPolicies(String token, {String kind = 'active', String period = 'month'}) async {
    final uri = Uri.parse('$baseUrl/api/policies').replace(queryParameters: {'kind':kind,'period':period});
    final response = await client.get(uri, headers: {'Authorization':'Bearer $token'});
    if (response.statusCode != 200) throw ApiException(response.statusCode, 'Poliçeler alınamadı');
    final decoded = jsonDecode(utf8.decode(response.bodyBytes));
    if (decoded is! List) throw const ApiException(502, 'Poliçe yanıtı geçersiz');
    return decoded;
  }
  Future<Map<String, dynamic>> getFinance(String token, {String period = 'month'}) =>
      _request('GET', '/api/finance/summary?period=$period', token: token);
  void close() => client.close();
}
