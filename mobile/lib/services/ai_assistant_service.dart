import '../core/api_client.dart';
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
}
