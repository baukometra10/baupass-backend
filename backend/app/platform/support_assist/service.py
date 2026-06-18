"""Live support assist — spectator channel for company admins (logout + watch cursor)."""
from __future__ import annotations

import secrets
import threading
import time
from typing import Any

_lock = threading.Lock()
_sessions: dict[str, dict[str, Any]] = {}
_MAX_EVENTS = 250
_TTL_SECONDS = 45 * 60


def _now_ts() -> float:
    return time.time()


def _purge_stale_locked() -> None:
    cutoff = _now_ts() - _TTL_SECONDS
    stale = [cid for cid, row in _sessions.items() if float(row.get("updated_at") or 0) < cutoff]
    for cid in stale:
        _sessions.pop(cid, None)


def _append_event_locked(company_id: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    row = _sessions.get(company_id)
    if not row:
        return {}
    seq = int(row.get("seq") or 0) + 1
    event = {
        "seq": seq,
        "type": event_type,
        "payload": payload or {},
        "ts": _now_ts(),
    }
    events: list[dict[str, Any]] = row.setdefault("events", [])
    events.append(event)
    if len(events) > _MAX_EVENTS:
        del events[: len(events) - _MAX_EVENTS]
    row["seq"] = seq
    row["updated_at"] = _now_ts()
    return event


def start_session(db, *, company_id: str, actor_name: str) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    if not cid:
        raise ValueError("missing_company")
    watch_token = secrets.token_urlsafe(24)
    session_id = f"sas-{secrets.token_hex(8)}"
    with _lock:
        _purge_stale_locked()
        _sessions[cid] = {
            "session_id": session_id,
            "company_id": cid,
            "watch_token": watch_token,
            "actor_name": str(actor_name or "Support").strip() or "Support",
            "started_at": _now_ts(),
            "updated_at": _now_ts(),
            "seq": 0,
            "events": [],
        }
        _append_event_locked(cid, "session_start", {"actorName": actor_name})
        _append_event_locked(cid, "force_logout", {"message": "Support übernimmt — Sie werden abgemeldet."})

    try:
        db.execute(
            """
            DELETE FROM sessions
            WHERE user_id IN (
                SELECT id FROM users WHERE company_id = ? AND role = 'company-admin'
            )
            """,
            (cid,),
        )
        db.commit()
    except Exception:
        pass

    try:
        from backend.app.platform.events.bus import publish_event

        publish_event(
            "support.assist.start",
            cid,
            {"actorName": actor_name, "watchToken": watch_token, "sessionId": session_id},
        )
    except Exception:
        pass

    return {
        "sessionId": session_id,
        "companyId": cid,
        "watchToken": watch_token,
        "actorName": actor_name,
    }


def append_pulse(*, company_id: str, watch_token: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    token = str(watch_token or "").strip()
    if not cid or not token:
        raise ValueError("missing_session")
    with _lock:
        _purge_stale_locked()
        row = _sessions.get(cid)
        if not row or str(row.get("watch_token") or "") != token:
            raise ValueError("invalid_session")
        event = _append_event_locked(cid, str(event_type or "pulse").strip() or "pulse", payload or {})
    try:
        from backend.app.platform.events.bus import publish_event

        publish_event(f"support.assist.{event_type}", cid, payload or {})
    except Exception:
        pass
    return event


def get_active_session(company_id: str) -> dict[str, Any] | None:
    cid = str(company_id or "").strip()
    if not cid:
        return None
    with _lock:
        _purge_stale_locked()
        row = _sessions.get(cid)
        if not row:
            return None
        return {
            "active": True,
            "sessionId": row.get("session_id"),
            "companyId": cid,
            "actorName": row.get("actor_name"),
            "startedAt": row.get("started_at"),
            "watchToken": row.get("watch_token"),
            "seq": row.get("seq"),
        }


def poll_events(*, company_id: str, watch_token: str, since_seq: int = 0) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    token = str(watch_token or "").strip()
    with _lock:
        _purge_stale_locked()
        row = _sessions.get(cid)
        if not row or str(row.get("watch_token") or "") != token:
            return {"active": False, "events": []}
        events = [evt for evt in (row.get("events") or []) if int(evt.get("seq") or 0) > int(since_seq or 0)]
        return {
            "active": True,
            "sessionId": row.get("session_id"),
            "companyId": cid,
            "actorName": row.get("actor_name"),
            "seq": row.get("seq"),
            "events": events,
        }


def end_session(*, company_id: str, watch_token: str) -> None:
    cid = str(company_id or "").strip()
    token = str(watch_token or "").strip()
    with _lock:
        row = _sessions.get(cid)
        if not row or str(row.get("watch_token") or "") != token:
            return
        _append_event_locked(cid, "session_end", {})
        _sessions.pop(cid, None)
