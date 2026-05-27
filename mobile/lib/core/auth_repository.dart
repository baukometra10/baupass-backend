import 'package:shared_preferences/shared_preferences.dart';

import 'api_client.dart';

class AuthRepository {
  AuthRepository(this._api);

  final ApiClient _api;
  static const _tokenKey = 'worker_session_token';

  Future<String?> loadToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_tokenKey);
  }

  Future<void> saveToken(String token) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, token);
  }

  Future<void> clearToken() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }

  /// Daily login: Badge-ID + PIN (same contract as worker PWA).
  Future<String> loginWithBadge({
    required String badgeId,
    required String badgePin,
    Map<String, dynamic>? location,
  }) async {
    final body = await _api.postJson(
      '/api/worker-app/login',
      body: <String, dynamic>{
        'badgeId': badgeId.trim().toUpperCase(),
        'badgePin': badgePin.trim(),
        if (location != null) 'location': location,
      },
    );
    final token = body['token'] as String?;
    if (token == null || token.isEmpty) {
      throw ApiException(500, 'missing_token', 'Login response did not include a session token.');
    }
    await saveToken(token);
    return token;
  }

  /// Login with one-time access token from admin (visitors / onboarding).
  Future<String> loginWithAccessToken(String accessToken) async {
    final body = await _api.postJson(
      '/api/worker-app/login',
      body: <String, dynamic>{'accessToken': accessToken.trim()},
    );
    final token = body['token'] as String?;
    if (token == null || token.isEmpty) {
      throw ApiException(500, 'missing_token', 'Login response did not include a session token.');
    }
    await saveToken(token);
    return token;
  }

  Future<Map<String, dynamic>> fetchProfile(String token) {
    return _api.getJson('/api/worker-app/me', bearerToken: token);
  }

  Future<void> logout(String token) async {
    try {
      await _api.postJson('/api/worker-app/logout', bearerToken: token);
    } finally {
      await clearToken();
    }
  }
}
