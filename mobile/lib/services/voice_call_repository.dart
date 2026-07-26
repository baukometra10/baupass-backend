import 'dart:async';
import 'dart:math' as math;

import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:open_file/open_file.dart';
import 'package:path_provider/path_provider.dart';

import '../core/api_client.dart';
import '../core/session_store.dart';

class VoiceCallRepository {
  VoiceCallRepository(this._api);

  final ApiClient _api;

  static const Map<String, dynamic> hdAudioConstraints = {
    'audio': {
      'echoCancellation': true,
      'noiseSuppression': true,
      'autoGainControl': true,
      'channelCount': 1,
      'sampleRate': 48000,
    },
    'video': false,
  };

  static Map<String, dynamic> cameraOnlyConstraints({
    String facingMode = 'user',
    String tier = 'hd',
  }) {
    final sd = tier.toLowerCase() == 'sd';
    return {
      'audio': false,
      'video': {
        'facingMode': facingMode,
        'width': {'ideal': sd ? 640 : 1280},
        'height': {'ideal': sd ? 480 : 720},
        'frameRate': {'ideal': sd ? 24 : 30},
      },
    };
  }

  static const Map<String, dynamic> offerOptions = {
    'offerToReceiveAudio': true,
    'offerToReceiveVideo': true,
    'voiceActivityDetection': true,
  };

