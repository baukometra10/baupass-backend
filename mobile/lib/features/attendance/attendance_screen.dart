import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/auth_repository.dart';
import '../../core/session_store.dart';
import '../../services/attendance_repository.dart';
import '../../services/location_service.dart';
import '../../services/nfc_service.dart';
import '../../services/offline_attendance_store.dart';
import '../../services/offline_sync_service.dart';
import '../../services/worker_cache.dart';

class AttendanceScreen extends StatefulWidget {
  const AttendanceScreen({
    super.key,
    required this.session,
    required this.auth,
    required this.attendance,
    required this.nfc,
    required this.location,
    required this.offlineStore,
    required this.offlineSync,
    required this.workerCache,
    this.embedded = false,
  });

  final WorkerSession session;
  final AuthRepository auth;
  final AttendanceRepository attendance;
  final NfcService nfc;
  final LocationService location;
  final OfflineAttendanceStore offlineStore;
  final OfflineSyncService offlineSync;
  final WorkerCache workerCache;
  final bool embedded;

  @override
  State<AttendanceScreen> createState() => _AttendanceScreenState();
}

class _AttendanceScreenState extends State<AttendanceScreen> {
  bool _busy = false;
  String? _status;
  String? _lastDirection;
  Map<String, dynamic>? _profile;
  int _pendingOffline = 0;

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    await _refreshPendingCount();
    await _loadProfile();
    await widget.offlineSync.syncNow();
    await _refreshPendingCount();
  }

  Future<void> _refreshPendingCount() async {
    final count = await widget.offlineStore.pendingCount();
    if (mounted) setState(() => _pendingOffline = count);
  }

  Future<void> _loadProfile() async {
    try {
      final me = await widget.auth.fetchProfile(widget.session);
      await widget.workerCache.saveProfile(me);
      if (!mounted) return;
      setState(() => _profile = me);
    } catch (_) {
      final cached = await widget.workerCache.loadProfile();
      if (!mounted) return;
      setState(() {
        _profile = cached;
        if (cached != null) {
          _status = 'Offline — zwischengespeichertes Profil.';
        }
      });
    }
  }

  String _resolveDirectionForQueue() {
    final siteAccess = _profile?['siteAccess'] as Map<String, dynamic>?;
    final open = siteAccess?['openCheckInToday'] == true;
    return open ? 'check-out' : 'check-in';
  }

  Future<void> _queueOfflineAttendance(
    String nfcUid,
    String direction, {
    Map<String, dynamic>? location,
  }) async {
    final clientEventId =
        'nfc-${DateTime.now().toUtc().millisecondsSinceEpoch}-${nfcUid.hashCode.abs()}';
    await widget.offlineStore.enqueue(<String, dynamic>{
      'type': 'nfc_attendance',
      'clientEventId': clientEventId,
      'nfcUid': nfcUid,
      'direction': direction,
      'occurredAt': DateTime.now().toUtc().toIso8601String(),
      if (location != null) 'location': location,
    });
    await widget.workerCache.setOpenCheckInToday(direction == 'check-in');
    await _refreshPendingCount();
    if (!mounted) return;
    setState(() {
      _lastDirection = direction;
      _status = 'Offline gespeichert ($direction) — wird synchronisiert.';
    });
  }

  Future<void> _tapAttendance() async {
    setState(() {
      _busy = true;
      _status = 'NFC-Karte ans Handy halten…';
    });
    try {
      final available = await widget.nfc.isAvailable();
      if (!available) {
        throw NfcUnavailableException('NFC nicht verfügbar — in den Einstellungen aktivieren.');
      }
      final scan = await widget.nfc.scanTag();
      final direction = _resolveDirectionForQueue();
      final clientEventId =
          'nfc-${DateTime.now().toUtc().millisecondsSinceEpoch}-${scan.uid.hashCode.abs()}';

      setState(() => _status = 'Standort wird ermittelt…');
      final location = await widget.location.captureForAttendance();

      setState(() => _status = 'Check-in wird gesendet…');
      try {
        final result = await widget.attendance.recordNfcAttendance(
          session: widget.session,
          nfcUid: scan.uid,
          direction: direction,
          location: location,
          clientEventId: clientEventId,
        );
        if (!mounted) return;
        final recordedDirection = result['direction'] as String? ?? direction;
        final duplicate = result['duplicate'] == true;
        final open = result['openCheckInToday'] == true;
        await widget.workerCache.setOpenCheckInToday(open);
        setState(() {
          _lastDirection = recordedDirection;
          _status = duplicate
              ? 'Bereits erfasst ($recordedDirection).'
              : 'Anwesenheit gespeichert: $recordedDirection';
        });
      } on ApiException catch (e) {
        if (e.statusCode == 0 || e.errorCode == 'network_error' || e.statusCode >= 500) {
          await _queueOfflineAttendance(scan.uid, direction, location: location);
          return;
        }
        if (e.errorCode == 'worker_geolocation_required' && location == null) {
          if (!mounted) return;
          setState(() => _status = 'GPS erforderlich — Standortfreigabe aktivieren.');
          return;
        }
        if (e.errorCode == 'device_not_bound') {
          if (!mounted) return;
          setState(() => _status = 'Gerät nicht freigegeben — bitte erneut anmelden.');
          return;
        }
        rethrow;
      }
    } on NfcUnavailableException catch (e) {
      if (!mounted) return;
      setState(() => _status = e.message);
    } catch (e) {
      if (!mounted) return;
      setState(() => _status = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final worker = _profile?['worker'] as Map<String, dynamic>?;
    final name = worker != null
        ? '${worker['firstName'] ?? ''} ${worker['lastName'] ?? ''}'.trim()
        : '';
    final badgeId = widget.workerCache.badgeIdFromProfile(_profile);

    return Scaffold(
      appBar: widget.embedded
          ? AppBar(
              title: const Text('Check-in'),
              automaticallyImplyLeading: false,
              actions: [
                if (_pendingOffline > 0)
                  Center(
                    child: Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: Chip(
                        label: Text('$_pendingOffline offline'),
                        visualDensity: VisualDensity.compact,
                      ),
                    ),
                  ),
                IconButton(
                  icon: const Icon(Icons.sync),
                  onPressed: _busy
                      ? null
                      : () async {
                          await widget.offlineSync.syncNow();
                          await _refreshPendingCount();
                          await _loadProfile();
                        },
                  tooltip: 'Offline-Sync',
                ),
              ],
            )
          : AppBar(title: const Text('Check-in')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (name.isNotEmpty)
              Text('Hallo, $name', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('NFC am Bauzaun', style: Theme.of(context).textTheme.titleSmall),
                    const SizedBox(height: 8),
                    const Text(
                      '1. Physische Karte am Gate-Reader (empfohlen bei schlechtem Netz).\n'
                      '2. Oder NFC hier scannen — offline zwischengespeichert, später synchronisiert.',
                    ),
                    if (badgeId != null && badgeId.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Text('Badge-ID: $badgeId', style: const TextStyle(fontFamily: 'monospace')),
                    ],
                  ],
                ),
              ),
            ),
            if (_lastDirection != null) ...[
              const SizedBox(height: 8),
              Text('Letzte Aktion: $_lastDirection'),
            ],
            const Spacer(),
            SizedBox(
              height: 120,
              child: FilledButton.icon(
                onPressed: _busy ? null : _tapAttendance,
                icon: _busy
                    ? const SizedBox(
                        width: 24,
                        height: 24,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.nfc, size: 36),
                label: Text(_busy ? 'Scanne…' : 'NFC — Check-in/out'),
                style: FilledButton.styleFrom(textStyle: const TextStyle(fontSize: 18)),
              ),
            ),
            const SizedBox(height: 24),
            if (_status != null)
              Text(_status!, textAlign: TextAlign.center, style: Theme.of(context).textTheme.bodyLarge),
            const Spacer(),
          ],
        ),
      ),
    );
  }
}
