"""Clear large evidence blobs from old camera escalations. Keeps metadata/history."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from ._common import now_iso
from .camera_watch import DEFAULT_EVIDENCE_RETENTION_DAYS, get_watch_settings


def run_camera_evidence_retention(db) -> dict[str, Any]:
    """Null out public and clear evidence blobs older than company retention days."""
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
        try:
            rows = db.execute(
                """
                SELECT DISTINCT company_id FROM camera_escalations
                UNION
                SELECT DISTINCT company_id FROM site_cameras
                """
            ).fetchall()
        except Exception:
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
            from backend.app.platform.governance.legal_hold import company_has_active_legal_hold

            if company_has_active_legal_hold(db, cid, target_type="camera_evidence"):
                continue
            if company_has_active_legal_hold(db, cid):
                continue
        except Exception:
            pass
        try:
            cfg = get_watch_settings(db, cid)
            days = int(cfg.get("evidenceRetentionDays") or DEFAULT_EVIDENCE_RETENTION_DAYS)
            days = max(1, min(3650, days))
            cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            try:
                cur = db.execute(
                    """
                    UPDATE camera_escalations
                    SET snapshot_b64 = '', clip_b64 = '', snapshot_clear_b64 = '', clip_clear_b64 = ''
                    WHERE company_id = ?
                      AND created_at < ?
                      AND (
                        COALESCE(snapshot_b64, '') != ''
                        OR COALESCE(clip_b64, '') != ''
                        OR COALESCE(snapshot_clear_b64, '') != ''
                        OR COALESCE(clip_clear_b64, '') != ''
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
            try:
                cur_cam = db.execute(
                    """
                    UPDATE site_cameras
                    SET last_snapshot_clear_b64 = ''
                    WHERE company_id = ?
                      AND COALESCE(last_snapshot_at, '') < ?
                      AND COALESCE(last_snapshot_clear_b64, '') != ''
                    """,
                    (cid, cutoff),
                )
                db.commit()
                cleared += int(getattr(cur_cam, "rowcount", 0) or 0)
            except Exception:
                pass
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
