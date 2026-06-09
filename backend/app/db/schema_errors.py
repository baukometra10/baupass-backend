"""Helpers for API responses when the database schema is not ready."""
from __future__ import annotations

from flask import jsonify

from backend.app.db.pg_bootstrap import missing_core_tables, pg_runtime_flag_enabled


def database_not_ready_response(*, ok_field: bool = False):
    missing = missing_core_tables()
    message = (
        "Datenbank-Schema ist unvollständig. "
        "Setze BAUPASS_PG_RUNTIME=0 mit BAUPASS_DB_PATH=/data/baupass.db "
        "oder führe sqlite_to_postgres.py aus."
    )
    if missing:
        message += f" Fehlende Tabellen: {', '.join(missing)}."
    else:
        try:
            from backend.app.db.runtime import _resolve_sqlite_path

            db_path = _resolve_sqlite_path()
            message += f" SQLite-Prüfung fehlgeschlagen für {db_path}."
        except Exception:
            pass
    payload = {
        "error": "database_not_ready",
        "message": message,
        "missingTables": missing,
    }
    if ok_field:
        payload["ok"] = False
    return jsonify(payload), 503


def guard_core_schema(*, ok_field: bool = False):
    """
    Block auth only when PostgreSQL runtime is explicitly enabled but schema is incomplete.
    SQLite uses init_db() at startup — do not reject login on flaky read probes.
    """
    from backend.app.db.runtime import postgres_runtime_enabled

    if postgres_runtime_enabled():
        if not missing_core_tables():
            return None
        return database_not_ready_response(ok_field=ok_field)

    if pg_runtime_flag_enabled():
        # PG flag on but runtime fell back to SQLite — do not block on PG missing tables.
        return None

    try:
        from backend.app.db.runtime import _resolve_sqlite_path

        db_path = _resolve_sqlite_path()
        if db_path.is_file() and db_path.stat().st_size >= 4096:
            return None
    except Exception:
        pass
    return database_not_ready_response(ok_field=ok_field)
