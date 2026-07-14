import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../core/session_store.dart';
import 'voice_call_repository.dart';

enum VoiceCallUiPhase { idle, ringing, connecting, connected, ended }

/// App-wide incoming/outgoing voice call orchestration (shows full-screen UI on any tab).
class VoiceCallController extends ChangeNotifier {
  VoiceCallController({
    required this.repo,
  });

  final VoiceCallRepository repo;

  WorkerSession? _session;
  Timer? _pollTimer;
  Timer? _ringTimer;
  Timer? _durationTimer;
  DateTime? _connectedAt;
  String? _pendingCallId;
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

  VoiceCallUiPhase get phase => _phase;
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
    _startPolling();
  }

  void unbind() {
    _pollTimer?.cancel();
    _ringTimer?.cancel();
    _durationTimer?.cancel();
    unawaited(_sessionRtc?.end('dispose'));
    _sessionRtc = null;
    _session = null;
    _call = null;
    _phase = VoiceCallUiPhase.idle;
  }

  void wakeForCall(String callId) {
    final id = callId.trim();
    if (id.isEmpty) return;
    _pendingCallId = id;
    unawaited(_pollIncoming(force: true));
  }

  void _startPolling() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(milliseconds: 1200), (_) {
      if (_phase == VoiceCallUiPhase.idle || _phase == VoiceCallUiPhase.ringing) {
        unawaited(_pollIncoming());
      }
    });
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
    _phase = VoiceCallUiPhase.ringing;
    _statusNote = 'Eingehender Anruf';
    _startRingFeedback();
    notifyListeners();
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
      _phase = VoiceCallUiPhase.connected;
      _statusNote = 'Sicher verbunden';
      _connectedAt = DateTime.now();
      _startDurationTimer();
      _stopRingFeedback();
    } else if (state == 'connecting' || state == 'ringing') {
      _phase = VoiceCallUiPhase.connecting;
      _statusNote = 'Verbindung wird aufgebaut…';
    } else if (state == 'ended') {
      _finishEnded('Anruf beendet');
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
    _durationTimer?.cancel();
    _durationTimer = null;
    _connectedAt = null;
    _elapsed = Duration.zero;
    _muted = false;
    _localLevel = 0;
    _remoteLevel = 0;
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
    super.dispose();
  }
}
