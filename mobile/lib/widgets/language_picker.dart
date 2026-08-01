import 'dart:async';

import 'package:flutter/material.dart';

import '../core/app_strings.dart';
import '../core/locale_controller.dart';

/// Simple language chips — Dropdown/InputDecorator caused release null-check crashes.
class LanguagePickerTile extends StatelessWidget {
  const LanguagePickerTile({super.key, this.dense = false});

  final bool dense;

  @override
  Widget build(BuildContext context) {
    final ctrl = LocaleController.instance;
    return ListenableBuilder(
      listenable: ctrl,
      builder: (context, _) {
        final current = LocaleController.supported.contains(ctrl.lang) ? ctrl.lang : 'de';
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              t('language', 'Sprache'),
              style: Theme.of(context).textTheme.labelLarge,
            ),
            SizedBox(height: dense ? 6 : 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: LocaleController.supported.map((code) {
                final selected = code == current;
                return ChoiceChip(
                  label: Text(ctrl.labelFor(code)),
                  selected: selected,
                  onSelected: (_) {
                    if (!selected) unawaited(ctrl.setLang(code));
                  },
                );
              }).toList(),
            ),
            if (!dense) ...[
              const SizedBox(height: 6),
              Text(
                t('languageHint', 'Sprache jederzeit hier ändern.'),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ],
        );
      },
    );
  }
}
