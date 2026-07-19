import 'dart:convert';
import 'dart:math' as math;
import 'dart:ui' show FontFeature;

import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../core/tenant_branding.dart';
import '../services/digital_card_repository.dart';
import 'tenant_brand_mark.dart';

/// Wallet pass card — mirrors PWA `.wallet-card` layout (emp-app / worker.css).
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

  /// Mobile-friendly card proportions (taller than ISO wallet CR80).
  static const _cardAspect = 0.72;

  @override
  Widget build(BuildContext context) {
    final tenant = branding ?? TenantBrandingScope.of(context);
    final brandLabel = tenant.displayName.isNotEmpty ? tenant.displayName : companyName;
    final name = '$firstName $lastName'.trim();
    final qrValue = dynamicQr?.qrToken ?? badgeId;
    final remaining = dynamicQr?.remainingSec ?? 0;
    final palette = _WalletPalette.fromBranding(tenant.accentColor);
    final active = _isActiveStatus(status);

    return LayoutBuilder(
      builder: (context, constraints) {
        final maxW = constraints.maxWidth.isFinite ? constraints.maxWidth : 430.0;
        final cardW = math.min(maxW, 380.0);
        final cardH = cardW / _cardAspect;

        return Center(
          child: SizedBox(
            width: cardW,
            height: cardH,
            child: _WalletCardShell(
              palette: palette,
              child: Padding(
                padding: EdgeInsets.fromLTRB(cardW * 0.062, cardW * 0.052, cardW * 0.062, cardW * 0.048),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _TopRow(brandLabel: brandLabel, tenant: tenant, palette: palette, cardW: cardW),
                    SizedBox(height: cardH * 0.04),
                    Expanded(
                      child: _MiddleRow(
                        qrValue: qrValue,
                        remaining: remaining,
                        photoData: photoData,
                        palette: palette,
                        cardW: cardW,
                        onQrTap: () => _showFullscreenQr(context, qrValue, remaining),
                      ),
                    ),
                    SizedBox(height: cardH * 0.02),
                    _BottomSection(
                      name: name,
                      role: role,
                      badgeId: badgeId,
                      validUntil: validUntil,
                      brandLabel: brandLabel,
                      subcompany: subcompany,
                      status: status,
                      active: active,
                      palette: palette,
                      cardW: cardW,
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  static bool _isActiveStatus(String value) {
    final s = value.trim().toLowerCase();
    return s.isEmpty || s == 'aktiv' || s == 'active' || s == 'ok';
  }

  static void _showFullscreenQr(BuildContext context, String qrValue, int remaining) {
    showDialog<void>(
      context: context,
      builder: (ctx) {
        final side = MediaQuery.sizeOf(ctx).shortestSide * 0.78;
        return Dialog(
          backgroundColor: Colors.white,
          insetPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 24),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'Zugangscode',
                  style: Theme.of(ctx).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
                ),
                if (remaining > 0) ...[
                  const SizedBox(height: 4),
                  Text('Noch ${remaining}s gültig', style: Theme.of(ctx).textTheme.bodySmall),
                ],
                const SizedBox(height: 16),
                SizedBox(
                  width: side,
                  height: side,
                  child: QrImageView(
                    data: qrValue,
                    backgroundColor: Colors.white,
                    padding: EdgeInsets.zero,
                  ),
                ),
                const SizedBox(height: 8),
                TextButton(
                  onPressed: () => Navigator.of(ctx).pop(),
                  child: const Text('Schließen'),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  static String _formatDate(String raw) {
    final text = raw.trim();
    if (text.length >= 10 && text[4] == '-' && text[7] == '-') {
      return '${text.substring(8, 10)}.${text.substring(5, 7)}.${text.substring(0, 4)}';
    }
    return text.isEmpty ? '—' : text;
  }
}

class _WalletPalette {
  const _WalletPalette({
    required this.backgroundStart,
    required this.backgroundMid,
    required this.backgroundEnd,
    required this.stripeStart,
    required this.stripeMid,
    required this.stripeEnd,
    required this.markStart,
    required this.markEnd,
    required this.qrFrameColors,
    required this.badgeGold,
    required this.borderGlow,
  });

  final Color backgroundStart;
  final Color backgroundMid;
  final Color backgroundEnd;
  final Color stripeStart;
  final Color stripeMid;
  final Color stripeEnd;
  final Color markStart;
  final Color markEnd;
  final List<Color> qrFrameColors;
  final Color badgeGold;
  final Color borderGlow;

  factory _WalletPalette.fromBranding(Color? accent) {
    if (accent == null) {
      return const _WalletPalette(
        backgroundStart: Color(0xFF0F172A),
        backgroundMid: Color(0xFF1E293B),
        backgroundEnd: Color(0xFF0B1220),
        stripeStart: Color(0xFF06B6D4),
        stripeMid: Color(0xFF22D3EE),
        stripeEnd: Color(0xFF0891B2),
        markStart: Color(0xFF0E7490),
        markEnd: Color(0xFF22D3EE),
        qrFrameColors: [
          Color(0xFF164E63),
          Color(0xFF06B6D4),
          Color(0xFFA5F3FC),
          Color(0xFF22D3EE),
          Color(0xFF155E75),
        ],
        badgeGold: Color(0xFFE0F2FE),
        borderGlow: Color(0xFF67E8F9),
      );
    }
    final primary = accent;
    final primaryDark = _shade(primary, -35);
    final primaryLight = _shade(primary, 40);
    return _WalletPalette(
      backgroundStart: Color.lerp(primaryDark, Colors.black, 0.55)!,
      backgroundMid: Color.lerp(primary, Colors.black, 0.35)!,
      backgroundEnd: Color.lerp(primaryDark, Colors.black, 0.6)!,
      stripeStart: primary,
      stripeMid: primaryLight,
      stripeEnd: primary,
      markStart: primaryDark,
      markEnd: primary,
      qrFrameColors: [primaryDark, primary, primaryLight, primary, primaryDark],
      badgeGold: Color.lerp(primaryLight, const Color(0xFFFFE9A6), 0.55)!,
      borderGlow: Color.lerp(primary, Colors.white, 0.25)!,
    );
  }

  static Color _shade(Color color, int amount) {
    return Color.fromARGB(
      color.alpha,
      (color.red + amount).clamp(0, 255),
      (color.green + amount).clamp(0, 255),
      (color.blue + amount).clamp(0, 255),
    );
  }
}

class _WalletCardShell extends StatelessWidget {
  const _WalletCardShell({required this.palette, required this.child});

  final _WalletPalette palette;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(32),
        gradient: LinearGradient(
          colors: [palette.backgroundStart, palette.backgroundMid, palette.backgroundEnd],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        boxShadow: [
          BoxShadow(
            color: palette.backgroundMid.withValues(alpha: 0.44),
            blurRadius: 52,
            offset: const Offset(0, 28),
          ),
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.38),
            blurRadius: 21,
            offset: const Offset(0, 14),
          ),
        ],
        border: Border.all(color: palette.borderGlow.withValues(alpha: 0.26)),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(32),
        child: Stack(
          fit: StackFit.expand,
          children: [
            Positioned(
              left: 0,
              right: 0,
              top: 0,
              height: 5,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [palette.stripeStart, palette.stripeMid, palette.stripeEnd],
                  ),
                ),
              ),
            ),
            CustomPaint(painter: _DotGridPainter()),
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.white.withValues(alpha: 0.06),
                    Colors.transparent,
                    Colors.transparent,
                    Colors.black.withValues(alpha: 0.14),
                  ],
                  stops: const [0, 0.16, 0.84, 1],
                ),
              ),
            ),
            child,
          ],
        ),
      ),
    );
  }
}

