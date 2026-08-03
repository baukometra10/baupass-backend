"""
Database Migration: SUPPIX Platform Components
===============================================

Schemas für alle 5 SUPPIX-Punkte:
1. Geospatial Optimization (Bounding Box) - bestehende cameras/zones nutzen
2. WebSockets - realtime messaging (in-memory oder Redis)
3. Offline-First Smart Boxes - offline_cache, sync_status
4. Battery Management - location_trails (erweitern)
5. Edge AI Processing - edge_events, edge_models, webhook_deliveries
"""

import sqlite3
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def migrate_up(db_path: str) -> None:
    """Apply migrations."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Point #3: Offline-First Smart Boxes
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS offline_cache (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                record_type TEXT NOT NULL,
                data TEXT NOT NULL,
                sync_status TEXT DEFAULT 'PENDING',
                attempts INT DEFAULT 0,
                last_attempt TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (device_id) REFERENCES devices(id),
                INDEX idx_device_status (device_id, sync_status)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_status (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                last_sync_time TIMESTAMP,
                pending_records INT DEFAULT 0,
                synced_records INT DEFAULT 0,
                failed_records INT DEFAULT 0,
                conflict_records INT DEFAULT 0,
                last_error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (device_id) REFERENCES devices(id),
                UNIQUE (device_id)
            )
        """)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Point #4: Battery Management / Fused Location Provider
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS battery_stats (
                id TEXT PRIMARY KEY,
                worker_id TEXT NOT NULL,
                battery_level FLOAT NOT NULL,
                drain_rate FLOAT,
                motion_state TEXT,
                sampling_interval INT,
                is_emergency_mode BOOLEAN DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (worker_id) REFERENCES workers(id),
                INDEX idx_worker_time (worker_id, timestamp DESC)
            )
        """)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Point #5: Edge AI Processing
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS edge_events (
                id TEXT PRIMARY KEY,
                gate_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                person_id TEXT,
                confidence FLOAT NOT NULL,
                bbox TEXT,
                zone_id TEXT,
                activity_type TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (gate_id) REFERENCES cameras(id),
                INDEX idx_gate_time (gate_id, timestamp DESC),
                INDEX idx_event_type (event_type)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS edge_models (
                id TEXT PRIMARY KEY,
                model_name TEXT NOT NULL,
                version TEXT NOT NULL,
                model_path TEXT NOT NULL,
                file_hash TEXT,
                status TEXT DEFAULT 'INACTIVE',
                deployed_gates TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (model_name, version)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS webhook_deliveries (
                id TEXT PRIMARY KEY,
                webhook_url TEXT NOT NULL,
                event_id TEXT NOT NULL,
                http_status INT,
                attempts INT DEFAULT 0,
                status TEXT DEFAULT 'PENDING',
                last_attempt TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES edge_events(id),
                INDEX idx_status (status, last_attempt),
                INDEX idx_event (event_id)
            )
        """)

        conn.commit()
        logger.info("Database migrations applied successfully")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        conn.close()


def migrate_down(db_path: str) -> None:
    """Rollback migrations."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        tables_to_drop = [
            "offline_cache",
            "sync_status",
            "battery_stats",
            "edge_events",
            "edge_models",
            "webhook_deliveries"
        ]

        for table in tables_to_drop:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")

        conn.commit()
        logger.info("Database migrations rolled back")

    except Exception as e:
        conn.rollback()
        logger.error(f"Rollback failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python migrate.py [up|down]")
        sys.exit(1)

    direction = sys.argv[1]
    db_path = sys.argv[2] if len(sys.argv) > 2 else "backend/baupass.db"

    if direction == "up":
        migrate_up(db_path)
    elif direction == "down":
        migrate_down(db_path)
    else:
        print(f"Unknown migration direction: {direction}")
        sys.exit(1)
