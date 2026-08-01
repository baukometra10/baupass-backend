import 'dart:async';

import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';

import '../../core/api_client.dart';
import '../../core/app_strings.dart';
import '../../core/auth_repository.dart';
import '../../core/locale_controller.dart';
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
      final hours = _formatMinutes(todayMin);
      setState(() {
        _timesheetSummary = open
            ? t('todayHoursOpen').replaceAll('{h}', hours)
            : t('todayHours').replaceAll('{h}', hours);
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
    // Warm GPS so the first tap resolves from cache in ≤1s.
    unawaited(widget.location.warmAttendanceGps());
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
          _status = t('offlineProfile');
        }
      });
    }
  }

  Future<void> _queueOfflineGps(
    String direction, {
    required Map<String, dynamic> location,
  }) async {
    final clientEventId =
        'gps-${DateTime.now().toUtc().millisecondsSinceEpoch}-${direction.hashCode.abs()}';
    await widget.offlineStore.enqueue(<String, dynamic>{
      'type': 'manual_gps_attendance',
      'clientEventId': clientEventId,
      'direction': direction,
      'occurredAt': DateTime.now().toUtc().toIso8601String(),
      'location': location,
    });
    await widget.workerCache.setOpenCheckInToday(direction != 'check-out');
    await _refreshPendingCount();
    if (!mounted) return;
    final msg = t('offlineQueued').replaceAll('{dir}', direction);
    setState(() {
      _lastDirection = direction;
      _status = msg;
    });
    _showFeedback(msg);
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
      _status = t('offlineQueued').replaceAll('{dir}', direction);
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
        final dist = e.payload?['distanceMeters'] ?? e.payload?['distance'];
        final radius = e.payload?['allowedRadiusMeters'] ?? e.payload?['radiusMeters'];
        if (dist != null && radius != null) {
          return t('errOutsideGeofenceDistance')
              .replaceAll('{dist}', '${(dist as num).round()}')
              .replaceAll('{radius}', '${(radius as num).round()}');
        }
        return t('errOutsideGeofence');
      case 'site_location_unavailable':
        return t('errSiteLocationUnavailable');
      case 'worker_geolocation_inaccurate':
        return t('errGpsInaccurate');
      case 'worker_geolocation_required':
        return t('gpsRequired');
      case 'nfc_card_not_enrolled':
        return t('errNfcNotEnrolled');
      case 'nfc_uid_mismatch':
        return t('errNfcMismatch');
      case 'device_not_bound':
        return t('errDeviceNotBound');
      case 'network_error':
        return t('errNetwork');
      case 'already_checked_in':
        return t('errAlreadyCheckedIn');
      case 'not_checked_in':
        return t('errNotCheckedIn');
      default:
        return e.message ?? e.toString();
    }
  }

  Future<void> _tapManualGps(String direction) async {
    setState(() {
      _busy = true;
      _status = t('locating');
    });
    try {
      final location = await widget.location.captureForAttendance();
      if (location == null) {
        _showFeedback(t('gpsRequired'), isError: true);
        return;
      }
      final clientEventId =
          'gps-${DateTime.now().toUtc().millisecondsSinceEpoch}-${direction.hashCode.abs()}';
      try {
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
        final msg = result['duplicate'] == true
            ? t('attendanceDuplicate').replaceAll('{dir}', recordedDirection)
            : t('attendanceSaved').replaceAll('{dir}', recordedDirection);
        setState(() {
          _lastDirection = recordedDirection;
          _status = msg;
        });
        _showFeedback(msg);
        await _loadTimesheetSummary();
      } on ApiException catch (e) {
        if (e.statusCode == 0 || e.errorCode == 'network_error' || e.statusCode >= 500) {
          await _queueOfflineGps(direction, location: location);
          return;
        }
        _showFeedback(_attendanceErrorMessage(e), isError: true);
      }
    } on LocationCaptureException catch (e) {
      if (e.openSettings) {
        await Geolocator.openLocationSettings();
      }
      _showFeedback(t(e.messageKey), isError: true);
    } catch (e) {
      _showFeedback(e.toString(), isError: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _tapAttendance() async {
    setState(() {
      _busy = true;
      _status = t('holdNfc');
    });
    try {
      final available = await widget.nfc.isAvailable();
      if (!available) {
        throw NfcUnavailableException(t('nfcUnavailable'));
      }
      final scan = await widget.nfc.scanTag();
      const direction = 'auto';
      final clientEventId =
          'nfc-${DateTime.now().toUtc().millisecondsSinceEpoch}-${scan.uid.hashCode.abs()}';

      setState(() => _status = t('locating'));
      Map<String, dynamic>? location;
      try {
        location = await widget.location.captureForAttendance();
      } on LocationCaptureException catch (e) {
        if (e.openSettings) await Geolocator.openLocationSettings();
        _showFeedback(t(e.messageKey), isError: true);
        return;
      }

      setState(() => _status = t('sendingCheckin'));
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
        final msg = duplicate
            ? t('attendanceDuplicate').replaceAll('{dir}', recordedDirection)
            : t('attendanceSaved').replaceAll('{dir}', recordedDirection);
        setState(() {
          _lastDirection = recordedDirection;
          _status = msg;
        });
        _showFeedback(msg);
        await _loadTimesheetSummary();
      } on ApiException catch (e) {
        if (e.statusCode == 0 || e.errorCode == 'network_error' || e.statusCode >= 500) {
          await _queueOfflineAttendance(scan.uid, direction, location: location);
          return;
        }
        if (e.errorCode == 'worker_geolocation_required' && location == null) {
          _showFeedback(t('gpsRequired'), isError: true);
          return;
        }
        if (e.errorCode == 'device_not_bound') {
          _showFeedback(t('errDeviceNotBound'), isError: true);
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
    return ListenableBuilder(
      listenable: LocaleController.instance,
      builder: (context, _) {
        final worker = _profile?['worker'] as Map<String, dynamic>?;
        final name = worker != null
            ? '${worker['firstName'] ?? ''} ${worker['lastName'] ?? ''}'.trim()
            : '';
        final badgeId = widget.workerCache.badgeIdFromProfile(_profile);

        return Scaffold(
          appBar: widget.embedded
              ? AppBar(
                  title: Text(t('navCheckin')),
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
                      tooltip: t('offlineSync'),
                    ),
                  ],
                )
              : AppBar(title: Text(t('navCheckin'))),
          body: SafeArea(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        if (name.isNotEmpty)
                          Text(
                            t('helloName').replaceAll('{name}', name),
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
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
                              label: Text(t('openTimesheet')),
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
                                Text(t('gpsNoNfcTitle'), style: Theme.of(context).textTheme.titleSmall),
                                const SizedBox(height: 8),
                                Text(t('gpsNoNfcHint')),
                                const SizedBox(height: 12),
                                SizedBox(
                                  width: double.infinity,
                                  height: 48,
                                  child: FilledButton.icon(
                                    onPressed: _busy ? null : () => _tapManualGps('auto'),
                                    icon: const Icon(Icons.my_location),
                                    label: Text(t('gpsCheckinAuto')),
                                  ),
                                ),
                                const SizedBox(height: 10),
                                Row(
                                  children: [
                                    Expanded(
                                      child: OutlinedButton.icon(
                                        onPressed: _busy ? null : () => _tapManualGps('check-in'),
                                        icon: const Icon(Icons.login),
                                        label: Text(t('gpsIn')),
                                      ),
                                    ),
                                    const SizedBox(width: 12),
                                    Expanded(
                                      child: OutlinedButton.icon(
                                        onPressed: _busy ? null : () => _tapManualGps('check-out'),
                                        icon: const Icon(Icons.logout),
                                        label: Text(t('gpsOut')),
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
                                Text(t('nfcGateTitle'), style: Theme.of(context).textTheme.titleSmall),
                                const SizedBox(height: 8),
                                Text(t('nfcGateHint')),
                                if (badgeId != null && badgeId.isNotEmpty) ...[
                                  const SizedBox(height: 8),
                                  Text(
                                    t('badgeIdLabel').replaceAll('{id}', badgeId),
                                    style: const TextStyle(fontFamily: 'monospace'),
                                  ),
                                ],
                              ],
                            ),
                          ),
                        ),
                        if (_lastDirection != null) ...[
                          const SizedBox(height: 8),
                          Text(t('lastAction').replaceAll('{dir}', _lastDirection!)),
                        ],
                      ],
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                  child: SizedBox(
                    width: double.infinity,
                    height: 56,
                    child: FilledButton.icon(
                      onPressed: _busy ? null : _tapAttendance,
                      icon: _busy
                          ? const SizedBox(
                              width: 22,
                              height: 22,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : const Icon(Icons.nfc, size: 28),
                      label: Text(_busy ? t('scanning') : t('nfcScanButton')),
                      style: FilledButton.styleFrom(textStyle: const TextStyle(fontSize: 16)),
                    ),
                  ),
                ),
                if (_status != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                    child: Text(
                      _status!,
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }
}
