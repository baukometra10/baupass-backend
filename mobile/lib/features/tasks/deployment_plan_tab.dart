import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/session_store.dart';
import '../../services/tasks_repository.dart';

/// Monats-Einsatzplan: Tage anzeigen, ablehnen, tauschen, PDF (ein Blatt).
class DeploymentPlanTab extends StatefulWidget {
  const DeploymentPlanTab({
    super.key,
    required this.session,
    required this.tasks,
    required this.enabled,
  });

  final WorkerSession session;
  final TasksRepository tasks;
  final bool enabled;

  @override
  State<DeploymentPlanTab> createState() => _DeploymentPlanTabState();
}

class _DeploymentPlanTabState extends State<DeploymentPlanTab> {
  bool _loading = true;
  String? _error;
  Map<String, dynamic>? _plan;
  int _year = DateTime.now().year;
  int _month = DateTime.now().month;
  List<Map<String, dynamic>> _coworkers = const [];

  @override
  void initState() {
    super.initState();
    _load();
    _loadCoworkers();
  }

  Future<void> _loadCoworkers() async {
    try {
      final list = await widget.tasks.listShiftCoworkers(widget.session);
      if (mounted) setState(() => _coworkers = list);
    } catch (_) {
      /* optional for swap sheet */
    }
  }

