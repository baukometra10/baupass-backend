"""
SQLite performance + stability pragmas (single place for tuning).
"""
from __future__ import annotations

import os
import sqlite3


def apply_sqlite_pragmas(conn: sqlite3.Connection) -> None:
    """Apply WAL and cache settings once per connection."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    busy_ms = int(os.getenv("BAUPASS_SQLITE_BUSY_TIMEOUT_MS", "60000"))
    cache_kb = int(os.getenv("BAUPASS_SQLITE_CACHE_KB", "64000"))
    mmap_mb = int(os.getenv("BAUPASS_SQLITE_MMAP_MB", "256"))
    conn.execute(f"PRAGMA busy_timeout={max(1000, busy_ms)}")
    conn.execute(f"PRAGMA cache_size=-{max(2000, cache_kb)}")
    conn.execute(f"PRAGMA temp_store=MEMORY")
    if mmap_mb > 0:
        conn.execute(f"PRAGMA mmap_size={mmap_mb * 1024 * 1024}")
