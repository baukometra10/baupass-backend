import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:livekit_client/livekit_client.dart';

import '../../core/session_store.dart';
import '../../services/conference_repository.dart';

/// Full-screen LiveKit company conference (audio + video) for workers.
class ConferenceRoomScreen extends StatefulWidget {
  const ConferenceRoomScreen({
    super.key,
    required this.session,
    required this.repo,
    required this.roomId,
    required this.livekitUrl,
    required this.token,
    this.title = 'Firmenkonferenz',
  });

  final WorkerSession session;
  final ConferenceRepository repo;
  final String roomId;
  final String livekitUrl;
  final String token;
  final String title;

  @override
  State<ConferenceRoomScreen> createState() => _ConferenceRoomScreenState();
}

class _ConferenceRoomScreenState extends State<ConferenceRoomScreen> {
  Room? _room;
  EventsListener<RoomEvent>? _listener;
  bool _connecting = true;
  bool _micOn = true;
  bool _camOn = false;
  bool _busyMedia = false;
  String? _error;
  String? _cameraNotice;
  bool _leaving = false;

  @override
  void initState() {
    super.initState();
    _connect();
  }

  @override
  void dispose() {
    _listener?.dispose();
    final room = _room;
    _room = null;
    room?.disconnect();
    super.dispose();
  }

  Future<void> _connect() async {
    setState(() {
      _connecting = true;
      _error = null;
    });
    final room = Room(
      roomOptions: const RoomOptions(
        adaptiveStream: true,
        dynacast: true,
      ),
    );
    final listener = room.createListener();
    listener
      ..on<RoomDisconnectedEvent>((_) {
        if (!mounted || _leaving) return;
        Navigator.of(context).maybePop();
      })
      ..on<DataReceivedEvent>(_onDataReceived)
      ..on<TrackSubscribedEvent>((_) {
        if (mounted) setState(() {});
      })
      ..on<TrackUnsubscribedEvent>((_) {
        if (mounted) setState(() {});
      })
      ..on<LocalTrackPublishedEvent>((_) {
        if (mounted) setState(() {});
      })
      ..on<LocalTrackUnpublishedEvent>((_) {
        if (mounted) setState(() {});
      })
      ..on<ParticipantConnectedEvent>((_) {
        if (mounted) setState(() {});
      })
      ..on<ParticipantDisconnectedEvent>((_) {
        if (mounted) setState(() {});
      });

    try {
      final url = widget.livekitUrl.trim().replaceAll(RegExp(r'/+$'), '');
      await room.connect(url, widget.token);
      await room.localParticipant?.setMicrophoneEnabled(true);
      try {
        await room.localParticipant?.setCameraEnabled(false);
      } catch (_) {
        /* camera optional until user enables */
      }
      if (!mounted) {
        await room.disconnect();
        listener.dispose();
        return;
      }
      setState(() {
        _room = room;
        _listener = listener;
        _connecting = false;
        _micOn = true;
        _camOn = false;
      });
    } catch (e) {
      listener.dispose();
      try {
        await room.disconnect();
      } catch (_) {
        /* ignore */
      }
      if (!mounted) return;
      setState(() {
        _connecting = false;
        _error = e.toString();
      });
    }
  }

  void _onDataReceived(DataReceivedEvent event) {
    try {
      final raw = utf8.decode(event.data);
      final map = jsonDecode(raw);
      if (map is! Map) return;
      if (map['type']?.toString() != 'camera_intent') return;
      final name = (map['name'] ?? event.participant?.name ?? event.participant?.identity ?? 'Teilnehmer')
          .toString()
          .trim();
      if (!mounted) return;
      setState(() => _cameraNotice = '$name möchte die Kamera öffnen');
      Future<void>.delayed(const Duration(seconds: 4), () {
        if (!mounted) return;
        if (_cameraNotice?.contains(name) == true) {
          setState(() => _cameraNotice = null);
        }
      });
    } catch (_) {
      /* ignore malformed payloads */
    }
  }

  Future<void> _broadcastCameraIntent() async {
    final lp = _room?.localParticipant;
    if (lp == null) return;
    final name = lp.name.trim().isNotEmpty ? lp.name : lp.identity;
    final payload = utf8.encode(jsonEncode({
      'type': 'camera_intent',
      'name': name,
    }));
    try {
      await lp.publishData(Uint8List.fromList(payload), reliable: true, topic: 'suppix.camera');
    } catch (_) {
      /* best-effort notice */
    }
  }

