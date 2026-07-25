"""Clear large evidence blobs from old camera escalations. Keeps metadata/history."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from ._common import now_iso
from .camera_watch import DEFAULT_EVIDENCE_RETENTION_DAYS, get_watch_settings


def run_camera_evidence_retention(db) -> dict[str, Any]:
    """Null out snapshot_b64/clip_b64 on escalations older than company retention days."""
    if str(os.getenv("BAUPASS_CAMERA_EVIDENCE_JOB", "1")).strip().lower() in {
        "0",
        "false",
        "off",
        "no",
    }:
        return {"ok": True, "skipped": True, "reason": "disabled", "autoDial": False}

    cleared = 0
    companies = 0
    errors = 0
    try:
        rows = db.execute(
            "SELECT DISTINCT company_id FROM camera_escalations"
        ).fetchall()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "autoDial": False}

    now = datetime.now(timezone.utc)
    for crow in rows:
        cid = str(crow["company_id"] or "").strip()
        if not cid:
            continue
        companies += 1
        try:
            cfg = get_watch_settings(db, cid)
            days = int(cfg.get("evidenceRetentionDays") or DEFAULT_EVIDENCE_RETENTION_DAYS)
            days = max(1, min(3650, days))
            cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            try:
                cur = db.execute(
                    """
                    UPDATE camera_escalations
                    SET snapshot_b64 = '', clip_b64 = ''
                    WHERE company_id = ?
                      AND created_at < ?
                      AND (
                        COALESCE(snapshot_b64, '') != ''
                        OR COALESCE(clip_b64, '') != ''
                      )
                    """,
                    (cid, cutoff),
                )
            except Exception:
                cur = db.execute(
                    """
                    UPDATE camera_escalations
                    SET snapshot_b64 = ''
                    WHERE company_id = ?
                      AND created_at < ?
                      AND COALESCE(snapshot_b64, '') != ''
                    """,
                    (cid, cutoff),
                )
            db.commit()
            cleared += int(getattr(cur, "rowcount", 0) or 0)
        except Exception:
            errors += 1

    return {
        "ok": True,
        "companies": companies,
        "cleared": cleared,
        "errors": errors,
        "autoDial": False,
        "checkedAt": now_iso(),
    }
