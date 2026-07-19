import 'package:flutter/material.dart';

import '../../core/session_store.dart';
import '../../services/conference_repository.dart';
import 'conference_room_screen.dart';

/// Conference invite sheet — join opens the in-app LiveKit video room.
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
      final token = (joined['token'] ?? '').toString();
      final url = (joined['livekitUrl'] ?? '').toString();
      final roomId = (joined['id'] ?? id).toString();
      final title = (joined['title'] ?? widget.invite['title'] ?? 'Firmenkonferenz').toString();
      if (token.isEmpty || url.isEmpty) {
        setState(() {
          _busy = false;
          _error = 'Konferenz-Server nicht konfiguriert (kein LiveKit-Token).';
        });
        return;
      }
      setState(() => _busy = false);
      final navigator = Navigator.of(context);
      navigator.pop();
      await navigator.push(
        MaterialPageRoute<void>(
          fullscreenDialog: true,
          builder: (_) => ConferenceRoomScreen(
            session: widget.session,
            repo: widget.repo,
            roomId: roomId,
            livekitUrl: url,
            token: token,
            title: title,
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = e.toString();
      });
    }
  }

  Future<void> _decline() async {
    final id = (widget.invite['id'] ?? '').toString();
    if (id.isNotEmpty) {
      try {
        await widget.repo.leave(widget.session, id);
      } catch (_) {
        /* ignore */
      }
    }
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final title = (widget.invite['title'] ?? 'Firmenkonferenz').toString();
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
              'Du wurdest zur Firmenkonferenz eingeladen. Mit Video und Audio beitreten.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _busy ? null : _join,
              child: _busy
                  ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Beitreten'),
            ),
            TextButton(onPressed: _busy ? null : _decline, child: const Text('Ablehnen')),
          ],
        ),
      ),
    );
  }
}
