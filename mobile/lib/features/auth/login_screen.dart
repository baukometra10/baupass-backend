import 'package:flutter/material.dart';

import '../../core/auth_repository.dart';
import '../../core/session_store.dart';
import '../../services/location_service.dart';
import '../../services/push_notification_service.dart';

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

class _LoginScreenState extends State<LoginScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  final _badgeIdController = TextEditingController();
  final _pinController = TextEditingController();
  final _tokenController = TextEditingController();
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    if (widget.initialError != null && widget.initialError!.isNotEmpty) {
      _error = widget.initialError;
    }
  }

  @override
  void dispose() {
    _tabs.dispose();
    _badgeIdController.dispose();
    _pinController.dispose();
    _tokenController.dispose();
    super.dispose();
  }

  Future<void> _loginBadge() async {
    final badgeId = _badgeIdController.text.trim();
    final pin = _pinController.text.trim();
    if (badgeId.isEmpty || pin.length < 4) {
      setState(() => _error = 'Badge-ID und PIN eingeben (mind. 4 Stellen).');
      return;
    }
    await _runLogin(() async {
      final gps = await widget.location.captureForAttendance();
      final pushToken = await widget.push.tokenForDeviceBinding();
      return widget.auth.loginWithBadge(
        badgeId: badgeId,
        badgePin: pin,
        location: gps,
        pushToken: pushToken,
      );
    });
  }

  Future<void> _loginToken() async {
    final token = _tokenController.text.trim();
    if (token.isEmpty) {
      setState(() => _error = 'Einmal-Link-Code einfügen.');
      return;
    }
    await _runLogin(() async {
      final pushToken = await widget.push.tokenForDeviceBinding();
      return widget.auth.loginWithAccessToken(token, pushToken: pushToken);
    });
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
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('BauPass Mitarbeiter'),
        bottom: TabBar(
          controller: _tabs,
          tabs: const [
            Tab(text: 'Badge + PIN'),
            Tab(text: 'Aktivierungslink'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: [
          _badgeForm(),
          _tokenForm(),
        ],
      ),
    );
  }

  Widget _badgeForm() {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            'Melde dich mit Badge-ID und PIN an. Das Gerät wird beim ersten Login gebunden.',
          ),
          const SizedBox(height: 16),
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
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ],
          const SizedBox(height: 24),
          FilledButton(
            onPressed: _loading ? null : _loginBadge,
            child: _loading
                ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Anmelden'),
          ),
        ],
      ),
    );
  }

  Widget _tokenForm() {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text(
            'Für Besucher oder Ersteinrichtung: Einmal-Code vom Administrator einfügen.',
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _tokenController,
            decoration: const InputDecoration(
              labelText: 'Aktivierungslink / Code',
              border: OutlineInputBorder(),
            ),
            enabled: !_loading,
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ],
          const SizedBox(height: 24),
          FilledButton(
            onPressed: _loading ? null : _loginToken,
            child: _loading
                ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Ausweis aktivieren'),
          ),
        ],
      ),
    );
  }
}
