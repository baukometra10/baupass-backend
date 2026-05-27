"""
Readiness checks for load balancers (Railway, K8s, uptime monitors).
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from flask import Flask


def _redis_status() -> dict[str, Any]:
    require = os.getenv("BAUPASS_REQUIRE_REDIS", "0").strip().lower() in {"1", "true", "yes"}
    try:
        from backend.app.extensions import get_redis

        client = get_redis()
        if not client:
            status = "not_configured"
            ok = not require
        else:
            client.ping()
            status = "ok"
            ok = True
    except Exception as exc:
        status = f"error:{exc}"
        ok = not require
    return {"ok": ok, "status": status, "required": require}


def _database_status(db_path: Path) -> dict[str, Any]:
    try:
        from backend.app.db.runtime import postgres_runtime_enabled
        from backend.app.database import get_database_health, init_postgres_pool, postgres_connection

        if postgres_runtime_enabled():
            health = get_database_health()
            ok = health.get("status") == "ok"
            tables_ok = False
            if ok:
                init_postgres_pool()
                with postgres_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT 1 FROM information_schema.tables WHERE table_name = 'companies' LIMIT 1"
                        )
                        tables_ok = cur.fetchone() is not None
            return {
                "ok": ok and tables_ok,
                "backend": "postgres",
                "companiesTable": tables_ok,
                "health": health,
                "readReplica": health.get("read_replica", {}),
            }
        with sqlite3.connect(str(db_path), timeout=3) as conn:
            conn.execute("SELECT 1").fetchone()
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
        return {"ok": True, "backend": "sqlite", "migrationsTable": bool(row), "path": str(db_path)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "path": str(db_path)}


def _blueprint_status(flask_app: Flask) -> dict[str, Any]:
    groups = flask_app.extensions.get("modular_blueprints") or []
    failed = [g for g in groups if g.get("status") != "ok"]
    platform_off = os.getenv("BAUPASS_PLATFORM_ENABLED", "1").strip().lower() in {"0", "false", "no"}
    ok = len(failed) == 0 or platform_off
    return {"ok": ok, "groups": groups, "failedCount": len(failed)}


def _queue_status() -> dict[str, Any]:
    try:
        from backend.app.tasks import get_queue_stats, task_queues_ready

        ready = task_queues_ready()
        stats = get_queue_stats() if ready else {}
        return {"ok": True, "ready": ready, "stats": stats}
    except Exception as exc:
        return {"ok": True, "ready": False, "error": str(exc)}


def collect_readiness(flask_app: Flask, db_path: Path) -> dict[str, Any]:
    checks = {
        "database": _database_status(db_path),
        "redis": _redis_status(),
        "blueprints": _blueprint_status(flask_app),
        "queues": _queue_status(),
    }
    ready = checks["database"].get("ok") and checks["blueprints"].get("ok")
    if checks["redis"].get("required"):
        ready = ready and checks["redis"].get("ok")
    return {"ready": ready, "checks": checks}
