import 'dart:io';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';

class ChatVoiceBubble extends StatefulWidget {
  const ChatVoiceBubble({
    super.key,
    required this.loadBytes,
    this.isWorker = false,
  });

  final Future<Uint8List> Function() loadBytes;
  final bool isWorker;

  @override
  State<ChatVoiceBubble> createState() => _ChatVoiceBubbleState();
}

class _ChatVoiceBubbleState extends State<ChatVoiceBubble> {
  final AudioPlayer _player = AudioPlayer();
  bool _loading = false;
  bool _playing = false;
  Duration _duration = Duration.zero;
  Duration _position = Duration.zero;
  String? _tempPath;

  @override
  void initState() {
    super.initState();
    _player.onPlayerComplete.listen((_) {
      if (!mounted) return;
      setState(() {
        _playing = false;
        _position = Duration.zero;
      });
    });
    _player.onDurationChanged.listen((duration) {
      if (!mounted) return;
      setState(() => _duration = duration);
    });
    _player.onPositionChanged.listen((position) {
      if (!mounted) return;
      setState(() => _position = position);
    });
  }

  @override
  void dispose() {
    _player.dispose();
    _deleteTempFile();
    super.dispose();
  }

  void _deleteTempFile() {
    final path = _tempPath;
    if (path == null) return;
    try {
      File(path).deleteSync();
    } catch (_) {
      /* ignore */
    }
    _tempPath = null;
  }

  Future<void> _toggle() async {
    if (_loading) return;
    if (_playing) {
      await _player.pause();
      if (mounted) setState(() => _playing = false);
      return;
    }
    if (_tempPath != null) {
      await _player.play(DeviceFileSource(_tempPath!));
      if (!context.mounted) return;
      setState(() => _playing = true);
      return;
    }
    setState(() => _loading = true);
    try {
      final bytes = await widget.loadBytes();
      final dir = await getTemporaryDirectory();
      final path = '${dir.path}/voice_play_${DateTime.now().millisecondsSinceEpoch}.m4a';
      final file = File(path);
      await file.writeAsBytes(bytes, flush: true);
      _tempPath = path;
      await _player.play(DeviceFileSource(path));
      if (mounted) setState(() => _playing = true);
    } catch (_) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Sprachnachricht konnte nicht abgespielt werden.')),
      );
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _format(Duration value) {
    final total = value.inSeconds;
    final mins = total ~/ 60;
    final secs = total % 60;
    return '$mins:${secs.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final accent = widget.isWorker ? const Color(0xFF0F766E) : const Color(0xFF1D4ED8);
    final label = _playing || _position > Duration.zero
        ? _format(_position)
        : (_duration > Duration.zero ? _format(_duration) : '0:00');
    return Container(
      padding: const EdgeInsets.fromLTRB(4, 4, 12, 4),
      decoration: BoxDecoration(
        color: widget.isWorker ? const Color(0xFFCCFBF1) : const Color(0xFFEFF6FF),
        borderRadius: BorderRadius.circular(24),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton(
            visualDensity: VisualDensity.compact,
            onPressed: _loading ? null : _toggle,
            icon: _loading
                ? SizedBox(
                    width: 22,
                    height: 22,
                    child: CircularProgressIndicator(strokeWidth: 2, color: accent),
                  )
                : Icon(
                    _playing ? Icons.pause_circle_filled : Icons.play_circle_filled,
                    color: accent,
                    size: 34,
                  ),
          ),
          Icon(Icons.graphic_eq, size: 18, color: accent.withValues(alpha: 0.75)),
          const SizedBox(width: 8),
          Text(
            label,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: accent,
                  fontWeight: FontWeight.w600,
                ),
          ),
        ],
      ),
    );
  }
}
