import 'package:flutter/material.dart';

import '../../core/auth_repository.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.auth, required this.onLoggedIn});

  final AuthRepository auth;
  final VoidCallback onLoggedIn;

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
      setState(() => _error = 'Enter Badge-ID and PIN (min. 4 digits).');
      return;
    }
    await _runLogin(() => widget.auth.loginWithBadge(badgeId: badgeId, badgePin: pin));
  }

  Future<void> _loginToken() async {
    final token = _tokenController.text.trim();
    if (token.isEmpty) {
      setState(() => _error = 'Paste the one-time access token.');
      return;
    }
    await _runLogin(() => widget.auth.loginWithAccessToken(token));
  }

  Future<void> _runLogin(Future<String> Function() action) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await action();
      if (!mounted) return;
      widget.onLoggedIn();
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
        title: const Text('BauPass Worker'),
        bottom: TabBar(
          controller: _tabs,
          tabs: const [
            Tab(text: 'Badge + PIN'),
            Tab(text: 'Access link'),
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
          const Text('Sign in with your employee Badge-ID and PIN.'),
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
                : const Text('Sign in'),
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
          const Text('For visitors or first setup: paste the one-time token from your administrator.'),
          const SizedBox(height: 16),
          TextField(
            controller: _tokenController,
            decoration: const InputDecoration(
              labelText: 'Access token',
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
                : const Text('Sign in'),
          ),
        ],
      ),
    );
  }
}
