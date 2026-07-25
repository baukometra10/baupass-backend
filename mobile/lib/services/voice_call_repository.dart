import 'dart:async';
import 'dart:math' as math;

import 'package:flutter_webrtc/flutter_webrtc.dart';

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

  static const Map<String, dynamic> cameraOnlyConstraints = {
    'audio': false,
    'video': {
      'facingMode': 'user',
      'mandatory': {
        'minWidth': '320',
        'minHeight': '240',
        'maxWidth': '640',
        'maxHeight': '480',
      },
    },
  };

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
  final void Function(MediaStream? stream, bool cameraOn)? onLocalStream;
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
  bool _deferredOffer = false;
  bool _offerSent = false;
  bool _makingOffer = false;
  final List<Map<String, dynamic>> _pendingIce = <Map<String, dynamic>>[];

  String get callId => (call['id'] ?? call['callId'] ?? '').toString();
  bool get cameraOn => _cameraOn;
  MediaStream? get localStream => _localStream;

  Future<void> _setupPeerConnection() async {
    _pc = await createPeerConnection(repo.peerConfig(call));
    _localStream = await navigator.mediaDevices.getUserMedia(VoiceCallRepository.hdAudioConstraints);
    for (final track in _localStream!.getTracks()) {
      await _pc!.addTrack(track, _localStream!);
    }
    onLocalStream?.call(_localStream, _cameraOn);
    _pc!.onTrack = (event) {
      if (event.streams.isNotEmpty) {
        _remoteStream = event.streams.first;
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

  Future<bool> setCameraEnabled(bool enabled) async {
    final pc = _pc;
    if (pc == null || _ended) {
      throw StateError('call_not_connected');
    }
    final next = enabled;
    if (next == _cameraOn) return _cameraOn;
    if (next) {
      await repo.sendSignal(
        session,
        callId,
        type: 'camera_intent',
        payload: {'enabled': true, 'fromName': displayName},
      );
      await Future<void>.delayed(const Duration(milliseconds: 320));
      var videoTracks = _localStream?.getVideoTracks() ?? const <MediaStreamTrack>[];
      MediaStreamTrack? videoTrack = videoTracks.isEmpty ? null : videoTracks.first;
      if (videoTrack == null || videoTrack.enabled == false) {
        final camStream = await navigator.mediaDevices.getUserMedia(VoiceCallRepository.cameraOnlyConstraints);
        videoTrack = camStream.getVideoTracks().first;
        _localStream ??= camStream;
        await _localStream!.addTrack(videoTrack);
        await pc.addTrack(videoTrack, _localStream!);
      } else {
        videoTrack.enabled = true;
      }
      await _renegotiate();
      _cameraOn = true;
    } else {
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
    }
    try {
      await repo.sendSignal(
        session,
        callId,
        type: 'camera_state',
        payload: {'enabled': _cameraOn, 'fromName': displayName},
      );
    } catch (_) {}
    onLocalStream?.call(_localStream, _cameraOn);
    return _cameraOn;
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
        if (onConnectionDiag != null) {
          final bits = <String>[
            if (iceState.isNotEmpty) 'ICE: $iceState',
            if (selectedType.isNotEmpty) 'Pfad: $selectedType',
          ];
          if (bits.isNotEmpty) onConnectionDiag!(bits.join(' · '));
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
    _cameraOn = false;
    onState('ended');
  }

  MediaStream? get remoteStream => _remoteStream;
  bool get isMuted => _muted;
}