  Future<void> _load() async {
    if (!widget.enabled) {
      setState(() => _loading = false);
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await widget.tasks.fetchDeploymentPlan(
        session: widget.session,
        year: _year,
        month: _month,
      );
      if (!mounted) return;
      setState(() {
        _plan = data;
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

  Future<void> _pickMonth() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime(_year, _month),
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 2, 12),
      initialDatePickerMode: DatePickerMode.year,
    );
    if (picked == null) return;
    setState(() {
      _year = picked.year;
      _month = picked.month;
    });
    await _load();
  }

  Future<void> _openPdf({bool printMode = false}) async {
    try {
      final bytes = await widget.tasks.fetchDeploymentPlanPdf(
        session: widget.session,
        year: _year,
        month: _month,
      );
      final name = 'einsatzplan-$_year-${_month.toString().padLeft(2, '0')}.pdf';
      await widget.tasks.saveAndOpenPdf(bytes, filename: name);
      if (printMode && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'PDF geöffnet — bitte „Drucken“ wählen (1 Seite Querformat).',
            ),
          ),
        );
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('PDF nicht verfügbar: $e')),
      );
    }
  }

  String _friendlyDeclineError(Object e) {
    if (e is ApiException) {
      switch (e.errorCode) {
        case 'deployment_decline_after_checkin':
          return 'Nach dem Check-in kann dieser Tag nicht mehr abgelehnt werden.';
        case 'deployment_decline_cutoff_elapsed':
          return e.message?.trim().isNotEmpty == true
              ? e.message!.trim()
              : 'Ablehnen ist nur bis 2 Stunden vor Schichtbeginn möglich.';
        case 'deployment_swap_after_checkin':
          return 'Nach dem Check-in kann dieser Tag nicht mehr getauscht werden.';
        case 'deployment_swap_cutoff_elapsed':
          return e.message?.trim().isNotEmpty == true
              ? e.message!.trim()
              : 'Tauschen ist nur bis 1 Stunde vor Schichtbeginn möglich.';
        case 'deployment_already_swapped':
          return 'Dieser Tag wurde bereits getauscht.';
        case 'past_day_not_allowed':
          return 'Vergangene Tage können nicht geändert werden.';
        default:
          return e.friendlyMessage;
      }
    }
    return e.toString();
  }

  Future<void> _declineDay(Map<String, dynamic> day) async {
    final iso = (day['date'] as String? ?? '').substring(0, 10);
    if (iso.isEmpty) return;
    if (!_canDecline(day, true)) {
      final msg = _declineBlockedMessage(day);
      if (mounted && msg != null) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      }
      return;
    }
    final reasonCtrl = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Einsatztag ablehnen'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${day['weekday'] ?? ''} · $iso'),
            const SizedBox(height: 8),
            Text(
              'Ablehnen ist nur möglich, solange noch kein Check-in erfolgte und mindestens 2 Stunden vor Schichtbeginn.',
              style: Theme.of(ctx).textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            TextField(
              controller: reasonCtrl,
              decoration: const InputDecoration(
                labelText: 'Grund (optional)',
                hintText: 'z. B. Arzttermin',
              ),
              maxLines: 2,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Abbrechen'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Ablehnen'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await widget.tasks.postDeploymentDayResponse(
        session: widget.session,
        date: iso,
        action: 'decline',
        reason: reasonCtrl.text.trim(),
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Ablehnung gespeichert — Firma wird informiert.'),
          ),
        );
      }
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_friendlyDeclineError(e))),
      );
    }
  }

  Future<void> _undoDecline(String iso) async {
    try {
      await widget.tasks.postDeploymentDayResponse(
        session: widget.session,
        date: iso,
        action: 'undo',
      );
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_friendlyDeclineError(e))),
      );
    }
  }

  Future<void> _proposeSwapForDay(Map<String, dynamic> day) async {
    final iso = (day['date'] as String? ?? '').substring(0, 10);
    if (iso.isEmpty) return;
    if (!_canSwap(day)) {
      final msg = _swapBlockedMessage(day);
      if (mounted && msg != null) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
      }
      return;
    }
    final coworkers =
        _coworkers.where((c) => (c['id'] ?? '').toString().isNotEmpty).toList();
    if (coworkers.isEmpty) {
      await _loadCoworkers();
    }
    final peers =
        _coworkers.where((c) => (c['id'] ?? '').toString().isNotEmpty).toList();
    if (peers.isEmpty) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Keine Kollegen für Tausch verfügbar. Bitte später erneut laden.',
          ),
        ),
      );
      return;
    }

    String? pickId;
    String? targetAssignmentId;
    List<Map<String, dynamic>> peerShifts = [];
    final reasonCtrl = TextEditingController();
    final loc = (day['location'] as String? ?? '').trim();
    final start = (day['shiftStart'] as String? ?? '').trim();
    final end = (day['shiftEnd'] as String? ?? '').trim();
    final time = [start, end].where((s) => s.isNotEmpty).join(' – ');

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
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '$iso${loc.isNotEmpty ? ' · $loc' : ''}'
                      '${time.isNotEmpty ? '\n$time' : ''}',
                      style: Theme.of(ctx).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Tauschen nur bis 1 Stunde vor Schichtbeginn. '
                      'Nach Annahme zählen die Stunden beim Kollegen.',
                      style: Theme.of(ctx).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 8),
                    DropdownButtonFormField<String>(
                      // ignore: deprecated_member_use
                      value: pickId,
                      decoration: const InputDecoration(labelText: 'Kollege'),
                      items: peers
                          .map(
                            (c) => DropdownMenuItem(
                              value: (c['id'] ?? '').toString(),
                              child: Text(
                                (c['name'] as String?) ??
                                    (c['id'] ?? '').toString(),
                              ),
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
                          peerShifts = await widget.tasks
                              .listShiftCoworkerAssignments(widget.session, v);
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
                        decoration: const InputDecoration(
                          labelText: 'Schicht des Kollegen (Tausch)',
                        ),
                        items: [
                          const DropdownMenuItem(
                            value: '',
                            child: Text('Nur abgeben (kein Gegentausch)'),
                          ),
                          ...peerShifts.map(
                            (s) {
                              final st = (s['startTime'] as String? ?? '')
                                  .replaceFirst('T', ' ');
                              final label = st.length >= 16
                                  ? st.substring(0, 16)
                                  : st;
                              final site = (s['site'] as String? ?? '').trim();
                              return DropdownMenuItem(
                                value: (s['id'] ?? '').toString(),
                                child: Text(
                                  site.isEmpty ? label : '$label · $site',
                                ),
                              );
                            },
                          ),
                        ],
                        onChanged: (v) => targetAssignmentId =
                            (v == null || v.isEmpty) ? null : v,
                      ),
                    TextField(
                      controller: reasonCtrl,
                      decoration:
                          const InputDecoration(labelText: 'Grund (optional)'),
                      maxLines: 2,
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(ctx, false),
                  child: const Text('Abbrechen'),
                ),
                FilledButton(
                  onPressed: () => Navigator.pop(ctx, true),
                  child: const Text('Senden'),
                ),
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
        toWorkerId: pickId!,
        workDate: iso,
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
    } catch (e) {
      if (!mounted) return;
      final msg = e is ApiException ? _friendlyDeclineError(e) : e.toString();
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
    }
  }

  Future<void> _openDayActions(
    Map<String, dynamic> day, {
    required bool canRespond,
  }) async {
    final iso = (day['date'] as String? ?? '').substring(0, 10);
    final free = _isFree(day);
    final declined = _isDeclined(day);
    final hasWork = _dayHasAssignment(day);
    if (free || !hasWork) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('An freien Tagen gibt es keine Aktionen.')),
      );
      return;
    }

    final canDecline = _canDecline(day, canRespond);
    final canSwap = _canSwap(day);
    final blockMsg = _declineBlockedMessage(day);
    final swapBlockMsg = _swapBlockedMessage(day);
    final swapMsg = _swapMessage(day);
    final swappedOut = _isSwappedOut(day);

    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) {
        final loc = (day['location'] as String? ?? '').trim();
        final start = (day['shiftStart'] as String? ?? '').trim();
        final end = (day['shiftEnd'] as String? ?? '').trim();
        final time = [start, end].where((s) => s.isNotEmpty).join(' – ');
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  '${day['weekday'] ?? ''} · $iso',
                  style: Theme.of(ctx).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                ),
                const SizedBox(height: 4),
                Text(
                  [
                    if (loc.isNotEmpty) loc,
                    if (time.isNotEmpty) time,
                    if (declined) 'Bereits abgelehnt',
                  ].join(' · '),
                  style: Theme.of(ctx).textTheme.bodyMedium,
                ),
                if (swapMsg != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    swapMsg,
                    style: TextStyle(
                      color: Theme.of(ctx).colorScheme.primary,
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                    ),
                  ),
                ],
                if (blockMsg != null && !declined && !swappedOut) ...[
                  const SizedBox(height: 8),
                  Text(
                    blockMsg,
                    style: TextStyle(
                      color: Theme.of(ctx).colorScheme.error,
                      fontSize: 13,
                    ),
                  ),
                ],
                if (swapBlockMsg != null && !swappedOut && !canSwap) ...[
                  const SizedBox(height: 8),
                  Text(
                    swapBlockMsg,
                    style: TextStyle(
                      color: Theme.of(ctx).colorScheme.error,
                      fontSize: 13,
                    ),
                  ),
                ],
                const SizedBox(height: 12),
                if (swappedOut)
                  const ListTile(
                    leading: Icon(Icons.swap_horiz),
                    title: Text('Bereits getauscht'),
                    subtitle: Text('Keine weiteren Aktionen für diesen Tag'),
                  )
                else if (declined)
                  ListTile(
                    leading: const Icon(Icons.undo),
                    title: const Text('Ablehnung zurücknehmen'),
                    onTap: () {
                      Navigator.pop(ctx);
                      _undoDecline(iso);
                    },
                  )
                else ...[
                  ListTile(
                    leading: Icon(
                      Icons.event_busy,
                      color: canDecline
                          ? Theme.of(ctx).colorScheme.error
                          : Theme.of(ctx).disabledColor,
                    ),
                    title: const Text('Tag ablehnen'),
                    subtitle: Text(
                      canDecline
                          ? 'Firma wird informiert'
                          : (blockMsg ?? 'Nicht möglich'),
                    ),
                    enabled: canDecline,
                    onTap: canDecline
                        ? () {
                            Navigator.pop(ctx);
                            _declineDay(day);
                          }
                        : null,
                  ),
                  ListTile(
                    leading: Icon(
                      Icons.swap_horiz,
                      color: canSwap
                          ? Theme.of(ctx).colorScheme.primary
                          : Theme.of(ctx).disabledColor,
                    ),
                    title: const Text('Schicht tauschen / abgeben'),
                    subtitle: Text(
                      canSwap
                          ? 'Mit einem Kollegen (bis 1 Std. vor Beginn)'
                          : (swapBlockMsg ?? 'Nicht möglich'),
                    ),
                    enabled: canSwap,
                    onTap: canSwap
                        ? () {
                            Navigator.pop(ctx);
                            _proposeSwapForDay(day);
                          }
                        : null,
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  bool _isFree(Map<String, dynamic> day) {
    if (day['isFree'] == true) return true;
    final loc = (day['location'] as String? ?? '').trim().toLowerCase();
    const markers = {
      'frei',
      'free',
      'off',
      'urlaub',
      'ferien',
      'kein einsatz',
      'keine arbeit',
      'rest day',
    };
    return markers.contains(loc);
  }

  bool _dayHasAssignment(Map<String, dynamic> day) {
    final loc = (day['location'] as String? ?? '').trim();
    if (loc.isEmpty) return false;
    return !_isFree(day);
  }

  bool _isDeclined(Map<String, dynamic> day) {
    return day['workerResponse'] == 'declined' || day['isDeclined'] == true;
  }

  bool _isSwappedOut(Map<String, dynamic> day) {
    return day['isSwappedOut'] == true ||
        (day['swapStatus'] as String? ?? '').toLowerCase() == 'out';
  }

  String? _swapMessage(Map<String, dynamic> day) {
    final msg = (day['swapMessage'] as String? ?? '').trim();
    if (msg.isNotEmpty) return msg;
    final partner = (day['swapPartnerName'] as String? ?? '').trim();
    if (_isSwappedOut(day) && partner.isNotEmpty) {
      return 'Du hast diesen Tag mit $partner getauscht.';
    }
    if ((day['swapStatus'] as String? ?? '').toLowerCase() == 'in' &&
        partner.isNotEmpty) {
      return 'Übernommen von $partner.';
    }
    return null;
  }

  bool _isTodayOrFuture(String iso) {
    final parsed = DateTime.tryParse(iso);
    if (parsed == null) return false;
    final today = DateTime.now();
    final d = DateTime(parsed.year, parsed.month, parsed.day);
    final t = DateTime(today.year, today.month, today.day);
    return !d.isBefore(t);
  }

  bool _canDecline(Map<String, dynamic> day, bool canRespond) {
    if (!canRespond ||
        !_dayHasAssignment(day) ||
        _isDeclined(day) ||
        _isSwappedOut(day)) {
      return false;
    }
    if (day.containsKey('canDecline')) return day['canDecline'] == true;
    final iso = (day['date'] as String? ?? '').substring(0, 10);
    return _isTodayOrFuture(iso);
  }

  bool _canSwap(Map<String, dynamic> day) {
    if (!_dayHasAssignment(day) || _isDeclined(day) || _isSwappedOut(day)) {
      return false;
    }
    if (day.containsKey('canSwap')) return day['canSwap'] == true;
    final iso = (day['date'] as String? ?? '').substring(0, 10);
    return _isTodayOrFuture(iso);
  }

  String? _declineBlockedMessage(Map<String, dynamic> day) {
    final reason = (day['declineBlockReason'] as String? ?? '').trim();
    switch (reason) {
      case 'checked_in':
        return 'Nach dem Check-in kann dieser Tag nicht mehr abgelehnt werden.';
      case 'cutoff':
        final hours = day['declineCutoffHours'];
        final h = hours is num ? hours.toString() : '2';
        return 'Ablehnen nur bis $h Stunden vor Schichtbeginn möglich.';
      case 'past_day':
        return 'Vergangene Tage können nicht abgelehnt werden.';
      case 'swapped_out':
        return _swapMessage(day) ?? 'Dieser Tag wurde bereits getauscht.';
      default:
        return null;
    }
  }

  String? _swapBlockedMessage(Map<String, dynamic> day) {
    final reason = (day['swapBlockReason'] as String? ?? '').trim();
    switch (reason) {
      case 'checked_in':
        return 'Nach dem Check-in kann dieser Tag nicht mehr getauscht werden.';
      case 'cutoff':
        final hours = day['swapCutoffHours'];
        final h = hours is num ? hours.toString() : '1';
        return 'Tauschen nur bis $h Stunde(n) vor Schichtbeginn möglich.';
      case 'past_day':
        return 'Vergangene Tage können nicht getauscht werden.';
      case 'swapped_out':
        return _swapMessage(day) ?? 'Dieser Tag wurde bereits getauscht.';
      default:
        return null;
    }
  }

  Color? _dayColor(Map<String, dynamic> day) {
    final raw =
        (day['dayColor'] as String? ?? day['day_color'] as String? ?? '').trim();
    if (raw.isEmpty) {
      if (_isFree(day)) return const Color(0xFF10B981);
      return null;
    }
    var hex = raw.replaceFirst('#', '');
    if (hex.length == 3) {
      hex = hex.split('').map((c) => '$c$c').join();
    }
    if (hex.length != 6) return null;
    final value = int.tryParse(hex, radix: 16);
    if (value == null) return null;
    return Color(0xFF000000 | value);
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'Einsatzplan ist in Ihrem Paket nicht freigeschaltet. Bitte Arbeitgeber kontaktieren.',
          ),
        ),
      );
    }

    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    final published = _plan?['published'] == true;
    final canRespond = _plan?['canRespond'] == true ||
        published ||
        (_plan?['visible'] != false &&
            ((_plan?['scheduledDayCount'] as num?)?.toInt() ?? 0) > 0);
    final visible = _plan?['visible'] != false;
    final days = (_plan?['days'] as List?)?.cast<Map<String, dynamic>>() ??
        <Map<String, dynamic>>[];

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _pickMonth,
                  icon: const Icon(Icons.calendar_month),
                  label: Text('${_month.toString().padLeft(2, '0')}/$_year'),
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                tooltip: 'PDF',
                onPressed: published ? () => _openPdf() : null,
                icon: const Icon(Icons.picture_as_pdf_outlined),
              ),
              IconButton(
                tooltip: 'Drucken',
                onPressed: published ? () => _openPdf(printMode: true) : null,
                icon: const Icon(Icons.print_outlined),
              ),
            ],
          ),
          if (!visible)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Text(
                  'Für diesen Monat liegt noch kein Plan vor. Ihr Arbeitgeber muss den Monatsplan speichern oder senden.',
                ),
              ),
            )
          else if (!published && canRespond)
            Card(
              color: Theme.of(context).colorScheme.surfaceContainerHighest,
              child: const Padding(
                padding: EdgeInsets.all(16),
                child: Text(
                  'Entwurf: Tippen Sie auf einen Einsatztag, um abzulehnen oder zu tauschen. PDF folgt nach Freigabe.',
                ),
              ),
            )
          else if (visible)
            Card(
              color: Theme.of(context).colorScheme.surfaceContainerHighest,
              child: const Padding(
                padding: EdgeInsets.all(12),
                child: Text(
                  'Tipp: Tippen Sie auf einen Arbeitstag → Ablehnen oder Schicht tauschen. Ablehnen bis 2 Std. / Tauschen bis 1 Std. vor Schichtbeginn; nach Check-in gesperrt. Nach Tausch zählen die Stunden beim Kollegen.',
                  style: TextStyle(fontSize: 13),
                ),
              ),
            ),
          if (visible) ...[
            ...days.where((d) {
              final loc = (d['location'] as String? ?? '').trim();
              final declined = _isDeclined(d);
              final free = _isFree(d);
              final weekend = d['isWeekend'] == true;
              return loc.isNotEmpty || free || declined || !weekend;
            }).map((day) {
              final iso = (day['date'] as String? ?? '').substring(0, 10);
              final loc = (day['location'] as String? ?? '').trim();
              final free = _isFree(day);
              final declined = _isDeclined(day);
              final start = (day['shiftStart'] as String? ?? '').trim();
              final end = (day['shiftEnd'] as String? ?? '').trim();
              String time = '';
              if (!free && (start.isNotEmpty || end.isNotEmpty)) {
                time = [start, end].where((s) => s.isNotEmpty).join(' – ');
              }
              final accent = _dayColor(day);
              final cardColor = declined
                  ? Theme.of(context)
                      .colorScheme
                      .errorContainer
                      .withValues(alpha: 0.35)
                  : (accent?.withValues(alpha: 0.22));
              final titleDate = iso.length >= 10 ? iso.substring(8, 10) : iso;
              final weekday = (day['weekday'] as String? ?? '').toString();
              final subtitleLines = <String>[
                if (free) 'Frei' else if (loc.isNotEmpty) loc else 'Kein Einsatz',
                if (time.isNotEmpty) time,
                if (declined) 'Abgelehnt',
                if (_swapMessage(day) != null) _swapMessage(day)!,
              ];
              final canDecline = _canDecline(day, canRespond);
              return Card(
                margin: const EdgeInsets.only(bottom: 8),
                color: cardColor,
                clipBehavior: Clip.antiAlias,
                child: IntrinsicHeight(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Container(
                        width: 6,
                        color: declined
                            ? Theme.of(context).colorScheme.error
                            : (accent ??
                                Theme.of(context).colorScheme.outlineVariant),
                      ),
                      Expanded(
                        child: ListTile(
                          onTap: free
                              ? null
                              : () => _openDayActions(
                                    day,
                                    canRespond: canRespond,
                                  ),
                          title: Text(
                            '$titleDate. · $weekday',
                            style: const TextStyle(fontWeight: FontWeight.w700),
                          ),
                          subtitle: Text(subtitleLines.join('\n')),
                          trailing: free
                              ? Chip(
                                  label: const Text('Frei'),
                                  visualDensity: VisualDensity.compact,
                                  backgroundColor: (accent ??
                                          const Color(0xFF10B981))
                                      .withValues(alpha: 0.18),
                                  side: BorderSide.none,
                                )
                              : (declined
                                  ? TextButton(
                                      onPressed: () => _undoDecline(iso),
                                      child: const Text('Zurück'),
                                    )
                                  : Icon(
                                      Icons.more_horiz,
                                      color: canDecline
                                          ? Theme.of(context).colorScheme.primary
                                          : Theme.of(context)
                                              .colorScheme
                                              .outline,
                                    )),
                        ),
                      ),
                    ],
                  ),
                ),
              );
            }),
          ],
        ],
      ),
    );
  }
}
