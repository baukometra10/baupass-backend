"""Access domain — gates, logs, geofences."""
from __future__ import annotations

from typing import Any


class AccessRepository:
    def recent_logs(self, db, company_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = db.execute(
            """
            SELECT al.id, al.worker_id, al.direction, al.gate, al.timestamp, w.badge_id, w.first_name, w.last_name
            FROM access_logs al
            JOIN workers w ON w.id = al.worker_id
            WHERE w.company_id = ?
            ORDER BY al.timestamp DESC
            LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_geofences(self, db, company_id: str) -> list[dict[str, Any]]:
        rows = db.execute(
            "SELECT * FROM geofences WHERE company_id = ? ORDER BY site_name",
            (company_id,),
        ).fetchall()
        return [dict(r) for r in rows]
