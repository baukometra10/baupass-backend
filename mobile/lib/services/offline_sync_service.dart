import 'package:connectivity_plus/connectivity_plus.dart';

import '../core/api_client.dart';
import '../core/session_store.dart';
import 'attendance_repository.dart';
import 'offline_attendance_store.dart';

/// Sync offline NFC queue when connectivity returns.
class OfflineSyncService {
  OfflineSyncService(this._attendance, this._store, {Connectivity? connectivity})
      : _connectivity = connectivity ?? Connectivity();

  final AttendanceRepository _attendance;
  final OfflineAttendanceStore _store;
  final Connectivity _connectivity;

  WorkerSession? _session;

  void bindSession(WorkerSession session) {
    _session = session;
  }

  void listen(void Function(int syncedCount) onSynced) {
    _connectivity.onConnectivityChanged.listen((results) async {
      final online = results.any((r) => r != ConnectivityResult.none);
      if (!online || _session == null) return;
      final synced = await syncNow();
      if (synced > 0) onSynced(synced);
    });
  }

  Future<int> syncNow() async {
    final session = _session;
    if (session == null) return 0;
    final queue = await _store.loadQueue();
    if (queue.isEmpty) return 0;
    try {
      final response = await _attendance.syncOfflineEvents(session: session, events: queue);
      final results = response['results'];
      if (results is List) {
        final syncedIds = <String>{};
        for (final item in results) {
          if (item is! Map) continue;
          final id = item['clientEventId'] as String?;
          if (id == null) continue;
          final synced = item['stored'] == true ||
              item['ok'] == true ||
              item['checkoutLogId'] != null ||
              item['siteLeaveLogId'] != null;
          if (synced) syncedIds.add(id);
        }
        if (syncedIds.isNotEmpty) {
          await _store.removeByClientEventIds(syncedIds);
        }
        return syncedIds.length;
      }
      final stored = response['stored'] as int? ?? 0;
      if (stored > 0) {
        await _store.clear();
      }
      return stored;
    } on ApiException {
      return 0;
    }
  }
}
