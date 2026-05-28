import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../core/api_client.dart';
import '../core/config.dart';
import '../core/session_store.dart';

class AiAssistantService {
  AiAssistantService(this._api);

  final ApiClient _api;

  Future<Map<String, dynamic>> status(WorkerSession session) async {
    return _api.getJson(
      '/api/worker-app/ai/status',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
  }

  Future<Map<String, dynamic>> ask(
    WorkerSession session, {
    required String question,
    String lang = 'de',
  }) async {
    return _api.postJson(
      '/api/worker-app/ai/ask',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: {'question': question, 'lang': lang},
    );
  }

  Future<Map<String, dynamic>> voice(
    WorkerSession session, {
    required String audioBase64,
    String mime = 'audio/m4a',
    String lang = 'de',
  }) async {
    return _api.postJson(
      '/api/worker-app/ai/voice',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: {'audio': audioBase64, 'mime': mime, 'lang': lang},
    );
  }

  /// Stream SSE tokens from worker AI (same event types as Command Center).
  Stream<Map<String, dynamic>> askStream(
    WorkerSession session, {
    required String question,
    String lang = 'de',
  }) async* {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}/api/worker-app/ai/ask/stream');
    final req = http.Request('POST', uri)
      ..headers.addAll({
        'Accept': 'text/event-stream',
        'Content-Type': 'application/json',
        if (session.bearer.isNotEmpty) 'Authorization': 'Bearer ${session.bearer}',
        if (session.deviceId != null && session.deviceId!.isNotEmpty)
          'X-Device-Id': session.deviceId!,
      })
      ..body = jsonEncode({'question': question, 'lang': lang});

    final client = http.Client();
    try {
      final res = await client.send(req);
      if (res.statusCode >= 400) {
        final body = await res.stream.bytesToString();
        yield {'type': 'error', 'hint': body};
        return;
      }
      var buf = '';
      await for (final chunk in res.stream.transform(utf8.decoder)) {
        buf += chunk;
        final parts = buf.split('\n\n');
        buf = parts.removeLast();
        for (final block in parts) {
          final line = block.split('\n').firstWhere(
                (l) => l.startsWith('data:'),
                orElse: () => '',
              );
          if (line.isEmpty) continue;
          try {
            yield jsonDecode(line.substring(5).trim()) as Map<String, dynamic>;
          } catch (_) {}
        }
      }
    } finally {
      client.close();
    }
  }
}
