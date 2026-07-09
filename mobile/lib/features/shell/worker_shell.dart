import 'package:flutter/material.dart';

import '../../core/tenant_branding.dart';
import '../../core/auth_repository.dart';
import '../../core/session_store.dart';
import '../../services/ai_assistant_service.dart';
import '../../services/attendance_repository.dart';
import '../../services/branding_applier.dart';
import '../../services/chat_repository.dart';
import '../../services/digital_card_repository.dart';
import '../../services/geofence_service.dart';
import '../../services/location_service.dart';
import '../../services/nfc_service.dart';
import '../../services/offline_attendance_store.dart';
import '../../services/offline_sync_service.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../services/push_notification_service.dart';
import '../../services/tasks_repository.dart';
import '../../services/usage_repository.dart';
import '../../services/worker_cache.dart';
import '../attendance/attendance_screen.dart';
import '../home/home_screen.dart';
import '../ai/worker_ai_screen.dart';
import '../chat/chat_screen.dart';
import '../profile/profile_screen.dart';
import '../tasks/tasks_screen.dart';
import '../../services/deep_link_service.dart';

/// Unified post-login shell — sole employee UI for Android and iOS.
class WorkerShell extends StatefulWidget {
  const WorkerShell({
    super.key,
    required this.session,
    required this.auth,
    required this.attendance,
    required this.digitalCard,
    required this.chat,
    required this.nfc,
    required this.location,
    required this.geofence,
    required this.offlineStore,
    required this.offlineSync,
    required this.workerCache,
    required this.tasks,
    required this.usage,
    required this.push,
    required this.ai,
    required this.onLogout,
  });

  final WorkerSession session;
  final AuthRepository auth;
  final AttendanceRepository attendance;
  final DigitalCardRepository digitalCard;
  final ChatRepository chat;
  final NfcService nfc;
  final LocationService location;
  final GeofenceService geofence;
  final OfflineAttendanceStore offlineStore;
  final OfflineSyncService offlineSync;
  final WorkerCache workerCache;
  final TasksRepository tasks;
  final UsageRepository usage;
  final PushNotificationService push;
  final AiAssistantService ai;
  final VoidCallback onLogout;

  @override
  State<WorkerShell> createState() => WorkerShellState();
}

class WorkerShellState extends State<WorkerShell> {
  int _index = 0;
  int _tasksSubTab = 0;
  int _offlinePending = 0;
  TenantBranding _branding = TenantBranding.fallback;
  final _brandingApplier = BrandingApplier();

  @override
  void initState() {
    super.initState();
    _loadProfileAndGeofence();
    _refreshBadges();
    widget.usage.trackTab(
      tabIndex: _index,
      bearerToken: widget.session.bearer,
      deviceId: widget.session.deviceId,
    );
  }

