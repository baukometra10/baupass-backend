import 'package:flutter/material.dart';

import '../../core/tenant_branding.dart';
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
  String? _busyId;

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

  Future<void> _openDocument(Map<String, dynamic> row) async {
    final id = row['id'] as String?;
    if (id == null || id.isEmpty) return;
    setState(() => _busyId = id);
    try {
      final bytes = await widget.tasks.downloadDocument(widget.session, id);
      final filename = (row['filename'] as String?)?.trim().isNotEmpty == true
          ? row['filename'] as String
          : 'dokument.pdf';
      await widget.tasks.saveAndOpenPdf(bytes, filename: filename);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Öffnen fehlgeschlagen: $e')),
      );
    } finally {
      if (mounted) setState(() => _busyId = null);
    }
  }

  Future<void> _acknowledge(Map<String, dynamic> row) async {
    final id = row['id'] as String?;
    if (id == null || id.isEmpty) return;
    setState(() => _busyId = id);
    try {
      await widget.tasks.acknowledgeDocument(widget.session, id);
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Als gelesen bestätigt')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Bestätigung fehlgeschlagen: $e')),
      );
    } finally {
      if (mounted) setState(() => _busyId = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final branding = TenantBrandingScope.of(context);
    final aiHint = '${branding.aiAssistantTitle} auf der Startseite.';
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
                    'Dein Arbeitgeber kann Nachweise hier bereitstellen. Bei Fragen: $aiHint',
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
                  final id = row['id'] as String? ?? '';
                  final expiry = row['expiry_date'] as String?;
                  final docType = (row['doc_type'] as String? ?? '').toLowerCase();
                  final isPlan = docType == 'einsatzplan';
                  final acknowledged = row['acknowledged'] == true;
                  final fromEditor = (row['source'] as String? ?? '') == 'editor' ||
                      ((row['editorDocumentId'] as String?)?.isNotEmpty ?? false);
                  final busy = _busyId == id;
                  return Card(
                    child: ListTile(
                      leading: busy
                          ? const SizedBox(
                              width: 24,
                              height: 24,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : Icon(isPlan ? Icons.event_note : Icons.description_outlined),
                      title: Text(row['filename'] as String? ?? row['label'] as String? ?? row['doc_type'] as String? ?? 'Document'),
                      subtitle: Text(
                        [
                          row['label'] ?? row['doc_type'],
                          if (row['created_at'] != null) 'Hochgeladen: ${row['created_at']}',
                          if (expiry != null && expiry.isNotEmpty) 'Läuft ab: $expiry',
                          if (fromEditor) 'Aus Docs-Editor',
                          if (acknowledged) 'Gelesen ✓',
                        ].whereType<String>().join(' · '),
                      ),
                      isThreeLine: true,
                      onTap: busy
                          ? null
                          : () {
                              if (isPlan && widget.onOpenDeploymentPlan != null) {
                                widget.onOpenDeploymentPlan!();
                              } else {
                                _openDocument(row);
                              }
                            },
                      trailing: isPlan && widget.onOpenDeploymentPlan != null
                          ? TextButton(
                              onPressed: widget.onOpenDeploymentPlan,
                              child: const Text('Öffnen'),
                            )
                          : Wrap(
                              spacing: 4,
                              children: [
                                IconButton(
                                  tooltip: 'Öffnen',
                                  onPressed: busy ? null : () => _openDocument(row),
                                  icon: const Icon(Icons.open_in_new),
                                ),
                                if (!acknowledged)
                                  TextButton(
                                    onPressed: busy ? null : () => _acknowledge(row),
                                    child: const Text('Gelesen'),
                                  ),
                              ],
                            ),
                    ),
                  );
                }),
              ],
            ),
    );
  }
}
