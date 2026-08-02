import 'package:flutter/material.dart';

/// Stable QR placeholder renderer that avoids the unstable QR package API.
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
    final side = 96.0;
    if (raw.isEmpty) {
      return _fallback(side);
    }
    return ColoredBox(
      color: backgroundColor,
      child: Padding(
        padding: padding,
        child: _fallback(side),
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
