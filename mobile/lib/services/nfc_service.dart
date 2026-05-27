import 'package:flutter/services.dart';

import '../core/config.dart';

class NfcScanResult {
  NfcScanResult({required this.uid, this.platform});

  final String uid;
  final String? platform;
}

class NfcUnavailableException implements Exception {
  NfcUnavailableException(this.message);
  final String message;
  @override
  String toString() => message;
}

/// Platform channel bridge: Flutter → Native NFC → Flutter.
class NfcService {
  static const MethodChannel _channel = MethodChannel(AppConfig.nfcChannel);

  Future<bool> isAvailable() async {
    try {
      final result = await _channel.invokeMethod<bool>('isAvailable');
      return result == true;
    } on PlatformException {
      return false;
    }
  }

  /// Opens native NFC reader UI and returns normalized tag UID (hex, uppercase).
  Future<NfcScanResult> scanTag({Duration timeout = const Duration(seconds: 30)}) async {
    try {
      final dynamic raw = await _channel.invokeMethod<dynamic>(
        'scanTag',
        <String, dynamic>{'timeoutMs': timeout.inMilliseconds},
      );
      if (raw is! Map) {
        throw NfcUnavailableException('Invalid NFC response from native layer.');
      }
      final uid = (raw['uid'] as String?)?.trim() ?? '';
      if (uid.isEmpty) {
        throw NfcUnavailableException('NFC scan returned an empty UID.');
      }
      return NfcScanResult(
        uid: uid,
        platform: raw['platform'] as String?,
      );
    } on PlatformException catch (e) {
      if (e.code == 'nfc_unavailable') {
        throw NfcUnavailableException(e.message ?? 'NFC is not available on this device.');
      }
      if (e.code == 'scan_cancelled') {
        throw NfcUnavailableException('NFC scan was cancelled.');
      }
      rethrow;
    }
  }
}
