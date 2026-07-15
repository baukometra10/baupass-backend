import 'dart:async';
import 'dart:io';
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
import '../../services/voice_call_controller.dart';
import 'chat_attachment_helpers.dart';
import 'chat_location_helpers.dart';
import 'chat_media_gallery.dart';
import 'chat_voice_compose_bar.dart';
import 'chat_voice_player.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.session,
    required this.chat,
    this.voiceCall,
  });

  final WorkerSession session;
  final ChatRepository chat;
  final VoiceCallController? voiceCall;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final TextEditingController _message = TextEditingController();
  final AudioRecorder _recorder = AudioRecorder();
  bool _loading = true;
  bool _sending = false;
  bool _voiceComposing = false;
  bool _voicePaused = false;
  bool _voiceViewOnce = false;
  String? _threadId;
  String? _recordPath;
  DateTime? _voiceSegmentStarted;
  Duration _voiceElapsed = Duration.zero;
  Duration _voiceAccumulated = Duration.zero;
  Timer? _voiceTicker;
  List<Map<String, dynamic>> _messages = <Map<String, dynamic>>[];
  bool _silentRefresh = false;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _message.addListener(_onComposeChanged);
    _boot();
    _pollTimer = Timer.periodic(const Duration(seconds: 4), (_) {
      if (!_sending && !_silentRefresh && !_voiceComposing && mounted) {
        _boot(silent: true);
      }
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _voiceTicker?.cancel();
    _message.removeListener(_onComposeChanged);
    _message.dispose();
    if (_voiceComposing) {
      unawaited(_recorder.stop());
    }
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

  Future<void> _sendVoiceFile(String filePath, {int? durationSec, bool viewOnce = false}) async {
    final threadId = _threadId;
    if (threadId == null || _sending) return;
    final file = File(filePath);
    if (!await file.exists()) return;
    final voiceName = 'voice-${DateTime.now().millisecondsSinceEpoch}.m4a';
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
        displayFilename: voiceName,
        viewOnce: viewOnce,
      );
      if (!mounted) return;
      await _boot(silent: true);
    } on StateError catch (e) {
      if (!mounted) return;
      final text = e.message == 'e2e_keys_missing'
          ? 'Sprachnachricht: Chat-Verschlüsselung nicht bereit.'
          : e.toString();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(text), duration: const Duration(seconds: 6)),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(e.message ?? 'Sprachnachricht fehlgeschlagen'),
          duration: const Duration(seconds: 6),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Sprachnachricht fehlgeschlagen: $e')),
      );
    } finally {
      if (mounted) setState(() => _sending = false);
      try {
        await file.delete();
      } catch (_) {
        /* ignore */
      }
    }
  }

  void _syncVoiceElapsed() {
    if (!_voiceComposing || _voicePaused || _voiceSegmentStarted == null) return;
    setState(() {
      _voiceElapsed = _voiceAccumulated + DateTime.now().difference(_voiceSegmentStarted!);
    });
  }

  void _startVoiceTicker() {
    _voiceTicker?.cancel();
    _voiceTicker = Timer.periodic(const Duration(milliseconds: 200), (_) => _syncVoiceElapsed());
  }

  Future<void> _startVoiceCompose() async {
    if (_sending || _voiceComposing) return;
    if (!await _recorder.hasPermission()) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Mikrofon-Berechtigung erforderlich. Bitte in den Einstellungen erlauben.',
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
      _voiceComposing = true;
      _voicePaused = false;
      _voiceViewOnce = false;
      _voiceElapsed = Duration.zero;
      _voiceAccumulated = Duration.zero;
      _voiceSegmentStarted = DateTime.now();
    });
    _startVoiceTicker();
  }

  Future<void> _cancelVoiceCompose() async {
    _voiceTicker?.cancel();
    if (_voiceComposing) {
      await _recorder.stop();
    }
    final path = _recordPath;
    _recordPath = null;
    if (path != null) {
      try {
        await File(path).delete();
      } catch (_) {
        /* ignore */
      }
    }
    if (!mounted) return;
    setState(() {
      _voiceComposing = false;
      _voicePaused = false;
      _voiceViewOnce = false;
      _voiceElapsed = Duration.zero;
      _voiceAccumulated = Duration.zero;
      _voiceSegmentStarted = null;
    });
  }

  Future<void> _toggleVoicePause() async {
    if (!_voiceComposing) return;
    if (_voicePaused) {
      await _recorder.resume();
      if (!mounted) return;
      setState(() {
        _voicePaused = false;
        _voiceSegmentStarted = DateTime.now();
      });
      _startVoiceTicker();
      return;
    }
    _syncVoiceElapsed();
    _voiceTicker?.cancel();
    await _recorder.pause();
    if (!mounted) return;
    setState(() {
      _voicePaused = true;
      _voiceAccumulated = _voiceElapsed;
      _voiceSegmentStarted = null;
    });
  }

  Future<void> _finishVoiceCompose() async {
    if (!_voiceComposing) return;
    _syncVoiceElapsed();
    _voiceTicker?.cancel();
    final viewOnce = _voiceViewOnce;
    final elapsed = _voiceElapsed;
    final path = await _recorder.stop();
    final filePath = path ?? _recordPath;
    _recordPath = null;
    if (!mounted) return;
    setState(() {
      _voiceComposing = false;
      _voicePaused = false;
      _voiceViewOnce = false;
      _voiceElapsed = Duration.zero;
      _voiceAccumulated = Duration.zero;
      _voiceSegmentStarted = null;
    });
    if (filePath == null || filePath.isEmpty) return;
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
    await _sendVoiceFile(
      filePath,
      durationSec: elapsed.inSeconds.clamp(1, 3600),
      viewOnce: viewOnce,
    );
  }

  Future<void> _sendLocation() async {
    final threadId = _threadId;
    if (threadId == null || _sending || _voiceComposing) return;
    final point = await showChatLocationShareSheet(context);
    if (point == null || !mounted) return;
    setState(() => _sending = true);
    try {
      final body = encodeChatLocationBody(
        lat: point.lat,
        lng: point.lng,
        accuracy: point.accuracy,
        note: point.note,
      );
      await widget.chat.sendMessage(
        session: widget.session,
        threadId: threadId,
        body: body,
      );
      await _boot(silent: true);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Standort senden fehlgeschlagen: $e')),
      );
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _openGallery() async {
    if (_messages.isEmpty) return;
    await showChatMediaGallery(
      context: context,
      messages: _messages,
      session: widget.session,
      chat: widget.chat,
      onDeleteMessage: (messageId) async {
        await widget.chat.deleteMessage(widget.session, messageId);
        await _boot(silent: true);
      },
      onOpenItem: (item) async {
        if (item.kind == ChatMediaKind.image) {
          await _showImageFullscreen({
            'id': item.id,
            'filename': item.filename,
            'e2eMeta': item.e2eMeta,
            'e2e_meta': item.e2eMeta,
          });
          return;
        }
        await _openAttachment({
          'id': item.id,
          'filename': item.filename,
          'e2eMeta': item.e2eMeta,
          'e2e_meta': item.e2eMeta,
        });
      },
    );
  }

  Future<void> _attach() async {
    final threadId = _threadId;
    if (threadId == null || _sending || _voiceComposing) return;
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

  bool _isImageAttachment(Map<String, dynamic> attachment) => isChatImageAttachment(attachment);

  bool _isAudioAttachment(Map<String, dynamic> attachment) => isChatAudioAttachment(attachment);

  Future<void> _showImageFullscreen(Map<String, dynamic> attachment) async {
    final id = attachment['id'] as String?;
    if (id == null || id.isEmpty) return;
    final filename = attachment['filename'] as String? ?? 'bild.jpg';
    final e2eMeta = attachment['e2eMeta'] as String? ?? attachment['e2e_meta'] as String?;
    try {
      final bytes = await widget.chat.downloadAttachment(
        session: widget.session,
        attachmentId: id,
        e2eMeta: e2eMeta,
        filename: filename,
      );
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        barrierColor: Colors.black87,
        builder: (context) {
          return Dialog.fullscreen(
            backgroundColor: Colors.black,
            child: Stack(
              children: [
                Center(
                  child: InteractiveViewer(
                    minScale: 0.5,
                    maxScale: 4,
                    child: Image.memory(bytes, fit: BoxFit.contain),
                  ),
                ),
                SafeArea(
                  child: Align(
                    alignment: Alignment.topRight,
                    child: IconButton(
                      onPressed: () => Navigator.of(context).pop(),
                      icon: const Icon(Icons.close, color: Colors.white),
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Bild konnte nicht geladen werden: $e')),
      );
    }
  }

  Widget _buildImageAttachment(Map<String, dynamic> attachment) {
    final id = attachment['id'] as String?;
    if (id == null || id.isEmpty) return const SizedBox.shrink();
    return _ChatImagePreview(
      key: ValueKey<String>(id),
      attachment: attachment,
      chat: widget.chat,
      session: widget.session,
      onTapFullscreen: () => _showImageFullscreen(attachment),
    );
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

  bool _shouldShowCallLogToWorker(Map<String, String> meta) {
    final audience = (meta['audience'] ?? 'both').toLowerCase();
    return audience != 'admin';
  }

  Map<String, String>? _parseVoiceCallLog(String? body) {
    final text = (body ?? '').trim();
    if (!text.startsWith('@voice-call|')) return null;
    final meta = <String, String>{};
    for (final part in text.substring('@voice-call|'.length).split('|')) {
      final idx = part.indexOf('=');
      if (idx <= 0) continue;
      meta[part.substring(0, idx)] = part.substring(idx + 1);
    }
    return meta.containsKey('status') ? meta : null;
  }

  String _voiceCallLogSummary(Map<String, String> meta) {
    final status = meta['status'] ?? 'ended';
    final duration = int.tryParse(meta['duration'] ?? '') ?? 0;
    final label = switch (status) {
      'declined' => 'Abgelehnt',
      'missed' => 'Verpasst',
      'cancelled' => 'Abgebrochen',
      'callback_requested' => 'Rückruf angefordert',
      _ => 'Anruf beendet',
    };
    if (duration > 0) {
      final m = (duration ~/ 60).toString().padLeft(2, '0');
      final s = (duration % 60).toString().padLeft(2, '0');
      return '$label · $m:$s';
    }
    return label;
  }

  Future<void> _requestCallback({String? callId}) async {
    try {
      await widget.chat.requestVoiceCallback(widget.session, callId: callId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Rückruf angefordert')),
      );
      await _boot(silent: true);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Rückruf fehlgeschlagen: $e')),
      );
    }
  }

  Widget _buildCallLogBubble(Map<String, String> meta, {required bool showCallback}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF0F766E).withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0xFF5EEAD4).withValues(alpha: 0.35)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('📞', style: TextStyle(fontSize: 16)),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  _voiceCallLogSummary(meta),
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ),
            ],
          ),
          if (showCallback) ...[
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: () => _requestCallback(callId: meta['callId']),
              child: const Text('Rückruf anfordern'),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildPrimaryAction() {
    final hasText = _message.text.trim().isNotEmpty;
    if (hasText) {
      return FilledButton(
        onPressed: _sending ? null : _send,
        style: FilledButton.styleFrom(
          backgroundColor: const Color(0xFF00A884),
          minimumSize: const Size(52, 52),
          padding: EdgeInsets.zero,
          shape: const CircleBorder(),
        ),
        child: const Icon(Icons.send),
      );
    }
    return FilledButton(
      onPressed: (_sending || _voiceComposing) ? null : _startVoiceCompose,
      style: FilledButton.styleFrom(
        backgroundColor: const Color(0xFF00A884),
        minimumSize: const Size(52, 52),
        padding: EdgeInsets.zero,
        shape: const CircleBorder(),
      ),
      child: const Icon(Icons.mic),
    );
  }

  @override
  Widget build(BuildContext context) {
    final branding = TenantBrandingScope.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(branding.chatTitle),
        actions: [
          if (widget.voiceCall != null)
            IconButton(
              icon: const Icon(Icons.call_rounded),
              tooltip: 'Anrufen',
              onPressed: widget.voiceCall!.isActive
                  ? null
                  : () {
                      unawaited(widget.voiceCall!.startOutgoingCall());
                    },
            ),
          IconButton(
            icon: const Icon(Icons.photo_library_outlined),
            tooltip: 'Medien',
            onPressed: _messages.isEmpty ? null : _openGallery,
          ),
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
                            final callLogRaw = _parseVoiceCallLog(item['body'] as String?);
                            final callLog = callLogRaw != null && _shouldShowCallLogToWorker(callLogRaw)
                                ? callLogRaw
                                : null;
                            final location = parseChatLocationBody(item['body'] as String?);
                            final attachments = (item['attachments'] as List?) ?? const [];
                            final audioAttachments = attachments
                                .map((att) => Map<String, dynamic>.from(att as Map))
                                .where(_isAudioAttachment)
                                .toList();
                            final showBody = callLog == null
                                && location == null
                                && (!_isVoiceOnlyBody(item['body'] as String?) || audioAttachments.isEmpty);
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
                                            if (callLog != null)
                                              _buildCallLogBubble(
                                                callLog,
                                                showCallback: !isWorker
                                                    && const {'missed', 'declined', 'cancelled', 'ended'}.contains(callLog['status']),
                                              )
                                            else if (location != null)
                                              Padding(
                                                padding: const EdgeInsets.only(top: 4),
                                                child: ChatLocationBubble(
                                                  point: location,
                                                  isMine: isWorker,
                                                  timeLabel: timeLabel,
                                                ),
                                              )
                                            else if (showBody && (item['body'] as String? ?? '').trim().isNotEmpty)
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
                                                  child: ChatVoicePlayer(
                                                    key: ValueKey<String>((map['id'] ?? '').toString()),
                                                    attachment: map,
                                                    chat: widget.chat,
                                                    session: widget.session,
                                                    isMine: isWorker,
                                                  ),
                                                );
                                              }),
                                            ],
                                            if (attachments.isNotEmpty) ...[
                                              const SizedBox(height: 6),
                                              ...attachments.map((att) {
                                                final map = Map<String, dynamic>.from(att as Map);
                                                if (_isImageAttachment(map)) {
                                                  return Padding(
                                                    padding: const EdgeInsets.only(top: 4),
                                                    child: _buildImageAttachment(map),
                                                  );
                                                }
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
                                            if (location == null) ...[
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
                                            ] else if (readLabel.isNotEmpty) ...[
                                              const SizedBox(height: 4),
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
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                ),
                if (_voiceComposing)
                  ChatVoiceComposeBar(
                    elapsed: _voiceElapsed,
                    paused: _voicePaused,
                    viewOnce: _voiceViewOnce,
                    onCancel: () => unawaited(_cancelVoiceCompose()),
                    onTogglePause: () => unawaited(_toggleVoicePause()),
                    onToggleViewOnce: () => setState(() => _voiceViewOnce = !_voiceViewOnce),
                    onSend: () => unawaited(_finishVoiceCompose()),
                  )
                else
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
                          IconButton(
                            onPressed: _sending ? null : _sendLocation,
                            icon: const Icon(Icons.location_on_outlined),
                            tooltip: 'Standort senden',
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

class _ChatImagePreview extends StatefulWidget {
  const _ChatImagePreview({
    super.key,
    required this.attachment,
    required this.chat,
    required this.session,
    required this.onTapFullscreen,
  });

  final Map<String, dynamic> attachment;
  final ChatRepository chat;
  final WorkerSession session;
  final VoidCallback onTapFullscreen;

  @override
  State<_ChatImagePreview> createState() => _ChatImagePreviewState();
}

class _ChatImagePreviewState extends State<_ChatImagePreview> {
  Uint8List? _bytes;
  bool _loading = true;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final id = widget.attachment['id'] as String?;
    if (id == null || id.isEmpty) {
      if (mounted) setState(() { _loading = false; _failed = true; });
      return;
    }
    try {
      final bytes = await widget.chat.downloadAttachment(
        session: widget.session,
        attachmentId: id,
        e2eMeta: widget.attachment['e2eMeta'] as String? ?? widget.attachment['e2e_meta'] as String?,
        filename: widget.attachment['filename'] as String? ?? 'bild.jpg',
      );
      if (!mounted) return;
      setState(() {
        _bytes = bytes;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _failed = true;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const SizedBox(
        width: 180,
        height: 120,
        child: Center(child: SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2))),
      );
    }
    if (_failed || _bytes == null) {
      return InkWell(
        onTap: widget.onTapFullscreen,
        child: const Text('🖼 Bild anzeigen', style: TextStyle(decoration: TextDecoration.underline)),
      );
    }
    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        onTap: widget.onTapFullscreen,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 280, maxHeight: 280),
          child: Image.memory(_bytes!, fit: BoxFit.cover),
        ),
      ),
    );
  }
}
