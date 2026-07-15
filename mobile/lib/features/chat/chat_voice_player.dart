import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';
import 'package:path_provider/path_provider.dart';

import '../../core/api_client.dart';
import '../../core/session_store.dart';
import '../../services/chat_repository.dart';
import 'chat_attachment_helpers.dart';

/// WhatsApp-style inline voice note with in-bubble play/pause.
class ChatVoicePlayer extends StatefulWidget {
  const ChatVoicePlayer({
    super.key,
    required this.attachment,
    required this.chat,
    required this.session,
    required this.isMine,
  });

  final Map<String, dynamic> attachment;
  final ChatRepository chat;
  final WorkerSession session;
  final bool isMine;

  @override
  State<ChatVoicePlayer> createState() => _ChatVoicePlayerState();
}

class _ChatVoicePlayerState extends State<ChatVoicePlayer> {
  static AudioPlayer? _sharedPlayer;
  static String? _activeId;
  static final Map<String, String> _fileCache = {};
  static final Set<String> _consumedIds = {};

  final AudioPlayer _player = AudioPlayer();
  StreamSubscription<Duration>? _posSub;
  StreamSubscription<PlayerState>? _stateSub;

  bool _loading = false;
  bool _playing = false;
  bool _consumed = false;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
  String? _error;

  String get _id => (widget.attachment['id'] ?? '').toString();

  bool get _isIncomingViewOnce =>
      !widget.isMine && isChatViewOnceAttachment(widget.attachment);

  @override
  void initState() {
    super.initState();
    _consumed = _isIncomingViewOnce && _consumedIds.contains(_id);
    final preset = parseE2eDurationSec(widget.attachment);
    if (preset > 0) _duration = Duration(seconds: preset);
    _posSub = _player.positionStream.listen((pos) {
      if (!mounted || _activeId != _id) return;
      setState(() => _position = pos);
    });
    _stateSub = _player.playerStateStream.listen((state) {
      if (!mounted) return;
      if (_activeId != _id) return;
      final playing = state.playing && state.processingState != ProcessingState.completed;
      setState(() {
        _playing = playing;
        if (state.processingState == ProcessingState.completed) {
          _position = Duration.zero;
          _playing = false;
          _activeId = null;
        }
      });
      if (state.processingState == ProcessingState.completed && _isIncomingViewOnce) {
        unawaited(_finalizeViewOnce());
      }
    });
  }

  @override
  void dispose() {
    unawaited(_posSub?.cancel());
    unawaited(_stateSub?.cancel());
    if (_activeId == _id) {
      unawaited(_player.stop());
      _activeId = null;
    }
    unawaited(_player.dispose());
    super.dispose();
  }

  Future<void> _clearLocalCache() async {
    final cached = _fileCache.remove(_id);
    if (cached == null) return;
    try {
      final file = File(cached);
      if (await file.exists()) await file.delete();
    } catch (_) {
      /* ignore */
    }
  }

  Future<void> _finalizeViewOnce() async {
    if (_consumed || _id.isEmpty) return;
    _consumedIds.add(_id);
    if (mounted) {
      setState(() {
        _consumed = true;
        _error = 'Bereits gehört';
      });
    }
    await _clearLocalCache();
    try {
      await widget.chat.consumeAttachment(
        session: widget.session,
        attachmentId: _id,
      );
    } catch (_) {
      /* download/server already enforces */
    }
  }

  Future<String> _ensureLocalFile() async {
    if (_isIncomingViewOnce && _consumed) {
      throw ApiException(410, 'view_once_consumed', 'Bereits gehört');
    }
    final cached = _fileCache[_id];
    if (cached != null && File(cached).existsSync()) {
      if (_isIncomingViewOnce) {
        // Do not keep a durable cache for view-once after first fetch.
      }
      return cached;
    }
    final filename = (widget.attachment['filename'] ?? 'voice.m4a').toString();
    final e2eMeta = widget.attachment['e2eMeta'] as String? ?? widget.attachment['e2e_meta'] as String?;
    final bytes = await widget.chat.downloadAttachment(
      session: widget.session,
      attachmentId: _id,
      e2eMeta: e2eMeta,
      filename: filename,
    );
    final dir = await getTemporaryDirectory();
    final safe = filename.replaceAll(RegExp(r'[^\w.\-]'), '_');
    final path = '${dir.path}/voice_${_id}_$safe';
    await File(path).writeAsBytes(Uint8List.fromList(bytes), flush: true);
    if (!_isIncomingViewOnce) {
      _fileCache[_id] = path;
    } else {
      _fileCache[_id] = path; // cleared after complete
    }
    return path;
  }

