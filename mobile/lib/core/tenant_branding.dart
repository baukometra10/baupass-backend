import 'package:flutter/material.dart';

/// White-label tenant branding from /me or public tenant-branding API.
class TenantBranding {
  const TenantBranding({
    required this.displayName,
    this.logoData,
    this.accentColor,
  });

  final String displayName;
  final String? logoData;
  final Color? accentColor;

  static const TenantBranding fallback = TenantBranding(displayName: 'Mitarbeiter');

  static const TenantBranding suppixShell = TenantBranding(
    displayName: 'SUPPIX',
    accentColor: Color(0xFF06B6D4),
  );

  bool get hasVisualIdentity =>
      (logoData != null && logoData!.isNotEmpty) ||
      accentColor != null ||
      (displayName.isNotEmpty && displayName != fallback.displayName && displayName != 'SUPPIX');

  TenantBranding mergeHostHints(TenantBranding host) {
    if (!hasVisualIdentity && host.accentColor != null) {
      return TenantBranding(
        displayName: 'SUPPIX',
        accentColor: host.accentColor,
      );
    }
    return this;
  }

  String get aiAssistantTitle => '$displayName Assistent';

  Map<String, dynamic> toCacheJson() => {
        'displayName': displayName,
        if (logoData != null && logoData!.isNotEmpty) 'logoData': logoData,
        if (accentColor != null)
          'accentColor': '#${accentColor!.toARGB32().toRadixString(16).padLeft(8, '0').substring(2)}',
      };

  static TenantBranding fromCacheJson(Map<String, dynamic> json) {
    final display = _firstNonEmpty([json['displayName']]);
    if (display.isEmpty) return fallback;
    return TenantBranding(
      displayName: display,
      logoData: _firstNonEmpty([json['logoData']]),
      accentColor: _parseColor(_firstNonEmpty([json['accentColor']])),
    );
  }

  static TenantBranding fromMePayload(Map<String, dynamic>? me) {
    if (me == null) return fallback;
    final company = me['company'];
    if (company is! Map) return fallback;
    final map = Map<String, dynamic>.from(company);
    return fromCompanyMap(map);
  }

  static TenantBranding fromPublicPayload(Map<String, dynamic>? payload) {
    if (payload == null) return fallback;
    final display = _firstNonEmpty([
      payload['portalDisplayName'],
      payload['companyName'],
      payload['platformName'],
    ]);
    if (display.isEmpty) return fallback;
    return TenantBranding(
      displayName: display,
      logoData: _firstNonEmpty([payload['logoData'], payload['brandingLogoData']]),
      accentColor: _parseColor(_firstNonEmpty([
        payload['accent'],
        payload['brandingAccentColor'],
        payload['primaryColor'],
      ])),
    );
  }

  static TenantBranding fromCompanyMap(Map<String, dynamic> company) {
    final display = _firstNonEmpty([
      company['portalDisplayName'],
      company['portal_display_name'],
      company['name'],
    ]);
    if (display.isEmpty) return fallback;
    return TenantBranding(
      displayName: display,
      logoData: _firstNonEmpty([
        company['brandingLogoData'],
        company['branding_logo_data'],
      ]),
      accentColor: _parseColor(_firstNonEmpty([
        company['brandingAccentColor'],
        company['branding_accent_color'],
      ])),
    );
  }

  String get initials => deriveInitials(displayName);

  String get chatTitle => displayName.isEmpty ? 'Chat mit Firma' : 'Chat mit $displayName';

  static const Color defaultSeed = Color(0xFF1B5E8C);

  Color get effectiveSeed => accentColor ?? defaultSeed;

  Color get onAccentColor {
    return effectiveSeed.computeLuminance() > 0.55 ? const Color(0xFF111827) : Colors.white;
  }

  ThemeData themeData({ThemeData? base}) {
    final scheme = ColorScheme.fromSeed(seedColor: effectiveSeed);
    if (base == null) {
      return ThemeData(colorScheme: scheme, useMaterial3: true);
    }
    return base.copyWith(colorScheme: scheme);
  }

  static String deriveInitials(String name) {
    final cleaned = name.trim().replaceAll(RegExp(r'\s+'), ' ');
    if (cleaned.isEmpty) return 'MI';
    final parts = cleaned.split(RegExp(r'[\s\-–—]+')).where((p) => p.isNotEmpty).toList();
    if (parts.length >= 2) {
      return '${parts[0][0]}${parts[1][0]}'.toUpperCase();
    }
    final word = parts.first;
    if (word.length >= 2) return word.substring(0, 2).toUpperCase();
    return word[0].toUpperCase();
  }

  static String _firstNonEmpty(List<dynamic> values) {
    for (final value in values) {
      final text = (value ?? '').toString().trim();
      if (text.isNotEmpty) return text;
    }
    return '';
  }

  static Color? _parseColor(String raw) {
    final match = RegExp(r'^#([0-9a-fA-F]{6})$').firstMatch(raw.trim());
    if (match == null) return null;
    final hex = match.group(1)!;
    return Color(int.parse('FF$hex', radix: 16));
  }
}

/// Provides tenant branding to descendant widgets.
class TenantBrandingScope extends InheritedWidget {
  const TenantBrandingScope({
    super.key,
    required this.branding,
    required super.child,
  });

  final TenantBranding branding;

  static TenantBranding of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<TenantBrandingScope>();
    return scope?.branding ?? TenantBranding.fallback;
  }

  @override
  bool updateShouldNotify(TenantBrandingScope oldWidget) {
    return oldWidget.branding.displayName != branding.displayName
        || oldWidget.branding.logoData != branding.logoData
        || oldWidget.branding.accentColor != branding.accentColor;
  }
}
