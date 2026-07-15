import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' show FontFeature;

import 'package:flutter/material.dart';
import 'package:open_file/open_file.dart';
import 'package:path_provider/path_provider.dart';

import '../../core/session_store.dart';
import '../../services/chat_repository.dart';
import 'chat_attachment_helpers.dart';

/// WhatsApp-style voice bubble. Downloads once, then opens the system player.
/// (Inline MediaPlayer package is pending when local Flutter pub resolution
/// is fixed on Flutter 3.44 — UI matches the chat34 web player.)
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
  static final Map<String, String> _fileCache = {};

  bool _loading = false;
  bool _playing = false;
  double _progress = 0;
  Timer? _progressTimer;
  Duration _duration = Duration.zero;
  String? _error;

  String get _id => (widget.attachment['id'] ?? '').toString();

  @override
  void initState() {
    super.initState();
    final preset = parseE2eDurationSec(widget.attachment);
    if (preset > 0) _duration = Duration(seconds: preset);
  }

  @override
  void dispose() {
    _progressTimer?.cancel();
    super.dispose();
  }

  Future<String> _ensureLocalFile() async {
    final cached = _fileCache[_id];
    if (cached != null && File(cached).existsSync()) return cached;
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
    _fileCache[_id] = path;
    return path;
  }

  void _startProgressAnim() {
    _progressTimer?.cancel();
    final totalMs = _duration.inMilliseconds > 0 ? _duration.inMilliseconds : 8000;
    final started = DateTime.now();
    _progressTimer = Timer.periodic(const Duration(milliseconds: 80), (_) {
      if (!mounted) return;
      final elapsed = DateTime.now().difference(started).inMilliseconds;
      final p = (elapsed / totalMs).clamp(0.0, 1.0);
      setState(() => _progress = p);
      if (p >= 1) {
        _progressTimer?.cancel();
        setState(() {
          _playing = false;
          _progress = 0;
        });
      }
    });
  }

  Future<void> _toggle() async {
    if (_id.isEmpty) return;
    if (_playing) {
      _progressTimer?.cancel();
      setState(() {
        _playing = false;
        _progress = 0;
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final path = await _ensureLocalFile();
      final result = await OpenFile.open(path);
      if (!mounted) return;
      if (result.type != ResultType.done) {
        setState(() {
          _loading = false;
          _error = 'Abspielen fehlgeschlagen';
        });
        return;
      }
      setState(() {
        _loading = false;
        _playing = true;
      });
      _startProgressAnim();
    } catch (_) {
      if (mounted) {
        setState(() {
          _loading = false;
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
    final remaining = _playing && _duration > Duration.zero
        ? Duration(milliseconds: ((_duration.inMilliseconds) * (1 - _progress)).round())
        : _duration;

    return Material(
      color: bg,
      borderRadius: BorderRadius.circular(999),
      child: InkWell(
        onTap: _loading ? null : _toggle,
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
                        _playing ? Icons.pause_rounded : Icons.play_arrow_rounded,
                        color: Colors.white,
                        size: 22,
                      ),
              ),
              const SizedBox(width: 8),
              SizedBox(
                width: 118,
                height: 26,
                child: CustomPaint(
                  painter: _WavePainter(progress: _progress, accent: accent),
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
