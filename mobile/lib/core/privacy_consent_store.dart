import 'package:shared_preferences/shared_preferences.dart';

class PrivacyConsentStore {
  static const _key = 'suppix_privacy_consent_v1';

  Future<bool> hasAccepted() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_key) ?? false;
  }

  Future<void> accept() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_key, true);
  }
}
