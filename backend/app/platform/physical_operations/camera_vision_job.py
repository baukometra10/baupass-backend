"""After-hours snapshot polling + vision analysis job."""
from __future__ import annotations

import os
from typing import Any

from .camera_registry import camera_is_online, get_camera_snapshot_b64, list_cameras
from .camera_vision import analyze_snapshot_b64, vision_enabled, vision_result_to_event_payload
from .camera_watch import (
    is_after_hours,
    mark_dedup_alert,
    should_dedup_alert,
    watch_status,
)


def run_camera_after_hours_vision(db) -> dict[str, Any]:
    if str(os.getenv("BAUPASS_CAMERA_VISION_JOB", "1")).strip().lower() in {"0", "false", "off", "no"}:
        return {"ok": True, "skipped": True, "reason": "disabled"}
    heuristic_ok = str(os.getenv("BAUPASS_CAMERA_VISION_HEURISTIC", "1")).strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }
    if not vision_enabled() and not heuristic_ok:
        return {"ok": True, "skipped": True, "reason": "vision_not_configured"}

    from .camera_ai import ingest_camera_event

    companies = db.execute("SELECT DISTINCT company_id FROM site_cameras").fetchall()
    scanned = 0
    ingested = 0
    skipped_hours = 0
    deduped = 0

    for crow in companies:
        cid = str(crow["company_id"])
        status = watch_status(db, cid)
        if not status.get("enabled"):
            continue
        if not is_after_hours(db, cid):
            skipped_hours += 1
            continue
        cams = list_cameras(db, cid)
        for cam in cams:
            if not cam.get("online") and not camera_is_online(cam.get("lastSeenAt")):
                continue
            scanned += 1
            cam_id = str(cam["id"])
            if should_dedup_alert(db, cid, cam_id, "vision_critical", minutes=int(os.getenv("BAUPASS_CAMERA_VISION_DEDUP_MINUTES", "10"))):
                deduped += 1
                continue
            snap = get_camera_snapshot_b64(db, cid, cam_id) or ""
            if not snap:
                continue
            vision = analyze_snapshot_b64(
                snap,
                camera_name=str(cam.get("name") or cam_id),
                location=str(cam.get("location") or ""),
                meta={"assume_person": True, "after_hours": True},
            )
            if not (vision.get("personDetected") or vision.get("possibleIntrusion")):
                continue
            payload = vision_result_to_event_payload(vision, camera_id=cam_id, company_id=cid)
            payload["image_base64"] = snap
            payload["camera_name"] = cam.get("name")
            payload["location"] = cam.get("location")
            result = ingest_camera_event(db, cid, payload)
            if result.get("id"):
                ingested += 1
                mark_dedup_alert(db, cid, cam_id, "vision_critical")

    return {
        "ok": True,
        "companies": len(companies),
        "scanned": scanned,
        "ingested": ingested,
        "skippedNotAfterHours": skipped_hours,
        "deduped": deduped,
    }
