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
      case 'leave-request-status':
        return const WorkerAppRoute(tabIndex: 2);
      case 'foreman-alert':
      case 'ops-notify':
        return const WorkerAppRoute(tabIndex: 3);
      default:
        return null;
    }
  }
}
