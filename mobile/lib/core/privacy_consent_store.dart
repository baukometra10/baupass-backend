import 'package:shared_preferences/shared_preferences.dart';

class PrivacyConsentStore {
  static const _acceptedKey = 'suppix_privacy_consent_v1';
  static const _versionKey = 'suppix_privacy_consent_version';
  static const version = '1.0';

  Future<bool> hasAccepted({String? contentVersion}) async {
    final prefs = await SharedPreferences.getInstance();
    final accepted = prefs.getBool(_acceptedKey) ?? false;
    if (!accepted) return false;
    if (contentVersion == null || contentVersion.isEmpty) return true;
    final stored = prefs.getString(_versionKey) ?? version;
    return stored == contentVersion;
  }

  Future<void> accept({String? contentVersion}) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_acceptedKey, true);
    await prefs.setString(_versionKey, contentVersion?.isNotEmpty == true ? contentVersion! : version);
  }
}
