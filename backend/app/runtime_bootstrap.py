"""
SUPPIX – Runtime integration for legacy server.py
===================================================
Wires migrations, distributed rate limiting, and security middleware
into the monolithic Flask app without replacing server.py yet.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

from flask import Flask

logger = logging.getLogger("baupass.bootstrap")

# Maps server.py rate-limit scope names to shared limiter scope keys.
LEGACY_RATE_SCOPE_MAP: dict[str, str] = {
    "import": "admin_api",
    "login": "auth_login",
    "worker_login": "auth_login",
    "worker_api": "worker_api",
    "worker_api_auth_fail": "worker_api_auth_fail",
    "password_reset": "auth_login",
}


def apply_sqlite_migrations(db_path: Path) -> list[str]:
    """Apply pending schema migrations to the SQLite database."""
    skip = os.getenv("BAUPASS_SKIP_MIGRATIONS", "").strip().lower()
    if skip in {"1", "true", "yes", "on"}:
        return []

    from backend.app.database import MigrationRunner
    from backend.app.migrations import ALL_MIGRATIONS

    conn = sqlite3.connect(str(db_path), timeout=60)
    conn.row_factory = sqlite3.Row
    try:
        try:
            from backend.app.core.sqlite_pragmas import apply_sqlite_pragmas

            apply_sqlite_pragmas(conn, db_path=db_path)
        except Exception:
            conn.executescript("PRAGMA journal_mode = DELETE; PRAGMA foreign_keys = ON;")
        runner = MigrationRunner(conn)
        return runner.run(ALL_MIGRATIONS)
    finally:
        conn.close()


def build_rate_limit_scopes(legacy_limits: dict[str, dict[str, int]]) -> dict[str, tuple[int, int]]:
    """Merge server.py limits with factory defaults (server limits win per scope)."""
    from backend.app.config import BaseConfig

    scopes: dict[str, tuple[int, int]] = dict(BaseConfig.RATE_LIMIT_SCOPES)
    for legacy_scope, rule in legacy_limits.items():
        mapped = LEGACY_RATE_SCOPE_MAP.get(legacy_scope, legacy_scope)
        max_req = int(rule.get("max") or 0)
        window = int(rule.get("window_seconds") or 60)
        if max_req > 0 and window > 0:
            scopes[mapped] = (max_req, window)
    return scopes


def integrate_server_runtime(
    flask_app: Flask,
    db_path: Path,
    legacy_rate_limits: Optional[dict[str, dict[str, int]]] = None,
) -> dict[str, Any]:
    """
    Apply enterprise runtime pieces to the legacy Flask app.

    Returns a short summary dict for startup logging.
    """
    summary: dict[str, Any] = {
        "migrations": [],
        "rate_limiter": "legacy",
        "security": False,
    }
    flask_app.extensions["runtime_summary"] = summary

    if db_path.suffix.lower() == ".db":
        try:
            applied = apply_sqlite_migrations(db_path)
            summary["migrations"] = applied
            if applied:
                print(
                    f"[baupass] Applied {len(applied)} schema migration(s): {', '.join(applied)}",
                    flush=True,
                )
        except Exception as exc:
            print(f"[baupass] WARNING: schema migrations failed: {exc}", flush=True)
            logger.exception("Schema migration failed")

    from backend.app.config import BaseConfig
    from backend.app.extensions import init_extensions
    from backend.app.middleware.rate_limiting import build_rate_limiter
    from backend.app.middleware.security import register_security_middleware

    flask_app.config.setdefault("RATE_LIMIT_ENABLED", True)
    flask_app.config.setdefault("REDIS_URL", os.getenv("REDIS_URL", BaseConfig.REDIS_URL))
    flask_app.config["RATE_LIMIT_SCOPES"] = build_rate_limit_scopes(legacy_rate_limits or {})

    init_extensions(flask_app)
    build_rate_limiter(flask_app)
    register_security_middleware(flask_app)

    try:
        from backend.app.middleware.edge_global import register_global_edge_middleware

        register_global_edge_middleware(flask_app)
        summary["edge_middleware"] = True
    except Exception as exc:
        print(f"[baupass] WARNING: global edge middleware skipped: {exc}", flush=True)
        summary["edge_middleware"] = False

    from backend.app.tasks import init_task_queues, task_queues_ready

    redis_url = str(flask_app.config.get("REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
    tasks_ok = init_task_queues(redis_url)
    summary["task_queues"] = "redis" if tasks_ok else "sync"
    flask_app.extensions["task_queues_ready"] = bool(tasks_ok)

    flask_app.extensions["rate_limit_legacy_map"] = LEGACY_RATE_SCOPE_MAP
    summary["rate_limiter"] = "redis" if flask_app.extensions.get("redis") else "memory"
    summary["security"] = True
    return summary


def resolve_background_job_mode(env_name: str, default: str = "auto") -> str:
    """
    Resolve background job transport mode.

    - auto (default): rq when Redis task queues are ready, otherwise thread
    - rq / thread: explicit override
    """
    mode = os.getenv(env_name, default).strip().lower()
    if mode != "auto":
        return mode

    try:
        from backend.app.tasks import task_queues_ready

        return "rq" if task_queues_ready() else "thread"
    except Exception:
        return "thread"
