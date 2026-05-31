import 'package:flutter/material.dart';

import '../../core/session_store.dart';
import '../../services/tasks_repository.dart';

/// Monats-Einsatzplan: Tage anzeigen, ablehnen, PDF (ein Blatt).
class DeploymentPlanTab extends StatefulWidget {
  const DeploymentPlanTab({
    super.key,
    required this.session,
    required this.tasks,
    required this.enabled,
  });

  final WorkerSession session;
  final TasksRepository tasks;
  final bool enabled;

  @override
  State<DeploymentPlanTab> createState() => _DeploymentPlanTabState();
}

class _DeploymentPlanTabState extends State<DeploymentPlanTab> {
  bool _loading = true;
  String? _error;
  Map<String, dynamic>? _plan;
  int _year = DateTime.now().year;
  int _month = DateTime.now().month;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (!widget.enabled) {
      setState(() => _loading = false);
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await widget.tasks.fetchDeploymentPlan(
        session: widget.session,
        year: _year,
        month: _month,
      );
      if (!mounted) return;
      setState(() {
        _plan = data;
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

  Future<void> _pickMonth() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime(_year, _month),
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 2, 12),
      initialDatePickerMode: DatePickerMode.year,
    );
    if (picked == null) return;
    setState(() {
      _year = picked.year;
      _month = picked.month;
    });
    await _load();
  }

  Future<void> _openPdf({bool printMode = false}) async {
    try {
      final bytes = await widget.tasks.fetchDeploymentPlanPdf(
        session: widget.session,
        year: _year,
        month: _month,
      );
      final name = 'einsatzplan-$_year-${_month.toString().padLeft(2, '0')}.pdf';
      await widget.tasks.saveAndOpenPdf(bytes, filename: name);
      if (printMode && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('PDF geöffnet — bitte „Drucken“ wählen (1 Seite Querformat).')),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('PDF nicht verfügbar: $e')),
      );
    }
  }

  Future<void> _declineDay(Map<String, dynamic> day) async {
    final iso = (day['date'] as String? ?? '').substring(0, 10);
    if (iso.isEmpty) return;
    final reasonCtrl = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Einsatztag ablehnen'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${day['weekday'] ?? ''} · $iso'),
            const SizedBox(height: 12),
            TextField(
              controller: reasonCtrl,
              decoration: const InputDecoration(
                labelText: 'Grund (optional)',
                hintText: 'z. B. Arzttermin',
              ),
              maxLines: 2,
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Abbrechen')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Ablehnen')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await widget.tasks.postDeploymentDayResponse(
        session: widget.session,
        date: iso,
        action: 'decline',
        reason: reasonCtrl.text.trim(),
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Ablehnung gespeichert — Firma wird informiert.')),
        );
      }
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  Future<void> _undoDecline(String iso) async {
    try {
      await widget.tasks.postDeploymentDayResponse(
        session: widget.session,
        date: iso,
        action: 'undo',
      );
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  bool _dayHasAssignment(Map<String, dynamic> day) {
    return (day['location'] as String? ?? '').trim().isNotEmpty;
  }

  bool _isDeclined(Map<String, dynamic> day) {
    return day['workerResponse'] == 'declined' || day['isDeclined'] == true;
  }

  bool _canDecline(Map<String, dynamic> day, bool canRespond) {
    if (!canRespond || !_dayHasAssignment(day) || _isDeclined(day)) return false;
    final iso = (day['date'] as String? ?? '').substring(0, 10);
    final parsed = DateTime.tryParse(iso);
    if (parsed == null) return false;
    final today = DateTime.now();
    final d = DateTime(parsed.year, parsed.month, parsed.day);
    final t = DateTime(today.year, today.month, today.day);
    return !d.isBefore(t);
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text('Einsatzplan ist in Ihrem Paket nicht freigeschaltet. Bitte Arbeitgeber kontaktieren.'),
        ),
      );
    }

    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    final published = _plan?['published'] == true;
    final canRespond = _plan?['canRespond'] == true ||
        published ||
        (_plan?['visible'] != false && ((_plan?['scheduledDayCount'] as num?)?.toInt() ?? 0) > 0);
    final visible = _plan?['visible'] != false;
    final days = (_plan?['days'] as List?)?.cast<Map<String, dynamic>>() ?? <Map<String, dynamic>>[];

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _pickMonth,
                  icon: const Icon(Icons.calendar_month),
                  label: Text('${_month.toString().padLeft(2, '0')}/$_year'),
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                tooltip: 'PDF',
                onPressed: published ? () => _openPdf() : null,
                icon: const Icon(Icons.picture_as_pdf_outlined),
              ),
              IconButton(
                tooltip: 'Drucken',
                onPressed: published ? () => _openPdf(printMode: true) : null,
                icon: const Icon(Icons.print_outlined),
              ),
            ],
          ),
          if (!visible)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Text('Für diesen Monat liegt noch kein Plan vor. Ihr Arbeitgeber muss den Monatsplan speichern oder senden.'),
              ),
            )
          else if (!published && canRespond)
            Card(
              color: Theme.of(context).colorScheme.surfaceContainerHighest,
              child: const Padding(
                padding: EdgeInsets.all(16),
                child: Text(
                  'Entwurf: Geplante Tage können Sie bereits ablehnen. Das PDF folgt nach Freigabe durch die Firma.',
                ),
              ),
            ),
          if (visible) ...[
            ...days.where((d) {
              final loc = (d['location'] as String? ?? '').trim();
              final declined = _isDeclined(d);
              final weekend = d['isWeekend'] == true;
              return loc.isNotEmpty || declined || !weekend;
            }).map((day) {
              final iso = (day['date'] as String? ?? '').substring(0, 10);
              final loc = (day['location'] as String? ?? '').trim();
              final declined = _isDeclined(day);
              final start = (day['shiftStart'] as String? ?? '').trim();
              final end = (day['shiftEnd'] as String? ?? '').trim();
              String time = '';
              if (start.isNotEmpty || end.isNotEmpty) {
                time = [start, end].where((s) => s.isNotEmpty).join(' – ');
              }
              return Card(
                margin: const EdgeInsets.only(bottom: 8),
                color: declined
                    ? Theme.of(context).colorScheme.errorContainer.withValues(alpha: 0.35)
                    : null,
                child: ListTile(
                  title: Text('${iso.length >= 10 ? iso.substring(8, 10) : iso}. · ${day['weekday'] ?? ''}'),
                  subtitle: Text(
                    [
                      if (loc.isNotEmpty) loc else 'Kein Einsatz',
                      if (time.isNotEmpty) time,
                      if (declined) 'Abgelehnt',
                    ].join('\n'),
                  ),
                  trailing: declined
                      ? TextButton(
                          onPressed: () => _undoDecline(iso),
                          child: const Text('Zurück'),
                        )
                      : (_canDecline(day, canRespond)
                          ? TextButton(
                              onPressed: () => _declineDay(day),
                              child: const Text('Kann nicht'),
                            )
                          : null),
                ),
              );
            }),
          ],
        ],
      ),
    );
  }
}
