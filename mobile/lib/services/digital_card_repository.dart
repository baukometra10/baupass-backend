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
    int asInt(dynamic v, int fallback) {
      if (v is int) return v;
      if (v is num) return v.toInt();
      return int.tryParse('$v') ?? fallback;
    }

    return DynamicQrPayload(
      qrToken: (json['qrToken'] ?? json['qr_token'] ?? '').toString(),
      remainingSec: asInt(json['remainingSec'] ?? json['remaining_sec'], 60),
      windowSec: asInt(json['windowSec'] ?? json['window_sec'], 60),
      badgeId: (json['badgeId'] ?? json['badge_id'] ?? '').toString(),
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

  /// Issues or returns an Apple/Google Wallet pass URL.
  Future<Map<String, dynamic>> requestWalletPass({
    required String bearer,
    String? deviceId,
    required String platform,
    bool forceRegenerate = false,
  }) async {
    final normalized = platform.trim().toLowerCase();
    final force = forceRegenerate ? '&force_regenerate=1' : '';
    return _api.getJson(
      '/api/worker-app/wallet/pass?platform=$normalized$force',
      bearerToken: bearer,
      deviceId: deviceId,
    );
  }
}
