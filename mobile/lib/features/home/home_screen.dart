import 'package:flutter/material.dart';

import '../../core/auth_repository.dart';
import '../../services/worker_cache.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    required this.sessionToken,
    required this.auth,
    required this.workerCache,
    required this.onOpenAttendance,
  });

  final String sessionToken;
  final AuthRepository auth;
  final WorkerCache workerCache;
  final VoidCallback onOpenAttendance;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  Map<String, dynamic>? _profile;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final me = await widget.auth.fetchProfile(widget.sessionToken);
      await widget.workerCache.saveProfile(me);
      if (!mounted) return;
      setState(() => _profile = me);
    } catch (_) {
      final cached = await widget.workerCache.loadProfile();
      if (mounted) setState(() => _profile = cached);
    }
  }

  @override
  Widget build(BuildContext context) {
    final worker = _profile?['worker'] as Map<String, dynamic>?;
    final company = _profile?['company'] as Map<String, dynamic>?;
    final siteAccess = _profile?['siteAccess'] as Map<String, dynamic>?;
    final name = worker != null
        ? '${worker['firstName'] ?? ''} ${worker['lastName'] ?? ''}'.trim()
        : 'Employee';
    final openCheckIn = siteAccess?['openCheckInToday'] == true;

    return Scaffold(
      appBar: AppBar(title: const Text('BauPass')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text('Hello, $name', style: Theme.of(context).textTheme.headlineSmall),
            if (company?['name'] != null)
              Text(company!['name'] as String, style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: 20),
            Card(
              child: ListTile(
                leading: Icon(
                  openCheckIn ? Icons.login : Icons.logout,
                  color: Theme.of(context).colorScheme.primary,
                ),
                title: Text(openCheckIn ? 'Checked in today' : 'Not checked in'),
                subtitle: worker?['site'] != null ? Text('Site: ${worker!['site']}') : null,
              ),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: widget.onOpenAttendance,
              icon: const Icon(Icons.nfc),
              label: const Text('Record attendance (NFC)'),
              style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
            ),
            const SizedBox(height: 24),
            Text('Enterprise hybrid app', style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 8),
            const Text(
              'Shared Flutter UI on Android and iPhone. NFC uses a small native layer per platform.',
            ),
          ],
        ),
      ),
    );
  }
}
