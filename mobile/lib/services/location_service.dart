import 'dart:io' show Platform;

import 'package:geolocator/geolocator.dart';

/// Captures GPS for site-based geofence attendance (site_app mode).
class LocationService {
  static const maxAccuracyMeters = 200.0;

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

  LocationSettings _captureSettings() {
    if (Platform.isAndroid) {
      // One-shot GPS: no foreground service — avoids silent failures on some devices.
      return AndroidSettings(
        accuracy: LocationAccuracy.high,
        timeLimit: const Duration(seconds: 25),
      );
    }
    if (Platform.isIOS) {
      return AppleSettings(
        accuracy: LocationAccuracy.high,
        timeLimit: const Duration(seconds: 25),
      );
    }
    return const LocationSettings(
      accuracy: LocationAccuracy.high,
      timeLimit: Duration(seconds: 25),
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

  /// Returns null when GPS unavailable; throws [LocationCaptureException] with user hint.
  Future<Map<String, dynamic>?> captureForAttendance() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      throw LocationCaptureException(
        'GPS ist am Handy aus — bitte Standort aktivieren.',
        openSettings: true,
      );
    }

    final permission = await requestLocationPermission();
    if (permission == LocationPermission.denied) {
      throw LocationCaptureException(
        'Standortfreigabe fehlt — bitte „Beim Verwenden der App“ erlauben.',
      );
    }
    if (permission == LocationPermission.deniedForever) {
      throw LocationCaptureException(
        'Standort dauerhaft blockiert — in Android-Einstellungen für SUPPIX erlauben.',
        openSettings: true,
      );
    }

    try {
      final position = await Geolocator.getCurrentPosition(
        locationSettings: _captureSettings(),
      );
      return _positionPayload(position);
    } on LocationServiceDisabledException {
      throw LocationCaptureException(
        'GPS ist aus — bitte Standortdienst aktivieren.',
        openSettings: true,
      );
    } on PermissionDeniedException {
      throw LocationCaptureException(
        'Standortfreigabe verweigert — bitte erneut erlauben.',
      );
    } catch (e) {
      throw LocationCaptureException(
        'Standort konnte nicht ermittelt werden: $e',
      );
    }
  }

  Map<String, dynamic> _positionPayload(Position position) {
    return <String, dynamic>{
      'latitude': position.latitude,
      'longitude': position.longitude,
      'accuracyMeters': position.accuracy,
      'capturedAt': DateTime.now().toUtc().toIso8601String(),
    };
  }
}

class LocationCaptureException implements Exception {
  LocationCaptureException(this.message, {this.openSettings = false});

  final String message;
  final bool openSettings;

  @override
  String toString() => message;
}
