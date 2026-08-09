import 'dart:async';

import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/app_strings.dart';
import '../../core/auth_repository.dart';
import '../../core/api_client.dart';
import '../../core/locale_controller.dart';
import '../../core/session_store.dart';
import '../../core/tenant_branding.dart';
import '../../core/worker_auth_errors.dart';
import '../../core/privacy_consent_store.dart';
import '../../services/ai_assistant_service.dart';
import '../../services/attendance_repository.dart';
import '../../services/branding_applier.dart';
import '../../services/chat_repository.dart';
import '../../services/conference_repository.dart';
import '../../services/digital_card_repository.dart';
import '../../services/deep_link_service.dart';
import '../../services/geofence_service.dart';
import '../../services/location_service.dart';
import '../../services/nfc_service.dart';
import '../../services/offline_attendance_store.dart';
import '../../services/offline_sync_service.dart';
import '../../services/push_notification_service.dart';
import '../../services/tasks_repository.dart';
import '../../services/usage_repository.dart';
import '../../services/voice_call_controller.dart';
import '../../services/push_background_handler.dart';
import '../../services/worker_cache.dart';
import '../attendance/attendance_screen.dart';
import '../home/home_screen.dart';
import '../ai/worker_ai_screen.dart';
import '../chat/chat_screen.dart';
import '../../services/legal_repository.dart';
import '../legal/privacy_consent_dialog.dart';
import '../profile/profile_screen.dart';
import '../tasks/tasks_screen.dart';
import '../voice_call/conference_invite_sheet.dart';
import '../voice_call/voice_call_overlay.dart';

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

