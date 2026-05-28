import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';

import '../firebase_bootstrap.dart';

/// Shows in-app feedback when FCM messages arrive in the foreground.
class PushForegroundListener {
  static void attach(GlobalKey<ScaffoldMessengerState> messengerKey) {
    if (!FirebaseBootstrap.isReady) return;

    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      final title = message.notification?.title ?? message.data['title'] ?? 'BauPass';
      final body = message.notification?.body ?? message.data['body'] ?? '';
      final text = body.isNotEmpty ? '$title: $body' : title;
      messengerKey.currentState?.showSnackBar(
        SnackBar(
          content: Text(text.length > 120 ? '${text.substring(0, 118)}…' : text),
          duration: const Duration(seconds: 4),
        ),
      );
    });
  }
}
