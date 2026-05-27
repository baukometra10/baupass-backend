"""
Disaster recovery and backup posture checks.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse_iso(ts: str) -> datetime | None:
    raw = (ts or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _sqlite_backup_status(db_path: Path) -> dict[str, Any]:
    backup_dirs = []
    data_backups = Path("/data/backups")
    if data_backups.is_dir():
        backup_dirs.append(data_backups)
    local_backups = db_path.parent / "backups"
    if local_backups.is_dir():
        backup_dirs.append(local_backups)
    backend_backups = Path(__file__).resolve().parents[2] / "backups"
    if backend_backups.is_dir():
        backup_dirs.append(backend_backups)

    latest_path = None
    latest_mtime = None
    for directory in backup_dirs:
        for pattern in ("db-backup-*.db", "baupass-*.sqlite3"):
            for candidate in directory.glob(pattern):
                mtime = candidate.stat().st_mtime
                if latest_mtime is None or mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_path = candidate

    max_age_hours = int(os.getenv("BAUPASS_DR_MAX_BACKUP_AGE_HOURS", "48"))
    if latest_path is None:
        return {"ok": False, "status": "no_backup_found", "maxAgeHours": max_age_hours}

    age_hours = (datetime.now(timezone.utc).timestamp() - latest_mtime) / 3600.0
    ok = age_hours <= max_age_hours
    return {
        "ok": ok,
        "status": "ok" if ok else "stale",
        "latestBackup": str(latest_path),
        "ageHours": round(age_hours, 2),
        "maxAgeHours": max_age_hours,
    }


def _postgres_dr_status() -> dict[str, Any]:
    from backend.app.database import get_database_health, is_postgres_replica_configured
    from backend.app.db.pg_bootstrap import core_schema_ready, missing_core_tables

    health = get_database_health()
    missing = missing_core_tables(force_refresh=True)
    schema_ok = core_schema_ready()
    primary_ok = health.get("status") == "ok" and schema_ok
    replica = health.get("read_replica", {})
    replica_ok = replica.get("status") in {"ok", "skipped"}
    require_replica = os.getenv("BAUPASS_DR_REQUIRE_REPLICA", "0").strip().lower() in {"1", "true", "yes"}
    if require_replica and is_postgres_replica_configured():
        replica_ok = replica.get("status") == "ok"

    ok = primary_ok and replica_ok and not missing
    return {
        "ok": ok,
        "status": "ok" if ok else "degraded",
        "primary": health,
        "readReplica": replica,
        "missingCoreTables": missing,
        "requireReplica": require_replica,
    }


def collect_dr_status(db_path: Path) -> dict[str, Any]:
    sqlite_backup = _sqlite_backup_status(db_path)
    try:
        from backend.app.db.runtime import postgres_runtime_enabled

        if postgres_runtime_enabled():
            postgres = _postgres_dr_status()
            require_sqlite_backup = os.getenv("BAUPASS_DR_REQUIRE_SQLITE_BACKUP", "0").strip().lower() in {
                "1",
                "true",
                "yes",
            }
            sqlite_ok = sqlite_backup.get("ok") if require_sqlite_backup else True
            ok = bool(postgres.get("ok")) and sqlite_ok
            return {
                "ok": ok,
                "mode": "postgres",
                "sqliteBackup": sqlite_backup,
                "sqliteBackupRequired": require_sqlite_backup,
                "postgres": postgres,
            }
    except Exception as exc:
        return {"ok": False, "mode": "unknown", "error": str(exc)}

    # SQLite-only production path
    try:
        with sqlite3.connect(str(db_path), timeout=3) as conn:
            conn.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception as exc:
        db_ok = False
        return {"ok": False, "mode": "sqlite", "database": {"ok": False, "error": str(exc)}, "sqliteBackup": sqlite_backup}

    ok = db_ok and sqlite_backup.get("ok")
    return {"ok": ok, "mode": "sqlite", "database": {"ok": db_ok}, "sqliteBackup": sqlite_backup}
