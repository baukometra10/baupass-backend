import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';

import '../core/branding_store.dart';
import '../firebase_bootstrap.dart';
import 'deep_link_service.dart';
import 'push_navigation.dart';

/// Foreground snackbars + tap-to-open when user opens a push notification.
class PushForegroundListener {
  static void attach({
    required GlobalKey<ScaffoldMessengerState> messengerKey,
    void Function(WorkerAppRoute route)? onRoute,
    void Function(String callId)? onVoiceCall,
  }) {
    if (!FirebaseBootstrap.isReady) return;

    void openFromMessage(RemoteMessage message) {
      final tag = (message.data['tag'] ?? '').trim();
      final callId = (message.data['callId'] ?? message.data['call_id'] ?? '').trim();
      if (tag == 'voice-call' && callId.isNotEmpty && onVoiceCall != null) {
        onVoiceCall(callId);
      }
      final route = PushNavigation.routeFromMessage(message);
      if (route != null && onRoute != null) onRoute(route);
    }

    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      final tag = (message.data['tag'] ?? '').trim();
      final callId = (message.data['callId'] ?? message.data['call_id'] ?? '').trim();
      if (tag == 'voice-call' && callId.isNotEmpty && onVoiceCall != null) {
        onVoiceCall(callId);
        return;
      }
      final title = message.notification?.title ??
          message.data['title'] ??
          BrandingStore.instance.value.displayName;
      final body = message.notification?.body ?? message.data['body'] ?? '';
      final text = body.isNotEmpty ? '$title: $body' : title;
      final route = PushNavigation.routeFromMessage(message);
      messengerKey.currentState?.showSnackBar(
        SnackBar(
          content: Text(text.length > 120 ? '${text.substring(0, 118)}…' : text),
          duration: const Duration(seconds: 5),
          action: route != null && onRoute != null
              ? SnackBarAction(
                  label: 'Open',
                  onPressed: () => onRoute(route),
                )
              : null,
        ),
      );
    });

    FirebaseMessaging.onMessageOpenedApp.listen(openFromMessage);

    FirebaseMessaging.instance.getInitialMessage().then((message) {
      if (message != null) openFromMessage(message);
    });
  }
}
