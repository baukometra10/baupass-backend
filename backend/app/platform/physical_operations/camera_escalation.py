"""Critical camera escalation packs + human-assisted police suggestion."""
from __future__ import annotations

import json
import uuid
from typing import Any

from ._common import now_iso
from .camera_watch import get_watch_settings
from .police_directory import suggest_nearest_police


def create_critical_escalation(
    db,
    *,
    company_id: str,
    event_id: str,
    camera_id: str,
    camera_name: str,
    location: str,
    event_type: str,
    analysis: dict[str, Any],
    snapshot_b64: str = "",
) -> dict[str, Any]:
    cfg = get_watch_settings(db, company_id)
    police = suggest_nearest_police(
        country=str(cfg.get("country") or ""),
        city=str(cfg.get("city") or ""),
        latitude=cfg.get("latitude"),
        longitude=cfg.get("longitude"),
    )
    station = police.get("station") or {}
    eid = f"cesc-{uuid.uuid4().hex[:12]}"
    details = {
        "cameraName": camera_name,
        "location": location,
        "eventType": event_type,
        "analysis": {
            "alerts": analysis.get("alerts") or [],
            "afterHours": analysis.get("afterHours"),
            "maxSeverity": analysis.get("maxSeverity"),
            "confidence": analysis.get("confidence"),
        },
        "police": police,
        "disclaimer": police.get("disclaimer"),
    }
    try:
        db.execute(
            """
            INSERT INTO camera_escalations (
                id, company_id, event_id, camera_id, severity, status,
                police_name, police_address, police_phone, police_country, police_city,
                snapshot_b64, details_json, created_at
            ) VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eid,
                str(company_id),
                str(event_id),
                str(camera_id),
                str(analysis.get("maxSeverity") or "critical"),
                str(station.get("name") or ""),
                str(station.get("address") or ""),
                str(station.get("phone") or (police.get("countryEmergency") or {}).get("number") or ""),
                str(station.get("country") or (police.get("countryEmergency") or {}).get("country") or ""),
                str(station.get("city") or cfg.get("city") or ""),
                str(snapshot_b64 or "")[:350000],
                json.dumps(details, ensure_ascii=False),
                now_iso(),
            ),
        )
        db.commit()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "police": police}

    # Optional firm security webhook (not emergency services)
    webhook = str(cfg.get("securityWebhookUrl") or "").strip()
    webhook_ok = False
    if webhook.startswith("http"):
        try:
            import urllib.request

            body = json.dumps(
                {
                    "type": "camera.critical_escalation",
                    "companyId": company_id,
                    "escalationId": eid,
                    "eventId": event_id,
                    "cameraId": camera_id,
                    "cameraName": camera_name,
                    "location": location,
                    "policeSuggestion": police,
                    "autoDial": False,
                },
                ensure_ascii=False,
            ).encode("utf-8")
            req = urllib.request.Request(
                webhook,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                webhook_ok = 200 <= int(resp.status) < 300
        except Exception:
            webhook_ok = False

    return {
        "ok": True,
        "id": eid,
        "police": police,
        "securityWebhookSent": webhook_ok,
        "autoDial": False,
    }


def list_escalations(db, company_id: str, *, limit: int = 30, status: str | None = None) -> list[dict[str, Any]]:
    lim = max(1, min(100, int(limit)))
    cid = str(company_id)
    try:
        if status:
            rows = db.execute(
                """
                SELECT * FROM camera_escalations
                WHERE company_id = ? AND status = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (cid, str(status), lim),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT * FROM camera_escalations
                WHERE company_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (cid, lim),
            ).fetchall()
    except Exception:
        return []
    out = []
    for r in rows:
        details = {}
        try:
            details = json.loads(r["details_json"] or "{}")
        except Exception:
            details = {}
        out.append(
            {
                "id": r["id"],
                "companyId": r["company_id"],
                "eventId": r["event_id"],
                "cameraId": r["camera_id"],
                "severity": r["severity"],
                "status": r["status"],
                "policeName": r["police_name"],
                "policeAddress": r["police_address"],
                "policePhone": r["police_phone"],
                "policeCountry": r["police_country"],
                "policeCity": r["police_city"],
                "hasSnapshot": bool(str(r["snapshot_b64"] or "").strip()),
                "details": details,
                "acknowledgedBy": r["acknowledged_by"],
                "acknowledgedAt": r["acknowledged_at"],
                "createdAt": r["created_at"],
            }
        )
    return out


def acknowledge_escalation(
    db,
    company_id: str,
    escalation_id: str,
    *,
    actor_user_id: str = "",
    mark_security_notified: bool = False,
) -> dict[str, Any] | None:
    cid = str(company_id)
    eid = str(escalation_id)
    row = db.execute(
        "SELECT * FROM camera_escalations WHERE company_id = ? AND id = ?",
        (cid, eid),
    ).fetchone()
    if not row:
        return None
    status = "security_notified" if mark_security_notified else "acknowledged"
    ts = now_iso()
    db.execute(
        """
        UPDATE camera_escalations
        SET status = ?, acknowledged_by = ?, acknowledged_at = ?
        WHERE company_id = ? AND id = ?
        """,
        (status, str(actor_user_id or "")[:120], ts, cid, eid),
    )
    db.commit()
    try:
        from backend.server import log_audit

        log_audit(
            "camera.escalation_acknowledged",
            f"{eid} → {status}",
            target_type="camera_escalation",
            target_id=eid,
            company_id=cid,
        )
    except Exception:
        pass
    items = list_escalations(db, cid, limit=1)
    for it in items:
        if it["id"] == eid:
            return it
    return {"id": eid, "status": status, "acknowledgedAt": ts}
