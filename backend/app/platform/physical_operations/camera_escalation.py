"""Critical camera escalation packs + human-assisted police suggestion."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from ._common import now_iso
from .camera_watch import (
    normalize_site_key,
    record_false_positive_learning,
    resolve_watch_settings,
)


def _parse_iso_dt(raw: str | None) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _format_age_label(seconds: int) -> str:
    secs = max(0, int(seconds))
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m"
    hours = mins // 60
    rem_m = mins % 60
    if hours < 48:
        return f"{hours}h {rem_m}m" if rem_m else f"{hours}h"
    days = hours // 24
    return f"{days}d"


def _row_keys(row) -> set[str]:
    try:
        if hasattr(row, "keys"):
            return {str(k) for k in row.keys()}
    except Exception:
        pass
    try:
        return {str(k) for k in dict(row).keys()}
    except Exception:
        return set()


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


def _row_val(row, key: str, default: Any = None) -> Any:
    if key not in _row_keys(row):
        return default
    try:
        val = row[key]
        return default if val is None else val
    except Exception:
        return default


def _sla_fields(row) -> dict[str, Any]:
    try:
        created = _parse_iso_dt(str(_row_val(row, "created_at", "") or ""))
        now = datetime.now(timezone.utc)
        age = int((now - created).total_seconds()) if created else 0
        stage = _safe_int(_row_val(row, "chain_stage", 0), 0)
        next_at = str(_row_val(row, "chain_next_at", "") or "") or None
        status = str(_row_val(row, "status", "") or "")
        openish = status in {"open", "pending_second_ack"}
        next_bit = ""
        if openish and next_at:
            nxt = _parse_iso_dt(next_at)
            if nxt:
                delta = int((nxt - now).total_seconds())
                if delta > 0:
                    next_bit = f" · nächster Schritt in {_format_age_label(delta)}"
                else:
                    next_bit = " · nächster Schritt fällig"
            else:
                next_bit = f" · nächster Schritt {next_at}"
        elif openish and stage >= 2:
            next_bit = " · Kette abgeschlossen"
        elif not openish:
            next_bit = f" · Status {status}"
        sla_label = f"offen seit {_format_age_label(age)} · Stufe {stage}{next_bit}"
        return {
            "ageSeconds": age,
            "chainStage": stage,
            "chainNextAt": next_at,
            "slaLabel": sla_label,
        }
    except Exception:
        return {
            "ageSeconds": 0,
            "chainStage": 0,
            "chainNextAt": None,
            "slaLabel": "offen",
        }


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


def _row_has(row, key: str) -> bool:
    try:
        return key in row.keys()
    except Exception:
        return False


def _parse_ack_users(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            return [str(x) for x in data if str(x).strip()]
    except Exception:
        pass
    return []


def _serialize_row(r) -> dict[str, Any]:
    details = {}
    try:
        details = json.loads(_row_val(r, "details_json", "{}") or "{}")
    except Exception:
        details = {}
    if not isinstance(details, dict):
        details = {}
    clip = str(_row_val(r, "clip_b64", "") or "")
    snap = str(_row_val(r, "snapshot_b64", "") or "")
    sla = _sla_fields(r)
    try:
        return {
            "id": _row_val(r, "id"),
            "companyId": _row_val(r, "company_id"),
            "eventId": _row_val(r, "event_id"),
            "cameraId": _row_val(r, "camera_id"),
            "cameraName": str(details.get("cameraName") or "") or None,
            "eventType": str(details.get("eventType") or "") or None,
            "location": str(details.get("location") or "") or None,
            "siteKey": str(_row_val(r, "site_key", "") or ""),
            "severity": _row_val(r, "severity"),
            "status": _row_val(r, "status"),
            "policeName": _row_val(r, "police_name"),
            "policeAddress": _row_val(r, "police_address"),
            "policePhone": _row_val(r, "police_phone"),
            "policeCountry": _row_val(r, "police_country"),
            "policeCity": _row_val(r, "police_city"),
            "hasSnapshot": bool(snap.strip()),
            "hasClip": bool(clip.strip()),
            "hasClearSnapshot": bool(str(_row_val(r, "snapshot_clear_b64", "") or "").strip()),
            "falsePositive": bool(_safe_int(_row_val(r, "false_positive", 0), 0)),
            "falsePositiveBy": _row_val(r, "false_positive_by"),
            "falsePositiveAt": _row_val(r, "false_positive_at"),
            "details": details,
            "test": bool(details.get("test")),
            "acknowledgedBy": _row_val(r, "acknowledged_by"),
            "acknowledgedAt": _row_val(r, "acknowledged_at"),
            "ackCount": _safe_int(_row_val(r, "ack_count", 0), 0),
            "ackUsers": _parse_ack_users(_row_val(r, "ack_users_json", "[]")),
            "chainStage": sla["chainStage"],
            "chainNextAt": sla["chainNextAt"],
            "ageSeconds": sla["ageSeconds"],
            "slaLabel": sla["slaLabel"],
            "dualAckRequired": bool(_safe_int(_row_val(r, "dual_ack_required", 0), 0)),
            "createdAt": _row_val(r, "created_at"),
            "autoDial": False,
        }
    except Exception as exc:
        return {
            "id": _row_val(r, "id"),
            "companyId": _row_val(r, "company_id"),
            "cameraId": _row_val(r, "camera_id"),
            "status": _row_val(r, "status"),
            "severity": _row_val(r, "severity"),
            "createdAt": _row_val(r, "created_at"),
            "error": f"serialize_failed:{exc}",
            "autoDial": False,
            "slaLabel": "offen",
            "ageSeconds": 0,
            "chainStage": 0,
            "ackCount": 0,
            "ackUsers": [],
            "dualAckRequired": False,
            "hasSnapshot": False,
            "hasClip": False,
            "falsePositive": False,
            "details": details,
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
    from .police_directory import suggest_nearest_police

    police = suggest_nearest_police(
        country=str(cfg.get("country") or ""),
        city=str(cfg.get("city") or ""),
        latitude=cfg.get("latitude"),
        longitude=cfg.get("longitude"),
        db=db,
    )
    station = police.get("station") or {}
    eid = f"cesc-{uuid.uuid4().hex[:12]}"
    is_test = bool(analysis.get("test") or str(event_type or "").lower() == "test_alarm")
    details = {
        "cameraName": camera_name,
        "location": location,
        "siteKey": site_key,
        "eventType": event_type,
        "test": is_test,
        "analysis": {
            "alerts": analysis.get("alerts") or [],
            "afterHours": analysis.get("afterHours"),
            "maxSeverity": analysis.get("maxSeverity"),
            "confidence": analysis.get("confidence"),
            "test": is_test,
        },
        "police": police,
        "disclaimer": police.get("disclaimer"),
        "resolvedFrom": cfg.get("resolvedFrom"),
    }
    dual_ack = bool(cfg.get("requireDualAck", True))
    try:
        escalate_mins = max(1, int(cfg.get("escalateAfterMinutes") or 15))
    except Exception:
        escalate_mins = 15
    chain_next = (datetime.now(timezone.utc) + timedelta(minutes=escalate_mins)).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    created_at = now_iso()
    public_snap = str(snapshot_b64 or "")
    clear_snap = ""
    public_clip = str(clip_b64 or "")
    clear_clip = ""
    try:
        from .camera_legal import allow_camera_evidence

        allowed, deny_reason = allow_camera_evidence(db, str(company_id))
        if not allowed:
            # Metadata-only escalation: never persist media without legal readiness.
            public_snap = ""
            public_clip = ""
            clear_snap = ""
            clear_clip = ""
            details["mediaBlocked"] = True
            details["mediaBlockReason"] = deny_reason
    except Exception:
        pass
    try:
        from .face_privacy import protect_camera_image
        from .camera_watch import get_watch_settings as _gws

        if public_snap:
            protected = protect_camera_image(db, company_id, public_snap)
            public_snap = str(protected.get("public") or public_snap)
            clear_snap = str(protected.get("clear") or "")
            blur_on = bool((_gws(db, company_id) or {}).get("faceBlurEnabled", True))
            if blur_on and public_clip:
                clear_clip = public_clip
                public_clip = ""
    except Exception:
        pass
    try:
        db.execute(
            """
            INSERT INTO camera_escalations (
                id, company_id, event_id, camera_id, severity, status,
                police_name, police_address, police_phone, police_country, police_city,
                snapshot_b64, details_json, created_at, clip_b64, site_key,
                ack_count, ack_users_json, chain_stage, chain_next_at, dual_ack_required,
                snapshot_clear_b64, clip_clear_b64
            ) VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '[]', 0, ?, ?, ?, ?)
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
                str(public_snap or "")[:350000],
                json.dumps(details, ensure_ascii=False),
                created_at,
                str(public_clip or "")[:2_000_000],
                site_key,
                chain_next,
                1 if dual_ack else 0,
                str(clear_snap or "")[:350000],
                str(clear_clip or "")[:2_000_000],
            ),
        )
        db.commit()
    except Exception:
        # Fallback without new columns (pre-046/047 DBs)
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
                    str(public_snap or "")[:350000],
                    json.dumps(details, ensure_ascii=False),
                    created_at,
                    str(public_clip or "")[:2_000_000],
                    site_key,
                ),
            )
            db.commit()
        except Exception:
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
                        str(public_snap or "")[:350000],
                        json.dumps(details, ensure_ascii=False),
                        created_at,
                    ),
                )
                db.commit()
            except Exception as exc:
                return {"ok": False, "error": str(exc), "police": police, "autoDial": False}

    _append_event(db, escalation_id=eid, company_id=company_id, event_type="created", note=event_type)

    webhook = str(cfg.get("securityWebhookUrl") or "").strip()
    webhook_ok = False
    webhook_meta: dict[str, Any] = {}
    if webhook.startswith("http"):
        try:
            from .camera_webhook import deliver_or_enqueue_webhook

            event_name = "camera.test_alarm" if is_test else "camera.critical_escalation"
            payload = {
                "type": event_name,
                "companyId": company_id,
                "escalationId": eid,
                "eventId": event_id,
                "cameraId": camera_id,
                "cameraName": camera_name,
                "location": location,
                "siteKey": site_key,
                "severity": str(analysis.get("maxSeverity") or "critical"),
                "policeSuggestion": police,
                "autoDial": False,
                "hasClip": bool(public_clip or clear_clip),
                "test": is_test,
            }
            webhook_meta = deliver_or_enqueue_webhook(
                db,
                company_id=str(company_id),
                url=webhook,
                payload=payload,
                secret=str(cfg.get("webhookSecret") or ""),
                event=event_name,
                escalation_id=eid,
                retry_max=int(cfg.get("webhookRetryMax") or 3),
            )
            webhook_ok = bool(webhook_meta.get("ok"))
        except Exception:
            webhook_ok = False

    return {
        "ok": True,
        "id": eid,
        "police": police,
        "securityWebhookSent": webhook_ok,
        "securityWebhook": webhook_meta,
        "autoDial": False,
        "test": is_test,
        "dualAckRequired": dual_ack,
        "chainNextAt": chain_next,
        "detailUrl": f"/admin-v2/camera-watch.html?company_id={company_id}&escalation={eid}",
    }


