"""
PostgreSQL bootstrap from SQLite (/data/baupass.db) for Railway cutover.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

# Tables required before admin login / session bootstrap work.
CORE_SCHEMA_TABLES = frozenset(
    {
        "settings",
        "users",
        "sessions",
        "audit_logs",
        "companies",
        "workers",
        "invoices",
        "system_alerts",
    }
)

_schema_cache: dict[str, object] = {"at": 0.0, "missing": []}


def pg_runtime_flag_enabled() -> bool:
    """True when BAUPASS_PG_RUNTIME=1 and DATABASE_URL is postgres (ignores SQLite fallback)."""
    from backend.app.database import is_postgres_configured

    if not is_postgres_configured():
        return False
    flag = os.getenv("BAUPASS_PG_RUNTIME", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def existing_core_tables() -> set[str]:
    from backend.app.database import init_postgres_pool, postgres_connection

    init_postgres_pool()
    with postgres_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ANY(%s)
                """,
                (list(CORE_SCHEMA_TABLES),),
            )
            names = set()
            for row in cur.fetchall():
                if isinstance(row, dict):
                    names.add(row.get("table_name") or row.get("TABLE_NAME"))
                else:
                    names.add(row[0])
            return names


def find_sqlite_data_path() -> Path | None:
    """Locate a usable SQLite DB on Railway volume (main file or latest backup)."""
    candidates: list[Path] = []
    explicit = os.getenv("BAUPASS_PG_BOOTSTRAP_SQLITE_PATH", os.getenv("BAUPASS_DB_PATH", "")).strip()
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.append(Path("/data/baupass.db"))

    for path in candidates:
        try:
            if path.is_file() and path.stat().st_size > 4096:
                return path
        except OSError:
            continue

    backup_dir = Path("/data/backups")
    if backup_dir.is_dir():
        backups = sorted(
            backup_dir.glob("db-backup-*.db"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for backup in backups:
            try:
                if backup.is_file() and backup.stat().st_size > 4096:
                    return backup
            except OSError:
                continue
    return None


def missing_core_tables(*, force_refresh: bool = False) -> list[str]:
    if not pg_runtime_flag_enabled():
        return []
    now = time.monotonic()
    cached_at = float(_schema_cache.get("at") or 0)
    if not force_refresh and cached_at and (now - cached_at) < 30.0:
        return list(_schema_cache.get("missing") or [])
    existing = existing_core_tables()
    missing = sorted(CORE_SCHEMA_TABLES - existing)
    _schema_cache["at"] = now
    _schema_cache["missing"] = missing
    return missing


def core_schema_ready() -> bool:
    return len(missing_core_tables()) == 0


def is_schema_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in {"UndefinedTable", "UndefinedColumn"}:
        return True
    msg = str(exc).lower()
    return "does not exist" in msg and ("relation" in msg or "column" in msg)


def ensure_postgres_bootstrap() -> None:
    """If PG runtime is enabled and core tables are missing, migrate from SQLite."""
    auto = str(os.getenv("BAUPASS_PG_AUTO_BOOTSTRAP", "1")).strip().lower() in {"1", "true", "yes", "on"}
    if not auto or not pg_runtime_flag_enabled():
        return

    missing = missing_core_tables(force_refresh=True)
    if not missing:
        print("[baupass] PostgreSQL bootstrap: core schema present", flush=True)
        return

    source = os.getenv("BAUPASS_PG_BOOTSTRAP_SQLITE_PATH", os.getenv("BAUPASS_DB_PATH", "/data/baupass.db"))
    source_path = Path(source).expanduser()
    if not source_path.exists():
        raise RuntimeError(
            f"PostgreSQL tables missing ({missing}), "
            f"but bootstrap SQLite source not found: {source_path}"
        )

    from backend.ops.sqlite_to_postgres import migrate_sqlite_to_postgres

    truncate = str(os.getenv("BAUPASS_PG_BOOTSTRAP_TRUNCATE", "0")).strip().lower() in {"1", "true", "yes", "on"}
    result = migrate_sqlite_to_postgres(source_path, truncate=truncate, schema_only=False)
    _schema_cache["at"] = 0.0
    still_missing = missing_core_tables(force_refresh=True)
    if still_missing:
        raise RuntimeError(
            f"PostgreSQL bootstrap finished but tables still missing: {still_missing} "
            f"(migrated tables={result.get('tables')}, rows={result.get('rows')})"
        )
    print(
        f"[baupass] PostgreSQL bootstrap completed from {source_path} "
        f"(tables={result.get('tables')}, rows={result.get('rows')})",
        flush=True,
    )
