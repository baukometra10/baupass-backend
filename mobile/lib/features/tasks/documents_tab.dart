import 'package:flutter/material.dart';

import '../../core/session_store.dart';
import '../../services/tasks_repository.dart';

class DocumentsTab extends StatefulWidget {
  const DocumentsTab({
    super.key,
    required this.session,
    required this.tasks,
    required this.enabled,
  });

  final WorkerSession session;
  final TasksRepository tasks;
  final bool enabled;

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
              children: const [
                SizedBox(height: 80),
                Center(child: Text('No documents on file.')),
              ],
            )
          : ListView(
              padding: const EdgeInsets.all(12),
              children: [
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                  ),
                ..._items.map((row) {
                  final expiry = row['expiry_date'] as String?;
                  return Card(
                    child: ListTile(
                      leading: const Icon(Icons.description_outlined),
                      title: Text(row['filename'] as String? ?? row['doc_type'] as String? ?? 'Document'),
                      subtitle: Text(
                        [
                          row['doc_type'],
                          if (row['created_at'] != null) 'Uploaded: ${row['created_at']}',
                          if (expiry != null && expiry.isNotEmpty) 'Expires: $expiry',
                        ].whereType<String>().join(' · '),
                      ),
                      isThreeLine: true,
                    ),
                  );
                }),
              ],
            ),
    );
  }
}
