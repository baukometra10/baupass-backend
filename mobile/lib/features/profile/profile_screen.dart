import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_client.dart';
import '../../core/tenant_branding.dart';
import '../../core/auth_repository.dart';
import '../../core/locale_controller.dart';
import '../../core/session_store.dart';
import '../../services/push_notification_service.dart';
import '../../services/worker_cache.dart';
import '../../core/app_strings.dart';
import '../../widgets/language_picker.dart';
import '../../widgets/tenant_brand_mark.dart';
import '../legal/legal_document_screen.dart';
import '../legal/legal_hub_screen.dart';

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
  Map<String, dynamic>? _distribution;

  @override
  void initState() {
    super.initState();
    _load();
    _loadPushPref();
    _loadPushServerStatus();
    _loadDistribution();
  }

  Future<void> _loadDistribution() async {
    try {
      final api = ApiClient();
      final data = await api.getJson('/api/v2/mobile/distribution');
      if (!mounted) return;
      setState(() => _distribution = data);
    } catch (_) {
      // optional — store links hidden when unavailable
    }
  }

  Future<void> _openStoreUrl(String? url) async {
    final trimmed = (url ?? '').trim();
    if (trimmed.isEmpty) return;
    final uri = Uri.parse(trimmed);
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Store-Link konnte nicht geöffnet werden.')),
      );
    }
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
    final branding = TenantBrandingScope.of(context);
    final worker = _profile?['worker'] as Map<String, dynamic>?;
    final leave = _profile?['leaveStats'] as Map<String, dynamic>?;
    final team = _profile?['teamSnapshot'] as Map<String, dynamic>?;
    final install = _distribution?['install'] as Map<String, dynamic>? ?? {};
    final playStoreUrl = (install['playStoreUrl'] as String?)?.trim() ?? '';
    final appStoreUrl = (install['appStoreUrl'] as String?)?.trim() ?? '';
    final apkUrl = (install['apkUrl'] as String?)?.trim() ?? '';
    final testFlightUrl = (install['testFlightUrl'] as String?)?.trim() ?? '';

    return ListenableBuilder(
      listenable: LocaleController.instance,
      builder: (context, _) => Scaffold(
      appBar: AppBar(
        title: Text(t('navProfile', 'Profil')),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _loading ? null : _load),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(20),
              children: [
                const LanguagePickerTile(),
                const SizedBox(height: 16),
                Row(
                  children: [
                    TenantBrandMark(branding: branding, size: 48, borderRadius: 12),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            branding.displayName,
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                          if (worker != null)
                            Text(
                              '${worker['firstName'] ?? ''} ${worker['lastName'] ?? ''}'.trim(),
                              style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                                  ),
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                if (worker != null) ...[
                  Text('${t('badge')}: ${worker['badgeId'] ?? '-'}'),
                  Text('${t('role')}: ${worker['role'] ?? '-'}'),
                  Text('${t('site')}: ${worker['site'] ?? '-'}'),
                ],
                const SizedBox(height: 16),
                if (leave != null)
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(t('leave'), style: Theme.of(context).textTheme.titleMedium),
                          Text('${t('leaveRemaining')}: ${leave['remaining'] ?? '-'} ${t('days')}'),
                          Text('${t('leaveTaken')}: ${leave['taken'] ?? 0}'),
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
                          Text(t('teamOnSite'), style: Theme.of(context).textTheme.titleMedium),
                          Text('${t('present')}: ${team['present'] ?? 0} / ${team['expected'] ?? 0}'),
                        ],
                      ),
                    ),
                  ),
                ],
                const SizedBox(height: 8),
                if (playStoreUrl.isNotEmpty ||
                    appStoreUrl.isNotEmpty ||
                    apkUrl.isNotEmpty ||
                    testFlightUrl.isNotEmpty)
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text(t('appUpdates'), style: Theme.of(context).textTheme.titleMedium),
                          const SizedBox(height: 8),
                          if (playStoreUrl.isNotEmpty)
                            OutlinedButton.icon(
                              onPressed: () => _openStoreUrl(playStoreUrl),
                              icon: const Icon(Icons.shop),
                              label: const Text('Google Play'),
                            ),
                          if (appStoreUrl.isNotEmpty) ...[
                            if (playStoreUrl.isNotEmpty) const SizedBox(height: 8),
                            OutlinedButton.icon(
                              onPressed: () => _openStoreUrl(appStoreUrl),
                              icon: const Icon(Icons.apple),
                              label: const Text('App Store'),
                            ),
                          ],
                          if (apkUrl.isNotEmpty) ...[
                            if (playStoreUrl.isNotEmpty || appStoreUrl.isNotEmpty)
                              const SizedBox(height: 8),
                            OutlinedButton.icon(
                              onPressed: () => _openStoreUrl(apkUrl),
                              icon: const Icon(Icons.android),
                              label: const Text('Android APK'),
                            ),
                          ],
                          if (testFlightUrl.isNotEmpty) ...[
                            const SizedBox(height: 8),
                            OutlinedButton.icon(
                              onPressed: () => _openStoreUrl(testFlightUrl),
                              icon: const Icon(Icons.flight_takeoff),
                              label: const Text('TestFlight (iOS)'),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                SwitchListTile(
                  title: Text(t('pushNotifications')),
                  subtitle: Text(
                    _pushServerStatus == null
                        ? '…'
                        : (_pushServerStatus!['fcmConfigured'] == true
                            ? (_pushEnabled
                                ? 'FCM'
                                : 'FCM')
                            : (_pushServerStatus!['anyChannelReady'] == true
                                ? 'Push'
                                : 'FCM')),
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
                              'Push — google-services.json / BAUPASS_FCM_TOKEN',
                            ),
                          ),
                        );
                      }
                    }
                  },
                ),
                const SizedBox(height: 20),
                Text(
                  t('legal'),
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 4),
                Text(
                  t('legalSubtitle'),
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                ),
                const SizedBox(height: 8),
                Card(
                  child: Column(
                    children: [
                      ListTile(
                        leading: const Icon(Icons.balance_outlined),
                        title: Text(t('legal')),
                        subtitle: Text(t('legalSubtitle')),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () {
                          Navigator.of(context).push(
                            MaterialPageRoute<void>(
                              builder: (_) => LegalHubScreen(session: widget.session),
                            ),
                          );
                        },
                      ),
                      const Divider(height: 1),
                      ListTile(
                        leading: const Icon(Icons.gavel_outlined),
                        title: Text(t('imprint')),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () {
                          Navigator.of(context).push(
                            MaterialPageRoute<void>(
                              builder: (_) => LegalHubScreen(
                                session: widget.session,
                                initialDocument: LegalDocumentKind.impressum,
                              ),
                            ),
                          );
                        },
                      ),
                      const Divider(height: 1),
                      ListTile(
                        leading: const Icon(Icons.privacy_tip_outlined),
                        title: Text(t('privacy')),
                        subtitle: Text(t('privacySubtitle')),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: () {
                          Navigator.of(context).push(
                            MaterialPageRoute<void>(
                              builder: (_) => LegalHubScreen(
                                session: widget.session,
                                initialDocument: LegalDocumentKind.datenschutz,
                              ),
                            ),
                          );
                        },
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                OutlinedButton.icon(
                  onPressed: _logout,
                  icon: const Icon(Icons.logout),
                  label: Text(t('logout')),
                ),
              ],
            ),
    ),
    );
  }
}
