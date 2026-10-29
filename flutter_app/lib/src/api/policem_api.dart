/// API endpoint configuration only. No authentication implementation yet.
class PolicemApi {
  static const String baseUrl = String.fromEnvironment(
    'POLICEM_API_URL',
    defaultValue: 'https://policem12-pilot.onrender.com',
  );
}