  Future<void> _toggleMic() async {
    final lp = _room?.localParticipant;
    if (lp == null || _busyMedia) return;
    setState(() => _busyMedia = true);
    try {
      final next = !_micOn;
      await lp.setMicrophoneEnabled(next);
      if (mounted) setState(() => _micOn = next);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Mikrofon: $e')));
      }
    } finally {
      if (mounted) setState(() => _busyMedia = false);
    }
  }

  Future<void> _toggleCam() async {
    final lp = _room?.localParticipant;
    if (lp == null || _busyMedia) return;
    setState(() => _busyMedia = true);
    try {
      final next = !_camOn;
      if (next) {
        await _broadcastCameraIntent();
        await Future<void>.delayed(const Duration(milliseconds: 350));
      }
      await lp.setCameraEnabled(next);
      if (mounted) setState(() => _camOn = next);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Kamera: $e')));
      }
    } finally {
      if (mounted) setState(() => _busyMedia = false);
    }
  }

  Future<void> _leave() async {
    if (_leaving) return;
    _leaving = true;
    try {
      await widget.repo.leave(widget.session, widget.roomId);
    } catch (_) {
      /* ignore */
    }
    try {
      await _room?.disconnect();
    } catch (_) {
      /* ignore */
    }
    if (mounted) Navigator.of(context).pop();
  }

  List<_ParticipantTile> _tiles() {
    final room = _room;
    if (room == null) return const [];
    final out = <_ParticipantTile>[];
    final local = room.localParticipant;
    if (local != null) {
      out.add(_ParticipantTile(participant: local, isLocal: true));
    }
    for (final p in room.remoteParticipants.values) {
      out.add(_ParticipantTile(participant: p, isLocal: false));
    }
    return out;
  }

  @override
  Widget build(BuildContext context) {
    final tiles = _tiles();
    return Scaffold(
      backgroundColor: const Color(0xFF0B1220),
      body: SafeArea(
        child: Stack(
          children: [
            Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              widget.title,
                              style: const TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w800,
                                fontSize: 18,
                              ),
                            ),
                            Text(
                              _connecting
                                  ? 'Verbindet…'
                                  : (_error != null ? 'Fehler' : 'Konferenz aktiv'),
                              style: TextStyle(color: Colors.white.withValues(alpha: 0.7), fontSize: 13),
                            ),
                          ],
                        ),
                      ),
                      IconButton(
                        onPressed: _leave,
                        icon: const Icon(Icons.close, color: Colors.white),
                      ),
                    ],
                  ),
                ),
                if (_error != null)
                  Expanded(
                    child: Center(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(_error!, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white70)),
                            const SizedBox(height: 16),
                            FilledButton(onPressed: _connect, child: const Text('Erneut versuchen')),
                            TextButton(onPressed: _leave, child: const Text('Verlassen')),
                          ],
                        ),
                      ),
                    ),
                  )
                else if (_connecting)
                  const Expanded(child: Center(child: CircularProgressIndicator()))
                else
                  Expanded(
                    child: tiles.isEmpty
                        ? const Center(
                            child: Text('Warte auf Teilnehmer…', style: TextStyle(color: Colors.white70)),
                          )
                        : GridView.builder(
                            padding: const EdgeInsets.all(12),
                            gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                              crossAxisCount: tiles.length == 1 ? 1 : 2,
                              mainAxisSpacing: 10,
                              crossAxisSpacing: 10,
                              childAspectRatio: tiles.length == 1 ? 0.75 : 0.72,
                            ),
                            itemCount: tiles.length,
                            itemBuilder: (context, i) => tiles[i],
                          ),
                  ),
                if (!_connecting && _error == null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                      children: [
                        _RoundControl(
                          icon: _micOn ? Icons.mic : Icons.mic_off,
                          label: _micOn ? 'Mikro' : 'Stumm',
                          active: _micOn,
                          onTap: _busyMedia ? null : _toggleMic,
                        ),
                        _RoundControl(
                          icon: _camOn ? Icons.videocam : Icons.videocam_off,
                          label: _camOn ? 'Kamera' : 'Cam aus',
                          active: _camOn,
                          onTap: _busyMedia ? null : _toggleCam,
                        ),
                        _RoundControl(
                          icon: Icons.call_end,
                          label: 'Verlassen',
                          active: false,
                          danger: true,
                          onTap: _leave,
                        ),
                      ],
                    ),
                  ),
              ],
            ),
            if (_cameraNotice != null)
              Positioned(
                left: 16,
                right: 16,
                top: 64,
                child: Material(
                  color: const Color(0xEE1E293B),
                  borderRadius: BorderRadius.circular(12),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                    child: Row(
                      children: [
                        const Icon(Icons.videocam, color: Color(0xFF38BDF8)),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            _cameraNotice!,
                            style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _ParticipantTile extends StatelessWidget {
  const _ParticipantTile({required this.participant, required this.isLocal});

  final Participant participant;
  final bool isLocal;

  VideoTrack? get _videoTrack {
    for (final pub in participant.videoTrackPublications) {
      final track = pub.track;
      if (track is VideoTrack && !pub.muted) return track;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final video = _videoTrack;
    final label = (participant.name.trim().isNotEmpty
            ? participant.name
            : participant.identity)
        .trim();
    final display = isLocal ? 'Du ($label)' : label;
    return ClipRRect(
      borderRadius: BorderRadius.circular(14),
      child: ColoredBox(
        color: const Color(0xFF1E293B),
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (video != null)
              VideoTrackRenderer(video)
            else
              Center(
                child: CircleAvatar(
                  radius: 36,
                  backgroundColor: const Color(0xFF334155),
                  child: Text(
                    display.isNotEmpty ? display.characters.first.toUpperCase() : '?',
                    style: const TextStyle(fontSize: 28, color: Colors.white, fontWeight: FontWeight.w700),
                  ),
                ),
              ),
            Positioned(
              left: 8,
              right: 8,
              bottom: 8,
              child: Text(
                display,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w600,
                  shadows: [Shadow(blurRadius: 6, color: Colors.black54)],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _RoundControl extends StatelessWidget {
  const _RoundControl({
    required this.icon,
    required this.label,
    required this.active,
    this.danger = false,
    this.onTap,
  });

  final IconData icon;
  final String label;
  final bool active;
  final bool danger;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final bg = danger
        ? const Color(0xFFE53935)
        : (active ? const Color(0xFF334155) : const Color(0xFF1E293B));
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Material(
          color: bg,
          shape: const CircleBorder(),
          child: InkWell(
            customBorder: const CircleBorder(),
            onTap: onTap,
            child: SizedBox(
              width: 58,
              height: 58,
              child: Icon(icon, color: Colors.white),
            ),
          ),
        ),
        const SizedBox(height: 6),
        Text(label, style: TextStyle(color: Colors.white.withValues(alpha: 0.85), fontSize: 12)),
      ],
    );
  }
}
