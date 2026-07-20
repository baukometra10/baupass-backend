import 'dart:async';

import 'package:flutter/material.dart';

import 'core/api_client.dart';
import 'core/auth_repository.dart';
import 'core/branding_store.dart';
import 'core/session_store.dart';
import 'core/tenant_branding.dart';
import 'features/auth/login_screen.dart';
import 'features/shell/worker_shell.dart';
import 'services/ai_assistant_service.dart';
import 'services/attendance_repository.dart';
import 'services/chat_repository.dart';
import 'services/deep_link_service.dart';
import 'services/digital_card_repository.dart';
import 'services/geofence_service.dart';
import 'services/location_service.dart';
import 'services/nfc_service.dart';
import 'services/offline_attendance_store.dart';
import 'services/offline_sync_service.dart';
import 'services/branding_applier.dart';
import 'services/push_foreground_listener.dart';
import 'services/push_background_handler.dart';
import 'services/push_notification_service.dart';
import 'services/tasks_repository.dart';
import 'services/usage_repository.dart';
import 'services/worker_cache.dart';
import 'core/worker_auth_errors.dart';

class WorkerApp extends StatefulWidget {
  const WorkerApp({super.key});

  @override
  State<WorkerApp> createState() => _WorkerAppState();
}

class _WorkerAppState extends State<WorkerApp> {
  late final ApiClient _api;
  late final AuthRepository _auth;
  late final AttendanceRepository _attendance;
  late final DigitalCardRepository _digitalCard;
  late final ChatRepository _chat;
  late final NfcService _nfc;
  late final LocationService _location;
  late final GeofenceService _geofence;
  late final OfflineAttendanceStore _offlineStore;
  late final OfflineSyncService _offlineSync;
  late final WorkerCache _workerCache;
  late final TasksRepository _tasks;
  late final UsageRepository _usage;
  late final PushNotificationService _push;
  late final AiAssistantService _ai;
  late final DeepLinkService _deepLinks;
  WorkerSession? _session;
  bool _bootstrapping = true;
  String? _joinError;
  final _shellKey = GlobalKey<WorkerShellState>();
  final _messengerKey = GlobalKey<ScaffoldMessengerState>();
  final _brandingApplier = BrandingApplier();
  TenantBranding _appBranding = TenantBranding.fallback;
  final List<WorkerAppRoute> _pendingRoutes = <WorkerAppRoute>[];
  String? _pendingVoiceCallId;
  String? _pendingConferenceRoomId;

  @override
  void initState() {
    super.initState();
    BrandingStore.instance.addListener(_onBrandingChanged);
    _api = ApiClient(onSessionExpired: _onSessionExpired);
    _auth = AuthRepository(_api);
    _attendance = AttendanceRepository(_api);
    _digitalCard = DigitalCardRepository(_api);
    _chat = ChatRepository(_api);
    _nfc = NfcService();
    _location = LocationService();
    _offlineStore = OfflineAttendanceStore();
    _geofence = GeofenceService(_api, _location, _offlineStore);
    _offlineSync = OfflineSyncService(_attendance, _offlineStore);
    _workerCache = WorkerCache();
    _tasks = TasksRepository(_api);
    _usage = UsageRepository(_api);
    _push = PushNotificationService(_api);
    _ai = AiAssistantService(_api);
    _deepLinks = DeepLinkService();
    PushForegroundListener.attach(
      messengerKey: _messengerKey,
      onRoute: _queueOrApplyRoute,
      onVoiceCall: _queueOrWakeVoiceCall,
      onConferenceInvite: _queueOrWakeConference,
    );
    _boot();
    _restoreBranding();
  }

