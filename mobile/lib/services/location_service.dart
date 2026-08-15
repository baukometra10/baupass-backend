import 'dart:io' show Platform;

import 'package:geolocator/geolocator.dart';

/// Captures GPS for attendance + continuous live-map tracking (incl. background).
class LocationService {
  static const maxAccuracyMeters = 350.0;
  /// Soft gate for live-map pings (server accepts up to ~500 m).
  static const liveMapMaxAccuracyMeters = 500.0;
  /// Prefer a cached fix if younger than this — keeps check-in under ~1s.
  static const _freshCacheMaxAge = Duration(seconds: 90);
  static const _fastFixTimeout = Duration(milliseconds: 900);
  /// Live map must not reuse stale lastKnown — that freezes the pin while walking.
  static const _liveLastKnownMaxAge = Duration(seconds: 2);

  static const _foregroundNotification = ForegroundNotificationConfig(
    notificationTitle: 'SUPPIX Live-Standort',
    notificationText:
        'Standort wird für die Live-Karte gesendet (Check-in aktiv).',
    notificationChannelName: 'Live-Standort',
    enableWakeLock: true,
    setOngoing: true,
  );

  LocationSettings _watchSettings({required bool background}) {
    if (Platform.isAndroid) {
      return AndroidSettings(
        accuracy: LocationAccuracy.bestForNavigation,
        // OS-level gate: wake the stream when the device moved ~1 m.
        // App-level [GeofenceService.minMoveMetersToSend] also filters to 1 m.
        distanceFilter: 1,
        // FGS notification is required for background; omit it for reliable
        // foreground-only tracking when notification permission is missing.
        foregroundNotificationConfig:
            background ? _foregroundNotification : null,
      );
    }
    if (Platform.isIOS) {
      return AppleSettings(
        accuracy: LocationAccuracy.bestForNavigation,
        distanceFilter: 1,
        allowBackgroundLocationUpdates: background,
        showBackgroundLocationIndicator: background,
        pauseLocationUpdatesAutomatically: false,
        activityType: ActivityType.otherNavigation,
      );
    }
    return const LocationSettings(
      accuracy: LocationAccuracy.bestForNavigation,
      distanceFilter: 1,
    );
  }

  LocationSettings _fastCaptureSettings() {
    if (Platform.isAndroid) {
      return AndroidSettings(
        accuracy: LocationAccuracy.medium,
        timeLimit: _fastFixTimeout,
      );
    }
    if (Platform.isIOS) {
      return AppleSettings(
        accuracy: LocationAccuracy.medium,
        timeLimit: _fastFixTimeout,
      );
    }
    return const LocationSettings(
      accuracy: LocationAccuracy.medium,
      timeLimit: _fastFixTimeout,
    );
  }

  LocationSettings _liveCaptureSettings() {
    if (Platform.isAndroid) {
      return AndroidSettings(
        accuracy: LocationAccuracy.bestForNavigation,
        timeLimit: const Duration(seconds: 4),
      );
    }
    if (Platform.isIOS) {
      return AppleSettings(
        accuracy: LocationAccuracy.bestForNavigation,
        timeLimit: const Duration(seconds: 4),
      );
    }
    return const LocationSettings(
      accuracy: LocationAccuracy.bestForNavigation,
      timeLimit: Duration(seconds: 4),
    );
  }

  /// At least while-in-use (needed to start tracking).
  Future<bool> ensureBackgroundPermission() async {
    final level = await requestLocationPermission();
    return level == LocationPermission.always ||
        level == LocationPermission.whileInUse;
  }

