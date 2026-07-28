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
    void Function(String callId, String fromName)? onCameraIntent,
    void Function(String roomId)? onConferenceInvite,
  }) {
    if (!FirebaseBootstrap.isReady) return;

    void openFromMessage(RemoteMessage message) {
      final tag = (message.data['tag'] ?? '').trim();
      final type = (message.data['type'] ?? '').trim();
      final callId = (message.data['callId'] ?? message.data['call_id'] ?? '').trim();
      final roomId = (message.data['roomId'] ?? message.data['room_id'] ?? '').trim();
      final fromName = (message.data['fromName'] ?? message.data['from_name'] ?? 'Arbeitgeber').toString();
      if (tag == 'voice-call' && callId.isNotEmpty && onVoiceCall != null) {
        onVoiceCall(callId);
      }
      if ((tag == 'voice-call-missed' || type == 'voice_call_missed') && onRoute != null) {
        final route = PushNavigation.routeFromMessage(message) ??
            WorkerAppRoute(
              tabIndex: 3,
              openChat: true,
              missedCallId: callId.isNotEmpty ? callId : null,
            );
        onRoute(route);
        return;
      }
      if (tag == 'voice-call-camera' && onCameraIntent != null) {
        onCameraIntent(callId, fromName);
      }
      if (tag == 'conference-invite' && roomId.isNotEmpty && onConferenceInvite != null) {
        onConferenceInvite(roomId);
      }
      final route = PushNavigation.routeFromMessage(message);
      if (route != null && onRoute != null) onRoute(route);
    }

    FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      final tag = (message.data['tag'] ?? '').trim();
      final callId = (message.data['callId'] ?? message.data['call_id'] ?? '').trim();
      final roomId = (message.data['roomId'] ?? message.data['room_id'] ?? '').trim();
      final fromName = (message.data['fromName'] ?? message.data['from_name'] ?? 'Arbeitgeber').toString();
      if (tag == 'voice-call' && callId.isNotEmpty && onVoiceCall != null) {
        onVoiceCall(callId);
        return;
      }
      final type = (message.data['type'] ?? '').trim();
      if (tag == 'voice-call-missed' || type == 'voice_call_missed') {
        final route = PushNavigation.routeFromMessage(message);
        final title = message.notification?.title ??
            message.data['title'] ??
            'Verpasster Anruf';
        final body = message.notification?.body ??
            message.data['body'] ??
            'Anruf vom Arbeitgeber — nicht erreicht.';
        messengerKey.currentState?.showSnackBar(
          SnackBar(
            content: Text('$title: $body'),
            duration: const Duration(seconds: 6),
            action: route != null && onRoute != null
                ? SnackBarAction(label: 'Chat', onPressed: () => onRoute(route))
                : null,
          ),
        );
        return;
      }
      if (tag == 'voice-call-camera') {
        if (onCameraIntent != null) onCameraIntent(callId, fromName);
        final title = message.notification?.title ??
            message.data['title'] ??
            'Kamera-Anfrage';
        final body = message.notification?.body ??
            message.data['body'] ??
            '$fromName möchte die Kamera öffnen.';
        messengerKey.currentState?.showSnackBar(
          SnackBar(
            content: Text('$title: $body'),
            duration: const Duration(seconds: 6),
          ),
        );
        return;
      }
      if (tag == 'conference-invite') {
        if (roomId.isNotEmpty && onConferenceInvite != null) {
          onConferenceInvite(roomId);
        }
        final route = PushNavigation.routeFromMessage(message);
        if (route != null && onRoute != null) onRoute(route);
        final title = message.notification?.title ??
            message.data['title'] ??
            BrandingStore.instance.value.displayName;
        final body = message.notification?.body ?? message.data['body'] ?? 'Konferenz-Einladung';
        messengerKey.currentState?.showSnackBar(
          SnackBar(
            content: Text('$title: $body'),
            duration: const Duration(seconds: 6),
            action: route != null && onRoute != null
                ? SnackBarAction(label: 'Öffnen', onPressed: () => onRoute(route))
                : null,
          ),
        );
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
