import 'dart:convert';
import 'dart:ui' show FontFeature;

import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../core/tenant_branding.dart';
import '../services/digital_card_repository.dart';
import 'tenant_brand_mark.dart';

class DigitalPassCard extends StatelessWidget {
  const DigitalPassCard({
    super.key,
    required this.firstName,
    required this.lastName,
    required this.role,
    required this.badgeId,
    required this.companyName,
    required this.validUntil,
    required this.status,
    this.photoData,
    this.dynamicQr,
    this.subcompany,
    this.branding,
  });

  final String firstName;
  final String lastName;
  final String role;
  final String badgeId;
  final String companyName;
  final String validUntil;
  final String status;
  final String? photoData;
  final DynamicQrPayload? dynamicQr;
  final String? subcompany;
  final TenantBranding? branding;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final tenant = branding ?? TenantBrandingScope.of(context);
    final brandLabel = tenant.displayName.isNotEmpty ? tenant.displayName : companyName;
    final name = '$firstName $lastName'.trim();
    final qrValue = dynamicQr?.qrToken ?? badgeId;
    final remaining = dynamicQr?.remainingSec ?? 0;
    final accent = tenant.accentColor ?? theme.colorScheme.primary;
    final gradientStart = Color.lerp(accent, Colors.black, 0.45) ?? accent;
    final gradientEnd = Color.lerp(accent, Colors.black, 0.72) ?? accent;
    final active = _isActiveStatus(status);

    return AspectRatio(
      aspectRatio: 1.62,
      child: Card(
        elevation: 6,
        margin: EdgeInsets.zero,
        clipBehavior: Clip.antiAlias,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(22)),
        child: Stack(
          fit: StackFit.expand,
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [gradientStart, gradientEnd],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
              ),
            ),
            CustomPaint(painter: _DotPatternPainter(color: Colors.white.withValues(alpha: 0.08))),
            Padding(
              padding: const EdgeInsets.fromLTRB(18, 16, 18, 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      TenantBrandMark(branding: tenant, size: 30, borderRadius: 8),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              brandLabel.toUpperCase(),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: theme.textTheme.titleSmall?.copyWith(
                                color: Colors.white,
                                letterSpacing: 1.1,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                            Text(
                              'MITARBEITERAUSWEIS',
                              style: theme.textTheme.labelSmall?.copyWith(
                                color: Colors.white.withValues(alpha: 0.72),
                                letterSpacing: 1.4,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      ),
                      Icon(Icons.nfc, color: Colors.white.withValues(alpha: 0.75), size: 22),
                      if (remaining > 0) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.16),
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: Text(
                            '${remaining}s',
                            style: const TextStyle(color: Colors.white, fontSize: 11),
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 14),
                  Expanded(
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.center,
                      children: [
                        Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(14),
                            boxShadow: [
                              BoxShadow(
                                color: accent.withValues(alpha: 0.35),
                                blurRadius: 18,
                                spreadRadius: 1,
                              ),
                            ],
                          ),
                          child: QrImageView(
                            data: qrValue,
                            size: 108,
                            backgroundColor: Colors.white,
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(child: _photoTile(accent)),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              name.isEmpty ? 'MITARBEITER' : name.toUpperCase(),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: theme.textTheme.titleLarge?.copyWith(
                                color: Colors.white,
                                fontWeight: FontWeight.w800,
                                letterSpacing: 0.4,
                                height: 1.05,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              role.isEmpty ? (subcompany ?? brandLabel) : role.toUpperCase(),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                color: Colors.white.withValues(alpha: 0.78),
                                fontWeight: FontWeight.w600,
                                letterSpacing: 0.8,
                              ),
                            ),
                            const SizedBox(height: 10),
                            Row(
                              children: [
                                Expanded(child: _field('BADGE-ID', badgeId, accent)),
                                const SizedBox(width: 12),
                                Expanded(child: _field('GÜLTIG BIS', _formatDate(validUntil), Colors.white)),
                              ],
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text(
                            brandLabel.toUpperCase(),
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.85),
                              fontWeight: FontWeight.w700,
                              fontSize: 11,
                              letterSpacing: 0.6,
                            ),
                          ),
                          const SizedBox(height: 6),
                          Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Container(
                                width: 8,
                                height: 8,
                                decoration: BoxDecoration(
                                  color: active ? const Color(0xFF4ADE80) : Colors.orangeAccent,
                                  shape: BoxShape.circle,
                                ),
                              ),
                              const SizedBox(width: 6),
                              Text(
                                active ? 'AKTIV' : status.toUpperCase(),
                                style: TextStyle(
                                  color: active ? const Color(0xFF4ADE80) : Colors.orangeAccent,
                                  fontWeight: FontWeight.w800,
                                  letterSpacing: 0.8,
                                  fontFeatures: const [FontFeature.tabularFigures()],
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  static bool _isActiveStatus(String value) {
    final s = value.trim().toLowerCase();
    return s.isEmpty || s == 'aktiv' || s == 'active' || s == 'ok';
  }

  static String _formatDate(String raw) {
    final text = raw.trim();
    if (text.length >= 10 && text[4] == '-' && text[7] == '-') {
      return '${text.substring(8, 10)}.${text.substring(5, 7)}.${text.substring(0, 4)}';
    }
    return text.isEmpty ? '—' : text;
  }

  Widget _photoTile(Color accent) {
    Widget image;
    if (photoData == null || photoData!.isEmpty) {
      image = Icon(Icons.person, color: accent.withValues(alpha: 0.55), size: 56);
    } else {
      try {
        final bytes = base64Decode(photoData!.split(',').last);
        image = Image.memory(bytes, fit: BoxFit.cover);
      } catch (_) {
        image = Icon(Icons.person, color: accent.withValues(alpha: 0.55), size: 56);
      }
    }
    return AspectRatio(
      aspectRatio: 1,
      child: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: Colors.white.withValues(alpha: 0.9), width: 2),
          boxShadow: [
            BoxShadow(
              color: accent.withValues(alpha: 0.25),
              blurRadius: 14,
            ),
          ],
        ),
        clipBehavior: Clip.antiAlias,
        child: image,
      ),
    );
  }

  Widget _field(String label, String value, Color valueColor) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.55),
            fontSize: 10,
            letterSpacing: 0.8,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          value.isEmpty ? '—' : value,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: valueColor,
            fontWeight: FontWeight.w800,
            fontSize: 13,
          ),
        ),
      ],
    );
  }
}

class _DotPatternPainter extends CustomPainter {
  _DotPatternPainter({required this.color});

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = color;
    const step = 14.0;
    for (var y = 0.0; y < size.height; y += step) {
      for (var x = 0.0; x < size.width; x += step) {
        canvas.drawCircle(Offset(x + (y / step).floor() % 2 == 0 ? 0 : step / 2, y), 1.1, paint);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _DotPatternPainter oldDelegate) => oldDelegate.color != color;
}
