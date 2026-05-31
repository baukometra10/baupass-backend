import 'package:flutter/material.dart';

import '../../core/session_store.dart';
import '../../services/tasks_repository.dart';

/// In-app Mitteilungen (server notifications).
class NotificationsSheet extends StatefulWidget {
  const NotificationsSheet({
    super.key,
    required this.session,
    required this.tasks,
    this.onOpenDeployment,
    this.onOpenDocuments,
  });

  final WorkerSession session;
  final TasksRepository tasks;
  final VoidCallback? onOpenDeployment;
  final VoidCallback? onOpenDocuments;

  @override
  State<NotificationsSheet> createState() => _NotificationsSheetState();
}

class _NotificationsSheetState extends State<NotificationsSheet> {
  bool _loading = true;
  List<Map<String, dynamic>> _items = <Map<String, dynamic>>[];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final rows = await widget.tasks.listNotifications(widget.session);
      if (!mounted) return;
      setState(() {
        _items = rows;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  void _handleTap(Map<String, dynamic> item) async {
    final id = item['id'] as String?;
    if (id != null && id.isNotEmpty) {
      try {
        await widget.tasks.markNotificationRead(widget.session, id);
      } catch (_) {
        // ignore
      }
    }
    if (!mounted) return;
    Navigator.pop(context);
    final action = (item['actionUrl'] as String? ?? '').toLowerCase();
    if (action.contains('deployment') || action.contains('einsatzplan')) {
      widget.onOpenDeployment?.call();
    } else if (action.contains('document') || action.contains('leave')) {
      widget.onOpenDocuments?.call();
    }
  }

  @override
  Widget build(BuildContext context) {
    final unread = _items.where((i) => i['isRead'] != true).length;
    return DraggableScrollableSheet(
      initialChildSize: 0.55,
      minChildSize: 0.35,
      maxChildSize: 0.92,
      expand: false,
      builder: (context, scrollController) {
        return Material(
          borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
          child: Column(
            children: [
              const SizedBox(height: 8),
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.outlineVariant,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
                child: Row(
                  children: [
                    Text(
                      'Mitteilungen',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    if (unread > 0) ...[
                      const SizedBox(width: 8),
                      Chip(
                        label: Text('$unread neu'),
                        visualDensity: VisualDensity.compact,
                      ),
                    ],
                    const Spacer(),
                    IconButton(
                      icon: const Icon(Icons.refresh),
                      onPressed: _load,
                    ),
                  ],
                ),
              ),
              const Divider(height: 1),
              Expanded(
                child: _loading
                    ? const Center(child: CircularProgressIndicator())
                    : _items.isEmpty
                        ? const Center(child: Text('Keine Mitteilungen'))
                        : ListView.builder(
                            controller: scrollController,
                            itemCount: _items.length,
                            itemBuilder: (context, index) {
                              final item = _items[index];
                              final read = item['isRead'] == true;
                              return ListTile(
                                title: Text(
                                  item['title'] as String? ?? 'Mitteilung',
                                  style: TextStyle(
                                    fontWeight: read ? FontWeight.normal : FontWeight.w700,
                                  ),
                                ),
                                subtitle: Text(
                                  [
                                    item['message'] as String? ?? '',
                                    item['createdAt'] as String? ?? '',
                                  ].where((s) => s.toString().trim().isNotEmpty).join('\n'),
                                ),
                                onTap: () => _handleTap(item),
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
