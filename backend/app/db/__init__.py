"""Unified database access (SQLite + PostgreSQL transition)."""
from .connection import get_connection, is_using_postgres
from .runtime import postgres_runtime_enabled

__all__ = ["get_connection", "is_using_postgres", "postgres_runtime_enabled"]
