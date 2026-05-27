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
    if not db_path.is_file() or db_path.stat().st_size < 4096:
        from backend.app.db.pg_bootstrap import find_sqlite_data_path
        import shutil

        fallback = find_sqlite_data_path()
        if fallback and fallback != db_path:
            try:
                db_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fallback, db_path)
                print(f"[baupass] Restored SQLite DB from {fallback} → {db_path}", flush=True)
            except Exception as exc:
                print(f"[baupass] WARNING: could not restore SQLite from backup: {exc}", flush=True)
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
