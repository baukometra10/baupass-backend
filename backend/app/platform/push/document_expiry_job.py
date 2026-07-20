"""Daily FCM reminders for expiring worker documents (hybrid app)."""
from __future__ import annotations

from typing import Any


def run_daily_document_expiry_fcm(db, *, horizon_days: int = 14) -> dict[str, Any]:
    """
    Push workers whose documents expire within horizon_days.
    One push per document per Berlin calendar day (dedup via system_alerts code).
    """
    from backend.app.platform.physical_operations._common import calendar_day_offset, today_prefix

    from .automation import push_document_expiry

    today = today_prefix()
    horizon = calendar_day_offset(horizon_days)
    rows = db.execute(
        """
        SELECT wd.id AS doc_id, wd.doc_type, wd.expiry_date, wd.worker_id, w.company_id
        FROM worker_documents wd
        JOIN workers w ON w.id = wd.worker_id
        WHERE wd.expiry_date IS NOT NULL
          AND wd.expiry_date <= ?
          AND wd.expiry_date >= ?
          AND w.deleted_at IS NULL
        ORDER BY wd.expiry_date ASC
        LIMIT 500
        """,
        (horizon, today),
    ).fetchall()

    sent = 0
    skipped = 0
    errors = 0
    for r in rows:
        doc_id = str(r["doc_id"])
        code = f"fcm_doc_expiry_{doc_id}_{today}"
        try:
            existing = db.execute("SELECT id FROM system_alerts WHERE code = ?", (code,)).fetchone()
            if existing:
                skipped += 1
                continue
        except Exception:
            pass

        doc_type = str(r["doc_type"] or "Dokument").replace("_", " ")
        expiry = str(r["expiry_date"] or "")
        try:
            delivery = push_document_expiry(
                db,
                worker_id=str(r["worker_id"]),
                company_id=r["company_id"],
                doc_type=doc_type,
                expiry_date=expiry,
            )
            if int(delivery.get("pushSent") or 0) > 0:
                sent += 1
                try:
                    from backend.server import create_system_alert

                    create_system_alert(
                        db,
                        code=code,
                        severity="info",
                        message=f"FCM Dokument-Ablauf an MA {r['worker_id']}: {doc_type} bis {expiry}",
                        details={"docId": doc_id, "workerId": r["worker_id"]},
                        dedup_minutes=60 * 24,
                    )
                    db.commit()
                except Exception:
                    pass
            else:
                skipped += 1
        except Exception:
            errors += 1

    return {
        "ok": True,
        "checked": len(rows),
        "pushSent": sent,
        "skipped": skipped,
        "errors": errors,
        "horizonDays": horizon_days,
    }
