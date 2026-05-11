from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def push_dead_letter_event(redis_conn: Any, *, job_id: str, func_name: str, queue_name: str, error: str) -> None:
    """Stores a capped dead-letter stream for operational visibility."""
    payload = {
        "at": _utc_now_iso(),
        "job_id": job_id,
        "func": func_name,
        "queue": queue_name,
        "error": error[:2000],
    }
    key = "baupass:dlq:events"
    redis_conn.lpush(key, json.dumps(payload, separators=(",", ":")))
    redis_conn.ltrim(key, 0, 4999)
