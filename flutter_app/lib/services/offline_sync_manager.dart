"""
SUPPIX Offline Sync Protocol - Flutter/Dart Implementation
===========================================================

Mobile client implementation für Offline-Sync mit dem SUPPIX Backend.
Unterstützt Check-in/Check-out, Location Updates, Security Alerts.
"""

import 'package:http/http.dart' as http;
import 'package:sqflite/sqflite.dart';
import 'dart:convert';
import 'package:uuid/uuid.dart';

enum RecordType {
  CHECKIN,
  CHECKOUT,
  LOCATION_UPDATE,
  SECURITY_ALERT,
}

enum SyncStatus {
  PENDING,
  SYNCING,
  SYNCED,
  CONFLICT,
  FAILED,
}

class CachedRecord {
  final String recordId;
  final RecordType recordType;
  final Map<String, dynamic> data;
  final DateTime timestamp;
  SyncStatus syncStatus;
  int attempts;
  DateTime? lastAttempt;
  Map<String, dynamic>? serverData;

  CachedRecord({
    required this.recordId,
    required this.recordType,
    required this.data,
    required this.timestamp,
    this.syncStatus = SyncStatus.PENDING,
    this.attempts = 0,
  });

  Map<String, dynamic> toJson() => {
    'recordId': recordId,
    'recordType': recordType.toString().split('.').last,
    'data': data,
    'timestamp': timestamp.toIso8601String(),
    'syncStatus': syncStatus.toString().split('.').last,
    'attempts': attempts,
    'lastAttempt': lastAttempt?.toIso8601String(),
  };

  factory CachedRecord.fromJson(Map<String, dynamic> json) => CachedRecord(
    recordId: json['recordId'] as String,
    recordType: RecordType.values.byName(json['recordType'] as String),
    data: json['data'] as Map<String, dynamic>,
    timestamp: DateTime.parse(json['timestamp'] as String),
    syncStatus: SyncStatus.values.byName(json['syncStatus'] as String? ?? 'PENDING'),
    attempts: json['attempts'] as int? ?? 0,
  )..lastAttempt = json['lastAttempt'] != null
    ? DateTime.parse(json['lastAttempt'] as String)
    : null;
}

class SyncResult {
  final String status; // success, partial, error
  final int syncedCount;
  final int failedCount;
  final int conflictCount;
  final List<Map<String, dynamic>>? conflicts;

  SyncResult({
    required this.status,
    required this.syncedCount,
    required this.failedCount,
    required this.conflictCount,
    this.conflicts,
  });

  factory SyncResult.fromJson(Map<String, dynamic> json) => SyncResult(
    status: json['status'] as String,
    syncedCount: json['synced'] as int? ?? json['syncedCount'] as int? ?? 0,
    failedCount: json['failed'] as int? ?? json['failedCount'] as int? ?? 0,
    conflictCount: json['conflicts'] as int? ?? json['conflictCount'] as int? ?? 0,
    conflicts: (json['conflicts'] as List?)?.cast<Map<String, dynamic>>(),
  );
}

class OfflineSyncManager {
  final String deviceId;
  final String baseUrl;
  final String apiKey;
  final Database database;

  static const int maxRetries = 5;
  static const int retryDelayMs = 1000;
  static const int batchSize = 100;

  OfflineSyncManager({
    required this.deviceId,
    required this.baseUrl,
    required this.apiKey,
    required this.database,
  });

  /// Create a record for later sync
  Future<String> createRecord(
    RecordType type,
    Map<String, dynamic> data,
  ) async {
    final recordId = '${deviceId}-${DateTime.now().millisecondsSinceEpoch}-${const Uuid().v4().substring(0, 8)}';

    final record = CachedRecord(
      recordId: recordId,
      recordType: type,
      data: data,
      timestamp: DateTime.now(),
    );

    await database.insert(
      'offline_cache',
      {
        'id': record.recordId,
        'record_type': record.recordType.toString().split('.').last,
        'data': jsonEncode(record.data),
        'sync_status': 'PENDING',
        'attempts': 0,
        'created_at': record.timestamp.toIso8601String(),
      },
    );

    return recordId;
  }

  /// Sync all pending records
  Future<SyncResult> syncPendingRecords() async {
    final pendingRecords = await _getPendingRecords();

    if (pendingRecords.isEmpty) {
      return SyncResult(
        status: 'success',
        syncedCount: 0,
        failedCount: 0,
        conflictCount: 0,
      );
    }

    print('[Sync] Starting batch sync of ${pendingRecords.length} records');

    final batches = _splitIntoBatches(pendingRecords, batchSize);
    final results = {
      'syncedCount': 0,
      'failedCount': 0,
      'conflictCount': 0,
      'conflicts': <Map<String, dynamic>>[],
    };

    for (final batch in batches) {
      await _syncBatch(batch, results);
    }

    return SyncResult(
      status: results['failedCount'] == 0
        ? 'success'
        : results['conflictCount'] == 0
          ? 'partial'
          : 'error',
      syncedCount: results['syncedCount'] as int,
      failedCount: results['failedCount'] as int,
      conflictCount: results['conflictCount'] as int,
      conflicts: (results['conflicts'] as List?)?.cast<Map<String, dynamic>>(),
    );
  }

