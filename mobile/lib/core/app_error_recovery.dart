import 'package:flutter/foundation.dart';

/// Global hook so ErrorWidget can reset the app after a widget crash.
class AppErrorRecovery {
  static VoidCallback? onReset;
  static String? lastError;

  static void reset() {
    final cb = onReset;
    if (cb != null) cb();
  }
}
