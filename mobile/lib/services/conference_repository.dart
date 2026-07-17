import '../core/api_client.dart';
import '../core/session_store.dart';

/// LiveKit-backed company conference (join token from backend).
class ConferenceRepository {
  ConferenceRepository(this._api);

  final ApiClient _api;

  Future<Map<String, dynamic>?> incoming(WorkerSession session) async {
    final data = await _api.getJson(
      '/api/worker-app/chat/conferences/incoming',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final conf = data['conference'];
    if (conf is Map<String, dynamic>) return conf;
    if (conf is Map) return Map<String, dynamic>.from(conf);
    return null;
  }

  Future<Map<String, dynamic>> join(WorkerSession session, String roomId) async {
    return _api.postJson(
      '/api/worker-app/chat/conferences/$roomId/join',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: const <String, dynamic>{},
    );
  }

  Future<void> leave(WorkerSession session, String roomId) async {
    await _api.postJson(
      '/api/worker-app/chat/conferences/$roomId/leave',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: const <String, dynamic>{},
    );
  }

  Future<void> postNote(WorkerSession session, String roomId, String body) async {
    await _api.postJson(
      '/api/worker-app/chat/conferences/$roomId/notes',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
      body: {'body': body},
    );
  }

  Future<List<Map<String, dynamic>>> callHistory(WorkerSession session, {int limit = 40}) async {
    final data = await _api.getJson(
      '/api/worker-app/chat/calls/history?limit=$limit',
      bearerToken: session.bearer,
      deviceId: session.deviceId,
    );
    final calls = data['calls'];
    if (calls is! List) return [];
    return calls.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }
}
