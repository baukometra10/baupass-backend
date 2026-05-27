import '../core/api_client.dart';

class AttendanceRepository {
  AttendanceRepository(this._api);

  final ApiClient _api;

  Future<Map<String, dynamic>> recordNfcAttendance({
    required String sessionToken,
    required String nfcUid,
    String direction = 'auto',
    Map<String, dynamic>? location,
    String? clientEventId,
  }) {
    return _api.postJson(
      '/api/worker-app/attendance/nfc',
      bearerToken: sessionToken,
      body: <String, dynamic>{
        'nfcUid': nfcUid,
        'direction': direction,
        if (location != null) 'location': location,
        if (clientEventId != null) 'clientEventId': clientEventId,
      },
    );
  }

  Future<Map<String, dynamic>> syncOfflineEvents({
    required String sessionToken,
    required List<Map<String, dynamic>> events,
  }) {
    return _api.postJson(
      '/api/worker-app/offline-events',
      bearerToken: sessionToken,
      body: <String, dynamic>{'events': events},
    );
  }
}
