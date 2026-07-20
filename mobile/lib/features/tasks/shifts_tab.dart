import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/session_store.dart';
import '../../services/tasks_repository.dart';

class ShiftsTab extends StatefulWidget {
  const ShiftsTab({
    super.key,
    required this.session,
    required this.tasks,
  });

  final WorkerSession session;
  final TasksRepository tasks;

  @override
  State<ShiftsTab> createState() => _ShiftsTabState();
}

class _ShiftsTabState extends State<ShiftsTab> with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  List<Map<String, dynamic>> _assignments = [];
  List<Map<String, dynamic>> _pendingSwaps = [];
  List<Map<String, dynamic>> _sentSwaps = [];
  List<Map<String, dynamic>> _historySwaps = [];
  List<Map<String, dynamic>> _coworkers = [];
  bool _loading = true;
  String? _error;
  String? _warning;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    _load();
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  String _friendlyError(Object e) {
    if (e is ApiException) {
      return e.friendlyMessage;
    }
    final text = e.toString().trim();
    if (text.contains('SocketException') || text.contains('Failed host lookup')) {
      return 'Keine Verbindung zum Server. Bitte Netz prüfen.';
    }
    if (text.contains('TimeoutException')) {
      return 'Zeitüberschreitung — bitte erneut versuchen.';
    }
    return text.isNotEmpty ? text : 'Unbekannter Fehler';
  }

  Future<List<Map<String, dynamic>>> _safeList(
    Future<List<Map<String, dynamic>>> Function() load,
    String label,
    List<String> warnings,
  ) async {
    try {
      return await load();
    } catch (e) {
      warnings.add('$label: ${_friendlyError(e)}');
      return <Map<String, dynamic>>[];
    }
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
      _warning = null;
    });
    final warnings = <String>[];
    final assignments = await _safeList(
      () => widget.tasks.listShiftAssignments(widget.session),
      'Schichten',
      warnings,
    );
    List<Map<String, dynamic>> pending = [];
    List<Map<String, dynamic>> sent = [];
    List<Map<String, dynamic>> history = [];
    try {
      final buckets = await widget.tasks.listShiftSwapBuckets(widget.session);
      pending = buckets['pending'] ?? [];
      sent = buckets['sent'] ?? [];
      history = buckets['history'] ?? [];
    } catch (e) {
      warnings.add('Tausch-Anfragen: ${_friendlyError(e)}');
    }
    final coworkers = await _safeList(
      () => widget.tasks.listShiftCoworkers(widget.session),
      'Kollegen',
      warnings,
    );
    if (!mounted) return;
    final allFailed = assignments.isEmpty &&
        pending.isEmpty &&
        sent.isEmpty &&
        history.isEmpty &&
        coworkers.isEmpty &&
        warnings.length >= 2;
    setState(() {
      _assignments = assignments;
      _pendingSwaps = pending;
      _sentSwaps = sent;
      _historySwaps = history;
      _coworkers = coworkers;
      _warning = warnings.isEmpty ? null : warnings.join('\n');
      _error = allFailed ? 'Schichtdaten konnten nicht geladen werden.' : null;
      _loading = false;
    });
  }

  String _statusLabel(String? status) {
    switch ((status ?? '').toLowerCase()) {
      case 'accepted':
        return 'Angenommen';
      case 'rejected':
        return 'Abgelehnt';
      case 'pending':
        return 'Offen';
      default:
        return status?.isNotEmpty == true ? status! : '—';
    }
  }

  String _fmt(String? iso) {
    if (iso == null || iso.isEmpty) return '—';
    return iso.length >= 16 ? iso.substring(0, 16).replaceFirst('T', ' ') : iso;
  }

  Future<void> _proposeSwap(Map<String, dynamic> assignment) async {
    final coworkers = _coworkers.where((c) => (c['id'] ?? '').toString().isNotEmpty).toList();
    if (coworkers.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Keine Kollegen für Tausch verfügbar. Bitte später erneut laden oder Admin prüfen.',
          ),
        ),
      );
      return;
    }
    String? pickId;
    String? targetAssignmentId;
    List<Map<String, dynamic>> peerShifts = [];
    final reasonCtrl = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setLocal) {
            return AlertDialog(
              title: const Text('Schicht tauschen'),
              content: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'Deine Schicht: ${_fmt(assignment['startTime'] as String?)}',
                      style: Theme.of(ctx).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 8),
                    DropdownButtonFormField<String>(
                      decoration: const InputDecoration(labelText: 'Kollege'),
                      items: coworkers
                          .map(
                            (c) => DropdownMenuItem(
                              value: (c['id'] ?? '').toString(),
                              child: Text((c['name'] as String?) ?? (c['id'] ?? '').toString()),
                            ),
                          )
                          .toList(),
                      onChanged: (v) async {
                        pickId = v;
                        targetAssignmentId = null;
                        peerShifts = [];
                        setLocal(() {});
                        if (v == null || v.isEmpty) return;
                        try {
                          peerShifts = await widget.tasks.listShiftCoworkerAssignments(widget.session, v);
                        } catch (_) {
                          peerShifts = [];
                        }
                        if (ctx.mounted) setLocal(() {});
                      },
                    ),
                    const SizedBox(height: 8),
                    if (pickId != null && peerShifts.isEmpty)
                      const Text(
                        'Kollege hat keine anstehende Schicht — dann wird deine Schicht nur abgegeben (Übernahme).',
                        style: TextStyle(fontSize: 12),
                      ),
                    if (peerShifts.isNotEmpty)
                      DropdownButtonFormField<String>(
                        decoration: const InputDecoration(labelText: 'Schicht des Kollegen (Tausch)'),
                        items: [
                          const DropdownMenuItem(value: '', child: Text('Nur abgeben (kein Gegentausch)')),
                          ...peerShifts.map(
                            (s) => DropdownMenuItem(
                              value: (s['id'] ?? '').toString(),
                              child: Text(
                                '${_fmt(s['startTime'] as String?)}'
                                '${((s['site'] as String?)?.isNotEmpty == true) ? ' · ${s['site']}' : ''}',
                              ),
                            ),
                          ),
                        ],
                        onChanged: (v) => targetAssignmentId = (v == null || v.isEmpty) ? null : v,
                      ),
                    TextField(
                      controller: reasonCtrl,
                      decoration: const InputDecoration(labelText: 'Grund (optional)'),
                      maxLines: 2,
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Abbrechen')),
                FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Senden')),
              ],
            );
          },
        );
      },
    );
    if (ok != true || pickId == null || pickId!.isEmpty) return;
    try {
      await widget.tasks.proposeShiftSwap(
        session: widget.session,
        assignmentId: (assignment['id'] ?? '').toString(),
        toWorkerId: pickId!,
        reason: reasonCtrl.text.trim(),
        targetAssignmentId: targetAssignmentId,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            targetAssignmentId == null || targetAssignmentId!.isEmpty
                ? 'Tausch-Anfrage gesendet (Abgabe)'
                : 'Tausch-Anfrage gesendet (Gegenschicht)',
          ),
        ),
      );
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(_friendlyError(e))));
    }
  }

  Future<void> _respondSwap(String swapId, String response) async {
    try {
      await widget.tasks.respondShiftSwap(
        session: widget.session,
        swapId: swapId,
        response: response,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(response == 'accepted' ? 'Angenommen' : 'Abgelehnt')),
      );
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(_friendlyError(e))));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_error!, textAlign: TextAlign.center),
              if (_warning != null) ...[
                const SizedBox(height: 8),
                Text(_warning!, textAlign: TextAlign.center, style: Theme.of(context).textTheme.bodySmall),
              ],
              const SizedBox(height: 12),
              FilledButton(onPressed: _load, child: const Text('Erneut laden')),
            ],
          ),
        ),
      );
    }
    return Column(
      children: [
        if (_warning != null)
          Material(
            color: Theme.of(context).colorScheme.errorContainer,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      _warning!,
                      style: TextStyle(color: Theme.of(context).colorScheme.onErrorContainer, fontSize: 12),
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.refresh, size: 18),
                    onPressed: _load,
                    tooltip: 'Erneut laden',
                  ),
                ],
              ),
            ),
          ),
        TabBar(
          controller: _tabs,
          tabs: const [
            Tab(text: 'Meine Schichten'),
            Tab(text: 'Tausch'),
          ],
        ),
        Expanded(
          child: TabBarView(
            controller: _tabs,
            children: [
              _buildAssignmentsList(),
              _buildSwapsList(),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildAssignmentsList() {
    if (_assignments.isEmpty) {
      return RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: const [
            SizedBox(height: 80),
            Center(child: Text('Keine anstehenden Schichten')),
          ],
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.separated(
        padding: const EdgeInsets.all(12),
        itemCount: _assignments.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (context, i) {
          final a = _assignments[i];
          final site = (a['site'] as String?)?.trim() ?? '';
          final notes = (a['notes'] as String?)?.trim() ?? '';
          final sub = '${_fmt(a['endTime'] as String?)}${site.isNotEmpty ? ' · $site' : ''}'
              '${notes.isNotEmpty ? '\n$notes' : ''}';
          return Card(
            child: ListTile(
              title: Text(_fmt(a['startTime'] as String?)),
              subtitle: Text(sub),
              trailing: IconButton(
                icon: const Icon(Icons.swap_horiz),
                tooltip: 'Abgeben / tauschen',
                onPressed: () => _proposeSwap(a),
              ),
              isThreeLine: notes.isNotEmpty,
            ),
          );
        },
      ),
    );
  }

  Widget _buildSwapsList() {
    final empty = _pendingSwaps.isEmpty && _sentSwaps.isEmpty && _historySwaps.isEmpty;
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(12),
        children: [
          if (empty) ...[
            const SizedBox(height: 80),
            const Center(child: Text('Noch keine Tausch-Anfragen')),
          ],
          if (_pendingSwaps.isNotEmpty) ...[
            Text('Offen für dich', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            ..._pendingSwaps.map(_buildSwapCard),
            const SizedBox(height: 16),
          ],
          if (_sentSwaps.isNotEmpty) ...[
            Text('Gesendet (wartet)', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            ..._sentSwaps.map(_buildSwapCard),
            const SizedBox(height: 16),
          ],
          if (_historySwaps.isNotEmpty) ...[
            Text('Verlauf', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            ..._historySwaps.map(_buildSwapCard),
          ],
        ],
      ),
    );
  }

  Widget _buildSwapCard(Map<String, dynamic> s) {
    final canRespond = s['canRespond'] == true;
    final direction = (s['direction'] as String?) ?? 'inbound';
    final counterpart = (s['counterpart'] as String?)?.trim().isNotEmpty == true
        ? s['counterpart'] as String
        : ((s['fromWorker'] as String?) ?? 'Kollege');
    final status = (s['status'] as String?) ?? 'pending';
    final title = direction == 'outbound' ? 'An $counterpart' : 'Von $counterpart';

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(title, style: Theme.of(context).textTheme.titleMedium),
                  ),
                  Chip(
                    label: Text(_statusLabel(status), style: const TextStyle(fontSize: 11)),
                    visualDensity: VisualDensity.compact,
                    padding: EdgeInsets.zero,
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text('${_fmt(s['startTime'] as String?)} – ${_fmt(s['endTime'] as String?)}'),
              if ((s['site'] as String?)?.isNotEmpty == true)
                Text(s['site'] as String, style: Theme.of(context).textTheme.bodySmall),
              if ((s['reason'] as String?)?.isNotEmpty == true)
                Text(s['reason'] as String, style: Theme.of(context).textTheme.bodySmall),
              if (canRespond) ...[
                const SizedBox(height: 8),
                Row(
                  children: [
                    FilledButton(
                      onPressed: () => _respondSwap((s['id'] ?? '').toString(), 'accepted'),
                      child: const Text('Annehmen'),
                    ),
                    const SizedBox(width: 8),
                    OutlinedButton(
                      onPressed: () => _respondSwap((s['id'] ?? '').toString(), 'rejected'),
                      child: const Text('Ablehnen'),
                    ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
