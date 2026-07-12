/// Runtime API configuration (override via --dart-define).
class AppConfig {
  AppConfig._();

  static const String apiBaseUrl = String.fromEnvironment(
    'SUPPIX_API_URL',
    defaultValue: String.fromEnvironment(
      'BAUPASS_API_URL',
      defaultValue: 'https://suppix-workpass-ai.up.railway.app',
    ),
  );

  static const String nfcChannel = 'com.baupass.worker/nfc';
}
