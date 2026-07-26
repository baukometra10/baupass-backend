import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'app.dart';
import 'core/locale_controller.dart';
import 'firebase_bootstrap.dart';
import 'services/push_background_handler.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Release builds otherwise show a blank white screen on widget errors.
  ErrorWidget.builder = (FlutterErrorDetails details) {
    final msg = details.exceptionAsString();
    return Material(
      color: const Color(0xFFF8FAFC),
      child: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(
              kDebugMode ? msg : 'Anzeige-Fehler — bitte App neu starten.\n$msg',
              textAlign: TextAlign.center,
              style: const TextStyle(color: Color(0xFF0F172A), fontSize: 14),
            ),
          ),
        ),
      ),
    );
  };

  try {
    await LocaleController.instance.load();
  } catch (_) {
    /* keep default language */
  }
  await FirebaseBootstrap.initialize();
  FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
  runApp(const WorkerApp());
}
