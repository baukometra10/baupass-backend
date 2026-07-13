import 'dart:async';

import 'package:flutter_webrtc/flutter_webrtc.dart';

import '../core/api_client.dart';
import '../core/session_store.dart';

class VoiceCallRepository {
  VoiceCallRepository(this._api);

  final ApiClient _api;

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
      ];
    }
    return raw.map((item) {
      if (item is Map) return Map<String, dynamic>.from(item);
      return {'urls': item.toString()};
    }).toList();
  }
}

class WorkerVoiceCallSession {
  WorkerVoiceCallSession({
    required this.repo,
    required this.session,
    required this.call,
    required this.onState,
  });

  final VoiceCallRepository repo;
  final WorkerSession session;
  final Map<String, dynamic> call;
  final void Function(String state) onState;

  RTCPeerConnection? _pc;
  MediaStream? _localStream;
  MediaStream? _remoteStream;
  Timer? _pollTimer;
  String _lastSignalId = '';
  bool _ended = false;

  String get callId => (call['id'] ?? call['callId'] ?? '').toString();

  Future<void> acceptAndConnect() async {
    onState('connecting');
    await repo.acceptCall(session, callId);
    final config = {'iceServers': repo.iceServersFromCall(call)};
    _pc = await createPeerConnection(config);
    _localStream = await navigator.mediaDevices.getUserMedia({'audio': true, 'video': false});
    for (final track in _localStream!.getTracks()) {
      await _pc!.addTrack(track, _localStream!);
    }
    _pc!.onTrack = (event) {
      if (event.streams.isNotEmpty) {
        _remoteStream = event.streams.first;
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
    _startPolling();
    onState('ringing');
  }

  Future<void> _applySignal(Map<String, dynamic> signal) async {
    final pc = _pc;
    if (pc == null) return;
    final type = (signal['signalType'] ?? '').toString();
    final payloadRaw = signal['payload'];
    final payload = payloadRaw is Map
        ? Map<String, dynamic>.from(payloadRaw)
        : <String, dynamic>{};
    if (type == 'offer') {
      await pc.setRemoteDescription(RTCSessionDescription(payload['sdp']?.toString() ?? '', payload['type']?.toString() ?? 'offer'));
      final answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      await repo.sendSignal(
        session,
        callId,
        type: 'answer',
        payload: {'type': answer.type, 'sdp': answer.sdp},
      );
      onState('connected');
    } else if (type == 'answer') {
      await pc.setRemoteDescription(RTCSessionDescription(payload['sdp']?.toString() ?? '', payload['type']?.toString() ?? 'answer'));
      onState('connected');
    } else if (type == 'ice-candidate') {
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
    _pollTimer = Timer.periodic(const Duration(milliseconds: 900), (_) async {
      if (_ended) return;
      try {
        final signals = await repo.pollSignals(session, callId, sinceId: _lastSignalId);
        for (final signal in signals) {
          _lastSignalId = (signal['id'] ?? _lastSignalId).toString();
          await _applySignal(signal);
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
    onState('ended');
  }

  MediaStream? get remoteStream => _remoteStream;
}
