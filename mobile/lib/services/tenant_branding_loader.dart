import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

import '../core/config.dart';
import '../core/tenant_branding.dart';

/// Loads public tenant branding before login (host-based white-label).
class TenantBrandingLoader {
  static Future<TenantBranding> loadPublic() async {
    try {
      final base = AppConfig.apiBaseUrl.replaceAll(RegExp(r'/+$'), '');
      final uri = Uri.parse('$base/api/public/tenant-branding');
      final res = await http.get(uri).timeout(const Duration(seconds: 8));
      if (res.statusCode < 200 || res.statusCode >= 300) {
        return TenantBranding.fallback;
      }
      final payload = jsonDecode(res.body);
      if (payload is Map<String, dynamic>) {
        return TenantBranding.fromPublicPayload(payload);
      }
      if (payload is Map) {
        return TenantBranding.fromPublicPayload(Map<String, dynamic>.from(payload));
      }
    } catch (_) {
      // optional
    }
    return TenantBranding.fallback;
  }
}
