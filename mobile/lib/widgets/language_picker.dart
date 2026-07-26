import 'dart:async';

import 'package:flutter/material.dart';

import '../core/app_strings.dart';
import '../core/locale_controller.dart';

class LanguagePickerTile extends StatelessWidget {
  const LanguagePickerTile({super.key, this.dense = false});

  final bool dense;

  @override
  Widget build(BuildContext context) {
    final ctrl = LocaleController.instance;
    return ListenableBuilder(
      listenable: ctrl,
      builder: (context, _) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            InputDecorator(
              decoration: InputDecoration(
                labelText: t('language', 'Sprache'),
                isDense: dense,
                border: const OutlineInputBorder(),
              ),
              child: DropdownButtonHideUnderline(
                child: DropdownButton<String>(
                  key: ValueKey('lang-${ctrl.lang}'),
                  value: LocaleController.supported.contains(ctrl.lang) ? ctrl.lang : 'de',
                  isExpanded: true,
                  items: LocaleController.supported
                      .map(
                        (code) => DropdownMenuItem(
                          value: code,
                          child: Text('${ctrl.labelFor(code)} (${code.toUpperCase()})'),
                        ),
                      )
                      .toList(),
                  onChanged: (v) {
                    if (v != null) unawaited(ctrl.setLang(v));
                  },
                ),
              ),
            ),
            if (!dense) ...[
              const SizedBox(height: 6),
              Text(
                t('languageHint'),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ],
        );
      },
    );
  }
}
