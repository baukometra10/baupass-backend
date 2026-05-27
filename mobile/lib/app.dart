import 'package:flutter/material.dart';

import 'core/api_client.dart';
import 'core/auth_repository.dart';
import 'features/auth/login_screen.dart';
import 'features/shell/worker_shell.dart';
import 'services/attendance_repository.dart';
import 'services/deep_link_service.dart';
import 'services/location_service.dart';
import 'services/nfc_service.dart';
import 'services/offline_attendance_store.dart';
import 'services/push_notification_service.dart';
import 'services/tasks_repository.dart';
import 'services/worker_cache.dart';

class WorkerApp extends StatefulWidget {
  const WorkerApp({super.key});

  @override
  State<WorkerApp> createState() => _WorkerAppState();
}

class _WorkerAppState extends State<WorkerApp> {
  late final ApiClient _api;
  late final AuthRepository _auth;
  late final AttendanceRepository _attendance;
  late final NfcService _nfc;
  late final LocationService _location;
  late final OfflineAttendanceStore _offlineStore;
  late final WorkerCache _workerCache;
  late final TasksRepository _tasks;
  late final PushNotificationService _push;
  late final DeepLinkService _deepLinks;
  String? _sessionToken;
  bool _bootstrapping = true;
  String? _joinError;

  @override
  void initState() {
    super.initState();
    _api = ApiClient();
    _auth = AuthRepository(_api);
    _attendance = AttendanceRepository(_api);
    _nfc = NfcService();
    _location = LocationService();
    _offlineStore = OfflineAttendanceStore();
    _workerCache = WorkerCache();
    _tasks = TasksRepository(_api);
    _push = PushNotificationService(_api);
    _deepLinks = DeepLinkService();
    _boot();
  }

  Future<void> _boot() async {
    final existing = await _auth.loadToken();
    if (existing != null && existing.isNotEmpty) {
      _finishBoot(existing);
      _listenDeepLinks();
      return;
    }
    final initialUri = await _deepLinks.getInitialUri();
    final access = DeepLinkService.accessTokenFromUri(initialUri);
    if (access != null) {
      await _loginWithJoinToken(access);
    } else {
      _finishBoot(null);
    }
    _listenDeepLinks();
  }

  void _listenDeepLinks() {
    _deepLinks.listen((uri) async {
      final access = DeepLinkService.accessTokenFromUri(uri);
      if (access == null || _sessionToken != null) return;
      await _loginWithJoinToken(access);
    });
  }

  Future<void> _loginWithJoinToken(String accessToken) async {
    setState(() {
      _bootstrapping = true;
      _joinError = null;
    });
    try {
      await _auth.loginWithAccessToken(accessToken);
      final token = await _auth.loadToken();
      _finishBoot(token);
    } catch (e) {
      _finishBoot(null, error: e.toString());
    }
  }

  void _finishBoot(String? token, {String? error}) {
    if (!mounted) return;
    setState(() {
      _sessionToken = token;
      _joinError = error;
      _bootstrapping = false;
    });
  }

  @override
  void dispose() {
    _deepLinks.dispose();
    _api.close();
    super.dispose();
  }

  void _onLoggedIn() async {
    final token = await _auth.loadToken();
    setState(() => _sessionToken = token);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'BauPass Worker',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1B5E8C)),
        useMaterial3: true,
      ),
      home: _bootstrapping
          ? const Scaffold(body: Center(child: CircularProgressIndicator()))
          : _sessionToken != null
              ? WorkerShell(
                  sessionToken: _sessionToken!,
                  auth: _auth,
                  attendance: _attendance,
                  nfc: _nfc,
                  location: _location,
                  offlineStore: _offlineStore,
                  workerCache: _workerCache,
                  tasks: _tasks,
                  push: _push,
                )
              : LoginScreen(
                  auth: _auth,
                  onLoggedIn: _onLoggedIn,
                  initialError: _joinError,
                ),
    );
  }
}
