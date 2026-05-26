"""Notifications domain repository."""
from __future__ import annotations

from typing import Any


class NotificationsRepository:
    def list_for_company(self, db, company_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = db.execute(
            """
            SELECT id, type, title, message, read_at, created_at
            FROM notifications
            WHERE company_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