  void navigateTo(WorkerAppRoute route) {
    final external = (route.externalUrl ?? '').trim();
    if (external.isNotEmpty) {
      launchUrl(Uri.parse(external), mode: LaunchMode.externalApplication);
      return;
    }
    setState(() {
      _index = route.openChat ? 3 : route.tabIndex.clamp(0, 4);
      _tasksSubTab = route.tasksSubTab.clamp(0, 3);
    });
    if (route.openChat && mounted) {
      widget.usage.trackFeature(
        featureId: 'worker-chat',
        bearerToken: widget.session.bearer,
        deviceId: widget.session.deviceId,
      );
    }
    if (route.openAi && mounted) {
      widget.usage.trackFeature(
        featureId: 'worker-ai',
        bearerToken: widget.session.bearer,
        deviceId: widget.session.deviceId,
      );
      Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => TenantBrandingScope(
            branding: _branding,
            child: WorkerAiScreen(session: widget.session, ai: widget.ai),
          ),
        ),
      );
    }
  }

  Future<void> _refreshBadges() async {
    final n = await widget.offlineStore.pendingCount();
    if (mounted) setState(() => _offlinePending = n);
  }

  @override
  void dispose() {
    widget.geofence.stop();
    super.dispose();
  }

  Future<void> _loadProfileAndGeofence() async {
    try {
      final me = await widget.auth.fetchProfile(widget.session);
      await widget.workerCache.saveProfile(me);
      if (!mounted) return;
      final branding = TenantBranding.fromMePayload(me);
      setState(() => _branding = branding);
      await _brandingApplier.apply(branding);
      _startGeofence(me);
    } catch (_) {
      final cached = await widget.workerCache.loadProfile();
      if (!mounted) return;
      if (cached != null) {
        final branding = TenantBranding.fromMePayload(cached);
        setState(() => _branding = branding);
        await _brandingApplier.apply(branding);
        _startGeofence(cached);
      }
    }
  }

  void _startGeofence(Map<String, dynamic> profile) {
    final company = profile['company'] as Map<String, dynamic>?;
    final siteAccess = profile['siteAccess'] as Map<String, dynamic>?;
    final accessMode = company?['accessMode'] as String? ?? '';
    widget.geofence.start(
      bearer: widget.session.bearer,
      deviceId: widget.session.deviceId,
      siteAppMode: accessMode == 'site_app',
      autoLogout: siteAccess?['autoLogout'] == true,
      onAutoLogout: () {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Automatischer Check-out — Baustelle verlassen')),
        );
        widget.onLogout();
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final pages = <Widget>[
      HomeScreen(
        session: widget.session,
        auth: widget.auth,
        digitalCard: widget.digitalCard,
        chat: widget.chat,
        workerCache: widget.workerCache,
        ai: widget.ai,
        tasks: widget.tasks,
        onOpenAttendance: () => setState(() => _index = 1),
        onOpenTasks: () => setState(() => _index = 2),
        onOpenDeploymentPlan: () => setState(() {
          _index = 2;
          _tasksSubTab = 0;
        }),
        onOpenChat: () => setState(() => _index = 3),
      ),
      AttendanceScreen(
        session: widget.session,
        auth: widget.auth,
        attendance: widget.attendance,
        nfc: widget.nfc,
        location: widget.location,
        offlineStore: widget.offlineStore,
        offlineSync: widget.offlineSync,
        workerCache: widget.workerCache,
        embedded: true,
      ),
      TasksScreen(
        key: ValueKey('tasks-$_tasksSubTab'),
        session: widget.session,
        tasks: widget.tasks,
        auth: widget.auth,
        workerCache: widget.workerCache,
        initialTab: _tasksSubTab,
      ),
      ChatScreen(session: widget.session, chat: widget.chat),
      ProfileScreen(
        session: widget.session,
        auth: widget.auth,
        workerCache: widget.workerCache,
        push: widget.push,
        onLogout: widget.onLogout,
      ),
    ];

    return TenantBrandingScope(
      branding: _branding,
      child: Theme(
        data: _branding.themeData(base: Theme.of(context)),
        child: Scaffold(
          body: IndexedStack(index: _index, children: pages),
          bottomNavigationBar: NavigationBar(
            selectedIndex: _index,
            onDestinationSelected: (i) {
              setState(() => _index = i);
              if (i == 1) _refreshBadges();
              widget.usage.trackTab(
                tabIndex: i,
                bearerToken: widget.session.bearer,
                deviceId: widget.session.deviceId,
              );
            },
            destinations: [
              const NavigationDestination(icon: Icon(Icons.badge_outlined), selectedIcon: Icon(Icons.badge), label: 'Ausweis'),
              NavigationDestination(
                icon: Badge(
                  isLabelVisible: _offlinePending > 0,
                  label: Text('$_offlinePending'),
                  child: const Icon(Icons.nfc_outlined),
                ),
                selectedIcon: Badge(
                  isLabelVisible: _offlinePending > 0,
                  label: Text('$_offlinePending'),
                  child: const Icon(Icons.nfc),
                ),
                label: 'Check-in',
              ),
              const NavigationDestination(icon: Icon(Icons.task_alt_outlined), selectedIcon: Icon(Icons.task_alt), label: 'Aufgaben'),
              const NavigationDestination(icon: Icon(Icons.chat_bubble_outline), selectedIcon: Icon(Icons.chat_bubble), label: 'Chat'),
              const NavigationDestination(icon: Icon(Icons.person_outline), selectedIcon: Icon(Icons.person), label: 'Profil'),
            ],
          ),
        ),
      ),
    );
  }
}