  Future<void> _toggle() async {
    if (_id.isEmpty) return;
    if (_isIncomingViewOnce && _consumed) {
      setState(() => _error = 'Bereits gehört');
      return;
    }
    if (_playing && _activeId == _id) {
      if (_isIncomingViewOnce) return; // no pause/replay mid-play for view-once
      await _player.pause();
      if (mounted) setState(() => _playing = false);
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (_sharedPlayer != null && _sharedPlayer != _player && _activeId != null && _activeId != _id) {
        await _sharedPlayer!.stop();
      }
      _sharedPlayer = _player;
      _activeId = _id;

      final path = await _ensureLocalFile();
      final dur = await _player.setFilePath(path);
      if (dur != null && dur.inMilliseconds > 0) {
        _duration = dur;
      }
      await _player.play();
      if (mounted) {
        setState(() {
          _playing = true;
          _loading = false;
        });
      }
    } on ApiException catch (e) {
      if (e.statusCode == 410 || e.errorCode == 'view_once_consumed') {
        _consumedIds.add(_id);
        await _clearLocalCache();
        if (mounted) {
          setState(() {
            _loading = false;
            _playing = false;
            _consumed = true;
            _error = 'Bereits gehört';
          });
        }
        return;
      }
      if (mounted) {
        setState(() {
          _loading = false;
          _playing = false;
          _error = 'Abspielen fehlgeschlagen';
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _loading = false;
          _playing = false;
          _error = 'Abspielen fehlgeschlagen';
        });
      }
    }
  }

  String _fmt(Duration d) {
    final total = d.inSeconds.clamp(0, 9999);
    final m = total ~/ 60;
    final s = total % 60;
    return '$m:${s.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final accent = widget.isMine ? const Color(0xFF0F766E) : const Color(0xFF1D4ED8);
    final bg = widget.isMine ? const Color(0xFF005C4B) : const Color(0xFF202C33);
    final progress = _duration.inMilliseconds > 0
        ? (_position.inMilliseconds / _duration.inMilliseconds).clamp(0.0, 1.0)
        : 0.0;
    final remaining = _playing && _duration > Duration.zero
        ? _duration - _position
        : _duration;

    return Material(
      color: bg,
      borderRadius: BorderRadius.circular(999),
      child: InkWell(
        onTap: _loading || (_isIncomingViewOnce && _consumed) ? null : _toggle,
        borderRadius: BorderRadius.circular(999),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(6, 7, 12, 7),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 34,
                height: 34,
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.18),
                  shape: BoxShape.circle,
                ),
                child: _loading
                    ? Padding(
                        padding: const EdgeInsets.all(8),
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white.withValues(alpha: 0.85),
                        ),
                      )
                    : Icon(
                        _consumed
                            ? Icons.visibility_off_rounded
                            : (_playing ? Icons.pause_rounded : Icons.play_arrow_rounded),
                        color: Colors.white,
                        size: 22,
                      ),
              ),
              const SizedBox(width: 8),
              SizedBox(
                width: 118,
                height: 26,
                child: CustomPaint(
                  painter: _WavePainter(progress: progress, accent: accent),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                _error ?? (_duration > Duration.zero ? _fmt(remaining) : '0:00'),
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.88),
                  fontSize: 12,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
              const SizedBox(width: 6),
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: _playing ? const Color(0xFF53BDEB) : accent.withValues(alpha: 0.85),
                  shape: BoxShape.circle,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _WavePainter extends CustomPainter {
  _WavePainter({required this.progress, required this.accent});

  final double progress;
  final Color accent;

  @override
  void paint(Canvas canvas, Size size) {
    const bars = 36;
    const gap = 2.0;
    final barW = (size.width - gap * (bars - 1)) / bars;
    final paint = Paint()..style = PaintingStyle.fill;
    for (var i = 0; i < bars; i++) {
      final t = i / bars;
      final h = 4 + math.sin(i * 0.55) * 8 + math.sin(i * 1.7) * 4;
      final x = i * (barW + gap);
      final y = (size.height - h) / 2;
      paint.color = t <= progress
          ? Colors.white.withValues(alpha: 0.92)
          : Colors.white.withValues(alpha: 0.42);
      canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromLTWH(x, y, barW, h), const Radius.circular(99)),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _WavePainter oldDelegate) =>
      oldDelegate.progress != progress || oldDelegate.accent != accent;
}
