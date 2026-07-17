import 'package:flutter/material.dart';

import '../../core/session_store.dart';
import '../../services/conference_repository.dart';

/// Minimal conference invite sheet — opens LiveKit URL/token via join payload.
/// Full video UI uses in-app WebView/external LiveKit client in a follow-up;
/// this surfaces invite + join + history entry points.
class ConferenceInviteSheet extends StatefulWidget {
  const ConferenceInviteSheet({
    super.key,
    required this.session,
    required this.repo,
    required this.invite,
  });

  final WorkerSession session;
  final ConferenceRepository repo;
  final Map<String, dynamic> invite;

  @override
  State<ConferenceInviteSheet> createState() => _ConferenceInviteSheetState();
}

class _ConferenceInviteSheetState extends State<ConferenceInviteSheet> {
  bool _busy = false;
  String? _error;
  Map<String, dynamic>? _joined;

  Future<void> _join() async {
    final id = (widget.invite['id'] ?? '').toString();
    if (id.isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final joined = await widget.repo.join(widget.session, id);
      if (!mounted) return;
      setState(() {
        _joined = joined;
        _busy = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = e.toString();
      });
    }
  }

  Future<void> _leave() async {
    final id = (widget.invite['id'] ?? _joined?['id'] ?? '').toString();
    if (id.isEmpty) return;
    try {
      await widget.repo.leave(widget.session, id);
    } catch (_) {
      /* ignore */
    }
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final title = (widget.invite['title'] ?? 'Firmenkonferenz').toString();
    final token = (_joined?['token'] ?? '').toString();
    final url = (_joined?['livekitUrl'] ?? '').toString();
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 8),
            Text(
              _joined == null
                  ? 'Du wurdest zur Firmenkonferenz eingeladen.'
                  : 'Verbunden. Token bereit (LiveKit). Video-Client folgt / nutze Web-PWA für Vollvideo.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            if (url.isNotEmpty) ...[
              const SizedBox(height: 8),
              SelectableText(url, style: Theme.of(context).textTheme.labelSmall),
            ],
            if (token.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text('Token length: ${token.length}', style: Theme.of(context).textTheme.labelSmall),
            ],
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
            const SizedBox(height: 16),
            if (_joined == null)
              FilledButton(
                onPressed: _busy ? null : _join,
                child: _busy
                    ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Beitreten'),
              )
            else
              FilledButton(
                onPressed: _leave,
                style: FilledButton.styleFrom(backgroundColor: const Color(0xFFE53935)),
                child: const Text('Verlassen'),
              ),
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('Schließen')),
          ],
        ),
      ),
    );
  }
}