class WorkerShellState extends State<WorkerShell> with WidgetsBindingObserver {
  int _index = 0;
  int _tasksSubTab = 0;
  int _shiftsInnerTab = 0;
  int _offlinePending = 0;
  TenantBranding _branding = TenantBranding.fallback;
  final _brandingApplier = BrandingApplier();
  late final VoiceCallController _voiceCall;
  late final ConferenceRepository _conferenceRepo;
  Timer? _conferencePollTimer;
  String? _shownConferenceId;
  String? _pendingConferenceForceId;
  bool _conferenceSheetOpen = false;
  String? _chatMissedCallId;
  bool _chatAutoCallback = false;
  int _chatRouteNonce = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _voiceCall = VoiceCallController(repo: widget.chat.voiceCalls);
    _voiceCall.onMissedCallback = (callId) {
      navigateTo(
        WorkerAppRoute(
          tabIndex: 3,
          openChat: true,
          missedCallId: callId,
          requestCallback: true,
        ),
      );
    };
    // Defer CallKit/bind so first frame (Ausweis) can paint after QR login.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _voiceCall.bind(widget.session);
    });
    _conferenceRepo = ConferenceRepository(widget.chat.apiClient);
    _conferencePollTimer = Timer.periodic(const Duration(seconds: 3), (_) {
      unawaited(_pollConferenceInvite());
    });
    unawaited(_pollConferenceInvite());
    _loadProfileAndGeofence();
    _refreshBadges();
    widget.usage.trackTab(
      tabIndex: _index,
      bearerToken: widget.session.bearer,
      deviceId: widget.session.deviceId,
    );
    WidgetsBinding.instance.addPostFrameCallback((_) => _maybeShowPrivacyConsent());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _voiceCall.onAppResumed();
      unawaited(_pollConferenceInvite());
      unawaited(_drainMissedCallbackIntent());
    }
  }

  Future<void> _drainMissedCallbackIntent() async {
    final id = await takePendingMissedCallback();
    if (id == null || id.isEmpty || !mounted) return;
    navigateTo(
      WorkerAppRoute(
        tabIndex: 3,
        openChat: true,
        missedCallId: id,
        requestCallback: true,
      ),
    );
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _conferencePollTimer?.cancel();
    _voiceCall.dispose();
    widget.geofence.stop();
    super.dispose();
  }

  Future<void> _pollConferenceInvite({String? forceRoomId}) async {
    if (!mounted || _conferenceSheetOpen || _voiceCall.isActive) return;
    try {
      final forced = (forceRoomId ?? _pendingConferenceForceId ?? '').trim();
      Map<String, dynamic>? invite;
      if (forced.isNotEmpty) {
        invite = await _conferenceRepo.inviteById(widget.session, forced);
      }
      invite ??= await _conferenceRepo.incoming(widget.session);
      if (!mounted || invite == null) return;
      final id = (invite['id'] ?? '').toString();
      if (id.isEmpty) return;
      if (forced.isNotEmpty && id != forced) return;
      if (forced.isEmpty && id == _shownConferenceId) return;
      _conferenceSheetOpen = true;
      final result = await showModalBottomSheet<String>(
        context: context,
        showDragHandle: true,
        isDismissible: true,
        builder: (_) => ConferenceInviteSheet(
          session: widget.session,
          repo: _conferenceRepo,
          invite: invite!,
        ),
      );
      // Only suppress re-prompt after explicit join/decline — not swipe-dismiss.
      if (result == 'joined' || result == 'declined') {
        _shownConferenceId = id;
        _pendingConferenceForceId = null;
      }
    } catch (_) {
      /* ignore transient */
    } finally {
      _conferenceSheetOpen = false;
    }
  }

  Future<void> _maybeShowPrivacyConsent() async {
    final store = PrivacyConsentStore();
    String contentVersion = PrivacyConsentStore.version;
    try {
      final legal = await LegalRepository(ApiClient()).fetch(widget.session);
      contentVersion = legal.contentVersion.isNotEmpty ? legal.contentVersion : contentVersion;
    } catch (_) {
      /* optional */
    }
    if (await store.hasAccepted(contentVersion: contentVersion)) return;
    if (!mounted) return;
    final accepted = await showPrivacyConsentDialog(context, session: widget.session);
    if (!mounted) return;
    if (accepted == true) {
      await store.accept(contentVersion: contentVersion);
      try {
        await ApiClient().postJson(
          '/api/worker-app/privacy-consent',
          bearerToken: widget.session.bearer,
          deviceId: widget.session.deviceId,
          body: {
            'granted': true,
            'version': contentVersion,
            'consentType': 'privacy_app',
          },
        );
      } catch (_) {
        /* audit best-effort */
      }
      return;
    }
    widget.onLogout();
  }

  void navigateTo(WorkerAppRoute route) {
    final external = (route.externalUrl ?? '').trim();
    if (external.isNotEmpty) {
      launchUrl(Uri.parse(external), mode: LaunchMode.externalApplication);
      return;
    }
    final callId = (route.incomingCallId ?? '').trim();
    if (callId.isNotEmpty) {
      _voiceCall.wakeForCall(callId);
    }
    final missedId = (route.missedCallId ?? '').trim();
    final roomId = (route.conferenceRoomId ?? '').trim();
    if (roomId.isNotEmpty) {
      wakeForConference(roomId);
    }
    setState(() {
      _index = route.openChat || missedId.isNotEmpty ? 3 : route.tabIndex.clamp(0, 4);
      _tasksSubTab = route.tasksSubTab.clamp(0, 4);
      _shiftsInnerTab = route.shiftsInnerTab.clamp(0, 1);
      if (missedId.isNotEmpty || route.requestCallback) {
        _chatMissedCallId = missedId.isNotEmpty ? missedId : null;
        _chatAutoCallback = route.requestCallback;
        _chatRouteNonce += 1;
      }
    });
    if ((route.openChat || missedId.isNotEmpty) && mounted) {
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

  void wakeForVoiceCall(String callId) {
    _voiceCall.wakeForCall(callId);
  }

  void notifyCameraIntent({String callId = '', String fromName = 'Arbeitgeber'}) {
    _voiceCall.notifyCameraIntentFromPush(fromName: fromName, callId: callId);
  }

  void wakeForConference(String roomId) {
    final id = roomId.trim();
    if (id.isNotEmpty) {
      _shownConferenceId = null;
      _pendingConferenceForceId = id;
    }
    unawaited(_pollConferenceInvite(forceRoomId: id.isEmpty ? null : id));
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
    } on ApiException catch (e) {
      if (isWorkerSessionAuthError(e.errorCode)) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(formatWorkerAuthError(e)), duration: const Duration(seconds: 6)),
        );
        widget.onLogout();
        return;
      }
      final cached = await widget.workerCache.loadProfile();
      if (!mounted) return;
      if (cached != null) {
        final branding = TenantBranding.fromMePayload(cached);
        setState(() => _branding = branding);
        await _brandingApplier.apply(branding);
        _startGeofence(cached);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(formatWorkerAuthError(e)), duration: const Duration(seconds: 6)),
        );
      }
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
    final openSession = siteAccess?['openCheckInToday'] == true ||
        siteAccess?['siteSessionOpen'] == true;
    unawaited(_startGeofenceAsync(
      siteAppMode: accessMode == 'site_app',
      liveTracking: openSession,
      autoLogout: siteAccess?['autoLogout'] != false,
    ));
  }

  Future<void> _startGeofenceAsync({
    required bool siteAppMode,
    required bool liveTracking,
    required bool autoLogout,
  }) async {
    final cachedOpen = await widget.workerCache.openCheckInToday();
    final enableLive = liveTracking || cachedOpen;

    void onPresence(Map<String, dynamic> presence) {
      final open = presence['openCheckInToday'] == true ||
          presence['siteSessionOpen'] == true ||
          presence['autoCheckInLogId'] != null ||
          presence['siteLoginLogId'] != null ||
          presence['locationSaved'] == true;
      final left = presence['siteLeaveApplied'] == true;
      if (open) {
        unawaited(widget.workerCache.setOpenCheckInToday(true));
        widget.geofence.setLiveTracking(true);
      } else if (left) {
        unawaited(widget.workerCache.setOpenCheckInToday(false));
        widget.geofence.setLiveTracking(false);
      }
    }

    void onNotify(String message) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message)),
      );
    }

    await widget.geofence.start(
      bearer: widget.session.bearer,
      deviceId: widget.session.deviceId,
      siteAppMode: siteAppMode,
      // Live pin only while checked in — not merely because the app is open.
      liveTracking: enableLive,
      autoLogout: autoLogout,
      onPresence: onPresence,
      onNotify: onNotify,
    );
    if (enableLive) {
      await widget.geofence.forcePing(
        bearer: widget.session.bearer,
        deviceId: widget.session.deviceId,
        autoLogout: autoLogout,
        onPresence: onPresence,
        onNotify: onNotify,
      );
    }
    unawaited(_maybeWarnBackgroundLocation(siteAppMode));
  }

  /// Re-sync live tracking after manual GPS/NFC check-in or check-out.
  Future<void> _onAttendanceSessionChanged() async {
    final open = await widget.workerCache.openCheckInToday();
    if (!open) {
      widget.geofence.setLiveTracking(false);
      return;
    }

    void onNotify(String message) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message)),
      );
    }

    if (widget.geofence.isRunning) {
      widget.geofence.setLiveTracking(true);
      await widget.geofence.forcePing(
        bearer: widget.session.bearer,
        deviceId: widget.session.deviceId,
        autoLogout: true,
        onNotify: onNotify,
      );
      return;
    }
    final cached = await widget.workerCache.loadProfile();
    if (cached != null) {
      final rawAccess = cached['siteAccess'];
      final siteAccess = <String, dynamic>{
        if (rawAccess is Map) ...Map<String, dynamic>.from(rawAccess),
        'openCheckInToday': true,
      };
      _startGeofence({...cached, 'siteAccess': siteAccess});
      return;
    }
    await widget.geofence.start(
      bearer: widget.session.bearer,
      deviceId: widget.session.deviceId,
      siteAppMode: false,
      liveTracking: true,
      autoLogout: true,
      onNotify: onNotify,
    );
  }

  Future<void> _maybeWarnBackgroundLocation(bool siteAppMode) async {
    if (!siteAppMode || !mounted) return;
    final permission = await widget.location.requestLocationPermission();
    if (!mounted) return;
    if (widget.location.isBackgroundCapable(permission)) return;
    if (permission == LocationPermission.whileInUse) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Für automatische Anwesenheit im Hintergrund: Standort «Immer erlauben» in den Systemeinstellungen aktivieren.',
          ),
          duration: Duration(seconds: 8),
        ),
      );
    }
  }

  Widget _pageFor(int index) {
    switch (index) {
      case 1:
        return AttendanceScreen(
          session: widget.session,
          auth: widget.auth,
          attendance: widget.attendance,
          nfc: widget.nfc,
          location: widget.location,
          offlineStore: widget.offlineStore,
          offlineSync: widget.offlineSync,
          workerCache: widget.workerCache,
          embedded: true,
          onSessionChanged: () {
            unawaited(_onAttendanceSessionChanged());
          },
        );
      case 2:
        return TasksScreen(
          key: ValueKey('tasks-$_tasksSubTab-$_shiftsInnerTab'),
          session: widget.session,
          tasks: widget.tasks,
          auth: widget.auth,
          workerCache: widget.workerCache,
          initialTab: _tasksSubTab,
          shiftsInnerTab: _shiftsInnerTab,
        );
      case 3:
        return ChatScreen(
          key: ValueKey('chat-$_chatRouteNonce-${_chatMissedCallId ?? ""}'),
          session: widget.session,
          chat: widget.chat,
          voiceCall: _voiceCall,
          focusMissedCallId: _chatMissedCallId,
          autoRequestCallback: _chatAutoCallback,
        );
      case 4:
        return ProfileScreen(
          session: widget.session,
          auth: widget.auth,
          workerCache: widget.workerCache,
          push: widget.push,
          onLogout: widget.onLogout,
        );
      case 0:
      default:
        return HomeScreen(
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
          voiceCall: _voiceCall,
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    // Build only the active tab. IndexedStack mounted Chat/Tasks/etc. at login
    // and a crash in any of them blanked the whole shell after QR join.
    return ListenableBuilder(
      listenable: LocaleController.instance,
      builder: (context, _) => TenantBrandingScope(
      branding: _branding,
      child: Theme(
        data: _branding.themeData(base: Theme.of(context)),
        child: Builder(
          builder: (context) {
            final scheme = Theme.of(context).colorScheme;
            return Scaffold(
              body: Stack(
                fit: StackFit.expand,
                children: [
                  KeyedSubtree(
                    key: ValueKey('shell-page-$_index'),
                    child: _pageFor(_index),
                  ),
                  ListenableBuilder(
                    listenable: _voiceCall,
                    builder: (context, _) {
                      if (_voiceCall.phase == VoiceCallUiPhase.idle) {
                        return const SizedBox.shrink();
                      }
                      return Positioned.fill(
                        child: Material(
                          type: MaterialType.transparency,
                          child: VoiceCallOverlay(
                            controller: _voiceCall,
                            branding: _branding,
                          ),
                        ),
                      );
                    },
                  ),
                ],
              ),
              bottomNavigationBar: Material(
                elevation: 14,
                color: scheme.surface,
                child: SafeArea(
                  top: false,
                  child: BottomNavigationBar(
                    type: BottomNavigationBarType.fixed,
                    currentIndex: _index,
                    backgroundColor: scheme.surface,
                    selectedItemColor: scheme.primary,
                    // ignore: deprecated_member_use
                    unselectedItemColor: scheme.onSurface.withOpacity(0.72),
                    selectedFontSize: 12,
                    unselectedFontSize: 11,
                    selectedLabelStyle: const TextStyle(fontWeight: FontWeight.w700),
                    unselectedLabelStyle: const TextStyle(fontWeight: FontWeight.w500),
                    showUnselectedLabels: true,
                    showSelectedLabels: true,
                    elevation: 0,
                    onTap: (i) {
                      setState(() => _index = i);
                      if (i == 0 || i == 1 || i == 3) _refreshBadges();
                      widget.usage.trackTab(
                        tabIndex: i,
                        bearerToken: widget.session.bearer,
                        deviceId: widget.session.deviceId,
                      );
                    },
                    items: [
                      BottomNavigationBarItem(
                        icon: const Icon(Icons.badge_outlined),
                        activeIcon: const Icon(Icons.badge),
                        label: t('navPass', 'Ausweis'),
                      ),
                      BottomNavigationBarItem(
                        icon: Badge(
                          isLabelVisible: _offlinePending > 0,
                          label: Text('$_offlinePending'),
                          child: const Icon(Icons.nfc_outlined),
                        ),
                        activeIcon: Badge(
                          isLabelVisible: _offlinePending > 0,
                          label: Text('$_offlinePending'),
                          child: const Icon(Icons.nfc),
                        ),
                        label: t('navCheckin', 'Check-in'),
                      ),
                      BottomNavigationBarItem(
                        icon: const Icon(Icons.task_alt_outlined),
                        activeIcon: const Icon(Icons.task_alt),
                        label: t('navTasks', 'Aufgaben'),
                      ),
                      BottomNavigationBarItem(
                        icon: const Icon(Icons.chat_bubble_outline),
                        activeIcon: const Icon(Icons.chat_bubble),
                        label: t('navChat', 'Chat'),
                      ),
                      BottomNavigationBarItem(
                        icon: const Icon(Icons.person_outline),
                        activeIcon: const Icon(Icons.person),
                        label: t('navProfile', 'Profil'),
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    ),
    );
  }
}
