"""Ephemeral chat typing indicators (in-memory, TTL)."""
from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_typing: dict[str, dict[str, Any]] = {}
_TTL_SEC = 5.0


def _entry_key(thread_id: str, actor_type: str, actor_id: str) -> str:
    return f"{thread_id}:{actor_type}:{actor_id}"


def _purge_expired(now: float | None = None) -> None:
    ts = now if now is not None else time.time()
    expired = [key for key, row in _typing.items() if float(row.get("expires") or 0) < ts]
    for key in expired:
        _typing.pop(key, None)


def set_typing(
    *,
    thread_id: str,
    company_id: str,
    worker_id: str,
    actor_type: str,
    actor_id: str,
    actor_label: str = "",
) -> None:
    now = time.time()
    key = _entry_key(thread_id, actor_type, actor_id)
    with _lock:
        _purge_expired(now)
        _typing[key] = {
            "threadId": thread_id,
            "companyId": company_id,
            "workerId": worker_id,
            "actorType": actor_type,
            "actorId": actor_id,
            "actorLabel": actor_label,
            "expires": now + _TTL_SEC,
        }
    try:
        from backend.app.platform.events.bus import publish_event

        publish_event(
            "chat.typing",
            company_id,
            {
                "threadId": thread_id,
                "workerId": worker_id,
                "actorType": actor_type,
                "actorId": actor_id,
                "actorLabel": actor_label,
            },
            actor_id=actor_id,
        )
    except Exception:
        pass


def list_typing(
    thread_id: str,
    *,
    exclude_actor_type: str | None = None,
    exclude_actor_id: str | None = None,
) -> list[dict[str, str]]:
    now = time.time()
    with _lock:
        _purge_expired(now)
        rows: list[dict[str, str]] = []
        for row in _typing.values():
            if str(row.get("threadId") or "") != thread_id:
                continue
            actor_type = str(row.get("actorType") or "")
            actor_id = str(row.get("actorId") or "")
            if exclude_actor_type and exclude_actor_id:
                if actor_type == exclude_actor_type and actor_id == exclude_actor_id:
                    continue
            rows.append(
                {
                    "actorType": actor_type,
                    "actorId": actor_id,
                    "actorLabel": str(row.get("actorLabel") or ""),
                }
            )
        return rows
