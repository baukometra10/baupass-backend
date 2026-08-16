import 'package:flutter/material.dart';

import '../../core/app_strings.dart';
import '../../core/locale_controller.dart';
import '../../core/tenant_branding.dart';
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
        return t('leaveStatusApproved', 'Genehmigt');
      case 'abgelehnt':
        return t('leaveStatusRejected', 'Abgelehnt');
      default:
        return t('leaveStatusPending', 'Offen');
    }
  }

  static String _typeLabel(String? type) {
    switch (type) {
      case 'krank':
        return t('leaveTypeSick', 'Krank');
      case 'sonstiges':
        return t('leaveTypeOther', 'Sonstiges');
      default:
        return t('leaveTypeVacation', 'Urlaub');
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: LocaleController.instance,
      builder: (context, _) {
        final branding = TenantBrandingScope.of(context);
        if (!widget.enabled) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Text(
                t(
                  'leavePlanDisabled',
                  'Urlaubsanträge sind in Ihrem Tarif nicht enthalten.',
                ),
              ),
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
                  child: Text(
                    _error!,
                    style: TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                child: FilledButton.icon(
                  onPressed: _openForm,
                  icon: const Icon(Icons.add),
                  label: Text(t('leaveNewRequest', 'Neuer Urlaubsantrag')),
                ),
              ),
              Expanded(
                child: _items.isEmpty
                    ? ListView(
                        physics: const AlwaysScrollableScrollPhysics(),
                        children: [
                          const SizedBox(height: 48),
                          Icon(
                            Icons.beach_access_outlined,
                            size: 56,
                            color: Theme.of(context).colorScheme.outline,
                          ),
                          const SizedBox(height: 16),
                          Text(
                            t('leaveEmptyTitle', 'Noch keine Urlaubsanträge'),
                            textAlign: TextAlign.center,
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                          const SizedBox(height: 8),
                          Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 32),
                            child: Text(
                              t(
                                'leaveEmptyHint',
                                'Stelle einen Antrag — dein Team sieht ihn sofort im Admin-Portal von {brand}.',
                              ).replaceAll('{brand}', branding.displayName),
                              textAlign: TextAlign.center,
                              style: Theme.of(context)
                                  .textTheme
                                  .bodyMedium
                                  ?.copyWith(
                                    color: Theme.of(context)
                                        .colorScheme
                                        .onSurfaceVariant,
                                  ),
                            ),
                          ),
                          const SizedBox(height: 24),
                          Center(
                            child: FilledButton.icon(
                              onPressed: _openForm,
                              icon: const Icon(Icons.add),
                              label: Text(
                                t('leaveFirstRequest', 'Ersten Antrag stellen'),
                              ),
                            ),
                          ),
                        ],
                      )
                    : ListView.builder(
                        padding: const EdgeInsets.all(12),
                        itemCount: _items.length,
                        itemBuilder: (context, index) {
                          final row = _items[index];
                          final days = row['days_count'] ?? '-';
                          return Card(
                            child: ListTile(
                              title: Text(
                                '${_typeLabel(row['type'] as String?)} · ${row['start_date']} → ${row['end_date']}',
                              ),
                              subtitle: Text(
                                '${_statusLabel(row['status'] as String?)} · $days ${t('days', 'Tage')}',
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
      },
    );
  }
}
