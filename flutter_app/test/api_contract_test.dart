import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:policem_flutter/src/api/policem_api.dart';

void main() {
  test('login parses backend bearer token and user', () async {
    final api = PolicemApi(client: MockClient((request) async {
      expect(request.url.path, '/api/login');
      expect(jsonDecode(request.body)['username'], 'test');
      return http.Response(jsonEncode({'token':'abc', 'user':{'role':'staff'}}), 200);
    }));
    final data = await api.login('test','secret');
    expect(data['token'], 'abc');
  });
  test('me sends Authorization Bearer', () async {
    final api = PolicemApi(client: MockClient((request) async {
      expect(request.headers['Authorization'], 'Bearer abc');
      return http.Response('{"id":1}', 200);
    }));
    expect((await api.me('abc'))['id'], 1);
  });
  test('rate limit is mapped to API error', () async {
    final api = PolicemApi(client: MockClient((_) async => http.Response('{"detail":"blocked"}',429)));
    expect(() => api.login('a','b'), throwsA(isA<ApiException>()));
  });
}