class _TopRow extends StatelessWidget {
  const _TopRow({
    required this.brandLabel,
    required this.tenant,
    required this.palette,
    required this.cardW,
  });

  final String brandLabel;
  final TenantBranding tenant;
  final _WalletPalette palette;
  final double cardW;

  @override
  Widget build(BuildContext context) {
    final markSize = (cardW * 0.09).clamp(30.0, 38.0);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Row(
            children: [
              TenantBrandMark(
                branding: tenant,
                size: markSize,
                borderRadius: 10,
              ),
              SizedBox(width: cardW * 0.022),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      brandLabel.toUpperCase(),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 0.6,
                        fontSize: (cardW * 0.048).clamp(14.0, 18.0),
                        height: 1.1,
                      ),
                    ),
                    Text(
                      'MITARBEITERAUSWEIS',
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.55),
                        fontSize: (cardW * 0.032).clamp(10.0, 12.0),
                        letterSpacing: 1.0,
                        fontWeight: FontWeight.w600,
                        height: 1.15,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        Opacity(
          opacity: 0.75,
          child: CustomPaint(
            size: Size((cardW * 0.06).clamp(22.0, 26.0), (cardW * 0.06).clamp(22.0, 26.0)),
            painter: _NfcIconPainter(),
          ),
        ),
      ],
    );
  }
}

