import 'package:flutter/material.dart';

import 'core/api_client.dart';
import 'core/auth_repository.dart';
import 'features/auth/login_screen.dart';
import 'features/shell/worker_shell.dart';
import 'services/attendance_repository.dart';
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
  late final OfflineAttendanceStore _offlineStore;
  late final WorkerCache _workerCache;
  late final TasksRepository _tasks;
  late final PushNotificationService _push;
  String? _sessionToken;
  bool _bootstrapping = true;

  @override
  void initState() {
    super.initState();
    _api = ApiClient();
    _auth = AuthRepository(_api);
    _attendance = AttendanceRepository(_api);
    _nfc = NfcService();
    _offlineStore = OfflineAttendanceStore();
    _workerCache = WorkerCache();
    _tasks = TasksRepository(_api);
    _push = PushNotificationService(_api);
    _restoreSession();
  }

  Future<void> _restoreSession() async {
    final token = await _auth.loadToken();
    setState(() {
      _sessionToken = token;
      _bootstrapping = false;
    });
  }

  void _onLoggedIn() async {
    final token = await _auth.loadToken();
    setState(() => _sessionToken = token);
  }

  @override
  void dispose() {
    _api.close();
    super.dispose();
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
                  offlineStore: _offlineStore,
                  workerCache: _workerCache,
                  tasks: _tasks,
                  push: _push,
                )
              : LoginScreen(auth: _auth, onLoggedIn: _onLoggedIn),
    );
  }
}
