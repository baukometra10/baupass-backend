import '../core/api_client.dart';
import '../core/session_store.dart';

/// Impressum & Datenschutz from admin "Rechtliches" settings.
class LegalRepository {
  LegalRepository(this._api);

  final ApiClient _api;

  Future<LegalContent> fetch(WorkerSession session) async {
    final data = await _api.getJson(
      '/api/worker-app/legal',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    return LegalContent.fromJson(data);
  }
}

class LegalContact {
  const LegalContact({
    required this.name,
    this.email = '',
    this.phone = '',
    this.street = '',
    this.zipCity = '',
    this.website = '',
  });

  final String name;
  final String email;
  final String phone;
  final String street;
  final String zipCity;
  final String website;

  bool get hasAny =>
      name.trim().isNotEmpty ||
      email.trim().isNotEmpty ||
      phone.trim().isNotEmpty ||
      street.trim().isNotEmpty ||
      zipCity.trim().isNotEmpty ||
      website.trim().isNotEmpty;

  factory LegalContact.fromJson(Map<String, dynamic>? json) {
    if (json == null) {
      return const LegalContact(name: '');
    }
    return LegalContact(
      name: (json['name'] as String?)?.trim() ?? '',
      email: (json['email'] as String?)?.trim() ?? '',
      phone: (json['phone'] as String?)?.trim() ?? '',
      street: (json['street'] as String?)?.trim() ?? '',
      zipCity: (json['zipCity'] as String?)?.trim() ?? '',
      website: (json['website'] as String?)?.trim() ?? '',
    );
  }
}

class LegalContent {
  const LegalContent({
    required this.impressumText,
    required this.datenschutzText,
    required this.hasImpressum,
    required this.hasDatenschutz,
    this.contentVersion = 'v0',
    this.controller,
    this.operator,
    this.sectionTitle = 'Impressum & Datenschutz',
    this.sectionEyebrow = 'Rechtliches',
  });

  final String impressumText;
  final String datenschutzText;
  final bool hasImpressum;
  final bool hasDatenschutz;
  final String contentVersion;
  final LegalContact? controller;
  final LegalContact? operator;
  final String sectionTitle;
  final String sectionEyebrow;

  factory LegalContent.fromJson(Map<String, dynamic> json) {
    Map<String, dynamic>? asMap(dynamic value) {
      if (value is Map<String, dynamic>) return value;
      if (value is Map) return Map<String, dynamic>.from(value);
      return null;
    }

    final impressum = (json['impressumText'] as String?)?.trim() ?? '';
    final datenschutz = (json['datenschutzText'] as String?)?.trim() ?? '';
    return LegalContent(
      impressumText: impressum,
      datenschutzText: datenschutz,
      hasImpressum: json['hasImpressum'] == true || impressum.isNotEmpty,
      hasDatenschutz: json['hasDatenschutz'] == true || datenschutz.isNotEmpty,
      contentVersion: (json['contentVersion'] as String?)?.trim().isNotEmpty == true
          ? (json['contentVersion'] as String).trim()
          : 'v0',
      controller: LegalContact.fromJson(asMap(json['controller'])),
      operator: LegalContact.fromJson(asMap(json['operator'])),
      sectionTitle: (json['sectionTitle'] as String?)?.trim().isNotEmpty == true
          ? (json['sectionTitle'] as String).trim()
          : 'Impressum & Datenschutz',
      sectionEyebrow: (json['sectionEyebrow'] as String?)?.trim().isNotEmpty == true
          ? (json['sectionEyebrow'] as String).trim()
          : 'Rechtliches',
    );
  }
}