class _MiddleRow extends StatelessWidget {
  const _MiddleRow({
    required this.qrValue,
    required this.remaining,
    required this.photoData,
    required this.palette,
    required this.cardW,
    this.onQrTap,
  });

  final String qrValue;
  final int remaining;
  final String? photoData;
  final _WalletPalette palette;
  final double cardW;
  final VoidCallback? onQrTap;

  @override
  Widget build(BuildContext context) {
    final qrSize = (cardW * 0.52).clamp(140.0, 200.0);
    final photoSize = (cardW * 0.24).clamp(72.0, 100.0);

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            GestureDetector(
              onTap: onQrTap,
              child: SizedBox(
                width: qrSize,
                height: qrSize,
                child: Stack(
                  clipBehavior: Clip.none,
                  children: [
                    Positioned.fill(
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(18),
                          gradient: LinearGradient(
                            colors: palette.qrFrameColors,
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                          ),
                          border: Border.all(color: Colors.white.withValues(alpha: 0.42)),
                          boxShadow: [
                            BoxShadow(
                              color: palette.qrFrameColors[1].withValues(alpha: 0.38),
                              blurRadius: 14,
                              offset: const Offset(0, 8),
                            ),
                          ],
                        ),
                        child: Padding(
                          padding: const EdgeInsets.all(7),
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Padding(
                              padding: const EdgeInsets.all(5),
                              child: QrImageView(
                                data: qrValue,
                                backgroundColor: Colors.white,
                                padding: EdgeInsets.zero,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                    if (remaining > 0)
                      Positioned(
                        right: -6,
                        top: -6,
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
                          decoration: BoxDecoration(
                            color: Colors.black.withValues(alpha: 0.55),
                            borderRadius: BorderRadius.circular(999),
                            border: Border.all(color: Colors.white.withValues(alpha: 0.35)),
                          ),
                          child: Text(
                            '${remaining}s',
                            style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w600),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 6),
            Text(
              'Zum Vergrößern tippen',
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.55),
                fontSize: 10,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
        _PhotoTile(size: photoSize, photoData: photoData),
      ],
    );
  }
}

class _PhotoTile extends StatelessWidget {
  const _PhotoTile({required this.size, required this.photoData});

  final double size;
  final String? photoData;

  @override
  Widget build(BuildContext context) {
    Widget image;
    if (photoData == null || photoData!.isEmpty) {
      image = Icon(Icons.person, color: Colors.white.withValues(alpha: 0.45), size: size * 0.45);
    } else {
      try {
        final bytes = base64Decode(photoData!.split(',').last);
        image = Image.memory(bytes, fit: BoxFit.cover, width: size, height: size);
      } catch (_) {
        image = Icon(Icons.person, color: Colors.white.withValues(alpha: 0.45), size: size * 0.45);
      }
    }
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: Colors.white.withValues(alpha: 0.22), width: 2),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.34),
            blurRadius: 15,
            offset: const Offset(0, 8),
          ),
        ],
        color: Colors.black.withValues(alpha: 0.15),
      ),
      clipBehavior: Clip.antiAlias,
      child: image,
    );
  }
}

class _BottomSection extends StatelessWidget {
  const _BottomSection({
    required this.name,
    required this.role,
    required this.badgeId,
    required this.validUntil,
    required this.brandLabel,
    required this.subcompany,
    required this.status,
    required this.active,
    required this.palette,
    required this.cardW,
  });

  final String name;
  final String role;
  final String badgeId;
  final String validUntil;
  final String brandLabel;
  final String? subcompany;
  final String status;
  final bool active;
  final _WalletPalette palette;
  final double cardW;

