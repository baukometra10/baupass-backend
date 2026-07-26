import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:qr/qr.dart';

/// Minimal QR painter — no qr_flutter QrImageView/QrPainter (those null-crashed in release).
class SafeQrCode extends StatelessWidget {
  const SafeQrCode({
    super.key,
    required this.data,
    this.padding = EdgeInsets.zero,
    this.backgroundColor = Colors.white,
    this.foregroundColor = const Color(0xFF111827),
  });

  final String data;
  final EdgeInsets padding;
  final Color backgroundColor;
  final Color foregroundColor;

  @override
  Widget build(BuildContext context) {
    final raw = data.trim();
    return ColoredBox(
      color: backgroundColor,
      child: Padding(
        padding: padding,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final side = math.min(
              constraints.maxWidth.isFinite ? constraints.maxWidth : 0.0,
              constraints.maxHeight.isFinite ? constraints.maxHeight : 0.0,
            );
            if (raw.isEmpty || side < 16) {
              return _fallback(side);
            }
            try {
              final qrCode = QrCode.fromData(
                data: raw,
                errorCorrectLevel: QrErrorCorrectLevel.M,
              );
              final qrImage = QrImage(qrCode);
              if (qrImage.moduleCount <= 0) return _fallback(side);
              return CustomPaint(
                size: Size.square(side),
                painter: _QrModulePainter(qrImage, foregroundColor),
              );
            } catch (_) {
              return _fallback(side);
            }
          },
        ),
      ),
    );
  }

  Widget _fallback(double side) {
    return Center(
      child: Icon(
        Icons.qr_code_2,
        color: foregroundColor.withValues(alpha: 0.45),
        size: side > 0 ? side * 0.45 : 28,
      ),
    );
  }
}

class _QrModulePainter extends CustomPainter {
  _QrModulePainter(this.image, this.color);

  final QrImage image;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final count = image.moduleCount;
    if (count <= 0 || size.shortestSide <= 0) return;
    final cell = size.shortestSide / count;
    final paint = Paint()..color = color..style = PaintingStyle.fill;
    for (var x = 0; x < count; x++) {
      for (var y = 0; y < count; y++) {
        if (image.isDark(y, x)) {
          canvas.drawRect(Rect.fromLTWH(x * cell, y * cell, cell + 0.5, cell + 0.5), paint);
        }
      }
    }
  }

  @override
  bool shouldRepaint(covariant _QrModulePainter oldDelegate) {
    return oldDelegate.image != image || oldDelegate.color != color;
  }
}
