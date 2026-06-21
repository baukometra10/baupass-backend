import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

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
                    child: Text(_error!, style: const TextStyle(color: Colors.redAccent)),
                  ),
                const SizedBox(height: 120),
                const Center(child: Text('Keine Arbeitsverträge')),
              ],
            )
          : ListView.separated(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(12),
              itemCount: _items.length,
              separatorBuilder: (_, __) => const SizedBox(height: 8),
              itemBuilder: (context, index) {
                final row = _items[index];
                final title = (row['title'] ?? row['id'] ?? 'Vertrag').toString();
                final needs = row['needsSignature'] == true;
                final signUrl = (row['signUrl'] ?? '').toString();
                return Card(
                  child: ListTile(
                    title: Text(title),
                    subtitle: Text(_statusLabel(row)),
                    trailing: needs && signUrl.isNotEmpty
                        ? FilledButton(
                            onPressed: () => _openSignUrl(signUrl),
                            child: const Text('Unterschreiben'),
                          )
                        : null,
                    onTap: needs && signUrl.isNotEmpty ? () => _openSignUrl(signUrl) : null,
                  ),
                );
              },
            ),
    );
  }
}