  void _queueOrApplyRoute(WorkerAppRoute route) {
    if (_session == null) {
      _pendingRoutes.add(route);
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _shellKey.currentState?.navigateTo(route);
    });
  }

  void _queueOrWakeVoiceCall(String callId) {
    final id = callId.trim();
    if (id.isEmpty) return;
    if (_session == null) {
      _pendingVoiceCallId = id;
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _shellKey.currentState?.wakeForVoiceCall(id);
    });
  }

  void _queueOrWakeConference(String roomId) {
    final id = roomId.trim();
    if (id.isEmpty) return;
    if (_session == null) {
      _pendingConferenceRoomId = id;
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _shellKey.currentState?.wakeForConference(id);
    });
  }

  void _flushPendingPushActions() {
    final routes = List<WorkerAppRoute>.from(_pendingRoutes);
    _pendingRoutes.clear();
    for (final route in routes) {
      _shellKey.currentState?.navigateTo(route);
    }
    final callId = (_pendingVoiceCallId ?? '').trim();
    _pendingVoiceCallId = null;
    if (callId.isNotEmpty) {
      _shellKey.currentState?.wakeForVoiceCall(callId);
    }
    final roomId = (_pendingConferenceRoomId ?? '').trim();
    _pendingConferenceRoomId = null;
    if (roomId.isNotEmpty) {
      _shellKey.currentState?.wakeForConference(roomId);
    }
  }

  Future<void> _restoreBranding() async {
    final branding = await BrandingApplier.loadCached();
    if (!mounted) return;
    setState(() => _appBranding = branding);
    await _brandingApplier.apply(branding);
  }

  void _onBrandingChanged() {
    if (!mounted) return;
    setState(() => _appBranding = BrandingStore.instance.value);
  }

  Future<void> _boot() async {
    final existing = await _auth.loadSession();
    if (existing != null) {
      try {
        await _auth.validateSession(existing);
        _bindSession(existing);
        _finishBoot(existing);
      } on ApiException catch (e) {
        await _auth.clearToken();
        _finishBoot(null, error: formatWorkerAuthError(e));
      }
      _listenDeepLinks();
      return;
    }
    final initialUri = await _deepLinks.getInitialUri();
    final access = DeepLinkService.accessTokenFromUri(initialUri);
    if (access != null) {
      await _loginWithJoinToken(access);
    } else {
      _finishBoot(null);
      final route = DeepLinkService.appRouteFromUri(initialUri);
      if (route != null && _session != null) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          _shellKey.currentState?.navigateTo(route);
        });
      }
    }
    _listenDeepLinks();
  }

  void _bindSession(WorkerSession session) {
    _session = session;
    _offlineSync.bindSession(session);
    _offlineSync.listen((synced) {
      if (!mounted || synced <= 0) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$synced offline Check-in(s) synchronisiert')),
      );
    });
    _offlineSync.syncNow();
    _push.initializeAfterLogin(session);
  }

  void _onSessionExpired() {
    if (!mounted) return;
    _auth.clearToken();
    _offlineSync.bindSession(null);
    setState(() => _session = null);
    _messengerKey.currentState?.showSnackBar(
      const SnackBar(
        content: Text('Sitzung abgelaufen — bitte erneut anmelden.'),
        duration: Duration(seconds: 5),
      ),
    );
  }

  void _listenDeepLinks() {
    _deepLinks.listen((uri) async {
      final access = DeepLinkService.accessTokenFromUri(uri);
      if (access != null && _session == null) {
        await _loginWithJoinToken(access);
        return;
      }
      final route = DeepLinkService.appRouteFromUri(uri);
      if (route != null && _session != null) {
        _shellKey.currentState?.navigateTo(route);
      }
    });
  }

  Future<void> _loginWithJoinToken(String accessToken) async {
    setState(() {
      _bootstrapping = true;
      _joinError = null;
    });
    try {
      final pushToken = await _push.tokenForDeviceBinding();
      final session = await _auth.loginWithAccessToken(accessToken, pushToken: pushToken);
      _bindSession(session);
      _finishBoot(session);
    } catch (e) {
      final message = e is ApiException ? formatWorkerAuthError(e) : e.toString();
      _finishBoot(null, error: message);
    }
  }

  void _finishBoot(WorkerSession? session, {String? error}) {
    if (!mounted) return;
    setState(() {
      _session = session;
      _joinError = error;
      _bootstrapping = false;
    });
    if (session != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        unawaited(_drainPersistedPushActions());
        _flushPendingPushActions();
      });
    }
  }

  Future<void> _drainPersistedPushActions() async {
    final callId = await takePendingVoiceCallId();
    if (callId != null && callId.isNotEmpty) {
      _queueOrWakeVoiceCall(callId);
    }
    final roomId = await takePendingConferenceRoomId();
    if (roomId != null && roomId.isNotEmpty) {
      _queueOrWakeConference(roomId);
    }
  }

  @override
  void dispose() {
    BrandingStore.instance.removeListener(_onBrandingChanged);
    _geofence.stop();
    _deepLinks.dispose();
    _api.close();
    super.dispose();
  }

  void _onLoggedIn(WorkerSession session) {
    _bindSession(session);
    setState(() => _session = session);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(_drainPersistedPushActions());
      _flushPendingPushActions();
    });
  }

  void _onLogout() {
    _geofence.stop();
    _auth.clearToken();
    _offlineSync.bindSession(null);
    setState(() => _session = null);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      scaffoldMessengerKey: _messengerKey,
      title: _session != null ? _appBranding.displayName : 'SUPPIX',
      theme: _appBranding.themeData(),
      home: _bootstrapping
          ? const Scaffold(body: Center(child: CircularProgressIndicator()))
          : _session != null
              ? WorkerShell(
                  key: _shellKey,
                  session: _session!,
                  auth: _auth,
                  attendance: _attendance,
                  digitalCard: _digitalCard,
                  chat: _chat,
                  nfc: _nfc,
                  location: _location,
                  geofence: _geofence,
                  offlineStore: _offlineStore,
                  offlineSync: _offlineSync,
                  workerCache: _workerCache,
                  tasks: _tasks,
                  usage: _usage,
                  push: _push,
                  ai: _ai,
                  onLogout: _onLogout,
                )
              : LoginScreen(
                  auth: _auth,
                  location: _location,
                  push: _push,
                  onLoggedIn: _onLoggedIn,
                  initialError: _joinError,
                ),
    );
  }
}
