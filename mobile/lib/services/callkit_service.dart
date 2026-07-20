import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_callkit_incoming/entities/android_params.dart';
import 'package:flutter_callkit_incoming/entities/call_event.dart';
import 'package:flutter_callkit_incoming/entities/call_kit_params.dart';
import 'package:flutter_callkit_incoming/entities/ios_params.dart';
import 'package:flutter_callkit_incoming/entities/notification_params.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';

import 'push_background_handler.dart';

typedef CallKitActionHandler = void Function(String callId);

/// Native incoming-call UI (CallKit iOS / full-screen Android).
class CallKitService {
  CallKitService();

  StreamSubscription<CallEvent?>? _eventSub;
  CallKitActionHandler? onAccept;
  CallKitActionHandler? onDecline;
  CallKitActionHandler? onEnded;
  bool _ready = false;

  Future<void> initialize({
    CallKitActionHandler? onAccept,
    CallKitActionHandler? onDecline,
    CallKitActionHandler? onEnded,
  }) async {
    if (_ready) {
      this.onAccept = onAccept ?? this.onAccept;
      this.onDecline = onDecline ?? this.onDecline;
      this.onEnded = onEnded ?? this.onEnded;
      return;
    }
    this.onAccept = onAccept;
    this.onDecline = onDecline;
    this.onEnded = onEnded;
    try {
      await FlutterCallkitIncoming.requestNotificationPermission({
        'title': 'Anrufbenachrichtigungen',
        'rationaleMessagePermission':
            'Benachrichtigungen sind nötig, um eingehende Anrufe anzuzeigen.',
        'postNotificationMessageRequired':
            'Bitte Anrufbenachrichtigungen in den Einstellungen erlauben.',
      });
      if (!kIsWeb) {
        try {
          final canFull = await FlutterCallkitIncoming.canUseFullScreenIntent();
          if (canFull == false) {
            await FlutterCallkitIncoming.requestFullIntentPermission();
          }
        } catch (_) {
          /* Android < 14 */
        }
      }
      _eventSub ??= FlutterCallkitIncoming.onEvent.listen(_handleEvent);
      _ready = true;
    } catch (error) {
      debugPrint('[callkit] init skipped: $error');
    }
  }

  void _handleEvent(CallEvent? raw) {
    if (raw == null) return;
    final event = raw.event;
    final callId = _extractCallId(raw.body);
    if (callId.isEmpty) return;
    switch (event) {
      case Event.actionCallAccept:
        if (onAccept != null) {
          onAccept!(callId);
        } else {
          unawaited(persistPendingCallKitAction('accept', callId));
        }
        break;
      case Event.actionCallDecline:
        if (onDecline != null) {
          onDecline!(callId);
        } else {
          unawaited(persistPendingCallKitAction('decline', callId));
        }
        break;
      case Event.actionCallEnded:
      case Event.actionCallTimeout:
        if (onEnded != null) {
          onEnded!(callId);
        } else {
          unawaited(persistPendingCallKitAction('decline', callId));
        }
        break;
      default:
        break;
    }
  }

  String _extractCallId(dynamic body) {
    if (body is Map) {
      final extra = body['extra'];
      if (extra is Map && extra['callId'] != null) {
        return extra['callId'].toString();
      }
      if (body['id'] != null) return body['id'].toString();
    }
    return '';
  }

  Future<void> showIncomingCall({
    required String callId,
    required String callerName,
    String? companyName,
  }) async {
    if (!_ready || callId.isEmpty) return;
    final label = callerName.trim().isNotEmpty ? callerName.trim() : 'Arbeitgeber';
    final params = CallKitParams(
      id: callId,
      nameCaller: label,
      appName: 'SUPPIX',
      handle: companyName?.trim().isNotEmpty == true ? companyName!.trim() : 'Sicherer Sprachkanal',
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
        // Standard system incoming UI — custom notifications often hide Accept/Decline.
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
      debugPrint('[callkit] show incoming failed: $error');
    }
  }

  Future<void> endCall(String callId) async {
    if (!_ready || callId.isEmpty) return;
    try {
      await FlutterCallkitIncoming.endCall(callId);
    } catch (_) {
      /* ignore */
    }
  }

  Future<void> dispose() async {
    await _eventSub?.cancel();
    _eventSub = null;
    _ready = false;
  }
}
