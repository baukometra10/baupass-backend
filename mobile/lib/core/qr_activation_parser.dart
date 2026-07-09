/// Parses worker activation QR payloads locally (no network).
class QrActivationPayload {
  const QrActivationPayload({
    this.accessToken,
    this.badgeId,
    this.qrLaunch = false,
  });

  final String? accessToken;
  final String? badgeId;
  final bool qrLaunch;

  bool get hasAccessToken => (accessToken ?? '').trim().isNotEmpty;
  bool get hasBadgeId => (badgeId ?? '').trim().isNotEmpty;
}

class QrActivationParser {
  static QrActivationPayload? parse(String raw) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty) return null;

    final uri = Uri.tryParse(trimmed);
    if (uri != null && uri.hasScheme) {
      final access = _first([
        uri.queryParameters['access'],
        uri.queryParameters['accessToken'],
        uri.queryParameters['token'],
      ]);
      final badge = _normalizeBadge(uri.queryParameters['badge']);
      final launch = uri.queryParameters['launch'] == '1' ||
          uri.queryParameters['fast'] == '1' ||
          access.isNotEmpty;
      if (access.isNotEmpty || badge.isNotEmpty) {
        return QrActivationPayload(
          accessToken: access.isNotEmpty ? access : null,
          badgeId: badge.isNotEmpty ? badge : null,
          qrLaunch: launch,
        );
      }
      if ((uri.scheme == 'baupass' && uri.host == 'join') ||
          uri.path.toLowerCase().endsWith('/join.html')) {
        return null;
      }
    }

    if (_looksLikeAccessToken(trimmed)) {
      return QrActivationPayload(accessToken: trimmed, qrLaunch: true);
    }

    final badgeOnly = _normalizeBadge(trimmed);
    if (badgeOnly.isNotEmpty && badgeOnly.contains('-')) {
      return QrActivationPayload(badgeId: badgeOnly, qrLaunch: true);
    }

    return null;
  }

  static String _first(List<String?> values) {
    for (final value in values) {
      final text = (value ?? '').trim();
      if (text.isNotEmpty) return text;
    }
    return '';
  }

  static String _normalizeBadge(String? raw) {
    return (raw ?? '').trim().toUpperCase();
  }

  static bool _looksLikeAccessToken(String value) {
    if (value.contains(' ') || value.length < 12) return false;
    if (value.startsWith('http://') || value.startsWith('https://')) return false;
    return RegExp(r'^[A-Za-z0-9._\-]+$').hasMatch(value);
  }
}
