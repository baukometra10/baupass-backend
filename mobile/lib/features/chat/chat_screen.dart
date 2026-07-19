import 'dart:async';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:open_file/open_file.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import '../../core/api_client.dart';
import '../../core/session_store.dart';
import '../../core/tenant_branding.dart';
import '../../services/chat_repository.dart';
import '../../services/conference_repository.dart';
import '../../services/voice_call_controller.dart';
import '../voice_call/conference_invite_sheet.dart';
import 'chat_attachment_helpers.dart';
import 'chat_location_helpers.dart';
import 'chat_media_gallery.dart';
import 'chat_message_prefs.dart';
import 'chat_voice_compose_bar.dart';
import 'chat_voice_player.dart';
import '../../widgets/company_contacts_sheet.dart';

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
  Map<String, dynamic>? _replyTo;
  bool _searchOpen = false;
  String _searchQuery = '';
  final TextEditingController _search = TextEditingController();
  final ChatMessagePrefsState _messagePrefs = ChatMessagePrefsState();
  final ScrollController _messageScroll = ScrollController();
  final Map<String, GlobalKey> _messageKeys = {};
  String? _shownConferenceId;

  @override
  void initState() {
    super.initState();
    _message.addListener(_onComposeChanged);
    _boot();
    _pollTimer = Timer.periodic(const Duration(seconds: 4), (_) {
      if (!_sending && !_silentRefresh && !_voiceComposing && mounted) {
        _boot(silent: true);
        unawaited(_pollConferenceInvite());
      }
    });
    unawaited(_pollConferenceInvite());
  }

  Future<void> _pollConferenceInvite() async {
    try {
      final repo = ConferenceRepository(widget.chat.apiClient);
      final invite = await repo.incoming(widget.session);
      if (!mounted || invite == null) return;
      final id = (invite['id'] ?? '').toString();
      if (id.isEmpty || id == _shownConferenceId) return;
      _shownConferenceId = id;
      await showModalBottomSheet<void>(
        context: context,
        showDragHandle: true,
        builder: (_) => ConferenceInviteSheet(
          session: widget.session,
          repo: repo,
          invite: invite,
        ),
      );
    } catch (_) {
      /* ignore */
    }
  }

  Future<void> _openCallHistory() async {
    try {
      final repo = ConferenceRepository(widget.chat.apiClient);
      final calls = await repo.callHistory(widget.session);
      if (!mounted) return;
      await showModalBottomSheet<void>(
        context: context,
        showDragHandle: true,
        builder: (context) {
          if (calls.isEmpty) {
            return const Padding(
              padding: EdgeInsets.all(24),
              child: Text('Noch keine Anrufe.'),
            );
          }
          return ListView.builder(
            shrinkWrap: true,
            itemCount: calls.length,
            itemBuilder: (context, index) {
              final c = calls[index];
              final status = (c['status'] ?? c['endReason'] ?? '').toString();
              final when = (c['createdAt'] ?? c['endedAt'] ?? '').toString();
              return ListTile(
                leading: const Icon(Icons.call),
                title: Text(status.isEmpty ? 'Anruf' : status),
                subtitle: Text(when),
              );
            },
          );
        },
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Anrufverlauf: $e')),
      );
    }
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _voiceTicker?.cancel();
    _message.removeListener(_onComposeChanged);
    _message.dispose();
    _search.dispose();
    _messageScroll.dispose();
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
      Map<String, dynamic> prefs = {};
      try {
        prefs = await widget.chat.listMessagePrefs(
          session: widget.session,
          threadId: threadId,
        );
      } catch (_) {
        /* local prefs remain */
      }
      if (!mounted) return;
      setState(() {
        _threadId = threadId;
        _messages = messages;
        _messagePrefs.applyServerPrefs(prefs);
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
    final replyId = (_replyTo?['id'] as String?)?.trim();
    setState(() => _sending = true);
    try {
      final res = await widget.chat.sendMessage(
        session: widget.session,
        threadId: threadId,
        body: body,
        replyToMessageId: replyId,
      );
      _message.clear();
      final msg = Map<String, dynamic>.from(res['message'] as Map);
      if (!mounted) return;
      setState(() {
        _messages = [..._messages, msg];
        _replyTo = null;
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
    final fileLen = await file.length();
    if (fileLen < 64) {
      try {
        await file.delete();
      } catch (_) {
        /* ignore */
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Aufnahme leer — bitte erneut versuchen.')),
      );
      return;
    }
    final voiceName = 'voice-${DateTime.now().millisecondsSinceEpoch}.m4a';
    setState(() => _sending = true);
    String? messageId;
    try {
      final res = await widget.chat.sendMessage(
        session: widget.session,
        threadId: threadId,
        body: 'Sprachnachricht',
      );
      final msg = Map<String, dynamic>.from(res['message'] as Map);
      messageId = (msg['id'] ?? '').toString().trim();
      if (messageId!.isEmpty) {
        throw StateError('message_id_missing');
      }
      await widget.chat.uploadAttachment(
        session: widget.session,
        threadId: threadId,
        messageId: messageId!,
        file: file,
        durationSec: durationSec,
        displayFilename: voiceName,
        viewOnce: viewOnce,
      );
      if (!mounted) return;
      await _boot(silent: true);
    } on StateError catch (e) {
      await _rollbackVoicePlaceholder(messageId);
      if (!mounted) return;
      final text = e.message == 'e2e_keys_missing'
          ? 'Sprachnachricht: Chat-Verschlüsselung nicht bereit.'
          : (e.message == 'attachment_empty'
              ? 'Aufnahme leer — bitte erneut versuchen.'
              : e.toString());
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(text), duration: const Duration(seconds: 6)),
      );
      await _boot(silent: true);
    } on ApiException catch (e) {
      await _rollbackVoicePlaceholder(messageId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(e.message ?? 'Sprachnachricht fehlgeschlagen'),
          duration: const Duration(seconds: 6),
        ),
      );
      await _boot(silent: true);
    } catch (e) {
      await _rollbackVoicePlaceholder(messageId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Sprachnachricht fehlgeschlagen: $e')),
      );
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

  Future<void> _rollbackVoicePlaceholder(String? messageId) async {
    final id = (messageId ?? '').trim();
    if (id.isEmpty) return;
    try {
      await widget.chat.deleteMessage(widget.session, id);
    } catch (_) {
      /* ignore */
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

  List<Map<String, dynamic>> get _visibleMessages {
    final q = _searchQuery.trim().toLowerCase();
    if (q.isEmpty) return _messages;
    return _messages.where((item) {
      final body = (item['body'] as String? ?? '').toLowerCase();
      final reply = item['replyTo'];
      final replyBody = reply is Map ? (reply['body'] as String? ?? '').toLowerCase() : '';
      return body.contains(q) || replyBody.contains(q);
    }).toList();
  }

  String _messagePreview(Map<String, dynamic> item) {
    final body = (item['body'] as String? ?? '').trim();
    if (body.isNotEmpty) return body;
    final attachments = (item['attachments'] as List?) ?? const [];
    if (attachments.isNotEmpty) return 'Anhang';
    return 'Nachricht';
  }

  void _setReplyTo(Map<String, dynamic> item) {
    final id = (item['id'] as String?)?.trim() ?? '';
    if (id.isEmpty) return;
    setState(() {
      _replyTo = {
        'id': id,
        'body': _messagePreview(item),
        'senderType': item['senderType'] ?? item['sender_type'] ?? '',
      };
    });
  }

  Map<String, dynamic>? _messageById(String id) {
    final mid = id.trim();
    if (mid.isEmpty) return null;
    for (final item in _messages) {
      if ('${item['id'] ?? ''}'.trim() == mid) return item;
    }
    return null;
  }

  void _scrollToMessage(String messageId) {
    final key = _messageKeys[messageId.trim()];
    final ctx = key?.currentContext;
    if (ctx == null) return;
    unawaited(Scrollable.ensureVisible(
      ctx,
      duration: const Duration(milliseconds: 280),
      curve: Curves.easeInOut,
      alignment: 0.25,
    ));
  }

  Future<void> _toggleMessagePin(Map<String, dynamic> item) async {
    final threadId = _threadId;
    final id = (item['id'] as String?)?.trim() ?? '';
    if (threadId == null || id.isEmpty) return;
    final pinned = _messagePrefs.togglePin(id);
    setState(() {});
    try {
      await widget.chat.upsertMessagePref(
        session: widget.session,
        threadId: threadId,
        messageId: id,
        pinned: pinned,
      );
    } catch (_) {
      _messagePrefs.togglePin(id);
      if (!mounted) return;
      setState(() {});
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Anheften fehlgeschlagen')),
      );
    }
  }

  Future<void> _toggleMessageStar(Map<String, dynamic> item) async {
    final threadId = _threadId;
    final id = (item['id'] as String?)?.trim() ?? '';
    if (threadId == null || id.isEmpty) return;
    final starred = _messagePrefs.toggleStar(id);
    setState(() {});
    try {
      await widget.chat.upsertMessagePref(
        session: widget.session,
        threadId: threadId,
        messageId: id,
        starred: starred,
      );
    } catch (_) {
      _messagePrefs.toggleStar(id);
      if (!mounted) return;
      setState(() {});
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Markieren fehlgeschlagen')),
      );
    }
  }

  Widget _buildPinnedBar() {
    final ids = _messagePrefs.pinnedIdsSorted();
    if (ids.isEmpty || _searchQuery.trim().isNotEmpty) return const SizedBox.shrink();
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: const Color(0xFF00A884).withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF00A884).withValues(alpha: 0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Angeheftet',
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  fontWeight: FontWeight.w800,
                  color: const Color(0xFF00A884),
                ),
          ),
          const SizedBox(height: 6),
          ...ids.take(3).map((id) {
            final item = _messageById(id);
            final preview = item != null ? _messagePreview(item) : 'Nachricht';
            return Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: InkWell(
                borderRadius: BorderRadius.circular(10),
                onTap: () => _scrollToMessage(id),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                  child: Row(
                    children: [
                      const Text('📌', style: TextStyle(fontSize: 14)),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          preview,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ),
                      Text(
                        'Springen',
                        style: Theme.of(context).textTheme.labelSmall?.copyWith(
                              color: const Color(0xFF53BDEB),
                              fontWeight: FontWeight.w700,
                            ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          }),
        ],
      ),
    );
  }

  Future<void> _showMessageActions(Map<String, dynamic> item) async {
    final isWorker = _isWorkerMessage(item);
    final id = (item['id'] as String?)?.trim() ?? '';
    final pinned = id.isNotEmpty && _messagePrefs.isPinned(id);
    final starred = id.isNotEmpty && _messagePrefs.isStarred(id);
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                leading: const Icon(Icons.reply),
                title: const Text('Antworten'),
                onTap: () {
                  Navigator.pop(context);
                  _setReplyTo(item);
                },
              ),
              if (id.isNotEmpty)
                ListTile(
                  leading: Icon(pinned ? Icons.push_pin : Icons.push_pin_outlined),
                  title: Text(pinned ? 'Loslösen' : 'Anheften'),
                  onTap: () async {
                    Navigator.pop(context);
                    await _toggleMessagePin(item);
                  },
                ),
              if (id.isNotEmpty)
                ListTile(
                  leading: Icon(
                    starred ? Icons.star : Icons.star_border,
                    color: starred ? const Color(0xFFF59E0B) : null,
                  ),
                  title: Text(starred ? 'Stern entfernen' : 'Mit Stern markieren'),
                  onTap: () async {
                    Navigator.pop(context);
                    await _toggleMessageStar(item);
                  },
                ),
              ListTile(
                leading: const Icon(Icons.copy),
                title: const Text('Kopieren'),
                onTap: () async {
                  Navigator.pop(context);
                  await Clipboard.setData(ClipboardData(text: _messagePreview(item)));
                  if (!mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Kopiert')),
                  );
                },
              ),
              if (isWorker && id.isNotEmpty)
                ListTile(
                  leading: Icon(Icons.delete_outline, color: Theme.of(context).colorScheme.error),
                  title: Text('Löschen', style: TextStyle(color: Theme.of(context).colorScheme.error)),
                  onTap: () async {
                    Navigator.pop(context);
                    try {
                      await widget.chat.deleteMessage(widget.session, id);
                      await _boot(silent: true);
                    } catch (e) {
                      if (!mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text('Löschen fehlgeschlagen: $e')),
                      );
                    }
                  },
                ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildReplyQuote(Map<String, dynamic> item) {
    final reply = item['replyTo'];
    if (reply is! Map) return const SizedBox.shrink();
    final who = (reply['senderType'] ?? reply['sender_type'] ?? '') == 'worker' ? 'Du' : 'Arbeitgeber';
    final body = (reply['body'] as String? ?? '').trim();
    if (body.isEmpty) return const SizedBox.shrink();
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.fromLTRB(10, 6, 10, 6),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(10),
        border: const Border(left: BorderSide(color: Color(0xFF00A884), width: 3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(who, style: Theme.of(context).textTheme.labelSmall?.copyWith(fontWeight: FontWeight.w800)),
          Text(
            body,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final branding = TenantBrandingScope.of(context);
    final visible = _visibleMessages;
    return Scaffold(
      appBar: AppBar(
        title: _searchOpen
            ? TextField(
                controller: _search,
                autofocus: true,
                decoration: const InputDecoration(
                  hintText: 'In Unterhaltung suchen…',
                  border: InputBorder.none,
                ),
                onChanged: (value) => setState(() => _searchQuery = value),
              )
            : Text(branding.chatTitle),
        actions: [
          IconButton(
            icon: Icon(_searchOpen ? Icons.close : Icons.search),
            tooltip: 'Suchen',
            onPressed: () {
              setState(() {
                _searchOpen = !_searchOpen;
                if (!_searchOpen) {
                  _search.clear();
                  _searchQuery = '';
                }
              });
            },
          ),
          if (widget.voiceCall != null)
            IconButton(
              icon: const Icon(Icons.contacts_rounded),
              tooltip: 'Kontakte',
              onPressed: () {
                unawaited(CompanyContactsSheet.show(
                  context,
                  session: widget.session,
                  api: widget.chat.apiClient,
                  onCallEmployer: widget.voiceCall!.isActive
                      ? null
                      : () => widget.voiceCall!.startOutgoingCall(),
                ));
              },
            ),
          if (widget.voiceCall != null)
            IconButton(
              icon: const Icon(Icons.call_rounded),
              tooltip: 'Firma anrufen',
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
            icon: const Icon(Icons.history),
            tooltip: 'Anrufverlauf',
            onPressed: () => unawaited(_openCallHistory()),
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
                _buildPinnedBar(),
                Expanded(
                  child: visible.isEmpty
                      ? Center(
                          child: Text(
                            _searchQuery.trim().isEmpty
                                ? 'Noch keine Nachrichten'
                                : 'Keine Treffer',
                          ),
                        )
                      : ListView.builder(
                          controller: _messageScroll,
                          padding: const EdgeInsets.all(16),
                          itemCount: visible.length,
                          itemBuilder: (context, index) {
                            final item = visible[index];
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
                            final messageId = (item['id'] as String?)?.trim() ?? '';
                            if (messageId.isNotEmpty) {
                              _messageKeys.putIfAbsent(messageId, GlobalKey.new);
                            }
                            final pinned = messageId.isNotEmpty && _messagePrefs.isPinned(messageId);
                            final starred = messageId.isNotEmpty && _messagePrefs.isStarred(messageId);
                            return Padding(
                              key: messageId.isNotEmpty ? _messageKeys[messageId] : null,
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
                                      child: GestureDetector(
                                        onLongPress: () => unawaited(_showMessageActions(item)),
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
                                            color: pinned
                                                ? const Color(0xFF00A884).withValues(alpha: 0.55)
                                                : (isWorker
                                                    ? const Color(0xFF93C5FD)
                                                    : Theme.of(context).colorScheme.outlineVariant),
                                            width: pinned ? 1.5 : 1,
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
                                            _buildReplyQuote(item),
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
                                                  if (pinned)
                                                    const Padding(
                                                      padding: EdgeInsets.only(right: 4),
                                                      child: Icon(Icons.push_pin, size: 14, color: Color(0xFF00A884)),
                                                    ),
                                                  if (starred)
                                                    const Padding(
                                                      padding: EdgeInsets.only(right: 4),
                                                      child: Icon(Icons.star, size: 14, color: Color(0xFFF59E0B)),
                                                    ),
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
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                ),
                if (_replyTo != null && !_voiceComposing)
                  Material(
                    color: Theme.of(context).colorScheme.surfaceContainerHighest,
                    child: ListTile(
                      dense: true,
                      leading: const Icon(Icons.reply, size: 20),
                      title: Text(
                        _isWorkerMessage(_replyTo!) ? 'Antwort auf dich' : 'Antwort auf Arbeitgeber',
                        style: Theme.of(context).textTheme.labelMedium?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      subtitle: Text(
                        (_replyTo!['body'] as String? ?? ''),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      trailing: IconButton(
                        icon: const Icon(Icons.close),
                        onPressed: () => setState(() => _replyTo = null),
                      ),
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
