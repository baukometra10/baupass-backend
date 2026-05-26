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
    is_postgres_configured,
    postgres_connection,
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
    if is_postgres_configured() and os.getenv("BAUPASS_USE_PG_ADAPTER", "1").strip() in {"1", "true", "yes"}:
        ensure_postgres_pool()
        with postgres_connection() as conn:
            yield conn
        return
    from backend.server import get_db

    yield get_db()


def health_snapshot() -> dict[str, Any]:
    return get_database_health()
