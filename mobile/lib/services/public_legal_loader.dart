import 'dart:convert';

import 'package:http/http.dart' as http;

import '../core/config.dart';
import 'legal_repository.dart';

/// Public Impressum / Datenschutz before login.
class PublicLegalLoader {
  static Future<PublicLegalBundle> load() async {
    try {
      final base = AppConfig.apiBaseUrl.replaceAll(RegExp(r'/+$'), '');
      final uri = Uri.parse('$base/api/public/tenant-branding');
      final res = await http.get(uri).timeout(const Duration(seconds: 8));
      if (res.statusCode < 200 || res.statusCode >= 300) {
        return PublicLegalBundle.empty;
      }
      final decoded = jsonDecode(res.body);
      if (decoded is! Map) return PublicLegalBundle.empty;
      final map = Map<String, dynamic>.from(decoded);
      final impressum = (map['impressumText'] as String?)?.trim() ?? '';
      final datenschutz = (map['datenschutzText'] as String?)?.trim() ?? '';
      final name = (map['companyName'] as String?)?.trim().isNotEmpty == true
          ? (map['companyName'] as String).trim()
          : ((map['operatorName'] as String?)?.trim() ??
              (map['platformName'] as String?)?.trim() ??
              '');
      final email = (map['operatorEmail'] as String?)?.trim() ??
          (map['invoiceOperatorEmail'] as String?)?.trim() ??
          '';
      return PublicLegalBundle(
        impressumText: impressum,
        datenschutzText: datenschutz,
        contentVersion: _hashVersion('$impressum\n$datenschutz'),
        controller: LegalContact(
          name: name,
          email: email,
          phone: (map['operatorPhone'] as String?)?.trim() ?? '',
          street: (map['operatorStreet'] as String?)?.trim() ?? '',
          zipCity: (map['operatorZipCity'] as String?)?.trim() ?? '',
          website: (map['operatorWebsite'] as String?)?.trim() ?? '',
        ),
      );
    } catch (_) {
      return PublicLegalBundle.empty;
    }
  }

  static String _hashVersion(String raw) {
    // Stable short fingerprint for consent re-prompt (not cryptographic).
    var h = 0;
    for (final cu in raw.codeUnits) {
      h = (h * 31 + cu) & 0x7fffffff;
    }
    return 'v${h.toRadixString(16)}';
  }
}

class PublicLegalBundle {
  const PublicLegalBundle({
    required this.impressumText,
    required this.datenschutzText,
    required this.contentVersion,
    this.controller,
  });

  final String impressumText;
  final String datenschutzText;
  final String contentVersion;
  final LegalContact? controller;

  static const empty = PublicLegalBundle(
    impressumText: '',
    datenschutzText: '',
    contentVersion: 'v0',
  );
}
