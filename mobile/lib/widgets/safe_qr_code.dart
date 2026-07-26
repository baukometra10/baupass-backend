import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

/// QR that never throws into ErrorWidget (empty / invalid / zero-size safe).
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
              return Center(
                child: Icon(
                  Icons.qr_code_2,
                  color: foregroundColor.withValues(alpha: 0.45),
                  size: side > 0 ? side * 0.45 : 28,
                ),
              );
            }

            try {
              final validation = QrValidator.validate(
                data: raw,
                version: QrVersions.auto,
                errorCorrectionLevel: QrErrorCorrectLevel.M,
              );
              final code = validation.qrCode;
              if (validation.status != QrValidationStatus.valid || code == null) {
                return _fallback(side);
              }
              return CustomPaint(
                size: Size.square(side),
                painter: QrPainter.withQr(
                  qr: code,
                  gapless: true,
                  eyeStyle: QrEyeStyle(eyeShape: QrEyeShape.square, color: foregroundColor),
                  dataModuleStyle: QrDataModuleStyle(
                    dataModuleShape: QrDataModuleShape.square,
                    color: foregroundColor,
                  ),
                ),
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
        size: side * 0.45,
      ),
    );
  }
}
