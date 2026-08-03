"""
Sync Manager: Handles syncing offline records to server with retry logic and batch processing.

Features:
- Automatic retry with exponential backoff
- Batch sync for efficiency
- Connection state monitoring
- Configurable sync intervals
- Detailed logging and metrics
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, Dict, List
from enum import Enum
import time


logger = logging.getLogger(__name__)


class SyncStrategy(str, Enum):
    """Strategy for syncing records."""
    FIFO = "fifo"  # First-in-first-out
    BY_TYPE = "by_type"  # Group by record type
    PRIORITY = "priority"  # Critical records first


@dataclass
class SyncConfig:
    """Configuration for sync behavior."""
    batch_size: int = 50
    max_retries: int = 5
    initial_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 300.0
    backoff_multiplier: float = 2.0
    sync_interval_seconds: float = 30.0
    conflict_resolution_strategy: str = "merge"
    enable_auto_sync: bool = True
    enable_logging: bool = True


@dataclass
class SyncMetrics:
    """Metrics for sync operations."""
    total_syncs: int = 0
    successful_syncs: int = 0
    failed_syncs: int = 0
    total_records_synced: int = 0
    total_conflicts: int = 0
    total_errors: int = 0
    avg_sync_time_ms: float = 0.0
    last_sync_time: Optional[str] = None
    last_error: Optional[str] = None


class SyncManager:
    """
    Manages syncing of offline records to server.

    Handles:
    - Batch sync operations
    - Retry logic with exponential backoff
    - Conflict resolution
    - Connection monitoring
    - Metrics and logging
    """

    def __init__(
        self,
        gateway: OfflineGateway,
        sync_api_handler: Callable[[List[Dict[str, Any]]], Dict[str, Any]],
        config: Optional[SyncConfig] = None,
    ):
        """
        Initialize sync manager.

        Args:
            gateway: OfflineGateway instance
            sync_api_handler: Async function that sends records to server
                             Should return dict with 'synced' and 'conflicts' keys
            config: Sync configuration
        """
        self.gateway = gateway
        self.sync_api_handler = sync_api_handler
        self.config = config or SyncConfig()
        self.metrics = SyncMetrics()
        self._sync_task: Optional[asyncio.Task] = None
        self._stop_requested = False
        self._retry_state: Dict[str, int] = {}
        self._last_sync_time = 0.0

    async def start_auto_sync(self) -> None:
        """Start automatic sync background task."""
        if not self.config.enable_auto_sync:
            return

        if self._sync_task and not self._sync_task.done():
            return

        self._stop_requested = False
        self._sync_task = asyncio.create_task(self._auto_sync_loop())

    async def stop_auto_sync(self) -> None:
        """Stop automatic sync background task."""
        self._stop_requested = True
        if self._sync_task:
            await self._sync_task

    async def _auto_sync_loop(self) -> None:
        """Background loop that syncs periodically."""
        while not self._stop_requested:
            try:
                # Respect minimum interval between syncs
                elapsed = time.time() - self._last_sync_time
                if elapsed < self.config.sync_interval_seconds:
                    await asyncio.sleep(
                        self.config.sync_interval_seconds - elapsed
                    )

                if self.gateway.is_online():
                    await self.sync_pending()
            except Exception as e:
                logger.error(f"Error in auto-sync loop: {e}")
                await asyncio.sleep(self.config.sync_interval_seconds)

    async def sync_pending(
        self,
        record_type: Optional[RecordType] = None,
        strategy: SyncStrategy = SyncStrategy.FIFO,
    ) -> SyncResult:
        """
        Sync pending records to server.

        Args:
            record_type: Optional filter by record type
            strategy: How to order records for sync

        Returns:
            SyncResult with detailed outcome
        """
        self._last_sync_time = time.time()
        start_time = time.time()

        try:
            pending = self.gateway.get_pending_records(record_type)

            if not pending:
                return SyncResult(
                    success=True,
                    synced_count=0,
                    failed_count=0,
                )

            # Batch processing
            result = SyncResult(
                success=True,
                synced_count=0,
                failed_count=0,
            )

            for i in range(0, len(pending), self.config.batch_size):
                batch = pending[i : i + self.config.batch_size]
                batch_result = await self._sync_batch(batch)

                result.synced_count += batch_result.synced_count
                result.failed_count += batch_result.failed_count
                result.conflicts.extend(batch_result.conflicts)
                result.errors.update(batch_result.errors)

                if not batch_result.success:
                    result.success = False

            self.metrics.total_syncs += 1
            if result.success:
                self.metrics.successful_syncs += 1
            else:
                self.metrics.failed_syncs += 1

            self.metrics.total_records_synced += result.synced_count
            self.metrics.total_conflicts += len(result.conflicts)
            self.metrics.total_errors += len(result.errors)

            elapsed_ms = (time.time() - start_time) * 1000
            self.metrics.avg_sync_time_ms = (
                (self.metrics.avg_sync_time_ms * (self.metrics.total_syncs - 1) +
                 elapsed_ms) / self.metrics.total_syncs
            )
            self.metrics.last_sync_time = datetime.now(timezone.utc).isoformat()

            if self.config.enable_logging:
                logger.info(
                    f"Sync completed: {result.synced_count} synced, "
                    f"{result.failed_count} failed, "
                    f"{len(result.conflicts)} conflicts"
                )

            return result

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            self.metrics.total_syncs += 1
            self.metrics.failed_syncs += 1
            self.metrics.last_error = str(e)
            return SyncResult(
                success=False,
                synced_count=0,
                failed_count=len(pending),
            )

    async def _sync_batch(self, batch: List[CachedRecord]) -> SyncResult:
        """Sync a single batch of records."""
        result = SyncResult(
            success=True,
            synced_count=0,
            failed_count=0,
        )

        # Prepare batch payload
        payload = []
        for record in batch:
            self.gateway.mark_syncing(record.id)
            payload.append({
                "id": record.id,
                "type": record.record_type.value,
                "timestamp": record.timestamp,
                "worker_id": record.worker_id,
                "device_id": record.device_id,
                "data": record.payload,
            })

        try:
            # Call sync API
            server_result = await self._call_sync_api(payload)

            # Process results
            synced_ids = set(server_result.get("synced", []))
            conflicts = server_result.get("conflicts", {})
            errors = server_result.get("errors", {})

            for record in batch:
                if record.id in synced_ids:
                    self.gateway.mark_synced(
                        record.id,
                        server_result.get("server_ids", {}).get(record.id),
                    )
                    result.synced_count += 1
                    self._retry_state.pop(record.id, None)

                elif record.id in conflicts:
                    self.gateway.mark_conflict(record.id, conflicts[record.id])
                    result.conflicts.append(record.id)

                elif record.id in errors:
                    error_msg = errors[record.id]
                    self._handle_sync_error(record.id, error_msg)
                    result.failed_count += 1
                    result.errors[record.id] = error_msg

        except Exception as e:
            # Retry entire batch
            for record in batch:
                self._handle_sync_error(record.id, str(e))
                result.failed_count += 1
            result.success = False

        return result

    def _handle_sync_error(self, record_id: str, error: str) -> None:
        """Handle sync error with retry logic."""
        attempt = self._retry_state.get(record_id, 0) + 1
        self._retry_state[record_id] = attempt

        if attempt >= self.config.max_retries:
            self.gateway.mark_failed(record_id, error)
            if self.config.enable_logging:
                logger.error(f"Record {record_id} failed after {attempt} retries")
        else:
            # Mark as pending for retry
            with self.gateway._lock:
                import sqlite3
                with sqlite3.connect(self.gateway.db_path) as conn:
                    conn.execute("""
                        UPDATE offline_records
                        SET sync_status = ?, last_sync_error = ?
                        WHERE id = ?
                    """, ("pending", error, record_id))
                    conn.commit()

    async def _call_sync_api(self, payload: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Call sync API handler (can be sync or async)."""
        # Handle both sync and async functions
        if asyncio.iscoroutinefunction(self.sync_api_handler):
            return await self.sync_api_handler(payload)
        else:
            # Run sync function in executor to avoid blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self.sync_api_handler,
                payload,
            )

    def get_metrics(self) -> SyncMetrics:
        """Get sync metrics."""
        return self.metrics

    def reset_metrics(self) -> None:
        """Reset sync metrics."""
        self.metrics = SyncMetrics()

    async def handle_connection_change(self, is_online: bool) -> None:
        """Handle device connection state change."""
        self.gateway.set_online(is_online)

        if is_online and self.config.enable_auto_sync:
            # Immediately sync pending when coming online
            await self.sync_pending()


# Import guard for type hints
try:
    from .offline_gateway import OfflineGateway, CachedRecord, RecordType, SyncResult
except ImportError:
    pass
