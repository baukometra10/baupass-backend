import 'package:firebase_messaging/firebase_messaging.dart';

import 'deep_link_service.dart';

/// Maps FCM data payloads to in-app routes.
class PushNavigation {
  static WorkerAppRoute? routeFromMessage(RemoteMessage message) {
    final data = message.data;
    final link = (data['route'] ?? data['deeplink'] ?? '').trim();
    if (link.isNotEmpty) {
      try {
        return DeepLinkService.appRouteFromUri(Uri.parse(link));
      } catch (_) {
        /* fall through */
      }
    }
    switch (data['tag']) {
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
        return const WorkerAppRoute(tabIndex: 2, tasksSubTab: 3);
      case 'site-checkin':
        return const WorkerAppRoute(tabIndex: 1);
      case 'ai-briefing':
        return const WorkerAppRoute(tabIndex: 0, openAi: true);
      case 'foreman-alert':
      case 'ops-notify':
        return const WorkerAppRoute(tabIndex: 3);
      default:
        return null;
    }
  }
}
