/// Runtime API configuration (override via --dart-define).
class AppConfig {
  AppConfig._();

  static const String apiBaseUrl = String.fromEnvironment(
    'BAUPASS_API_URL',
    defaultValue: 'http://10.0.2.2:5000',
  );

  static const String nfcChannel = 'com.baupass.worker/nfc';
}
