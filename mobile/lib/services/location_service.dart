import 'dart:io' show Platform;

import 'package:geolocator/geolocator.dart';

/// Captures GPS for site-based geofence attendance (site_app mode).
class LocationService {
  static const maxAccuracyMeters = 200.0;
  /// Prefer a cached fix if younger than this — keeps check-in under ~1s.
  static const _freshCacheMaxAge = Duration(seconds: 90);
  static const _fastFixTimeout = Duration(milliseconds: 900);

  static const _foregroundNotification = ForegroundNotificationConfig(
    notificationTitle: 'SUPPIX Anwesenheit',
    notificationText: 'Standort wird für An- und Abwesenheit überwacht',
    notificationChannelName: 'Baustellen-Standort',
    enableWakeLock: true,
  );

  LocationSettings _watchSettings() {
    if (Platform.isAndroid) {
      return AndroidSettings(
        accuracy: LocationAccuracy.high,
        distanceFilter: 5,
        foregroundNotificationConfig: _foregroundNotification,
      );
    }
    if (Platform.isIOS) {
      return AppleSettings(
        accuracy: LocationAccuracy.high,
        distanceFilter: 5,
        allowBackgroundLocationUpdates: true,
        showBackgroundLocationIndicator: true,
        pauseLocationUpdatesAutomatically: false,
      );
    }
    return const LocationSettings(
      accuracy: LocationAccuracy.high,
      distanceFilter: 5,
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

  /// Returns true when at least while-in-use location is granted.
  Future<bool> ensureBackgroundPermission() async {
    final level = await requestLocationPermission();
    return level == LocationPermission.always ||
        level == LocationPermission.whileInUse;
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

  Stream<Position> watchPosition() {
    return Geolocator.getPositionStream(locationSettings: _watchSettings());
  }

  bool _usable(Position? position, {required Duration maxAge}) {
    if (position == null) return false;
    if (position.accuracy > maxAccuracyMeters) return false;
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
  /// Target: resolve in ≤1s via last-known / medium-accuracy fast fix.
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

      // Accept a slightly older cached fix rather than blocking the worker.
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

  Map<String, dynamic> _positionPayload(Position position) {
    return <String, dynamic>{
      'latitude': position.latitude,
      'longitude': position.longitude,
      'accuracyMeters': position.accuracy,
      'accuracy': position.accuracy,
      'capturedAt': DateTime.now().toUtc().toIso8601String(),
    };
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
