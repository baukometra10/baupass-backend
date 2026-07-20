import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../services/legal_repository.dart';

/// Read-only legal document without login (public branding texts).
class PublicLegalScreen extends StatelessWidget {
  const PublicLegalScreen({
    super.key,
    required this.title,
    required this.body,
    this.controller,
  });

  final String title;
  final String body;
  final LegalContact? controller;

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
    final text = body.trim();
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 40),
        children: [
          if (controller?.hasAny == true) ...[
            Text('Kontakt', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            if (controller!.name.isNotEmpty) Text(controller!.name),
            if (controller!.street.isNotEmpty) Text(controller!.street),
            if (controller!.zipCity.isNotEmpty) Text(controller!.zipCity),
            if (controller!.email.isNotEmpty)
              TextButton(
                onPressed: () => _mail(context, controller!.email),
                style: TextButton.styleFrom(padding: EdgeInsets.zero),
                child: Text(controller!.email),
              ),
            if (controller!.phone.isNotEmpty) Text(controller!.phone),
            const SizedBox(height: 16),
            const Divider(),
            const SizedBox(height: 12),
          ],
          if (text.isNotEmpty)
            SelectableText(text, style: Theme.of(context).textTheme.bodyLarge?.copyWith(height: 1.45))
          else
            Material(
              color: scheme.surfaceContainerHighest.withValues(alpha: 0.5),
              borderRadius: BorderRadius.circular(12),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  'Noch kein Text hinterlegt. Nach dem Login finden Sie aktuelle '
                  'Angaben unter Profil → Rechtliches.',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
