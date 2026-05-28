import 'package:flutter/material.dart';

import '../../core/session_store.dart';
import '../../services/ai_assistant_service.dart';

/// On-site assistant for workers (HR agent, live BauPass data).
class WorkerAiScreen extends StatefulWidget {
  const WorkerAiScreen({super.key, required this.session, required this.ai});

  final WorkerSession session;
  final AiAssistantService ai;

  @override
  State<WorkerAiScreen> createState() => _WorkerAiScreenState();
}

class _WorkerAiScreenState extends State<WorkerAiScreen> {
  final _controller = TextEditingController();
  final _messages = <_ChatMsg>[];
  bool _loading = false;
  bool _configured = false;

  @override
  void initState() {
    super.initState();
    _loadStatus();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _loadStatus() async {
    try {
      final st = await widget.ai.status(widget.session);
      if (!mounted) return;
      setState(() => _configured = st['configured'] == true);
      final hints = (st['hints'] as List?)?.cast<String>() ?? [];
      if (hints.isNotEmpty) {
        _messages.add(_ChatMsg(
          role: 'bot',
          text: 'Beispiele:\n• ${hints.join('\n• ')}',
        ));
        setState(() {});
      }
    } catch (_) {
      if (mounted) setState(() => _configured = false);
    }
  }

  Future<void> _send() async {
    final q = _controller.text.trim();
    if (q.isEmpty || _loading) return;
    _controller.clear();
    setState(() {
      _loading = true;
      _messages.add(_ChatMsg(role: 'user', text: q));
    });
    try {
      final res = await widget.ai.ask(widget.session, question: q);
      final answer = (res['answer'] as String?)?.trim();
      final hint = (res['hint'] as String?)?.trim();
      _messages.add(_ChatMsg(
        role: 'bot',
        text: answer?.isNotEmpty == true ? answer! : (hint ?? 'Keine Antwort'),
        isError: answer == null || answer.isEmpty,
      ));
    } catch (e) {
      _messages.add(_ChatMsg(role: 'bot', text: e.toString(), isError: true));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('BauPass Assistent'),
        actions: [
          Icon(
            _configured ? Icons.cloud_done_outlined : Icons.cloud_off_outlined,
            color: _configured ? Colors.tealAccent : Colors.grey,
          ),
          const SizedBox(width: 12),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(12),
              itemCount: _messages.length,
              itemBuilder: (context, i) {
                final m = _messages[i];
                final align = m.role == 'user' ? Alignment.centerRight : Alignment.centerLeft;
                final bg = m.role == 'user'
                    ? Theme.of(context).colorScheme.primaryContainer
                    : (m.isError
                        ? Theme.of(context).colorScheme.errorContainer
                        : Theme.of(context).colorScheme.surfaceContainerHighest);
                return Align(
                  alignment: align,
                  child: Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.85),
                    decoration: BoxDecoration(
                      color: bg,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(m.text),
                  ),
                );
              },
            ),
          ),
          if (_loading)
            const Padding(
              padding: EdgeInsets.all(8),
              child: LinearProgressIndicator(minHeight: 2),
            ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _controller,
                      minLines: 1,
                      maxLines: 3,
                      decoration: const InputDecoration(
                        hintText: 'Frage zur Baustelle…',
                        border: OutlineInputBorder(),
                        isDense: true,
                      ),
                      onSubmitted: (_) => _send(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    onPressed: _loading ? null : _send,
                    icon: const Icon(Icons.send),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ChatMsg {
  _ChatMsg({required this.role, required this.text, this.isError = false});
  final String role;
  final String text;
  final bool isError;
}
