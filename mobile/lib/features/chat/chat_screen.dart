import 'dart:io';
import 'dart:async';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:open_file/open_file.dart';
import 'package:path_provider/path_provider.dart';

import '../../core/session_store.dart';
import '../../services/chat_repository.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.session,
    required this.chat,
  });

  final WorkerSession session;
  final ChatRepository chat;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final TextEditingController _message = TextEditingController();
  bool _loading = true;
  bool _sending = false;
  String? _threadId;
  List<Map<String, dynamic>> _messages = <Map<String, dynamic>>[];
  bool _silentRefresh = false;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _boot();
    _pollTimer = Timer.periodic(const Duration(seconds: 8), (_) {
      if (!_sending && !_silentRefresh && mounted) {
        _boot(silent: true);
      }
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _message.dispose();
    super.dispose();
  }

  Future<void> _boot({bool silent = false}) async {
    if (!silent) {
      setState(() => _loading = true);
    } else {
      _silentRefresh = true;
    }
    try {
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
      if (_messages.isNotEmpty && mounted) {
        WidgetsBinding.instance.addPostFrameCallback((_) {});
      }
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    } finally {
      _silentRefresh = false;
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
      setState(() {
        _messages = [..._messages, msg];
      });
      await _boot(silent: true);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _attach() async {
    final threadId = _threadId;
    if (threadId == null || _sending) return;
    final picked = await FilePicker.platform.pickFiles(withData: false);
    if (picked == null || picked.files.isEmpty) return;
    final file = picked.files.single.path;
    if (file == null || file.isEmpty) return;
    setState(() => _sending = true);
    try {
      final res = await widget.chat.sendMessage(
        session: widget.session,
        threadId: threadId,
        body: _message.text.trim().isEmpty ? 'Anhang gesendet' : _message.text.trim(),
      );
      final msg = Map<String, dynamic>.from(res['message'] as Map);
      await widget.chat.uploadAttachment(
        session: widget.session,
        threadId: threadId,
        messageId: msg['id'] as String,
        file: File(file),
      );
      _message.clear();
      await _boot(silent: true);
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
    await _saveAndOpenFile(bytes, filename: filename);
  }

  Future<void> _saveAndOpenFile(Uint8List bytes, {required String filename}) async {
    final dir = await getTemporaryDirectory();
    final file = File('${dir.path}/$filename');
    await file.writeAsBytes(bytes, flush: true);
    await OpenFile.open(file.path);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Chat mit Firma'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _boot,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              children: [
                Expanded(
                  child: _messages.isEmpty
                      ? const Center(child: Text('Noch keine Nachrichten'))
                      : ListView.builder(
                          padding: const EdgeInsets.all(16),
                          itemCount: _messages.length,
                          itemBuilder: (context, index) {
                            final item = _messages[index];
                            final isWorker = item['senderType'] == 'worker';
                            final attachments = (item['attachments'] as List?) ?? const [];
                            return Align(
                              alignment: isWorker ? Alignment.centerRight : Alignment.centerLeft,
                              child: Container(
                                margin: const EdgeInsets.only(bottom: 12),
                                padding: const EdgeInsets.all(12),
                                constraints: const BoxConstraints(maxWidth: 320),
                                decoration: BoxDecoration(
                                  color: isWorker
                                      ? Theme.of(context).colorScheme.primaryContainer
                                      : Theme.of(context).colorScheme.surfaceContainerHighest,
                                  borderRadius: BorderRadius.circular(16),
                                ),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      isWorker ? 'Du' : 'Firma',
                                      style: Theme.of(context).textTheme.labelMedium?.copyWith(
                                            fontWeight: FontWeight.w700,
                                          ),
                                    ),
                                    const SizedBox(height: 4),
                                    Text(item['body'] as String? ?? ''),
                                    if (attachments.isNotEmpty) ...[
                                      const SizedBox(height: 8),
                                      ...attachments.map((att) {
                                        final map = Map<String, dynamic>.from(att as Map);
                                        return InkWell(
                                          onTap: () => _openAttachment(map),
                                          child: Padding(
                                            padding: const EdgeInsets.only(top: 4),
                                            child: Text('📎 ${map['filename'] ?? 'Anhang'}'),
                                          ),
                                        );
                                      }),
                                    ],
                                  ],
                                ),
                              ),
                            );
                          },
                        ),
                ),
                SafeArea(
                  top: false,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
                    child: Row(
                      children: [
                        IconButton(
                          onPressed: _sending ? null : _attach,
                          icon: const Icon(Icons.attach_file),
                        ),
                        Expanded(
                          child: TextField(
                            controller: _message,
                            minLines: 1,
                            maxLines: 4,
                            decoration: const InputDecoration(
                              hintText: 'Nachricht schreiben…',
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        FilledButton(
                          onPressed: _sending ? null : _send,
                          child: const Text('Senden'),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}
