import 'dart:async';
import 'dart:io' show Platform;

import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:url_launcher/url_launcher.dart';

const _locationPrefix = '@location|';
const _mobileSendMaxAccuracyM = 18.0;
const _mapMaxAccuracyM = 150.0;

class ChatLocationPoint {
  const ChatLocationPoint({
    required this.lat,
    required this.lng,
    this.accuracy = 0,
    this.note = '',
  });

  final double lat;
  final double lng;
  final double accuracy;
  final String note;

  bool get canSend => accuracy <= 0 || accuracy <= _mapMaxAccuracyM;

  String get accuracyLabel {
    if (accuracy <= 0) return 'Standort';
    return '±${accuracy.round()} m';
  }
}

ChatLocationPoint? parseChatLocationBody(String? text) {
  final raw = (text ?? '').trim();
  if (!raw.startsWith(_locationPrefix)) return null;
  final meta = <String, String>{};
  for (final part in raw.substring(_locationPrefix.length).split('|')) {
    final idx = part.indexOf('=');
    if (idx <= 0) continue;
    meta[part.substring(0, idx)] = Uri.decodeComponent(part.substring(idx + 1));
  }
  final lat = double.tryParse(meta['lat'] ?? '');
  final lng = double.tryParse(meta['lng'] ?? '');
  if (lat == null || lng == null) return null;
  return ChatLocationPoint(
    lat: lat,
    lng: lng,
    accuracy: double.tryParse(meta['acc'] ?? '') ?? 0,
    note: meta['note'] ?? meta['label'] ?? '',
  );
}

String encodeChatLocationBody({
  required double lat,
  required double lng,
  double? accuracy,
  String? note,
}) {
  final parts = <String>[
    'lat=${lat.toStringAsFixed(6)}',
    'lng=${lng.toStringAsFixed(6)}',
  ];
  if (accuracy != null && accuracy > 0) {
    parts.add('acc=${accuracy.round()}');
  }
  final cleanNote = (note ?? '').trim();
  if (cleanNote.isNotEmpty) {
    parts.add('note=${Uri.encodeComponent(cleanNote)}');
  }
  return '$_locationPrefix${parts.join('|')}';
}

bool isChatLocationBody(String? text) => parseChatLocationBody(text) != null;

Uri googleMapsUri(ChatLocationPoint point) {
  return Uri.parse(
    'https://www.google.com/maps/search/?api=1&query=${point.lat},${point.lng}',
  );
}

Future<void> openChatLocationInMaps(ChatLocationPoint point) async {
  final uri = googleMapsUri(point);
  if (await canLaunchUrl(uri)) {
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }
}

Future<ChatLocationPoint> captureChatLocationPoint({
  Duration refineFor = const Duration(seconds: 12),
}) async {
  if (!await Geolocator.isLocationServiceEnabled()) {
    throw Exception('GPS ist aus — bitte Standortdienst aktivieren.');
  }
  var permission = await Geolocator.checkPermission();
  if (permission == LocationPermission.denied) {
    permission = await Geolocator.requestPermission();
  }
  if (permission == LocationPermission.denied ||
      permission == LocationPermission.deniedForever) {
    throw Exception('Standortfreigabe erforderlich.');
  }

  final LocationSettings settings;
  if (Platform.isAndroid) {
    settings = AndroidSettings(
      accuracy: LocationAccuracy.high,
      timeLimit: const Duration(seconds: 25),
    );
  } else if (Platform.isIOS) {
    settings = AppleSettings(
      accuracy: LocationAccuracy.high,
      timeLimit: const Duration(seconds: 25),
    );
  } else {
    settings = const LocationSettings(
      accuracy: LocationAccuracy.high,
      timeLimit: Duration(seconds: 25),
    );
  }

  var best = await Geolocator.getCurrentPosition(locationSettings: settings);
  if (best.accuracy <= _mobileSendMaxAccuracyM) {
    return ChatLocationPoint(
      lat: best.latitude,
      lng: best.longitude,
      accuracy: best.accuracy,
    );
  }

  StreamSubscription<Position>? sub;
  try {
    final done = Completer<void>();
    sub = Geolocator.getPositionStream(locationSettings: settings).listen((position) {
      if (position.accuracy < best.accuracy) {
        best = position;
      }
      if (best.accuracy <= _mobileSendMaxAccuracyM && !done.isCompleted) {
        done.complete();
      }
    });
    await done.future.timeout(refineFor, onTimeout: () {});
  } finally {
    await sub?.cancel();
  }

  return ChatLocationPoint(
    lat: best.latitude,
    lng: best.longitude,
    accuracy: best.accuracy,
  );
}

Future<ChatLocationPoint?> showChatLocationShareSheet(BuildContext context) async {
  return showModalBottomSheet<ChatLocationPoint>(
    context: context,
    isScrollControlled: true,
    backgroundColor: const Color(0xFF1F2C34),
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
    ),
    builder: (context) => const _ChatLocationShareSheet(),
  );
}

