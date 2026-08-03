/**
 * SUPPIX Offline Sync Protocol - Mobile Client Implementation
 * ============================================================
 *
 * Implementierung für Android (Kotlin) und Flutter (Dart)
 * zur Koordination von Offline-Sync mit dem Backend.
 */

class OfflineSyncProtocol {
  private deviceId: string;
  private baseUrl: string;
  private apiKey: string;
  private maxRetries: number = 5;
  private retryDelayMs: number = 1000;
  private batchSize: number = 100;

  constructor(deviceId: string, baseUrl: string, apiKey: string) {
    this.deviceId = deviceId;
    this.baseUrl = baseUrl;
    this.apiKey = apiKey;
  }

  /**
   * Record types that can be synced
   */
  enum RecordType {
    CHECKIN = "CHECKIN",
    CHECKOUT = "CHECKOUT",
    LOCATION_UPDATE = "LOCATION_UPDATE",
    SECURITY_ALERT = "SECURITY_ALERT",
  }

  /**
   * Sync status for each record
   */
  enum SyncStatus {
    PENDING = "PENDING",
    SYNCING = "SYNCING",
    SYNCED = "SYNCED",
    CONFLICT = "CONFLICT",
    FAILED = "FAILED",
  }

  /**
   * Conflict resolution strategies
   */
  enum ConflictStrategy {
    LOCAL_WINS = "local_wins",
    SERVER_WINS = "server_wins",
    MERGE = "merge",
    MANUAL = "manual",
  }

  /**
   * Record interface
   */
  interface CachedRecord {
    recordId: string;
    recordType: RecordType;
    data: Record<string, any>;
    timestamp: string; // ISO8601
    syncStatus: SyncStatus;
    attempts: number;
    lastAttempt?: string;
    serverData?: Record<string, any>; // For conflicts
  }

  /**
   * Sync result from server
   */
  interface SyncResult {
    status: "success" | "partial" | "error";
    syncedCount: number;
    failedCount: number;
    conflictCount: number;
    conflicts?: Array<{
      recordId: string;
      localData: Record<string, any>;
      serverData: Record<string, any>;
    }>;
  }

  /**
   * 1. Record Creation (Offline)
   * ============================
   */

  /**
   * Erstelle einen neuen Record, der später synced wird.
   *
   * @example
   * await syncProtocol.createRecord(
   *   "CHECKIN",
   *   {
   *     workerId: "w-123",
   *     timestamp: "2025-08-03T09:00:00Z",
   *     location: { lat: 40.7128, lng: -74.0060 }
   *   }
   * )
   */
  async createRecord(
    recordType: string,
    data: Record<string, any>
  ): Promise<string> {
    const recordId = `${this.deviceId}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    const record: CachedRecord = {
      recordId,
      recordType: recordType as RecordType,
      data,
      timestamp: new Date().toISOString(),
      syncStatus: SyncStatus.PENDING,
      attempts: 0,
    };

    // Save to local storage
    await this.saveRecordLocally(record);

    console.log(`[Offline] Record created: ${recordId}`);
    return recordId;
  }

  /**
   * 2. Batch Sync (Online)
   * ======================
   */

  /**
   * Sync alle pending records mit dem Server.
   *
   * @example
   * const result = await syncProtocol.syncPendingRecords();
   * console.log(`Synced: ${result.syncedCount}, Failed: ${result.failedCount}`);
   */
  async syncPendingRecords(): Promise<SyncResult> {
    // Get pending records from local storage
    const pendingRecords = await this.getPendingRecords();

    if (pendingRecords.length === 0) {
      return {
        status: "success",
        syncedCount: 0,
        failedCount: 0,
        conflictCount: 0,
      };
    }

    console.log(
      `[Sync] Starting batch sync of ${pendingRecords.length} records`
    );

    // Split into batches
    const batches = this.splitIntoBatches(pendingRecords, this.batchSize);
    const results = {
      syncedCount: 0,
      failedCount: 0,
      conflictCount: 0,
      conflicts: [] as any[],
    };

    for (const batch of batches) {
      await this.syncBatch(batch, results);
    }

    return {
      status:
        results.failedCount === 0
          ? "success"
          : results.conflictCount === 0
            ? "partial"
            : "error",
      ...results,
    };
  }

  /**
   * Sync a single batch of records
   */
  private async syncBatch(
    batch: CachedRecord[],
    results: any
  ): Promise<void> {
    for (let attempt = 0; attempt < this.maxRetries; attempt++) {
      try {
        const response = await fetch(`${this.baseUrl}/api/platform/offline/sync`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${this.apiKey}`,
            "X-Device-Id": this.deviceId,
          },
          body: JSON.stringify({
            device_id: this.deviceId,
            records: batch.map((r) => ({
              record_type: r.recordType,
              data: r.data,
              timestamp: r.timestamp,
              record_id: r.recordId,
            })),
          }),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const result: SyncResult = await response.json();

        results.syncedCount += result.syncedCount;
        results.failedCount += result.failedCount;
        results.conflictCount += result.conflictCount;

        if (result.conflicts) {
          results.conflicts.push(...result.conflicts);
        }

        // Mark records as synced
        for (const record of batch) {
          record.syncStatus = SyncStatus.SYNCED;
          record.lastAttempt = new Date().toISOString();
          await this.updateRecordLocally(record);
        }

