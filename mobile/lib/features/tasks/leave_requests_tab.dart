import 'package:flutter/material.dart';

import '../../core/session_store.dart';
import '../../services/tasks_repository.dart';
import 'leave_request_form.dart';

class LeaveRequestsTab extends StatefulWidget {
  const LeaveRequestsTab({
    super.key,
    required this.session,
    required this.tasks,
    required this.enabled,
    this.onSubmitted,
  });

  final WorkerSession session;
  final TasksRepository tasks;
  final bool enabled;
  final VoidCallback? onSubmitted;

  @override
  State<LeaveRequestsTab> createState() => _LeaveRequestsTabState();
}

class _LeaveRequestsTabState extends State<LeaveRequestsTab> {
  List<Map<String, dynamic>> _items = <Map<String, dynamic>>[];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (!widget.enabled) {
      setState(() {
        _loading = false;
        _items = <Map<String, dynamic>>[];
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final rows = await widget.tasks.listLeaveRequests(widget.session);
      if (!mounted) return;
      setState(() {
        _items = rows;
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

  Future<void> _openForm() async {
    final created = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => LeaveRequestForm(
          session: widget.session,
          tasks: widget.tasks,
        ),
      ),
    );
    if (created == true) {
      widget.onSubmitted?.call();
      await _load();
    }
  }

  static String _statusLabel(String? status) {
    switch (status) {
      case 'genehmigt':
        return 'Approved';
      case 'abgelehnt':
        return 'Rejected';
      default:
        return 'Pending';
    }
  }

  static String _typeLabel(String? type) {
    switch (type) {
      case 'krank':
        return 'Sick';
      case 'sonstiges':
        return 'Other';
      default:
        return 'Vacation';
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text('Leave requests are not included in your company plan.'),
        ),
      );
    }

    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    return RefreshIndicator(
      onRefresh: _load,
      child: Column(
        children: [
          if (_error != null)
            Padding(
              padding: const EdgeInsets.all(12),
              child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: FilledButton.icon(
              onPressed: _openForm,
              icon: const Icon(Icons.add),
              label: const Text('New leave request'),
            ),
          ),
          Expanded(
            child: _items.isEmpty
                ? ListView(
                    children: const [
                      SizedBox(height: 80),
                      Center(child: Text('No leave requests yet.')),
                    ],
                  )
                : ListView.builder(
                    padding: const EdgeInsets.all(12),
                    itemCount: _items.length,
                    itemBuilder: (context, index) {
                      final row = _items[index];
                      return Card(
                        child: ListTile(
                          title: Text(
                            '${_typeLabel(row['type'] as String?)} · ${row['start_date']} → ${row['end_date']}',
                          ),
                          subtitle: Text(
                            '${_statusLabel(row['status'] as String?)} · ${row['days_count'] ?? '-'} day(s)',
                          ),
                          trailing: Text(
                            _statusLabel(row['status'] as String?),
                            style: TextStyle(
                              color: row['status'] == 'genehmigt'
                                  ? Colors.green.shade700
                                  : row['status'] == 'abgelehnt'
                                      ? Colors.red.shade700
                                      : Colors.orange.shade800,
                            ),
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
