import 'package:firebase_messaging/firebase_messaging.dart';

import 'deep_link_service.dart';

/// Maps FCM data payloads to in-app routes.
class PushNavigation {
  static WorkerAppRoute? routeFromMessage(RemoteMessage message) {
    return routeFromData(message.data);
  }

  /// Pure mapper for tests (no Firebase types required beyond Map).
  static WorkerAppRoute? routeFromData(Map<String, dynamic> raw) {
    final data = <String, String>{};
    raw.forEach((key, value) {
      data[key.toString()] = (value ?? '').toString();
    });
    final link = (data['route'] ?? data['deeplink'] ?? '').trim();
    if (link.isNotEmpty) {
      try {
        return DeepLinkService.appRouteFromUri(Uri.parse(link));
      } catch (_) {
        /* fall through */
      }
    }
    final tag = (data['tag'] ?? '').trim();
    final type = (data['type'] ?? '').trim();
    final callId = (data['callId'] ?? data['call_id'] ?? '').trim();
    final roomId = (data['roomId'] ?? data['room_id'] ?? '').trim();

    // Admin camera-watch pushes use url=/admin-v2/camera-watch.html?…
    // Worker app has no admin route — ignore those tags below.
    switch (tag) {
      case 'deployment-plan':
      case 'deployment_plan':
      case 'einsatzplan':
        return const WorkerAppRoute(tabIndex: 2, tasksSubTab: 0);
      case 'leave-request-status':
      case 'leave-approved':
      case 'leave-denied':
      case 'document-expiry':
        return const WorkerAppRoute(tabIndex: 2, tasksSubTab: 2);
      case 'attendance-reminder':
        return const WorkerAppRoute(tabIndex: 2, tasksSubTab: 4);
      case 'shift-swap':
      case 'shift_swap':
        return const WorkerAppRoute(tabIndex: 2, tasksSubTab: 4, shiftsInnerTab: 1);
      case 'site-checkin':
        return const WorkerAppRoute(tabIndex: 1);
      case 'ai-briefing':
        return const WorkerAppRoute(tabIndex: 0, openAi: true);
      case 'morning-brief':
      case 'worker-morning-brief':
        return const WorkerAppRoute(tabIndex: 0);
      case 'foreman-alert':
      case 'ops-notify':
        return const WorkerAppRoute(tabIndex: 4);
      case 'worker-chat':
        return const WorkerAppRoute(tabIndex: 3, openChat: true);
      case 'voice-call-missed':
        return WorkerAppRoute(
          tabIndex: 3,
          openChat: true,
          missedCallId: callId.isNotEmpty ? callId : null,
        );
      case 'voice-call':
      case 'voice-call-camera':
        return WorkerAppRoute(
          tabIndex: 3,
          openChat: true,
          incomingCallId: callId.isNotEmpty ? callId : null,
        );
      case 'conference-invite':
      case 'conference':
        return WorkerAppRoute(
          tabIndex: 3,
          openChat: true,
          conferenceRoomId: roomId.isNotEmpty ? roomId : null,
        );
      case 'contract-sign':
        final signUrl = (data['signUrl'] ?? data['sign_url'] ?? '').trim();
        if (signUrl.isNotEmpty) {
          return WorkerAppRoute(tabIndex: 0, externalUrl: signUrl);
        }
        return const WorkerAppRoute(tabIndex: 0);
      default:
        break;
    }

    // Backend may send type without matching tag.
    if (type == 'voice_call_missed') {
      return WorkerAppRoute(
        tabIndex: 3,
        openChat: true,
        missedCallId: callId.isNotEmpty ? callId : null,
      );
    }
    return null;
  }
}
