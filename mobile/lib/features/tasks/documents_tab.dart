import 'package:flutter/material.dart';

import '../../core/session_store.dart';
import '../../services/tasks_repository.dart';

class DocumentsTab extends StatefulWidget {
  const DocumentsTab({
    super.key,
    required this.session,
    required this.tasks,
    required this.enabled,
    this.onOpenDeploymentPlan,
  });

  final WorkerSession session;
  final TasksRepository tasks;
  final bool enabled;
  final VoidCallback? onOpenDeploymentPlan;

  @override
  State<DocumentsTab> createState() => _DocumentsTabState();
}

class _DocumentsTabState extends State<DocumentsTab> {
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
      setState(() => _loading = false);
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final rows = await widget.tasks.listDocuments(widget.session);
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

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text('Document access is not included in your company plan.'),
        ),
      );
    }

    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    return RefreshIndicator(
      onRefresh: _load,
      child: _items.isEmpty && _error == null
          ? ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              children: [
                const SizedBox(height: 48),
                Icon(Icons.folder_open_outlined, size: 56, color: Theme.of(context).colorScheme.outline),
                const SizedBox(height: 16),
                Text(
                  'Keine Dokumente hinterlegt',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 32),
                  child: Text(
                    'Dein Arbeitgeber kann Nachweise hier bereitstellen. Bei Fragen: BauPass Assistent auf der Startseite.',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                  ),
                ),
              ],
            )
          : ListView(
              padding: const EdgeInsets.all(12),
              children: [
                if (widget.onOpenDeploymentPlan != null)
                  Card(
                    color: Theme.of(context).colorScheme.primaryContainer,
                    child: ListTile(
                      leading: const Icon(Icons.calendar_month),
                      title: const Text('Monatsplan in der App'),
                      subtitle: const Text(
                        'Tage ansehen, ablehnen — nicht nur PDF herunterladen.',
                      ),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: widget.onOpenDeploymentPlan,
                    ),
                  ),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                  ),
                ..._items.map((row) {
                  final expiry = row['expiry_date'] as String?;
                  final docType = (row['doc_type'] as String? ?? '').toLowerCase();
                  final isPlan = docType == 'einsatzplan';
                  return Card(
                    child: ListTile(
                      leading: Icon(isPlan ? Icons.event_note : Icons.description_outlined),
                      title: Text(row['filename'] as String? ?? row['doc_type'] as String? ?? 'Document'),
                      subtitle: Text(
                        [
                          row['doc_type'],
                          if (row['created_at'] != null) 'Hochgeladen: ${row['created_at']}',
                          if (expiry != null && expiry.isNotEmpty) 'Läuft ab: $expiry',
                        ].whereType<String>().join(' · '),
                      ),
                      isThreeLine: true,
                      trailing: isPlan && widget.onOpenDeploymentPlan != null
                          ? TextButton(
                              onPressed: widget.onOpenDeploymentPlan,
                              child: const Text('Öffnen'),
                            )
                          : null,
                    ),
                  );
                }),
              ],
            ),
    );
  }
}