        console.log(
          `[Sync] Batch synced: ${result.syncedCount} synced, ${result.failedCount} failed`
        );
        break; // Success, exit retry loop
      } catch (error) {
        console.warn(
          `[Sync] Attempt ${attempt + 1}/${this.maxRetries} failed: ${error}`
        );

        if (attempt < this.maxRetries - 1) {
          const delay = this.retryDelayMs * Math.pow(2, attempt);
          await this.sleep(delay);
        } else {
          // Mark as failed after all retries
          for (const record of batch) {
            record.syncStatus = SyncStatus.FAILED;
            record.attempts++;
            record.lastAttempt = new Date().toISOString();
            await this.updateRecordLocally(record);
          }

          results.failedCount += batch.length;
        }
      }
    }
  }

  /**
   * 3. Conflict Resolution
   * ======================
   */

  /**
   * Resolve conflicts interactively.
   *
   * @example
   * const conflicts = result.conflicts || [];
   * for (const conflict of conflicts) {
   *   const strategy = userChoseStrategy(conflict);
   *   await syncProtocol.resolveConflict(conflict.recordId, strategy, userData);
   * }
   */
  async resolveConflict(
    recordId: string,
    strategy: string,
    resolvedData?: Record<string, any>
  ): Promise<boolean> {
    try {
      const response = await fetch(
        `${this.baseUrl}/api/platform/offline/conflict/${recordId}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${this.apiKey}`,
            "X-Device-Id": this.deviceId,
          },
          body: JSON.stringify({
            strategy,
            resolved_data: resolvedData,
          }),
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      // Mark as synced after resolution
      const record = await this.getRecordLocally(recordId);
      if (record) {
        record.syncStatus = SyncStatus.SYNCED;
        await this.updateRecordLocally(record);
      }

      console.log(`[Conflict] Resolved: ${recordId} with strategy: ${strategy}`);
      return true;
    } catch (error) {
      console.error(`[Conflict] Resolution failed: ${error}`);
      return false;
    }
  }

  /**
   * 4. Local Storage Operations
   * ===========================
   */

  private async saveRecordLocally(record: CachedRecord): Promise<void> {
    // Implementierung abhängig von Platform (localStorage, SQLite, etc.)
    // iOS: UserDefaults / SQLite
    // Android: SharedPreferences / SQLite
    // Web: localStorage / IndexedDB

    const key = `suppix_record_${record.recordId}`;
    localStorage.setItem(key, JSON.stringify(record));
  }

  private async updateRecordLocally(record: CachedRecord): Promise<void> {
    const key = `suppix_record_${record.recordId}`;
    localStorage.setItem(key, JSON.stringify(record));
  }

  private async getRecordLocally(recordId: string): Promise<CachedRecord | null> {
    const key = `suppix_record_${recordId}`;
    const data = localStorage.getItem(key);
    return data ? JSON.parse(data) : null;
  }

  private async getPendingRecords(): Promise<CachedRecord[]> {
    const records: CachedRecord[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith("suppix_record_")) {
        const data = localStorage.getItem(key);
        if (data) {
          const record = JSON.parse(data) as CachedRecord;
          if (
            record.syncStatus === SyncStatus.PENDING ||
            record.syncStatus === SyncStatus.CONFLICT
          ) {
            records.push(record);
          }
        }
      }
    }
    return records;
  }

  /**
   * 5. Utilities
   * ============
   */

  private splitIntoBatches<T>(items: T[], size: number): T[][] {
    const batches: T[][] = [];
    for (let i = 0; i < items.length; i += size) {
      batches.push(items.slice(i, i + size));
    }
    return batches;
  }

  private async sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * Get sync status for device
   */
  async getSyncStatus(): Promise<any> {
    try {
      const response = await fetch(
        `${this.baseUrl}/api/platform/offline/status/${this.deviceId}`,
        {
          headers: {
            Authorization: `Bearer ${this.apiKey}`,
            "X-Device-Id": this.deviceId,
          },
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`[Status] Failed to get sync status: ${error}`);
      return null;
    }
  }
}

/**
 * Usage Example - Flutter/Dart
 * ============================
 *
 * ```dart
 * final syncProtocol = OfflineSyncProtocol(
 *   deviceId: Platform.instance.getDeviceId(),
 *   baseUrl: "https://api.example.com",
 *   apiKey: authToken
 * );
 *
 * // Create offline record
 * await syncProtocol.createRecord(
 *   "CHECKIN",
 *   {"workerId": "w-123", "location": {"lat": 40.7128, "lng": -74.0060}}
 * );
 *
 * // Listen for connectivity changes
 * connectivity.onConnectivityChanged.listen((result) {
 *   if (result == ConnectivityResult.mobile || result == ConnectivityResult.wifi) {
 *     // Online: trigger sync
 *     syncProtocol.syncPendingRecords().then((result) {
 *       ScaffoldMessenger.of(context).showSnackBar(
 *         SnackBar(content: Text("Synced: ${result.syncedCount} records"))
 *       );
 *
 *       // Handle conflicts
 *       if (result.conflicts?.isNotEmpty == true) {
 *         showConflictDialog(result.conflicts!);
 *       }
 *     });
 *   }
 * });
 * ```
 */

export default OfflineSyncProtocol;
