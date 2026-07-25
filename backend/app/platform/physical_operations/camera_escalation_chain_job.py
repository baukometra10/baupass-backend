"""Escalation notification chain — second contact, then security webhook. Never auto-dials police."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from ._common import now_iso
from .camera_watch import resolve_watch_settings


def _parse_iso(raw: str | None) -> datetime | None:
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


def _looks_like_phone(value: str) -> bool:
    s = str(value or "").strip()
    if not s or "@" in s:
        return False
    digits = sum(ch.isdigit() for ch in s)
    return digits >= 8


def _looks_like_email(value: str) -> bool:
    s = str(value or "").strip()
    return "@" in s and "." in s.split("@")[-1]


def _append_chain_event(db, *, escalation_id: str, company_id: str, event_type: str, note: str = "") -> None:
    try:
        from .camera_escalation import _append_event

        _append_event(
            db,
            escalation_id=escalation_id,
            company_id=company_id,
            event_type=event_type,
            note=note,
        )
    except Exception:
        pass


def _advance_chain(db, row, *, stage: int, next_at: str | None) -> None:
    db.execute(
        """
        UPDATE camera_escalations
        SET chain_stage = ?, chain_next_at = ?
        WHERE id = ? AND company_id = ?
        """,
        (int(stage), next_at, str(row["id"]), str(row["company_id"])),
    )
    db.commit()


def _notify_second_contact(db, contact: str, *, title: str, message: str) -> dict[str, Any]:
    result = {"sms": False, "email": False, "skipped": False}
    contact = str(contact or "").strip()
    if not contact:
        result["skipped"] = True
        return result
    if _looks_like_phone(contact):
        try:
            from backend.app.platform.notifications.sms import send_sms, sms_configured

            if sms_configured():
                ok, _ = send_sms(to=contact, body=f"{title}\n{message}"[:300])
                result["sms"] = bool(ok)
            else:
                result["skipped"] = True
        except Exception:
            result["skipped"] = True
        return result
    if _looks_like_email(contact):
        try:
            from backend.app.platform.reports.email_delivery import send_attachments_email

            ok, _ = send_attachments_email(
                to=contact,
                subject=title[:120],
                body_text=message,
                attachments=[],
            )
            result["email"] = bool(ok)
        except Exception:
            result["skipped"] = True
        return result
    result["skipped"] = True
    return result


def _post_security_webhook(db, url: str, payload: dict[str, Any], *, cfg: dict[str, Any] | None = None) -> bool:
    if not str(url or "").startswith("http"):
        return False
    try:
        from .camera_webhook import deliver_or_enqueue_webhook

        settings = cfg or {}
        result = deliver_or_enqueue_webhook(
            db,
            company_id=str(payload.get("companyId") or ""),
            url=url,
            payload=payload,
            secret=str(settings.get("webhookSecret") or ""),
            event=str(payload.get("type") or "camera.escalation_chain_security"),
            escalation_id=str(payload.get("escalationId") or ""),
            retry_max=int(settings.get("webhookRetryMax") or 3),
        )
        return bool(result.get("ok") or result.get("queued"))
    except Exception:
        return False


def run_camera_escalation_chain(db) -> dict[str, Any]:
    """Advance open escalations through second-contact → security webhook stages.

    Never auto-dials police.
    """
    if str(os.getenv("BAUPASS_CAMERA_CHAIN_JOB", "1")).strip().lower() in {"0", "false", "off", "no"}:
        return {"ok": True, "skipped": True, "reason": "disabled", "autoDial": False}

    now = datetime.now(timezone.utc)
    now_s = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    processed = 0
    stage1 = 0
    stage2 = 0
    errors = 0

    try:
        rows = db.execute(
            """
            SELECT * FROM camera_escalations
            WHERE status IN ('open', 'pending_second_ack')
              AND COALESCE(chain_stage, 0) < 2
              AND chain_next_at IS NOT NULL
              AND chain_next_at <= ?
            ORDER BY chain_next_at ASC
            LIMIT 50
            """,
            (now_s,),
        ).fetchall()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "autoDial": False}

    for row in rows:
        processed += 1
        try:
            cid = str(row["company_id"])
            eid = str(row["id"])
            stage = int(row["chain_stage"] if row["chain_stage"] is not None else 0)
            site_key = ""
            try:
                site_key = str(row["site_key"] or "")
            except Exception:
                site_key = ""
            details = {}
            try:
                details = json.loads(row["details_json"] or "{}")
            except Exception:
                details = {}
            cfg = resolve_watch_settings(db, cid, site=site_key or details.get("location") or "")
            try:
                escalate_mins = max(1, int(cfg.get("escalateAfterMinutes") or 15))
            except Exception:
                escalate_mins = 15

            if stage <= 0:
                contact = str(cfg.get("escalateSecondContact") or "").strip()
                title = f"Kamera-Eskalation (Stufe 2): {details.get('cameraName') or row['camera_id']}"
                message = (
                    f"Kritischer Vorfall ohne vollständige Bestätigung. "
                    f"Eskalation {eid} · Kamera {row['camera_id']} · "
                    f"{details.get('eventType') or row['severity']}. "
                    f"Kein automatischer Notruf."
                )
                notify = _notify_second_contact(db, contact, title=title, message=message)
                next_at = (now + timedelta(minutes=escalate_mins)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                _advance_chain(db, row, stage=1, next_at=next_at)
                _append_chain_event(
                    db,
                    escalation_id=eid,
                    company_id=cid,
                    event_type="chain_second_contact",
                    note=json.dumps(notify, ensure_ascii=False)[:500],
                )
                stage1 += 1
                continue

            if stage == 1:
                webhook = str(cfg.get("securityWebhookUrl") or "").strip()
                sent = _post_security_webhook(
                    db,
                    webhook,
                    {
                        "type": "camera.escalation_chain_security",
                        "companyId": cid,
                        "escalationId": eid,
                        "cameraId": row["camera_id"],
                        "eventId": row["event_id"],
                        "severity": row["severity"],
                        "autoDial": False,
                        "chainStage": 2,
                        "test": bool(details.get("test")),
                    },
                    cfg=cfg,
                )
                _advance_chain(db, row, stage=2, next_at=None)
                _append_chain_event(
                    db,
                    escalation_id=eid,
                    company_id=cid,
                    event_type="chain_security_webhook",
                    note="sent" if sent else "skipped_or_failed",
                )
                stage2 += 1
        except Exception:
            errors += 1

    return {
        "ok": True,
        "processed": processed,
        "stage1": stage1,
        "stage2": stage2,
        "errors": errors,
        "autoDial": False,
        "checkedAt": now_iso(),
    }
