import 'dart:async';

import '../core/api_client.dart';
import 'location_service.dart';

/// Polls site presence for `site_app` companies (PWA parity).
class GeofenceService {
  GeofenceService(this._api, this._location);

  final ApiClient _api;
  final LocationService _location;
  Timer? _timer;
  bool _running = false;

  static const pollInterval = Duration(seconds: 20);

  void start({
    required String bearer,
    String? deviceId,
    required bool siteAppMode,
    required bool autoLogout,
    void Function(Map<String, dynamic> result)? onPresence,
    void Function()? onAutoLogout,
  }) {
    stop();
    if (!siteAppMode) return;
    _running = true;
    _timer = Timer.periodic(pollInterval, (_) async {
      if (!_running) return;
      try {
        final location = await _location.captureForAttendance();
        if (location == null) return;
        final result = await _api.postJson(
          '/api/worker-app/site-presence',
          bearerToken: bearer,
          deviceId: deviceId,
          body: <String, dynamic>{'location': location},
        );
        onPresence?.call(result);
        if (autoLogout && result['autoLogout'] == true) {
          onAutoLogout?.call();
        }
      } on ApiException catch (e) {
        if (e.errorCode == 'outside_geofence' && autoLogout) {
          try {
            await _api.postJson(
              '/api/worker-app/site-leave',
              bearerToken: bearer,
              deviceId: deviceId,
              body: <String, dynamic>{},
            );
            onAutoLogout?.call();
          } catch (_) {}
        }
      } catch (_) {}
    });
  }

  void stop() {
    _running = false;
    _timer?.cancel();
    _timer = null;
  }
}