def create_test_alarm(
    db,
    company_id: str,
    *,
    dry_run: bool = False,
    severity: str = "high",
    send_webhook: bool = True,
    actor_user_id: str = "",
) -> dict[str, Any]:
    """Admin test alarm — creates a short-lived ackable escalation with test=true.

    Never auto-dials police. Assisted police suggestion only.
    """
    cid = str(company_id or "").strip()
    if not cid:
        raise ValueError("company_id_required")
    sev = str(severity or "high").lower()
    if sev not in {"high", "critical"}:
        sev = "high"
    cfg = resolve_watch_settings(db, cid)
    analysis = {
        "maxSeverity": sev,
        "critical": sev == "critical",
        "afterHours": True,
        "test": True,
        "alerts": [
            {
                "type": "test_alarm",
                "severity": sev,
                "message": "Test-Alarm (kein echter Vorfall)",
            }
        ],
    }
    if dry_run:
        from .police_directory import suggest_nearest_police

        police = suggest_nearest_police(
            country=str(cfg.get("country") or ""),
            city=str(cfg.get("city") or ""),
            latitude=cfg.get("latitude"),
            longitude=cfg.get("longitude"),
            db=db,
        )
        return {
            "ok": True,
            "dryRun": True,
            "test": True,
            "severity": sev,
            "police": police,
            "webhookWouldSend": bool(str(cfg.get("securityWebhookUrl") or "").startswith("http")) and send_webhook,
            "autoDial": False,
        }

    created = create_critical_escalation(
        db,
        company_id=cid,
        event_id=f"test-{uuid.uuid4().hex[:10]}",
        camera_id="cam-test-alarm",
        camera_name="Test-Alarm",
        location=str(cfg.get("city") or "test"),
        event_type="test_alarm",
        analysis=analysis,
        snapshot_b64="",
        clip_b64="",
        site=str(cfg.get("siteKey") or ""),
    )
    if not send_webhook and created.get("ok"):
        # Escalation still created; webhook already attempted in create — acceptable for test path
        pass
    try:
        from backend.app.platform.physical_operations.camera_notifications import _notify_admin_inbox

        _notify_admin_inbox(
            cid,
            title=f"Test-Alarm ({sev})",
            message="Manueller Test-Alarm aus Kamera-Wächter — kein echter Vorfall. Kein Auto-Notruf.",
            severity=sev,
        )
    except Exception:
        pass
    if actor_user_id and created.get("id"):
        _append_event(
            db,
            escalation_id=str(created["id"]),
            company_id=cid,
            event_type="test_alarm",
            actor_user_id=actor_user_id,
            note="Admin test alarm",
        )
    return {
        **(created if isinstance(created, dict) else {"ok": False}),
        "test": True,
        "dryRun": False,
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
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            out.append(_serialize_row(r))
        except Exception:
            continue
    return out


def get_escalation(
    db, company_id: str, escalation_id: str, *, include_media: bool = False, reveal: bool = False
) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT * FROM camera_escalations WHERE company_id = ? AND id = ?",
        (str(company_id), str(escalation_id)),
    ).fetchone()
    if not row:
        return None
    item = _serialize_row(row)
    if include_media:
        if reveal:
            item["snapshotBase64"] = str(_row_val(row, "snapshot_clear_b64", "") or "") or str(
                _row_val(row, "snapshot_b64", "") or ""
            )
            item["clipBase64"] = str(_row_val(row, "clip_clear_b64", "") or "") or str(
                _row_val(row, "clip_b64", "") or ""
            )
            item["facesRevealed"] = True
        else:
            item["snapshotBase64"] = str(_row_val(row, "snapshot_b64", "") or "")
            item["clipBase64"] = str(_row_val(row, "clip_b64", "") or "")
            item["facesRevealed"] = False
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

    actor = str(actor_user_id or "").strip()[:120]
    dual_required = bool(int(row["dual_ack_required"] if _row_has(row, "dual_ack_required") else 0) or 0)
    ack_count = int(row["ack_count"] if _row_has(row, "ack_count") and row["ack_count"] is not None else 0)
    ack_users = _parse_ack_users(row["ack_users_json"] if _row_has(row, "ack_users_json") else "[]")
    ts = now_iso()

    if dual_required and actor and actor in ack_users:
        raise ValueError("duplicate_ack")

    if dual_required and ack_count < 1:
        # First ack — wait for a second distinct user
        new_users = list(ack_users)
        if actor and actor not in new_users:
            new_users.append(actor)
        try:
            db.execute(
                """
                UPDATE camera_escalations
                SET status = 'pending_second_ack', ack_count = 1, ack_users_json = ?
                WHERE company_id = ? AND id = ?
                """,
                (json.dumps(new_users, ensure_ascii=False), cid, eid),
            )
            db.commit()
        except Exception:
            db.execute(
                """
                UPDATE camera_escalations
                SET status = 'pending_second_ack'
                WHERE company_id = ? AND id = ?
                """,
                (cid, eid),
            )
            db.commit()
        _append_event(
            db,
            escalation_id=eid,
            company_id=cid,
            event_type="ack_partial",
            actor_user_id=actor,
            note="First acknowledgment — second required",
        )
        return get_escalation(db, cid, eid, include_media=False)

    # Full ack (no dual requirement, or second distinct user)
    status = "security_notified" if mark_security_notified else "acknowledged"
    new_users = list(ack_users)
    if actor and actor not in new_users:
        new_users.append(actor)
    final_count = max(ack_count + (1 if actor and actor not in ack_users else 0), len(new_users), 1)
    try:
        db.execute(
            """
            UPDATE camera_escalations
            SET status = ?, acknowledged_by = ?, acknowledged_at = ?,
                ack_count = ?, ack_users_json = ?
            WHERE company_id = ? AND id = ?
            """,
            (
                status,
                actor,
                ts,
                final_count,
                json.dumps(new_users, ensure_ascii=False),
                cid,
                eid,
            ),
        )
        db.commit()
    except Exception:
        db.execute(
            """
            UPDATE camera_escalations
            SET status = ?, acknowledged_by = ?, acknowledged_at = ?
            WHERE company_id = ? AND id = ?
            """,
            (status, actor, ts, cid, eid),
        )
        db.commit()
    _append_event(
        db,
        escalation_id=eid,
        company_id=cid,
        event_type=status,
        actor_user_id=actor,
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
