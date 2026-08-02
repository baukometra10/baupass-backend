import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../core/app_strings.dart';
import '../core/tenant_branding.dart';
import '../services/digital_card_repository.dart';
import 'safe_qr_code.dart';
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

  /// ISO/IEC 7810 ID-1 (CR80): 85.6 × 54 mm → width/height ≈ 1.585.
  static const double id1WidthMm = 85.6;
  static const double id1HeightMm = 54.0;
  static const double _cardAspect = id1WidthMm / id1HeightMm;

  @override
  Widget build(BuildContext context) {
    try {
      return _buildCard(context);
    } catch (e) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Text('Ausweis konnte nicht angezeigt werden.\n$e'),
        ),
      );
    }
  }

  Widget _buildCard(BuildContext context) {
    final tenant = branding ?? TenantBrandingScope.of(context);
    final brandLabel = tenant.displayName.isNotEmpty ? tenant.displayName : companyName;
    final name = '$firstName $lastName'.trim();
    final qrValue = dynamicQr?.qrToken ?? badgeId;
    final remaining = dynamicQr?.remainingSec ?? 0;
    final palette = _WalletPalette.fromBranding(tenant.accentColor ?? tenant.effectiveSeed);
    final active = _isActiveStatus(status);

    return LayoutBuilder(
      builder: (context, constraints) {
        final maxW = constraints.maxWidth.isFinite ? constraints.maxWidth : 430.0;
        if (maxW < 48) {
          return const SizedBox(height: 48, child: Center(child: CircularProgressIndicator(strokeWidth: 2)));
        }
        // ID-1 proportions — nearly full width for a balanced phone pass.
        final cardW = math.min(maxW * 0.98, 520.0).clamp(220.0, 520.0);
        final cardH = cardW / _cardAspect;

        return Center(
          child: SizedBox(
            width: cardW,
            height: cardH,
            child: _WalletCardShell(
              palette: palette,
              child: Padding(
                padding: EdgeInsets.fromLTRB(cardW * 0.04, cardH * 0.055, cardW * 0.04, cardH * 0.05),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _TopRow(brandLabel: brandLabel, tenant: tenant, palette: palette, cardW: cardW),
                    SizedBox(height: cardH * 0.02),
                    Expanded(
                      child: _MiddleRow(
                        qrValue: qrValue,
                        remaining: remaining,
                        photoData: photoData,
                        palette: palette,
                        cardW: cardW,
                        cardH: cardH,
                        onQrTap: () => _showFullscreenQr(context, qrValue, remaining),
                      ),
                    ),
                    SizedBox(height: cardH * 0.015),
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
      barrierColor: Colors.black.withValues(alpha: 0.88),
      builder: (ctx) {
        final side = MediaQuery.sizeOf(ctx).shortestSide * 0.82;
        return Dialog(
          backgroundColor: Colors.white,
          insetPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 28),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
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
                  child: SafeQrCode(
                    data: qrValue,
                    padding: const EdgeInsets.all(8),
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

  /// Badge-style Latin uppercase; keep Arabic/Unicode names readable.
  static String _displayName(String raw) {
    final name = raw.trim();
    if (name.isEmpty) return '—';
    final hasArabic = RegExp(r'[\u0600-\u06FF]').hasMatch(name);
    if (hasArabic) return name;
    return name.toUpperCase();
  }

  static String _displayMeta(String raw) {
    final text = raw.trim();
    if (text.isEmpty) return '';
    final hasArabic = RegExp(r'[\u0600-\u06FF]').hasMatch(text);
    if (hasArabic) return text;
    return text.toUpperCase();
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
    final primaryDark = _shade(primary, -0.35);
    final primaryLight = _shade(primary, 0.40);
    return _WalletPalette(
      backgroundStart: Color.lerp(primaryDark, Colors.black, 0.55) ?? primaryDark,
      backgroundMid: Color.lerp(primary, Colors.black, 0.35) ?? primary,
      backgroundEnd: Color.lerp(primaryDark, Colors.black, 0.6) ?? primaryDark,
      stripeStart: primary,
      stripeMid: primaryLight,
      stripeEnd: primary,
      markStart: primaryDark,
      markEnd: primary,
      qrFrameColors: [primaryDark, primary, primaryLight, primary, primaryDark],
      badgeGold: Color.lerp(primaryLight, const Color(0xFFFFE9A6), 0.55) ?? primaryLight,
      borderGlow: Color.lerp(primary, Colors.white, 0.25) ?? primary,
    );
  }

  static Color _shade(Color color, double amount) {
    // Use classic channel math — avoids Color.r/withValues edge crashes on some devices.
    // ignore: deprecated_member_use
    final r = ((color.red / 255.0) + amount).clamp(0.0, 1.0);
    // ignore: deprecated_member_use
    final g = ((color.green / 255.0) + amount).clamp(0.0, 1.0);
    // ignore: deprecated_member_use
    final b = ((color.blue / 255.0) + amount).clamp(0.0, 1.0);
    // ignore: deprecated_member_use
    return Color.fromRGBO(
      (r * 255).round(),
      (g * 255).round(),
      (b * 255).round(),
      color.opacity,
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
                      DigitalPassCard._displayMeta(brandLabel),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 0.4,
                        fontSize: (cardW * 0.046).clamp(13.0, 17.0),
                        height: 1.1,
                      ),
                    ),
                    Text(
                      t('cardEmployee', 'MITARBEITERAUSWEIS'),
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.55),
                        fontSize: (cardW * 0.03).clamp(9.5, 11.5),
                        letterSpacing: 0.8,
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
    required this.cardH,
    this.onQrTap,
  });

  final String qrValue;
  final int remaining;
  final String? photoData;
  final _WalletPalette palette;
  final double cardW;
  final double cardH;
  final VoidCallback? onQrTap;

  @override
  Widget build(BuildContext context) {
    // Photo dominant left, compact QR right — balanced ID-1 layout.
    final qrSize = (cardW * 0.26).clamp(72.0, 108.0);
    final photoH = (cardH * 0.46).clamp(96.0, 140.0);
    final photoW = photoH * 0.76;

    return Row(
      textDirection: Directionality.of(context),
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        _PhotoTile(width: photoW, height: photoH, photoData: photoData),
        SizedBox(width: cardW * 0.035),
        Expanded(
          child: Align(
            alignment: AlignmentDirectional.centerEnd,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Material(
                  color: Colors.transparent,
                  child: InkWell(
                    onTap: onQrTap,
                    borderRadius: BorderRadius.circular(12),
                    child: SizedBox(
                      width: qrSize,
                      height: qrSize,
                      child: Stack(
                        clipBehavior: Clip.none,
                        children: [
                          Positioned.fill(
                            child: DecoratedBox(
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(12),
                                color: palette.stripeMid.withValues(alpha: 0.35),
                                border: Border.all(color: Colors.white.withValues(alpha: 0.5), width: 1.5),
                              ),
                              child: Padding(
                                padding: const EdgeInsets.all(4),
                                child: DecoratedBox(
                                  decoration: BoxDecoration(
                                    color: Colors.white,
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: Padding(
                                    padding: const EdgeInsets.all(3),
                                    child: SafeQrCode(data: qrValue),
                                  ),
                                ),
                              ),
                            ),
                          ),
                          if (remaining > 0)
                            Positioned(
                              right: -4,
                              top: -4,
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
                                decoration: BoxDecoration(
                                  color: palette.stripeStart,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Text(
                                  '${remaining}s',
                                  style: const TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.w700),
                                ),
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  'QR',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.55),
                    fontSize: 9,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.2,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _PhotoTile extends StatelessWidget {
  const _PhotoTile({
    required this.width,
    required this.height,
    required this.photoData,
  });

  final double width;
  final double height;
  final String? photoData;

  @override
  Widget build(BuildContext context) {
    Widget image;
    if (photoData == null || photoData!.isEmpty) {
      image = ColoredBox(
        color: Colors.white.withValues(alpha: 0.06),
        child: Center(
          child: Icon(Icons.person, color: Colors.white.withValues(alpha: 0.5), size: height * 0.42),
        ),
      );
    } else {
      try {
        final bytes = base64Decode(photoData!.split(',').last);
        image = Image.memory(
          bytes,
          fit: BoxFit.cover,
          width: width,
          height: height,
          alignment: const Alignment(0, -0.15),
          filterQuality: FilterQuality.high,
          errorBuilder: (_, __, ___) => ColoredBox(
            color: Colors.white.withValues(alpha: 0.06),
            child: Icon(Icons.person, color: Colors.white.withValues(alpha: 0.5), size: height * 0.42),
          ),
        );
      } catch (_) {
        image = ColoredBox(
          color: Colors.white.withValues(alpha: 0.06),
          child: Icon(Icons.person, color: Colors.white.withValues(alpha: 0.5), size: height * 0.42),
        );
      }
    }
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withValues(alpha: 0.35), width: 2.2),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.4),
            blurRadius: 14,
            offset: const Offset(0, 6),
          ),
        ],
        color: Colors.black.withValues(alpha: 0.2),
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
    final rtl = Directionality.of(context) == TextDirection.rtl;
    final displayName = DigitalPassCard._displayName(
      name.isEmpty ? t('cardEmployeeName', 'Mitarbeiter') : name,
    );
    final arabicName = RegExp(r'[\u0600-\u06FF]').hasMatch(displayName);
    final longName = displayName.length > (arabicName ? 16 : 20);
    // Keep name secondary to photo/QR — closer to PWA .wc-name scale.
    final nameSize = (cardW * (arabicName ? (longName ? 0.032 : 0.038) : (longName ? 0.036 : 0.042)))
        .clamp(arabicName ? 11.0 : 12.0, arabicName ? 15.0 : 16.0);
    final roleSize = (cardW * 0.032).clamp(10.0, 12.5);
    final labelSize = (cardW * 0.025).clamp(8.5, 10.0);
    final valueSize = (cardW * 0.032).clamp(10.5, 12.5);
    final badgeSize = (cardW * 0.038).clamp(11.5, 14.0);
    final roleLine = DigitalPassCard._displayMeta(role.isEmpty ? (subcompany ?? '') : role);
    final statusLabel = active ? t('cardActive', 'AKTIV') : DigitalPassCard._displayMeta(status);
    final nameAlign = rtl ? TextAlign.right : TextAlign.left;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        FittedBox(
          fit: BoxFit.scaleDown,
          alignment: rtl ? Alignment.centerRight : Alignment.centerLeft,
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: cardW * 0.92),
            child: Text(
              displayName,
              maxLines: arabicName ? 2 : 1,
              overflow: TextOverflow.ellipsis,
              textAlign: nameAlign,
              textDirection: arabicName ? TextDirection.rtl : null,
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w800,
                letterSpacing: arabicName ? 0 : 0.4,
                fontSize: nameSize,
                height: arabicName ? 1.2 : 1.15,
              ),
            ),
          ),
        ),
        if (roleLine.isNotEmpty) ...[
          const SizedBox(height: 2),
          Text(
            roleLine,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: nameAlign,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.62),
              fontSize: roleSize,
              letterSpacing: arabicName ? 0 : 0.6,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
        SizedBox(height: cardW * 0.012),
        Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              flex: 6,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _FieldLabelValue(
                    label: t('cardBadgeId', 'BADGE-ID'),
                    value: badgeId.trim().isEmpty ? '—' : badgeId.trim(),
                    labelSize: labelSize,
                    valueSize: badgeSize,
                    valueColor: palette.badgeGold,
                    bold: true,
                    rtl: rtl,
                  ),
                  const SizedBox(height: 5),
                  _FieldLabelValue(
                    label: t('cardValidUntil', 'GÜLTIG BIS'),
                    value: DigitalPassCard._formatDate(validUntil),
                    labelSize: labelSize,
                    valueSize: valueSize,
                    valueColor: Colors.white.withValues(alpha: 0.95),
                    rtl: rtl,
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              flex: 5,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    DigitalPassCard._displayMeta(brandLabel),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.end,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.9),
                      fontSize: labelSize + 0.5,
                      fontWeight: FontWeight.w800,
                      letterSpacing: rtl ? 0 : 0.4,
                    ),
                  ),
                  if (subcompany != null &&
                      subcompany!.trim().isNotEmpty &&
                      role.trim().isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(
                      subcompany!.trim(),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      textAlign: TextAlign.end,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.5),
                        fontSize: labelSize,
                      ),
                    ),
                  ],
                  const SizedBox(height: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: (active ? const Color(0xFF4ADE80) : const Color(0xFFFF6B6B))
                          .withValues(alpha: 0.18),
                      borderRadius: BorderRadius.circular(999),
                      border: Border.all(
                        color: (active ? const Color(0xFF4ADE80) : const Color(0xFFFF6B6B))
                            .withValues(alpha: 0.65),
                      ),
                    ),
                    child: Text(
                      statusLabel,
                      style: TextStyle(
                        color: active ? const Color(0xFF86EFAC) : const Color(0xFFFFB3B3),
                        fontWeight: FontWeight.w800,
                        fontSize: labelSize,
                        letterSpacing: rtl ? 0 : 0.8,
                      ),
                    ),
                  ),
                ],
              ),
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
    this.rtl = false,
  });

  final String label;
  final String value;
  final double labelSize;
  final double valueSize;
  final Color valueColor;
  final bool bold;
  final bool rtl;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          textAlign: rtl ? TextAlign.right : TextAlign.left,
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.6),
            fontSize: labelSize,
            letterSpacing: rtl ? 0 : 1.4,
            fontWeight: FontWeight.w500,
            height: 1.05,
          ),
        ),
        Text(
          value.isEmpty ? '—' : value,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          textAlign: rtl ? TextAlign.right : TextAlign.left,
          style: TextStyle(
            color: valueColor,
            fontSize: valueSize,
            fontWeight: bold ? FontWeight.w800 : FontWeight.w600,
            letterSpacing: rtl ? 0 : (bold ? 0.9 : 0.4),
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
