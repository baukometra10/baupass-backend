import 'dart:async';
import 'dart:math' as math;

import 'package:geolocator/geolocator.dart';
import 'package:uuid/uuid.dart';

import '../core/api_client.dart';
import 'location_service.dart';
import 'offline_attendance_store.dart';

typedef GeofenceNotify = void Function(String message);
typedef GeofencePresence = void Function(Map<String, dynamic> presence);

/// Site geofence monitor (PWA parity): movement-triggered presence + sparse heartbeat.
///
/// Battery strategy:
/// - OS distanceFilter (~12 m) — GPS callbacks only when the worker moves
/// - Network POST only on significant move OR heartbeat (~60 s) while on duty
/// - Slow timer when idle (no continuous 5 s GPS spam)
class GeofenceService {
  GeofenceService(this._api, this._location, this._offlineStore);

  final ApiClient _api;
  final LocationService _location;
  final OfflineAttendanceStore _offlineStore;
  final _uuid = const Uuid();

  Timer? _timer;
  StreamSubscription<Position>? _positionSub;
  bool _running = false;
  bool _pollInFlight = false;
  bool _leaveInProgress = false;
  int _offSiteStrikes = 0;
  String? _lastNoticeKey;
  DateTime? _lastWatchPollAt;
  DateTime? _lastSentAt;
  double? _lastSentLat;
  double? _lastSentLng;

  /// Idle heartbeat for freshness / leave detection (not continuous tracking).
  static const pollInterval = Duration(seconds: 45);

  /// Debounce rapid GPS stream events after a move.
  static const positionDebounceMs = 2500;

  /// Significant move before another live-map update (meters).
  static const minMoveMetersToSend = 10.0;

  /// Max silence while on site — keeps employer map "fresh" without draining battery.
  static const heartbeatInterval = Duration(seconds: 60);

  static const offSiteStrikesRequired = 3;

  Future<void> start({
    required String bearer,
    String? deviceId,
    required bool siteAppMode,
    required bool autoLogout,
    GeofencePresence? onPresence,
    GeofenceNotify? onNotify,
  }) async {
    stop();
    if (!siteAppMode) return;

    final allowed = await _location.ensureBackgroundPermission();
    if (!allowed) return;

    _running = true;
    _offSiteStrikes = 0;
    _lastNoticeKey = '';
    _lastSentAt = null;
    _lastSentLat = null;
    _lastSentLng = null;

    void schedulePoll() {
      _timer?.cancel();
      _timer = Timer.periodic(pollInterval, (_) {
        unawaited(
          _poll(
            bearer: bearer,
            deviceId: deviceId,
            autoLogout: autoLogout,
            onPresence: onPresence,
            onNotify: onNotify,
            reason: _PollReason.heartbeat,
          ),
        );
      });
    }

    _positionSub = _location.watchPosition().listen(
      (position) {
        final now = DateTime.now();
        if (_lastWatchPollAt != null &&
            now.difference(_lastWatchPollAt!).inMilliseconds <
                positionDebounceMs) {
          return;
        }
        _lastWatchPollAt = now;
        unawaited(
          _poll(
            bearer: bearer,
            deviceId: deviceId,
            autoLogout: autoLogout,
            onPresence: onPresence,
            onNotify: onNotify,
            reason: _PollReason.movement,
            forcedPosition: position,
          ),
        );
      },
      onError: (_) {},
    );

    schedulePoll();
    await _poll(
      bearer: bearer,
      deviceId: deviceId,
      autoLogout: autoLogout,
      onPresence: onPresence,
      onNotify: onNotify,
      reason: _PollReason.initial,
    );
  }

  void stop() {
    _running = false;
    _timer?.cancel();
    _timer = null;
    unawaited(_positionSub?.cancel());
    _positionSub = null;
    _pollInFlight = false;
    _leaveInProgress = false;
    _offSiteStrikes = 0;
    _lastNoticeKey = null;
    _lastWatchPollAt = null;
    _lastSentAt = null;
    _lastSentLat = null;
    _lastSentLng = null;
  }

  bool _shouldSend({
    required double lat,
    required double lng,
    required _PollReason reason,
  }) {
    if (reason == _PollReason.initial) return true;
    if (_lastSentLat == null || _lastSentLng == null || _lastSentAt == null) {
      return true;
    }
    final moved = _distanceMeters(_lastSentLat!, _lastSentLng!, lat, lng);
    if (moved >= minMoveMetersToSend) return true;
    // Stationary: sparse heartbeat only (leave detection + live freshness).
    if (DateTime.now().difference(_lastSentAt!) >= heartbeatInterval) {
      return true;
    }
    return false;
  }

