import 'dart:async';
import 'dart:math' as math;

import 'package:geolocator/geolocator.dart';
import 'package:uuid/uuid.dart';

import '../core/api_client.dart';
import '../core/worker_auth_errors.dart';
import 'location_service.dart';
import 'offline_attendance_store.dart';

typedef GeofenceNotify = void Function(String message);
typedef GeofencePresence = void Function(Map<String, dynamic> presence);

/// Live GPS for employer map during an active work session + optional site_app auto check-in/out.
///
/// Live pin updates only while [liveTracking] is true (checked-in). site_app auto
/// attendance can run without live tracking so workers can still punch in on site.
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
  bool _siteAppMode = false;
  bool _liveTracking = false;
  int _offSiteStrikes = 0;
  String? _lastNoticeKey;
  DateTime? _lastWatchPollAt;
  DateTime? _lastSentAt;
  DateTime? _lastSitePresenceAt;
  double? _lastSentLat;
  double? _lastSentLng;
  bool _trackingStartedNotified = false;

  Position? _pendingForcedPosition;
  Position? _latestStreamPosition;
  DateTime? _latestStreamAt;
  DateTime? _rateLimitedUntil;
  int _rateLimitNotices = 0;
  int _notCheckedInStrikes = 0;
  int _gpsFailStrikes = 0;
  String _lastStatus = '';

  /// Stream-driven movement is primary; heartbeat only fills gaps.
  static const pollInterval = Duration(milliseconds: 2000);

  static const positionDebounceMs = 120;
  static const minMoveMetersToSend = 0.5;
  static const heartbeatInterval = Duration(seconds: 3);
  static const minSendInterval = Duration(seconds: 2);
  static const offSiteStrikesRequired = 3;
  static const streamFreshForHeartbeat = Duration(seconds: 3);

  bool get liveTrackingActive => _running && _liveTracking;
  bool get isRunning => _running;
  /// Short status for UI: "Pin live", "GPS sendet…", "GPS fehlgeschlagen", …
  String get lastStatus => _lastStatus;

  /// Turn live map pings on/off without restarting site_app geofence.
  void setLiveTracking(bool enabled) {
    _liveTracking = enabled;
    if (!enabled) {
      _trackingStartedNotified = false;
      _notCheckedInStrikes = 0;
    } else {
      _notCheckedInStrikes = 0;
    }
  }

  /// Force an immediate GPS ping (e.g. right after check-in).
  Future<void> forcePing({
    required String bearer,
    String? deviceId,
    required bool autoLogout,
    GeofencePresence? onPresence,
    GeofenceNotify? onNotify,
  }) async {
    if (!_running) return;
    await _poll(
      bearer: bearer,
      deviceId: deviceId,
      autoLogout: autoLogout,
      onPresence: onPresence,
      onNotify: onNotify,
      reason: _PollReason.initial,
    );
  }

  Future<void> start({
    required String bearer,
    String? deviceId,
    required bool siteAppMode,
    bool liveTracking = false,
    required bool autoLogout,
    GeofencePresence? onPresence,
    GeofenceNotify? onNotify,
  }) async {
    stop();
    if (!siteAppMode && !liveTracking) return;

    final allowed = await _location.ensureBackgroundPermission();
    if (!allowed) {
      if (liveTracking) {
        onNotify?.call(
          'Standort-Berechtigung fehlt — bitte GPS erlauben.',
        );
      }
      return;
    }

    // Background / app-closed tracking needs "Allow all the time".
    var useBackgroundStream = false;
    if (liveTracking) {
      final always = await _location.ensureAlwaysPermission();
      useBackgroundStream = _location.isBackgroundCapable(always);
      if (!useBackgroundStream) {
        onNotify?.call(
          'App offen: Pin bewegt sich. Für geschlossene App: Standort «Immer erlauben».',
        );
      }
    }

    _running = true;
    _siteAppMode = siteAppMode;
    _liveTracking = liveTracking;
    _offSiteStrikes = 0;
    _lastNoticeKey = '';
    _lastSentAt = null;
    _lastSitePresenceAt = null;
    _lastSentLat = null;
    _lastSentLng = null;
    _trackingStartedNotified = false;
    _notCheckedInStrikes = 0;
    _gpsFailStrikes = 0;
    _pendingForcedPosition = null;
    _rateLimitedUntil = null;
    _rateLimitNotices = 0;
    _lastStatus = 'GPS startet…';

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

    void attachStream({required bool background}) {
      unawaited(_positionSub?.cancel());
      _positionSub = _location.watchPosition(background: background).listen(
        (position) {
          final now = DateTime.now();
          _latestStreamPosition = position;
          _latestStreamAt = now;
          if (_lastWatchPollAt != null &&
              now.difference(_lastWatchPollAt!).inMilliseconds <
                  positionDebounceMs) {
            _pendingForcedPosition = position;
            return;
          }
          _lastWatchPollAt = now;
          if (_pollInFlight) {
            _pendingForcedPosition = position;
            return;
          }
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
        onError: (Object error) {
          // FGS/notification failures are common on Android 13+ — fall back.
          if (background) {
            attachStream(background: false);
            onNotify?.call(
              'Hintergrund-GPS blockiert — App offen lassen für Live-Pin.',
            );
            return;
          }
          _lastStatus = 'GPS-Stream unterbrochen';
          onNotify?.call('GPS-Stream unterbrochen — bitte App im Vordergrund lassen.');
        },
      );
    }

    // Prefer FGS/background stream when Always is granted; else foreground-only.
    attachStream(background: useBackgroundStream);

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
    _siteAppMode = false;
    _liveTracking = false;
    _timer?.cancel();
    _timer = null;
    unawaited(_positionSub?.cancel());
    _positionSub = null;
    _pollInFlight = false;
    _leaveInProgress = false;
    _offSiteStrikes = 0;
    _notCheckedInStrikes = 0;
    _gpsFailStrikes = 0;
    _pendingForcedPosition = null;
    _latestStreamPosition = null;
    _latestStreamAt = null;
    _rateLimitedUntil = null;
    _rateLimitNotices = 0;
    _lastNoticeKey = null;
    _lastWatchPollAt = null;
    _lastSentAt = null;
    _lastSitePresenceAt = null;
    _lastSentLat = null;
    _lastSentLng = null;
    _trackingStartedNotified = false;
    _lastStatus = '';
  }

  bool _shouldSend({
    required double lat,
    required double lng,
    required _PollReason reason,
  }) {
    final now = DateTime.now();
    if (_rateLimitedUntil != null && now.isBefore(_rateLimitedUntil!)) {
      return false;
    }
    if (_lastSentAt != null &&
        now.difference(_lastSentAt!) < minSendInterval &&
        reason != _PollReason.initial) {
      return false;
    }
    if (reason == _PollReason.initial || reason == _PollReason.movement) {
      if (_lastSentLat == null || _lastSentLng == null) return true;
      final moved = _distanceMeters(_lastSentLat!, _lastSentLng!, lat, lng);
      if (moved >= minMoveMetersToSend) return true;
      // Movement events still heartbeat so lastLocationAt stays fresh.
      if (_lastSentAt != null &&
          now.difference(_lastSentAt!) >= heartbeatInterval) {
        return true;
      }
      return false;
    }
    if (_lastSentLat == null || _lastSentLng == null || _lastSentAt == null) {
      return true;
    }
    final moved = _distanceMeters(_lastSentLat!, _lastSentLng!, lat, lng);
    if (moved >= minMoveMetersToSend) return true;
    if (now.difference(_lastSentAt!) >= heartbeatInterval) {
      return true;
    }
    return false;
  }

  Future<Map<String, dynamic>> _postLiveLocation({
    required String bearer,
    String? deviceId,
    required Map<String, dynamic> location,
  }) async {
    try {
      return await _api.postJson(
        '/api/worker-app/live-location',
        bearerToken: bearer,
        deviceId: deviceId,
        body: <String, dynamic>{'location': location},
      );
    } on ApiException catch (e) {
      // Older backends / deploy lag: fall back to site-presence (now also saves GPS).
      if (e.statusCode == 404 ||
          e.statusCode == 405 ||
          e.errorCode == 'not_found') {
        return await _api.postJson(
          '/api/worker-app/site-presence',
          bearerToken: bearer,
          deviceId: deviceId,
          body: <String, dynamic>{'location': location},
        );
      }
      rethrow;
    }
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
    // Keep live GPS posting even while site-leave is in flight.
    if (!_running || _pollInFlight) {
      if (forcedPosition != null) _pendingForcedPosition = forcedPosition;
      return;
    }
    if (_leaveInProgress && reason != _PollReason.heartbeat) {
      if (forcedPosition != null) _pendingForcedPosition = forcedPosition;
      return;
    }
    _pollInFlight = true;
    try {
      Map<String, dynamic>? location;
      final streamFresh = _latestStreamAt != null &&
          DateTime.now().difference(_latestStreamAt!) <= streamFreshForHeartbeat;
      final Position? preferred = forcedPosition ??
          (streamFresh ? _latestStreamPosition : null);

      if (preferred != null &&
          preferred.accuracy <= LocationService.liveMapMaxAccuracyMeters) {
        // Stream / movement path — never block on getCurrentPosition.
        location = _location.positionToPayload(preferred);
      } else if (reason == _PollReason.heartbeat) {
        // Heartbeat must stay short; a 4s fix starves the watch stream.
        location = await _location.captureQuickForLiveHeartbeat();
      } else {
        location = await _location.captureFreshForLiveMap();
      }
      if (location == null) {
        _gpsFailStrikes += 1;
        _lastStatus = 'GPS-Signal fehlt';
        if (_gpsFailStrikes == 3) {
          onNotify?.call(
            'Kein GPS-Signal — Standortdienste prüfen und App im Vordergrund lassen.',
          );
        }
        return;
      }

      final accuracy = (location['accuracyMeters'] as num?)?.toDouble();
      if (accuracy != null &&
          accuracy > LocationService.liveMapMaxAccuracyMeters) {
        _lastStatus = 'GPS zu ungenau';
        return;
      }

      final lat = (location['latitude'] as num).toDouble();
      final lng = (location['longitude'] as num).toDouble();
      _gpsFailStrikes = 0;

      // Live map pings while tracking is enabled (server always stores coords).
      if (_liveTracking) {
        if (!_shouldSend(lat: lat, lng: lng, reason: reason)) {
          // Still allow site_app presence path below on heartbeat/initial.
        } else {
          final result = await _postLiveLocation(
            bearer: bearer,
            deviceId: deviceId,
            location: location,
          );
          _lastSentAt = DateTime.now();
          _lastSentLat = lat;
          _lastSentLng = lng;
          onPresence?.call(result);

          if (result['locationSaved'] == true) {
            _notCheckedInStrikes = 0;
            _rateLimitedUntil = null;
            _rateLimitNotices = 0;
            _lastStatus = 'Pin live · GPS gespeichert';
            if (!_trackingStartedNotified) {
              _trackingStartedNotified = true;
              onNotify?.call(
                'Live-Standort aktiv — Pin bewegt sich auf der Karte.',
              );
            }
          } else if (result['reason'] == 'not_checked_in' ||
              result['trackingActive'] == false) {
            // Keep sending; server may accept as soon as check-in is visible.
            _notCheckedInStrikes += 1;
            _lastStatus = 'GPS sendet · warte auf Check-in';
            if (_notCheckedInStrikes == 1) {
              onNotify?.call(
                'GPS läuft — Pin bewegt sich nach erfolgreichem Check-in.',
              );
            }
          } else if (result['locationSaved'] == false) {
            _lastStatus = 'GPS Antwort ohne Speicherung';
          } else {
            // Older/partial responses — still treat as ok if request succeeded.
            _lastStatus = 'Pin live · GPS gesendet';
          }
        }
      }

      // Attendance / auto leave stays on site-presence (site_app only, less often).
      final shouldPingPresence = _siteAppMode &&
          (reason == _PollReason.initial ||
              (reason == _PollReason.heartbeat &&
                  (_lastSitePresenceAt == null ||
                      DateTime.now().difference(_lastSitePresenceAt!) >=
                          const Duration(seconds: 15))));
      if (shouldPingPresence) {
        try {
          final presence = await _api.postJson(
            '/api/worker-app/site-presence',
            bearerToken: bearer,
            deviceId: deviceId,
            body: <String, dynamic>{'location': location},
          );
          _lastSitePresenceAt = DateTime.now();
          onPresence?.call(presence);
          await _handleSiteAppPresenceSideEffects(
            presence: presence,
            bearer: bearer,
            deviceId: deviceId,
            location: location,
            autoLogout: autoLogout,
            onNotify: onNotify,
          );
        } catch (_) {
          // live-location already saved; attendance ping can fail independently
        }
      }
    } on ApiException catch (e) {
      if (e.statusCode == 429 || e.errorCode == 'rate_limited') {
        final retry = (e.payload?['retryAfterSeconds'] as num?)?.toInt() ?? 20;
        _rateLimitedUntil =
            DateTime.now().add(Duration(seconds: retry.clamp(5, 120)));
        _lastStatus = 'GPS pausiert (429) · ${retry}s';
        _rateLimitNotices += 1;
        if (_rateLimitNotices == 1) {
          onNotify?.call(
            'Zu viele Anfragen — Live-GPS pausiert kurz, dann weiter.',
          );
        }
        return;
      }
      _lastStatus = 'GPS-Serverfehler (${e.statusCode})';
      if (e.errorCode == 'worker_geolocation_inaccurate' ||
          e.errorCode == 'worker_geolocation_required' ||
          e.errorCode == 'site_location_unavailable') {
        return;
      }
      if (isWorkerSessionAuthError(e.errorCode)) {
        onNotify?.call('Sitzung abgelaufen — bitte erneut anmelden.');
      } else if (_notCheckedInStrikes <= 1) {
        onNotify?.call('Live-GPS konnte nicht gesendet werden (${e.statusCode}).');
      }
    } catch (_) {
      _lastStatus = 'GPS Netzwerkfehler';
      // ignore transient GPS/network errors
    } finally {
      _pollInFlight = false;
      final pending = _pendingForcedPosition;
      _pendingForcedPosition = null;
      if (_running && pending != null) {
        unawaited(
          _poll(
            bearer: bearer,
            deviceId: deviceId,
            autoLogout: autoLogout,
            onPresence: onPresence,
            onNotify: onNotify,
            reason: _PollReason.movement,
            forcedPosition: pending,
          ),
        );
      }
    }
  }

  Future<void> _handleSiteAppPresenceSideEffects({
    required Map<String, dynamic> presence,
    required String bearer,
    String? deviceId,
    required Map<String, dynamic> location,
    required bool autoLogout,
    GeofenceNotify? onNotify,
  }) async {
      if (presence['autoCheckInLogId'] != null) {
        _liveTracking = true;
        _notifyOnce(
          'checkin:${presence['autoCheckInLogId']}',
          'Automatischer Check-in an der Baustelle',
          onNotify,
        );
      } else if (presence['siteLoginLogId'] != null) {
        _liveTracking = true;
        _notifyOnce(
          'login:${presence['siteLoginLogId']}',
          'Standort auf der Baustelle registriert',
          onNotify,
        );
      } else if (presence['siteLeaveApplied'] == true) {
        // Keep GPS loop alive — server/map decide whether the pin is shown.
        _liveTracking = true;
        final leaveKey =
            'leave:${presence['checkoutLogId'] ?? presence['siteLeaveLogId'] ?? 'applied'}';
        _notifyOnce(
          leaveKey,
          'Automatischer Check-out — Baustelle verlassen',
          onNotify,
        );
        _offSiteStrikes = 0;
        return;
      } else if (presence['attendanceBlocked'] is Map) {
        final blocked = Map<String, dynamic>.from(
          presence['attendanceBlocked'] as Map,
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

      final offSiteForLeave = presence['onSiteForLeave'] == false ||
          (presence['onSiteForLeave'] == null && presence['onSite'] != true);
      final registeredOnSite = presence['openCheckInToday'] == true ||
          presence['siteSessionOpen'] == true;

      if (offSiteForLeave &&
          autoLogout &&
          registeredOnSite &&
          presence['siteLeaveApplied'] != true) {
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
      // Keep posting GPS; map hides the pin when no longer on site.
      _liveTracking = true;
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
