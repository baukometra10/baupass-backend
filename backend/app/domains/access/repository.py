"""Access domain — gates, logs, geofences."""
from __future__ import annotations

from typing import Any


class AccessRepository:
    def recent_logs(self, db, company_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Recent access events (history), newest first."""
        rows = db.execute(
            """
            SELECT al.id, al.worker_id, al.direction, al.gate, al.timestamp, al.checked_in_late,
                   w.badge_id, w.first_name, w.last_name
            FROM access_logs al
            JOIN workers w ON w.id = al.worker_id
            WHERE w.company_id = ?
              AND NOT (
                  al.direction = 'check-out'
                  AND al.note = 'Automatischer Austritt nach 00:00'
                  AND (
                        al.timestamp LIKE '%T00:00:00%'
                     OR al.gate LIKE '%Tagesabschluss%'
                  )
              )
            ORDER BY al.timestamp DESC, al.id DESC
            LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def latest_logs_per_worker(self, db, company_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Latest check-in/out per worker only, newest activity first."""
        rows = db.execute(
            """
            SELECT id, worker_id, direction, gate, timestamp, checked_in_late,
                   badge_id, first_name, last_name
            FROM (
                SELECT al.id, al.worker_id, al.direction, al.gate, al.timestamp, al.checked_in_late,
                       w.badge_id, w.first_name, w.last_name,
                       ROW_NUMBER() OVER (
                           PARTITION BY al.worker_id
                           ORDER BY al.timestamp DESC, al.id DESC
                       ) AS row_no
                FROM access_logs al
                JOIN workers w ON w.id = al.worker_id
                WHERE w.company_id = ?
                  AND NOT (
                      al.direction = 'check-out'
                      AND al.note = 'Automatischer Austritt nach 00:00'
                      AND (
                            al.timestamp LIKE '%T00:00:00%'
                         OR al.gate LIKE '%Tagesabschluss%'
                      )
                  )
            ) latest
            WHERE row_no = 1
            ORDER BY timestamp DESC, id DESC
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
