import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// Local queue for NFC attendance when the phone has no internet.
class OfflineAttendanceStore {
  static const _queueKey = 'baupass_offline_nfc_queue';
  static const maxQueueSize = 50;

  Future<List<Map<String, dynamic>>> loadQueue() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_queueKey);
    if (raw == null || raw.isEmpty) {
      return <Map<String, dynamic>>[];
    }
    try {
      final parsed = jsonDecode(raw);
      if (parsed is! List) {
        return <Map<String, dynamic>>[];
      }
      return parsed
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
    } catch (_) {
      return <Map<String, dynamic>>[];
    }
  }

  Future<void> saveQueue(List<Map<String, dynamic>> queue) async {
    final prefs = await SharedPreferences.getInstance();
    final trimmed = queue.length > maxQueueSize
        ? queue.sublist(queue.length - maxQueueSize)
        : queue;
    await prefs.setString(_queueKey, jsonEncode(trimmed));
  }

  Future<void> enqueue(Map<String, dynamic> event) async {
    final queue = await loadQueue();
    queue.add(event);
    await saveQueue(queue);
  }

  Future<void> removeByClientEventIds(Set<String> ids) async {
    if (ids.isEmpty) return;
    final queue = await loadQueue();
    queue.removeWhere((event) => ids.contains(event['clientEventId'] as String?));
    await saveQueue(queue);
  }

  Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_queueKey);
  }

  Future<int> pendingCount() async {
    final queue = await loadQueue();
    return queue.length;
  }
}
