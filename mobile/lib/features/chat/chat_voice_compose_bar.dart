import 'dart:math' as math;

import 'package:flutter/material.dart';

class ChatVoiceComposeBar extends StatefulWidget {
  const ChatVoiceComposeBar({
    super.key,
    required this.elapsed,
    required this.paused,
    required this.viewOnce,
    required this.onCancel,
    required this.onTogglePause,
    required this.onToggleViewOnce,
    required this.onSend,
  });

  final Duration elapsed;
  final bool paused;
  final bool viewOnce;
  final VoidCallback onCancel;
  final VoidCallback onTogglePause;
  final VoidCallback onToggleViewOnce;
  final VoidCallback onSend;

  @override
  State<ChatVoiceComposeBar> createState() => _ChatVoiceComposeBarState();
}

class _ChatVoiceComposeBarState extends State<ChatVoiceComposeBar>
    with SingleTickerProviderStateMixin {
  late final AnimationController _waveCtrl;

  @override
  void initState() {
    super.initState();
    _waveCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat();
  }

  @override
  void dispose() {
    _waveCtrl.dispose();
    super.dispose();
  }

  String _format(Duration d) {
    final total = d.inSeconds.clamp(0, 359999);
    final mins = total ~/ 60;
    final secs = total % 60;
    return '$mins:${secs.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF1F2C34),
        border: Border(top: BorderSide(color: Colors.white.withValues(alpha: 0.08))),
      ),
      child: Row(
        children: [
          IconButton(
            onPressed: widget.onCancel,
            icon: const Icon(Icons.delete_outline, color: Color(0xFFEA4335)),
            tooltip: 'Verwerfen',
          ),
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              color: widget.paused ? const Color(0xFFEAA860) : const Color(0xFFEA4335),
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 8),
          Text(
            _format(widget.elapsed),
            style: const TextStyle(
              color: Color(0xFFE9EDEF),
              fontWeight: FontWeight.w700,
              fontFeatures: [FontFeature.tabularFigures()],
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: SizedBox(
              height: 28,
              child: AnimatedBuilder(
                animation: _waveCtrl,
                builder: (context, _) {
                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: List.generate(28, (index) {
                      final phase = (_waveCtrl.value * math.pi * 2) + (index * 0.35);
                      final amp = widget.paused ? 0.15 : (0.35 + (math.sin(phase).abs() * 0.65));
                      return Expanded(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 1),
                          child: Align(
                            alignment: Alignment.center,
                            child: Container(
                              height: 4 + (amp * 18),
                              decoration: BoxDecoration(
                                color: const Color(0xFF00A884).withValues(alpha: 0.55 + amp * 0.35),
                                borderRadius: BorderRadius.circular(999),
                              ),
                            ),
                          ),
                        ),
                      );
                    }),
                  );
                },
              ),
            ),
          ),
          IconButton(
            onPressed: widget.onTogglePause,
            icon: Icon(widget.paused ? Icons.play_arrow : Icons.pause, color: const Color(0xFF8696A0)),
            tooltip: widget.paused ? 'Fortsetzen' : 'Pause',
          ),
          IconButton(
            onPressed: widget.onToggleViewOnce,
            style: IconButton.styleFrom(
              backgroundColor: widget.viewOnce
                  ? const Color(0xFF00A884).withValues(alpha: 0.18)
                  : Colors.transparent,
            ),
            icon: Icon(
              Icons.looks_one,
              color: widget.viewOnce ? const Color(0xFF00A884) : const Color(0xFF8696A0),
            ),
            tooltip: 'Einmal anhören',
          ),
          const SizedBox(width: 4),
          FilledButton(
            onPressed: widget.onSend,
            style: FilledButton.styleFrom(
              backgroundColor: const Color(0xFF00A884),
              minimumSize: const Size(48, 48),
              padding: EdgeInsets.zero,
              shape: const CircleBorder(),
            ),
            child: const Icon(Icons.send, size: 20),
          ),
        ],
      ),
    );
  }
}
