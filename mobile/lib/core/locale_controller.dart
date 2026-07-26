import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Worker app language — same storage key as PWA (`workpass-worker-lang`)
/// so language survives reinstall when backup/restore keeps app prefs, and
/// is always choosable after install (not only before APK build).
class LocaleController extends ChangeNotifier {
  LocaleController._();
  static final LocaleController instance = LocaleController._();

  static const prefsKey = 'workpass-worker-lang';
  static const supported = <String>['de', 'en', 'tr', 'ar', 'pl', 'fr', 'es', 'it'];

  String _lang = 'de';
  bool _ready = false;

  String get lang => _lang;
  bool get ready => _ready;
  bool get isRtl => _lang == 'ar';

  TextDirection get textDirection => isRtl ? TextDirection.rtl : TextDirection.ltr;

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    final stored = (prefs.getString(prefsKey) ?? '').trim().toLowerCase();
    if (supported.contains(stored)) {
      _lang = stored;
    } else {
      final device = ui.PlatformDispatcher.instance.locale.languageCode.toLowerCase();
      _lang = supported.contains(device) ? device : 'de';
      await prefs.setString(prefsKey, _lang);
    }
    _ready = true;
    notifyListeners();
  }

  Future<void> setLang(String next) async {
    final lang = next.trim().toLowerCase();
    if (!supported.contains(lang) || lang == _lang) return;
    _lang = lang;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(prefsKey, lang);
    notifyListeners();
  }

  String labelFor(String code) {
    switch (code) {
      case 'de':
        return 'Deutsch';
      case 'en':
        return 'English';
      case 'tr':
        return 'Türkçe';
      case 'ar':
        return 'العربية';
      case 'pl':
        return 'Polski';
      case 'fr':
        return 'Français';
      case 'es':
        return 'Español';
      case 'it':
        return 'Italiano';
      default:
        return code.toUpperCase();
    }
  }
}
