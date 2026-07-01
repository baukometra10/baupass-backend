import 'package:flutter/services.dart';

import '../core/branding_store.dart';
import '../core/tenant_branding.dart';
import 'worker_cache.dart';

/// Persists tenant branding and applies it to OS surfaces (recents, native title).
class BrandingApplier {
  BrandingApplier({WorkerCache? cache}) : _cache = cache ?? WorkerCache();

  static const _channel = MethodChannel('com.baupass.worker/branding');

  final WorkerCache _cache;

  Future<void> apply(TenantBranding branding) async {
    BrandingStore.instance.value = branding;
    await _cache.saveBranding(branding);

    final accent = branding.accentColor?.toARGB32() ?? TenantBranding.defaultSeed.toARGB32();
    await SystemChrome.setApplicationSwitcherDescription(
      ApplicationSwitcherDescription(
        label: branding.displayName,
        primaryColor: accent & 0xFFFFFFFF,
      ),
    );

    try {
      await _channel.invokeMethod<void>('applyBranding', {
        'displayName': branding.displayName,
        'initials': branding.initials,
        'accentColor': accent,
      });
    } catch (_) {
      // optional native plugin
    }
  }

  static Future<TenantBranding> loadCached() async {
    final cached = await WorkerCache().loadBranding();
    if (cached != null) {
      BrandingStore.instance.value = cached;
      return cached;
    }
    return TenantBranding.fallback;
  }
}
