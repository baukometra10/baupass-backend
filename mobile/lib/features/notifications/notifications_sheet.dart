import 'package:flutter/material.dart';

import '../../core/app_strings.dart';
import '../../core/locale_controller.dart';
import '../../core/session_store.dart';
import '../../core/worker_datetime_format.dart';
import '../../services/tasks_repository.dart';

/// In-app Mitteilungen (server notifications).
class NotificationsSheet extends StatefulWidget {
  const NotificationsSheet({
    super.key,
    required this.session,
    required this.tasks,
    this.onOpenDeployment,
    this.onOpenDocuments,
    this.onOpenChat,
  });

  final WorkerSession session;
  final TasksRepository tasks;
  final VoidCallback? onOpenDeployment;
  final VoidCallback? onOpenDocuments;
  final VoidCallback? onOpenChat;

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

  Future<void> _markRead(Map<String, dynamic> item) async {
    final id = item['id'] as String?;
    if (id == null || id.isEmpty) return;
    try {
      await widget.tasks.markNotificationRead(widget.session, id);
    } catch (_) {
      // ignore
    }
  }

  void _handleTap(Map<String, dynamic> item) async {
    await _markRead(item);
    if (!mounted) return;
    Navigator.pop(context);
    final action = (item['actionUrl'] as String? ?? '').toLowerCase();
    final type = (item['type'] as String? ?? '').toLowerCase();
    if (action.contains('chat') ||
        action.contains('worker-chat') ||
        type.contains('chat') ||
        type.contains('message')) {
      widget.onOpenChat?.call();
    } else if (action.contains('deployment') || action.contains('einsatzplan')) {
      widget.onOpenDeployment?.call();
    } else if (action.contains('document') || action.contains('leave')) {
      widget.onOpenDocuments?.call();
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: LocaleController.instance,
      builder: (context, _) {
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
                          t('notifications', 'Mitteilungen'),
                          style: Theme.of(context).textTheme.titleLarge,
                        ),
                        if (unread > 0) ...[
                          const SizedBox(width: 8),
                          Chip(
                            label: Text(t('notificationsNew', '{n} neu').replaceAll('{n}', '$unread')),
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
                            ? Center(child: Text(t('notificationsEmpty', 'Keine Mitteilungen')))
                            : ListView.builder(
                                controller: scrollController,
                                itemCount: _items.length,
                                itemBuilder: (context, index) {
                                  final item = _items[index];
                                  final read = item['isRead'] == true;
                                  final when = formatDateTimeLocal(item['createdAt'] as String?);
                                  final body = (item['message'] as String? ?? '').trim();
                                  return ListTile(
                                    title: Text(
                                      item['title'] as String? ?? t('notifications', 'Mitteilung'),
                                      style: TextStyle(
                                        fontWeight: read ? FontWeight.normal : FontWeight.w700,
                                      ),
                                    ),
                                    subtitle: Text(
                                      [
                                        if (body.isNotEmpty) body,
                                        if (when.isNotEmpty) when,
                                      ].join('\n'),
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
      },
    );
  }
}
