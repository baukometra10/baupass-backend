"""
SQLite performance + stability pragmas (single place for tuning).
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def preferred_journal_mode(db_path: Path | str | None = None) -> str:
    """
    WAL is faster locally but often fails on Railway/network volumes (disk I/O error).
    Default to DELETE for /data persistent volumes unless overridden.
    """
    explicit = os.getenv("BAUPASS_SQLITE_JOURNAL_MODE", "").strip().upper()
    if explicit in {"WAL", "DELETE", "TRUNCATE", "PERSIST", "MEMORY", "OFF"}:
        return explicit

    candidates: list[str] = []
    if db_path is not None:
        candidates.append(str(db_path).replace("\\", "/"))
    env_path = os.getenv("BAUPASS_DB_PATH", "").strip().replace("\\", "/")
    if env_path:
        candidates.append(env_path)
    if Path("/data").is_dir():
        candidates.append("/data/baupass.db")

    for path in candidates:
        if path.startswith("/data/") or path == "/data/baupass.db":
            return "DELETE"
    return "WAL"


def recover_sqlite_disk_io(db_path: Path) -> bool:
    """Best-effort cleanup after SQLite disk I/O errors on persistent volumes."""
    recovered = False
    try:
        if db_path.is_file():
            with sqlite3.connect(str(db_path), timeout=5) as conn:
                try:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception:
                    pass
    except Exception:
        pass

    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = Path(f"{db_path}{suffix}")
        if not sidecar.is_file():
            continue
        try:
            sidecar.unlink()
            recovered = True
            print(f"[baupass] Removed SQLite sidecar after disk I/O error: {sidecar}", flush=True)
        except OSError:
            pass
    return recovered


def _safe_pragma(conn: sqlite3.Connection, sql: str) -> None:
    try:
        conn.execute(sql)
    except sqlite3.OperationalError:
        pass


def apply_sqlite_pragmas(conn: sqlite3.Connection, *, db_path: Path | str | None = None) -> None:
    """Apply journal mode and cache settings once per connection (never raises)."""
    journal_mode = preferred_journal_mode(db_path)
    _safe_pragma(conn, f"PRAGMA journal_mode={journal_mode}")
    _safe_pragma(
        conn,
        "PRAGMA synchronous=FULL" if journal_mode == "DELETE" else "PRAGMA synchronous=NORMAL",
    )
    _safe_pragma(conn, "PRAGMA foreign_keys=ON")
    busy_ms = int(os.getenv("BAUPASS_SQLITE_BUSY_TIMEOUT_MS", "60000"))
    cache_kb = int(os.getenv("BAUPASS_SQLITE_CACHE_KB", "64000"))
    mmap_mb = int(os.getenv("BAUPASS_SQLITE_MMAP_MB", "0"))
    _safe_pragma(conn, f"PRAGMA busy_timeout={max(1000, busy_ms)}")
    _safe_pragma(conn, f"PRAGMA cache_size=-{max(2000, cache_kb)}")
    _safe_pragma(conn, "PRAGMA temp_store=MEMORY")
    if mmap_mb > 0 and journal_mode != "DELETE":
        _safe_pragma(conn, f"PRAGMA mmap_size={mmap_mb * 1024 * 1024}")
