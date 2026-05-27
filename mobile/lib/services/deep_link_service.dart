import 'dart:async';

import 'package:app_links/app_links.dart';

/// Handles `baupass://join?access=...` and https join URLs.
class DeepLinkService {
  DeepLinkService() : _appLinks = AppLinks();

  final AppLinks _appLinks;
  StreamSubscription<Uri>? _subscription;

  static String? accessTokenFromUri(Uri? uri) {
    if (uri == null) return null;
    final access = (uri.queryParameters['access'] ?? '').trim();
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
