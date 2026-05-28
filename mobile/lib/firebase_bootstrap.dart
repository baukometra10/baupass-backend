import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

/// Initializes Firebase when google-services / GoogleService-Info are present.
class FirebaseBootstrap {
  static bool _ready = false;

  static bool get isReady => _ready;

  static Future<bool> initialize() async {
    try {
      await Firebase.initializeApp();
      _ready = true;
      return true;
    } catch (_) {
      _ready = false;
      return false;
    }
  }

  static Future<String?> deviceToken() async {
    if (!_ready) return null;
    try {
      await FirebaseMessaging.instance.requestPermission(
        alert: true,
        badge: true,
        sound: true,
      );
      return await FirebaseMessaging.instance.getToken();
    } catch (_) {
      return null;
    }
  }
}
