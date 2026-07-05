import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import '../core/api_client.dart';
import '../core/session_store.dart';
import 'e2e_crypto_service.dart';

class ChatRepository {
  ChatRepository(this._api, {E2eCryptoService? e2e}) : _e2e = e2e ?? E2eCryptoService();

  final ApiClient _api;
  final E2eCryptoService _e2e;
  String? _workerId;

  Future<void> bootstrapE2e(WorkerSession session, {required String workerId}) async {
    _workerId = workerId;
    final identity = await _e2e.ensureLocalIdentity(entityType: 'worker', entityId: workerId);
    await _api.putJson(
      '/api/e2e/identity/me',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: {
        'publicKeySpkiB64': identity['publicKeySpkiB64'],
        'algorithm': 'X25519',
      },
    );
  }

  Future<List<String>> _publicKeys(WorkerSession session) async {
    final data = await _api.getJson(
      '/api/e2e/identity/public-keys',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final rows = data['publicKeys'];
    if (rows is! List) return <String>[];
    return rows
        .map((row) => (row as Map)['publicKeySpkiB64'] as String? ?? '')
        .where((value) => value.trim().isNotEmpty)
        .toList();
  }

  Future<void> ensureE2eReady(WorkerSession session) async {
    final me = await _api.getJson(
      '/api/worker-app/me',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final worker = me['worker'];
    final workerId = worker is Map ? (worker['id'] as String? ?? '') : '';
    if (workerId.isEmpty) return;
    await bootstrapE2e(session, workerId: workerId);
  }

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
    final workerId = _workerId ?? '';
    final out = <Map<String, dynamic>>[];
    for (final item in raw) {
      final msg = Map<String, dynamic>.from(item as Map);
      final body = msg['body']?.toString() ?? '';
      if (workerId.isNotEmpty && _e2e.isE2eEnvelope(body)) {
        msg['body'] = await _e2e.decryptUtf8(body, 'worker', workerId);
      }
      out.add(msg);
    }
    return out;
  }

  Future<Map<String, dynamic>> sendMessage({
    required WorkerSession session,
    required String threadId,
    required String body,
  }) async {
    final workerId = _workerId ?? '';
    var outbound = body;
    if (workerId.isNotEmpty && !_e2e.isE2eEnvelope(body)) {
      final keys = await _publicKeys(session);
      if (keys.isEmpty) throw StateError('e2e_keys_missing');
      outbound = await _e2e.encryptUtf8(body, keys);
    }
    return _api.postJson(
      '/api/worker-app/chat/threads/$threadId/messages',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: <String, dynamic>{'body': outbound},
    );
  }

  Future<Map<String, dynamic>> uploadAttachment({
    required WorkerSession session,
    required String threadId,
    required String messageId,
    required File file,
  }) async {
    final workerId = _workerId ?? '';
    final keys = workerId.isEmpty ? <String>[] : await _publicKeys(session);
    if (keys.isEmpty) throw StateError('e2e_keys_missing');
    final bytes = await file.readAsBytes();
    final packed = await _e2e.encryptBlob(
      Uint8List.fromList(bytes),
      keys,
      filename: file.path.split(Platform.pathSeparator).last,
      mime: 'application/octet-stream',
    );
    final tempDir = Directory.systemTemp;
    final tempFile = File('${tempDir.path}/suppix-${DateTime.now().millisecondsSinceEpoch}.e2e');
    await tempFile.writeAsBytes(packed['blob'] as Uint8List, flush: true);
    return _api.postMultipart(
      '/api/worker-app/chat/threads/$threadId/attachments',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      file: tempFile,
      fileField: 'file',
      fields: <String, String>{
        'message_id': messageId,
        'e2e_meta': packed['meta'] as String,
        'e2e_encrypted': '1',
      },
    );
  }

  Future<Uint8List> downloadAttachment({
    required WorkerSession session,
    required String attachmentId,
    String? e2eMeta,
    String? filename,
  }) async {
    final bytes = await _api.getBytes(
      '/api/worker-app/chat/attachments/$attachmentId/download',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final workerId = _workerId ?? '';
    final meta = e2eMeta ?? '';
    if (workerId.isNotEmpty && meta.isNotEmpty) {
      final clear = await _e2e.decryptBlob(bytes, meta, 'worker', workerId);
      return clear.bytes;
    }
    return bytes;
  }
}
