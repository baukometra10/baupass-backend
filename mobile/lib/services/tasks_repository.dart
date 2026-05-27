import '../core/api_client.dart';

class TasksRepository {
  TasksRepository(this._api);

  final ApiClient _api;

  Future<List<Map<String, dynamic>>> listLeaveRequests(String sessionToken) {
    return _api.getJsonList('/api/worker-app/leave-requests', bearerToken: sessionToken);
  }

  Future<Map<String, dynamic>> submitLeaveRequest({
    required String sessionToken,
    required String type,
    required String startDate,
    required String endDate,
    String note = '',
    String? recipientEmail,
  }) {
    return _api.postJson(
      '/api/worker-app/leave-requests',
      bearerToken: sessionToken,
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

  Future<List<Map<String, dynamic>>> listDocuments(String sessionToken) {
    return _api.getJsonList('/api/worker-app/my-documents', bearerToken: sessionToken);
  }

  Future<List<Map<String, dynamic>>> listCompanyAdmins(String sessionToken) {
    return _api.getJsonList('/api/worker-app/company-admins', bearerToken: sessionToken);
  }
}
