import '../core/api_client.dart';

class UsageRepository {
  UsageRepository(this._api);

  final ApiClient _api;

  static const _tabFeatures = <int, String>{
    0: 'worker-badge',
    1: 'worker-attendance',
    2: 'worker-tasks',
    3: 'worker-chat',
    4: 'worker-profile',
  };

  Future<void> trackFeature({
    required String featureId,
    required String bearerToken,
    String? deviceId,
    String source = 'mobile',
  }) async {
    final fid = featureId.trim();
    if (fid.isEmpty) return;
    try {
      await _api.postJson(
        '/api/worker-app/usage/event',
        body: <String, dynamic>{
          'feature_id': fid,
          'source': source,
        },
        bearerToken: bearerToken,
        deviceId: deviceId,
      );
    } on Exception {
      // analytics must never break the app
    }
  }

  Future<void> trackTab({
    required int tabIndex,
    required String bearerToken,
    String? deviceId,
  }) {
    final featureId = _tabFeatures[tabIndex] ?? 'worker-tab-$tabIndex';
    return trackFeature(
      featureId: featureId,
      bearerToken: bearerToken,
      deviceId: deviceId,
      source: 'mobile',
    );
  }
}
