import 'dart:async';

import 'package:app_links/app_links.dart';

/// Handles `baupass://join?access=...` and https join URLs.
class DeepLinkService {
  DeepLinkService() : _appLinks = AppLinks();

  final AppLinks _appLinks;
  StreamSubscription<Uri>? _subscription;

  /// App routes: baupass://app/ai | attendance | tasks | profile
  static WorkerAppRoute? appRouteFromUri(Uri? uri) {
    if (uri == null) return null;
    if (uri.scheme != 'baupass' || uri.host != 'app') return null;
    final seg = uri.pathSegments.isNotEmpty ? uri.pathSegments.first : uri.path.replaceFirst('/', '');
    switch (seg) {
      case 'ai':
        return const WorkerAppRoute(tabIndex: 0, openAi: true);
      case 'attendance':
      case 'nfc':
        return const WorkerAppRoute(tabIndex: 1);
      case 'tasks':
      case 'leave':
        return const WorkerAppRoute(tabIndex: 2, tasksSubTab: 1);
      case 'deployment':
      case 'deployment-plan':
      case 'einsatzplan':
        return const WorkerAppRoute(tabIndex: 2, tasksSubTab: 0);
      case 'documents':
        return const WorkerAppRoute(tabIndex: 2, tasksSubTab: 2);
      case 'shifts':
      case 'shift':
        final tab = (uri.queryParameters['tab'] ?? '').toLowerCase();
        return WorkerAppRoute(
          tabIndex: 2,
          tasksSubTab: 4,
          shiftsInnerTab: (tab == 'swap' || tab == 'tausch') ? 1 : 0,
        );
      case 'chat':
      case 'messages':
        return const WorkerAppRoute(tabIndex: 3);
      case 'voice-call':
        return WorkerAppRoute(
          tabIndex: 3,
          openChat: true,
          incomingCallId: uri.queryParameters['callId'] ?? uri.queryParameters['call_id'],
        );
      case 'conference':
      case 'conference-invite':
        return WorkerAppRoute(
          tabIndex: 3,
          openChat: true,
          conferenceRoomId: uri.queryParameters['roomId'] ?? uri.queryParameters['room_id'],
        );
      case 'contract-sign':
        return WorkerAppRoute(tabIndex: 0, externalUrl: uri.queryParameters['url']);
      case 'profile':
        return const WorkerAppRoute(tabIndex: 4);
      default:
        return const WorkerAppRoute(tabIndex: 0);
    }
  }

  static String? accessTokenFromUri(Uri? uri) {
    if (uri == null) return null;
    final access = _firstNonEmpty([
      uri.queryParameters['access'],
      uri.queryParameters['accessToken'],
      uri.queryParameters['token'],
    ]);
    if (access.isEmpty) return null;

    final host = uri.host.toLowerCase();
    final path = uri.path.toLowerCase();
    if (uri.scheme == 'baupass' && host == 'join') {
      return access;
    }
    if (path == '/join.html' || path.endsWith('/join.html')) {
      return access;
    }
    return null;
  }

  static String _firstNonEmpty(List<String?> values) {
    for (final value in values) {
      final text = (value ?? '').trim();
      if (text.isNotEmpty) return text;
    }
    return '';
  }

  Future<Uri?> getInitialUri() async {
    try {
      return await _appLinks.getInitialLink();
    } catch (_) {
      return null;
    }
  }

  void listen(void Function(Uri uri) onUri) {
    _subscription?.cancel();
    _subscription = _appLinks.uriLinkStream.listen(
      onUri,
      onError: (_) {},
    );
  }

  void dispose() {
    _subscription?.cancel();
    _subscription = null;
  }
}

class WorkerAppRoute {
  const WorkerAppRoute({
    required this.tabIndex,
    this.openAi = false,
    this.openChat = false,
    this.tasksSubTab = 0,
    this.shiftsInnerTab = 0,
    this.externalUrl,
    this.incomingCallId,
    this.conferenceRoomId,
  });

  final int tabIndex;
  final bool openAi;
  final bool openChat;
  final int tasksSubTab;
  /// 0 = Meine Schichten, 1 = Tausch
  final int shiftsInnerTab;
  final String? externalUrl;
  final String? incomingCallId;
  final String? conferenceRoomId;
}
