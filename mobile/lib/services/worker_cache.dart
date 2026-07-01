import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../core/tenant_branding.dart';

/// Cached worker profile / attendance state for offline UX.
class WorkerCache {
  static const _profileKey = 'baupass_worker_cached_profile';
  static const _brandingKey = 'baupass_worker_cached_branding';
  static const _openCheckInKey = 'baupass_worker_open_checkin';

  Future<void> saveProfile(Map<String, dynamic> mePayload) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_profileKey, jsonEncode(mePayload));
    final siteAccess = mePayload['siteAccess'] as Map<String, dynamic>?;
    if (siteAccess != null && siteAccess['openCheckInToday'] is bool) {
      await prefs.setBool(_openCheckInKey, siteAccess['openCheckInToday'] as bool);
    }
  }

  Future<void> saveBranding(TenantBranding branding) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_brandingKey, jsonEncode(branding.toCacheJson()));
  }

  Future<TenantBranding?> loadBranding() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_brandingKey);
    if (raw == null) return null;
    try {
      final parsed = jsonDecode(raw);
      if (parsed is Map<String, dynamic>) {
        return TenantBranding.fromCacheJson(parsed);
      }
      if (parsed is Map) {
        return TenantBranding.fromCacheJson(Map<String, dynamic>.from(parsed));
      }
    } catch (_) {}
    return null;
  }

  Future<Map<String, dynamic>?> loadProfile() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_profileKey);
    if (raw == null) return null;
    try {
      final parsed = jsonDecode(raw);
      if (parsed is Map<String, dynamic>) return parsed;
      if (parsed is Map) return Map<String, dynamic>.from(parsed);
    } catch (_) {}
    return null;
  }

  Future<bool> openCheckInToday() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_openCheckInKey) ?? false;
  }

  Future<void> setOpenCheckInToday(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_openCheckInKey, value);
  }

  String? badgeIdFromProfile(Map<String, dynamic>? profile) {
    final worker = profile?['worker'] as Map<String, dynamic>?;
    return worker?['badgeId'] as String?;
  }
}
