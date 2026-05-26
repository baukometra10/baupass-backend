"""Workers domain — data access."""
from __future__ import annotations

from typing import Any


class WorkersRepository:
    def list_active(self, db, company_id: str, limit: int = 500) -> list[dict[str, Any]]:
        rows = db.execute(
            """
            SELECT id, badge_id, first_name, last_name, status, worker_type, site
            FROM workers
            WHERE company_id = ? AND deleted_at IS NULL
            ORDER BY last_name, first_name
            LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_id(self, db, company_id: str, worker_id: str) -> dict[str, Any] | None:
        row = db.execute(
            """
            SELECT * FROM workers
            WHERE id = ? AND company_id = ? AND deleted_at IS NULL
            """,
            (worker_id, company_id),
        ).fetchone()
        return dict(row) if row else None

    def count_on_site_today(self, db, company_id: str, today_prefix: str) -> int:
        row = db.execute(
            """
            SELECT COUNT(*) AS c
            FROM (
                SELECT al.worker_id, al.direction
                FROM access_logs al
                JOIN workers w ON w.id = al.worker_id
                WHERE w.company_id = ? AND w.deleted_at IS NULL AND al.timestamp LIKE ?
                  AND al.timestamp = (
                      SELECT MAX(al2.timestamp) FROM access_logs al2
                      WHERE al2.worker_id = al.worker_id AND al2.timestamp LIKE ?
                  )
            ) latest
            WHERE latest.direction = 'check-in'
            """,
            (company_id, f"{today_prefix}%", f"{today_prefix}%"),
        ).fetchone()
        return int((row["c"] if row else 0) or 0)
