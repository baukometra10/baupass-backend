import 'dart:async';
import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';

import '../../core/tenant_branding.dart';
import '../../services/voice_call_controller.dart';

/// Immersive full-screen voice call experience for workers.
class VoiceCallOverlay extends StatefulWidget {
  const VoiceCallOverlay({
    super.key,
    required this.controller,
    required this.branding,
  });

  final VoiceCallController controller;
  final TenantBranding branding;

  @override
  State<VoiceCallOverlay> createState() => _VoiceCallOverlayState();
}

class _VoiceCallOverlayState extends State<VoiceCallOverlay> with TickerProviderStateMixin {
  late final AnimationController _pulseController;
  late final AnimationController _waveController;
  RTCVideoRenderer? _remoteRenderer;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(vsync: this, duration: const Duration(milliseconds: 2200))
      ..repeat();
    _waveController = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat(reverse: true);
    widget.controller.addListener(_onControllerChanged);
    _syncRemoteRenderer();
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onControllerChanged);
    _pulseController.dispose();
    _waveController.dispose();
    _disposeRenderer();
    super.dispose();
  }

  void _onControllerChanged() {
    _syncRemoteRenderer();
    if (mounted) setState(() {});
  }

  Future<void> _syncRemoteRenderer() async {
    final stream = widget.controller.rtcSession?.remoteStream;
    if (stream == null) {
      await _disposeRenderer();
      return;
    }
    _remoteRenderer ??= RTCVideoRenderer();
    if (!_remoteRenderer!.initialized) {
      await _remoteRenderer!.initialize();
    }
    _remoteRenderer!.srcObject = stream;
    if (mounted) setState(() {});
  }

  Future<void> _disposeRenderer() async {
    final renderer = _remoteRenderer;
    _remoteRenderer = null;
    if (renderer == null) return;
    await renderer.dispose();
  }

  Color get _accent => widget.branding.accentColor ?? const Color(0xFF06B6D4);

  String _formatDuration(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    if (d.inHours > 0) {
      return '${d.inHours}:$m:$s';
    }
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    final phase = widget.controller.phase;
    if (phase == VoiceCallUiPhase.idle) return const SizedBox.shrink();

    final isRinging = phase == VoiceCallUiPhase.ringing;
    final isConnected = phase == VoiceCallUiPhase.connected;
    final isEnded = phase == VoiceCallUiPhase.ended;

    return SizedBox.expand(
      child: Material(
        color: Colors.transparent,
        child: Stack(
        fit: StackFit.expand,
        children: [
          _AmbientBackground(accent: _accent, pulse: _pulseController),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
              child: Column(
                children: [
                  _SecureBadge(accent: _accent),
                  const Spacer(flex: 2),
                  _CallerAvatar(
                    label: widget.controller.callerLabel,
                    accent: _accent,
                    pulse: _pulseController,
                    ringing: isRinging,
                  ),
                  const SizedBox(height: 22),
                  Text(
                    widget.controller.callerLabel,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 28,
                      fontWeight: FontWeight.w700,
                      letterSpacing: -0.3,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    isConnected
                        ? _formatDuration(widget.controller.elapsed)
                        : widget.controller.statusNote,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.78),
                      fontSize: 16,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    widget.controller.subtitleLabel,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.55),
                      fontSize: 13,
                    ),
                  ),
                  if (isConnected) ...[
                    const SizedBox(height: 28),
                    _WaveBars(controller: _waveController, accent: _accent),
                  ],
                  const Spacer(flex: 3),
                  if (_remoteRenderer != null)
                    SizedBox(
                      width: 1,
                      height: 1,
                      child: RTCVideoView(
                        _remoteRenderer!,
                        objectFit: RTCVideoViewObjectFit.RTCVideoViewObjectFitCover,
                      ),
                    ),
                  if (isRinging)
                    _IncomingActions(
                      accent: _accent,
                      onDecline: widget.controller.decline,
                      onAccept: widget.controller.accept,
                    )
                  else if (isConnected)
                    _ActiveControls(
                      accent: _accent,
                      muted: widget.controller.muted,
                      speakerOn: widget.controller.speakerOn,
                      onToggleMute: widget.controller.toggleMute,
                      onToggleSpeaker: widget.controller.toggleSpeaker,
                      onHangup: widget.controller.hangup,
                    )
                  else if (isEnded)
                    _EndedHint(note: widget.controller.statusNote)
                  else
                    const Padding(
                      padding: EdgeInsets.only(bottom: 12),
                      child: CircularProgressIndicator(color: Colors.white70),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
      ),
    );
  }
}

class _AmbientBackground extends StatelessWidget {
  const _AmbientBackground({required this.accent, required this.pulse});

  final Color accent;
  final AnimationController pulse;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: pulse,
      builder: (context, _) {
        final t = pulse.value;
        return Container(
          decoration: BoxDecoration(
            gradient: RadialGradient(
              center: Alignment(0, -0.15 + math.sin(t * math.pi * 2) * 0.05),
              radius: 1.2,
              colors: [
                Color.lerp(const Color(0xFF0B1220), accent.withValues(alpha: 0.35), 0.35 + t * 0.15)!,
                const Color(0xFF020617),
                const Color(0xFF000000),
              ],
            ),
          ),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 0.5, sigmaY: 0.5),
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    accent.withValues(alpha: 0.08 + t * 0.06),
                    Colors.transparent,
                    Colors.black.withValues(alpha: 0.55),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _SecureBadge extends StatelessWidget {
  const _SecureBadge({required this.accent});

  final Color accent;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: accent.withValues(alpha: 0.35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.lock_rounded, size: 14, color: accent),
          const SizedBox(width: 6),
          Text(
            'Sicherer Sprachkanal · DTLS-SRTP',
            style: TextStyle(color: Colors.white.withValues(alpha: 0.88), fontSize: 12, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}

class _CallerAvatar extends StatelessWidget {
  const _CallerAvatar({
    required this.label,
    required this.accent,
    required this.pulse,
    required this.ringing,
  });

  final String label;
  final Color accent;
  final AnimationController pulse;
  final bool ringing;

  @override
  Widget build(BuildContext context) {
    final parts = label.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).take(2);
    final initials = parts.map((p) => p.substring(0, 1).toUpperCase()).join();
    return SizedBox(
      width: 168,
      height: 168,
      child: Stack(
        alignment: Alignment.center,
        children: [
          if (ringing)
            ...List.generate(3, (index) {
              return AnimatedBuilder(
                animation: pulse,
                builder: (context, child) {
                  final delay = index * 0.22;
                  final scale = 1 + ((pulse.value + delay) % 1) * 0.55;
                  final opacity = (1 - ((pulse.value + delay) % 1)) * 0.35;
                  return Transform.scale(
                    scale: scale,
                    child: Container(
                      width: 120,
                      height: 120,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(color: accent.withValues(alpha: opacity)),
                      ),
                    ),
                  );
                },
              );
            }),
          Container(
            width: 120,
            height: 120,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  accent.withValues(alpha: 0.95),
                  accent.withValues(alpha: 0.45),
                ],
              ),
              boxShadow: [
                BoxShadow(color: accent.withValues(alpha: 0.35), blurRadius: 36, spreadRadius: 2),
              ],
            ),
            alignment: Alignment.center,
            child: Text(
              initials.isNotEmpty ? initials : 'AG',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 40,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _WaveBars extends StatelessWidget {
  const _WaveBars({required this.controller, required this.accent});

  final AnimationController controller;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        return Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: List.generate(12, (index) {
            final phase = (controller.value + index * 0.08) % 1;
            final height = 8 + math.sin(phase * math.pi * 2).abs() * 28;
            return Container(
              width: 4,
              height: height,
              margin: const EdgeInsets.symmetric(horizontal: 2.5),
              decoration: BoxDecoration(
                color: accent.withValues(alpha: 0.55 + phase * 0.35),
                borderRadius: BorderRadius.circular(999),
              ),
            );
          }),
        );
      },
    );
  }
}

class _IncomingActions extends StatelessWidget {
  const _IncomingActions({
    required this.accent,
    required this.onDecline,
    required this.onAccept,
  });

  final Color accent;
  final Future<void> Function() onDecline;
  final Future<void> Function() onAccept;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: [
        _RoundActionButton(
          icon: Icons.call_end_rounded,
          label: 'Ablehnen',
          color: const Color(0xFFEF4444),
          onTap: onDecline,
        ),
        _RoundActionButton(
          icon: Icons.call_rounded,
          label: 'Annehmen',
          color: const Color(0xFF10B981),
          onTap: onAccept,
          glow: accent,
        ),
      ],
    );
  }
}

class _ActiveControls extends StatelessWidget {
  const _ActiveControls({
    required this.accent,
    required this.muted,
    required this.speakerOn,
    required this.onToggleMute,
    required this.onToggleSpeaker,
    required this.onHangup,
  });

  final Color accent;
  final bool muted;
  final bool speakerOn;
  final Future<void> Function() onToggleMute;
  final Future<void> Function() onToggleSpeaker;
  final Future<void> Function() onHangup;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            _MiniControl(
              icon: muted ? Icons.mic_off_rounded : Icons.mic_rounded,
              label: muted ? 'Stumm' : 'Mikro',
              active: muted,
              onTap: onToggleMute,
            ),
            const SizedBox(width: 28),
            _MiniControl(
              icon: speakerOn ? Icons.volume_up_rounded : Icons.hearing_rounded,
              label: speakerOn ? 'Lautsp.' : 'Ohrhörer',
              active: speakerOn,
              onTap: onToggleSpeaker,
            ),
          ],
        ),
        const SizedBox(height: 28),
        _RoundActionButton(
          icon: Icons.call_end_rounded,
          label: 'Auflegen',
          color: const Color(0xFFEF4444),
          onTap: onHangup,
        ),
      ],
    );
  }
}