  /// Sync a single batch
  Future<void> _syncBatch(
    List<CachedRecord> batch,
    Map<String, dynamic> results,
  ) async {
    for (int attempt = 0; attempt < maxRetries; attempt++) {
      try {
        final response = await http.post(
          Uri.parse('$baseUrl/api/platform/offline/sync'),
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer $apiKey',
            'X-Device-Id': deviceId,
          },
          body: jsonEncode({
            'device_id': deviceId,
            'records': batch.map((r) => {
              'record_type': r.recordType.toString().split('.').last,
              'data': r.data,
              'timestamp': r.timestamp.toIso8601String(),
              'record_id': r.recordId,
            }).toList(),
          }),
        );

        if (response.statusCode != 200) {
          throw Exception('HTTP ${response.statusCode}');
        }

        final result = SyncResult.fromJson(jsonDecode(response.body));

        results['syncedCount'] += result.syncedCount;
        results['failedCount'] += result.failedCount;
        results['conflictCount'] += result.conflictCount;
        if (result.conflicts != null) {
          (results['conflicts'] as List).addAll(result.conflicts!);
        }

        // Mark as synced
        for (final record in batch) {
          await database.update(
            'offline_cache',
            {
              'sync_status': 'SYNCED',
              'updated_at': DateTime.now().toIso8601String(),
            },
            where: 'id = ?',
            whereArgs: [record.recordId],
          );
        }

        print('[Sync] Batch synced: ${result.syncedCount} synced, ${result.failedCount} failed');
        return; // Success
      } catch (e) {
        print('[Sync] Attempt ${attempt + 1}/$maxRetries failed: $e');

        if (attempt < maxRetries - 1) {
          await Future.delayed(Duration(milliseconds: retryDelayMs * (1 << attempt)));
        } else {
          // Mark as failed
          for (final record in batch) {
            await database.update(
              'offline_cache',
              {
                'sync_status': 'FAILED',
                'attempts': record.attempts + 1,
                'updated_at': DateTime.now().toIso8601String(),
              },
              where: 'id = ?',
              whereArgs: [record.recordId],
            );
          }
          results['failedCount'] += batch.length;
        }
      }
    }
  }

  /// Resolve conflicts
  Future<bool> resolveConflict(
    String recordId,
    String strategy, {
    Map<String, dynamic>? resolvedData,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/api/platform/offline/conflict/$recordId'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $apiKey',
          'X-Device-Id': deviceId,
        },
        body: jsonEncode({
          'strategy': strategy,
          'resolved_data': resolvedData,
        }),
      );

      if (response.statusCode != 200) {
        throw Exception('HTTP ${response.statusCode}');
      }

      // Mark as synced
      await database.update(
        'offline_cache',
        {
          'sync_status': 'SYNCED',
          'updated_at': DateTime.now().toIso8601String(),
        },
        where: 'id = ?',
        whereArgs: [recordId],
      );

      return true;
    } catch (e) {
      print('[Conflict] Resolution failed: $e');
      return false;
    }
  }

  /// Get pending records
  Future<List<CachedRecord>> _getPendingRecords() async {
    final maps = await database.query(
      'offline_cache',
      where: 'sync_status IN (?, ?)',
      whereArgs: ['PENDING', 'CONFLICT'],
    );

    return maps.map((m) => CachedRecord(
      recordId: m['id'] as String,
      recordType: RecordType.values.byName(m['record_type'] as String),
      data: jsonDecode(m['data'] as String) as Map<String, dynamic>,
      timestamp: DateTime.parse(m['created_at'] as String),
      syncStatus: SyncStatus.values.byName(m['sync_status'] as String),
      attempts: m['attempts'] as int? ?? 0,
    )).toList();
  }

  /// Split into batches
  List<List<T>> _splitIntoBatches<T>(List<T> items, int size) {
    final batches = <List<T>>[];
    for (int i = 0; i < items.length; i += size) {
      batches.add(items.sublist(i, min(i + size, items.length)));
    }
    return batches;
  }

  /// Get sync status
  Future<Map<String, dynamic>?> getSyncStatus() async {
    try {
      final response = await http.get(
        Uri.parse('$baseUrl/api/platform/offline/status/$deviceId'),
        headers: {
          'Authorization': 'Bearer $apiKey',
          'X-Device-Id': deviceId,
        },
      );

      if (response.statusCode != 200) {
        throw Exception('HTTP ${response.statusCode}');
      }

      return jsonDecode(response.body) as Map<String, dynamic>;
    } catch (e) {
      print('[Status] Failed to get sync status: $e');
      return null;
    }
  }
}
