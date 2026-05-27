import 'package:geolocator/geolocator.dart';

/// Captures GPS for site-based geofence attendance (site_app mode).
class LocationService {
  Future<Map<String, dynamic>?> captureForAttendance() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      return null;
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      return null;
    }

    final position = await Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.high,
        timeLimit: Duration(seconds: 12),
      ),
    );

    return <String, dynamic>{
      'latitude': position.latitude,
      'longitude': position.longitude,
      'accuracyMeters': position.accuracy,
      'capturedAt': DateTime.now().toUtc().toIso8601String(),
    };
  }
}
