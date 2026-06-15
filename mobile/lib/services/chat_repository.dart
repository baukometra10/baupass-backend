import 'dart:io';
import 'dart:typed_data';

import '../core/api_client.dart';
import '../core/session_store.dart';

class ChatRepository {
  ChatRepository(this._api);

  final ApiClient _api;

  Future<List<Map<String, dynamic>>> listThreads(WorkerSession session) async {
    final data = await _api.getJson(
      '/api/worker-app/chat/threads',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final raw = data['threads'];
    if (raw is! List) return [];
    return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<String> ensureThread(WorkerSession session, {String subject = 'general'}) async {
    final data = await _api.postJson(
      '/api/worker-app/chat/threads',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: <String, dynamic>{'subject': subject},
    );
    return data['threadId'] as String;
  }

  Future<List<Map<String, dynamic>>> listMessages(WorkerSession session, String threadId) async {
    final data = await _api.getJson(
      '/api/worker-app/chat/threads/$threadId/messages',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final raw = data['messages'];
    if (raw is! List) return [];
    return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<Map<String, dynamic>> sendMessage({
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

  Future<Map<String, dynamic>> uploadAttachment({
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

  Future<Uint8List> downloadAttachment({
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
