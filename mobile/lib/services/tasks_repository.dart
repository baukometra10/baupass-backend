import '../core/api_client.dart';
import '../core/session_store.dart';

class TasksRepository {
  TasksRepository(this._api);

  final ApiClient _api;

  Future<List<Map<String, dynamic>>> listLeaveRequests(WorkerSession session) {
    return _api.getJsonList(
      '/api/worker-app/leave-requests',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
  }

  Future<Map<String, dynamic>> submitLeaveRequest({
    required WorkerSession session,
    required String type,
    required String startDate,
    required String endDate,
    String note = '',
    String? recipientEmail,
  }) {
    return _api.postJson(
      '/api/worker-app/leave-requests',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: <String, dynamic>{
        'type': type,
        'start_date': startDate,
        'end_date': endDate,
        'note': note,
        if (recipientEmail != null && recipientEmail.isNotEmpty)
          'recipient_email': recipientEmail,
      },
    );
  }

  Future<List<Map<String, dynamic>>> listDocuments(WorkerSession session) {
    return _api.getJsonList(
      '/api/worker-app/my-documents',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
  }

  Future<List<Map<String, dynamic>>> listShiftAssignments(WorkerSession session) async {
    final data = await _api.getJson(
      '/api/shift/assignments',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final raw = data['assignments'];
    if (raw is! List) return [];
    return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<List<Map<String, dynamic>>> listCompanyAdmins(WorkerSession session) {
    return _api.getJsonList(
      '/api/worker-app/company-admins',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
  }
}
