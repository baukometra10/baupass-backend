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
  bool _usingBackgroundStream = false;
  String? _sessionBearer;
  String? _sessionDeviceId;
  bool _sessionAutoLogout = true;
  GeofencePresence? _sessionOnPresence;
  GeofenceNotify? _sessionOnNotify;
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
  DateTime? _lastSuccessAt;
  int _rateLimitNotices = 0;
  int _notCheckedInStrikes = 0;
  int _gpsFailStrikes = 0;
  int _networkFailStrikes = 0;
  String _lastStatus = '';
  String _stableOkStatus = 'Pin live · verbunden';

  /// Stream-driven movement is primary; heartbeat only fills gaps.
  static const pollInterval = Duration(seconds: 20);

  static const positionDebounceMs = 250;
  /// Clear step-level signal: send when the worker moved ~1 m (saves battery + server).
  static const minMoveMetersToSend = 1.0;
  /// Keep lastLocationAt fresh while standing still (not every few seconds).
  static const heartbeatInterval = Duration(seconds: 45);
  static const minSendInterval = Duration(seconds: 3);
  static const offSiteStrikesRequired = 3;
  static const streamFreshForHeartbeat = Duration(seconds: 8);
  static const statusHoldAfterSuccess = Duration(seconds: 90);

  bool get liveTrackingActive => _running && _liveTracking;
  bool get isRunning => _running;
  /// True when OS "Always" permission + FGS stream is active.
  bool get backgroundTrackingActive => _running && _usingBackgroundStream;
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
    _usingBackgroundStream = useBackgroundStream;
    _sessionBearer = bearer;
    _sessionDeviceId = deviceId;
    _sessionAutoLogout = autoLogout;
    _sessionOnPresence = onPresence;
    _sessionOnNotify = onNotify;
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
    _networkFailStrikes = 0;
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

    // Prefer FGS/background stream when Always is granted; else foreground-only.
    _attachPositionStream(background: useBackgroundStream);

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

  /// If the user later grants «Immer erlauben», switch the GPS stream to FGS/background.
  Future<bool> refreshBackgroundCapability({GeofenceNotify? onNotify}) async {
    if (!_running || !_liveTracking) return false;
    final always = await _location.ensureAlwaysPermission();
    final wantBg = _location.isBackgroundCapable(always);
    if (wantBg == _usingBackgroundStream) return wantBg;
    _usingBackgroundStream = wantBg;
    _attachPositionStream(background: wantBg);
    if (wantBg) {
      _markGpsSuccess('Pin live · Hintergrund aktiv');
      onNotify?.call(
        'Hintergrund-GPS aktiv — Pin bewegt sich auch bei geschlossener App.',
      );
    } else {
      _markGpsSuccess('Pin live · App offen halten');
    }
    return wantBg;
  }

  void _attachPositionStream({required bool background}) {
    final bearer = _sessionBearer;
    if (bearer == null || bearer.isEmpty) return;
    final deviceId = _sessionDeviceId;
    final autoLogout = _sessionAutoLogout;
    final onPresence = _sessionOnPresence;
    final onNotify = _sessionOnNotify;

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
        if (background) {
          _usingBackgroundStream = false;
          _attachPositionStream(background: false);
          onNotify?.call(
            'Hintergrund-GPS blockiert — App offen lassen für Live-Pin.',
          );
          return;
        }
        _lastStatus = 'GPS-Stream unterbrochen';
        onNotify?.call(
          'GPS-Stream unterbrochen — bitte App im Vordergrund lassen.',
        );
      },
    );
  }

  void stop() {
    _running = false;
    _siteAppMode = false;
    _liveTracking = false;
    _usingBackgroundStream = false;
    _sessionBearer = null;
    _sessionDeviceId = null;
    _sessionAutoLogout = true;
    _sessionOnPresence = null;
    _sessionOnNotify = null;
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
    _networkFailStrikes = 0;
    _lastSuccessAt = null;
    _lastNoticeKey = null;
    _lastWatchPollAt = null;
    _lastSentAt = null;
    _lastSitePresenceAt = null;
    _lastSentLat = null;
    _lastSentLng = null;
    _trackingStartedNotified = false;
    _lastStatus = '';
  }

  void _markGpsSuccess([String status = 'Pin live · verbunden']) {
    _lastSuccessAt = DateTime.now();
    _networkFailStrikes = 0;
    _gpsFailStrikes = 0;
    _stableOkStatus = status;
    _lastStatus = status;
  }

  void _markTransientFailure(String status, {bool force = false}) {
    _networkFailStrikes += 1;
    // Keep a calm "verbunden" banner after recent success — avoids connect/disconnect flicker.
    if (!force &&
        _lastSuccessAt != null &&
        DateTime.now().difference(_lastSuccessAt!) < statusHoldAfterSuccess &&
        _networkFailStrikes < 3) {
      _lastStatus = _stableOkStatus;
      return;
    }
    _lastStatus = status;
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
          // No send this tick — keep calm connected status.
          if (_lastSuccessAt != null) {
            _lastStatus = _stableOkStatus;
          }
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
            _markGpsSuccess(
              _usingBackgroundStream
                  ? 'Pin live · Hintergrund aktiv'
                  : 'Pin live · verbunden',
            );
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
            final err = (result['saveError'] ?? result['saveReason'] ?? '')
                .toString()
                .trim();
            _markTransientFailure(
              err.isEmpty
                  ? 'GPS empfangen · Speichern fehlgeschlagen'
                  : 'Speichern fehlgeschlagen: ${err.length > 42 ? err.substring(0, 42) : err}',
              force: true,
            );
            if (_notCheckedInStrikes == 0) {
              _notCheckedInStrikes = 1;
              onNotify?.call(
                err.isEmpty
                    ? 'GPS kommt an, Speichern fehlgeschlagen — bitte App kurz neu starten.'
                    : 'GPS-Speichern fehlgeschlagen ($err).',
              );
            }
          } else {
            // Older/partial responses — still treat as ok if request succeeded.
            _markGpsSuccess(
              _usingBackgroundStream
                  ? 'Pin live · Hintergrund aktiv'
                  : 'Pin live · verbunden',
            );
          }
        }
      }

      // Attendance / auto leave stays on site-presence (site_app only, less often).
      final shouldPingPresence = _siteAppMode &&
          (reason == _PollReason.initial ||
              (reason == _PollReason.heartbeat &&
                  (_lastSitePresenceAt == null ||
                      DateTime.now().difference(_lastSitePresenceAt!) >=
                          const Duration(seconds: 45))));
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
      if (e.statusCode == 429 ||
          e.errorCode == 'rate_limited' ||
          e.statusCode == 502 ||
          e.statusCode == 503 ||
          e.statusCode == 504) {
        final retry = (e.payload?['retryAfterSeconds'] as num?)?.toInt() ??
            (e.statusCode == 429 ? 30 : 20);
        _rateLimitedUntil =
            DateTime.now().add(Duration(seconds: retry.clamp(10, 120)));
        _markTransientFailure('GPS pausiert (${e.statusCode}) · ${retry}s');
        _rateLimitNotices += 1;
        if (_rateLimitNotices == 1 && _networkFailStrikes >= 3) {
          onNotify?.call(
            e.statusCode == 429
                ? 'Zu viele Anfragen — Live-GPS pausiert kurz, dann weiter.'
                : 'Server kurz überlastet (${e.statusCode}) — GPS pausiert, dann weiter.',
          );
        }
        return;
      }
      _markTransientFailure('GPS-Serverfehler (${e.statusCode})');
      if (e.errorCode == 'worker_geolocation_inaccurate' ||
          e.errorCode == 'worker_geolocation_required' ||
          e.errorCode == 'site_location_unavailable') {
        return;
      }
      if (isWorkerSessionAuthError(e.errorCode)) {
        onNotify?.call('Sitzung abgelaufen — bitte erneut anmelden.');
      } else if (_networkFailStrikes >= 3 && _rateLimitNotices == 0) {
        onNotify?.call('Live-GPS konnte nicht gesendet werden (${e.statusCode}).');
      }
    } catch (_) {
      _markTransientFailure('GPS Netzwerkfehler');
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