class _MiniControl extends StatelessWidget {
  const _MiniControl({
    required this.icon,
    required this.label,
    required this.active,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool active;
  final Future<void> Function() onTap;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Material(
          color: active ? Colors.white.withValues(alpha: 0.18) : Colors.white.withValues(alpha: 0.08),
          shape: const CircleBorder(),
          child: InkWell(
            customBorder: const CircleBorder(),
            onTap: () { unawaited(onTap()); },
            child: SizedBox(
              width: 58,
              height: 58,
              child: Icon(icon, color: Colors.white),
            ),
          ),
        ),
        const SizedBox(height: 8),
        Text(label, style: TextStyle(color: Colors.white.withValues(alpha: 0.75), fontSize: 12)),
      ],
    );
  }
}

class _RoundActionButton extends StatelessWidget {
  const _RoundActionButton({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
    this.glow,
  });

  final IconData icon;
  final String label;
  final Color color;
  final Future<void> Function() onTap;
  final Color? glow;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Material(
          elevation: 0,
          color: color,
          shape: const CircleBorder(),
          child: InkWell(
            customBorder: const CircleBorder(),
            onTap: () { unawaited(onTap()); },
            child: Container(
              width: 74,
              height: 74,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: color,
                boxShadow: glow != null
                    ? [BoxShadow(color: glow!.withValues(alpha: 0.45), blurRadius: 24, spreadRadius: 1)]
                    : null,
              ),
              child: Icon(icon, color: Colors.white, size: 32),
            ),
          ),
        ),
        const SizedBox(height: 10),
        Text(label, style: TextStyle(color: Colors.white.withValues(alpha: 0.82), fontWeight: FontWeight.w600)),
      ],
    );
  }
}

class _EndedHint extends StatelessWidget {
  const _EndedHint({required this.note});

  final String note;

  @override
  Widget build(BuildContext context) {
    return Text(
      note,
      style: TextStyle(color: Colors.white.withValues(alpha: 0.7), fontSize: 15),
    );
  }
}
