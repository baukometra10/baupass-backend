"""Live support assist — spectator channel shared across gunicorn workers."""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_sessions: dict[str, dict[str, Any]] = {}
_MAX_EVENTS = 80
_TTL_SECONDS = 45 * 60
_ENDED_KEEP_SECONDS = 45
# Tests set this to False so they stay in-process only.
_STORE_OVERRIDE: Path | bool | None = None
_schema_ready = False


def _now_ts() -> float:
    return time.time()


def _store_path() -> Path | None:
    if _STORE_OVERRIDE is False:
        return None
    if isinstance(_STORE_OVERRIDE, Path):
        return _STORE_OVERRIDE
    explicit = str(os.getenv("BAUPASS_DB_PATH") or "").strip().replace("\\", "/")
    if explicit:
        return Path(explicit).expanduser().resolve().parent / "support_assist.db"
    data_dir = Path("/data")
    if data_dir.is_dir() and os.access(data_dir, os.W_OK):
        return data_dir / "support_assist.db"
    return Path(__file__).resolve().parents[3] / "support_assist.db"


def _connect_store() -> sqlite3.Connection | None:
    path = _store_path()
    if path is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=4, isolation_level=None)
    con.row_factory = sqlite3.Row
    return con


def _ensure_schema(con: sqlite3.Connection) -> None:
    global _schema_ready
    if _schema_ready:
        return
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS support_assist_sessions (
            company_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            watch_token TEXT NOT NULL,
            actor_name TEXT,
            started_at REAL,
            updated_at REAL,
            seq INTEGER DEFAULT 0,
            ended INTEGER DEFAULT 0,
            ended_at REAL,
            events_json TEXT,
            last_mouse_json TEXT
        )
        """
    )
    _schema_ready = True


def _row_from_db(raw: sqlite3.Row) -> dict[str, Any]:
    try:
        events = json.loads(raw["events_json"] or "[]")
    except Exception:
        events = []
    try:
        last_mouse = json.loads(raw["last_mouse_json"] or "null")
    except Exception:
        last_mouse = None
    return {
        "session_id": raw["session_id"],
        "company_id": raw["company_id"],
        "watch_token": raw["watch_token"],
        "actor_name": raw["actor_name"] or "Support",
        "started_at": float(raw["started_at"] or 0),
        "updated_at": float(raw["updated_at"] or 0),
        "seq": int(raw["seq"] or 0),
        "ended": bool(raw["ended"]),
        "ended_at": float(raw["ended_at"] or 0),
        "events": events if isinstance(events, list) else [],
        "last_mouse": last_mouse if isinstance(last_mouse, dict) else None,
    }


def _persist_row(row: dict[str, Any]) -> None:
    try:
        con = _connect_store()
        if con is None:
            return
        with con:
            _ensure_schema(con)
            con.execute(
                """
                INSERT OR REPLACE INTO support_assist_sessions (
                    company_id, session_id, watch_token, actor_name,
                    started_at, updated_at, seq, ended, ended_at,
                    events_json, last_mouse_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("company_id"),
                    row.get("session_id"),
                    row.get("watch_token"),
                    row.get("actor_name"),
                    float(row.get("started_at") or 0),
                    float(row.get("updated_at") or 0),
                    int(row.get("seq") or 0),
                    1 if row.get("ended") else 0,
                    float(row.get("ended_at") or 0),
                    json.dumps(row.get("events") or [], ensure_ascii=False),
                    json.dumps(row.get("last_mouse"), ensure_ascii=False),
                ),
            )
        con.close()
    except Exception:
        pass


def _load_from_store(company_id: str) -> dict[str, Any] | None:
    try:
        con = _connect_store()
        if con is None:
            return None
        _ensure_schema(con)
        raw = con.execute(
            "SELECT * FROM support_assist_sessions WHERE company_id = ?",
            (company_id,),
        ).fetchone()
        con.close()
        if not raw:
            return None
        return _row_from_db(raw)
    except Exception:
        return None


def _delete_from_store(company_id: str) -> None:
    try:
        con = _connect_store()
        if con is None:
            return
        with con:
            _ensure_schema(con)
            con.execute("DELETE FROM support_assist_sessions WHERE company_id = ?", (company_id,))
        con.close()
    except Exception:
        pass


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
        _delete_from_store(cid)


def _get_row(company_id: str) -> dict[str, Any] | None:
    cid = str(company_id or "").strip()
    if not cid:
        return None
    row = _sessions.get(cid)
    if row:
        return row
    stored = _load_from_store(cid)
    if stored:
        _sessions[cid] = stored
        return stored
    return None


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
    if event_type == "mouse" and isinstance(payload, dict):
        row["last_mouse"] = payload
    return event


def start_session(db, *, company_id: str, actor_name: str) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    if not cid:
        raise ValueError("missing_company")
    watch_token = secrets.token_urlsafe(24)
    session_id = f"sas-{secrets.token_hex(8)}"
    with _lock:
        _purge_stale_locked()
        row = {
            "session_id": session_id,
            "company_id": cid,
            "watch_token": watch_token,
            "actor_name": str(actor_name or "Support").strip() or "Support",
            "started_at": _now_ts(),
            "updated_at": _now_ts(),
            "seq": 0,
            "ended": False,
            "ended_at": 0.0,
            "events": [],
            "last_mouse": None,
        }
        _sessions[cid] = row
        _append_event_locked(cid, "session_start", {"actorName": actor_name})
        _persist_row(row)

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
        row = _get_row(cid)
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
        row = _get_row(cid)
        if not row or str(row.get("watch_token") or "") != token or row.get("ended"):
            raise ValueError("invalid_session")
        kind = str(event_type or "pulse").strip() or "pulse"
        body = payload or {}
        if kind == "mouse":
            row["last_mouse"] = body
            row["updated_at"] = _now_ts()
            event = {
                "seq": int(row.get("seq") or 0),
                "type": "mouse",
                "payload": body,
                "ts": _now_ts(),
            }
        else:
            event = _append_event_locked(cid, kind, body)
        _persist_row(row)
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
        row = _get_row(cid)
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
        row = _get_row(cid)
        if not row or str(row.get("watch_token") or "") != token:
            return {"active": False, "ended": True, "events": [], "lastMouse": None}
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
            "lastMouse": row.get("last_mouse"),
        }


def end_session(*, company_id: str, watch_token: str) -> None:
    cid = str(company_id or "").strip()
    token = str(watch_token or "").strip()
    with _lock:
        row = _get_row(cid)
        if not row or str(row.get("watch_token") or "") != token:
            return
        if not row.get("ended"):
            _append_event_locked(cid, "session_end", {"restoreCustomer": True})
            row["ended"] = True
            row["ended_at"] = _now_ts()
            row["updated_at"] = _now_ts()
            _persist_row(row)
