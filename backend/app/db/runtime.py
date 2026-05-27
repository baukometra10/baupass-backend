"""
Request-scoped database runtime (SQLite default, PostgreSQL when enabled).
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from backend.app.database import init_postgres_pool, is_postgres_configured


def postgres_runtime_enabled() -> bool:
    """Use PostgreSQL for get_db() when DATABASE_URL is postgres and flag is on."""
    if not is_postgres_configured():
        return False
    flag = os.getenv("BAUPASS_PG_RUNTIME", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _resolve_sqlite_path() -> Path:
    explicit = os.getenv("BAUPASS_DB_PATH", "").strip().replace("\\", "/")
    if explicit:
        return Path(explicit).expanduser()
    data = Path("/data/baupass.db")
    if data.parent.is_dir() and os.access(data.parent, os.W_OK):
        return data
    base = Path(__file__).resolve().parents[2]
    return base / "baupass.db"


def open_request_db() -> Any:
    """Open DB for current Flask request (caller stores on flask.g)."""
    if postgres_runtime_enabled():
        if not init_postgres_pool():
            raise RuntimeError("PostgreSQL pool failed to initialize (check DATABASE_URL)")
        from backend.app.database import _pg_pool

        if _pg_pool is None:
            raise RuntimeError("PostgreSQL pool is not available")
        cm = _pg_pool.connection()
        raw = cm.__enter__()
        from .pg_adapter import PgConnection

        return PgConnection(raw, pool_cm=cm)

    db_path = _resolve_sqlite_path()
    conn = sqlite3.connect(db_path, timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        from backend.app.core.sqlite_pragmas import apply_sqlite_pragmas

        apply_sqlite_pragmas(conn)
    except Exception:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=60000")
    return conn


def close_request_db(db: Any) -> None:
    if db is not None:
        db.close()
