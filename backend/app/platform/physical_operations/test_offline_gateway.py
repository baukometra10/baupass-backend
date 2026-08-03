"""Tests for Offline-First Smart Boxes: OfflineGateway and SyncManager."""

import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import asyncio

import pytest

from backend.app.platform.physical_operations.offline_gateway import (
    OfflineGateway,
    CachedRecord,
    RecordType,
    SyncStatus,
    SyncResult,
    OfflineStats,
)
from backend.app.platform.physical_operations.sync_manager import (
    SyncManager,
    SyncConfig,
    SyncMetrics,
)


@pytest.fixture
def temp_db():
    """Create temporary database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "offline.db"
        yield db_path


@pytest.fixture
def gateway(temp_db):
    """Create OfflineGateway instance."""
    return OfflineGateway(
        db_path=temp_db,
        device_id="device-1",
        company_id="comp-1",
    )


class TestOfflineGateway:
    """Test OfflineGateway functionality."""

    def test_init_creates_database(self, temp_db):
        """Test database is created on init."""
        gateway = OfflineGateway(
            db_path=temp_db,
            device_id="device-1",
            company_id="comp-1",
        )
        assert temp_db.exists()

    def test_cache_record(self, gateway):
        """Test caching a record."""
        record = gateway.cache_record(
            record_type=RecordType.CHECKIN,
            worker_id="worker-1",
            payload={"action": "checkin", "site": "main"},
        )

        assert record.id is not None
        assert record.record_type == RecordType.CHECKIN
        assert record.worker_id == "worker-1"
        assert record.sync_status == SyncStatus.PENDING
        assert record.payload["action"] == "checkin"

    def test_get_pending_records(self, gateway):
        """Test retrieving pending records."""
        gateway.cache_record(
            RecordType.CHECKIN,
            "worker-1",
            {"action": "checkin"},
        )
        gateway.cache_record(
            RecordType.LOCATION_UPDATE,
            "worker-1",
            {"lat": 40.7, "lng": -74.0},
        )

        pending = gateway.get_pending_records()
        assert len(pending) == 2

        pending_checkins = gateway.get_pending_records(RecordType.CHECKIN)
        assert len(pending_checkins) == 1
        assert pending_checkins[0].record_type == RecordType.CHECKIN

    def test_mark_syncing(self, gateway):
        """Test marking record as syncing."""
        record = gateway.cache_record(
            RecordType.CHECKIN,
            "worker-1",
            {"action": "checkin"},
        )

        result = gateway.mark_syncing(record.id)
        assert result is True

    def test_mark_synced(self, gateway):
        """Test marking record as synced."""
        record = gateway.cache_record(
            RecordType.CHECKIN,
            "worker-1",
            {"action": "checkin"},
        )

        gateway.mark_synced(record.id, "server-id-123")

        pending = gateway.get_pending_records()
        assert len(pending) == 0

    def test_mark_conflict(self, gateway):
        """Test marking record as conflict."""
        record = gateway.cache_record(
            RecordType.CHECKIN,
            "worker-1",
            {"action": "checkin", "timestamp": "2024-01-01T10:00:00Z"},
        )

        server_version = {"action": "checkout", "timestamp": "2024-01-01T10:05:00Z"}
        gateway.mark_conflict(record.id, server_version)

        # Should not be in pending anymore
        pending = gateway.get_pending_records()
        assert len(pending) == 0

    def test_mark_failed(self, gateway):
        """Test marking record as failed."""
        record = gateway.cache_record(
            RecordType.CHECKIN,
            "worker-1",
            {"action": "checkin"},
        )

        gateway.mark_failed(record.id, "Connection timeout")

    def test_get_records_for_worker(self, gateway):
        """Test retrieving records for specific worker."""
        gateway.cache_record(RecordType.CHECKIN, "worker-1", {"action": "checkin"})
        gateway.cache_record(RecordType.LOCATION_UPDATE, "worker-1", {"lat": 40.7})
        gateway.cache_record(RecordType.CHECKOUT, "worker-2", {"action": "checkout"})

        worker1_records = gateway.get_records_for_worker("worker-1")
        assert len(worker1_records) == 2

        worker1_checkins = gateway.get_records_for_worker(
            "worker-1",
            record_type=RecordType.CHECKIN,
        )
        assert len(worker1_checkins) == 1

    def test_resolve_conflict_local_wins(self, gateway):
        """Test conflict resolution with local_wins strategy."""
        local = CachedRecord(
            id="rec-1",
            record_type=RecordType.CHECKIN,
            device_id="dev-1",
            company_id="comp-1",
            worker_id="worker-1",
            timestamp="2024-01-01T10:05:00Z",
            payload={"action": "checkin", "site": "main"},
            created_locally_at="2024-01-01T10:05:00Z",
        )

        server = {"action": "checkout", "site": "main"}

        result = gateway.resolve_conflict(
            "rec-1",
            local,
            server,
            strategy="local_wins",
        )
        assert result["action"] == "checkin"

    def test_resolve_conflict_server_wins(self, gateway):
        """Test conflict resolution with server_wins strategy."""
        local = CachedRecord(
            id="rec-1",
            record_type=RecordType.CHECKIN,
            device_id="dev-1",
            company_id="comp-1",
            worker_id="worker-1",
            timestamp="2024-01-01T10:05:00Z",
            payload={"action": "checkin"},
            created_locally_at="2024-01-01T10:05:00Z",
        )

        server = {"action": "checkout"}

        result = gateway.resolve_conflict(
            "rec-1",
            local,
            server,
            strategy="server_wins",
        )
        assert result["action"] == "checkout"

    def test_get_stats(self, gateway):
        """Test statistics collection."""
        for i in range(5):
            gateway.cache_record(
                RecordType.CHECKIN,
                f"worker-{i}",
                {"action": "checkin"},
            )

        # Mark some as synced
        pending = gateway.get_pending_records(limit=2)
        for record in pending:
            gateway.mark_synced(record.id)

        stats = gateway.get_stats()
        assert stats.total_records == 5
        assert stats.pending_records == 3
        assert stats.synced_records == 2

    def test_cleanup_old_records(self, gateway):
        """Test cleanup of old synced records."""
        # Create records and mark as synced
        for i in range(15):
            record = gateway.cache_record(
                RecordType.CHECKIN,
                f"worker-{i}",
                {"action": "checkin"},
            )
            gateway.mark_synced(record.id)

        # Add a pending record
        gateway.cache_record(RecordType.CHECKOUT, "worker-100", {"action": "checkout"})

        # Trigger cleanup
        gateway.max_cache_records = 10
        stats_before = gateway.get_stats()

        # Add one more to trigger cleanup
        gateway.cache_record(RecordType.CHECKIN, "worker-200", {"action": "checkin"})

        stats_after = gateway.get_stats()
        # Should still have pending record
        assert stats_after.pending_records >= 1

    def test_on_sync_success_callback(self, gateway):
        """Test sync success callback registration."""
        callback = Mock()
        gateway.on_sync_success(RecordType.CHECKIN, callback)

        record = gateway.cache_record(
            RecordType.CHECKIN,
            "worker-1",
            {"action": "checkin"},
        )

        # Callbacks would be called by sync manager
        assert len(gateway._sync_callbacks[RecordType.CHECKIN]) == 1

    def test_online_status(self, gateway):
        """Test online/offline status tracking."""
        assert gateway.is_online() is True

        gateway.set_online(False)
        assert gateway.is_online() is False

        gateway.set_online(True)
        assert gateway.is_online() is True


class TestSyncManager:
    """Test SyncManager functionality."""

    @pytest.fixture
    def sync_manager(self, gateway):
        """Create SyncManager instance."""
        mock_api = AsyncMock(return_value={
            "synced": [],
            "conflicts": {},
            "errors": {},
            "server_ids": {},
        })
        return SyncManager(gateway, mock_api)

    @pytest.mark.asyncio
    async def test_sync_pending_empty(self, sync_manager):
        """Test sync when no pending records."""
        result = await sync_manager.sync_pending()
        assert result.success is True
        assert result.synced_count == 0

    @pytest.mark.asyncio
    async def test_sync_pending_success(self, gateway, sync_manager):
        """Test successful sync of pending records."""
        # Create pending records
        rec1 = gateway.cache_record(
            RecordType.CHECKIN,
            "worker-1",
            {"action": "checkin"},
        )
        rec2 = gateway.cache_record(
            RecordType.LOCATION_UPDATE,
            "worker-1",
            {"lat": 40.7, "lng": -74.0},
        )

        # Mock successful sync
        sync_manager.sync_api_handler = AsyncMock(return_value={
            "synced": [rec1.id, rec2.id],
            "conflicts": {},
            "errors": {},
            "server_ids": {rec1.id: "srv-1", rec2.id: "srv-2"},
        })

        result = await sync_manager.sync_pending()
        assert result.success is True
        assert result.synced_count == 2

    @pytest.mark.asyncio
    async def test_sync_with_conflicts(self, gateway, sync_manager):
        """Test sync handling conflicts."""
        record = gateway.cache_record(
            RecordType.CHECKIN,
            "worker-1",
            {"action": "checkin"},
        )

        sync_manager.sync_api_handler = AsyncMock(return_value={
            "synced": [],
            "conflicts": {
                record.id: {"action": "checkout"}
            },
            "errors": {},
            "server_ids": {},
        })

        result = await sync_manager.sync_pending()
        assert len(result.conflicts) == 1

    @pytest.mark.asyncio
    async def test_sync_with_errors(self, gateway, sync_manager):
        """Test sync handling errors."""
        record = gateway.cache_record(
            RecordType.CHECKIN,
            "worker-1",
            {"action": "checkin"},
        )

        sync_manager.sync_api_handler = AsyncMock(return_value={
            "synced": [],
            "conflicts": {},
            "errors": {
                record.id: "Server validation failed"
            },
            "server_ids": {},
        })

        result = await sync_manager.sync_pending()
        assert result.failed_count == 1

    @pytest.mark.asyncio
    async def test_metrics_collection(self, gateway, sync_manager):
        """Test sync metrics are collected."""
        rec = gateway.cache_record(
            RecordType.CHECKIN,
            "worker-1",
            {"action": "checkin"},
        )

        sync_manager.sync_api_handler = AsyncMock(return_value={
            "synced": [rec.id],
            "conflicts": {},
            "errors": {},
            "server_ids": {rec.id: "srv-1"},
        })

        await sync_manager.sync_pending()

        metrics = sync_manager.get_metrics()
        assert metrics.total_syncs == 1
        assert metrics.successful_syncs == 1
        assert metrics.total_records_synced == 1

    @pytest.mark.asyncio
    async def test_batch_processing(self, gateway, sync_manager):
        """Test batch processing of records."""
        # Create more records than batch size
        config = SyncConfig(batch_size=5)
        manager = SyncManager(gateway, sync_manager.sync_api_handler, config)

        for i in range(12):
            gateway.cache_record(
                RecordType.CHECKIN,
                f"worker-{i}",
                {"action": "checkin"},
            )

        # Should process in batches
        call_count = 0
        async def mock_api(payload):
            nonlocal call_count
            call_count += 1
            return {
                "synced": [r["id"] for r in payload],
                "conflicts": {},
                "errors": {},
                "server_ids": {r["id"]: f"srv-{i}" for i, r in enumerate(payload)},
            }

        manager.sync_api_handler = mock_api
        await manager.sync_pending()

        # Should have called API multiple times (batch_size=5, 12 records = 3 batches)
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_auto_sync_loop(self, gateway, sync_manager):
        """Test auto sync background loop."""
        sync_manager.config.sync_interval_seconds = 0.1
        sync_manager.config.enable_auto_sync = True

        # Add a record
        gateway.cache_record(
            RecordType.CHECKIN,
            "worker-1",
            {"action": "checkin"},
        )

        sync_count = 0
        async def counting_api(payload):
            nonlocal sync_count
            sync_count += 1
            return {
                "synced": [r["id"] for r in payload],
                "conflicts": {},
                "errors": {},
                "server_ids": {},
            }

        sync_manager.sync_api_handler = counting_api

        # Start auto sync
        await sync_manager.start_auto_sync()
        await asyncio.sleep(0.3)

        # Should have synced at least once
        assert sync_count > 0

        await sync_manager.stop_auto_sync()

    @pytest.mark.asyncio
    async def test_connection_change_handling(self, gateway, sync_manager):
        """Test handling connection state changes."""
        assert gateway.is_online() is True

        await sync_manager.handle_connection_change(False)
        assert gateway.is_online() is False

        await sync_manager.handle_connection_change(True)
        assert gateway.is_online() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
