import 'dart:io';

import 'package:shared_preferences/shared_preferences.dart';

import '../core/api_client.dart';
import '../core/session_store.dart';

/// Native push (FCM / APNs) integration point.
class PushNotificationService {
  PushNotificationService(this._api);

  final ApiClient _api;
  static const _enabledKey = 'baupass_push_enabled';

  Future<bool> isEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_enabledKey) ?? false;
  }

  Future<void> setEnabled(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_enabledKey, value);
  }

  Future<void> registerIfEnabled({required WorkerSession session, required String deviceToken}) async {
    if (!await isEnabled()) return;
    final deviceType = Platform.isIOS ? 'ios' : 'android';
    await _api.postJson(
      '/api/worker-app/push/register',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: <String, dynamic>{
        'pushToken': deviceToken,
        'platform': deviceType,
        'deviceName': Platform.operatingSystemVersion,
        if (session.deviceId != null) 'deviceId': session.deviceId,
      },
    );
  }

  /// Native FCM token: set via --dart-define=BAUPASS_FCM_TOKEN=... for CI/dev,
  /// or wire firebase_messaging when google-services.json is in the project.
  Future<String?> obtainNativeDeviceToken() async {
    const fromDefine = String.fromEnvironment('BAUPASS_FCM_TOKEN');
    if (fromDefine.isNotEmpty) return fromDefine;
    // When firebase_messaging is added: return FirebaseMessaging.instance.getToken();
    return null;
  }

  /// Returns true when a token was registered with the backend.
  Future<bool> initializeAfterLogin(WorkerSession session) async {
    if (!await isEnabled()) return false;
    final token = await obtainNativeDeviceToken();
    if (token == null || token.isEmpty) return false;
    try {
      await registerIfEnabled(session: session, deviceToken: token);
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<Map<String, dynamic>?> fetchServerPushStatus({required WorkerSession session}) async {
    try {
      return await _api.getJson(
        '/api/worker-app/push/status',
        bearerToken: session.bearer,
        deviceId: session.deviceId,
      );
    } catch (_) {
      return null;
    }
  }
}
