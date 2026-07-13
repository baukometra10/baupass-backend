import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/auth_repository.dart';
import '../../core/api_client.dart';
import '../../core/session_store.dart';
import '../../core/worker_auth_errors.dart';
import '../../services/ai_assistant_service.dart';
import '../../services/chat_repository.dart';
import '../../services/digital_card_repository.dart';
import '../ai/worker_ai_screen.dart';
import '../chat/chat_screen.dart';
import '../../services/tasks_repository.dart';
import '../../services/worker_cache.dart';
import '../../core/tenant_branding.dart';
import '../../widgets/tenant_brand_mark.dart';
import '../../widgets/digital_pass_card.dart';
import '../notifications/notifications_sheet.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    required this.session,
    required this.auth,
    required this.digitalCard,
    required this.chat,
    required this.workerCache,
    required this.ai,
    required this.tasks,
    required this.onOpenAttendance,
    this.onOpenTasks,
    this.onOpenDeploymentPlan,
    this.onOpenChat,
  });

  final WorkerSession session;
  final AuthRepository auth;
  final DigitalCardRepository digitalCard;
  final ChatRepository chat;
  final WorkerCache workerCache;
  final AiAssistantService ai;
  final TasksRepository tasks;
  final VoidCallback onOpenAttendance;
  final VoidCallback? onOpenTasks;
  final VoidCallback? onOpenDeploymentPlan;
  final VoidCallback? onOpenChat;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  Map<String, dynamic>? _profile;
  DynamicQrPayload? _dynamicQr;
  Timer? _qrTimer;
  int _unreadNotifications = 0;
  String? _loadError;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _qrTimer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loadError = null);
    try {
      final me = await widget.auth.fetchProfile(widget.session);
      await widget.workerCache.saveProfile(me);
      if (!mounted) return;
      setState(() => _profile = me);
      await _refreshQr();
      await _refreshNotifications();
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _loadError = formatWorkerAuthError(e));
      final cached = await widget.workerCache.loadProfile();
      if (mounted) setState(() => _profile = cached);
    } catch (_) {
      final cached = await widget.workerCache.loadProfile();
      if (mounted) {
        setState(() {
          _profile = cached;
          _loadError = 'Profil konnte nicht geladen werden — nach unten ziehen zum Aktualisieren.';
        });
      }
    }
  }

  Future<void> _refreshNotifications() async {
    try {
      final rows = await widget.tasks.listNotifications(widget.session);
      if (!mounted) return;
      setState(() {
        _unreadNotifications = rows.where((r) => r['isRead'] != true).length;
      });
    } catch (_) {
      // ignore
    }
  }

  void _openNotifications() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => NotificationsSheet(
        session: widget.session,
        tasks: widget.tasks,
        onOpenDeployment: () {
          widget.onOpenDeploymentPlan?.call();
          widget.onOpenTasks?.call();
        },
        onOpenDocuments: () {
          widget.onOpenTasks?.call();
        },
      ),
    ).then((_) => _refreshNotifications());
  }

  void _openChatFullScreen() {
    if (widget.onOpenChat != null) {
      widget.onOpenChat!();
      return;
    }
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => ChatScreen(session: widget.session, chat: widget.chat),
      ),
    );
  }

  Future<void> _refreshQr() async {
    try {
      final qr = await widget.digitalCard.fetchDynamicQr(
        bearer: widget.session.bearer,
        deviceId: widget.session.deviceId,
      );
      if (!mounted) return;
      setState(() => _dynamicQr = qr);
      _qrTimer?.cancel();
      final waitSec = (qr.remainingSec > 5) ? qr.remainingSec - 2 : qr.windowSec - 2;
      _qrTimer = Timer(Duration(seconds: waitSec.clamp(5, 58)), _refreshQr);
    } catch (_) {}
  }

  Widget _infoTile(String label, String value, {Widget? valueWidget}) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: Theme.of(context).colorScheme.outlineVariant),
          color: Theme.of(context).colorScheme.surfaceContainerLow,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.4,
                  ),
            ),
            const SizedBox(height: 4),
            valueWidget ??
                Text(
                  value,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final worker = _profile?['worker'] as Map<String, dynamic>?;
    final company = _profile?['company'] as Map<String, dynamic>?;
    final subcompany = _profile?['subcompany'] as Map<String, dynamic>?;
    final siteAccess = _profile?['siteAccess'] as Map<String, dynamic>?;
    final branding = TenantBranding.fromMePayload(_profile);
    final brandLabel = branding.displayName;
    final openCheckIn = siteAccess?['openCheckInToday'] == true;
    final status = worker?['status'] as String? ?? 'aktiv';

    return Scaffold(
      appBar: AppBar(
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            TenantBrandMark(branding: branding, size: 28, borderRadius: 8),
            const SizedBox(width: 10),
            Flexible(
              child: Text(
                brandLabel,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Mitteilungen',
            icon: Badge(
              isLabelVisible: _unreadNotifications > 0,
              label: Text('$_unreadNotifications'),
              child: const Icon(Icons.notifications_outlined),
            ),
            onPressed: _openNotifications,
          ),
          IconButton(
            tooltip: 'KI Assistent',
            icon: const Icon(Icons.smart_toy_outlined),
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => TenantBrandingScope(
                    branding: branding,
                    child: WorkerAiScreen(session: widget.session, ai: widget.ai),
                  ),
                ),
              );
            },
          ),
          IconButton(
            tooltip: 'Chat mit Firma',
            icon: const Icon(Icons.chat_bubble_outline),
            onPressed: _openChatFullScreen,
          ),
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
          children: [
            if (_loadError != null)
              Card(
                color: Theme.of(context).colorScheme.errorContainer,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Text(
                    _loadError!,
                    style: TextStyle(color: Theme.of(context).colorScheme.onErrorContainer),
                  ),
                ),
              ),
            if (worker != null)
              DigitalPassCard(
                firstName: worker['firstName'] as String? ?? '',
                lastName: worker['lastName'] as String? ?? '',
                role: worker['role'] as String? ?? '',
                badgeId: worker['badgeId'] as String? ?? '-',
                companyName: brandLabel,
                subcompany: subcompany?['name'] as String?,
                validUntil: worker['validUntil'] as String? ?? '-',
                status: status,
                photoData: worker['photoData'] as String?,
                dynamicQr: _dynamicQr,
                branding: branding,
              ),
            const SizedBox(height: 16),
            Card(
              child: ListTile(
                leading: Icon(
                  openCheckIn ? Icons.login : Icons.logout,
                  color: Theme.of(context).colorScheme.primary,
                ),
                title: Text(openCheckIn ? 'Heute eingecheckt' : 'Noch nicht eingecheckt'),
                subtitle: worker?['site'] != null ? Text('Baustelle: ${worker!['site']}') : null,
              ),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: widget.onOpenAttendance,
              icon: const Icon(Icons.nfc),
              label: const Text('NFC Check-in / Check-out'),
              style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
            ),
            const SizedBox(height: 8),
            if (widget.onOpenDeploymentPlan != null)
              FilledButton.tonalIcon(
                onPressed: widget.onOpenDeploymentPlan,
                icon: const Icon(Icons.event_note),
                label: const Text('Mein Einsatzplan'),
                style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)),
              ),
            if (widget.onOpenDeploymentPlan != null) const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => TenantBrandingScope(
                      branding: branding,
                      child: WorkerAiScreen(session: widget.session, ai: widget.ai),
                    ),
                  ),
                );
              },
              icon: const Icon(Icons.smart_toy_outlined),
              label: Text(branding.aiAssistantTitle),
              style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48)),
            ),
          ],
        ),
      ),
    );
  }
}
