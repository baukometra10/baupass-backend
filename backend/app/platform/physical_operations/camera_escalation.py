"""Critical camera escalation packs + human-assisted police suggestion."""
from __future__ import annotations

import json
import uuid
from typing import Any

from ._common import now_iso
from .camera_watch import (
    normalize_site_key,
    record_false_positive_learning,
    resolve_watch_settings,
)
from .police_directory import suggest_nearest_police


def _append_event(
    db,
    *,
    escalation_id: str,
    company_id: str,
    event_type: str,
    actor_user_id: str = "",
    note: str = "",
) -> None:
    try:
        db.execute(
            """
            INSERT INTO camera_escalation_events
                (id, escalation_id, company_id, event_type, actor_user_id, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"cee-{uuid.uuid4().hex[:12]}",
                str(escalation_id),
                str(company_id),
                str(event_type)[:80],
                str(actor_user_id or "")[:120],
                str(note or "")[:500],
                now_iso(),
            ),
        )
        db.commit()
    except Exception:
        pass


def _serialize_row(r) -> dict[str, Any]:
    details = {}
    try:
        details = json.loads(r["details_json"] or "{}")
    except Exception:
        details = {}
    keys = r.keys() if hasattr(r, "keys") else []
    clip = str(r["clip_b64"] if "clip_b64" in keys else "") or ""
    return {
        "id": r["id"],
        "companyId": r["company_id"],
        "eventId": r["event_id"],
        "cameraId": r["camera_id"],
        "siteKey": str(r["site_key"] if "site_key" in keys else "") or "",
        "severity": r["severity"],
        "status": r["status"],
        "policeName": r["police_name"],
        "policeAddress": r["police_address"],
        "policePhone": r["police_phone"],
        "policeCountry": r["police_country"],
        "policeCity": r["police_city"],
        "hasSnapshot": bool(str(r["snapshot_b64"] or "").strip()),
        "hasClip": bool(clip.strip()),
        "falsePositive": bool(int(r["false_positive"] if "false_positive" in keys else 0) or 0),
        "falsePositiveBy": r["false_positive_by"] if "false_positive_by" in keys else None,
        "falsePositiveAt": r["false_positive_at"] if "false_positive_at" in keys else None,
        "details": details,
        "acknowledgedBy": r["acknowledged_by"],
        "acknowledgedAt": r["acknowledged_at"],
        "createdAt": r["created_at"],
    }


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
    clip_b64: str = "",
    site: str = "",
) -> dict[str, Any]:
    site_key = normalize_site_key(site or location)
    cfg = resolve_watch_settings(db, company_id, site=site_key or location)
    police = suggest_nearest_police(
        country=str(cfg.get("country") or ""),
        city=str(cfg.get("city") or ""),
        latitude=cfg.get("latitude"),
        longitude=cfg.get("longitude"),
        db=db,
    )
    station = police.get("station") or {}
    eid = f"cesc-{uuid.uuid4().hex[:12]}"
    details = {
        "cameraName": camera_name,
        "location": location,
        "siteKey": site_key,
        "eventType": event_type,
        "analysis": {
            "alerts": analysis.get("alerts") or [],
            "afterHours": analysis.get("afterHours"),
            "maxSeverity": analysis.get("maxSeverity"),
            "confidence": analysis.get("confidence"),
        },
        "police": police,
        "disclaimer": police.get("disclaimer"),
        "resolvedFrom": cfg.get("resolvedFrom"),
    }
    try:
        db.execute(
            """
            INSERT INTO camera_escalations (
                id, company_id, event_id, camera_id, severity, status,
                police_name, police_address, police_phone, police_country, police_city,
                snapshot_b64, details_json, created_at, clip_b64, site_key
            ) VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                str(clip_b64 or "")[:2_000_000],
                site_key,
            ),
        )
        db.commit()
    except Exception:
        # Fallback without new columns (pre-046 DBs)
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

    _append_event(db, escalation_id=eid, company_id=company_id, event_type="created", note=event_type)

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
                    "siteKey": site_key,
                    "policeSuggestion": police,
                    "autoDial": False,
                    "hasClip": bool(clip_b64),
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
        "detailUrl": f"/admin-v2/camera-watch.html?escalation={eid}",
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
    return [_serialize_row(r) for r in rows]


def get_escalation(
    db, company_id: str, escalation_id: str, *, include_media: bool = False
) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT * FROM camera_escalations WHERE company_id = ? AND id = ?",
        (str(company_id), str(escalation_id)),
    ).fetchone()
    if not row:
        return None
    item = _serialize_row(row)
    if include_media:
        item["snapshotBase64"] = str(row["snapshot_b64"] or "")
        keys = row.keys()
        item["clipBase64"] = str(row["clip_b64"] if "clip_b64" in keys else "") or ""
    try:
        ev_rows = db.execute(
            """
            SELECT id, event_type, actor_user_id, note, created_at
            FROM camera_escalation_events
            WHERE escalation_id = ?
            ORDER BY created_at ASC
            """,
            (str(escalation_id),),
        ).fetchall()
        item["history"] = [
            {
                "id": e["id"],
                "type": e["event_type"],
                "actorUserId": e["actor_user_id"],
                "note": e["note"],
                "createdAt": e["created_at"],
            }
            for e in ev_rows
        ]
    except Exception:
        item["history"] = []
    return item


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
    _append_event(
        db,
        escalation_id=eid,
        company_id=cid,
        event_type=status,
        actor_user_id=actor_user_id,
    )
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
    return get_escalation(db, cid, eid, include_media=False)


def mark_false_positive(
    db,
    company_id: str,
    escalation_id: str,
    *,
    actor_user_id: str = "",
    note: str = "",
) -> dict[str, Any] | None:
    cid = str(company_id)
    eid = str(escalation_id)
    row = db.execute(
        "SELECT * FROM camera_escalations WHERE company_id = ? AND id = ?",
        (cid, eid),
    ).fetchone()
    if not row:
        return None
    ts = now_iso()
    try:
        db.execute(
            """
            UPDATE camera_escalations
            SET false_positive = 1, false_positive_by = ?, false_positive_at = ?, status = 'false_positive'
            WHERE company_id = ? AND id = ?
            """,
            (str(actor_user_id or "")[:120], ts, cid, eid),
        )
        db.commit()
    except Exception:
        db.execute(
            """
            UPDATE camera_escalations
            SET status = 'false_positive', acknowledged_by = ?, acknowledged_at = ?
            WHERE company_id = ? AND id = ?
            """,
            (str(actor_user_id or "")[:120], ts, cid, eid),
        )
        db.commit()

    details = {}
    try:
        details = json.loads(row["details_json"] or "{}")
    except Exception:
        details = {}
    alert_key = str((details.get("eventType") or row["severity"] or "critical"))[:120]
    learn = record_false_positive_learning(db, cid, str(row["camera_id"]), alert_key)
    _append_event(
        db,
        escalation_id=eid,
        company_id=cid,
        event_type="false_positive",
        actor_user_id=actor_user_id,
        note=note or "Marked as false positive",
    )
    try:
        from backend.server import log_audit

        log_audit(
            "camera.escalation_false_positive",
            f"{eid} key={alert_key}",
            target_type="camera_escalation",
            target_id=eid,
            company_id=cid,
        )
    except Exception:
        pass
    item = get_escalation(db, cid, eid, include_media=False) or {}
    item["learning"] = learn
    return item
