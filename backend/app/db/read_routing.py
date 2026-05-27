"""
Helpers to route read-heavy code paths to replica when configured.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator


@contextmanager
def read_db() -> Generator[Any, None, None]:
    """Yield a read-optimized DB connection (replica on PostgreSQL when available)."""
    from .connection import get_read_connection

    with get_read_connection() as conn:
        yield conn


def analytics_db() -> Any:
    """Convenience for analytics handlers (use as context manager in caller)."""
    return read_db()
