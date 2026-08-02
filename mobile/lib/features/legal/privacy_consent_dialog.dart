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
                        '• Ihr Standort wird nur während der Arbeitszeit am Arbeitsplatz '
                        '(innerhalb des definierten Betriebsgeländes) erfasst und angezeigt.\n'
                        '• Außerhalb des Arbeitsplatzes wird Ihr Standort nicht verfolgt oder '
                        'dem Arbeitgeber angezeigt.\n'
                        '• Die Standorterfassung dient ausschließlich der Zeiterfassung und '
                        'Anwesenheitskontrolle am Einsatzort.\n\n'
                        'Weitere Informationen erhalten Sie in der Datenschutzerklärung '
                        'unter Profil → Rechtliches.',
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
