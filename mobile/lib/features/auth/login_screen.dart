import 'package:flutter/material.dart';

import '../../core/app_strings.dart';
import '../../core/auth_repository.dart';
import '../../core/api_client.dart';
import '../../core/config.dart';
import '../../core/worker_auth_errors.dart';
import '../../core/branding_store.dart';
import '../../core/qr_activation_parser.dart';
import '../../core/session_store.dart';
import '../../core/tenant_branding.dart';
import '../../services/branding_applier.dart';
import '../../services/location_service.dart';
import '../../services/push_notification_service.dart';
import '../../services/public_legal_loader.dart';
import '../../services/tenant_branding_loader.dart';
import '../../widgets/language_picker.dart';
import '../../widgets/simple_text_field.dart';
import '../../widgets/tenant_brand_mark.dart';
import '../legal/public_legal_screen.dart';
import 'qr_scan_panel.dart';

/// QR-first onboarding: SUPPIX shell icon, company branding after scan/login.
class LoginScreen extends StatefulWidget {
  const LoginScreen({
    super.key,
    required this.auth,
    required this.location,
    required this.push,
    required this.onLoggedIn,
    this.initialError,
  });

  final AuthRepository auth;
  final LocationService location;
  final PushNotificationService push;
  final void Function(WorkerSession session) onLoggedIn;
  final String? initialError;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _badgeIdController = TextEditingController();
  final _pinController = TextEditingController();
  final _tokenController = TextEditingController();
  bool _loading = false;
  // Default manual — camera scanner must not block first paint / login.
  bool _manualMode = true;
  bool _qrBadgeLaunch = false;
  String? _error;
  TenantBranding _shellBranding = TenantBranding.suppixShell;
  TenantBranding _companyBranding = TenantBranding.fallback;
  PublicLegalBundle _legal = PublicLegalBundle.empty;

  @override
  void initState() {
    super.initState();
    if (widget.initialError != null && widget.initialError!.isNotEmpty) {
      _error = widget.initialError;
    }
    _loadShellBranding();
    _loadLegal();
  }

  Future<void> _loadLegal() async {
    final legal = await PublicLegalLoader.load();
    if (!mounted) return;
    setState(() => _legal = legal);
  }

