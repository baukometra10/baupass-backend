import 'package:flutter/material.dart';

import '../../core/app_strings.dart';
import '../../core/locale_controller.dart';
import '../../core/session_store.dart';
import 'legal_document_screen.dart';
import 'legal_hub_screen.dart';

Future<bool?> showPrivacyConsentDialog(
  BuildContext context, {
  WorkerSession? session,
}) {
  return showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (dialogContext) {
      return ListenableBuilder(
        listenable: LocaleController.instance,
        builder: (context, _) {
          return AlertDialog(
            title: Text(t('privacyNoticeTitle', 'Datenschutzhinweis')),
            content: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(t(
                    'privacyNoticeBody',
                    'Mit der Nutzung dieser App erklären Sie sich mit der Verarbeitung Ihrer '
                        'personenbezogenen Daten einverstanden.\n\n'
                        'Standortdaten:\n'
                        '• Ihr Standort wird nur während der angemeldeten Arbeitszeit erfasst '
                        '(nach Check-in), nicht dauerhaft und nicht privat.\n'
                        '• Zweck: Sicherheit am Einsatzort und bessere Arbeitsabläufe / Produktion '
                        '— nicht zur Dauerüberwachung.\n'
                        '• Außerhalb der Arbeitszeit bzw. nach Check-out wird Ihr Standort nicht '
                        'an den Arbeitgeber übermittelt.\n'
                        '• Innerhalb der definierten Betriebsfläche kann die Position während der '
                        'Schicht in Echtzeit aktualisiert werden, wenn Sie sich bewegen.\n\n'
                        'Weitere Informationen: Profil → Rechtliches.',
                  )),
                  if (session != null) ...[
                    const SizedBox(height: 12),
                    TextButton.icon(
                      onPressed: () {
                        Navigator.of(dialogContext, rootNavigator: true).push(
                          MaterialPageRoute<void>(
                            builder: (_) => LegalHubScreen(
                              session: session,
                              initialDocument: LegalDocumentKind.datenschutz,
                            ),
                          ),
                        );
                      },
                      icon: const Icon(Icons.privacy_tip_outlined),
                      label: Text(t('privacyOpenLegal', 'Datenschutz & Impressum öffnen')),
                    ),
                  ],
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(false),
                child: Text(t('privacyDecline', 'Ablehnen')),
              ),
              FilledButton(
                onPressed: () => Navigator.of(dialogContext).pop(true),
                child: Text(t('privacyAccept', 'Verstanden & akzeptieren')),
              ),
            ],
          );
        },
      );
    },
  );
}
