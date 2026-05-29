import 'package:flutter/material.dart';

import '../../core/session_store.dart';
import '../../services/tasks_repository.dart';

class ShiftsTab extends StatefulWidget {
  const ShiftsTab({
    super.key,
    required this.session,
    required this.tasks,
  });

  final WorkerSession session;
  final TasksRepository tasks;

  @override
  State<ShiftsTab> createState() => _ShiftsTabState();
}

class _ShiftsTabState extends State<ShiftsTab> {
  List<Map<String, dynamic>> _assignments = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final rows = await widget.tasks.listShiftAssignments(widget.session);
      if (!mounted) return;
      setState(() {
        _assignments = rows;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  String _fmt(String? iso) {
    if (iso == null || iso.isEmpty) return '—';
    final s = iso.length >= 16 ? iso.substring(0, 16).replaceFirst('T', ' ') : iso;
    return s;
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_error!, textAlign: TextAlign.center),
              const SizedBox(height: 12),
              FilledButton(onPressed: _load, child: const Text('Erneut laden')),
            ],
          ),
        ),
      );
    }
    if (_assignments.isEmpty) {
      return RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: const [
            SizedBox(height: 80),
            Center(child: Text('Keine anstehenden Schichten')),
          ],
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.separated(
        padding: const EdgeInsets.all(12),
        itemCount: _assignments.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (context, i) {
          final a = _assignments[i];
          final status = (a['status'] as String?) ?? 'scheduled';
          final site = (a['site'] as String?)?.trim() ?? '';
          final notes = (a['notes'] as String?)?.trim() ?? '';
          final sub = '${_fmt(a['endTime'] as String?)}${site.isNotEmpty ? ' · $site' : ''}'
              '${notes.isNotEmpty ? '\n$notes' : ''}';
          return Card(
            child: ListTile(
              title: Text(_fmt(a['startTime'] as String?)),
              subtitle: Text(sub),
              trailing: Chip(
                label: Text(status, style: const TextStyle(fontSize: 11)),
                visualDensity: VisualDensity.compact,
              ),
              isThreeLine: notes.isNotEmpty,
            ),
          );
        },
      ),
    );
  }
}
