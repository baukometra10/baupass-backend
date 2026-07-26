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

  static int argb32(Color color) {
    // ignore: deprecated_member_use
    return color.value;
  }

  Map<String, dynamic> toCacheJson() => {
        'displayName': displayName,
        if (logoData != null && logoData!.isNotEmpty) 'logoData': logoData,
        if (accentColor != null)
          'accentColor': '#${argb32(accentColor!).toRadixString(16).padLeft(8, '0').substring(2)}',
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
    final seed = effectiveSeed;
    final scheme = ColorScheme.fromSeed(
      seedColor: seed,
      brightness: Brightness.light,
    );
    // ignore: deprecated_member_use — withOpacity is more stable than withValues on some devices
    final muted = scheme.onSurface.withOpacity(0.72);
    final nav = BottomNavigationBarThemeData(
      backgroundColor: scheme.surface,
      selectedItemColor: scheme.primary,
      unselectedItemColor: muted,
      type: BottomNavigationBarType.fixed,
      elevation: 8,
      showUnselectedLabels: true,
    );
    const inputTheme = InputDecorationTheme(
      border: InputBorder.none,
      enabledBorder: InputBorder.none,
      focusedBorder: InputBorder.none,
      disabledBorder: InputBorder.none,
      errorBorder: InputBorder.none,
      focusedErrorBorder: InputBorder.none,
      floatingLabelBehavior: FloatingLabelBehavior.never,
      isDense: true,
    );
    final appBar = AppBarTheme(
      backgroundColor: scheme.surface,
      foregroundColor: scheme.onSurface,
      elevation: 0,
      centerTitle: false,
      surfaceTintColor: Colors.transparent,
    );
    final elevated = ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: scheme.primary,
        foregroundColor: onAccentColor,
        // ignore: deprecated_member_use
        disabledBackgroundColor: scheme.primary.withOpacity(0.35),
        // ignore: deprecated_member_use
        disabledForegroundColor: onAccentColor.withOpacity(0.7),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
    if (base == null) {
      return ThemeData(
        colorScheme: scheme,
        useMaterial3: true,
        scaffoldBackgroundColor: scheme.surface,
        canvasColor: scheme.surface,
        bottomNavigationBarTheme: nav,
        inputDecorationTheme: inputTheme,
        appBarTheme: appBar,
        elevatedButtonTheme: elevated,
        floatingActionButtonTheme: FloatingActionButtonThemeData(
          backgroundColor: scheme.primary,
          foregroundColor: onAccentColor,
        ),
        progressIndicatorTheme: ProgressIndicatorThemeData(color: scheme.primary),
        chipTheme: ChipThemeData(
          // ignore: deprecated_member_use
          selectedColor: scheme.primary.withOpacity(0.18),
          checkmarkColor: scheme.primary,
          labelStyle: TextStyle(color: scheme.onSurface),
          secondaryLabelStyle: TextStyle(color: scheme.primary),
          side: BorderSide(color: scheme.outlineVariant),
        ),
      );
    }
    return base.copyWith(
      colorScheme: scheme,
      scaffoldBackgroundColor: scheme.surface,
      canvasColor: scheme.surface,
      bottomNavigationBarTheme: nav,
      inputDecorationTheme: inputTheme,
      appBarTheme: appBar,
      elevatedButtonTheme: elevated,
    );
  }

  static String deriveInitials(String name) {
    final cleaned = name.trim().replaceAll(RegExp(r'\s+'), ' ');
    if (cleaned.isEmpty) return 'MI';
    final parts = cleaned.split(RegExp(r'[\s\-–—]+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return 'MI';
    String initial(String part) {
      final runes = part.runes;
      if (runes.isEmpty) return '';
      return String.fromCharCode(runes.first).toUpperCase();
    }

    if (parts.length >= 2) {
      final a = initial(parts[0]);
      final b = initial(parts[1]);
      final joined = '$a$b';
      return joined.isEmpty ? 'MI' : joined;
    }
    final word = parts.first;
    if (word.runes.length >= 2) {
      final it = word.runes.iterator;
      it.moveNext();
      final c1 = it.current;
      it.moveNext();
      return String.fromCharCodes([c1, it.current]).toUpperCase();
    }
    final one = initial(word);
    return one.isEmpty ? 'MI' : one;
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
