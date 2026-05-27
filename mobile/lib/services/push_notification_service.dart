import 'dart:io';

import 'package:shared_preferences/shared_preferences.dart';

import '../core/api_client.dart';

/// Native push (FCM / APNs) integration point.
///
/// Wire [firebase_messaging] when `google-services.json` / `GoogleService-Info.plist`
/// are configured. Until then, preferences and API hooks are prepared.
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

  /// Call after login when user opts in. Registers device token with central backend.
  Future<void> registerIfEnabled({
    required String sessionToken,
    required String deviceToken,
  }) async {
    if (!await isEnabled()) return;
    final deviceType = Platform.isIOS ? 'ios' : 'android';
    await _api.postJson(
      '/api/device/register',
      bearerToken: sessionToken,
      body: <String, dynamic>{
        'deviceToken': deviceToken,
        'deviceType': deviceType,
        'deviceName': Platform.operatingSystemVersion,
        // Placeholder until biometric keys are implemented on device.
        'publicKey': 'push-only-${deviceToken.hashCode.abs()}',
      },
    );
  }

  /// Stub: obtain FCM/APNs token — replace with FirebaseMessaging when configured.
  Future<String?> obtainNativeDeviceToken() async {
    // return await FirebaseMessaging.instance.getToken();
    return null;
  }

  Future<void> initializeAfterLogin(String sessionToken) async {
    if (!await isEnabled()) return;
    final token = await obtainNativeDeviceToken();
    if (token == null || token.isEmpty) return;
    try {
      await registerIfEnabled(sessionToken: sessionToken, deviceToken: token);
    } catch (_) {
      // Non-fatal until Firebase project is linked.
    }
  }
}
