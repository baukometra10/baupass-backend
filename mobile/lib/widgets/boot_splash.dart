import 'package:flutter/material.dart';

import '../core/app_strings.dart';
import '../core/tenant_branding.dart';
import 'tenant_brand_mark.dart';

/// Branded splash while the worker app restores session / bindings.
class BootSplash extends StatefulWidget {
  const BootSplash({super.key, this.branding});

  final TenantBranding? branding;

  @override
  State<BootSplash> createState() => _BootSplashState();
}

class _BootSplashState extends State<BootSplash> with SingleTickerProviderStateMixin {
  late final AnimationController _pulse;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final branding = widget.branding ?? TenantBranding.suppixShell;
    final accent = branding.accentColor ?? const Color(0xFF06B6D4);

    return Scaffold(
      body: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              const Color(0xFF0B1220),
              Color.lerp(const Color(0xFF0F172A), accent, 0.22)!,
              const Color(0xFF111827),
            ],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: FadeTransition(
              opacity: Tween<double>(begin: 0.82, end: 1).animate(
                CurvedAnimation(parent: _pulse, curve: Curves.easeInOut),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  ScaleTransition(
                    scale: Tween<double>(begin: 0.96, end: 1.04).animate(
                      CurvedAnimation(parent: _pulse, curve: Curves.easeInOut),
                    ),
                    child: Container(
                      padding: const EdgeInsets.all(18),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(28),
                        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
                      ),
                      child: TenantBrandMark(
                        branding: branding,
                        size: 88,
                        borderRadius: 22,
                      ),
                    ),
                  ),
                  const SizedBox(height: 28),
                  Text(
                    branding.displayName.isNotEmpty ? branding.displayName : 'SUPPIX',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 28,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 1.2,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    t('splashTagline', 'Mitarbeiter-App'),
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.72),
                      fontSize: 15,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 36),
                  SizedBox(
                    width: 28,
                    height: 28,
                    child: CircularProgressIndicator(
                      strokeWidth: 2.4,
                      color: accent,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
