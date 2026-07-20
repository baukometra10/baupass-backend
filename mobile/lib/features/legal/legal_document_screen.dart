import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../services/legal_repository.dart';

enum LegalDocumentKind { impressum, datenschutz }

class LegalDocumentScreen extends StatelessWidget {
  const LegalDocumentScreen({
    super.key,
    required this.kind,
    required this.content,
  });

  final LegalDocumentKind kind;
  final LegalContent content;

  bool get _isPrivacy => kind == LegalDocumentKind.datenschutz;

  String get _title => _isPrivacy ? 'Datenschutz' : 'Impressum';

  String get _body {
    final raw = _isPrivacy ? content.datenschutzText : content.impressumText;
    return raw.trim();
  }

  Future<void> _mail(BuildContext context, String email) async {
    final uri = Uri(scheme: 'mailto', path: email);
    if (!await launchUrl(uri) && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('E-Mail an $email konnte nicht geöffnet werden.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final body = _body;
    final showContacts = _isPrivacy || body.isEmpty;

    return Scaffold(
      appBar: AppBar(title: Text(_title)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 40),
        children: [
          if (showContacts && content.controller?.hasAny == true) ...[
            Text(
              'Verantwortlicher für die Datenverarbeitung',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
            ),
            const SizedBox(height: 6),
            Text(
              'Nach DSGVO Art. 13 müssen Sie den Verantwortlichen und dessen '
              'Kontaktdaten (insbesondere E-Mail) einsehen können.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
            ),
            const SizedBox(height: 12),
            _ContactBlock(
              contact: content.controller!,
              onMail: (email) => _mail(context, email),
            ),
            const SizedBox(height: 20),
            const Divider(),
            const SizedBox(height: 12),
          ],
          if (body.isNotEmpty)
            SelectableText(
              body,
              style: Theme.of(context).textTheme.bodyLarge?.copyWith(height: 1.45),
            )
          else
            Material(
              color: scheme.surfaceContainerHighest.withValues(alpha: 0.5),
              borderRadius: BorderRadius.circular(12),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  _isPrivacy
                      ? 'Es ist noch keine Datenschutzerklärung hinterlegt. '
                          'Bitte wenden Sie sich an Ihren Arbeitgeber '
                          '(Kontaktdaten oben) oder an den Plattform-Betreiber.'
                      : 'Es ist noch kein Impressum hinterlegt. '
                          'Sobald Ihr Arbeitgeber die Texte unter „Rechtliches → '
                          'Impressum & Datenschutz“ speichert, erscheinen sie hier.',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
            ),
          if (_isPrivacy && content.operator?.hasAny == true) ...[
            const SizedBox(height: 28),
            Text(
              'Plattform-Betreiber (App-Anbieter)',
              style: Theme.of(context).textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
            ),
            const SizedBox(height: 8),
            _ContactBlock(
              contact: content.operator!,
              onMail: (email) => _mail(context, email),
            ),
          ],
        ],
      ),
    );
  }
}

class _ContactBlock extends StatelessWidget {
  const _ContactBlock({
    required this.contact,
    required this.onMail,
  });

  final LegalContact contact;
  final Future<void> Function(String email) onMail;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (contact.name.isNotEmpty) Text(contact.name, style: Theme.of(context).textTheme.titleSmall),
        if (contact.street.isNotEmpty) Text(contact.street),
        if (contact.zipCity.isNotEmpty) Text(contact.zipCity),
        if (contact.website.isNotEmpty) Text(contact.website),
        if (contact.email.isNotEmpty)
          TextButton(
            onPressed: () => onMail(contact.email),
            style: TextButton.styleFrom(
              padding: EdgeInsets.zero,
              visualDensity: VisualDensity.compact,
            ),
            child: Text(contact.email),
          ),
        if (contact.phone.isNotEmpty) Text(contact.phone),
      ],
    );
  }
}
