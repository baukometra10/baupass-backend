import '../core/api_client.dart';

class DynamicQrPayload {
  DynamicQrPayload({
    required this.qrToken,
    required this.remainingSec,
    required this.windowSec,
    required this.badgeId,
  });

  final String qrToken;
  final int remainingSec;
  final int windowSec;
  final String badgeId;

  factory DynamicQrPayload.fromJson(Map<String, dynamic> json) {
    return DynamicQrPayload(
      qrToken: json['qrToken'] as String? ?? '',
      remainingSec: json['remainingSec'] as int? ?? 60,
      windowSec: json['windowSec'] as int? ?? 60,
      badgeId: json['badgeId'] as String? ?? '',
    );
  }
}

class DigitalCardRepository {
  DigitalCardRepository(this._api);

  final ApiClient _api;

  Future<DynamicQrPayload> fetchDynamicQr({
    required String bearer,
    String? deviceId,
  }) async {
    final body = await _api.getJson(
      '/api/worker-app/dynamic-qr',
      bearerToken: bearer,
      deviceId: deviceId,
    );
    return DynamicQrPayload.fromJson(body);
  }
}
