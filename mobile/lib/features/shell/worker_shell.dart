import 'package:flutter/material.dart';

import '../../core/auth_repository.dart';
import '../../services/attendance_repository.dart';
import '../../services/location_service.dart';
import '../../services/nfc_service.dart';
import '../../services/offline_attendance_store.dart';
import '../../services/push_notification_service.dart';
import '../../services/tasks_repository.dart';
import '../../services/worker_cache.dart';
import '../attendance/attendance_screen.dart';
import '../home/home_screen.dart';
import '../profile/profile_screen.dart';
import '../tasks/tasks_screen.dart';

/// Unified post-login shell — shared navigation for Android and iOS.
class WorkerShell extends StatefulWidget {
  const WorkerShell({
    super.key,
    required this.sessionToken,
    required this.auth,
    required this.attendance,
    required this.nfc,
    required this.location,
    required this.offlineStore,
    required this.workerCache,
    required this.tasks,
    required this.push,
  });

  final String sessionToken;
  final AuthRepository auth;
  final AttendanceRepository attendance;
  final NfcService nfc;
  final LocationService location;
  final OfflineAttendanceStore offlineStore;
  final WorkerCache workerCache;
  final TasksRepository tasks;
  final PushNotificationService push;

  @override
  State<WorkerShell> createState() => _WorkerShellState();
}

class _WorkerShellState extends State<WorkerShell> {
  int _index = 0;

  @override
  void initState() {
    super.initState();
    widget.push.initializeAfterLogin(widget.sessionToken);
  }

  @override
  Widget build(BuildContext context) {
    final pages = <Widget>[
      HomeScreen(
        sessionToken: widget.sessionToken,
        auth: widget.auth,
        workerCache: widget.workerCache,
        onOpenAttendance: () => setState(() => _index = 1),
      ),
      AttendanceScreen(
        sessionToken: widget.sessionToken,
        auth: widget.auth,
        attendance: widget.attendance,
        nfc: widget.nfc,
        location: widget.location,
        offlineStore: widget.offlineStore,
        workerCache: widget.workerCache,
        embedded: true,
      ),
      TasksScreen(
        sessionToken: widget.sessionToken,
        tasks: widget.tasks,
        auth: widget.auth,
        workerCache: widget.workerCache,
      ),
      ProfileScreen(
        sessionToken: widget.sessionToken,
        auth: widget.auth,
        workerCache: widget.workerCache,
        push: widget.push,
        onLogout: () => Navigator.of(context).popUntil((route) => route.isFirst),
      ),
    ];

    return Scaffold(
      body: IndexedStack(index: _index, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(
            icon: Icon(Icons.nfc_outlined),
            selectedIcon: Icon(Icons.nfc),
            label: 'Attendance',
          ),
          NavigationDestination(icon: Icon(Icons.task_alt_outlined), selectedIcon: Icon(Icons.task_alt), label: 'Tasks'),
          NavigationDestination(icon: Icon(Icons.person_outline), selectedIcon: Icon(Icons.person), label: 'Profile'),
        ],
      ),
    );
  }
}
