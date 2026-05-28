import 'dart:io';

import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

/// Stable per-install device fingerprint for server-side device binding.
class DeviceIdentityService {
  static const _fingerprintKey = 'baupass_device_fingerprint';

  Future<String> fingerprint() async {
    final prefs = await SharedPreferences.getInstance();
    final existing = prefs.getString(_fingerprintKey);
    if (existing != null && existing.isNotEmpty) {
      return existing;
    }
    final generated = const Uuid().v4();
    await prefs.setString(_fingerprintKey, generated);
    return generated;
  }

  Future<Map<String, dynamic>> loginPayload({String? pushToken}) async {
    final fp = await fingerprint();
    return <String, dynamic>{
      'fingerprint': fp,
      'name': _deviceName(),
      'platform': Platform.isIOS ? 'ios' : 'android',
      if (pushToken != null && pushToken.isNotEmpty) 'pushToken': pushToken,
    };
  }

  String _deviceName() {
    if (Platform.isIOS) return 'iPhone (${Platform.operatingSystemVersion})';
    return 'Android (${Platform.operatingSystemVersion})';
  }
}
