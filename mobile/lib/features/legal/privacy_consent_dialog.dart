import 'package:flutter/material.dart';

Future<bool?> showPrivacyConsentDialog(BuildContext context) {
  return showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (context) {
      return AlertDialog(
        title: const Text('Datenschutzhinweis'),
        content: const SingleChildScrollView(
          child: Text(
            'Mit der Nutzung dieser App erklären Sie sich mit der Verarbeitung Ihrer '
            'personenbezogenen Daten einverstanden.\n\n'
            'Standortdaten:\n'
            '• Ihr Standort wird nur während der Arbeitszeit am Arbeitsplatz '
            '(innerhalb des definierten Betriebsgeländes) erfasst und angezeigt.\n'
            '• Außerhalb des Arbeitsplatzes wird Ihr Standort nicht verfolgt oder '
            'dem Arbeitgeber angezeigt.\n'
            '• Die Standorterfassung dient ausschließlich der Zeiterfassung und '
            'Anwesenheitskontrolle am Einsatzort.\n\n'
            'Weitere Informationen erhalten Sie beim Arbeitgeber oder in der '
            'Datenschutzerklärung Ihres Unternehmens.',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Ablehnen'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Verstanden & akzeptieren'),
          ),
        ],
      );
    },
  );
}