class _ChatLocationShareSheet extends StatefulWidget {
  const _ChatLocationShareSheet();

  @override
  State<_ChatLocationShareSheet> createState() => _ChatLocationShareSheetState();
}

class _ChatLocationShareSheetState extends State<_ChatLocationShareSheet> {
  final _note = TextEditingController();
  ChatLocationPoint? _point;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final point = await captureChatLocationPoint();
      if (!mounted) return;
      setState(() {
        _point = point;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  String _statusText(ChatLocationPoint point) {
    final acc = point.accuracy;
    if (acc <= 0) return 'Standort wird ermittelt…';
    if (acc <= 8) return 'Genauigkeit ${point.accuracyLabel}';
    if (acc <= 20) return 'Standort bereit · ${point.accuracyLabel}';
    if (acc <= _mapMaxAccuracyM) return 'Standort ungefähr · ${point.accuracyLabel}';
    return 'GPS-Signal schwach';
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.viewInsetsOf(context).bottom;
    final point = _point;
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 12, 16, 16 + bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              IconButton(
                onPressed: () => Navigator.of(context).pop(),
                icon: const Icon(Icons.close, color: Color(0xFFE9EDEF)),
              ),
              const Expanded(
                child: Text(
                  'Standort senden',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Color(0xFFE9EDEF),
                    fontWeight: FontWeight.w700,
                    fontSize: 17,
                  ),
                ),
              ),
              const SizedBox(width: 48),
            ],
          ),
          if (_loading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 28),
              child: Center(child: CircularProgressIndicator(color: Color(0xFF00A884))),
            )
          else if (_error != null)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 20),
              child: Text(_error!, style: const TextStyle(color: Color(0xFFEAA860))),
            )
          else if (point != null) ...[
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: const Color(0xFF2A3942),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _statusText(point),
                    style: TextStyle(
                      color: point.accuracy <= 20
                          ? const Color(0xFF25D366)
                          : const Color(0xFFEAA860),
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '${point.lat.toStringAsFixed(5)}, ${point.lng.toStringAsFixed(5)}',
                    style: const TextStyle(color: Color(0xFF8696A0), fontSize: 13),
                  ),
                  if (point.note.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(point.note, style: const TextStyle(color: Color(0xFFE9EDEF))),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _note,
              maxLines: 2,
              maxLength: 500,
              style: const TextStyle(color: Color(0xFFE9EDEF)),
              decoration: InputDecoration(
                hintText: 'Hinweis hinzufügen…',
                hintStyle: TextStyle(color: Colors.white.withValues(alpha: 0.42)),
                filled: true,
                fillColor: const Color(0xFF2A3942),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
              ),
            ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: point.canSend
                  ? () {
                      Navigator.of(context).pop(
                        ChatLocationPoint(
                          lat: point.lat,
                          lng: point.lng,
                          accuracy: point.accuracy,
                          note: _note.text.trim(),
                        ),
                      );
                    }
                  : null,
              style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFF00A884),
                minimumSize: const Size.fromHeight(48),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
              ),
              child: const Text('Senden', style: TextStyle(fontWeight: FontWeight.w700)),
            ),
          ],
        ],
      ),
    );
  }
}

class ChatLocationBubble extends StatelessWidget {
  const ChatLocationBubble({
    super.key,
    required this.point,
    this.timeLabel = '',
    this.isMine = false,
  });

  final ChatLocationPoint point;
  final String timeLabel;
  final bool isMine;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: () => openChatLocationInMaps(point),
      borderRadius: BorderRadius.circular(10),
      child: Container(
        width: 240,
        decoration: BoxDecoration(
          color: isMine ? const Color(0xFF005C4B) : const Color(0xFF202C33),
          borderRadius: BorderRadius.circular(10),
        ),
        padding: const EdgeInsets.all(3),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              height: 120,
              decoration: BoxDecoration(
                color: const Color(0xFFE5E3DF),
                borderRadius: BorderRadius.circular(8),
              ),
              alignment: Alignment.center,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.location_on, size: 36, color: Colors.red.shade700),
                  const SizedBox(height: 6),
                  Text(
                    point.accuracyLabel,
                    style: const TextStyle(fontWeight: FontWeight.w700, color: Color(0xFF3C4043)),
                  ),
                ],
              ),
            ),
            if (point.note.isNotEmpty)
              Padding(
                padding: const EdgeInsets.fromLTRB(8, 8, 8, 4),
                child: Text(
                  point.note,
                  style: const TextStyle(color: Color(0xFFE9EDEF), fontSize: 14),
                ),
              ),
            Padding(
              padding: const EdgeInsets.fromLTRB(8, 4, 8, 6),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    'In Maps öffnen',
                    style: TextStyle(color: Color(0xFF53BDFB), fontSize: 12, fontWeight: FontWeight.w600),
                  ),
                  if (timeLabel.isNotEmpty)
                    Text(timeLabel, style: const TextStyle(color: Color(0xFF8696A0), fontSize: 11)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
