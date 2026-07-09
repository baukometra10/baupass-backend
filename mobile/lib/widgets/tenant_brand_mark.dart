import 'dart:convert';

import 'package:flutter/material.dart';

import '../core/tenant_branding.dart';

/// Compact logo chip: uploaded logo or derived initials.
class TenantBrandMark extends StatelessWidget {
  const TenantBrandMark({
    super.key,
    required this.branding,
    this.size = 32,
    this.borderRadius = 8,
  });

  final TenantBranding branding;
  final double size;
  final double borderRadius;

  @override
  Widget build(BuildContext context) {
    final accent = branding.accentColor ?? Theme.of(context).colorScheme.primary;
    final logo = branding.logoData?.trim() ?? '';
    if (logo.isEmpty && branding.displayName == 'SUPPIX') {
      return ClipRRect(
        borderRadius: BorderRadius.circular(borderRadius),
        child: Image.asset(
          'assets/branding/suppix-icon-192.png',
          width: size,
          height: size,
          fit: BoxFit.cover,
        ),
      );
    }
    if (logo.isNotEmpty) {
      final image = _logoImage(logo);
      if (image != null) {
        return ClipRRect(
          borderRadius: BorderRadius.circular(borderRadius),
          child: Image(image: image, width: size, height: size, fit: BoxFit.cover),
        );
      }
    }
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: accent,
        borderRadius: BorderRadius.circular(borderRadius),
      ),
      child: Text(
        branding.initials,
        style: TextStyle(
          color: branding.onAccentColor,
          fontWeight: FontWeight.w800,
          fontSize: size * (branding.initials.length > 1 ? 0.36 : 0.42),
          letterSpacing: 0.5,
        ),
      ),
    );
  }

  ImageProvider? _logoImage(String logo) {
    if (logo.startsWith('data:image')) {
      try {
        final payload = logo.split(',').last;
        final bytes = base64Decode(payload);
        return MemoryImage(bytes);
      } catch (_) {
        return null;
      }
    }
    if (logo.startsWith('http://') || logo.startsWith('https://')) {
      return NetworkImage(logo);
    }
    return null;
  }
}
