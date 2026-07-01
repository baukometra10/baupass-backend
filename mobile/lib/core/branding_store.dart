import 'package:flutter/foundation.dart';

import 'tenant_branding.dart';

/// Global tenant branding for app title, push defaults, and native recents label.
class BrandingStore extends ValueNotifier<TenantBranding> {
  BrandingStore._() : super(TenantBranding.fallback);

  static final BrandingStore instance = BrandingStore._();
}
