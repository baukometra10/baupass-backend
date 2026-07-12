import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:open_file/open_file.dart';
import 'package:path_provider/path_provider.dart';

import '../core/api_client.dart';
import '../core/session_store.dart';
import '../core/tenant_branding.dart';
import '../services/chat_repository.dart';

/// Kompakter Chat auf dem Start-Tab (wie PWA home-chat-card).
class WorkerHomeChatPanel extends StatefulWidget {
  const WorkerHomeChatPanel({
    super.key,
    required this.session,
    required this.chat,
    this.onOpenFullScreen,
  });

  final WorkerSession session;
  final ChatRepository chat;
  final VoidCallback? onOpenFullScreen;

  @override
  State<WorkerHomeChatPanel> createState() => _WorkerHomeChatPanelState();
}

class _WorkerHomeChatPanelState extends State<WorkerHomeChatPanel> {
  final TextEditingController _message = TextEditingController();
  bool _loading = true;
  bool _sending = false;
  String? _threadId;
  List<Map<String, dynamic>> _messages = <Map<String, dynamic>>[];
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _load();
    _pollTimer = Timer.periodic(const Duration(seconds: 10), (_) {
      if (!_sending && mounted) _load(silent: true);
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _message.dispose();
    super.dispose();
  }

  Future<void> _load({bool silent = false}) async {
    if (!silent) setState(() => _loading = true);
    try {
      await widget.chat.ensureE2eReady(widget.session);
      final threads = await widget.chat.listThreads(widget.session);
      String threadId;
      if (threads.isNotEmpty) {
        threadId = threads.first['id'] as String;
      } else {
        threadId = await widget.chat.ensureThread(widget.session);
      }
      final messages = await widget.chat.listMessages(widget.session, threadId);
      if (!mounted) return;
      setState(() {
        _threadId = threadId;
        _messages = messages;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  Future<void> _send() async {
    final threadId = _threadId;
    final body = _message.text.trim();
    if (threadId == null || body.isEmpty || _sending) return;
    setState(() => _sending = true);
    try {
      final res = await widget.chat.sendMessage(
        session: widget.session,
        threadId: threadId,
        body: body,
      );
      _message.clear();
      final msg = Map<String, dynamic>.from(res['message'] as Map);
      if (!mounted) return;
      setState(() => _messages = [..._messages, msg]);
      await _load(silent: true);
    } on StateError catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            e.message == 'e2e_keys_missing'
                ? 'Chat-Verschlüsselung nicht bereit.'
                : e.toString(),
          ),
        ),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.message ?? e.toString())),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Senden fehlgeschlagen: $e')),
      );
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _attach() async {
    final threadId = _threadId;
    if (threadId == null || _sending) return;
    final picked = await FilePicker.platform.pickFiles(withData: false);
    if (picked == null || picked.files.isEmpty) return;
    final path = picked.files.single.path;
    if (path == null || path.isEmpty) return;
    setState(() => _sending = true);
    try {
      final res = await widget.chat.sendMessage(
        session: widget.session,
        threadId: threadId,
        body: _message.text.trim().isEmpty ? 'Unterlage gesendet' : _message.text.trim(),
      );
      final msg = Map<String, dynamic>.from(res['message'] as Map);
      await widget.chat.uploadAttachment(
        session: widget.session,
        threadId: threadId,
        messageId: msg['id'] as String,
        file: File(path),
      );
      _message.clear();
      await _load(silent: true);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _openAttachment(Map<String, dynamic> attachment) async {
    final id = attachment['id'] as String?;
    final filename = attachment['filename'] as String? ?? 'attachment.bin';
    if (id == null || id.isEmpty) return;
    final bytes = await widget.chat.downloadAttachment(
      session: widget.session,
      attachmentId: id,
    );
    final dir = await getTemporaryDirectory();
    final file = File('${dir.path}/$filename');
    await file.writeAsBytes(bytes, flush: true);
    await OpenFile.open(file.path);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final branding = TenantBrandingScope.of(context);
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: theme.colorScheme.outlineVariant),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Text(
                  branding.chatTitle,
                  style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
                ),
                const Spacer(),
                if (widget.onOpenFullScreen != null)
                  TextButton(
                    onPressed: widget.onOpenFullScreen,
                    child: const Text('Vollbild'),
                  ),
                IconButton(
                  tooltip: 'Aktualisieren',
                  onPressed: _load,
                  icon: const Icon(Icons.refresh, size: 20),
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (_loading)
              const SizedBox(
                height: 120,
                child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
              )
            else if (_messages.isEmpty)
              SizedBox(
                height: 72,
                child: Center(
                  child: Text(
                    'Noch keine Nachrichten',
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
              )
            else
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 220),
                child: ListView.builder(
                  shrinkWrap: true,
                  itemCount: _messages.length,
                  itemBuilder: (context, index) {
                    final item = _messages[index];
                    final isWorker = item['senderType'] == 'worker';
                    final attachments = (item['attachments'] as List?) ?? const [];
                    return Align(
                      alignment: isWorker ? Alignment.centerRight : Alignment.centerLeft,
                      child: Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        constraints: const BoxConstraints(maxWidth: 280),
                        decoration: BoxDecoration(
                          color: isWorker
                              ? theme.colorScheme.primaryContainer
                              : theme.colorScheme.surfaceContainerHighest,
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              isWorker ? 'Du' : branding.displayName,
                              style: theme.textTheme.labelSmall?.copyWith(fontWeight: FontWeight.w700),
                            ),
                            const SizedBox(height: 2),
                            Text(item['body'] as String? ?? ''),
                            if (attachments.isNotEmpty)
                              ...attachments.map((att) {
                                final map = Map<String, dynamic>.from(att as Map);
                                return InkWell(
                                  onTap: () => _openAttachment(map),
                                  child: Padding(
                                    padding: const EdgeInsets.only(top: 4),
                                    child: Text(
                                      '📎 ${map['filename'] ?? 'Anhang'}',
                                      style: theme.textTheme.bodySmall?.copyWith(
                                        decoration: TextDecoration.underline,
                                      ),
                                    ),
                                  ),
                                );
                              }),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
            const SizedBox(height: 10),
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                IconButton(
                  onPressed: _sending ? null : _attach,
                  icon: const Icon(Icons.attach_file),
                ),
                Expanded(
                  child: TextField(
                    controller: _message,
                    minLines: 1,
                    maxLines: 3,
                    decoration: const InputDecoration(
                      hintText: 'Nachricht schreiben…',
                      isDense: true,
                      border: OutlineInputBorder(),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: _sending ? null : _send,
                  child: _sending
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Senden'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
