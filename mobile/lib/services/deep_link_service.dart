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
        return const WorkerAppRoute(tabIndex: 2, tasksSubTab: 3);
      case 'chat':
      case 'messages':
        return const WorkerAppRoute(tabIndex: 3);
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
    this.externalUrl,
  });

  final int tabIndex;
  final bool openAi;
  final bool openChat;
  final int tasksSubTab;
  final String? externalUrl;
}
