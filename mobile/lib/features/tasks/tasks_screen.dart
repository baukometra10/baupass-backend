import 'package:flutter/material.dart';

import '../../core/auth_repository.dart';
import '../../core/plan_features.dart';
import '../../core/session_store.dart';
import '../../services/tasks_repository.dart';
import '../../services/worker_cache.dart';
import 'contracts_tab.dart';
import 'deployment_plan_tab.dart';
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
    this.shiftsInnerTab = 0,
  });

  final WorkerSession session;
  final TasksRepository tasks;
  final AuthRepository auth;
  final WorkerCache workerCache;
  final int initialTab;
  final int shiftsInnerTab;

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
      length: 5,
      vsync: this,
      initialIndex: widget.initialTab.clamp(0, 4),
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
    final contractsOk = planHasFeature(_profile, 'employment_contracts');
    final planOk = planHasFeature(_profile, 'deployment_plan');

    return Scaffold(
      appBar: AppBar(
        title: const Text('Aufgaben'),
        automaticallyImplyLeading: false,
        bottom: TabBar(
          controller: _tabs,
          isScrollable: true,
          tabs: const [
            Tab(text: 'Einsatzplan'),
            Tab(text: 'Urlaub'),
            Tab(text: 'Dokumente'),
            Tab(text: 'Verträge'),
            Tab(text: 'Schichten'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabs,
        children: [
          DeploymentPlanTab(
            session: widget.session,
            tasks: widget.tasks,
            enabled: planOk,
          ),
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
            onOpenDeploymentPlan: planOk
                ? () {
                    _tabs.animateTo(0);
                  }
                : null,
          ),
          ContractsTab(
            session: widget.session,
            tasks: widget.tasks,
            enabled: contractsOk,
          ),
          ShiftsTab(
            session: widget.session,
            tasks: widget.tasks,
            initialInnerTab: widget.shiftsInnerTab,
          ),
        ],
      ),
    );
  }
}
