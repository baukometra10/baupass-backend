"""
Reporting business logic — incremental extraction from server.py.

Next: move ``_operations_snapshot_for_user`` and ``reporting_summary`` SQL here.
"""
from __future__ import annotations


def operations_snapshot_for_user(db, user) -> dict:
    """Delegate to legacy implementation until SQL moves into this package."""
    from backend.server import _operations_snapshot_for_user

    return _operations_snapshot_for_user(db, user)
