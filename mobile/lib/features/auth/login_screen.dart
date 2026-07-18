import 'package:flutter/material.dart';

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
import '../../services/tenant_branding_loader.dart';
import '../../widgets/tenant_brand_mark.dart';
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
  bool _manualMode = false;
  bool _qrBadgeLaunch = false;
  String? _error;
  TenantBranding _shellBranding = TenantBranding.suppixShell;
  TenantBranding _companyBranding = TenantBranding.fallback;

  @override
  void initState() {
    super.initState();
    if (widget.initialError != null && widget.initialError!.isNotEmpty) {
      _error = widget.initialError;
    }
    _loadShellBranding();
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
    final branding = _visibleBranding;
    return TenantBrandingScope(
      branding: branding,
      child: Scaffold(
        appBar: AppBar(
          title: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              TenantBrandMark(branding: branding, size: 28, borderRadius: 8),
              const SizedBox(width: 10),
              Flexible(
                child: Text(
                  _companyBranding.hasVisualIdentity ? branding.displayName : 'SUPPIX',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: _loading
                  ? null
                  : () => setState(() {
                        _manualMode = !_manualMode;
                        _error = null;
                      }),
              child: Text(_manualMode ? 'QR-Scan' : 'Manuell'),
            ),
          ],
        ),
        body: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            if (_badApiBuild)
              Card(
                color: Theme.of(context).colorScheme.errorContainer,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text(
                    'Falsche Server-URL in dieser APK (${AppConfig.apiBaseUrl}). '
                    'Bitte aktuelle APK von join.html installieren.',
                    style: TextStyle(color: Theme.of(context).colorScheme.onErrorContainer),
                  ),
                ),
              ),
            if (_companyBranding.hasVisualIdentity) ...[
              Card(
                child: ListTile(
                  leading: TenantBrandMark(branding: _companyBranding, size: 44, borderRadius: 12),
                  title: Text(_companyBranding.displayName),
                  subtitle: const Text('Firmenprofil erkannt'),
                ),
              ),
              const SizedBox(height: 12),
            ],
            if (!_manualMode) ...[
              Text(
                'Aktivierungs-QR scannen',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              const Text(
                'Nach APK-Installation: Admin-QR hier scannen. '
                'Wenn die Kamera blockiert: Einstellungen → Apps → SUPPIX → Kamera erlauben. '
                'Oder oben „Manuell“ → Badge-ID + PIN (oder Einmal-Link aus dem Browser).',
              ),
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
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
          ],
        ),
      ),
    );
  }

  Widget _manualForm() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Manuelle Anmeldung', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        Text(
          'Ohne Kamera: Badge-ID + PIN vom Admin, oder den kompletten join-Link '
          'aus dem Browser hier einfügen. Ein QR-Link funktioniert nur einmal.',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _badgeIdController,
          decoration: const InputDecoration(
            labelText: 'Badge-ID',
            border: OutlineInputBorder(),
          ),
          textCapitalization: TextCapitalization.characters,
          enabled: !_loading,
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _pinController,
          decoration: const InputDecoration(
            labelText: 'PIN',
            border: OutlineInputBorder(),
          ),
          obscureText: true,
          keyboardType: TextInputType.number,
          enabled: !_loading,
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _tokenController,
          decoration: const InputDecoration(
            labelText: 'Einmal-Aktivierungslink (optional)',
            border: OutlineInputBorder(),
          ),
          enabled: !_loading,
        ),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: _loading
              ? null
              : () async {
                  final raw = _tokenController.text.trim();
                  if (raw.isNotEmpty) {
                    final parsed = QrActivationParser.parse(raw);
                    final token = (parsed?.accessToken ?? '').trim().isNotEmpty
                        ? parsed!.accessToken!.trim()
                        : raw;
                    final preview = await widget.auth.previewJoin(token);
                    await _applyCompanyBranding(preview);
                    await _loginToken(token);
                  } else {
                    await _loginBadge(qrLaunch: _qrBadgeLaunch);
                    _qrBadgeLaunch = false;
                  }
                },
          child: _loading
              ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2))
              : const Text('Anmelden'),
        ),
      ],
    );
  }
}
