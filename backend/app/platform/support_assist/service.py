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
_ENDED_KEEP_SECONDS = 45


def _now_ts() -> float:
    return time.time()


def _purge_stale_locked() -> None:
    now = _now_ts()
    cutoff = now - _TTL_SECONDS
    ended_cutoff = now - _ENDED_KEEP_SECONDS
    stale = []
    for cid, row in _sessions.items():
        if row.get("ended"):
            if float(row.get("ended_at") or 0) < ended_cutoff:
                stale.append(cid)
        elif float(row.get("updated_at") or 0) < cutoff:
            stale.append(cid)
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

    # Keep company-admin sessions so the customer can attach as spectator
    # and see cursor/views live. Kicking them to login hid the watch token.

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


def get_watch_session(company_id: str, watch_token: str) -> dict[str, Any] | None:
    cid = str(company_id or "").strip()
    token = str(watch_token or "").strip()
    if not cid or not token:
        return None
    with _lock:
        _purge_stale_locked()
        row = _sessions.get(cid)
        if not row or str(row.get("watch_token") or "") != token:
            return None
        if row.get("ended"):
            return None
        return {
            "companyId": cid,
            "actorName": row.get("actor_name") or "Support",
            "sessionId": row.get("session_id"),
        }


def append_pulse(*, company_id: str, watch_token: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    token = str(watch_token or "").strip()
    if not cid or not token:
        raise ValueError("missing_session")
    with _lock:
        _purge_stale_locked()
        row = _sessions.get(cid)
        if not row or str(row.get("watch_token") or "") != token or row.get("ended"):
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
        if not row or row.get("ended"):
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
            return {"active": False, "ended": True, "events": []}
        events = [evt for evt in (row.get("events") or []) if int(evt.get("seq") or 0) > int(since_seq or 0)]
        ended = bool(row.get("ended"))
        return {
            "active": not ended,
            "ended": ended,
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
        if not row.get("ended"):
            _append_event_locked(cid, "session_end", {"restoreCustomer": True})
            row["ended"] = True
            row["ended_at"] = _now_ts()
            row["updated_at"] = _now_ts()
