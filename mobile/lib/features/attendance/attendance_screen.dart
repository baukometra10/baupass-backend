import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/auth_repository.dart';
import '../../services/attendance_repository.dart';
import '../../services/nfc_service.dart';
import '../../services/offline_attendance_store.dart';
import '../../services/worker_cache.dart';

class AttendanceScreen extends StatefulWidget {
  const AttendanceScreen({
    super.key,
    required this.sessionToken,
    required this.auth,
    required this.attendance,
    required this.nfc,
    required this.offlineStore,
    required this.workerCache,
    this.embedded = false,
  });

  final String sessionToken;
  final AuthRepository auth;
  final AttendanceRepository attendance;
  final NfcService nfc;
  final OfflineAttendanceStore offlineStore;
  final WorkerCache workerCache;
  final bool embedded;

  @override
  State<AttendanceScreen> createState() => _AttendanceScreenState();
}

class _AttendanceScreenState extends State<AttendanceScreen> {
  bool _busy = false;
  String? _status;
  String? _lastDirection;
  Map<String, dynamic>? _profile;
  int _pendingOffline = 0;

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    await _refreshPendingCount();
    await _loadProfile();
    await _trySyncOffline();
  }

  Future<void> _refreshPendingCount() async {
    final count = await widget.offlineStore.pendingCount();
    if (mounted) setState(() => _pendingOffline = count);
  }

  Future<void> _loadProfile() async {
    try {
      final me = await widget.auth.fetchProfile(widget.sessionToken);
      await widget.workerCache.saveProfile(me);
      if (!mounted) return;
      setState(() => _profile = me);
    } catch (_) {
      final cached = await widget.workerCache.loadProfile();
      if (!mounted) return;
      setState(() {
        _profile = cached;
        if (cached != null) {
          _status = 'Offline — showing cached profile. Sync when online.';
        }
      });
    }
  }

  Future<void> _trySyncOffline() async {
    final queue = await widget.offlineStore.loadQueue();
    if (queue.isEmpty) return;
    try {
      final response = await widget.attendance.syncOfflineEvents(
        sessionToken: widget.sessionToken,
        events: queue,
      );
      final stored = response['stored'] as int? ?? 0;
      if (stored > 0) {
        await widget.offlineStore.clear();
        await _refreshPendingCount();
        if (mounted) {
          setState(() => _status = 'Synced $stored offline attendance event(s).');
        }
        await _loadProfile();
      }
    } on ApiException {
      // Stay queued until connectivity returns.
    } catch (_) {}
  }

  String _resolveDirectionForQueue() {
    // Direction is fixed at tap time so offline replay stays correct.
    final siteAccess = _profile?['siteAccess'] as Map<String, dynamic>?;
    final open = siteAccess?['openCheckInToday'] == true;
    return open ? 'check-out' : 'check-in';
  }

  Future<void> _queueOfflineAttendance(String nfcUid, String direction) async {
    final clientEventId =
        'nfc-${DateTime.now().toUtc().millisecondsSinceEpoch}-${nfcUid.hashCode.abs()}';
    await widget.offlineStore.enqueue(<String, dynamic>{
      'type': 'nfc_attendance',
      'clientEventId': clientEventId,
      'nfcUid': nfcUid,
      'direction': direction,
      'occurredAt': DateTime.now().toUtc().toIso8601String(),
    });
    await widget.workerCache.setOpenCheckInToday(direction == 'check-in');
    await _refreshPendingCount();
    if (!mounted) return;
    setState(() {
      _lastDirection = direction;
      _status =
          'No internet: attendance saved on phone ($direction). Will sync automatically.';
    });
  }

  Future<void> _tapAttendance() async {
    setState(() {
      _busy = true;
      _status = 'Hold your NFC card near the phone…';
    });
    try {
      final available = await widget.nfc.isAvailable();
      if (!available) {
        throw NfcUnavailableException('NFC is not available. Enable NFC in device settings.');
      }
      final scan = await widget.nfc.scanTag();
      final direction = _resolveDirectionForQueue();
      final clientEventId =
          'nfc-${DateTime.now().toUtc().millisecondsSinceEpoch}-${scan.uid.hashCode.abs()}';

      setState(() => _status = 'Sending attendance…');
      try {
        final result = await widget.attendance.recordNfcAttendance(
          sessionToken: widget.sessionToken,
          nfcUid: scan.uid,
          direction: direction,
          clientEventId: clientEventId,
        );
        if (!mounted) return;
        final recordedDirection = result['direction'] as String? ?? direction;
        final duplicate = result['duplicate'] == true;
        final open = result['openCheckInToday'] == true;
        await widget.workerCache.setOpenCheckInToday(open);
        setState(() {
          _lastDirection = recordedDirection;
          _status = duplicate
              ? 'Already recorded ($recordedDirection).'
              : 'Attendance saved: $recordedDirection';
        });
      } on ApiException catch (e) {
        if (e.statusCode == 0 || e.errorCode == 'network_error' || e.statusCode >= 500) {
          await _queueOfflineAttendance(scan.uid, direction);
          return;
        }
        rethrow;
      }
    } on NfcUnavailableException catch (e) {
      if (!mounted) return;
      setState(() => _status = e.message);
    } catch (e) {
      if (!mounted) return;
      setState(() => _status = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final worker = _profile?['worker'] as Map<String, dynamic>?;
    final name = worker != null
        ? '${worker['firstName'] ?? ''} ${worker['lastName'] ?? ''}'.trim()
        : '';
    final badgeId = widget.workerCache.badgeIdFromProfile(_profile);

    return Scaffold(
      appBar: widget.embedded
          ? AppBar(
              title: const Text('Attendance'),
              automaticallyImplyLeading: false,
              actions: [
                if (_pendingOffline > 0)
                  Center(
                    child: Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: Chip(
                        label: Text('$_pendingOffline pending'),
                        visualDensity: VisualDensity.compact,
                      ),
                    ),
                  ),
                IconButton(
                  icon: const Icon(Icons.sync),
                  onPressed: _busy ? null : _trySyncOffline,
                  tooltip: 'Sync offline queue',
                ),
              ],
            )
          : AppBar(
              title: const Text('Attendance'),
              actions: [
                if (_pendingOffline > 0)
                  Center(
                    child: Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: Chip(
                        label: Text('$_pendingOffline pending'),
                        visualDensity: VisualDensity.compact,
                      ),
                    ),
                  ),
                IconButton(
                  icon: const Icon(Icons.sync),
                  onPressed: _busy ? null : _trySyncOffline,
                ),
              ],
            ),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (name.isNotEmpty)
              Text('Hello, $name', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'If the phone has no internet',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      '1. Tap your physical card on the site gate reader (recommended).\n'
                      '2. Or scan NFC here — we save on the phone and sync later.',
                    ),
                    if (badgeId != null && badgeId.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Text('Badge ID: $badgeId', style: const TextStyle(fontFamily: 'monospace')),
                    ],
                  ],
                ),
              ),
            ),
            if (_lastDirection != null) ...[
              const SizedBox(height: 8),
              Text('Last action: $_lastDirection'),
            ],
            const Spacer(),
            SizedBox(
              height: 120,
              child: FilledButton.icon(
                onPressed: _busy ? null : _tapAttendance,
                icon: _busy
                    ? const SizedBox(
                        width: 24,
                        height: 24,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Icon(Icons.nfc, size: 36),
                label: Text(_busy ? 'Scanning…' : 'Tap NFC — Attendance'),
                style: FilledButton.styleFrom(
                  textStyle: const TextStyle(fontSize: 18),
                ),
              ),
            ),
            const SizedBox(height: 24),
            if (_status != null)
              Text(
                _status!,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyLarge,
              ),
            const Spacer(),
          ],
        ),
      ),
    );
  }
}
