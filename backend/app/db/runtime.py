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
    from backend.app.db.pg_bootstrap import find_sqlite_data_path, missing_core_tables, pg_runtime_flag_enabled

    if not pg_runtime_flag_enabled():
        return False

    auto_sqlite = str(os.getenv("BAUPASS_PG_AUTO_SQLITE_FALLBACK", "1")).strip().lower()
    if auto_sqlite in {"0", "false", "no", "off"}:
        return True

    try:
        missing = missing_core_tables()
        if missing and find_sqlite_data_path() is not None:
            print(
                "[baupass] PostgreSQL schema incomplete "
                f"({', '.join(missing)}) — auto-using SQLite on /data. "
                "Set BAUPASS_PG_RUNTIME=0 to disable Postgres entirely.",
                flush=True,
            )
            return False
    except Exception as exc:
        print(f"[baupass] WARNING: PG/SQLite fallback check failed: {exc}", flush=True)

    return True


def postgres_runtime_required() -> bool:
    """If enabled, fail fast when runtime is not actually on PostgreSQL."""
    flag = os.getenv("BAUPASS_PG_REQUIRED", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _resolve_sqlite_path() -> Path:
    """Use the same resolved DB path as server.py (Railway /data volume override)."""
    try:
        import backend.server as srv

        return Path(srv.DB_PATH)
    except Exception:
        pass

    explicit = os.getenv("BAUPASS_DB_PATH", "").strip().replace("\\", "/")
    _ephemeral_db_hints = {
        "",
        "backend/baupass.db",
        "/app/backend/baupass.db",
    }
    railway_data = Path("/data")
    railway_candidate = railway_data / "baupass.db"
    if railway_data.is_dir() and os.access(railway_data, os.W_OK):
        if explicit in _ephemeral_db_hints or not explicit.startswith("/data/"):
            return railway_candidate
    if explicit:
        return Path(explicit).expanduser()
    if railway_candidate.parent.is_dir() and os.access(railway_candidate.parent, os.W_OK):
        return railway_candidate
    base = Path(__file__).resolve().parents[2]
    return base / "baupass.db"


def open_request_db() -> Any:
    """Open DB for current Flask request (caller stores on flask.g)."""
    if postgres_runtime_required() and not postgres_runtime_enabled():
        raise RuntimeError("BAUPASS_PG_REQUIRED=1 but PostgreSQL runtime is disabled")
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
    from backend.app.db.sqlite_recovery import ensure_usable_sqlite_path

    db_path = ensure_usable_sqlite_path(db_path)
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