  /// Escalate to "Allow all the time" so GPS continues when the app is closed.
  /// Android 10+ requires a second prompt after while-in-use.
  Future<LocationPermission> ensureAlwaysPermission() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      return LocationPermission.denied;
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.whileInUse) {
      // Second request surfaces the "Allow all the time" option on Android.
      permission = await Geolocator.requestPermission();
    }
    return permission;
  }

  Future<LocationPermission> requestLocationPermission() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      return LocationPermission.denied;
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    return permission;
  }

  bool isBackgroundCapable(LocationPermission permission) {
    return permission == LocationPermission.always;
  }

  /// Continuous GPS stream. Prefer [background]=true when Always is granted.
  Stream<Position> watchPosition({bool background = false}) {
    return Geolocator.getPositionStream(
      locationSettings: _watchSettings(background: background),
    );
  }

  bool _usable(
    Position? position, {
    required Duration maxAge,
    double maxAccuracy = maxAccuracyMeters,
  }) {
    if (position == null) return false;
    if (position.accuracy > maxAccuracy) return false;
    final age = DateTime.now().difference(position.timestamp);
    if (age.isNegative) return true;
    return age <= maxAge;
  }

  /// Warm GPS cache so the next check-in can resolve in under a second.
  Future<void> warmAttendanceGps() async {
    try {
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) return;
      final permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return;
      }
      await Geolocator.getCurrentPosition(locationSettings: _fastCaptureSettings());
    } catch (_) {
      /* best-effort warm-up */
    }
  }

  /// Returns null when GPS unavailable; throws [LocationCaptureException] with i18n key.
  Future<Map<String, dynamic>?> captureForAttendance() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      throw LocationCaptureException('gpsOff', openSettings: true);
    }

    final permission = await requestLocationPermission();
    if (permission == LocationPermission.denied) {
      throw LocationCaptureException('gpsPermissionDenied');
    }
    if (permission == LocationPermission.deniedForever) {
      throw LocationCaptureException('gpsPermissionForever', openSettings: true);
    }

    try {
      Position? lastKnown;
      try {
        lastKnown = await Geolocator.getLastKnownPosition();
      } catch (_) {
        lastKnown = null;
      }
      if (_usable(lastKnown, maxAge: _freshCacheMaxAge)) {
        return _positionPayload(lastKnown!);
      }

      try {
        final fresh = await Geolocator.getCurrentPosition(
          locationSettings: _fastCaptureSettings(),
        );
        if (fresh.accuracy <= maxAccuracyMeters) {
          return _positionPayload(fresh);
        }
      } catch (_) {
        /* fall through to older cache / error */
      }

      if (_usable(lastKnown, maxAge: const Duration(minutes: 10))) {
        return _positionPayload(lastKnown!);
      }

      throw LocationCaptureException('gpsSlowOrInaccurate');
    } on LocationCaptureException {
      rethrow;
    } on LocationServiceDisabledException {
      throw LocationCaptureException('gpsOff', openSettings: true);
    } on PermissionDeniedException {
      throw LocationCaptureException('gpsPermissionDenied');
    } catch (_) {
      throw LocationCaptureException('gpsCaptureFailed');
    }
  }

  Map<String, dynamic> positionToPayload(Position position) {
    return <String, dynamic>{
      'latitude': position.latitude,
      'longitude': position.longitude,
      'accuracyMeters': position.accuracy,
      'accuracy': position.accuracy,
      'capturedAt': DateTime.now().toUtc().toIso8601String(),
    };
  }

  Map<String, dynamic> _positionPayload(Position position) =>
      positionToPayload(position);

  /// Short heartbeat fill-in — must not block the position stream (≤ ~1s).
  Future<Map<String, dynamic>?> captureQuickForLiveHeartbeat() async {
    try {
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) return null;
      final permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return null;
      }

      Position? lastKnown;
      try {
        lastKnown = await Geolocator.getLastKnownPosition();
      } catch (_) {
        lastKnown = null;
      }
      if (_usable(
        lastKnown,
        maxAge: const Duration(seconds: 3),
        maxAccuracy: liveMapMaxAccuracyMeters,
      )) {
        return positionToPayload(lastKnown!);
      }

      try {
        final fresh = await Geolocator.getCurrentPosition(
          locationSettings: _fastCaptureSettings(),
        );
        if (fresh.accuracy <= liveMapMaxAccuracyMeters) {
          return positionToPayload(fresh);
        }
      } catch (_) {
        /* no fix this tick */
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  /// Fresh GPS for initial / forced ping — never reuse a stale lastKnown pin.
  Future<Map<String, dynamic>?> captureFreshForLiveMap() async {
    try {
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) return null;
      final permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return null;
      }

      // Prefer a brand-new fix so walking updates the pin immediately.
      try {
        final fresh = await Geolocator.getCurrentPosition(
          locationSettings: _liveCaptureSettings(),
        );
        if (fresh.accuracy <= liveMapMaxAccuracyMeters) {
          return positionToPayload(fresh);
        }
      } catch (_) {
        /* fall through to ultra-fresh lastKnown */
      }

      Position? lastKnown;
      try {
        lastKnown = await Geolocator.getLastKnownPosition();
      } catch (_) {
        lastKnown = null;
      }
      if (_usable(
        lastKnown,
        maxAge: _liveLastKnownMaxAge,
        maxAccuracy: liveMapMaxAccuracyMeters,
      )) {
        return positionToPayload(lastKnown!);
      }
      return null;
    } catch (_) {
      return null;
    }
  }
}

class LocationCaptureException implements Exception {
  LocationCaptureException(this.messageKey, {this.openSettings = false});

  /// Key for [t] in app_strings.dart
  final String messageKey;
  final bool openSettings;

  @override
  String toString() => messageKey;
}
