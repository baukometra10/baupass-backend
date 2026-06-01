"""Periodic camera health checks — detect offline cameras and alert admins."""
from __future__ import annotations

import os
from typing import Any

from .camera_registry import CAMERA_ONLINE_THRESHOLD_SECONDS, camera_is_online, serialize_camera
from .camera_notifications import notify_camera_offline


def run_camera_health_check(db) -> dict[str, Any]:
    if str(os.getenv("BAUPASS_CAMERA_HEALTH_CHECK", "1")).strip().lower() in {"0", "false", "off", "no"}:
        return {"ok": True, "skipped": True}

    rows = db.execute(
        """
        SELECT * FROM site_cameras
        WHERE COALESCE(last_seen_at, '') != ''
        ORDER BY company_id, name
        """
    ).fetchall()

    checked = 0
    offline = 0
    alerts_sent = 0

    for row in rows:
        checked += 1
        cam = serialize_camera(row)
        if cam.get("online"):
            continue
        offline += 1
        if str(row["offline_alert_sent_at"] or "").strip():
            continue
        try:
            notify_camera_offline(
                db,
                company_id=str(row["company_id"]),
                camera_id=str(row["id"]),
                camera_name=str(row["name"] or row["id"]),
                location=str(row["location"] or ""),
                last_seen_at=str(row["last_seen_at"] or "") or None,
            )
            alerts_sent += 1
        except Exception:
            pass

    return {
        "ok": True,
        "checked": checked,
        "offline": offline,
        "alertsSent": alerts_sent,
        "thresholdSeconds": CAMERA_ONLINE_THRESHOLD_SECONDS,
    }
