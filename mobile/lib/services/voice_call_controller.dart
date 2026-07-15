import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../core/session_store.dart';
import 'voice_call_repository.dart';
import 'callkit_service.dart';

enum VoiceCallUiPhase { idle, ringing, outgoing, connecting, connected, ended }

/// App-wide incoming/outgoing voice call orchestration (shows full-screen UI on any tab).
class VoiceCallController extends ChangeNotifier {
  VoiceCallController({
    required this.repo,
    CallKitService? callKit,
  }) : _callKit = callKit ?? CallKitService();

  final VoiceCallRepository repo;
  final CallKitService _callKit;

  WorkerSession? _session;
  Timer? _pollTimer;
  Timer? _eventTimer;
  Timer? _ringTimer;
  Timer? _ringTimeoutTimer;
  Timer? _ringCountdownTimer;
  DateTime? _ringStartedAt;
  static const Duration ringTimeout = Duration(seconds: 60);
  Timer? _durationTimer;
  DateTime? _connectedAt;
  String? _pendingCallId;
  String _lastEventId = '';
  WorkerVoiceCallSession? _sessionRtc;
  Map<String, dynamic>? _call;
  VoiceCallUiPhase _phase = VoiceCallUiPhase.idle;
  String _statusNote = '';
  Duration _elapsed = Duration.zero;
  bool _muted = false;
  bool _speakerOn = true;
  double _localLevel = 0;
  double _remoteLevel = 0;
  String? _lastDismissedCallId;
  bool _isOutgoing = false;

  VoiceCallUiPhase get phase => _phase;
  bool get isOutgoing => _isOutgoing;
  Duration get ringRemaining {
    final started = _ringStartedAt;
    if (started == null) return Duration.zero;
    final left = ringTimeout - DateTime.now().difference(started);
    if (left.isNegative) return Duration.zero;
    return left;
  }
  Map<String, dynamic>? get call => _call;
  String get statusNote => _statusNote;
  Duration get elapsed => _elapsed;
  bool get muted => _muted;
  bool get speakerOn => _speakerOn;
  double get localLevel => _localLevel;
  double get remoteLevel => _remoteLevel;
  bool get isActive => _phase != VoiceCallUiPhase.idle && _phase != VoiceCallUiPhase.ended;
  WorkerVoiceCallSession? get rtcSession => _sessionRtc;

  String get callerLabel {
    final call = _call;
    if (call == null) return 'Arbeitgeber';
    final name = (call['callerName'] ?? call['caller_name'] ?? '').toString().trim();
    if (name.isNotEmpty) return name;
    final company = (call['companyName'] ?? call['company_name'] ?? '').toString().trim();
    if (company.isNotEmpty) return company;
    return 'Arbeitgeber';
  }

  String get subtitleLabel {
    final call = _call;
    if (call == null) return 'Sicherer Sprachkanal';
    final company = (call['companyName'] ?? call['company_name'] ?? '').toString().trim();
    if (company.isNotEmpty) return company;
    return 'Ende-zu-Ende verschlüsselt · DTLS-SRTP';
  }

  void bind(WorkerSession session) {
    _session = session;
    unawaited(_callKit.initialize(
      onAccept: (callId) {
        if ((_call?['id'] ?? '').toString() == callId || _phase == VoiceCallUiPhase.ringing) {
          unawaited(accept());
        }
      },
      onDecline: (callId) {
        if ((_call?['id'] ?? '').toString() == callId || _phase == VoiceCallUiPhase.ringing) {
          unawaited(decline());
        }
      },
      onEnded: (callId) {
        if ((_call?['id'] ?? '').toString() == callId) {
          unawaited(decline());
        }
      },
    ));
    _startPolling();
    _startEventPolling();
  }

  void onAppResumed() {
    unawaited(_pollIncoming(force: true));
    unawaited(_pollEvents());
  }

  void unbind() {
    _pollTimer?.cancel();
    _eventTimer?.cancel();
    _ringTimer?.cancel();
    _ringTimeoutTimer?.cancel();
    _ringCountdownTimer?.cancel();
    _durationTimer?.cancel();
    unawaited(_sessionRtc?.end('dispose'));
    _sessionRtc = null;
    _session = null;
    _call = null;
    _phase = VoiceCallUiPhase.idle;
    _isOutgoing = false;
    _ringStartedAt = null;
    _lastEventId = '';
  }

  void wakeForCall(String callId) {
    final id = callId.trim();
    if (id.isEmpty) return;
    _pendingCallId = id;
    unawaited(_pollIncoming(force: true));
  }

