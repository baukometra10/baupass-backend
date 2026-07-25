"""AI Video & Camera Layer — ingest + rule-based vision analysis."""
from __future__ import annotations

import json
import uuid
from typing import Any

from ._common import now_iso


def analyze_camera_event(company_id: Any, payload: dict[str, Any], *, after_hours: bool | None = None) -> dict[str, Any]:
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
        alerts.append(
            {
                "type": "restricted_zone",
                "severity": "critical",
                "message": f"Entry in unauthorized / restricted area: {zone}",
            }
        )
    if event_type in ("unknown_person", "tailgating", "forced_entry", "possible_intrusion"):
        alerts.append(
            {
                "type": event_type,
                "severity": "critical",
                "message": "Suspicious access event from camera (not confirmed theft)",
            }
        )
    if event_type == "restricted_area_activity":
        zone_violation = 1
        alerts.append(
            {
                "type": "restricted_area_activity",
                "severity": "critical",
                "message": "Activity in unauthorized area detected by vision review",
            }
        )
    if payload.get("face_match") is False:
        alerts.append({"type": "identity_mismatch", "severity": "high", "message": "Face/badge mismatch"})

    analysis = {
        "event_type": event_type,
        "worker_id": worker_id,
        "confidence": confidence,
        "ppe_compliant": ppe_compliant,
        "zone_violation": zone_violation,
        "alerts": alerts,
    }

    from .camera_watch import apply_after_hours_escalation

    if after_hours is None:
        after_hours = bool(payload.get("afterHours") or payload.get("after_hours"))
    return apply_after_hours_escalation(analysis, after_hours=bool(after_hours))


def ingest_camera_event(db, company_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    from .camera_registry import get_camera_snapshot_b64, touch_camera_heartbeat
    from .camera_watch import (
        is_after_hours_for_site,
        is_alert_suppressed,
        mark_dedup_alert,
        should_dedup_alert,
    )

    company_id_str = str(company_id)
    camera_id = str(payload.get("camera_id") or "unknown")
    created_at = now_iso()
    is_heartbeat_only = bool(payload.get("heartbeat")) and not payload.get("event_type")
    site = str(payload.get("location") or payload.get("site") or payload.get("site_key") or "")

    snapshot_b64 = str(
        payload.get("image_base64") or payload.get("snapshot_base64") or payload.get("photo_base64") or ""
    )
    clip_b64 = str(payload.get("clip_base64") or payload.get("clipBase64") or payload.get("video_base64") or "")

    touch_camera_heartbeat(
        db,
        company_id_str,
        camera_id,
        payload=payload,
        snapshot_b64=snapshot_b64,
        health_error=str(payload.get("health_error") or payload.get("error") or ""),
    )

    if is_heartbeat_only:
        from backend.app.platform.events.bus import publish_event

        publish_event("camera.heartbeat", company_id_str, {"camera_id": camera_id})
        return {"id": None, "heartbeat": True, "camera_id": camera_id}

    after_hours = is_after_hours_for_site(db, company_id_str, site=site)

    cam_meta = None
    try:
        cam_meta = db.execute(
            "SELECT * FROM site_cameras WHERE company_id = ? AND id = ?",
            (company_id_str, camera_id),
        ).fetchone()
    except Exception:
        cam_meta = None

    # Zone min-confidence gate — skip alerts when payload confidence is too low.
    try:
        min_conf = float(cam_meta["min_confidence"]) if cam_meta and "min_confidence" in cam_meta.keys() and cam_meta["min_confidence"] is not None else 0.0
    except Exception:
        min_conf = 0.0
    conf_raw = payload.get("confidence")
    try:
        payload_conf = float(conf_raw) if conf_raw is not None and str(conf_raw).strip() != "" else None
    except Exception:
        payload_conf = None
    if min_conf > 0 and payload_conf is not None and payload_conf < min_conf:
        return {
            "id": None,
            "skipped": "below_min_confidence",
            "camera_id": camera_id,
            "minConfidence": min_conf,
            "confidence": payload_conf,
            "afterHours": after_hours,
        }

    analysis = analyze_camera_event(company_id_str, payload, after_hours=after_hours)

    # Zone: critical only after hours — downgrade daytime critical to high (skip create_critical path).
    zone_crit_only = False
    try:
        zone_crit_only = bool(
            int(cam_meta["zone_critical_only_after_hours"] if cam_meta and "zone_critical_only_after_hours" in cam_meta.keys() else 0)
            or 0
        )
    except Exception:
        zone_crit_only = False
    if zone_crit_only and not after_hours and (
        analysis.get("critical") or str(analysis.get("maxSeverity") or "").lower() == "critical"
    ):
        from .camera_watch import severity_rank

        alerts = []
        for a in analysis.get("alerts") or []:
            item = dict(a)
            if str(item.get("severity") or "").lower() == "critical":
                item["severity"] = "high"
            alerts.append(item)
        analysis["alerts"] = alerts
        max_sev = "info"
        for a in alerts:
            if severity_rank(a.get("severity")) > severity_rank(max_sev):
                max_sev = str(a.get("severity") or "info")
        analysis["maxSeverity"] = max_sev if max_sev != "info" else "high"
        analysis["critical"] = False
        analysis["criticalDowngraded"] = True

    # Critical alerts require evidence — fall back to last camera snapshot.
    if analysis.get("snapshotRequired") and not snapshot_b64:
        fallback = get_camera_snapshot_b64(db, company_id_str, camera_id) or ""
        if fallback:
            snapshot_b64 = fallback
            analysis["snapshotFallback"] = True
    analysis["hasSnapshot"] = bool(snapshot_b64)
    analysis["hasClip"] = bool(clip_b64)

    # Dedup / false-positive learning suppress window.
    alert_key = f"{analysis.get('event_type')}:{analysis.get('maxSeverity')}"
    if analysis.get("alerts") and (
        is_alert_suppressed(db, company_id_str, camera_id, str(analysis.get("event_type") or alert_key))
        or should_dedup_alert(db, company_id_str, camera_id, alert_key, minutes=5)
    ):
        return {
            "id": None,
            "deduped": True,
            "camera_id": camera_id,
            "analysis": analysis,
        }

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
                json.dumps({**payload, "analysis": analysis, "hasSnapshot": bool(snapshot_b64)}, ensure_ascii=False),
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
                camera_name=str(cam_row["name"] if cam_row else payload.get("camera_name") or camera_id),
                location=str(cam_row["location"] if cam_row else payload.get("location") or site),
                event_type=analysis["event_type"],
                created_at=created_at,
                analysis=analysis,
                snapshot_b64=snapshot_b64,
                clip_b64=clip_b64,
                worker_id=analysis.get("worker_id"),
            )
            mark_dedup_alert(db, company_id_str, camera_id, alert_key)
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
    return {"id": eid, "analysis": analysis, "afterHours": after_hours}