  Future<void> _poll({
    required String bearer,
    String? deviceId,
    required bool autoLogout,
    GeofencePresence? onPresence,
    GeofenceNotify? onNotify,
    required _PollReason reason,
    Position? forcedPosition,
  }) async {
    if (!_running || _pollInFlight || _leaveInProgress) return;
    _pollInFlight = true;
    try {
      Map<String, dynamic>? location;
      if (forcedPosition != null) {
        if (forcedPosition.accuracy > LocationService.maxAccuracyMeters) {
          return;
        }
        location = <String, dynamic>{
          'latitude': forcedPosition.latitude,
          'longitude': forcedPosition.longitude,
          'accuracyMeters': forcedPosition.accuracy,
          'accuracy': forcedPosition.accuracy,
          'capturedAt': DateTime.now().toUtc().toIso8601String(),
        };
      } else {
        location = await _location.captureForAttendance();
      }
      if (location == null) return;

      final accuracy = (location['accuracyMeters'] as num?)?.toDouble();
      if (accuracy != null && accuracy > LocationService.maxAccuracyMeters) {
        return;
      }

      final lat = (location['latitude'] as num).toDouble();
      final lng = (location['longitude'] as num).toDouble();
      if (!_shouldSend(lat: lat, lng: lng, reason: reason)) {
        return;
      }

      final result = await _api.postJson(
        '/api/worker-app/site-presence',
        bearerToken: bearer,
        deviceId: deviceId,
        body: <String, dynamic>{'location': location},
      );
      _lastSentAt = DateTime.now();
      _lastSentLat = lat;
      _lastSentLng = lng;
      onPresence?.call(result);

      if (result['autoCheckInLogId'] != null) {
        _notifyOnce(
          'checkin:${result['autoCheckInLogId']}',
          'Automatischer Check-in an der Baustelle',
          onNotify,
        );
      } else if (result['siteLoginLogId'] != null) {
        _notifyOnce(
          'login:${result['siteLoginLogId']}',
          'Standort auf der Baustelle registriert',
          onNotify,
        );
      } else if (result['siteLeaveApplied'] == true) {
        final leaveKey =
            'leave:${result['checkoutLogId'] ?? result['siteLeaveLogId'] ?? 'applied'}';
        _notifyOnce(
          leaveKey,
          'Automatischer Check-out — Baustelle verlassen',
          onNotify,
        );
        _offSiteStrikes = 0;
        return;
      } else if (result['attendanceBlocked'] is Map) {
        final blocked = Map<String, dynamic>.from(
          result['attendanceBlocked'] as Map,
        );
        final msg = blocked['message']?.toString();
        if (msg != null && msg.isNotEmpty) {
          _notifyOnce(
            'blocked:${blocked['reason'] ?? msg}',
            msg,
            onNotify,
          );
        }
      }

      final offSiteForLeave = result['onSiteForLeave'] == false ||
          (result['onSiteForLeave'] == null && result['onSite'] != true);
      final registeredOnSite = result['openCheckInToday'] == true ||
          result['siteSessionOpen'] == true;

      if (offSiteForLeave &&
          autoLogout &&
          registeredOnSite &&
          result['siteLeaveApplied'] != true) {
        _offSiteStrikes += 1;
        if (_offSiteStrikes >= offSiteStrikesRequired) {
          await _handleSiteLeave(
            bearer: bearer,
            deviceId: deviceId,
            location: location,
            onNotify: onNotify,
          );
        }
      } else {
        _offSiteStrikes = 0;
      }
    } on ApiException catch (e) {
      if (e.errorCode == 'worker_geolocation_inaccurate' ||
          e.errorCode == 'worker_geolocation_required' ||
          e.errorCode == 'site_location_unavailable') {
        return;
      }
    } catch (_) {
      // ignore transient GPS/network errors
    } finally {
      _pollInFlight = false;
    }
  }

  Future<void> _handleSiteLeave({
    required String bearer,
    String? deviceId,
    required Map<String, dynamic> location,
    GeofenceNotify? onNotify,
  }) async {
    if (_leaveInProgress) return;
    _leaveInProgress = true;
    try {
      await _api.postJson(
        '/api/worker-app/site-leave',
        bearerToken: bearer,
        deviceId: deviceId,
        body: <String, dynamic>{'location': location},
      );
      onNotify?.call('Automatischer Check-out — Baustelle verlassen');
    } catch (_) {
      await _offlineStore.enqueue(<String, dynamic>{
        'type': 'site_leave',
        'occurredAt': DateTime.now().toUtc().toIso8601String(),
        'location': location,
        'clientEventId': 'site-leave-${_uuid.v4()}',
      });
      onNotify?.call('Check-out offline gespeichert — wird synchronisiert');
    } finally {
      _leaveInProgress = false;
      _offSiteStrikes = 0;
    }
  }

  void _notifyOnce(String key, String message, GeofenceNotify? onNotify) {
    if (key == _lastNoticeKey) return;
    _lastNoticeKey = key;
    onNotify?.call(message);
  }

  static double _distanceMeters(
    double lat1,
    double lng1,
    double lat2,
    double lng2,
  ) {
    const earth = 6371000.0;
    final p1 = lat1 * math.pi / 180;
    final p2 = lat2 * math.pi / 180;
    final dp = (lat2 - lat1) * math.pi / 180;
    final dl = (lng2 - lng1) * math.pi / 180;
    final a = math.sin(dp / 2) * math.sin(dp / 2) +
        math.cos(p1) * math.cos(p2) * math.sin(dl / 2) * math.sin(dl / 2);
    return 2 * earth * math.asin(math.sqrt(a));
  }
}

enum _PollReason { initial, movement, heartbeat }
