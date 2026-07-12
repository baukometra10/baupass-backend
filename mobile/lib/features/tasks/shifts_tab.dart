import 'package:flutter/material.dart';

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
  List<Map<String, dynamic>> _swaps = [];
  List<Map<String, dynamic>> _coworkers = [];
  bool _loading = true;
  String? _error;

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

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await Future.wait([
        widget.tasks.listShiftAssignments(widget.session),
        widget.tasks.listShiftSwaps(widget.session),
        widget.tasks.listShiftCoworkers(widget.session),
      ]);
      if (!mounted) return;
      setState(() {
        _assignments = results[0];
        _swaps = results[1];
        _coworkers = results[2];
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

  String _fmt(String? iso) {
    if (iso == null || iso.isEmpty) return '—';
    return iso.length >= 16 ? iso.substring(0, 16).replaceFirst('T', ' ') : iso;
  }

  Future<void> _proposeSwap(Map<String, dynamic> assignment) async {
    final coworkers = _coworkers.where((c) => c['id'] != null).toList();
    if (coworkers.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Keine Kollegen für Tausch verfügbar')),
      );
      return;
    }
    String? pickId;
    final reasonCtrl = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Schicht tauschen'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
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
                onChanged: (v) => pickId = v,
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
      ),
    );
    if (ok != true || pickId == null || pickId!.isEmpty) return;
    try {
      await widget.tasks.proposeShiftSwap(
        session: widget.session,
        assignmentId: (assignment['id'] ?? '').toString(),
        toWorkerId: pickId!,
        reason: reasonCtrl.text.trim(),
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Tausch-Anfrage gesendet')),
      );
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
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
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
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
              const SizedBox(height: 12),
              FilledButton(onPressed: _load, child: const Text('Erneut laden')),
            ],
          ),
        ),
      );
    }
    return Column(
      children: [
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
                tooltip: 'Tauschen',
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
    if (_swaps.isEmpty) {
      return RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: const [
            SizedBox(height: 80),
            Center(child: Text('Keine offenen Tausch-Anfragen')),
          ],
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView.separated(
        padding: const EdgeInsets.all(12),
        itemCount: _swaps.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (context, i) {
          final s = _swaps[i];
          return Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text((s['fromWorker'] as String?) ?? 'Kollege', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 4),
                  Text('${_fmt(s['startTime'] as String?)} – ${_fmt(s['endTime'] as String?)}'),
                  if ((s['site'] as String?)?.isNotEmpty == true)
                    Text(s['site'] as String, style: Theme.of(context).textTheme.bodySmall),
                  if ((s['reason'] as String?)?.isNotEmpty == true)
                    Text(s['reason'] as String, style: Theme.of(context).textTheme.bodySmall),
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
              ),
            ),
          );
        },
      ),
    );
  }
}
