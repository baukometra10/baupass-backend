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
  Map<String, dynamic>? _security;
  String? _cachedThreadId;

  String? _extractThreadId(Map<String, dynamic>? row) {
    if (row == null) return null;
    for (final key in ['id', 'threadId', 'thread_id', 'ID']) {
      final value = row[key]?.toString().trim() ?? '';
      if (value.isNotEmpty) return value;
    }
    return null;
  }

  String? _threadIdFromMe(Map<String, dynamic> me) {
    final chat = me['chat'];
    if (chat is Map) {
      final tid = (chat['threadId'] ?? chat['thread_id'])?.toString().trim() ?? '';
      if (tid.isNotEmpty) return tid;
    }
    return null;
  }

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

  Future<Map<String, dynamic>> _loadMe(WorkerSession session) async {
    final me = await _api.getJson(
      '/api/worker-app/me',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final worker = me['worker'];
    final workerId = worker is Map ? (worker['id'] as String? ?? '') : '';
    if (workerId.isNotEmpty) {
      _workerId = workerId;
    }
    final security = me['security'];
    if (security is Map) {
      _security = Map<String, dynamic>.from(security);
    }
    final threadId = _threadIdFromMe(me);
    if (threadId != null && threadId.isNotEmpty) {
      _cachedThreadId = threadId;
    }
    return me;
  }

  bool _e2eChatRequired() => _security?['e2eChatRequired'] == true;

  bool _e2eAttachmentsRequired() => _security?['e2eAttachmentsRequired'] == true;

  String _guessAttachmentMime(String filename) {
    final lower = filename.toLowerCase();
    if (lower.endsWith('.m4a') || lower.endsWith('.mp4')) return 'audio/mp4';
    if (lower.endsWith('.wav')) return 'audio/wav';
    if (lower.endsWith('.webm')) return 'audio/webm';
    if (lower.endsWith('.ogg')) return 'audio/ogg';
    if (lower.endsWith('.aac')) return 'audio/aac';
    if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg';
    if (lower.endsWith('.png')) return 'image/png';
    if (lower.endsWith('.pdf')) return 'application/pdf';
    return 'application/octet-stream';
  }

  Future<List<String>> _chatRecipientKeys(WorkerSession session) async {
    final data = await _api.getJson(
      '/api/e2e/identity/public-keys',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final rows = data['publicKeys'];
    if (rows is! List) return <String>[];
    final adminKeys = <String>[];
    for (final row in rows) {
      if (row is! Map) continue;
      final entityType = (row['entityType'] ?? row['entity_type'] ?? '').toString().toLowerCase();
      if (entityType != 'user') continue;
      final key = (row['publicKeySpkiB64'] ?? row['public_key_spki_b64'] ?? '').toString().trim();
      if (key.isNotEmpty) adminKeys.add(key);
    }
    if (adminKeys.isEmpty) return <String>[];
    final workerId = _workerId ?? '';
    if (workerId.isEmpty) return adminKeys;
    try {
      final identity = await _e2e.ensureLocalIdentity(entityType: 'worker', entityId: workerId);
      final selfKey = (identity['publicKeySpkiB64'] ?? '').toString().trim();
      if (selfKey.isNotEmpty) {
        return <String>[...adminKeys, selfKey];
      }
    } catch (_) {
      // Admin keys alone are enough to send.
    }
    return adminKeys;
  }

  Future<void> ensureE2eReady(WorkerSession session) async {
    await _loadMe(session);
    final workerId = _workerId ?? '';
    if (workerId.isEmpty) return;
    try {
      await bootstrapE2e(session, workerId: workerId);
    } catch (_) {
      // Identity upload is best-effort; chat may still work with plaintext fallback.
    }
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
    final threadId = _extractThreadId(data) ??
        data['threadId']?.toString().trim() ??
        data['thread_id']?.toString().trim() ??
        '';
    if (threadId.isEmpty) {
      throw StateError('chat_thread_missing');
    }
    _cachedThreadId = threadId;
    return threadId;
  }

  /// Resolve chat thread like PWA ensureWorkerChatThread (prefers /me chat.threadId).
  Future<String> resolveThread(WorkerSession session, {bool forceRefresh = false}) async {
    final cached = _cachedThreadId?.trim() ?? '';
    if (cached.isNotEmpty && !forceRefresh) return cached;

    await _loadMe(session);
    final fromMe = _cachedThreadId?.trim() ?? '';
    if (fromMe.isNotEmpty && !forceRefresh) return fromMe;

    try {
      final created = await ensureThread(session);
      if (created.isNotEmpty) return created;
    } catch (_) {
      // Fall back to listing existing threads.
    }

    final threads = await listThreads(session);
    if (threads.isNotEmpty) {
      final sorted = [...threads]
        ..sort((left, right) {
          final leftTs = (left['last_message_at'] ??
                  left['updated_at'] ??
                  left['lastMessageAt'] ??
                  '')
              .toString();
          final rightTs = (right['last_message_at'] ??
                  right['updated_at'] ??
                  right['lastMessageAt'] ??
                  '')
              .toString();
          return rightTs.compareTo(leftTs);
        });
      Map<String, dynamic>? selected;
      for (final row in sorted) {
        if ((row['subject'] ?? 'general').toString() == 'general') {
          selected = row;
          break;
        }
      }
      selected ??= sorted.first;
      final resolved = _extractThreadId(selected);
      if (resolved != null && resolved.isNotEmpty) {
        _cachedThreadId = resolved;
        return resolved;
      }
    }

    if (fromMe.isNotEmpty) return fromMe;
    if (cached.isNotEmpty) return cached;
    throw StateError('chat_thread_unavailable');
  }

  Future<List<Map<String, dynamic>>> listMessages(WorkerSession session, String threadId) async {
    await _loadMe(session);
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

  Future<({String outbound, bool e2eClientUnavailable})> _prepareOutboundBody(
    WorkerSession session,
    String body,
  ) async {
    final workerId = _workerId ?? '';
    if (workerId.isEmpty || !_e2eChatRequired() || _e2e.isE2eEnvelope(body)) {
      return (outbound: body, e2eClientUnavailable: false);
    }

    try {
      final keys = await _chatRecipientKeys(session);
      if (keys.isEmpty) {
        throw StateError('e2e_keys_missing');
      }
      final encrypted = await _e2e.encryptUtf8(body, keys);
      return (outbound: encrypted, e2eClientUnavailable: false);
    } on StateError catch (e) {
      if (e.message == 'e2e_keys_missing' || e.message == 'e2e_recipients_required') {
        rethrow;
      }
      return (outbound: body, e2eClientUnavailable: true);
    } catch (_) {
      return (outbound: body, e2eClientUnavailable: true);
    }
  }

  Future<Map<String, dynamic>> _postMessage({
    required WorkerSession session,
    required String threadId,
    required String outbound,
    required bool e2eClientUnavailable,
  }) {
    return _api.postJson(
      '/api/worker-app/chat/threads/$threadId/messages',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: <String, dynamic>{'body': outbound},
      extraHeaders: e2eClientUnavailable ? {'X-E2E-Client-Unavailable': '1'} : null,
    );
  }

  Future<Map<String, dynamic>> sendMessage({
    required WorkerSession session,
    required String threadId,
    required String body,
  }) async {
    await ensureE2eReady(session);
    final prepared = await _prepareOutboundBody(session, body);
    try {
      return await _postMessage(
        session: session,
        threadId: threadId,
        outbound: prepared.outbound,
        e2eClientUnavailable: prepared.e2eClientUnavailable,
      );
    } on ApiException catch (e) {
      if (e.errorCode == 'thread_not_found' || e.errorCode == 'chat_send_failed') {
        _cachedThreadId = null;
        final freshThreadId = await resolveThread(session, forceRefresh: true);
        return _postMessage(
          session: session,
          threadId: freshThreadId,
          outbound: prepared.outbound,
          e2eClientUnavailable: prepared.e2eClientUnavailable,
        );
      }
      rethrow;
    }
  }

  Future<Map<String, dynamic>> uploadAttachment({
    required WorkerSession session,
    required String threadId,
    required String messageId,
    required File file,
  }) async {
    await ensureE2eReady(session);
    final workerId = _workerId ?? '';
    if (_e2eAttachmentsRequired()) {
      final keys = await _chatRecipientKeys(session);
      if (keys.isEmpty) throw StateError('e2e_keys_missing');
      final bytes = await file.readAsBytes();
      final filename = file.path.split(Platform.pathSeparator).last;
      final packed = await _e2e.encryptBlob(
        Uint8List.fromList(bytes),
        keys,
        filename: filename,
        mime: _guessAttachmentMime(filename),
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
