import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import '../../core/tenant_branding.dart';
import '../../core/session_store.dart';
import '../../services/ai_assistant_service.dart';

/// On-site assistant for workers (HR agent, live tenant data).
class WorkerAiScreen extends StatefulWidget {
  const WorkerAiScreen({super.key, required this.session, required this.ai});

  final WorkerSession session;
  final AiAssistantService ai;

  @override
  State<WorkerAiScreen> createState() => _WorkerAiScreenState();
}

class _WorkerAiScreenState extends State<WorkerAiScreen> {
  final _controller = TextEditingController();
  final _recorder = AudioRecorder();
  final _messages = <_ChatMsg>[];
  bool _loading = false;
  bool _configured = false;
  bool _recording = false;
  String? _recordPath;

  static const _promptChips = [
    'Wer ist gerade auf der Baustelle?',
    'Wann war mein letzter Check-in?',
    'Welche Dokumente laufen bald ab?',
    'Gibt es Sicherheitshinweise für heute?',
  ];

  @override
  void initState() {
    super.initState();
    _loadStatus();
  }

  @override
  void dispose() {
    _controller.dispose();
    _recorder.dispose();
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
          text: 'Beispiele:\n• ${hints.join('\n• ')}\n\nSprache: Mikrofon antippen, erneut antippen zum Senden.',
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
    await _askText(q);
  }

  Future<void> _askText(String q) async {
    setState(() {
      _loading = true;
      _messages.add(_ChatMsg(role: 'user', text: q));
    });
    _messages.add(_ChatMsg(role: 'bot', text: ''));
    final botIdx = _messages.length - 1;
    try {
      var answer = '';
      Map<String, dynamic> doneMeta = {};
      await for (final ev in widget.ai.askStream(widget.session, question: q)) {
        if (!mounted) return;
        final t = ev['type'] as String?;
        if (t == 'chunk') {
          answer += ev['text'] as String? ?? '';
          _messages[botIdx] = _ChatMsg(role: 'bot', text: answer);
          setState(() {});
        } else if (t == 'tool_start') {
          _messages[botIdx] = _ChatMsg(role: 'bot', text: '${answer}\n⏳ ${ev['tool']}…'.trim());
          setState(() {});
        } else if (t == 'done') {
          doneMeta = ev;
          answer = (ev['answer'] as String?) ?? answer;
        } else if (t == 'error') {
          answer = ev['hint'] as String? ?? 'Fehler';
        }
      }
      _messages[botIdx] = _ChatMsg(
        role: 'bot',
        text: answer.isNotEmpty ? answer : 'Keine Antwort',
        isError: answer.isEmpty,
        meta: doneMeta.isNotEmpty ? doneMeta : null,
      );
      if (mounted) setState(() {});
    } catch (e) {
      _messages[botIdx] = _ChatMsg(role: 'bot', text: e.toString(), isError: true);
      if (mounted) setState(() {});
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Widget _sourcesLine(Map<String, dynamic> res) {
    final tools = (res['toolsUsed'] as List?)?.cast<String>() ?? [];
    final sources = (res['sources'] as List?)?.cast<String>() ?? [];
    if (tools.isEmpty && sources.isEmpty) return const SizedBox.shrink();
    final parts = <String>[];
    if (tools.isNotEmpty) parts.add('Tools: ${tools.join(', ')}');
    if (sources.isNotEmpty) parts.add('Daten: ${sources.take(4).join(' · ')}');
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Text(parts.join('\n'), style: Theme.of(context).textTheme.labelSmall),
    );
  }

  void _appendBot(Map<String, dynamic> res) {
    final answer = (res['answer'] as String?)?.trim();
    final hint = (res['hint'] as String?)?.trim();
    final transcript = (res['transcript'] as String?)?.trim();
    var text = answer?.isNotEmpty == true ? answer! : (hint ?? 'Keine Antwort');
    if (transcript != null && transcript.isNotEmpty) {
      text = '🎤 $transcript\n\n$text';
    }
    _messages.add(_ChatMsg(
      role: 'bot',
      text: text,
      isError: answer == null || answer.isEmpty,
      meta: res,
    ));
    if (mounted) setState(() {});
  }

  Future<void> _toggleVoice() async {
    if (_loading) return;
    if (!_recording) {
      if (!await _recorder.hasPermission()) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Mikrofon-Berechtigung erforderlich.')),
        );
        return;
      }
      final dir = await getTemporaryDirectory();
      _recordPath = '${dir.path}/voice_${DateTime.now().millisecondsSinceEpoch}.m4a';
      await _recorder.start(
        const RecordConfig(encoder: AudioEncoder.aacLc, sampleRate: 16000),
        path: _recordPath!,
      );
      if (!mounted) return;
      setState(() => _recording = true);
      return;
    }

    final path = await _recorder.stop();
    if (!mounted) return;
    setState(() => _recording = false);
    final filePath = path ?? _recordPath;
    if (filePath == null) return;
    final file = File(filePath);
    if (!await file.exists()) return;

    setState(() {
      _loading = true;
      _messages.add(_ChatMsg(role: 'user', text: '🎤 Sprachnachricht…'));
    });
    try {
      final bytes = await file.readAsBytes();
      await file.delete();
      final res = await widget.ai.voice(
        widget.session,
        audioBase64: base64Encode(bytes),
        mime: 'audio/m4a',
      );
      if (_messages.isNotEmpty && _messages.last.role == 'user') {
        final transcript = (res['transcript'] as String?)?.trim();
        _messages[_messages.length - 1] = _ChatMsg(
          role: 'user',
          text: transcript?.isNotEmpty == true ? '🎤 $transcript' : '🎤 (Sprache)',
        );
      }
      _appendBot(res);
    } catch (e) {
      _messages.add(_ChatMsg(role: 'bot', text: e.toString(), isError: true));
      if (mounted) setState(() {});
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final branding = TenantBrandingScope.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(branding.aiAssistantTitle),
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
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(m.text),
                        if (m.meta != null) _sourcesLine(m.meta!),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
          if (!_loading && _messages.length < 4)
            SizedBox(
              height: 40,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                children: _promptChips.map((chip) {
                  return Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ActionChip(
                      label: Text(chip, style: const TextStyle(fontSize: 12)),
                      onPressed: _loading ? null : () => _askText(chip),
                    ),
                  );
                }).toList(),
              ),
            ),
          if (_recording)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              child: Row(
                children: [
                  Icon(Icons.mic, color: Theme.of(context).colorScheme.error),
                  const SizedBox(width: 8),
                  const Text('Aufnahme… erneut antippen zum Senden'),
                ],
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
                  IconButton.filledTonal(
                    onPressed: _loading ? null : _toggleVoice,
                    icon: Icon(_recording ? Icons.stop_circle_outlined : Icons.mic_none),
                    tooltip: _recording ? 'Aufnahme beenden' : 'Sprachfrage',
                  ),
                  const SizedBox(width: 8),
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
  _ChatMsg({required this.role, required this.text, this.isError = false, this.meta});
  final String role;
  final String text;
  final bool isError;
  final Map<String, dynamic>? meta;
}
