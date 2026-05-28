import 'package:shared_preferences/shared_preferences.dart';

/// Persisted worker session (opaque token, optional JWT, bound device id).
class WorkerSession {
  const WorkerSession({
    required this.token,
    this.jwt,
    this.deviceId,
  });

  final String token;
  final String? jwt;
  final String? deviceId;

  /// Prefer signed JWT for API calls when available.
  String get bearer => (jwt != null && jwt!.isNotEmpty) ? jwt! : token;

  bool get hasDeviceBinding => deviceId != null && deviceId!.isNotEmpty;
}

class SessionStore {
  static const _tokenKey = 'worker_session_token';
  static const _jwtKey = 'worker_session_jwt';
  static const _deviceIdKey = 'worker_bound_device_id';

  Future<WorkerSession?> load() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString(_tokenKey);
    if (token == null || token.isEmpty) return null;
    return WorkerSession(
      token: token,
      jwt: prefs.getString(_jwtKey),
      deviceId: prefs.getString(_deviceIdKey),
    );
  }

  Future<void> save(WorkerSession session) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, session.token);
    if (session.jwt != null && session.jwt!.isNotEmpty) {
      await prefs.setString(_jwtKey, session.jwt!);
    } else {
      await prefs.remove(_jwtKey);
    }
    if (session.deviceId != null && session.deviceId!.isNotEmpty) {
      await prefs.setString(_deviceIdKey, session.deviceId!);
    } else {
      await prefs.remove(_deviceIdKey);
    }
  }

  Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
    await prefs.remove(_jwtKey);
    await prefs.remove(_deviceIdKey);
  }
}
