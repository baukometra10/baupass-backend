"""
Payroll integration adapter (structured export; extend per vendor).
"""
from __future__ import annotations

from typing import Any


def payroll_export_preview(db, company_id: int, *, period: str = "") -> dict[str, Any]:
    rows = db.execute(
        """
        SELECT w.id, w.first_name, w.last_name, w.badge_id, w.status,
               COUNT(al.id) AS access_events
        FROM workers w
        LEFT JOIN access_logs al ON al.worker_id = w.id
            AND (? = '' OR substr(al.timestamp, 1, 7) = ?)
        WHERE w.company_id = ? AND w.deleted_at IS NULL
        GROUP BY w.id
        ORDER BY w.last_name, w.first_name
        LIMIT 500
        """,
        (period, period, company_id),
    ).fetchall()
    return {
        "ok": True,
        "provider": "payroll",
        "period": period or "all",
        "rows": [dict(r) for r in rows],
        "format": "baupass_payroll_v1",
        "note": "Connect DATEV/SAP payroll via custom mapping when vendor credentials are configured",
    }
