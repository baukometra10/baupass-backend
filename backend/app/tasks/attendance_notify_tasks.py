"""RQ tasks for employer attendance notifications (non-blocking gate path)."""
from __future__ import annotations

from typing import Any


def notify_outside_hours_checkin_task(ctx: dict[str, Any]) -> dict[str, Any]:
    from backend.server import app, get_db
    from backend.app.platform.notifications.company_mitteilung import (
        notify_company_outside_hours_checkin_attempt,
    )

    with app.app_context():
        db = get_db()
        return notify_company_outside_hours_checkin_attempt(
            db,
            company_id=str(ctx.get("companyId") or ""),
            worker_id=str(ctx.get("workerId") or ""),
            worker_name=str(ctx.get("workerName") or ""),
            reason=str(ctx.get("reason") or ""),
            channel=str(ctx.get("channel") or "gps"),
            gate=str(ctx.get("gate") or ""),
            shift_start=str(ctx.get("shiftStart") or ""),
            shift_end=str(ctx.get("shiftEnd") or ""),
            message=str(ctx.get("message") or ""),
        )


def notify_repeated_late_task(ctx: dict[str, Any]) -> dict[str, Any]:
    from backend.server import app, get_db
    from backend.app.platform.notifications.company_mitteilung import (
        notify_company_repeated_late_checkin,
    )

    with app.app_context():
        db = get_db()
        return notify_company_repeated_late_checkin(
            db,
            company_id=str(ctx.get("companyId") or ""),
            worker_id=str(ctx.get("workerId") or ""),
            worker_name=str(ctx.get("workerName") or ""),
            streak=int(ctx.get("streak") or 0),
            late_events=list(ctx.get("lateEvents") or []),
            reason_summary=str(ctx.get("reasonSummary") or "") or None,
        )


def gate_tap_side_effects_task(ctx: dict[str, Any]) -> dict[str, Any]:
    from backend.server import _run_gate_tap_side_effects

    _run_gate_tap_side_effects(ctx)
    return {"ok": True}


def process_gate_async_ingest_task(event_uid: str) -> dict[str, Any]:
    """Process a previously accepted async gate event (BAUPASS_GATE_ASYNC_INGEST)."""
    from backend.server import app, get_db, _process_gate_tap_payload
    import json

    with app.app_context():
        db = get_db()
        row = db.execute(
            """
            SELECT raw_payload_json, company_id, device_id, outcome
            FROM device_ingest_events
            WHERE event_uid = ?
            LIMIT 1
            """,
            (str(event_uid),),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "event_not_found"}
        outcome = str(row["outcome"] or "")
        if outcome in {"processed", "duplicate_ignored"}:
            return {"ok": True, "skipped": True, "reason": "already_processed"}
        payload = {}
        try:
            payload = json.loads(row["raw_payload_json"] or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        turnstile = {
            "id": str(row["device_id"] or ""),
            "company_id": str(row["company_id"] or ""),
            "role": "turnstile",
        }
        # Prefer live turnstile row when available (plan features / company checks).
        try:
            live = db.execute(
                "SELECT * FROM users WHERE id = ? AND role = 'turnstile' LIMIT 1",
                (turnstile["id"],),
            ).fetchone()
            if live:
                turnstile = live
        except Exception:
            pass
        result, status = _process_gate_tap_payload(
            db,
            turnstile,
            payload,
            pre_accepted_event_uid=str(event_uid),
        )
        return {"ok": status < 400, "status": status, "result": result}
