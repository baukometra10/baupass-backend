import 'api_client.dart';
import 'session_store.dart';
import '../services/device_identity_service.dart';

class AuthRepository {
  AuthRepository(this._api, {SessionStore? sessionStore, DeviceIdentityService? deviceIdentity})
      : _sessionStore = sessionStore ?? SessionStore(),
        _deviceIdentity = deviceIdentity ?? DeviceIdentityService();

  final ApiClient _api;
  final SessionStore _sessionStore;
  final DeviceIdentityService _deviceIdentity;

  Future<WorkerSession?> loadSession() => _sessionStore.load();

  Future<String?> loadToken() async {
    final session = await _sessionStore.load();
    return session?.token;
  }

  Future<void> saveSession(WorkerSession session) => _sessionStore.save(session);

  Future<void> clearToken() => _sessionStore.clear();

  Future<WorkerSession> loginWithBadge({
    required String badgeId,
    required String badgePin,
    Map<String, dynamic>? location,
    String? pushToken,
    bool qrLaunch = false,
  }) async {
    final device = await _deviceIdentity.loginPayload(pushToken: pushToken);
    final body = await _api.postJson(
      '/api/worker-app/login',
      body: <String, dynamic>{
        'badgeId': badgeId.trim().toUpperCase(),
        'badgePin': badgePin.trim(),
        if (location != null) 'location': location,
        if (qrLaunch) 'qrLaunch': true,
        'device': device,
      },
    );
    return _sessionFromLoginBody(body);
  }

  Future<Map<String, dynamic>> previewJoin(String accessToken) async {
    return _api.postJson(
      '/api/worker-app/join-preview',
      body: <String, dynamic>{'accessToken': accessToken.trim()},
    );
  }

  Future<WorkerSession> loginWithAccessToken(String accessToken, {String? pushToken}) async {
    final device = await _deviceIdentity.loginPayload(pushToken: pushToken);
    final body = await _api.postJson(
      '/api/worker-app/login',
      body: <String, dynamic>{
        'accessToken': accessToken.trim(),
        'device': device,
      },
    );
    return _sessionFromLoginBody(body);
  }

  Future<WorkerSession> _sessionFromLoginBody(Map<String, dynamic> body) async {
    final token = body['token'] as String?;
    if (token == null || token.isEmpty) {
      throw ApiException(500, 'missing_token', 'Login response did not include a session token.');
    }
    final session = WorkerSession(
      token: token,
      jwt: body['jwt'] as String?,
      deviceId: body['deviceId'] as String?,
    );
    await _sessionStore.save(session);
    return session;
  }

  Future<Map<String, dynamic>> fetchProfile(WorkerSession session) {
    return _api.getJson(
      '/api/worker-app/me',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
  }

  Future<void> logout(WorkerSession session) async {
    try {
      await _api.postJson(
        '/api/worker-app/logout',
        bearerToken: session.bearer,
        deviceId: session.deviceId,
      );
    } finally {
      await _sessionStore.clear();
    }
  }
}
