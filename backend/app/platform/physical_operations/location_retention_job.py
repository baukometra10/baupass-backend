"""Purge GPS trail samples older than company retention days."""
from __future__ import annotations

import os
from typing import Any

from backend.app.platform.physical_operations._common import now_iso
from backend.app.platform.physical_operations.location_trail import purge_old_location_samples
from backend.app.platform.workforce.location_privacy import gps_retention_days


def run_gps_location_retention(db) -> dict[str, Any]:
    if str(os.getenv("BAUPASS_GPS_RETENTION_JOB", "1")).strip().lower() in {
        "0",
        "false",
        "off",
        "no",
    }:
        return {"ok": True, "skipped": True, "reason": "disabled"}

    deleted = 0
    companies = 0
    errors = 0
    try:
        rows = db.execute("SELECT DISTINCT company_id FROM worker_location_samples").fetchall()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    for crow in rows:
        cid = str(crow["company_id"] or "").strip()
        if not cid:
            continue
        companies += 1
        try:
            days = gps_retention_days(db, cid)
            deleted += int(purge_old_location_samples(db, company_id=cid, retention_days=days) or 0)
            db.commit()
        except Exception:
            errors += 1
            try:
                db.rollback()
            except Exception:
                pass

    return {
        "ok": True,
        "companies": companies,
        "deleted": deleted,
        "errors": errors,
        "checkedAt": now_iso(),
    }
