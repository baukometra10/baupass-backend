"""AI Video & Camera Layer — ingest + rule-based vision analysis."""
from __future__ import annotations

import json
import uuid
from typing import Any

from ._common import now_iso


def analyze_camera_event(company_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Rule-based analysis when no external CV service is connected."""
    event_type = str(payload.get("event_type") or payload.get("type") or "motion").lower()
    worker_id = payload.get("worker_id")
    ppe = payload.get("ppe")
    zone = str(payload.get("zone") or payload.get("restricted_zone") or "")
    conf_raw = payload.get("confidence")
    confidence = float(conf_raw) if conf_raw is not None and str(conf_raw).strip() != "" else None
    ppe_compliant = None
    zone_violation = 0
    alerts = []
    if ppe is False or str(payload.get("helmet")).lower() in ("false", "0", "no"):
        ppe_compliant = 0
        alerts.append({"type": "ppe_missing", "severity": "high", "message": "Safety equipment not detected"})
    elif ppe is True:
        ppe_compliant = 1
    if zone and payload.get("in_restricted_zone"):
        zone_violation = 1
        alerts.append({"type": "restricted_zone", "severity": "critical", "message": f"Entry in restricted zone: {zone}"})
    if event_type in ("unknown_person", "tailgating", "forced_entry"):
        alerts.append({"type": event_type, "severity": "critical", "message": "Suspicious access event from camera"})
    if payload.get("face_match") is False:
        alerts.append({"type": "identity_mismatch", "severity": "high", "message": "Face/badge mismatch"})
    return {
        "event_type": event_type,
        "worker_id": worker_id,
        "confidence": confidence,
        "ppe_compliant": ppe_compliant,
        "zone_violation": zone_violation,
        "alerts": alerts,
    }


def ingest_camera_event(db, company_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    from .camera_registry import touch_camera_heartbeat

    company_id_str = str(company_id)
    camera_id = str(payload.get("camera_id") or "unknown")
    created_at = now_iso()
    is_heartbeat_only = bool(payload.get("heartbeat")) and not payload.get("event_type")

    touch_camera_heartbeat(
        db,
        company_id_str,
        camera_id,
        payload=payload,
        snapshot_b64=str(
            payload.get("image_base64") or payload.get("snapshot_base64") or payload.get("photo_base64") or ""
        ),
        health_error=str(payload.get("health_error") or payload.get("error") or ""),
    )

    if is_heartbeat_only:
        from backend.app.platform.events.bus import publish_event

        publish_event("camera.heartbeat", company_id_str, {"camera_id": camera_id})
        return {"id": None, "heartbeat": True, "camera_id": camera_id}

    analysis = analyze_camera_event(company_id, payload)
    eid = f"cam-{uuid.uuid4().hex[:12]}"
    try:
        db.execute(
            """
            INSERT INTO camera_ai_events
                (id, company_id, camera_id, event_type, worker_id, confidence,
                 ppe_compliant, zone_violation, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eid,
                company_id_str,
                camera_id,
                analysis["event_type"],
                analysis.get("worker_id"),
                analysis["confidence"],
                analysis.get("ppe_compliant"),
                analysis.get("zone_violation") or 0,
                json.dumps({**payload, "analysis": analysis}),
                created_at,
            ),
        )
        db.commit()
    except Exception:
        pass

    if analysis.get("alerts"):
        try:
            from .camera_notifications import notify_camera_violation

            cam_row = db.execute(
                "SELECT name, location FROM site_cameras WHERE company_id = ? AND id = ?",
                (company_id_str, camera_id),
            ).fetchone()
            notify_camera_violation(
                db,
                company_id=company_id_str,
                event_id=eid,
                camera_id=camera_id,
                camera_name=str(cam_row["name"] if cam_row else camera_id),
                location=str(cam_row["location"] if cam_row else payload.get("location") or ""),
                event_type=analysis["event_type"],
                created_at=created_at,
                analysis=analysis,
                snapshot_b64=str(
                    payload.get("image_base64") or payload.get("snapshot_base64") or ""
                ),
                worker_id=analysis.get("worker_id"),
            )
        except Exception:
            from .security_engine import _persist_alert

            for a in analysis["alerts"]:
                _persist_alert(
                    db,
                    company_id,
                    {
                        "alert_type": a["type"],
                        "severity": a["severity"],
                        "title": a["message"],
                        "worker_id": analysis.get("worker_id"),
                        "details": {"camera_id": camera_id, "event_id": eid},
                    },
                )

    from backend.app.platform.events.bus import publish_event

    publish_event("camera.ai.event", company_id_str, {"event_id": eid, "analysis": analysis})
    return {"id": eid, "analysis": analysis}