  Future<Map<String, dynamic>?> incomingCall(WorkerSession session) async {
    final data = await _api.getJson(
      '/api/worker-app/chat/calls/incoming',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final call = data['call'];
    if (call is Map<String, dynamic>) return call;
    if (call is Map) return Map<String, dynamic>.from(call);
    return null;
  }

  Future<List<Map<String, dynamic>>> recentEvents(
    WorkerSession session, {
    String sinceId = '',
    int limit = 25,
  }) async {
    var path = '/api/worker-app/chat/events/recent?limit=$limit';
    if (sinceId.isNotEmpty) path += '&since_id=${Uri.encodeComponent(sinceId)}';
    final data = await _api.getJson(
      path,
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final rows = data['events'];
    if (rows is! List) return const [];
    return rows.map((row) => Map<String, dynamic>.from(row as Map)).toList();
  }

  Future<Map<String, dynamic>?> fetchCall(WorkerSession session, String callId) async {
    final data = await _api.getJson(
      '/api/worker-app/chat/calls/${Uri.encodeComponent(callId)}',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final call = data['call'];
    if (call is Map<String, dynamic>) return call;
    if (call is Map) return Map<String, dynamic>.from(call);
    return null;
  }

  Future<Map<String, dynamic>> startWorkerCall(WorkerSession session) async {
    final data = await _api.postJson(
      '/api/worker-app/chat/calls',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: const {},
    );
    return Map<String, dynamic>.from(data['call'] as Map? ?? data);
  }

  Future<Map<String, dynamic>> acceptCall(WorkerSession session, String callId) async {
    final data = await _api.postJson(
      '/api/worker-app/chat/calls/$callId/accept',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: const {},
    );
    return Map<String, dynamic>.from(data['call'] as Map? ?? data);
  }

  Future<void> declineCall(WorkerSession session, String callId) async {
    await _api.postJson(
      '/api/worker-app/chat/calls/$callId/decline',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: const {},
    );
  }

  Future<void> endCall(WorkerSession session, String callId, {String reason = 'hangup'}) async {
    await _api.postJson(
      '/api/worker-app/chat/calls/$callId/end',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: {'reason': reason},
    );
  }

  Future<void> sendSignal(
    WorkerSession session,
    String callId, {
    required String type,
    required Map<String, dynamic> payload,
  }) async {
    await _api.postJson(
      '/api/worker-app/chat/calls/$callId/signal',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: {'type': type, 'payload': payload},
    );
  }

  Future<({List<Map<String, dynamic>> signals, Map<String, dynamic>? call})> pollSignalsWithCall(
    WorkerSession session,
    String callId, {
    String sinceId = '',
  }) async {
    var path = '/api/worker-app/chat/calls/$callId/signals';
    if (sinceId.isNotEmpty) path += '?since_id=${Uri.encodeComponent(sinceId)}';
    final data = await _api.getJson(
      path,
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final rows = data['signals'];
    final signals = rows is List
        ? rows.map((row) => Map<String, dynamic>.from(row as Map)).toList()
        : <Map<String, dynamic>>[];
    final callRaw = data['call'];
    final call = callRaw is Map ? Map<String, dynamic>.from(callRaw) : null;
    return (signals: signals, call: call);
  }

  Future<List<Map<String, dynamic>>> pollSignals(
    WorkerSession session,
    String callId, {
    String sinceId = '',
  }) async {
    var path = '/api/worker-app/chat/calls/$callId/signals';
    if (sinceId.isNotEmpty) path += '?since_id=${Uri.encodeComponent(sinceId)}';
    final data = await _api.getJson(
      path,
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final rows = data['signals'];
    if (rows is! List) return const [];
    return rows.map((row) => Map<String, dynamic>.from(row as Map)).toList();
  }

  List<Map<String, dynamic>> iceServersFromCall(Map<String, dynamic> call) {
    final raw = call['iceServers'];
    if (raw is! List) {
      return const [
        {'urls': 'stun:stun.l.google.com:19302'},
        {'urls': 'stun:stun1.l.google.com:19302'},
      ];
    }
    return raw.map((item) {
      if (item is Map) return Map<String, dynamic>.from(item);
      return {'urls': item.toString()};
    }).toList();
  }

  Map<String, dynamic> peerConfig(Map<String, dynamic> call) {
    return {
      'iceServers': iceServersFromCall(call),
      'sdpSemantics': 'unified-plan',
      'iceCandidatePoolSize': 4,
    };
  }
}

class WorkerVoiceCallSession {
  WorkerVoiceCallSession({
    required this.repo,
    required this.session,
    required this.call,
    required this.onState,
    this.onRemoteStream,
    this.onLocalStream,
    this.onAudioLevels,
    this.onConnectionDiag,
    this.onCameraIntent,
    this.onCameraState,
    this.onCallImage,
    this.displayName = 'Mitarbeiter',
  });

  final VoiceCallRepository repo;
  final WorkerSession session;
  final Map<String, dynamic> call;
  final void Function(String state) onState;
  final void Function(MediaStream stream)? onRemoteStream;
  final void Function(MediaStream? stream, bool cameraOn, {bool preview})? onLocalStream;
  final void Function(double local, double remote)? onAudioLevels;
  final void Function(String summary)? onConnectionDiag;
  final void Function(Map<String, dynamic> payload)? onCameraIntent;
  final void Function(Map<String, dynamic> payload)? onCameraState;
  final void Function(Map<String, dynamic> payload)? onCallImage;
  final String displayName;

  RTCPeerConnection? _pc;
  MediaStream? _localStream;
  MediaStream? _remoteStream;
  Timer? _pollTimer;
  Timer? _meterTimer;
  String _lastSignalId = '';
  bool _ended = false;
  bool _muted = false;
  bool _cameraOn = false;
  bool _cameraPreviewing = false;
  MediaStream? _previewStream;
  bool _blurEnabled = false;
  bool _screenSharing = false;
  MediaStreamTrack? _cameraTrackBeforeShare;
  MediaStream? _screenStream;
  MediaRecorder? _recorder;
  String? _recordPath;
  bool _recording = false;
  bool _remoteHasVideo = false;
  String _facingMode = 'user';
  String _videoQuality = 'hd';
  int _qualityBadStreak = 0;
  int _qualityGoodStreak = 0;
  int? _lastQualityBytes;
  double? _lastQualityTs;
  DateTime? _lastQualityAdaptAt;
  bool _deferredOffer = false;
  bool _offerSent = false;
  bool _makingOffer = false;
  final List<Map<String, dynamic>> _pendingIce = <Map<String, dynamic>>[];

  String get callId => (call['id'] ?? call['callId'] ?? '').toString();
  bool get cameraOn => _cameraOn;
  bool get cameraPreviewing => _cameraPreviewing;
  bool get blurEnabled => _blurEnabled;
  bool get screenSharing => _screenSharing;
  bool get isRecording => _recording;
  bool get remoteHasVideo => _remoteHasVideo;
  String get facingMode => _facingMode;
  String get videoQuality => _videoQuality;
  MediaStream? get localStream => _localStream;
  MediaStream? get previewStream => _previewStream;

  void _refreshRemoteHasVideo() {
    final tracks = _remoteStream?.getVideoTracks() ?? const <MediaStreamTrack>[];
    _remoteHasVideo = tracks.any((t) => t.enabled);
  }

  Future<void> _setupPeerConnection() async {
    _pc = await createPeerConnection(repo.peerConfig(call));
    _localStream = await navigator.mediaDevices.getUserMedia(VoiceCallRepository.hdAudioConstraints);
    for (final track in _localStream!.getTracks()) {
      await _pc!.addTrack(track, _localStream!);
    }
    _emitLocal(preview: false);
    _pc!.onTrack = (event) {
      if (event.streams.isNotEmpty) {
        _remoteStream = event.streams.first;
        _refreshRemoteHasVideo();
        onRemoteStream?.call(_remoteStream!);
        onState('connected');
      }
    };
    _pc!.onIceCandidate = (candidate) {
      if (candidate.candidate == null || candidate.candidate!.isEmpty) return;
      unawaited(repo.sendSignal(
        session,
        callId,
        type: 'ice-candidate',
        payload: candidate.toMap(),
      ));
    };
    _pc!.onConnectionState = (state) {
      if (state == RTCPeerConnectionState.RTCPeerConnectionStateConnected) {
        onState('connected');
      } else if (state == RTCPeerConnectionState.RTCPeerConnectionStateFailed) {
        onState('ended');
      }
    };
    _pc!.onIceConnectionState = (state) {
      if (state == RTCIceConnectionState.RTCIceConnectionStateConnected ||
          state == RTCIceConnectionState.RTCIceConnectionStateCompleted) {
        onState('connected');
      } else if (state == RTCIceConnectionState.RTCIceConnectionStateFailed) {
        onState('ended');
      }
    };
  }

  Future<void> startOutgoing() async {
    onState('ringing');
    _deferredOffer = true;
    _offerSent = false;
    _startPolling();
  }

  Future<void> _sendOfferAfterAccept() async {
    if (_offerSent || _ended) return;
    _offerSent = true;
    onState('connecting');
    await _setupPeerConnection();
    _makingOffer = true;
    try {
      final offer = await _pc!.createOffer(VoiceCallRepository.offerOptions);
      await _pc!.setLocalDescription(offer);
      await repo.sendSignal(
        session,
        callId,
        type: 'offer',
        payload: {'type': offer.type, 'sdp': offer.sdp},
      );
    } finally {
      _makingOffer = false;
    }
    _startMeters();
  }

  Future<void> _renegotiate() async {
    final pc = _pc;
    if (pc == null || _ended) return;
    _makingOffer = true;
    try {
      final offer = await pc.createOffer(VoiceCallRepository.offerOptions);
      await pc.setLocalDescription(offer);
      await repo.sendSignal(
        session,
        callId,
        type: 'offer',
        payload: {'type': offer.type, 'sdp': offer.sdp},
      );
    } finally {
      _makingOffer = false;
    }
  }

  void _emitLocal({bool preview = false}) {
    final stream = preview ? _previewStream : _localStream;
    final on = preview ? true : _cameraOn;
    onLocalStream?.call(stream, on, preview: preview);
  }

  Future<bool> startCameraPreview() async {
    final pc = _pc;
    if (pc == null || _ended) throw StateError('call_not_connected');
    if (_cameraOn) return true;
    if (_cameraPreviewing && _previewStream != null) {
      _emitLocal(preview: true);
      return true;
    }
    try {
      final camStream = await navigator.mediaDevices.getUserMedia(
        VoiceCallRepository.cameraOnlyConstraints(facingMode: _facingMode, tier: _videoQuality),
      );
      _previewStream = camStream;
      _cameraPreviewing = true;
      _emitLocal(preview: true);
      return true;
    } catch (e) {
      _cameraPreviewing = false;
      _previewStream = null;
      rethrow;
    }
  }

  Future<void> cancelCameraPreview() async {
    _cameraPreviewing = false;
    final preview = _previewStream;
    _previewStream = null;
    if (preview != null) {
      for (final t in preview.getTracks()) {
        try {
          await t.stop();
        } catch (_) {}
      }
      try {
        await preview.dispose();
      } catch (_) {}
    }
    _emitLocal(preview: false);
  }

  Future<bool> confirmCameraPreview() async {
    final pc = _pc;
    if (pc == null || _ended) throw StateError('call_not_connected');
    if (_cameraOn) return true;
    if (_previewStream == null) {
      await startCameraPreview();
    }
    final camStream = _previewStream;
    final videoTrack = camStream?.getVideoTracks().isNotEmpty == true
        ? camStream!.getVideoTracks().first
        : null;
    if (videoTrack == null) throw StateError('camera_failed');

    await repo.sendSignal(
      session,
      callId,
      type: 'camera_intent',
      payload: {'enabled': true, 'fromName': displayName},
    );
    await Future<void>.delayed(const Duration(milliseconds: 320));

    _localStream ??= camStream;
    if (_localStream != camStream && camStream != null) {
      await _localStream!.addTrack(videoTrack);
    }
    final senders = await pc.getSenders();
    final hasVideo = senders.any((s) => s.track?.kind == 'video');
    if (!hasVideo) {
      await pc.addTrack(videoTrack, _localStream!);
    }
    await _renegotiate();
    _cameraPreviewing = false;
    _previewStream = null;
    _cameraOn = true;
    _qualityBadStreak = 0;
    _qualityGoodStreak = 0;
    try {
      await repo.sendSignal(
        session,
        callId,
        type: 'camera_state',
        payload: {'enabled': true, 'fromName': displayName},
      );
    } catch (_) {}
    _emitLocal(preview: false);
    return true;
  }

  Future<bool> setCameraEnabled(bool enabled, {bool skipPreview = false}) async {
    final pc = _pc;
    if (pc == null || _ended) {
      throw StateError('call_not_connected');
    }
    final next = enabled;
    if (!next) {
      if (_cameraPreviewing) {
        await cancelCameraPreview();
        return false;
      }
      if (!_cameraOn) return false;
      if (_blurEnabled) await setBlurEnabled(false);
      if (_screenSharing) await setScreenShareEnabled(false);
      for (final sender in await pc.getSenders()) {
        final track = sender.track;
        if (track?.kind == 'video') {
          try {
            await track?.stop();
          } catch (_) {}
          try {
            await pc.removeTrack(sender);
          } catch (_) {}
        }
      }
      for (final track in List<MediaStreamTrack>.from(_localStream?.getVideoTracks() ?? const [])) {
        try {
          await track.stop();
          await _localStream?.removeTrack(track);
        } catch (_) {}
      }
      await _renegotiate();
      _cameraOn = false;
      _videoQuality = 'hd';
      _qualityBadStreak = 0;
      _qualityGoodStreak = 0;
      _lastQualityBytes = null;
      _lastQualityTs = null;
      try {
        await repo.sendSignal(
          session,
          callId,
          type: 'camera_state',
          payload: {'enabled': false, 'fromName': displayName},
        );
      } catch (_) {}
      _emitLocal(preview: false);
      return false;
    }
    if (_cameraOn) return true;
    if (!skipPreview) {
      await startCameraPreview();
      return false; // previewing, not published yet
    }
    return confirmCameraPreview();
  }

  Future<MediaStreamTrack?> _videoSenderTrack() async {
    final pc = _pc;
    if (pc == null) return null;
    for (final sender in await pc.getSenders()) {
      if (sender.track?.kind == 'video') return sender.track;
    }
    return null;
  }

  Future<void> _replaceOutgoingVideoTrack(MediaStreamTrack newTrack, {bool stopOld = true}) async {
    final pc = _pc;
    if (pc == null) return;
    RTCRtpSender? videoSender;
    for (final sender in await pc.getSenders()) {
      if (sender.track?.kind == 'video') {
        videoSender = sender;
        break;
      }
    }
    final oldTrack = videoSender?.track ??
        (_localStream?.getVideoTracks().isNotEmpty == true ? _localStream!.getVideoTracks().first : null);
    if (videoSender != null) {
      await videoSender.replaceTrack(newTrack);
    } else {
      _localStream ??= await createLocalMediaStream('local');
      await _localStream!.addTrack(newTrack);
      await pc.addTrack(newTrack, _localStream!);
      await _renegotiate();
    }
    if (_localStream != null && !_localStream!.getVideoTracks().contains(newTrack)) {
      await _localStream!.addTrack(newTrack);
    }
    if (stopOld && oldTrack != null && oldTrack.id != newTrack.id) {
      try {
        await oldTrack.stop();
        await _localStream?.removeTrack(oldTrack);
      } catch (_) {}
    }
  }

  Future<bool> setBlurEnabled(bool enabled) async {
    final next = enabled;
    if ((!_cameraOn && !_cameraPreviewing) || _screenSharing) {
      _blurEnabled = false;
      return false;
    }
    if (next == _blurEnabled) return _blurEnabled;
    _blurEnabled = next;
    // Soften capture when blur is on (peer sees softer image); UI also applies ImageFilter.
    if (_cameraOn) {
      final track = await _videoSenderTrack();
      if (track != null) {
        try {
          await track.applyConstraints(
            VoiceCallRepository.cameraOnlyConstraints(
              facingMode: _facingMode,
              tier: next ? 'sd' : _videoQuality,
            )['video'] as Map<String, dynamic>,
          );
        } catch (_) {}
      }
    }
    if (onConnectionDiag != null) {
      onConnectionDiag!(next ? 'Blur an' : 'Blur aus');
    }
    _emitLocal(preview: _cameraPreviewing && !_cameraOn);
    return _blurEnabled;
  }

  Future<bool> setScreenShareEnabled(bool enabled) async {
    final pc = _pc;
    if (pc == null || _ended) return false;
    final next = enabled;
    if (next == _screenSharing) return _screenSharing;
    if (!next) {
      final restore = _cameraTrackBeforeShare;
      _cameraTrackBeforeShare = null;
      final screen = _screenStream;
      _screenStream = null;
      if (screen != null) {
        for (final t in screen.getTracks()) {
          try {
            await t.stop();
          } catch (_) {}
        }
        try {
          await screen.dispose();
        } catch (_) {}
      }
      _screenSharing = false;
      if (restore != null) {
        await _replaceOutgoingVideoTrack(restore, stopOld: false);
        _cameraOn = true;
      } else if (_cameraOn) {
        await setCameraEnabled(false);
        await setCameraEnabled(true, skipPreview: true);
      }
      _emitLocal(preview: false);
      return false;
    }

    MediaStream display;
    try {
      display = await navigator.mediaDevices.getDisplayMedia({
        'video': true,
        'audio': false,
      });
    } catch (e) {
      throw StateError('screen_share_denied');
    }
    final screenTrack = display.getVideoTracks().isNotEmpty ? display.getVideoTracks().first : null;
    if (screenTrack == null) throw StateError('screen_share_failed');
    if (_blurEnabled) await setBlurEnabled(false);
    _cameraTrackBeforeShare = await _videoSenderTrack();
    _screenStream = display;
    if (!_cameraOn && _cameraTrackBeforeShare == null) {
      await repo.sendSignal(
        session,
        callId,
        type: 'camera_intent',
        payload: {'enabled': true, 'fromName': displayName},
      );
      await Future<void>.delayed(const Duration(milliseconds: 200));
      _localStream ??= display;
      if (!_localStream!.getVideoTracks().contains(screenTrack)) {
        await _localStream!.addTrack(screenTrack);
      }
      await pc.addTrack(screenTrack, _localStream!);
      await _renegotiate();
      _cameraOn = true;
    } else {
      await _replaceOutgoingVideoTrack(screenTrack, stopOld: false);
    }
    _screenSharing = true;
    try {
      screenTrack.onEnded = () {
        unawaited(setScreenShareEnabled(false));
      };
    } catch (_) {
      /* platform may not support onEnded */
    }
    _emitLocal(preview: false);
    return true;
  }

  Future<bool> startRecording() async {
    if (_recording) return true;
    final video = (_remoteStream?.getVideoTracks().isNotEmpty == true)
        ? _remoteStream!.getVideoTracks().first
        : (_localStream?.getVideoTracks().isNotEmpty == true)
            ? _localStream!.getVideoTracks().first
            : null;
    final dir = await getTemporaryDirectory();
    const ext = 'mp4';
    _recordPath = '${dir.path}/workpass-call-${DateTime.now().millisecondsSinceEpoch}.$ext';
    _recorder = MediaRecorder();
    try {
      await _recorder!.start(
        _recordPath!,
        videoTrack: video,
        audioChannel: RecorderAudioChannel.OUTPUT,
      );
      _recording = true;
      if (onConnectionDiag != null) onConnectionDiag!('Aufnahme läuft');
      return true;
    } catch (_) {
      try {
        await _recorder!.start(
          _recordPath!,
          videoTrack: video,
          audioChannel: RecorderAudioChannel.INPUT,
        );
        _recording = true;
        if (onConnectionDiag != null) onConnectionDiag!('Aufnahme läuft');
        return true;
      } catch (e) {
        _recorder = null;
        _recordPath = null;
        _recording = false;
        throw StateError('recording_failed');
      }
    }
  }

  Future<bool> stopRecording({bool openFile = true}) async {
    if (!_recording || _recorder == null) return false;
    try {
      await _recorder!.stop();
    } catch (_) {}
    _recorder = null;
    _recording = false;
    final path = _recordPath;
    _recordPath = null;
    if (openFile && path != null && path.isNotEmpty) {
      try {
        await OpenFile.open(path);
      } catch (_) {}
    }
    if (onConnectionDiag != null) onConnectionDiag!('Aufnahme gespeichert');
    return true;
  }

  Future<String> switchCamera() async {
    final pc = _pc;
    if (pc == null || _ended || (!_cameraOn && !_cameraPreviewing)) {
      throw StateError('camera_not_active');
    }
    final previewMode = _cameraPreviewing && !_cameraOn;
    final tracks = previewMode
        ? (_previewStream?.getVideoTracks() ?? const <MediaStreamTrack>[])
        : (_localStream?.getVideoTracks() ?? const <MediaStreamTrack>[]);
    if (tracks.isEmpty) {
      throw StateError('camera_not_active');
    }
    final current = tracks.first;
    try {
      await Helper.switchCamera(current);
      final settings = current.getSettings();
      final facing = (settings['facingMode'] ?? '').toString();
      if (facing == 'environment' || facing == 'user') {
        _facingMode = facing;
      } else {
        _facingMode = _facingMode == 'user' ? 'environment' : 'user';
      }
      _emitLocal(preview: previewMode);
      return _facingMode;
    } catch (_) {
      if (previewMode) {
        final nextFacing = _facingMode == 'environment' ? 'user' : 'environment';
        final camStream = await navigator.mediaDevices.getUserMedia(
          VoiceCallRepository.cameraOnlyConstraints(facingMode: nextFacing, tier: _videoQuality),
        );
        final old = _previewStream;
        _previewStream = camStream;
        _facingMode = nextFacing;
        if (old != null) {
          for (final t in old.getTracks()) {
            try {
              await t.stop();
            } catch (_) {}
          }
          try {
            await old.dispose();
          } catch (_) {}
        }
        _emitLocal(preview: true);
        return _facingMode;
      }
      final nextFacing = _facingMode == 'environment' ? 'user' : 'environment';
      final camStream = await navigator.mediaDevices.getUserMedia(
        VoiceCallRepository.cameraOnlyConstraints(facingMode: nextFacing, tier: _videoQuality),
      );
      final newTrack = camStream.getVideoTracks().first;
      final senders = await pc.getSenders();
      RTCRtpSender? videoSender;
      for (final sender in senders) {
        if (sender.track?.kind == 'video') {
          videoSender = sender;
          break;
        }
      }
      if (videoSender != null) {
        await videoSender.replaceTrack(newTrack);
      } else {
        await pc.addTrack(newTrack, _localStream ?? camStream);
        await _renegotiate();
      }
      try {
        await current.stop();
        await _localStream?.removeTrack(current);
      } catch (_) {}
      _localStream ??= camStream;
      await _localStream!.addTrack(newTrack);
      for (final t in camStream.getTracks()) {
        if (t != newTrack) {
          try {
            await t.stop();
          } catch (_) {}
        }
      }
      _facingMode = nextFacing;
      _emitLocal(preview: false);
      return _facingMode;
    }
  }

  Future<void> sendCallImage(String dataUrl, {String? fromName}) async {
    final raw = dataUrl.trim();
    if (!raw.startsWith('data:image/')) {
      throw ArgumentError('invalid_image');
    }
    if (raw.length > 300000) {
      throw ArgumentError('call_image_too_large');
    }
      final name = (fromName ?? displayName).toString().trim();
      await repo.sendSignal(
        session,
        callId,
        type: 'call_image',
        payload: {
          'dataUrl': raw,
          'fromName': name.length > 80 ? name.substring(0, 80) : name,
          'mime': 'image/jpeg',
        },
      );
    }

  Future<void> acceptAndConnect() async {
    onState('connecting');
    await repo.acceptCall(session, callId);
    await _setupPeerConnection();
    _startPolling();
    _startMeters();
  }

  void _startMeters() {
    _meterTimer?.cancel();
    _meterTimer = Timer.periodic(const Duration(milliseconds: 90), (_) async {
      final pc = _pc;
      if (_ended || pc == null) return;
      try {
        final stats = await pc.getStats();
        var local = 0.0;
        var remote = 0.0;
        String iceState = '${pc.iceConnectionState ?? ''}';
        String selectedType = '';
        for (final report in stats) {
          final values = report.values;
          final type = report.type;
          if (type == 'media-source' && values['kind'] == 'audio') {
            final level = values['audioLevel'];
            if (level is num) local = math.max(local, level.toDouble().clamp(0.0, 1.0));
          }
          if (type == 'inbound-rtp' && (values['kind'] == 'audio' || values['mediaType'] == 'audio')) {
            final level = values['audioLevel'];
            if (level is num) remote = math.max(remote, level.toDouble().clamp(0.0, 1.0));
          }
          if (type == 'candidate-pair' && (values['state'] == 'succeeded' || values['nominated'] == true)) {
            final localCandId = values['localCandidateId']?.toString() ?? '';
            if (localCandId.isNotEmpty) {
              for (final other in stats) {
                if (other.id == localCandId) {
                  selectedType = (other.values['candidateType'] ?? other.values['type'] ?? '').toString();
                }
              }
            }
          }
        }
        if (_muted) local = 0;
        onAudioLevels?.call(local, remote);
        if (onConnectionDiag != null && !_cameraOn) {
          final bits = <String>[
            if (iceState.isNotEmpty) 'ICE: $iceState',
            if (selectedType.isNotEmpty) 'Pfad: $selectedType',
          ];
          if (bits.isNotEmpty) onConnectionDiag!(bits.join(' · '));
        }
        final now = DateTime.now();
        if (_cameraOn &&
            (_lastQualityAdaptAt == null || now.difference(_lastQualityAdaptAt!) > const Duration(seconds: 3))) {
          _lastQualityAdaptAt = now;
          unawaited(_adaptVideoQuality(stats.toList()));
        }
      } catch (_) {
        /* ignore transient stats errors */
      }
    });
  }

  void _stopMeters() {
    _meterTimer?.cancel();
    _meterTimer = null;
    onAudioLevels?.call(0, 0);
  }

  Future<void> _applyVideoTier(String tier) async {
    final next = tier.toLowerCase() == 'sd' ? 'sd' : 'hd';
    if (next == _videoQuality) return;
    final track = await _videoSenderTrack();
    if (track == null) return;
    final constraints = VoiceCallRepository.cameraOnlyConstraints(
      facingMode: _facingMode,
      tier: next,
    )['video'];
    try {
      await track.applyConstraints(constraints as Map<String, dynamic>);
    } catch (_) {
      try {
        await track.applyConstraints({
          'width': next == 'sd' ? 640 : 1280,
          'height': next == 'sd' ? 480 : 720,
          'frameRate': next == 'sd' ? 24 : 30,
        });
      } catch (_) {
        return;
      }
    }
    _videoQuality = next;
    if (onConnectionDiag != null) {
      onConnectionDiag!(next == 'sd' ? 'Video: 480p' : 'Video: 720p');
    }
  }

  Future<void> _adaptVideoQuality(List<StatsReport> stats) async {
    if (_ended || !_cameraOn || _pc == null || _screenSharing) return;
    var rttMs = 0.0;
    var lossRatio = 0.0;
    var bitrate = 0.0;
    var packetsLost = 0;
    var packetsSent = 0;
    var bytesSent = 0;
    var timestamp = 0.0;
    for (final report in stats) {
      final values = report.values;
      if (report.type == 'candidate-pair' &&
          (values['state'] == 'succeeded' || values['nominated'] == true)) {
        final rtt = values['currentRoundTripTime'];
        if (rtt is num && rtt > 0) {
          rttMs = math.max(rttMs, rtt.toDouble() * 1000);
        }
      }
      if (report.type == 'outbound-rtp' &&
          (values['kind'] == 'video' || values['mediaType'] == 'video')) {
        final lost = values['packetsLost'];
        final sent = values['packetsSent'];
        final bytes = values['bytesSent'];
        final ts = values['timestamp'];
        if (lost is num) packetsLost += lost.toInt();
        if (sent is num) packetsSent += sent.toInt();
        if (bytes is num) bytesSent = bytes.toInt();
        if (ts is num) timestamp = ts.toDouble();
      }
    }
    final total = packetsLost + packetsSent;
    if (total > 20) lossRatio = packetsLost / total;
    if (_lastQualityBytes != null && _lastQualityTs != null && timestamp > _lastQualityTs!) {
      final dt = (timestamp - _lastQualityTs!) / 1000;
      if (dt > 0) {
        bitrate = ((bytesSent - _lastQualityBytes!) * 8) / dt;
      }
    }
    _lastQualityBytes = bytesSent;
    _lastQualityTs = timestamp;

    final bad = rttMs > 420 || lossRatio > 0.05 || (bitrate > 0 && bitrate < 180000);
    final good = rttMs > 0 && rttMs < 220 && lossRatio < 0.015 && (bitrate == 0 || bitrate > 450000);
    if (bad) {
      _qualityBadStreak += 1;
      _qualityGoodStreak = 0;
    } else if (good) {
      _qualityGoodStreak += 1;
      _qualityBadStreak = 0;
    } else {
      _qualityBadStreak = math.max(0, _qualityBadStreak - 1);
      _qualityGoodStreak = math.max(0, _qualityGoodStreak - 1);
    }
    if (_videoQuality != 'sd' && _qualityBadStreak >= 2) {
      await _applyVideoTier('sd');
    } else if (_videoQuality == 'sd' && _qualityGoodStreak >= 3) {
      await _applyVideoTier('hd');
    }
  }

  Future<void> setMuted(bool muted) async {
    _muted = muted;
    final stream = _localStream;
    if (stream == null) return;
    for (final track in stream.getAudioTracks()) {
      track.enabled = !muted;
    }
  }

  Future<void> setSpeakerphone(bool enabled) async {
    try {
      await Helper.setSpeakerphoneOn(enabled);
    } catch (_) {
      /* platform may not support */
    }
  }

  Future<void> _flushPendingIce(RTCPeerConnection pc) async {
    final queued = List<Map<String, dynamic>>.from(_pendingIce);
    _pendingIce.clear();
    for (final payload in queued) {
      try {
        await pc.addCandidate(RTCIceCandidate(
          payload['candidate']?.toString(),
          payload['sdpMid']?.toString(),
          payload['sdpMLineIndex'] is int
              ? payload['sdpMLineIndex'] as int
              : int.tryParse('${payload['sdpMLineIndex']}'),
        ));
      } catch (_) {
        /* ignore */
      }
    }
  }

  Future<void> _applySignal(Map<String, dynamic> signal) async {
    final type = (signal['signalType'] ?? '').toString();
    final payloadRaw = signal['payload'];
    final payload = payloadRaw is Map
        ? Map<String, dynamic>.from(payloadRaw)
        : <String, dynamic>{};
    if (type == 'camera_intent') {
      onCameraIntent?.call(payload);
      return;
    }
    if (type == 'camera_state') {
      onCameraState?.call(payload);
      return;
    }
    if (type == 'call_image') {
      onCallImage?.call(payload);
      return;
    }
    final pc = _pc;
    if (pc == null) return;
    if (type == 'offer') {
      // Worker is the polite peer — always accept remote offers (incl. renegotiation).
      if (_makingOffer) {
        /* glare: still accept as polite */
      }
      await pc.setRemoteDescription(RTCSessionDescription(payload['sdp']?.toString() ?? '', payload['type']?.toString() ?? 'offer'));
      await _flushPendingIce(pc);
      final answer = await pc.createAnswer(VoiceCallRepository.offerOptions);
      await pc.setLocalDescription(answer);
      await repo.sendSignal(
        session,
        callId,
        type: 'answer',
        payload: {'type': answer.type, 'sdp': answer.sdp},
      );
      onState('connecting');
    } else if (type == 'answer') {
      await pc.setRemoteDescription(RTCSessionDescription(payload['sdp']?.toString() ?? '', payload['type']?.toString() ?? 'answer'));
      await _flushPendingIce(pc);
      onState('connecting');
    } else if (type == 'ice-candidate') {
      final hasRemote = (await pc.getRemoteDescription()) != null;
      if (!hasRemote) {
        _pendingIce.add(payload);
        return;
      }
      try {
        await pc.addCandidate(RTCIceCandidate(
          payload['candidate']?.toString(),
          payload['sdpMid']?.toString(),
          payload['sdpMLineIndex'] is int ? payload['sdpMLineIndex'] as int : int.tryParse('${payload['sdpMLineIndex']}'),
        ));
      } catch (_) {
        /* ignore duplicate */
      }
    } else if (type == 'hangup') {
      await end('remote_hangup');
    }
  }

  void _startPolling() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(milliseconds: 700), (_) async {
      if (_ended) return;
      try {
        final result = await repo.pollSignalsWithCall(session, callId, sinceId: _lastSignalId);
        final callStatus = result.call;
        if (callStatus != null) {
          final status = (callStatus['status'] ?? '').toString();
          if (status == 'declined' || status == 'missed' || status == 'ended') {
            await end(callStatus['endReason']?.toString() ?? status);
            return;
          }
          if (_deferredOffer && !_offerSent && status == 'accepted') {
            onState('accepted');
            await _sendOfferAfterAccept();
          }
        }
        for (final signal in result.signals) {
          try {
            await _applySignal(signal);
            _lastSignalId = (signal['id'] ?? _lastSignalId).toString();
          } catch (_) {
            /* keep cursor so a failed signal can be retried next tick */
          }
        }
      } catch (_) {
        /* ignore transient poll errors */
      }
    });
  }

  Future<void> decline() async {
    await repo.declineCall(session, callId);
    await end('declined');
  }

  Future<void> end([String reason = 'hangup']) async {
    if (_ended) return;
    _ended = true;
    _pollTimer?.cancel();
    _stopMeters();
    _pendingIce.clear();
    try {
      await repo.endCall(session, callId, reason: reason);
    } catch (_) {
      /* ignore */
    }
    await _pc?.close();
    _pc = null;
    await _localStream?.dispose();
    _localStream = null;
    _remoteStream = null;
    try {
      if (_recording) await stopRecording(openFile: false);
    } catch (_) {}
    try {
      await cancelCameraPreview();
    } catch (_) {}
    if (_screenStream != null) {
      for (final t in _screenStream!.getTracks()) {
        try {
          await t.stop();
        } catch (_) {}
      }
      try {
        await _screenStream!.dispose();
      } catch (_) {}
      _screenStream = null;
    }
    _cameraOn = false;
    _cameraPreviewing = false;
    _blurEnabled = false;
    _screenSharing = false;
    _cameraTrackBeforeShare = null;
    _recording = false;
    _recorder = null;
    _recordPath = null;
    _remoteHasVideo = false;
    _facingMode = 'user';
    _videoQuality = 'hd';
    _qualityBadStreak = 0;
    _qualityGoodStreak = 0;
    _lastQualityBytes = null;
    _lastQualityTs = null;
    _lastQualityAdaptAt = null;
    onState('ended');
  }

  MediaStream? get remoteStream => _remoteStream;
  bool get isMuted => _muted;
}
