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
      return AndroidSettings(
        accuracy: LocationAccuracy.high,
        timeLimit: const Duration(seconds: 12),
        foregroundNotificationConfig: _foregroundNotification,
      );
    }
    if (Platform.isIOS) {
      return AppleSettings(
        accuracy: LocationAccuracy.high,
        timeLimit: const Duration(seconds: 12),
        allowBackgroundLocationUpdates: true,
      );
    }
    return const LocationSettings(
      accuracy: LocationAccuracy.high,
      timeLimit: Duration(seconds: 12),
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
    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      return permission;
    }

    // Android 11+: second prompt may offer «Allow all the time» for background GPS.
    if (permission == LocationPermission.whileInUse) {
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

  Future<Map<String, dynamic>?> captureForAttendance() async {
    final permission = await requestLocationPermission();
    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      return null;
    }

    final position = await Geolocator.getCurrentPosition(
      locationSettings: _captureSettings(),
    );

    return _positionPayload(position);
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
