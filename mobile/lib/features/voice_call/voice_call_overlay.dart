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
  RTCVideoRenderer? _localRenderer;
  bool _remoteRendererReady = false;
  bool _localRendererReady = false;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(vsync: this, duration: const Duration(milliseconds: 2200))
      ..repeat();
    _waveController = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat(reverse: true);
    widget.controller.addListener(_onControllerChanged);
    _syncRenderers();
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onControllerChanged);
    _pulseController.dispose();
    _waveController.dispose();
    _disposeRenderers();
    super.dispose();
  }

  void _onControllerChanged() {
    _syncRenderers();
    if (mounted) setState(() {});
  }

  Future<void> _syncRenderers() async {
    final remote = widget.controller.rtcSession?.remoteStream;
    final local = widget.controller.rtcSession?.localStream;
    final cameraOn = widget.controller.cameraOn;
    final remoteHasVideo = remote?.getVideoTracks().isNotEmpty == true;

    if (remote != null && remoteHasVideo) {
      _remoteRenderer ??= RTCVideoRenderer();
      if (!_remoteRendererReady) {
        await _remoteRenderer!.initialize();
        _remoteRendererReady = true;
      }
      _remoteRenderer!.srcObject = remote;
    } else if (_remoteRenderer != null) {
      _remoteRenderer!.srcObject = null;
    }

    if (local != null && cameraOn) {
      _localRenderer ??= RTCVideoRenderer();
      if (!_localRendererReady) {
        await _localRenderer!.initialize();
        _localRendererReady = true;
      }
      _localRenderer!.srcObject = local;
    } else if (_localRenderer != null) {
      _localRenderer!.srcObject = null;
    }

    if (mounted) setState(() {});
  }

  Future<void> _disposeRenderers() async {
    final remote = _remoteRenderer;
    final local = _localRenderer;
    _remoteRenderer = null;
    _localRenderer = null;
    _remoteRendererReady = false;
    _localRendererReady = false;
    await remote?.dispose();
    await local?.dispose();
  }

  bool get _showVideoStage {
    final remoteHasVideo = widget.controller.rtcSession?.remoteStream?.getVideoTracks().isNotEmpty == true;
    return widget.controller.cameraOn || remoteHasVideo;
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
    final isOutgoing = phase == VoiceCallUiPhase.outgoing;
    final isConnecting = phase == VoiceCallUiPhase.connecting;
    final isConnected = phase == VoiceCallUiPhase.connected;
    final isEnded = phase == VoiceCallUiPhase.ended;
    final showRingAnim = isRinging || isOutgoing || isConnecting;
    final ringLeft = widget.controller.ringRemaining;
    final ringCountdown = ringLeft.inSeconds > 0
        ? '${ringLeft.inMinutes.remainder(60).toString().padLeft(2, '0')}:${ringLeft.inSeconds.remainder(60).toString().padLeft(2, '0')}'
        : '';

    String statusLine;
    if (isConnected) {
      statusLine = _formatDuration(widget.controller.elapsed);
    } else if ((isRinging || isOutgoing) && ringCountdown.isNotEmpty) {
      statusLine = '${widget.controller.statusNote} · $ringCountdown';
    } else {
      statusLine = widget.controller.statusNote;
    }

    final peerBanner = widget.controller.peerCameraBanner;
    final incomingImage = widget.controller.incomingImageDataUrl;

    return SizedBox.expand(
      child: Material(
        color: Colors.transparent,
        child: Stack(
          fit: StackFit.expand,
          children: [
            _AmbientBackground(accent: _accent, pulse: _pulseController),
            if (_showVideoStage && _remoteRenderer != null && _remoteRendererReady)
              Positioned.fill(
                child: RTCVideoView(
                  _remoteRenderer!,
                  objectFit: RTCVideoViewObjectFit.RTCVideoViewObjectFitCover,
                  mirror: false,
                ),
              ),
            if (_showVideoStage)
              Positioned.fill(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        Colors.black.withValues(alpha: 0.35),
                        Colors.transparent,
                        Colors.black.withValues(alpha: 0.72),
                      ],
                    ),
                  ),
                ),
              ),
            if (widget.controller.cameraOn && _localRenderer != null && _localRendererReady)
              Positioned(
                right: 18,
                top: 88,
                width: 108,
                height: 148,
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(14),
                  child: RTCVideoView(
                    _localRenderer!,
                    mirror: true,
                    objectFit: RTCVideoViewObjectFit.RTCVideoViewObjectFitCover,
                  ),
                ),
              ),
            SafeArea(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
                child: Column(
                  children: [
                    _SecureBadge(accent: _accent),
                    if (peerBanner.isNotEmpty) ...[
                      const SizedBox(height: 12),
                      _PeerCameraBanner(message: peerBanner, accent: _accent),
                    ],
                    const Spacer(flex: 2),
                    if (!_showVideoStage)
                      _CallerAvatar(
                        label: widget.controller.callerLabel,
                        accent: _accent,
                        pulse: _pulseController,
                        ringing: showRingAnim,
                      ),
                    if (!_showVideoStage) const SizedBox(height: 22),
                    Text(
                      widget.controller.isOutgoing ? 'Arbeitgeber' : widget.controller.callerLabel,
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
                      statusLine,
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
                      const SizedBox(height: 22),
                      _CallLevelMeters(
                        local: widget.controller.localLevel,
                        remote: widget.controller.remoteLevel,
                        accent: _accent,
                      ),
                      if (widget.controller.connectionDiag.isNotEmpty) ...[
                        const SizedBox(height: 10),
                        Text(
                          widget.controller.connectionDiag,
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            color: Colors.white.withValues(alpha: 0.5),
                            fontSize: 11,
                            fontFamily: 'monospace',
                          ),
                        ),
                      ],
                      if (!_showVideoStage) ...[
                        const SizedBox(height: 18),
                        _WaveBars(controller: _waveController, accent: _accent),
                      ],
                    ] else if (showRingAnim) ...[
                      const SizedBox(height: 28),
                      _WaveBars(controller: _waveController, accent: _accent),
                    ],
                    const Spacer(flex: 3),
                    if (isRinging && !widget.controller.isOutgoing)
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
                        cameraOn: widget.controller.cameraOn,
                        onToggleMute: widget.controller.toggleMute,
                        onToggleSpeaker: widget.controller.toggleSpeaker,
                        onToggleCamera: widget.controller.toggleCamera,
                        onShareImage: widget.controller.shareImage,
                        onHangup: widget.controller.hangup,
                      )
                    else if (isConnecting)
                      _ConnectingActions(
                        accent: _accent,
                        note: widget.controller.statusNote,
                        onHangup: widget.controller.hangup,
                      )
                    else if (isOutgoing || (isRinging && widget.controller.isOutgoing))
                      _OutgoingActions(
                        onCancel: widget.controller.decline,
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
            if (incomingImage != null && incomingImage.isNotEmpty)
              Positioned.fill(
                child: _IncomingImageSheet(
                  dataUrl: incomingImage,
                  fromName: widget.controller.incomingImageFrom,
                  onClose: widget.controller.clearIncomingImage,
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _PeerCameraBanner extends StatelessWidget {
  const _PeerCameraBanner({required this.message, required this.accent});

  final String message;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFFFBBF24).withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFFBBF24).withValues(alpha: 0.5)),
      ),
      child: Row(
        children: [
          Icon(Icons.videocam_rounded, color: accent, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: const TextStyle(
                color: Color(0xFFFDE68A),
                fontWeight: FontWeight.w600,
                fontSize: 13.5,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _IncomingImageSheet extends StatelessWidget {
  const _IncomingImageSheet({
    required this.dataUrl,
    required this.fromName,
    required this.onClose,
  });

  final String dataUrl;
  final String fromName;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final bytes = Uri.parse(dataUrl).data?.contentAsBytes();
    return Material(
      color: Colors.black.withValues(alpha: 0.72),
      child: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Container(
              margin: const EdgeInsets.all(20),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFF111B21),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: Colors.white24),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (bytes != null)
                    ClipRRect(
                      borderRadius: BorderRadius.circular(10),
                      child: Image.memory(bytes, fit: BoxFit.contain),
                    ),
                  const SizedBox(height: 10),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          'Bild von ${fromName.isEmpty ? 'Arbeitgeber' : fromName}',
                          style: const TextStyle(color: Colors.white70, fontWeight: FontWeight.w600),
                        ),
                      ),
                      TextButton(
                        onPressed: onClose,
                        child: const Text('Schließen'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
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
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                Color(0xFF0B141A),
                Color(0xFF111B21),
                Color(0xFF0B141A),
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
      width: 180,
      height: 180,
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
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  Color(0xFF00A884),
                  Color(0xFF128C7E),
                ],
              ),
              boxShadow: const [
                BoxShadow(color: Color(0x6600A884), blurRadius: 36, spreadRadius: 2),
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

class _CallLevelMeters extends StatelessWidget {
  const _CallLevelMeters({
    required this.local,
    required this.remote,
    required this.accent,
  });

  final double local;
  final double remote;
  final Color accent;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 280,
      child: Column(
        children: [
          _meterRow('Sie', local, accent),
          const SizedBox(height: 8),
          _meterRow('Arbeitgeber', remote, const Color(0xFF34D399)),
        ],
      ),
    );
  }

  Widget _meterRow(String label, double level, Color color) {
    return Row(
      children: [
        SizedBox(
          width: 72,
          child: Text(
            label,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.72),
              fontSize: 11,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.4,
            ),
          ),
        ),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: LinearProgressIndicator(
              minHeight: 8,
              value: level.clamp(0.0, 1.0),
              backgroundColor: Colors.white.withValues(alpha: 0.12),
              color: color,
            ),
          ),
        ),
      ],
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
          color: const Color(0xFFE53935),
          onTap: onDecline,
        ),
        _RoundActionButton(
          icon: Icons.call_rounded,
          label: 'Annehmen',
          color: const Color(0xFF00A884),
          onTap: onAccept,
          glow: const Color(0xFF00A884),
        ),
      ],
    );
  }
}

