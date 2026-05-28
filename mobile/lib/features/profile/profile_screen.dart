import 'package:flutter/material.dart';

import '../../core/auth_repository.dart';
import '../../core/session_store.dart';
import '../../services/push_notification_service.dart';
import '../../services/worker_cache.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({
    super.key,
    required this.session,
    required this.auth,
    required this.workerCache,
    required this.push,
    required this.onLogout,
  });

  final WorkerSession session;
  final AuthRepository auth;
  final WorkerCache workerCache;
  final PushNotificationService push;
  final VoidCallback onLogout;

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  Map<String, dynamic>? _profile;
  bool _loading = true;
  bool _pushEnabled = false;
  Map<String, dynamic>? _pushServerStatus;

  @override
  void initState() {
    super.initState();
    _load();
    _loadPushPref();
    _loadPushServerStatus();
  }

  Future<void> _loadPushServerStatus() async {
    final st = await widget.push.fetchServerPushStatus(session: widget.session);
    if (mounted) setState(() => _pushServerStatus = st);
  }

  Future<void> _loadPushPref() async {
    final enabled = await widget.push.isEnabled();
    if (mounted) setState(() => _pushEnabled = enabled);
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final me = await widget.auth.fetchProfile(widget.session);
      await widget.workerCache.saveProfile(me);
      if (!mounted) return;
      setState(() {
        _profile = me;
        _loading = false;
      });
    } catch (_) {
      final cached = await widget.workerCache.loadProfile();
      if (!mounted) return;
      setState(() {
        _profile = cached;
        _loading = false;
      });
    }
  }

  Future<void> _logout() async {
    await widget.auth.logout(widget.session);
    widget.onLogout();
  }

  @override
  Widget build(BuildContext context) {
    final worker = _profile?['worker'] as Map<String, dynamic>?;
    final leave = _profile?['leaveStats'] as Map<String, dynamic>?;
    final team = _profile?['teamSnapshot'] as Map<String, dynamic>?;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Profile'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _loading ? null : _load),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(20),
              children: [
                if (worker != null) ...[
                  Text(
                    '${worker['firstName'] ?? ''} ${worker['lastName'] ?? ''}'.trim(),
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 4),
                  Text('Badge: ${worker['badgeId'] ?? '-'}'),
                  Text('Role: ${worker['role'] ?? '-'}'),
                  Text('Site: ${worker['site'] ?? '-'}'),
                ],
                const SizedBox(height: 16),
                if (leave != null)
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Leave', style: Theme.of(context).textTheme.titleMedium),
                          Text('Remaining: ${leave['remaining'] ?? '-'} days'),
                          Text('Taken this year: ${leave['taken'] ?? 0}'),
                        ],
                      ),
                    ),
                  ),
                if (team != null) ...[
                  const SizedBox(height: 8),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Team on site', style: Theme.of(context).textTheme.titleMedium),
                          Text('Present: ${team['present'] ?? 0} / ${team['expected'] ?? 0}'),
                        ],
                      ),
                    ),
                  ),
                ],
                const SizedBox(height: 8),
                SwitchListTile(
                  title: const Text('Push notifications'),
                  subtitle: Text(
                    _pushServerStatus == null
                        ? 'Loading push status…'
                        : (_pushServerStatus!['anyChannelReady'] == true
                            ? (_pushEnabled
                                ? 'Server ready (FCM/Web). Token sync on login.'
                                : 'Server push ready — enable to register device.')
                            : 'Server push not configured (FCM/VAPID).'),
                  ),
                  value: _pushEnabled,
                  onChanged: (value) async {
                    await widget.push.setEnabled(value);
                    var registered = false;
                    if (value) {
                      registered = await widget.push.initializeAfterLogin(widget.session);
                    }
                    if (mounted) {
                      setState(() => _pushEnabled = value);
                      if (value && !registered) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text(
                              'Push enabled locally — add Firebase or BAUPASS_FCM_TOKEN for delivery.',
                            ),
                          ),
                        );
                      }
                    }
                  },
                ),
                const SizedBox(height: 16),
                OutlinedButton.icon(
                  onPressed: _logout,
                  icon: const Icon(Icons.logout),
                  label: const Text('Sign out'),
                ),
              ],
            ),
    );
  }
}
