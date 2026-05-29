import 'package:flutter/material.dart';

import '../../core/auth_repository.dart';
import '../../core/plan_features.dart';
import '../../core/session_store.dart';
import '../../services/tasks_repository.dart';
import '../../services/worker_cache.dart';
import 'documents_tab.dart';
import 'leave_requests_tab.dart';
import 'shifts_tab.dart';

class TasksScreen extends StatefulWidget {
  const TasksScreen({
    super.key,
    required this.session,
    required this.tasks,
    required this.auth,
    required this.workerCache,
    this.initialTab = 0,
  });

  final WorkerSession session;
  final TasksRepository tasks;
  final AuthRepository auth;
  final WorkerCache workerCache;
  final int initialTab;

  @override
  State<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends State<TasksScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  Map<String, dynamic>? _profile;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(
      length: 3,
      vsync: this,
      initialIndex: widget.initialTab.clamp(0, 2),
    );
    _loadProfile();
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  Future<void> _loadProfile() async {
    try {
      final me = await widget.auth.fetchProfile(widget.session);
      await widget.workerCache.saveProfile(me);
      if (mounted) setState(() => _profile = me);
    } catch (_) {
      final cached = await widget.workerCache.loadProfile();
      if (mounted) setState(() => _profile = cached);
    }
  }

  @override
  Widget build(BuildContext context) {
    final leaveOk = planHasFeature(_profile, 'leave_management');
    final docsOk = planHasFeature(_profile, 'document_upload');

    return Scaffold(
      appBar: AppBar(
        title: const Text('Tasks'),
        automaticallyImplyLeading: false,
        bottom: TabBar(
          controller: _tabs,
          tabs: const [
            Tab(text: 'Leave'),
            Tab(text: 'Documents'),
            Tab(text: 'Shifts'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: [
          LeaveRequestsTab(
            session: widget.session,
            tasks: widget.tasks,
            enabled: leaveOk,
            onSubmitted: _loadProfile,
          ),
          DocumentsTab(
            session: widget.session,
            tasks: widget.tasks,
            enabled: docsOk,
          ),
          ShiftsTab(session: widget.session, tasks: widget.tasks),
        ],
      ),
    );
  }
}
