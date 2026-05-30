"""Payroll and compliance aggregates for operational PDF reports."""
from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any


def build_hr_compliance_snapshot(db, company_id: str) -> dict[str, Any]:
    """Lohn + Compliance KPIs for one company (used in PDF/guidance)."""
    from backend.server import now_iso, utc_now

    company_id = str(company_id or "").strip()
    if not company_id:
        return {}

    today = utc_now().date()
    today_s = today.isoformat()
    soon_s = (today + timedelta(days=14)).isoformat()
    month_prefix = now_iso()[:7]

    workers_row = db.execute(
        """
        SELECT COUNT(*) AS c
        FROM workers
        WHERE company_id = ?
          AND deleted_at IS NULL
        """,
        (company_id,),
    ).fetchone()
    workers_total = int(workers_row["c"] or 0)

    expired_row = db.execute(
        """
        SELECT COUNT(DISTINCT wd.worker_id) AS c
        FROM worker_documents wd
        JOIN workers w ON w.id = wd.worker_id
        WHERE w.company_id = ?
          AND w.deleted_at IS NULL
          AND COALESCE(wd.expiry_date, '') != ''
          AND DATE(wd.expiry_date) < DATE('now')
        """,
        (company_id,),
    ).fetchone()
    workers_with_expired_docs = int(expired_row["c"] or 0)

    expiring_row = db.execute(
        """
        SELECT COUNT(DISTINCT wd.worker_id) AS c
        FROM worker_documents wd
        JOIN workers w ON w.id = wd.worker_id
        WHERE w.company_id = ?
          AND w.deleted_at IS NULL
          AND COALESCE(wd.expiry_date, '') != ''
          AND DATE(wd.expiry_date) >= DATE('now')
          AND DATE(wd.expiry_date) <= DATE(?)
        """,
        (company_id, soon_s),
    ).fetchone()
    workers_expiring_14d = int(expiring_row["c"] or 0)

    payroll_row = db.execute(
        """
        SELECT COUNT(*) AS c
        FROM worker_documents wd
        JOIN workers w ON w.id = wd.worker_id
        WHERE w.company_id = ?
          AND w.deleted_at IS NULL
          AND wd.doc_type IN ('lohnabrechnung', 'gehaltsabrechnung')
          AND substr(wd.created_at, 1, 7) = ?
        """,
        (company_id, month_prefix),
    ).fetchone()
    payroll_docs_this_month = int(payroll_row["c"] or 0)

    missing_required = 0
    required_types = ("mindestlohnnachweis", "personalausweis")
    worker_ids = db.execute(
        "SELECT id FROM workers WHERE company_id = ? AND deleted_at IS NULL",
        (company_id,),
    ).fetchall()
    placeholders = ", ".join("?" for _ in required_types)
    for row in worker_ids:
        wid = str(row["id"])
        latest = db.execute(
            f"""
            SELECT wd.doc_type, wd.expiry_date
            FROM worker_documents wd
            JOIN (
                SELECT doc_type, MAX(created_at) AS latest_created_at
                FROM worker_documents
                WHERE worker_id = ?
                  AND doc_type IN ({placeholders})
                GROUP BY doc_type
            ) latest ON latest.doc_type = wd.doc_type AND latest.latest_created_at = wd.created_at
            WHERE wd.worker_id = ?
            """,
            (wid, *required_types, wid),
        ).fetchall()
        have = {str(r["doc_type"] or "").lower() for r in latest}
        if any(rt not in have for rt in required_types):
            missing_required += 1
            continue
        for r in latest:
            exp = str(r["expiry_date"] or "").strip()
            if exp and exp < today_s:
                missing_required += 1
                break

    inbox_unread = 0
    try:
        inbox_row = db.execute(
            """
            SELECT COUNT(*) AS c
            FROM email_inbox
            WHERE matched_company_id = ?
              AND COALESCE(is_read, 0) = 0
            """,
            (company_id,),
        ).fetchone()
        inbox_unread = int(inbox_row["c"] or 0)
    except Exception:
        inbox_unread = 0

    datev_row = db.execute(
        """
        SELECT status FROM integration_connections
        WHERE company_id = ? AND provider = 'datev'
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (company_id,),
    ).fetchone()
    datev_status = str(datev_row["status"] or "") if datev_row else ""

    period_label = month_prefix
    return {
        "period": period_label,
        "workersTotal": workers_total,
        "workersWithExpiredDocs": workers_with_expired_docs,
        "workersExpiringDocs14d": workers_expiring_14d,
        "workersMissingRequiredDocs": missing_required,
        "payrollDocsThisMonth": payroll_docs_this_month,
        "inboxUnread": inbox_unread,
        "datevConnected": datev_status.lower() in {"connected", "active", "ok"},
        "datevStatus": datev_status or "not_connected",
    }