  void _startPolling() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(milliseconds: 800), (_) {
      if (_phase == VoiceCallUiPhase.idle ||
          (_phase == VoiceCallUiPhase.ringing && !_isOutgoing)) {
        unawaited(_pollIncoming());
      }
    });
  }

  void _startEventPolling() {
    _eventTimer?.cancel();
    _eventTimer = Timer.periodic(const Duration(milliseconds: 1800), (_) {
      unawaited(_pollEvents());
    });
  }

  Future<void> _pollEvents() async {
    final session = _session;
    if (session == null) return;
    if (_phase == VoiceCallUiPhase.connecting || _phase == VoiceCallUiPhase.connected) {
      return;
    }
    try {
      final events = await repo.recentEvents(session, sinceId: _lastEventId);
      for (final evt in events) {
        final id = (evt['id'] ?? '').toString();
        if (id.isNotEmpty) _lastEventId = id;
        final type = (evt['type'] ?? evt['event_type'] ?? '').toString();
        if (!type.startsWith('voice_call.')) continue;
        final payloadRaw = evt['payload'];
        final payload = payloadRaw is Map
            ? Map<String, dynamic>.from(payloadRaw)
            : <String, dynamic>{};
        final callId = (payload['callId'] ?? payload['call_id'] ?? '').toString();
        if (type.contains('incoming') && callId.isNotEmpty) {
          _pendingCallId = callId;
          unawaited(_pollIncoming(force: true));
        }
      }
    } catch (_) {
      /* ignore transient errors */
    }
  }

  Future<void> _pollIncoming({bool force = false}) async {
    final session = _session;
    if (session == null) return;
    if (!force && (_phase == VoiceCallUiPhase.connecting || _phase == VoiceCallUiPhase.connected)) {
      return;
    }
    try {
      Map<String, dynamic>? incoming;
      final pending = _pendingCallId;
      if (pending != null && pending.isNotEmpty) {
        incoming = await repo.fetchCall(session, pending);
        _pendingCallId = null;
      }
      incoming ??= await repo.incomingCall(session);
      if (incoming == null) return;
      final callId = (incoming['id'] ?? incoming['callId'] ?? '').toString();
      if (callId.isEmpty || callId == _lastDismissedCallId) return;
      if (_phase == VoiceCallUiPhase.ringing && _call != null) {
        final currentId = (_call!['id'] ?? '').toString();
        if (currentId == callId) return;
      }
      _presentIncoming(incoming);
    } catch (_) {
      /* ignore transient errors */
    }
  }

  void _presentIncoming(Map<String, dynamic> call) {
    _call = call;
    _isOutgoing = false;
    _phase = VoiceCallUiPhase.ringing;
    _statusNote = 'Eingehender Anruf';
    _startRingFeedback();
    _startRingTimeout();
    final callId = (call['id'] ?? call['callId'] ?? '').toString();
    unawaited(_callKit.showIncomingCall(
      callId: callId,
      callerName: callerLabel,
      companyName: subtitleLabel,
    ));
    notifyListeners();
  }

  void _startRingTimeout() {
    _ringStartedAt = DateTime.now();
    _ringTimeoutTimer?.cancel();
    _ringCountdownTimer?.cancel();
    _ringTimeoutTimer = Timer(ringTimeout, () {
      if (_phase == VoiceCallUiPhase.ringing || _phase == VoiceCallUiPhase.outgoing) {
        if (_isOutgoing) {
          unawaited(hangup());
        } else {
          unawaited(decline());
        }
      }
    });
    _ringCountdownTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (_phase == VoiceCallUiPhase.ringing || _phase == VoiceCallUiPhase.outgoing) {
        notifyListeners();
      }
    });
  }

  void _clearRingTimeout() {
    _ringTimeoutTimer?.cancel();
    _ringCountdownTimer?.cancel();
    _ringTimeoutTimer = null;
    _ringCountdownTimer = null;
    _ringStartedAt = null;
  }

  Future<void> startOutgoingCall() async {
    final session = _session;
    if (session == null || isActive) return;
    _isOutgoing = true;
    _call = {'callerName': 'Arbeitgeber', 'companyName': subtitleLabel};
    _phase = VoiceCallUiPhase.outgoing;
    _statusNote = 'Wählt…';
    notifyListeners();
    try {
      final call = await repo.startWorkerCall(session);
      _call = call;
      _phase = VoiceCallUiPhase.ringing;
      _statusNote = 'Klingelt beim Arbeitgeber…';
      _startRingFeedback();
      _startRingTimeout();
      notifyListeners();
      _sessionRtc = WorkerVoiceCallSession(
        repo: repo,
        session: session,
        call: call,
        onState: _onRtcState,
        onRemoteStream: (_) => notifyListeners(),
        onAudioLevels: (local, remote) {
          _localLevel = local;
          _remoteLevel = remote;
          notifyListeners();
        },
      );
      await _sessionRtc!.startOutgoing();
      await _sessionRtc!.setSpeakerphone(_speakerOn);
    } catch (_) {
      _finishEnded('Anruf fehlgeschlagen');
    }
  }

  void _startRingFeedback() {
    _ringTimer?.cancel();
    _ringTimer = Timer.periodic(const Duration(milliseconds: 1400), (_) {
      HapticFeedback.heavyImpact();
      SystemSound.play(SystemSoundType.click);
    });
    HapticFeedback.heavyImpact();
  }

  void _stopRingFeedback() {
    _ringTimer?.cancel();
    _ringTimer = null;
  }

  Future<void> accept() async {
    final session = _session;
    final call = _call;
    if (session == null || call == null) return;
    _stopRingFeedback();
    _clearRingTimeout();
    _phase = VoiceCallUiPhase.connecting;
    _statusNote = 'Verbindung wird aufgebaut…';
    notifyListeners();

    _sessionRtc = WorkerVoiceCallSession(
      repo: repo,
      session: session,
      call: call,
      onState: _onRtcState,
      onRemoteStream: (_) => notifyListeners(),
      onAudioLevels: (local, remote) {
        _localLevel = local;
        _remoteLevel = remote;
        notifyListeners();
      },
    );
    await _sessionRtc!.acceptAndConnect();
    await _sessionRtc!.setSpeakerphone(_speakerOn);
  }

  Future<void> decline() async {
    final session = _session;
    final call = _call;
    _stopRingFeedback();
    _clearRingTimeout();
    final callId = (call?['id'] ?? '').toString();
    if (callId.isNotEmpty) {
      unawaited(_callKit.endCall(callId));
    }
    if (_isOutgoing) {
      await _sessionRtc?.end('cancelled');
      _sessionRtc = null;
      _finishEnded('Abgebrochen');
      return;
    }
    if (session != null && call != null) {
      final callId = (call['id'] ?? '').toString();
      if (callId.isNotEmpty) {
        _lastDismissedCallId = callId;
        try {
          await repo.declineCall(session, callId);
        } catch (_) {
          /* ignore */
        }
      }
    }
    await _sessionRtc?.end('declined');
    _sessionRtc = null;
    _finishEnded('Abgelehnt');
  }

  Future<void> hangup() async {
    _stopRingFeedback();
    _clearRingTimeout();
    final callId = (_call?['id'] ?? '').toString();
    if (callId.isNotEmpty) {
      unawaited(_callKit.endCall(callId));
    }
    await _sessionRtc?.end('hangup');
    _sessionRtc = null;
    _finishEnded('Anruf beendet');
  }

  Future<void> toggleMute() async {
    _muted = !_muted;
    await _sessionRtc?.setMuted(_muted);
    notifyListeners();
  }

  Future<void> toggleSpeaker() async {
    _speakerOn = !_speakerOn;
    await _sessionRtc?.setSpeakerphone(_speakerOn);
    notifyListeners();
  }

  void _onRtcState(String state) {
    if (state == 'connected') {
      _clearRingTimeout();
      _phase = VoiceCallUiPhase.connected;
      _statusNote = 'Sicher verbunden';
      _connectedAt = DateTime.now();
      _startDurationTimer();
      _stopRingFeedback();
    } else if (state == 'connecting') {
      _clearRingTimeout();
      _phase = VoiceCallUiPhase.connecting;
      _statusNote = 'Verbindung wird aufgebaut…';
    } else if (state == 'ringing') {
      if (_isOutgoing) {
        _phase = VoiceCallUiPhase.ringing;
        _statusNote = 'Klingelt beim Arbeitgeber…';
      }
    } else if (state == 'ended') {
      final note = _isOutgoing ? 'Nicht angenommen' : 'Anruf beendet';
      _finishEnded(note);
    }
    notifyListeners();
  }

  void _startDurationTimer() {
    _durationTimer?.cancel();
    _durationTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      final started = _connectedAt;
      if (started == null) return;
      _elapsed = DateTime.now().difference(started);
      notifyListeners();
    });
  }

  void _finishEnded(String note) {
    _stopRingFeedback();
    _clearRingTimeout();
    _durationTimer?.cancel();
    _durationTimer = null;
    _connectedAt = null;
    _elapsed = Duration.zero;
    _muted = false;
    _localLevel = 0;
    _remoteLevel = 0;
    _isOutgoing = false;
    _phase = VoiceCallUiPhase.ended;
    _statusNote = note;
    notifyListeners();
    Future<void>.delayed(const Duration(milliseconds: 900), () {
      if (_phase != VoiceCallUiPhase.ended) return;
      final endedId = (_call?['id'] ?? '').toString();
      if (endedId.isNotEmpty) _lastDismissedCallId = endedId;
      _call = null;
      _phase = VoiceCallUiPhase.idle;
      _statusNote = '';
      notifyListeners();
    });
  }

  @override
  void dispose() {
    unbind();
    unawaited(_callKit.dispose());
    super.dispose();
  }
}
