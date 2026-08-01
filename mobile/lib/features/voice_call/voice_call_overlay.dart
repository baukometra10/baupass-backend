import 'dart:async';
import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';

import '../../core/app_strings.dart';
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
  bool _chromeVisible = true;
  Timer? _chromeHideTimer;
  Offset? _pipOffset;

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
    _chromeHideTimer?.cancel();
    _pulseController.dispose();
    _waveController.dispose();
    _disposeRenderers();
    super.dispose();
  }

  void _onControllerChanged() {
    _syncRenderers();
    if (_showVideoStage) {
      _bumpChrome();
    } else {
      _pipOffset = null;
    }
    if (mounted) setState(() {});
  }

  void _bumpChrome() {
    _chromeHideTimer?.cancel();
    if (!_chromeVisible && mounted) setState(() => _chromeVisible = true);
    else _chromeVisible = true;
    if (!_showVideoStage || widget.controller.cameraPreviewing) return;
    _chromeHideTimer = Timer(const Duration(milliseconds: 3200), () {
      if (!mounted || !_showVideoStage || widget.controller.cameraPreviewing) return;
      setState(() => _chromeVisible = false);
    });
  }

  MediaStream? _boundRemoteStream;
  int _boundRemoteVideoCount = -1;
  MediaStream? _boundLocalStream;

  Future<void> _bindRenderer(RTCVideoRenderer renderer, MediaStream? stream) async {
    // Re-bind when track set changes — srcObject identity alone is not enough
    // after late video tracks are added to an existing MediaStream.
    if (identical(renderer.srcObject, stream) && stream != null) {
      // Force refresh by toggling when video track count changed.
    }
    renderer.srcObject = null;
    renderer.srcObject = stream;
  }

  Future<void> _syncRenderers() async {
    try {
      final remote = widget.controller.rtcSession?.remoteStream;
      final previewing = widget.controller.cameraPreviewing;
      final local = previewing
          ? widget.controller.rtcSession?.previewStream
          : widget.controller.rtcSession?.localStream;
      final localLive = widget.controller.cameraOn || previewing;
      final remoteVideoCount = remote?.getVideoTracks().length ?? 0;
      final remoteHasVideo = remoteVideoCount > 0 || widget.controller.remoteHasVideo;

      _remoteRenderer ??= RTCVideoRenderer();
      final remoteRenderer = _remoteRenderer;
      if (remoteRenderer == null) return;
      if (!_remoteRendererReady) {
        await remoteRenderer.initialize();
        if (!mounted || !identical(_remoteRenderer, remoteRenderer)) return;
        _remoteRendererReady = true;
      }
      // Prefer employer/remote video whenever any remote video track exists.
      // Bug: worker camera ON kept local stream on the main view and never
      // switched back when admin video arrived late.
      final hasRemoteVideo = remoteVideoCount > 0 || remoteHasVideo;
      if (remote != null && hasRemoteVideo && !previewing) {
        final wasSelfPreview = _boundRemoteVideoCount == -2;
        final changed = wasSelfPreview ||
            !identical(_boundRemoteStream, remote) ||
            _boundRemoteVideoCount != remoteVideoCount ||
            remoteRenderer.srcObject != remote;
        if (changed) {
          await _bindRenderer(remoteRenderer, remote);
          await Future<void>.delayed(const Duration(milliseconds: 50));
          if (!mounted || !identical(_remoteRenderer, remoteRenderer)) return;
          await _bindRenderer(remoteRenderer, remote);
          _boundRemoteStream = remote;
          _boundRemoteVideoCount = remoteVideoCount;
        }
      } else if (local != null && localLive) {
        // Alone / waiting for peer video — temporary self preview on main.
        if (!identical(_boundRemoteStream, local) || _boundRemoteVideoCount != -2) {
          await _bindRenderer(remoteRenderer, local);
          _boundRemoteStream = local;
          _boundRemoteVideoCount = -2;
        }
      } else if (remoteRenderer.srcObject != null) {
        remoteRenderer.srcObject = null;
        _boundRemoteStream = null;
        _boundRemoteVideoCount = -1;
      }

      // Zoom-style: keep self on PiP renderer whenever camera is live.
      if (local != null && localLive) {
        _localRenderer ??= RTCVideoRenderer();
        final localRenderer = _localRenderer;
        if (localRenderer == null) return;
        if (!_localRendererReady) {
          await localRenderer.initialize();
          if (!mounted || !identical(_localRenderer, localRenderer)) return;
          _localRendererReady = true;
        }
        if (!identical(_boundLocalStream, local)) {
          await _bindRenderer(localRenderer, local);
          _boundLocalStream = local;
        }
      } else {
        final localRenderer = _localRenderer;
        if (localRenderer != null) {
          localRenderer.srcObject = null;
          _boundLocalStream = null;
        }
      }

      if (mounted) setState(() {});
    } catch (_) {
      /* keep overlay alive without video */
    }
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
    return widget.controller.cameraOn ||
        widget.controller.cameraPreviewing ||
        remoteHasVideo ||
        widget.controller.remoteHasVideo;
  }

  bool get _remoteHasVideo {
    return widget.controller.rtcSession?.remoteStream?.getVideoTracks().isNotEmpty == true ||
        widget.controller.remoteHasVideo;
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

    final showVideo = _showVideoStage &&
        (isConnected || isConnecting || widget.controller.cameraOn || widget.controller.cameraPreviewing);
    final previewing = widget.controller.cameraPreviewing;
    final remoteOnMain = showVideo && _remoteHasVideo && !previewing;
    final mirrorMain = showVideo && !remoteOnMain && (widget.controller.cameraOn || previewing);
    final blurLocal = widget.controller.blurEnabled;
    final showSelfPip = showVideo &&
        !previewing &&
        widget.controller.cameraOn &&
        _localRenderer != null &&
        _localRendererReady &&
        (remoteOnMain || _remoteHasVideo);

    return SizedBox.expand(
      child: Material(
        color: Colors.transparent,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: showVideo ? _bumpChrome : null,
          child: Stack(
            fit: StackFit.expand,
            children: [
              if (!showVideo) _AmbientBackground(accent: _accent, pulse: _pulseController),
              if (showVideo && _remoteRenderer != null && _remoteRendererReady)
                Positioned.fill(
                  child: _maybeBlurVideo(
                    enabled: blurLocal && (previewing || !_remoteHasVideo),
                    child: RTCVideoView(
                      _remoteRenderer!,
                      objectFit: RTCVideoViewObjectFit.RTCVideoViewObjectFitCover,
                      mirror: mirrorMain,
                    ),
                  ),
                )
              else if (showVideo)
                const ColoredBox(color: Color(0xFF0B141A)),
              if (showVideo)
                Positioned.fill(
                  child: IgnorePointer(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [
                            Colors.black.withValues(alpha: _chromeVisible ? 0.45 : 0.15),
                            Colors.transparent,
                            Colors.black.withValues(alpha: _chromeVisible ? 0.78 : 0.25),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              if (showSelfPip)
                Builder(
                  builder: (context) {
                    final size = MediaQuery.sizeOf(context);
                    const pipW = 108.0;
                    const pipH = 144.0;
                    // Zoom-like default: top-end PiP (RTL-aware via Directionality).
                    final rtl = Directionality.of(context) == TextDirection.rtl;
                    final defaultLeft = rtl ? 16.0 : size.width - pipW - 16;
                    final defaultTop = MediaQuery.paddingOf(context).top + 56;
                    final left = (_pipOffset?.dx ?? defaultLeft).clamp(8.0, size.width - pipW - 8);
                    final top = (_pipOffset?.dy ?? defaultTop).clamp(8.0, size.height - pipH - 8);
                    return Positioned(
                      left: left,
                      top: top,
                      width: pipW,
                      height: pipH,
                      child: GestureDetector(
                        onPanUpdate: (details) {
                          setState(() {
                            final next = (_pipOffset ?? Offset(defaultLeft, defaultTop)) + details.delta;
                            _pipOffset = Offset(
                              next.dx.clamp(8.0, size.width - pipW - 8),
                              next.dy.clamp(8.0, size.height - pipH - 8),
                            );
                          });
                        },
                        onPanEnd: (_) {
                          setState(() {
                            final cur = _pipOffset ?? Offset(defaultLeft, defaultTop);
                            final toLeft = cur.dx + pipW / 2 < size.width / 2;
                            final toTop = cur.dy + pipH / 2 < size.height / 2;
                            _pipOffset = Offset(
                              toLeft ? 8.0 : size.width - pipW - 8,
                              toTop ? 8.0 : size.height - pipH - 8,
                            );
                          });
                        },
                        child: DecoratedBox(
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(14),
                            border: Border.all(color: Colors.white.withValues(alpha: 0.4), width: 2),
                            boxShadow: const [
                              BoxShadow(color: Colors.black54, blurRadius: 18, offset: Offset(0, 8)),
                            ],
                          ),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(12),
                            child: _maybeBlurVideo(
                              enabled: blurLocal,
                              child: RTCVideoView(
                                _localRenderer!,
                                mirror: true,
                                objectFit: RTCVideoViewObjectFit.RTCVideoViewObjectFitCover,
                              ),
                            ),
                          ),
                        ),
                      ),
                    );
                  },
                ),
              if (previewing && isConnected)
                Positioned(
                  left: 16,
                  right: 16,
                  bottom: 28,
                  child: SafeArea(
                    child: _CameraPreviewBar(
                      accent: _accent,
                      note: widget.controller.statusNote,
                      onConfirm: widget.controller.confirmCameraPreview,
                      onCancel: widget.controller.cancelCameraPreview,
                      onRetry: widget.controller.startCameraPreview,
                      onFlip: widget.controller.flipCamera,
                      onHangup: widget.controller.hangup,
                    ),
                  ),
                ),
              SafeArea(
                child: AnimatedOpacity(
                  opacity: !showVideo || _chromeVisible ? 1 : 0,
                  duration: const Duration(milliseconds: 220),
                  child: IgnorePointer(
                    ignoring: showVideo && !_chromeVisible,
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                      child: Column(
                        children: [
                          if (!showVideo) _SecureBadge(accent: _accent),
                          if (peerBanner.isNotEmpty) ...[
                            const SizedBox(height: 10),
                            _PeerCameraBanner(message: peerBanner, accent: _accent),
                          ],
                          if (showVideo) ...[
                            Align(
                              alignment: Alignment.topCenter,
                              child: Column(
                                children: [
                                  Text(
                                    widget.controller.isOutgoing
                                        ? t('employer', 'Arbeitgeber')
                                        : widget.controller.callerLabel,
                                    textAlign: TextAlign.center,
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 16,
                                      fontWeight: FontWeight.w700,
                                      shadows: [Shadow(blurRadius: 10, color: Colors.black54)],
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    statusLine,
                                    style: TextStyle(
                                      color: Colors.white.withValues(alpha: 0.8),
                                      fontSize: 13,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const Spacer(),
                          ] else ...[
                            const Spacer(flex: 2),
                            _CallerAvatar(
                              label: widget.controller.callerLabel,
                              accent: _accent,
                              pulse: _pulseController,
                              ringing: showRingAnim,
                            ),
                            const SizedBox(height: 22),
                            Text(
                              widget.controller.isOutgoing
                                  ? t('employer', 'Arbeitgeber')
                                  : widget.controller.callerLabel,
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 28,
                                fontWeight: FontWeight.w700,
                                letterSpacing: -0.3,
                                shadows: [Shadow(blurRadius: 12, color: Colors.black54)],
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              statusLine,
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: Colors.white.withValues(alpha: 0.85),
                                fontSize: 16,
                                fontWeight: FontWeight.w500,
                                shadows: const [Shadow(blurRadius: 10, color: Colors.black54)],
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
                              const SizedBox(height: 18),
                              _WaveBars(controller: _waveController, accent: _accent),
                            ] else if (showRingAnim) ...[
                              const SizedBox(height: 28),
                              _WaveBars(controller: _waveController, accent: _accent),
                            ],
                            const Spacer(flex: 3),
                          ],
                          if (isRinging && !widget.controller.isOutgoing)
                            _IncomingActions(
                              accent: _accent,
                              onDecline: widget.controller.decline,
                              onAccept: widget.controller.accept,
                            )
                          else if (isConnected && !previewing)
                            _ActiveControls(
                              accent: _accent,
                              muted: widget.controller.muted,
                              speakerOn: widget.controller.speakerOn,
                              cameraOn: widget.controller.cameraOn,
                              blurEnabled: widget.controller.blurEnabled,
                              screenSharing: widget.controller.screenSharing,
                              recording: widget.controller.isRecording,
                              onToggleMute: widget.controller.toggleMute,
                              onToggleSpeaker: widget.controller.toggleSpeaker,
                              onToggleCamera: widget.controller.toggleCamera,
                              onFlipCamera: widget.controller.flipCamera,
                              onToggleBlur: widget.controller.toggleBlur,
                              onToggleScreenShare: widget.controller.toggleScreenShare,
                              onToggleRecording: widget.controller.toggleRecording,
                              onShareImage: widget.controller.shareImage,
                              onHangup: widget.controller.hangup,
                            )
                          else if (isConnected && previewing)
                            const SizedBox(height: 120)
                          else if (isConnecting)
                            _ConnectingActions(
                              accent: _accent,
                              note: widget.controller.statusNote,
                              muted: widget.controller.muted,
                              speakerOn: widget.controller.speakerOn,
                              onToggleMute: widget.controller.toggleMute,
                              onToggleSpeaker: widget.controller.toggleSpeaker,
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
      ),
    );
  }

  Widget _maybeBlurVideo({required bool enabled, required Widget child}) {
    if (!enabled) return child;
    return ImageFiltered(
      imageFilter: ImageFilter.blur(sigmaX: 14, sigmaY: 14),
      child: child,
    );
  }
}

class _CameraPreviewBar extends StatelessWidget {
  const _CameraPreviewBar({
    required this.accent,
    required this.note,
    required this.onConfirm,
    required this.onCancel,
    required this.onRetry,
    required this.onFlip,
    required this.onHangup,
  });

  final Color accent;
  final String note;
  final Future<void> Function() onConfirm;
  final Future<void> Function() onCancel;
  final Future<void> Function() onRetry;
  final Future<void> Function() onFlip;
  final Future<void> Function() onHangup;

  @override
  Widget build(BuildContext context) {
    final retry = note.contains('verweigert') ||
        note.contains('belegt') ||
        note.contains('gefunden') ||
        note.contains('nicht aktiviert');
    return Material(
      color: Colors.black.withValues(alpha: 0.72),
      borderRadius: BorderRadius.circular(18),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              retry ? note : 'Kamera-Vorschau — nur du siehst dieses Bild',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.92),
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 12),
            Wrap(
              alignment: WrapAlignment.center,
              spacing: 10,
              runSpacing: 10,
              children: [
                if (retry)
                  FilledButton.tonal(
                    onPressed: () => unawaited(onRetry()),
                    child: const Text('Erneut versuchen'),
                  )
                else ...[
                  OutlinedButton(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.white,
                      side: BorderSide(color: Colors.white.withValues(alpha: 0.35)),
                    ),
                    onPressed: () => unawaited(onCancel()),
                    child: const Text('Abbrechen'),
                  ),
                  FilledButton(
                    style: FilledButton.styleFrom(backgroundColor: accent),
                    onPressed: () => unawaited(onConfirm()),
                    child: const Text('Freigeben'),
                  ),
                  IconButton.filledTonal(
                    onPressed: () => unawaited(onFlip()),
                    icon: const Icon(Icons.cameraswitch_rounded),
                    tooltip: 'Kamera drehen',
                  ),
                ],
                IconButton(
                  onPressed: () => unawaited(onHangup()),
                  icon: const Icon(Icons.call_end_rounded, color: Color(0xFFE53935)),
                  tooltip: 'Auflegen',
                ),
              ],
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
    required this.muted,
    required this.speakerOn,
    required this.onToggleMute,
    required this.onToggleSpeaker,
    required this.onHangup,
  });

  final Color accent;
  final String note;
  final bool muted;
  final bool speakerOn;
  final Future<void> Function() onToggleMute;
  final Future<void> Function() onToggleSpeaker;
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
        const SizedBox(height: 22),
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
    required this.blurEnabled,
    required this.screenSharing,
    required this.recording,
    required this.onToggleMute,
    required this.onToggleSpeaker,
    required this.onToggleCamera,
    required this.onFlipCamera,
    required this.onToggleBlur,
    required this.onToggleScreenShare,
    required this.onToggleRecording,
    required this.onShareImage,
    required this.onHangup,
  });

  final Color accent;
  final bool muted;
  final bool speakerOn;
  final bool cameraOn;
  final bool blurEnabled;
  final bool screenSharing;
  final bool recording;
  final Future<void> Function() onToggleMute;
  final Future<void> Function() onToggleSpeaker;
  final Future<void> Function() onToggleCamera;
  final Future<void> Function() onFlipCamera;
  final Future<void> Function() onToggleBlur;
  final Future<void> Function() onToggleScreenShare;
  final Future<void> Function() onToggleRecording;
  final Future<void> Function() onShareImage;
  final Future<void> Function() onHangup;

  @override
  Widget build(BuildContext context) {
    // Zoom-style: compact floating pill — mic / cam / flip / speaker / more / hangup.
    return Material(
      color: Colors.black.withValues(alpha: 0.42),
      borderRadius: BorderRadius.circular(28),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _ZoomControl(
              icon: muted ? Icons.mic_off_rounded : Icons.mic_rounded,
              active: muted,
              onTap: onToggleMute,
            ),
            const SizedBox(width: 8),
            _ZoomControl(
              icon: cameraOn ? Icons.videocam_rounded : Icons.videocam_off_rounded,
              active: cameraOn,
              onTap: onToggleCamera,
            ),
            if (cameraOn) ...[
              const SizedBox(width: 8),
              _ZoomControl(
                icon: Icons.cameraswitch_rounded,
                onTap: onFlipCamera,
              ),
            ],
            const SizedBox(width: 8),
            _ZoomControl(
              icon: speakerOn ? Icons.volume_up_rounded : Icons.hearing_rounded,
              active: speakerOn,
              onTap: onToggleSpeaker,
            ),
            const SizedBox(width: 8),
            PopupMenuButton<String>(
              tooltip: '…',
              color: const Color(0xFF1E293B),
              onSelected: (v) {
                switch (v) {
                  case 'blur':
                    unawaited(onToggleBlur());
                    break;
                  case 'screen':
                    unawaited(onToggleScreenShare());
                    break;
                  case 'rec':
                    unawaited(onToggleRecording());
                    break;
                  case 'image':
                    unawaited(onShareImage());
                    break;
                }
              },
              itemBuilder: (_) => [
                PopupMenuItem(
                  value: 'blur',
                  enabled: cameraOn,
                  child: Text(
                    blurEnabled ? 'Blur off' : 'Blur',
                    style: const TextStyle(color: Colors.white),
                  ),
                ),
                PopupMenuItem(
                  value: 'screen',
                  child: Text(
                    screenSharing ? 'Stop share' : 'Share',
                    style: const TextStyle(color: Colors.white),
                  ),
                ),
                PopupMenuItem(
                  value: 'rec',
                  child: Text(
                    recording ? 'Stop rec' : 'Record',
                    style: const TextStyle(color: Colors.white),
                  ),
                ),
                const PopupMenuItem(
                  value: 'image',
                  child: Text('Image', style: TextStyle(color: Colors.white)),
                ),
              ],
              child: Material(
                color: Colors.white.withValues(alpha: 0.12),
                shape: const CircleBorder(),
                child: const SizedBox(
                  width: 52,
                  height: 52,
                  child: Icon(Icons.more_horiz_rounded, color: Colors.white, size: 24),
                ),
              ),
            ),
            const SizedBox(width: 12),
            _ZoomControl(
              icon: Icons.call_end_rounded,
              danger: true,
              onTap: onHangup,
            ),
          ],
        ),
      ),
    );
  }
}

class _ZoomControl extends StatelessWidget {
  const _ZoomControl({
    required this.icon,
    this.active = false,
    this.danger = false,
    this.onTap,
  });

  final IconData icon;
  final bool active;
  final bool danger;
  final Future<void> Function()? onTap;

  @override
  Widget build(BuildContext context) {
    final bg = danger
        ? const Color(0xFFE53935)
        : Colors.white.withValues(alpha: active ? 0.28 : 0.12);
    return Material(
      color: bg,
      shape: const CircleBorder(),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onTap == null ? null : () => unawaited(onTap!()),
        child: SizedBox(
          width: 52,
          height: 52,
          child: Icon(icon, color: Colors.white, size: 24),
        ),
      ),
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
