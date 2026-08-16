import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_client.dart';
import '../../core/session_store.dart';
import '../../services/tasks_repository.dart';

class ContractsTab extends StatefulWidget {
  const ContractsTab({
    super.key,
    required this.session,
    required this.tasks,
    required this.enabled,
  });

  final WorkerSession session;
  final TasksRepository tasks;
  final bool enabled;

  @override
  State<ContractsTab> createState() => _ContractsTabState();
}

class _ContractsTabState extends State<ContractsTab> {
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
      final rows = await widget.tasks.listEmploymentContracts(widget.session);
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

  Future<void> _openSignUrl(String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  bool _canView(Map<String, dynamic> row) {
    if (row.containsKey('canView')) return row['canView'] == true;
    if (row.containsKey('canDownload')) return row['canDownload'] == true;
    return true;
  }

  String _filename(Map<String, dynamic> row) {
    final raw = (row['filename'] as String?)?.trim();
    if (raw != null && raw.isNotEmpty) return raw;
    final id = (row['id'] ?? 'vertrag').toString();
    return 'arbeitsvertrag-$id.pdf';
  }

  Future<void> _openOrDownload(
    Map<String, dynamic> row, {
    required bool download,
  }) async {
    final id = (row['id'] ?? '').toString();
    if (id.isEmpty) return;
    if (!_canView(row)) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Vertrag ist noch nicht zum Lesen bereit.'),
        ),
      );
      return;
    }
    setState(() => _busyId = id);
    try {
      final bytes = await widget.tasks.downloadEmploymentContract(
        widget.session,
        id,
        asAttachment: download,
      );
      await widget.tasks.saveAndOpenPdf(bytes, filename: _filename(row));
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            download
                ? 'Arbeitsvertrag gespeichert und geöffnet.'
                : 'Arbeitsvertrag geöffnet.',
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      final msg = e is ApiException ? e.friendlyMessage : e.toString();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('PDF fehlgeschlagen: $msg')),
      );
    } finally {
      if (mounted) setState(() => _busyId = null);
    }
  }

  String _statusLabel(Map<String, dynamic> row) {
    final st = (row['signStatus'] ?? row['status'] ?? 'draft').toString();
    switch (st) {
      case 'fully_signed':
        return 'Signiert';
      case 'partially_signed':
        return 'Teilweise signiert';
      case 'awaiting_signature':
        return 'Wartet auf Signatur';
      case 'ready':
      case 'final':
        return 'Bereit';
      default:
        return 'Entwurf';
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text('Arbeitsverträge sind in Ihrem Tarif nicht enthalten.'),
        ),
      );
    }
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: _items.isEmpty
          ? ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              children: [
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Text(
                      _error!,
                      style: const TextStyle(color: Colors.redAccent),
                    ),
                  ),
                const SizedBox(height: 120),
                const Center(child: Text('Keine Arbeitsverträge')),
              ],
            )
          : ListView.separated(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(12),
              itemCount: _items.length + 1,
              separatorBuilder: (_, __) => const SizedBox(height: 8),
              itemBuilder: (context, index) {
                if (index == 0) {
                  return Card(
                    color: Theme.of(context).colorScheme.surfaceContainerHighest,
                    child: const Padding(
                      padding: EdgeInsets.all(12),
                      child: Text(
                        'Tippen Sie auf einen Vertrag, um ihn vollständig zu lesen. '
                        'Sie können ihn öffnen und herunterladen.',
                        style: TextStyle(fontSize: 13),
                      ),
                    ),
                  );
                }
                final row = _items[index - 1];
                final title =
                    (row['title'] ?? row['id'] ?? 'Vertrag').toString();
                final needs = row['needsSignature'] == true;
                final signUrl = (row['signUrl'] ?? '').toString();
                final id = (row['id'] ?? '').toString();
                final busy = _busyId == id;
                final canView = _canView(row);
                return Card(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(12, 8, 8, 8),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text(
                            title,
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                          subtitle: Text(
                            [
                              _statusLabel(row),
                              if (!canView) 'Noch kein PDF/Text',
                              if (canView) 'Vollständig lesbar',
                            ].join(' · '),
                          ),
                          trailing: busy
                              ? const SizedBox(
                                  width: 28,
                                  height: 28,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : Icon(
                                  Icons.picture_as_pdf_outlined,
                                  color: canView
                                      ? Theme.of(context).colorScheme.primary
                                      : Theme.of(context).disabledColor,
                                ),
                          onTap: busy || !canView
                              ? null
                              : () => _openOrDownload(row, download: false),
                        ),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            FilledButton.tonalIcon(
                              onPressed: busy || !canView
                                  ? null
                                  : () =>
                                      _openOrDownload(row, download: false),
                              icon: const Icon(Icons.visibility_outlined),
                              label: const Text('Lesen'),
                            ),
                            OutlinedButton.icon(
                              onPressed: busy || !canView
                                  ? null
                                  : () =>
                                      _openOrDownload(row, download: true),
                              icon: const Icon(Icons.download_outlined),
                              label: const Text('Herunterladen'),
                            ),
                            if (needs && signUrl.isNotEmpty)
                              FilledButton(
                                onPressed: busy
                                    ? null
                                    : () => _openSignUrl(signUrl),
                                child: const Text('Unterschreiben'),
                              ),
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
    );
  }
}
