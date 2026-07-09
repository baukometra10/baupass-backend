import '../core/api_client.dart';
import '../core/session_store.dart';

class AttendanceRepository {
  AttendanceRepository(this._api);

  final ApiClient _api;

  Future<Map<String, dynamic>> recordManualGpsAttendance({
    required WorkerSession session,
    required String direction,
    required Map<String, dynamic> location,
    String? clientEventId,
  }) {
    return _api.postJson(
      '/api/worker-app/attendance/manual',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: <String, dynamic>{
        'direction': direction,
        'location': location,
        if (clientEventId != null) 'clientEventId': clientEventId,
      },
    );
  }

  Future<Map<String, dynamic>> recordNfcAttendance({
    required WorkerSession session,
    required String nfcUid,
    String direction = 'auto',
    Map<String, dynamic>? location,
    String? clientEventId,
  }) {
    return _api.postJson(
      '/api/worker-app/attendance/nfc',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: <String, dynamic>{
        'nfcUid': nfcUid,
        'direction': direction,
        if (location != null) 'location': location,
        if (clientEventId != null) 'clientEventId': clientEventId,
      },
    );
  }

  Future<Map<String, dynamic>> syncOfflineEvents({
    required WorkerSession session,
    required List<Map<String, dynamic>> events,
  }) {
    return _api.postJson(
      '/api/worker-app/offline-events',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: <String, dynamic>{'events': events},
    );
  }
}
