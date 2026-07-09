import 'package:flutter/material.dart';

import '../../core/session_store.dart';
import '../../services/attendance_repository.dart';

class TimesheetsScreen extends StatefulWidget {
  const TimesheetsScreen({
    super.key,
    required this.session,
    required this.attendance,
  });

  final WorkerSession session;
  final AttendanceRepository attendance;

  @override
  State<TimesheetsScreen> createState() => _TimesheetsScreenState();
}

class _TimesheetsScreenState extends State<TimesheetsScreen> {
  bool _loading = true;
  String? _error;
  String _month = '';
  int _monthTotalMinutes = 0;
  int _todayWorkMinutes = 0;
  bool _attendanceOpen = false;
  List<Map<String, dynamic>> _rows = [];

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    _month =
        '${now.year.toString().padLeft(4, '0')}-${now.month.toString().padLeft(2, '0')}';
    _load();
  }

  String _formatMinutes(int minutes) {
    final h = minutes ~/ 60;
    final m = minutes % 60;
    return '${h}:${m.toString().padLeft(2, '0')} h';
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await widget.attendance.fetchMyTimesheets(
        session: widget.session,
        month: _month,
      );
      if (!mounted) return;
      setState(() {
        _month = (data['month'] as String?) ?? _month;
        _monthTotalMinutes = (data['monthTotalMinutes'] as num?)?.toInt() ?? 0;
        _todayWorkMinutes = (data['todayWorkMinutes'] as num?)?.toInt() ?? 0;
        _attendanceOpen = data['attendanceOpen'] == true;
        _rows = (data['rows'] as List<dynamic>? ?? const [])
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList();
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

  void _shiftMonth(int delta) {
    final parts = _month.split('-');
    if (parts.length < 2) return;
    var year = int.tryParse(parts[0]) ?? DateTime.now().year;
    var month = int.tryParse(parts[1]) ?? DateTime.now().month;
    month += delta;
    while (month < 1) {
      month += 12;
      year -= 1;
    }
    while (month > 12) {
      month -= 12;
      year += 1;
    }
    setState(() {
      _month =
          '${year.toString().padLeft(4, '0')}-${month.toString().padLeft(2, '0')}';
    });
    _load();
  }

  String _directionLabel(String direction) {
    final d = direction.toLowerCase();
    if (d.contains('check-in') || d == 'in' || d == 'login') return 'Ein';
    if (d.contains('check-out') || d == 'out' || d == 'logout') return 'Aus';
    return direction;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Stundennachweis'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _load,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
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
                )
              : ListView(
                  padding: const EdgeInsets.all(20),
                  children: [
                    Row(
                      children: [
                        IconButton(
                          onPressed: () => _shiftMonth(-1),
                          icon: const Icon(Icons.chevron_left),
                        ),
                        Expanded(
                          child: Text(
                            _month,
                            textAlign: TextAlign.center,
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                        ),
                        IconButton(
                          onPressed: () => _shiftMonth(1),
                          icon: const Icon(Icons.chevron_right),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Monat gesamt', style: Theme.of(context).textTheme.titleSmall),
                            Text(
                              _formatMinutes(_monthTotalMinutes),
                              style: Theme.of(context).textTheme.headlineSmall,
                            ),
                            const SizedBox(height: 8),
                            Text(
                              'Heute: ${_formatMinutes(_todayWorkMinutes)}'
                              '${_attendanceOpen ? ' (eingestempelt)' : ''}',
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text('Ereignisse', style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 8),
                    if (_rows.isEmpty)
                      const Text('Keine Einträge in diesem Monat.')
                    else
                      ..._rows.map((row) {
                        final ts = (row['timestamp'] as String?) ?? '';
                        final direction = (row['direction'] as String?) ?? '';
                        final gate = (row['gate'] as String?) ?? '';
                        final note = (row['note'] as String?) ?? '';
                        return Card(
                          child: ListTile(
                            leading: Icon(
                              direction.toLowerCase().contains('out') ||
                                      direction.toLowerCase().contains('check-out')
                                  ? Icons.logout
                                  : Icons.login,
                            ),
                            title: Text(_directionLabel(direction)),
                            subtitle: Text(
                              [
                                if (ts.isNotEmpty) ts.replaceFirst('T', ' ').substring(0, 16),
                                if (gate.isNotEmpty) gate,
                                if (note.isNotEmpty) note,
                              ].join(' · '),
                            ),
                          ),
                        );
                      }),
                  ],
                ),
    );
  }
}
