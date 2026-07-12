import 'dart:io';
import 'dart:async';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:open_file/open_file.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import '../../core/api_client.dart';
import '../../core/session_store.dart';
import '../../core/tenant_branding.dart';
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
  final AudioRecorder _recorder = AudioRecorder();
  bool _loading = true;
  bool _sending = false;
  bool _recording = false;
  String? _threadId;
  String? _recordPath;
  DateTime? _recordStartedAt;
  List<Map<String, dynamic>> _messages = <Map<String, dynamic>>[];
  bool _silentRefresh = false;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _message.addListener(_onComposeChanged);
    _boot();
    _pollTimer = Timer.periodic(const Duration(seconds: 8), (_) {
      if (!_sending && !_silentRefresh && !_recording && mounted) {
        _boot(silent: true);
      }
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _message.removeListener(_onComposeChanged);
    _message.dispose();
    _recorder.dispose();
    super.dispose();
  }

  void _onComposeChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _boot({bool silent = false}) async {
    if (!silent) {
      setState(() => _loading = true);
    } else {
      _silentRefresh = true;
    }
    try {
      await widget.chat.ensureE2eReady(widget.session);
      final threadId = await widget.chat.resolveThread(widget.session);
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
    } on StateError catch (e) {
      if (!mounted) return;
      final text = e.message == 'e2e_keys_missing'
          ? 'Chat-Verschlüsselung nicht bereit — Admin muss E2E-Schlüssel hinterlegen.'
          : e.toString();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(text), duration: const Duration(seconds: 6)),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      final text = e.errorCode == 'e2e_required'
          ? 'Verschlüsselter Chat erforderlich — bitte kurz warten und erneut senden.'
          : (e.message ?? e.toString());
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(text), duration: const Duration(seconds: 6)),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Nachricht fehlgeschlagen: $e')),
      );
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _sendVoiceFile(String filePath, {int? durationSec}) async {
    final threadId = _threadId;
    if (threadId == null || _sending) return;
    final file = File(filePath);
    if (!await file.exists()) return;
    setState(() => _sending = true);
    try {
      final res = await widget.chat.sendMessage(
        session: widget.session,
        threadId: threadId,
        body: 'Sprachnachricht',
      );
      final msg = Map<String, dynamic>.from(res['message'] as Map);
      await widget.chat.uploadAttachment(
        session: widget.session,
        threadId: threadId,
        messageId: msg['id'] as String,
        file: file,
        durationSec: durationSec,
      );
      if (!mounted) return;
      setState(() {
        _messages = [..._messages, msg];
      });
      await _boot(silent: true);
    } finally {
      if (mounted) setState(() => _sending = false);
      try {
        await file.delete();
      } catch (_) {
        /* ignore */
      }
    }
  }

  Future<void> _toggleVoice() async {
    if (_sending) return;
    if (!_recording) {
      if (!await _recorder.hasPermission()) {
        if (!context.mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Mikrofon-Berechtigung erforderlich. Bitte in den iPhone-Einstellungen für die Mitarbeiter-App erlauben.',
            ),
          ),
        );
        return;
      }
      final dir = await getTemporaryDirectory();
      _recordPath = '${dir.path}/voice_${DateTime.now().millisecondsSinceEpoch}.m4a';
      await _recorder.start(
        const RecordConfig(encoder: AudioEncoder.aacLc, sampleRate: 16000),
        path: _recordPath!,
      );
      if (!mounted) return;
      setState(() {
        _recording = true;
        _recordStartedAt = DateTime.now();
      });
      return;
    }

    final path = await _recorder.stop();
    if (!mounted) return;
    final startedAt = _recordStartedAt;
    setState(() {
      _recording = false;
      _recordStartedAt = null;
    });
    final filePath = path ?? _recordPath;
    _recordPath = null;
    if (filePath == null || filePath.isEmpty) return;
    final elapsed = startedAt == null ? Duration.zero : DateTime.now().difference(startedAt);
    if (elapsed < const Duration(milliseconds: 800)) {
      try {
        await File(filePath).delete();
      } catch (_) {
        /* ignore */
      }
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Aufnahme zu kurz — bitte erneut versuchen.')),
      );
      return;
    }
    await _sendVoiceFile(filePath, durationSec: elapsed.inSeconds.clamp(1, 3600));
  }

  Future<void> _attach() async {
    final threadId = _threadId;
    if (threadId == null || _sending || _recording) return;
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
    final e2eMeta = attachment['e2eMeta'] as String? ?? attachment['e2e_meta'] as String?;
    if (id == null || id.isEmpty) return;
    final bytes = await widget.chat.downloadAttachment(
      session: widget.session,
      attachmentId: id,
      e2eMeta: e2eMeta,
      filename: filename,
    );
    await _saveAndOpenFile(bytes, filename: filename);
  }

  Future<void> _saveAndOpenFile(Uint8List bytes, {required String filename}) async {
    final dir = await getTemporaryDirectory();
    final file = File('${dir.path}/$filename');
    await file.writeAsBytes(bytes, flush: true);
    await OpenFile.open(file.path);
  }

  bool _isWorkerMessage(Map<String, dynamic> item) {
    final sender = (item['senderType'] ?? item['sender_type'] ?? '').toString().toLowerCase();
    return sender == 'worker';
  }

  bool _isAudioAttachment(Map<String, dynamic> attachment) {
    final contentType = (attachment['contentType'] ?? attachment['content_type'] ?? '')
        .toString()
        .toLowerCase();
    final filename = (attachment['filename'] ?? '').toString().toLowerCase();
    if (contentType.startsWith('audio/')) return true;
    return filename.endsWith('.m4a')
        || filename.endsWith('.mp4')
        || filename.endsWith('.wav')
        || filename.endsWith('.webm')
        || filename.endsWith('.aac');
  }

  bool _isVoiceOnlyBody(String? body) {
    final text = (body ?? '').trim().toLowerCase();
    if (text.isEmpty) return true;
    return text == 'sprachnachricht'
        || text.contains('voice message')
        || text.startsWith('🎤');
  }

  String _readStatusLabel(Map<String, dynamic> item) {
    if (!_isWorkerMessage(item)) return '';
    final read = item['readByRecipient'] == true || item['read_by_recipient'] == true;
    return read ? '✓✓ Gelesen' : '✓ Zugestellt';
  }

  String _formatTime(String? raw) {
    if (raw == null || raw.trim().isEmpty) return '';
    final date = DateTime.tryParse(raw);
    if (date == null) return '';
    final h = date.hour.toString().padLeft(2, '0');
    final m = date.minute.toString().padLeft(2, '0');
    return '$h:$m';
  }

  Widget _buildPrimaryAction() {
    final hasText = _message.text.trim().isNotEmpty;
    if (_recording) {
      return FilledButton(
        onPressed: _sending ? null : _toggleVoice,
        style: FilledButton.styleFrom(
          backgroundColor: const Color(0xFFEA4335),
          minimumSize: const Size(52, 52),
          padding: EdgeInsets.zero,
          shape: const CircleBorder(),
        ),
        child: const Icon(Icons.stop),
      );
    }
    if (!hasText) {
      return FilledButton(
        onPressed: _sending ? null : _toggleVoice,
        style: FilledButton.styleFrom(
          backgroundColor: const Color(0xFF00A884),
          minimumSize: const Size(52, 52),
          padding: EdgeInsets.zero,
          shape: const CircleBorder(),
        ),
        child: const Icon(Icons.mic),
      );
    }
    return FilledButton(
      onPressed: _sending ? null : _send,
      child: const Text('Senden'),
    );
  }

  @override
  Widget build(BuildContext context) {
    final branding = TenantBrandingScope.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(branding.chatTitle),
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
                            final isWorker = _isWorkerMessage(item);
                            final attachments = (item['attachments'] as List?) ?? const [];
                            final audioAttachments = attachments
                                .map((att) => Map<String, dynamic>.from(att as Map))
                                .where(_isAudioAttachment)
                                .toList();
                            final showBody = !_isVoiceOnlyBody(item['body'] as String?)
                                || audioAttachments.isEmpty;
                            final read = item['readByRecipient'] == true || item['read_by_recipient'] == true;
                            final readLabel = _readStatusLabel(item);
                            final timeLabel = _formatTime(item['createdAt'] as String?);
                            return Padding(
                              padding: const EdgeInsets.only(bottom: 10),
                              child: Row(
                                mainAxisAlignment:
                                    isWorker ? MainAxisAlignment.end : MainAxisAlignment.start,
                                crossAxisAlignment: CrossAxisAlignment.end,
                                children: [
                                  Flexible(
                                    child: ConstrainedBox(
                                      constraints: BoxConstraints(
                                        maxWidth: MediaQuery.sizeOf(context).width * 0.78,
                                      ),
                                      child: Container(
                                        padding: const EdgeInsets.fromLTRB(12, 10, 12, 8),
                                        decoration: BoxDecoration(
                                          color: isWorker
                                              ? const Color(0xFFDBEAFE)
                                              : Colors.white,
                                          borderRadius: BorderRadius.only(
                                            topLeft: const Radius.circular(18),
                                            topRight: const Radius.circular(18),
                                            bottomLeft: Radius.circular(isWorker ? 18 : 6),
                                            bottomRight: Radius.circular(isWorker ? 6 : 18),
                                          ),
                                          border: Border.all(
                                            color: isWorker
                                                ? const Color(0xFF93C5FD)
                                                : Theme.of(context).colorScheme.outlineVariant,
                                          ),
                                          boxShadow: [
                                            BoxShadow(
                                              color: Colors.black.withValues(alpha: 0.06),
                                              blurRadius: 8,
                                              offset: const Offset(0, 2),
                                            ),
                                          ],
                                        ),
                                        child: Column(
                                          crossAxisAlignment: isWorker
                                              ? CrossAxisAlignment.end
                                              : CrossAxisAlignment.start,
                                          children: [
                                            if (isWorker)
                                              Text(
                                                'Du',
                                                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                                                      fontWeight: FontWeight.w800,
                                                      letterSpacing: 0.4,
                                                      color: Theme.of(context).colorScheme.primary,
                                                    ),
                                              )
                                            else
                                              Text(
                                                branding.displayName,
                                                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                                                      fontWeight: FontWeight.w800,
                                                      letterSpacing: 0.4,
                                                      color: const Color(0xFFC2410C),
                                                    ),
                                              ),
                                            const SizedBox(height: 4),
                                            if (showBody && (item['body'] as String? ?? '').trim().isNotEmpty)
                                              Text(
                                                item['body'] as String? ?? '',
                                                style: Theme.of(context).textTheme.bodyMedium,
                                              ),
                                            if (audioAttachments.isNotEmpty) ...[
                                              if (showBody) const SizedBox(height: 6),
                                              ...audioAttachments.map((att) {
                                                final map = Map<String, dynamic>.from(att);
                                                return Padding(
                                                  padding: const EdgeInsets.only(top: 4),
                                                  child: InkWell(
                                                    onTap: () => _openAttachment(map),
                                                    child: Row(
                                                      mainAxisSize: MainAxisSize.min,
                                                      children: [
                                                        Icon(
                                                          Icons.mic,
                                                          size: 18,
                                                          color: isWorker
                                                              ? const Color(0xFF0F766E)
                                                              : const Color(0xFF1D4ED8),
                                                        ),
                                                        const SizedBox(width: 8),
                                                        Text(
                                                          'Sprachnachricht abspielen',
                                                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                                                decoration: TextDecoration.underline,
                                                                fontWeight: FontWeight.w600,
                                                              ),
                                                        ),
                                                      ],
                                                    ),
                                                  ),
                                                );
                                              }),
                                            ],
                                            if (attachments.isNotEmpty) ...[
                                              const SizedBox(height: 6),
                                              ...attachments.map((att) {
                                                final map = Map<String, dynamic>.from(att as Map);
                                                if (_isAudioAttachment(map)) return const SizedBox.shrink();
                                                return InkWell(
                                                  onTap: () => _openAttachment(map),
                                                  child: Padding(
                                                    padding: const EdgeInsets.only(top: 2),
                                                    child: Text(
                                                      '📎 ${map['filename'] ?? 'Anhang'}',
                                                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                                            decoration: TextDecoration.underline,
                                                          ),
                                                    ),
                                                  ),
                                                );
                                              }),
                                            ],
                                            const SizedBox(height: 4),
                                            Row(
                                              mainAxisSize: MainAxisSize.min,
                                              mainAxisAlignment: MainAxisAlignment.end,
                                              children: [
                                                if (timeLabel.isNotEmpty)
                                                  Text(
                                                    timeLabel,
                                                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                                                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                                                        ),
                                                  ),
                                                if (readLabel.isNotEmpty) ...[
                                                  const SizedBox(width: 6),
                                                  Text(
                                                    readLabel,
                                                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                                                          fontWeight: FontWeight.w700,
                                                          color: read
                                                              ? Theme.of(context).colorScheme.primary
                                                              : Theme.of(context).colorScheme.onSurfaceVariant,
                                                        ),
                                                  ),
                                                ],
                                              ],
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                ),
                if (_recording)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 4),
                    child: Row(
                      children: [
                        Icon(Icons.mic, color: Theme.of(context).colorScheme.error),
                        const SizedBox(width: 8),
                        const Expanded(
                          child: Text('Aufnahme läuft — erneut tippen zum Senden'),
                        ),
                      ],
                    ),
                  ),
                SafeArea(
                  top: false,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
                    child: Row(
                      children: [
                        IconButton(
                          onPressed: (_sending || _recording) ? null : _attach,
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
                        _buildPrimaryAction(),
                      ],
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}