  void _openLegal({required bool privacy}) {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => PublicLegalScreen(
          title: privacy ? 'Datenschutz' : 'Impressum',
          body: privacy ? _legal.datenschutzText : _legal.impressumText,
          controller: privacy ? _legal.controller : _legal.controller,
        ),
      ),
    );
  }

  Future<void> _loadShellBranding() async {
    final branding = await TenantBrandingLoader.loadPublic();
    if (!mounted) return;
    setState(() => _shellBranding = TenantBranding.suppixShell.mergeHostHints(branding));
  }

  Future<void> _applyCompanyBranding(Map<String, dynamic>? preview) async {
    if (preview == null) return;
    final company = preview['company'];
    TenantBranding next;
    if (company is Map) {
      next = TenantBranding.fromCompanyMap(Map<String, dynamic>.from(company));
    } else {
      next = TenantBranding.fromPublicPayload(preview);
    }
    if (next.displayName == TenantBranding.fallback.displayName && !next.hasVisualIdentity) {
      return;
    }
    setState(() => _companyBranding = next);
    BrandingStore.instance.value = next;
    await BrandingApplier().apply(next);
  }

  @override
  void dispose() {
    _badgeIdController.dispose();
    _pinController.dispose();
    _tokenController.dispose();
    super.dispose();
  }

  TenantBranding get _visibleBranding =>
      _companyBranding.hasVisualIdentity ? _companyBranding : _shellBranding;

  bool get _badApiBuild {
    final url = AppConfig.apiBaseUrl.toLowerCase();
    return url.contains('10.0.2.2') || url.contains('localhost') || url.contains('127.0.0.1');
  }

  Future<void> _loginBadge({bool qrLaunch = false}) async {
    final badgeId = _badgeIdController.text.trim();
    final pin = _pinController.text.trim();
    if (badgeId.isEmpty || pin.length < 4) {
      setState(() => _error = 'Badge-ID und PIN eingeben (mind. 4 Stellen).');
      return;
    }
    await _runLogin(() async {
      Map<String, dynamic>? gps;
      try {
        gps = await widget.location.captureForAttendance();
      } on LocationCaptureException {
        gps = null;
      }
      final pushToken = await widget.push.tokenForDeviceBinding();
      return widget.auth.loginWithBadge(
        badgeId: badgeId,
        badgePin: pin,
        location: gps,
        pushToken: pushToken,
        qrLaunch: qrLaunch,
      );
    });
  }

  Future<void> _loginToken(String token) async {
    final trimmed = token.trim();
    if (trimmed.isEmpty) {
      setState(() => _error = 'Einmal-Link-Code fehlt.');
      return;
    }
    await _runLogin(() async {
      final pushToken = await widget.push.tokenForDeviceBinding();
      return widget.auth.loginWithAccessToken(trimmed, pushToken: pushToken);
    });
  }

  Future<void> _handleQrPayload(QrActivationPayload payload) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (payload.hasAccessToken) {
        final preview = await widget.auth.previewJoin(payload.accessToken!);
        if (preview['tokenValid'] == false) {
          throw Exception('Aktivierungslink ungültig oder bereits verwendet.');
        }
        await _applyCompanyBranding(preview);
        final session = await widget.auth.loginWithAccessToken(
          payload.accessToken!,
          pushToken: await widget.push.tokenForDeviceBinding(),
        );
        if (!mounted) return;
        widget.onLoggedIn(session);
        return;
      }
      if (payload.hasBadgeId) {
        setState(() {
          _manualMode = true;
          _qrBadgeLaunch = true;
          _badgeIdController.text = payload.badgeId!;
        });
        _error = 'Badge erkannt — bitte PIN eingeben.';
        return;
      }
      setState(() => _error = 'QR-Code nicht erkannt.');
    } catch (e) {
      if (!mounted) return;
      _showAuthError(e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _runLogin(Future<WorkerSession> Function() action) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final session = await action();
      if (!mounted) return;
      widget.onLoggedIn(session);
    } catch (e) {
      if (!mounted) return;
      _showAuthError(e);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _showAuthError(Object e) {
    if (e is ApiException) {
      if (e.errorCode == 'access_token_already_used') {
        final badge = badgeIdFromAuthError(e);
        setState(() {
          _manualMode = true;
          if (badge != null) _badgeIdController.text = badge;
          _error = '${formatWorkerAuthError(e)} Badge-ID ist vorausgefüllt — PIN eingeben.';
        });
        return;
      }
      if (e.errorCode == 'access_token_expired' || e.errorCode == 'invalid_access_token') {
        final badge = badgeIdFromAuthError(e);
        setState(() {
          _manualMode = true;
          if (badge != null) _badgeIdController.text = badge;
          _error = formatWorkerAuthError(e);
        });
        return;
      }
      setState(() => _error = formatWorkerAuthError(e));
      return;
    }
    setState(() => _error = e.toString());
  }

  @override
  Widget build(BuildContext context) {
    try {
      return _buildLogin(context);
    } catch (e) {
      return Scaffold(
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text('Login-Fehler: $e'),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: () => setState(() {
                    _manualMode = true;
                    _error = null;
                  }),
                  child: const Text('Manuell versuchen'),
                ),
              ],
            ),
          ),
        ),
      );
    }
  }

  Widget _buildLogin(BuildContext context) {
    final branding = _visibleBranding;
    final scheme = Theme.of(context).colorScheme;
    final brand = branding.effectiveSeed;
    final onBrand = branding.onAccentColor;
    return TenantBrandingScope(
      branding: branding,
      child: Theme(
        data: branding.themeData(base: Theme.of(context)),
        child: Scaffold(
          appBar: AppBar(
            title: Row(
              children: [
                TenantBrandMark(branding: branding, size: 28, borderRadius: 8),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    _companyBranding.hasVisualIdentity ? branding.displayName : 'SUPPIX',
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
          body: ListView(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
            children: [
              Text(
                t('loginTitle', 'Digitalen Ausweis aktivieren'),
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 6),
              Text(
                t('loginSubtitle', 'Mitarbeiterausweis'),
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: scheme.onSurfaceVariant),
              ),
              const SizedBox(height: 18),
              const LanguagePickerTile(dense: true),
              const SizedBox(height: 18),
              Container(
                padding: const EdgeInsets.all(4),
                decoration: BoxDecoration(
                  // ignore: deprecated_member_use
                  color: scheme.surfaceContainerHighest.withOpacity(0.55),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: _ModeTab(
                        selected: _manualMode,
                        icon: Icons.keyboard_rounded,
                        label: t('loginManual', 'Manuell'),
                        brand: brand,
                        onBrand: onBrand,
                        onTap: _loading
                            ? null
                            : () => setState(() {
                                  _manualMode = true;
                                  _error = null;
                                }),
                      ),
                    ),
                    Expanded(
                      child: _ModeTab(
                        selected: !_manualMode,
                        icon: Icons.qr_code_scanner_rounded,
                        label: t('loginQr', 'QR-Scan'),
                        brand: brand,
                        onBrand: onBrand,
                        onTap: _loading
                            ? null
                            : () => setState(() {
                                  _manualMode = false;
                                  _error = null;
                                }),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 18),
              if (_badApiBuild)
                Card(
                  color: scheme.errorContainer,
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Text(
                      'Falsche Server-URL in dieser APK (${AppConfig.apiBaseUrl}).',
                      style: TextStyle(color: scheme.onErrorContainer),
                    ),
                  ),
                ),
              if (_companyBranding.hasVisualIdentity) ...[
                Card(
                  child: ListTile(
                    leading: TenantBrandMark(branding: _companyBranding, size: 44, borderRadius: 12),
                    title: Text(_companyBranding.displayName),
                    subtitle: Text(t('loginSubtitle', 'Mitarbeiterausweis')),
                  ),
                ),
                const SizedBox(height: 12),
              ],
              if (!_manualMode) ...[
                Text(t('loginQrTitle', 'Aktivierungs-QR scannen'), style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 8),
                Text(t('loginQrHint', 'Kamera erlauben, dann Admin-QR scannen.')),
                const SizedBox(height: 16),
                QrScanPanel(
                  busy: _loading,
                  onScanned: _handleQrPayload,
                  onRequestManualLogin: () => setState(() {
                    _manualMode = true;
                    _error = null;
                  }),
                ),
              ] else ...[
                _manualForm(),
              ],
              if (_error != null) ...[
                const SizedBox(height: 16),
                Text(_error!, style: TextStyle(color: scheme.error)),
              ],
              const SizedBox(height: 28),
              Center(
                child: Text(
                  t('legal', 'Rechtliches'),
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(color: brand),
                ),
              ),
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  TextButton(
                    onPressed: () => _openLegal(privacy: false),
                    child: Text(t('imprint', 'Impressum')),
                  ),
                  Text('·', style: TextStyle(color: scheme.onSurfaceVariant)),
                  TextButton(
                    onPressed: () => _openLegal(privacy: true),
                    child: Text(t('privacy', 'Datenschutz')),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _manualForm() {
    final brand = _visibleBranding.effectiveSeed;
    final onBrand = _visibleBranding.onAccentColor;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(t('loginManualTitle', 'Manuelle Anmeldung'), style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        Text(
          t('loginManualHint', 'Badge-ID + PIN vom Admin, oder Join-Link einfügen.'),
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 14),
        SimpleTextField(
          controller: _badgeIdController,
          hint: t('loginBadge', 'Badge-ID'),
          textCapitalization: TextCapitalization.characters,
          enabled: !_loading,
        ),
        const SizedBox(height: 12),
        SimpleTextField(
          controller: _pinController,
          hint: t('loginPin', 'PIN'),
          obscureText: true,
          keyboardType: TextInputType.number,
          enabled: !_loading,
        ),
        const SizedBox(height: 12),
        SimpleTextField(
          controller: _tokenController,
          hint: t('loginLink', 'Einmal-Aktivierungslink (optional)'),
          enabled: !_loading,
          minLines: 1,
          maxLines: 3,
        ),
        const SizedBox(height: 16),
        SizedBox(
          height: 50,
          child: ElevatedButton(
            onPressed: _loading
                ? null
                : () async {
                    final raw = _tokenController.text.trim();
                    if (raw.isNotEmpty) {
                      final parsed = QrActivationParser.parse(raw);
                      final access = (parsed?.accessToken ?? '').trim();
                      final token = access.isNotEmpty ? access : raw;
                      final preview = await widget.auth.previewJoin(token);
                      await _applyCompanyBranding(preview);
                      await _loginToken(token);
                    } else {
                      await _loginBadge(qrLaunch: _qrBadgeLaunch);
                      _qrBadgeLaunch = false;
                    }
                  },
            style: ElevatedButton.styleFrom(
              backgroundColor: brand,
              foregroundColor: onBrand,
            ),
            child: _loading
                ? SizedBox(
                    height: 22,
                    width: 22,
                    child: CircularProgressIndicator(strokeWidth: 2, color: onBrand),
                  )
                : Text(t('loginSubmit', 'Anmelden')),
          ),
        ),
      ],
    );
  }
}

class _ModeTab extends StatelessWidget {
  const _ModeTab({
    required this.selected,
    required this.icon,
    required this.label,
    required this.brand,
    required this.onBrand,
    required this.onTap,
  });

  final bool selected;
  final IconData icon;
  final String label;
  final Color brand;
  final Color onBrand;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected ? brand : Colors.transparent,
      borderRadius: BorderRadius.circular(11),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(11),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 18, color: selected ? onBrand : const Color(0xFF334155)),
              const SizedBox(width: 6),
              Text(
                label,
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  color: selected ? onBrand : const Color(0xFF334155),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
