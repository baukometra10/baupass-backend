import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_callkit_incoming/entities/android_params.dart';
import 'package:flutter_callkit_incoming/entities/call_kit_params.dart';
import 'package:flutter_callkit_incoming/entities/ios_params.dart';
import 'package:flutter_callkit_incoming/entities/notification_params.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';
import 'package:shared_preferences/shared_preferences.dart';

const String kPendingVoiceCallIdKey = 'suppix_pending_voice_call_id';
const String kPendingConferenceRoomIdKey = 'suppix_pending_conference_room_id';

/// Top-level FCM handler — runs even when the APK is killed/backgrounded.
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  try {
    await Firebase.initializeApp();
  } catch (_) {
    /* already initialized */
  }
  final data = message.data;
  final tag = (data['tag'] ?? '').toString().trim();
  final callId = (data['callId'] ?? data['call_id'] ?? '').toString().trim();
  final roomId = (data['roomId'] ?? data['room_id'] ?? '').toString().trim();
  final title = (message.notification?.title ?? data['title'] ?? 'SUPPIX').toString();
  final body = (message.notification?.body ?? data['body'] ?? '').toString();

  try {
    final prefs = await SharedPreferences.getInstance();
    if (tag == 'voice-call' && callId.isNotEmpty) {
      await prefs.setString(kPendingVoiceCallIdKey, callId);
      await _showBackgroundIncomingCall(
        callId: callId,
        callerName: title.isNotEmpty ? title : 'Arbeitgeber',
        handle: body.isNotEmpty ? body : 'Eingehender Anruf',
      );
    } else if (tag == 'conference-invite' && roomId.isNotEmpty) {
      await prefs.setString(kPendingConferenceRoomIdKey, roomId);
    }
  } catch (error) {
    debugPrint('[fcm-bg] handler failed: $error');
  }
}

Future<void> _showBackgroundIncomingCall({
  required String callId,
  required String callerName,
  required String handle,
}) async {
  final params = CallKitParams(
    id: callId,
    nameCaller: callerName,
    appName: 'SUPPIX',
    handle: handle,
    type: 0,
    duration: 60000,
    textAccept: 'Annehmen',
    textDecline: 'Ablehnen',
    missedCallNotification: const NotificationParams(
      showNotification: true,
      isShowCallback: false,
      subtitle: 'Verpasster Anruf',
      callbackText: 'Zurückrufen',
    ),
    extra: <String, dynamic>{'callId': callId},
    android: const AndroidParams(
      isCustomNotification: false,
      isShowLogo: false,
      ringtonePath: 'system_ringtone_default',
      backgroundColor: '#0b141a',
      actionColor: '#00a884',
      textColor: '#ffffff',
      incomingCallNotificationChannelName: 'Eingehende Anrufe',
      missedCallNotificationChannelName: 'Verpasste Anrufe',
      isShowFullLockedScreen: true,
    ),
    ios: const IOSParams(
      handleType: 'generic',
      supportsVideo: false,
      maximumCallGroups: 1,
      maximumCallsPerCallGroup: 1,
      supportsDTMF: false,
      supportsHolding: false,
      supportsGrouping: false,
      supportsUngrouping: false,
      ringtonePath: 'system_ringtone_default',
    ),
  );
  try {
    await FlutterCallkitIncoming.showCallkitIncoming(params);
  } catch (error) {
    debugPrint('[fcm-bg] CallKit failed: $error');
  }
}

Future<String?> takePendingVoiceCallId() async {
  final prefs = await SharedPreferences.getInstance();
  final id = (prefs.getString(kPendingVoiceCallIdKey) ?? '').trim();
  if (id.isEmpty) return null;
  await prefs.remove(kPendingVoiceCallIdKey);
  return id;
}

Future<String?> takePendingConferenceRoomId() async {
  final prefs = await SharedPreferences.getInstance();
  final id = (prefs.getString(kPendingConferenceRoomIdKey) ?? '').trim();
  if (id.isEmpty) return null;
  await prefs.remove(kPendingConferenceRoomIdKey);
  return id;
}
