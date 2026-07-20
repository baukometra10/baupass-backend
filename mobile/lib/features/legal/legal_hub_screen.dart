import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_client.dart';
import '../../core/session_store.dart';
import '../../services/legal_repository.dart';
import 'legal_document_screen.dart';

/// Hub: Rechtliches → Impressum & Datenschutz (admin-saved texts + Kontakt).
class LegalHubScreen extends StatefulWidget {
  const LegalHubScreen({
    super.key,
    required this.session,
    this.initialDocument,
  });

  final WorkerSession session;

  /// Optional: open Impressum or Datenschutz immediately after load.
  final LegalDocumentKind? initialDocument;

  @override
  State<LegalHubScreen> createState() => _LegalHubScreenState();
}

class _LegalHubScreenState extends State<LegalHubScreen> {
  final _repo = LegalRepository(ApiClient());
  LegalContent? _content;
  bool _loading = true;
  String? _error;
  bool _openedInitial = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final content = await _repo.fetch(widget.session);
      if (!mounted) return;
      setState(() {
        _content = content;
        _loading = false;
      });
      _maybeOpenInitial();
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message ?? 'Rechtstexte konnten nicht geladen werden.';
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  void _maybeOpenInitial() {
    if (_openedInitial || widget.initialDocument == null || _content == null) return;
    _openedInitial = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _openDocument(widget.initialDocument!);
    });
  }

  Future<void> _openDocument(LegalDocumentKind kind) async {
    final content = _content;
    if (content == null) return;
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => LegalDocumentScreen(kind: kind, content: content),
      ),
    );
  }

  Future<void> _mail(String email) async {
    final uri = Uri(scheme: 'mailto', path: email);
    if (!await launchUrl(uri)) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('E-Mail an $email konnte nicht geöffnet werden.')),
      );
    }
  }

  Future<void> _call(String phone) async {
    final uri = Uri(scheme: 'tel', path: phone);
    if (!await launchUrl(uri)) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Anruf an $phone fehlgeschlagen.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final content = _content;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Rechtliches'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _load,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
                children: [
                  if (_error != null) ...[
                    Material(
                      color: scheme.errorContainer,
                      borderRadius: BorderRadius.circular(12),
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Text(_error!, style: TextStyle(color: scheme.onErrorContainer)),
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],
                  Text(
                    content?.sectionEyebrow ?? 'Rechtliches',
                    style: Theme.of(context).textTheme.labelLarge?.copyWith(
                          color: scheme.primary,
                          letterSpacing: 0.6,
                        ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    content?.sectionTitle ?? 'Impressum & Datenschutz',
                    style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Hier finden Sie die vom Arbeitgeber hinterlegten Angaben '
                    'gemäß TMG/DDV und DSGVO (Art. 13).',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: scheme.onSurfaceVariant,
                        ),
                  ),
                  const SizedBox(height: 20),
                  _LegalTile(
                    icon: Icons.gavel_outlined,
                    title: 'Impressum',
                    subtitle: content?.hasImpressum == true
                        ? 'Anbieterkennzeichnung lesen'
                        : 'Noch kein Text hinterlegt',
                    enabled: content != null,
                    onTap: () => _openDocument(LegalDocumentKind.impressum),
                  ),
                  const SizedBox(height: 10),
                  _LegalTile(
                    icon: Icons.privacy_tip_outlined,
                    title: 'Datenschutz',
                    subtitle: content?.hasDatenschutz == true
                        ? 'Datenschutzerklärung & Kontakt'
                        : 'Erklärung fehlt — Kontakt unten',
                    enabled: content != null,
                    onTap: () => _openDocument(LegalDocumentKind.datenschutz),
                  ),
                  if (content?.controller?.hasAny == true) ...[
                    const SizedBox(height: 24),
                    Text(
                      'Verantwortlicher (Arbeitgeber)',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    _ContactCard(
                      contact: content!.controller!,
                      onMail: _mail,
                      onCall: _call,
                    ),
                  ],
                  if (content?.operator?.hasAny == true) ...[
                    const SizedBox(height: 16),
                    Text(
                      'Plattform-Betreiber',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    _ContactCard(
                      contact: content!.operator!,
                      onMail: _mail,
                      onCall: _call,
                    ),
                  ],
                ],
              ),
            ),
    );
  }
}

class _LegalTile extends StatelessWidget {
  const _LegalTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.enabled = true,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.surfaceContainerHighest.withValues(alpha: 0.55),
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: enabled ? onTap : null,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: scheme.primary.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(icon, color: scheme.primary),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 2),
                    Text(
                      subtitle,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: scheme.onSurfaceVariant,
                          ),
                    ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right, color: scheme.onSurfaceVariant),
            ],
          ),
        ),
      ),
    );
  }
}

class _ContactCard extends StatelessWidget {
  const _ContactCard({
    required this.contact,
    required this.onMail,
    required this.onCall,
  });

  final LegalContact contact;
  final Future<void> Function(String email) onMail;
  final Future<void> Function(String phone) onCall;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final lines = <String>[
      if (contact.name.isNotEmpty) contact.name,
      if (contact.street.isNotEmpty) contact.street,
      if (contact.zipCity.isNotEmpty) contact.zipCity,
      if (contact.website.isNotEmpty) contact.website,
    ];

    return Material(
      color: scheme.surfaceContainerHighest.withValues(alpha: 0.4),
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final line in lines) ...[
              Text(line),
              const SizedBox(height: 2),
            ],
            if (contact.email.isNotEmpty) ...[
              const SizedBox(height: 8),
              TextButton.icon(
                onPressed: () => onMail(contact.email),
                icon: const Icon(Icons.mail_outline, size: 18),
                label: Text(contact.email),
                style: TextButton.styleFrom(
                  padding: EdgeInsets.zero,
                  visualDensity: VisualDensity.compact,
                ),
              ),
            ],
            if (contact.phone.isNotEmpty)
              TextButton.icon(
                onPressed: () => onCall(contact.phone),
                icon: const Icon(Icons.phone_outlined, size: 18),
                label: Text(contact.phone),
                style: TextButton.styleFrom(
                  padding: EdgeInsets.zero,
                  visualDensity: VisualDensity.compact,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
