"""Billing domain repository."""
from __future__ import annotations

from typing import Any


class BillingRepository:
    def invoice_summary(self, db, company_id: str) -> dict[str, Any]:
        row = db.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) AS paid,
                SUM(CASE WHEN status IN ('sent','overdue') THEN 1 ELSE 0 END) AS open_count
            FROM invoices
            WHERE company_id = ?
            """,
            (company_id,),
        ).fetchone()
        return dict(row) if row else {"total": 0, "paid": 0, "open_count": 0}

    def recent_invoices(self, db, company_id: str, limit: int = 20) -> list[dict]:
        rows = db.execute(
            """
            SELECT id, status, invoice_date, invoice_period, total_amount
            FROM invoices
            WHERE company_id = ?
            ORDER BY invoice_date DESC
            LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