  @override
  Widget build(BuildContext context) {
    final longName = name.length > 22;
    final nameSize = (cardW * (longName ? 0.052 : 0.058)).clamp(16.0, 22.0);
    final roleSize = (cardW * 0.036).clamp(11.0, 14.0);
    final labelSize = (cardW * 0.028).clamp(9.0, 11.0);
    final valueSize = (cardW * 0.034).clamp(11.0, 13.5);
    final badgeSize = (cardW * 0.042).clamp(12.0, 15.0);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          name.isEmpty ? 'MITARBEITER' : name.toUpperCase(),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.0,
            fontSize: nameSize,
            height: 1.1,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          (role.isEmpty ? (subcompany ?? '') : role).toUpperCase(),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.55),
            fontSize: roleSize,
            letterSpacing: 1.2,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 4),
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _FieldLabelValue(
                    label: 'BADGE-ID',
                    value: badgeId,
                    labelSize: labelSize,
                    valueSize: badgeSize,
                    valueColor: palette.badgeGold,
                    bold: true,
                  ),
                  const SizedBox(height: 4),
                  _FieldLabelValue(
                    label: 'GÜLTIG BIS',
                    value: DigitalPassCard._formatDate(validUntil),
                    labelSize: labelSize,
                    valueSize: valueSize,
                    valueColor: Colors.white.withValues(alpha: 0.98),
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  brandLabel.toUpperCase(),
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.85),
                    fontSize: labelSize,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.6,
                  ),
                ),
                if (subcompany != null && subcompany!.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(
                    subcompany!,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.5),
                      fontSize: labelSize - 0.5,
                    ),
                  ),
                ],
                const SizedBox(height: 4),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 6,
                      height: 6,
                      decoration: BoxDecoration(
                        color: active ? const Color(0xFF4ADE80) : const Color(0xFFFF6B6B),
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: (active ? const Color(0xFF4ADE80) : const Color(0xFFFF6B6B))
                                .withValues(alpha: 0.7),
                            blurRadius: 7,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 5),
                    Text(
                      active ? 'AKTIV' : status.toUpperCase(),
                      style: TextStyle(
                        color: active ? const Color(0xFF4ADE80) : const Color(0xFFFFB3B3),
                        fontWeight: FontWeight.w700,
                        fontSize: labelSize,
                        letterSpacing: 1.0,
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
    );
  }
}

class _FieldLabelValue extends StatelessWidget {
  const _FieldLabelValue({
    required this.label,
    required this.value,
    required this.labelSize,
    required this.valueSize,
    required this.valueColor,
    this.bold = false,
  });

  final String label;
  final String value;
  final double labelSize;
  final double valueSize;
  final Color valueColor;
  final bool bold;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.6),
            fontSize: labelSize,
            letterSpacing: 1.4,
            fontWeight: FontWeight.w500,
            height: 1.05,
          ),
        ),
        Text(
          value.isEmpty ? '—' : value,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: valueColor,
            fontSize: valueSize,
            fontWeight: bold ? FontWeight.w800 : FontWeight.w600,
            letterSpacing: bold ? 0.9 : 0.4,
            height: 1.1,
          ),
        ),
      ],
    );
  }
}

class _DotGridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = Colors.white.withValues(alpha: 0.035);
    const step = 18.0;
    for (var y = 0.0; y < size.height; y += step) {
      for (var x = 0.0; x < size.width; x += step) {
        canvas.drawCircle(Offset(x, y), 1, paint);
      }
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _NfcIconPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 2.2;
    final cx = size.width / 2;
    final cy = size.height / 2;
    paint.color = Colors.white.withValues(alpha: 0.75);
    canvas.drawArc(Rect.fromCircle(center: Offset(cx, cy), radius: size.width * 0.35), -2.4, 2.4, false, paint);
    paint.color = Colors.white.withValues(alpha: 0.55);
    canvas.drawArc(Rect.fromCircle(center: Offset(cx, cy), radius: size.width * 0.22), -2.2, 2.2, false, paint);
    paint.color = Colors.white.withValues(alpha: 0.4);
    canvas.drawArc(Rect.fromCircle(center: Offset(cx, cy), radius: size.width * 0.1), -1.8, 1.8, false, paint);
    canvas.drawCircle(Offset(cx, cy), 1.2, Paint()..color = Colors.white.withValues(alpha: 0.6));
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
