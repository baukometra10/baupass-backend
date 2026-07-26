import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'app.dart';
import 'core/app_error_recovery.dart';
import 'core/locale_controller.dart';
import 'firebase_bootstrap.dart';
import 'services/push_background_handler.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  ErrorWidget.builder = (FlutterErrorDetails details) {
    final msg = details.exceptionAsString();
    AppErrorRecovery.lastError = msg;
    return Material(
      color: const Color(0xFFF8FAFC),
      child: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.error_outline, size: 40, color: Color(0xFFB91C1C)),
                const SizedBox(height: 12),
                const Text(
                  'Anzeige-Fehler',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Color(0xFF0F172A),
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  msg,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Color(0xFF334155), fontSize: 13),
                ),
                const SizedBox(height: 20),
                FilledButton(
                  onPressed: () {
                    // Schedule after the tap frame so the crushed tree can be replaced.
                    WidgetsBinding.instance.addPostFrameCallback((_) {
                      AppErrorRecovery.reset();
                    });
                  },
                  child: const Text('Zum Login zurück'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  };

  FlutterError.onError = (details) {
    FlutterError.presentError(details);
    AppErrorRecovery.lastError = details.exceptionAsString();
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