class _ConnectingActions extends StatelessWidget {
  const _ConnectingActions({
    required this.accent,
    required this.note,
    required this.onHangup,
  });

  final Color accent;
  final String note;
  final Future<void> Function() onHangup;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          note.isNotEmpty ? note : 'Verbindung wird aufgebaut…',
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.white.withValues(alpha: 0.85), fontSize: 15, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 16),
        SizedBox(
          width: 28,
          height: 28,
          child: CircularProgressIndicator(strokeWidth: 2.5, color: accent),
        ),
        const SizedBox(height: 28),
        _RoundActionButton(
          icon: Icons.call_end_rounded,
          label: 'Auflegen',
          color: const Color(0xFFE53935),
          onTap: onHangup,
        ),
      ],
    );
  }
}

class _OutgoingActions extends StatelessWidget {
  const _OutgoingActions({required this.onCancel});

  final Future<void> Function() onCancel;

  @override
  Widget build(BuildContext context) {
    return _RoundActionButton(
      icon: Icons.call_end_rounded,
      label: 'Abbrechen',
      color: const Color(0xFFE53935),
      onTap: onCancel,
    );
  }
}

class _ActiveControls extends StatelessWidget {
  const _ActiveControls({
    required this.accent,
    required this.muted,
    required this.speakerOn,
    required this.cameraOn,
    required this.onToggleMute,
    required this.onToggleSpeaker,
    required this.onToggleCamera,
    required this.onShareImage,
    required this.onHangup,
  });

  final Color accent;
  final bool muted;
  final bool speakerOn;
  final bool cameraOn;
  final Future<void> Function() onToggleMute;
  final Future<void> Function() onToggleSpeaker;
  final Future<void> Function() onToggleCamera;
  final Future<void> Function() onShareImage;
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
            const SizedBox(width: 18),
            _MiniControl(
              icon: cameraOn ? Icons.videocam_rounded : Icons.videocam_off_rounded,
              label: cameraOn ? 'Cam aus' : 'Kamera',
              active: cameraOn,
              onTap: onToggleCamera,
            ),
            const SizedBox(width: 18),
            _MiniControl(
              icon: speakerOn ? Icons.volume_up_rounded : Icons.hearing_rounded,
              label: speakerOn ? 'Lautsp.' : 'Ohrhörer',
              active: speakerOn,
              onTap: onToggleSpeaker,
            ),
            const SizedBox(width: 18),
            _MiniControl(
              icon: Icons.image_rounded,
              label: 'Bild',
              active: false,
              onTap: onShareImage,
            ),
          ],
        ),
        const SizedBox(height: 28),
        _RoundActionButton(
          icon: Icons.call_end_rounded,
          label: 'Auflegen',
          color: const Color(0xFFE53935),
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
