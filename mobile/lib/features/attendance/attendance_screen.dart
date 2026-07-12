import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';

import '../../core/api_client.dart';
import '../../core/auth_repository.dart';
import '../../core/session_store.dart';
import '../../services/attendance_repository.dart';
import 'timesheets_screen.dart';
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
  String? _timesheetSummary;

  String _formatMinutes(int minutes) {
    final h = minutes ~/ 60;
    final m = minutes % 60;
    return '${h}:${m.toString().padLeft(2, '0')} h';
  }

  Future<void> _loadTimesheetSummary() async {
    try {
      final data = await widget.attendance.fetchMyTimesheets(session: widget.session);
      final todayMin = (data['todayWorkMinutes'] as num?)?.toInt() ?? 0;
      final open = data['attendanceOpen'] == true;
      if (!mounted) return;
      setState(() {
        _timesheetSummary = open
            ? 'Heute: ${_formatMinutes(todayMin)} (eingestempelt)'
            : 'Heute: ${_formatMinutes(todayMin)}';
      });
    } catch (_) {
      // optional summary — ignore transient errors
    }
  }

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    await _refreshPendingCount();
    await _loadProfile();
    await _loadTimesheetSummary();
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

  void _showFeedback(String message, {bool isError = false}) {
    setState(() => _status = message);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: isError ? Theme.of(context).colorScheme.error : null,
        duration: const Duration(seconds: 5),
      ),
    );
  }

  String _attendanceErrorMessage(ApiException e) {
    switch (e.errorCode) {
      case 'outside_geofence':
        return 'Außerhalb der Baustelle — Check-in nur vor Ort möglich.';
      case 'site_location_unavailable':
        return 'Baustelle hat keinen GPS-Standort — Admin muss Standort in Firmeneinstellungen setzen.';
      case 'worker_geolocation_inaccurate':
        return 'GPS zu ungenau — kurz warten und erneut versuchen.';
      case 'device_not_bound':
        return 'Gerät nicht freigegeben — bitte erneut anmelden.';
      case 'network_error':
        return 'Keine Verbindung zum Server — Internet prüfen.';
      default:
        return e.message ?? e.toString();
    }
  }

  Future<void> _tapManualGps(String direction) async {
    setState(() {
      _busy = true;
      _status = 'Standort wird ermittelt…';
    });
    try {
      final location = await widget.location.captureForAttendance();
      if (location == null) {
        _showFeedback('GPS erforderlich — Standortfreigabe aktivieren.', isError: true);
        return;
      }
      final clientEventId =
          'gps-${DateTime.now().toUtc().millisecondsSinceEpoch}-${direction.hashCode.abs()}';
      final result = await widget.attendance.recordManualGpsAttendance(
        session: widget.session,
        direction: direction,
        location: location,
        clientEventId: clientEventId,
      );
      if (!mounted) return;
      final recordedDirection = result['direction'] as String? ?? direction;
      final open = result['openCheckInToday'] == true || result['attendanceOpen'] == true;
      await widget.workerCache.setOpenCheckInToday(open);
      setState(() {
        _lastDirection = recordedDirection;
        _status = result['duplicate'] == true
            ? 'Bereits erfasst ($recordedDirection).'
            : 'Anwesenheit gespeichert: $recordedDirection';
      });
      _showFeedback(_status!);
      await _loadTimesheetSummary();
    } on LocationCaptureException catch (e) {
      if (e.openSettings) {
        await Geolocator.openLocationSettings();
      }
      _showFeedback(e.message, isError: true);
    } on ApiException catch (e) {
      _showFeedback(_attendanceErrorMessage(e), isError: true);
    } catch (e) {
      _showFeedback(e.toString(), isError: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
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
      Map<String, dynamic>? location;
      try {
        location = await widget.location.captureForAttendance();
      } on LocationCaptureException catch (e) {
        if (e.openSettings) await Geolocator.openLocationSettings();
        _showFeedback(e.message, isError: true);
        return;
      }

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
        await _loadTimesheetSummary();
      } on ApiException catch (e) {
        if (e.statusCode == 0 || e.errorCode == 'network_error' || e.statusCode >= 500) {
          await _queueOfflineAttendance(scan.uid, direction, location: location);
          return;
        }
        if (e.errorCode == 'worker_geolocation_required' && location == null) {
          _showFeedback('GPS erforderlich — Standortfreigabe aktivieren.', isError: true);
          return;
        }
        if (e.errorCode == 'device_not_bound') {
          _showFeedback('Gerät nicht freigegeben — bitte erneut anmelden.', isError: true);
          return;
        }
        _showFeedback(_attendanceErrorMessage(e), isError: true);
        return;
      }
    } on NfcUnavailableException catch (e) {
      _showFeedback(e.message, isError: true);
    } catch (e) {
      _showFeedback(e.toString(), isError: true);
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
            if (_timesheetSummary != null) ...[
              const SizedBox(height: 8),
              Text(_timesheetSummary!, style: Theme.of(context).textTheme.bodyMedium),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: () {
                    Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => TimesheetsScreen(
                          session: widget.session,
                          attendance: widget.attendance,
                        ),
                      ),
                    );
                  },
                  icon: const Icon(Icons.schedule),
                  label: const Text('Stundennachweis öffnen'),
                ),
              ),
            ],
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('GPS ohne NFC', style: Theme.of(context).textTheme.titleSmall),
                    const SizedBox(height: 8),
                    const Text(
                      'Manuell ein- oder ausstempeln, wenn Sie bereits auf der Baustelle sind '
                      '(ohne NFC-Karte am Gate).',
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: _busy ? null : () => _tapManualGps('check-in'),
                            icon: const Icon(Icons.login),
                            label: const Text('Ein'),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: _busy ? null : () => _tapManualGps('check-out'),
                            icon: const Icon(Icons.logout),
                            label: const Text('Aus'),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
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
