"""Unified database access (SQLite + PostgreSQL transition)."""
from .connection import get_connection, is_using_postgres

__all__ = ["get_connection", "is_using_postgres"]
