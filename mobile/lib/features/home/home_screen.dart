import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/auth_repository.dart';
import '../../core/session_store.dart';
import '../../services/ai_assistant_service.dart';
import '../../services/chat_repository.dart';
import '../../services/digital_card_repository.dart';
import '../ai/worker_ai_screen.dart';
import '../chat/chat_screen.dart';
import '../../services/tasks_repository.dart';
import '../../services/worker_cache.dart';
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

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  Map<String, dynamic>? _profile;
  DynamicQrPayload? _dynamicQr;
  Timer? _qrTimer;
  int _unreadNotifications = 0;

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
    try {
      final me = await widget.auth.fetchProfile(widget.session);
      await widget.workerCache.saveProfile(me);
      if (!mounted) return;
      setState(() => _profile = me);
      await _refreshQr();
      await _refreshNotifications();
    } catch (_) {
      final cached = await widget.workerCache.loadProfile();
      if (mounted) setState(() => _profile = cached);
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

  @override
  Widget build(BuildContext context) {
    final worker = _profile?['worker'] as Map<String, dynamic>?;
    final company = _profile?['company'] as Map<String, dynamic>?;
    final subcompany = _profile?['subcompany'] as Map<String, dynamic>?;
    final siteAccess = _profile?['siteAccess'] as Map<String, dynamic>?;
    final openCheckIn = siteAccess?['openCheckInToday'] == true;

    return Scaffold(
      appBar: AppBar(
        title: const Text('WorkPass'),
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
                  builder: (_) => WorkerAiScreen(session: widget.session, ai: widget.ai),
                ),
              );
            },
          ),
          IconButton(
            tooltip: 'Chat mit Firma',
            icon: const Icon(Icons.chat_bubble_outline),
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => ChatScreen(session: widget.session, tasks: widget.tasks),
                  builder: (_) => ChatScreen(session: widget.session, chat: widget.chat),
                ),
              );
            },
          ),
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (worker != null)
              DigitalPassCard(
                firstName: worker['firstName'] as String? ?? '',
                lastName: worker['lastName'] as String? ?? '',
                role: worker['role'] as String? ?? '',
                badgeId: worker['badgeId'] as String? ?? '-',
                companyName: company?['name'] as String? ?? '',
                subcompany: subcompany?['name'] as String?,
                validUntil: worker['validUntil'] as String? ?? '-',
                status: worker['status'] as String? ?? 'aktiv',
                photoData: worker['photoData'] as String?,
                dynamicQr: _dynamicQr,
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
            if (widget.session.hasDeviceBinding) ...[
              const SizedBox(height: 8),
              const ListTile(
                leading: Icon(Icons.phonelink_lock),
                title: Text('Gerät gebunden'),
                subtitle: Text('Nur dieses Gerät darf Check-ins senden.'),
              ),
            ],
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
                    builder: (_) => WorkerAiScreen(session: widget.session, ai: widget.ai),
                  ),
                );
              },
              icon: const Icon(Icons.chat_outlined),
              label: const Text('SUPPIX AI Assistent'),
              style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48)),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => ChatScreen(session: widget.session, tasks: widget.tasks),
                    builder: (_) => ChatScreen(session: widget.session, chat: widget.chat),
                  ),
                );
              },
              icon: const Icon(Icons.chat_bubble_outline),
              label: const Text('Chat mit Firma'),
              style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48)),
            ),
          ],
        ),
      ),
    );
  }
}
