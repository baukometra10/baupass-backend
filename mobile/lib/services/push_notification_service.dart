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

  /// Wire [firebase_messaging] when Firebase project files are present.
  Future<String?> obtainNativeDeviceToken() async {
    // return await FirebaseMessaging.instance.getToken();
    return null;
  }

  Future<void> initializeAfterLogin(WorkerSession session) async {
    if (!await isEnabled()) return;
    final token = await obtainNativeDeviceToken();
    if (token == null || token.isEmpty) return;
    try {
      await registerIfEnabled(session: session, deviceToken: token);
    } catch (_) {}
  }
}
