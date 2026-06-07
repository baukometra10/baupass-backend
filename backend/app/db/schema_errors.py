"""Helpers for API responses when the database schema is not ready."""
from __future__ import annotations

from flask import jsonify

from backend.app.db.pg_bootstrap import core_schema_ready, is_schema_error, missing_core_tables


def database_not_ready_response(*, ok_field: bool = False):
    missing = missing_core_tables()
    message = (
        "Datenbank-Schema ist unvollständig. "
        "Setze BAUPASS_PG_RUNTIME=0 mit BAUPASS_DB_PATH=/data/baupass.db "
        "oder führe sqlite_to_postgres.py aus."
    )
    if missing:
        message += f" Fehlende Tabellen: {', '.join(missing)}."
    payload = {
        "error": "database_not_ready",
        "message": message,
        "missingTables": missing,
    }
    if ok_field:
        payload["ok"] = False
    return jsonify(payload), 503


def guard_core_schema(*, ok_field: bool = False):
    from backend.app.db.runtime import postgres_runtime_enabled

    if postgres_runtime_enabled():
        if not missing_core_tables():
            return None
        return database_not_ready_response(ok_field=ok_field)

    try:
        from backend.app.db.runtime import _resolve_sqlite_path
        from backend.app.db.sqlite_recovery import sqlite_core_tables_ok

        db_path = _resolve_sqlite_path()
        if not sqlite_core_tables_ok(db_path):
            return database_not_ready_response(ok_field=ok_field)
    except Exception:
        return database_not_ready_response(ok_field=ok_field)
    return None
