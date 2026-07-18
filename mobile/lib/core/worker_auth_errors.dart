import 'api_client.dart';

const workerSessionAuthErrors = {
  'invalid_worker_session',
  'worker_session_expired',
  'worker_not_available',
  'missing_device_id',
  'device_not_bound',
  'device_not_active',
  'unauthorized',
};

bool isWorkerSessionAuthError(String? errorCode) {
  if (errorCode == null || errorCode.isEmpty) return false;
  return workerSessionAuthErrors.contains(errorCode);
}

String formatWorkerAuthError(ApiException error) {
  final code = error.errorCode ?? '';
  if (error.message != null && error.message!.trim().isNotEmpty) {
    return error.message!.trim();
  }
  switch (code) {
    case 'network_error':
      return 'Keine Verbindung zum Server — Internet prüfen.';
    case 'rate_limited':
      final retry = error.payload?['retryAfterSeconds'];
      final seconds = retry is num ? retry.toInt() : int.tryParse('$retry') ?? 0;
      if (seconds > 0) {
        return 'Zu viele Anmeldeversuche — bitte in $seconds Sekunden erneut versuchen.';
      }
      return 'Zu viele Anmeldeversuche — kurz warten und erneut versuchen.';
    case 'access_token_already_used':
      return 'Einmal-Link bereits verwendet — bitte Badge-ID und PIN eingeben.';
    case 'invalid_access_token':
    case 'access_token_expired':
      return 'Aktivierungslink ungültig — Admin soll neuen QR erzeugen.';
    case 'invalid_badge_id':
      return 'Badge-ID nicht gefunden.';
    case 'invalid_badge_pin':
      return 'PIN falsch.';
    case 'missing_device_id':
      return 'Gerät nicht registriert — bitte erneut anmelden.';
    case 'device_not_bound':
      return 'Dieses Gerät ist nicht freigegeben — bitte erneut anmelden.';
    case 'device_binding_failed':
      return 'Geräteregistrierung fehlgeschlagen — App neu starten und erneut anmelden.';
    default:
      return error.toString();
  }
}

String? badgeIdFromAuthError(ApiException error) {
  final badge = error.payload?['badgeId'] ?? error.payload?['badge_id'];
  final text = badge?.toString().trim() ?? '';
  return text.isNotEmpty ? text : null;
}
