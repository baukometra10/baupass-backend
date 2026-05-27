"""
Unified DB connection for domain/platform code.

Legacy server.py still uses sqlite get_db(); new modules should use get_connection().
When DATABASE_URL is PostgreSQL, returns a psycopg connection from the pool.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Generator

from backend.app.database import (
    get_database_health,
    init_postgres_pool,
    init_postgres_read_pool,
    is_postgres_configured,
    postgres_connection,
    postgres_read_connection,
)


def is_using_postgres() -> bool:
    return is_postgres_configured()


def ensure_postgres_pool(config: dict[str, Any] | None = None) -> bool:
    if not is_postgres_configured(config):
        return False
    return init_postgres_pool(config)


@contextmanager
def get_connection() -> Generator[Any, None, None]:
    """Yield sqlite (server) or postgres connection."""
    from backend.app.db.runtime import postgres_runtime_enabled, open_request_db, close_request_db

    if postgres_runtime_enabled():
        conn = open_request_db()
        try:
            yield conn
        finally:
            close_request_db(conn)
        return
    from backend.server import get_db

    yield get_db()


@contextmanager
def get_read_connection() -> Generator[Any, None, None]:
    """Yield read-optimized connection (replica if configured)."""
    from backend.app.db.runtime import postgres_runtime_enabled

    if postgres_runtime_enabled():
        from backend.app.db.pg_adapter import PgConnection

        init_postgres_read_pool()
        with postgres_read_connection() as conn:
            yield PgConnection(conn)
        return
    from backend.server import get_db

    yield get_db()


def health_snapshot() -> dict[str, Any]:
    return get_database_health()
