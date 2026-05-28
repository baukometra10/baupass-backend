"""SSE stream of recent platform / access events for ops dashboards."""
from __future__ import annotations

import json
import time
from typing import Any, Generator


def _fetch_recent_events(db, company_id: str | None, limit: int = 25) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        if company_id:
            from backend.app.platform.events.bus import list_recent_events

            events = list_recent_events(company_id, limit=limit)
        else:
            rows = db.execute(
                """
                SELECT company_id, event_type, payload_json, created_at
                FROM platform_events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            for r in rows:
                payload = {}
                try:
                    payload = json.loads(r["payload_json"] or "{}")
                except Exception:
                    pass
                events.append(
                    {
                        "companyId": r["company_id"],
                        "type": r["event_type"],
                        "payload": payload,
                        "at": r["created_at"],
                    }
                )
    except Exception:
        pass

    try:
        today = time.strftime("%Y-%m-%d")
        q = """
            SELECT al.timestamp, al.action, al.gate, w.first_name, w.last_name, w.company_id
            FROM access_logs al
            JOIN workers w ON w.id = al.worker_id
            WHERE al.timestamp LIKE ?
        """
        params: list[Any] = [f"{today}%"]
        if company_id:
            q += " AND w.company_id = ?"
            params.append(company_id)
        q += " ORDER BY al.timestamp DESC LIMIT 15"
        rows = db.execute(q, tuple(params)).fetchall()
        for r in rows:
            name = f"{r['first_name']} {r['last_name']}".strip()
            events.insert(
                0,
                {
                    "type": "access",
                    "action": r["action"],
                    "gate": r["gate"],
                    "worker": name,
                    "companyId": r["company_id"],
                    "at": r["timestamp"],
                },
            )
    except Exception:
        pass
    return events[:limit]


def stream_ops_events(db, company_id: str | None, *, interval_sec: float = 12.0) -> Generator[str, None, None]:
    """Yield SSE lines for EventSource clients."""
    last_sig = ""
    while True:
        batch = _fetch_recent_events(db, company_id)
        sig = json.dumps(batch[:5], sort_keys=True, default=str)
        if sig != last_sig:
            payload = json.dumps({"type": "events", "items": batch, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ")}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            last_sig = sig
        else:
            yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        time.sleep(interval_sec)
