import 'dart:io';
import 'dart:typed_data';

import 'package:open_file/open_file.dart';
import 'package:path_provider/path_provider.dart';

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

  Future<List<Map<String, dynamic>>> listEmploymentContracts(WorkerSession session) async {
    final data = await _api.getJson(
      '/api/worker-app/employment-contracts',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final rows = data['contracts'];
    if (rows is! List) return <Map<String, dynamic>>[];
    return rows.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
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

  Future<Map<String, List<Map<String, dynamic>>>> listShiftSwapBuckets(WorkerSession session) async {
    final data = await _api.getJson(
      '/api/shift/swaps',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    List<Map<String, dynamic>> asList(dynamic raw) {
      if (raw is! List) return [];
      return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    }

    final pending = asList(data['pending'] ?? data['swaps']);
    final sent = asList(data['sent']);
    final history = asList(data['history']);
    return {
      'pending': pending,
      'sent': sent,
      'history': history,
    };
  }

  Future<List<Map<String, dynamic>>> listShiftSwaps(WorkerSession session) async {
    final buckets = await listShiftSwapBuckets(session);
    return buckets['pending'] ?? [];
  }

  Future<List<Map<String, dynamic>>> listShiftCoworkers(WorkerSession session) async {
    final data = await _api.getJson(
      '/api/shift/coworkers',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final raw = data['coworkers'];
    if (raw is! List) return [];
    return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<List<Map<String, dynamic>>> listShiftCoworkerAssignments(
    WorkerSession session,
    String coworkerId,
  ) async {
    final data = await _api.getJson(
      '/api/shift/coworker-assignments?workerId=${Uri.encodeQueryComponent(coworkerId)}',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final raw = data['assignments'];
    if (raw is! List) return [];
    return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<Map<String, dynamic>> proposeShiftSwap({
    required WorkerSession session,
    required String assignmentId,
    required String toWorkerId,
    String reason = '',
    String? targetAssignmentId,
  }) {
    return _api.postJson(
      '/api/shift/propose-swap',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: <String, dynamic>{
        'assignmentId': assignmentId,
        'toWorkerId': toWorkerId,
        'reason': reason,
        if (targetAssignmentId != null && targetAssignmentId.isNotEmpty)
          'targetAssignmentId': targetAssignmentId,
      },
    );
  }

  Future<Map<String, dynamic>> respondShiftSwap({
    required WorkerSession session,
    required String swapId,
    required String response,
  }) {
    return _api.postJson(
      '/api/shift/respond-swap/$swapId',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: <String, dynamic>{'response': response},
    );
  }

  Future<List<Map<String, dynamic>>> listCompanyAdmins(WorkerSession session) {
    return _api.getJsonList(
      '/api/worker-app/company-admins',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
  }

  Future<Map<String, dynamic>> fetchDeploymentPlan({
    required WorkerSession session,
    required int year,
    required int month,
    String lang = 'de',
  }) {
    return _api.getJson(
      '/api/worker-app/deployment-plan?year=$year&month=$month&lang=$lang',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
  }

  Future<Uint8List> fetchDeploymentPlanPdf({
    required WorkerSession session,
    required int year,
    required int month,
    String lang = 'de',
  }) async {
    final uri = Uri.parse(
      '${_api.baseUrl}/api/worker-app/deployment-plan/pdf?year=$year&month=$month&lang=$lang',
    );
    final response = await _api.getBytes(
      uri.toString(),
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    return response;
  }

  Future<Map<String, dynamic>> postDeploymentDayResponse({
    required WorkerSession session,
    required String date,
    required String action,
    String reason = '',
  }) {
    return _api.postJson(
      '/api/worker-app/deployment-plan/day-response',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: <String, dynamic>{
        'date': date,
        'action': action,
        if (reason.isNotEmpty) 'reason': reason,
      },
    );
  }

  Future<List<Map<String, dynamic>>> listNotifications(WorkerSession session) async {
    final data = await _api.getJson(
      '/api/worker-app/notifications',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final raw = data['notifications'];
    if (raw is! List) return [];
    return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<void> markNotificationRead(WorkerSession session, String notifId) async {
    await _api.postJson(
      '/api/worker-app/notifications/$notifId/mark-read',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: <String, dynamic>{},
    );
  }

  Future<void> saveAndOpenPdf(Uint8List bytes, {required String filename}) async {
    final dir = await getTemporaryDirectory();
    final file = File('${dir.path}/$filename');
    await file.writeAsBytes(bytes, flush: true);
    await OpenFile.open(file.path);
  }

  Future<List<Map<String, dynamic>>> listChatThreads(WorkerSession session) async {
    final data = await _api.getJson(
      '/api/worker-app/chat/threads',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final raw = data['threads'];
    if (raw is! List) return [];
    return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<String> ensureChatThread(WorkerSession session, {String subject = 'general'}) async {
    final data = await _api.postJson(
      '/api/worker-app/chat/threads',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: <String, dynamic>{'subject': subject},
    );
    return data['threadId'] as String;
  }

  Future<List<Map<String, dynamic>>> listChatMessages(WorkerSession session, String threadId) async {
    final data = await _api.getJson(
      '/api/worker-app/chat/threads/$threadId/messages',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final raw = data['messages'];
    if (raw is! List) return [];
    return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<Map<String, dynamic>> sendChatMessage({
    required WorkerSession session,
    required String threadId,
    required String body,
  }) {
    return _api.postJson(
      '/api/worker-app/chat/threads/$threadId/messages',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: <String, dynamic>{'body': body},
    );
  }

  Future<Map<String, dynamic>> uploadChatAttachment({
    required WorkerSession session,
    required String threadId,
    required String messageId,
    required File file,
  }) {
    return _api.postMultipart(
      '/api/worker-app/chat/threads/$threadId/attachments',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      file: file,
      fileField: 'file',
      fields: <String, String>{'message_id': messageId},
    );
  }

  Future<Uint8List> downloadChatAttachment({
    required WorkerSession session,
    required String attachmentId,
  }) {
    return _api.getBytes(
      '/api/worker-app/chat/attachments/$attachmentId/download',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
  }
}
