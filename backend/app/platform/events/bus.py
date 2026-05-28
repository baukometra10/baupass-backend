"""
Event bus — Redis pub/sub when available, SQLite event log always.

Hot-path rule: persist synchronously; side effects (webhooks, automation, WS) run in
a background thread so gate taps and API responses stay fast.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("baupass.events")

CHANNEL_PREFIX = "baupass:events"

try:
    from backend.app.platform.observability.metrics import EVENTS_PUBLISHED
except Exception:
    EVENTS_PUBLISHED = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def publish_event(
    event_type: str,
    company_id: str | int | None,
    payload: dict[str, Any] | None = None,
    *,
    actor_id: str | None = None,
) -> str:
    """Publish a domain event to the bus and persistent log."""
    event_id = f"evt-{uuid.uuid4().hex[:16]}"
    body = {
        "id": event_id,
        "type": event_type,
        "company_id": company_id,
        "actor_id": actor_id,
        "payload": payload or {},
        "created_at": _now_iso(),
    }
    if EVENTS_PUBLISHED is not None:
        try:
            EVENTS_PUBLISHED.labels(event_type=event_type).inc()
        except Exception:
            pass

    _persist_event(body)

    def _side_effects() -> None:
        _redis_publish(body)
        _websocket_broadcast(body)
        if company_id is not None:
            try:
                from backend.app.platform.enterprise.automation_engine import evaluate_event
                from backend.server import get_db

                evaluate_event(get_db(), str(company_id), event_type, payload or {})
            except Exception as exc:
                logger.debug("automation evaluate skipped: %s", exc)
        try:
            from backend.app.platform.api_platform.webhooks import schedule_webhook_deliveries

            schedule_webhook_deliveries(event_type, company_id, body)
        except Exception as exc:
            logger.debug("webhook scheduling skipped: %s", exc)

    threading.Thread(target=_side_effects, daemon=True, name=f"evt-{event_id[:8]}").start()
    return event_id


def _persist_event(body: dict[str, Any]) -> None:
    try:
        from backend.server import get_db

        db = get_db()
        db.execute(
            """
            INSERT INTO platform_events (id, event_type, company_id, actor_id, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                body["id"],
                body["type"],
                body.get("company_id"),
                body.get("actor_id"),
                json.dumps(body.get("payload") or {}, ensure_ascii=False),
                body["created_at"],
            ),
        )
        db.commit()
    except Exception as exc:
        logger.debug("platform_events persist skipped: %s", exc)


def _redis_publish(body: dict[str, Any]) -> None:
    try:
        from backend.app.extensions import get_redis

        redis = get_redis()
        if not redis:
            return
        message = json.dumps(body, ensure_ascii=False)
        company_id = body.get("company_id")
        redis.publish(f"{CHANNEL_PREFIX}:all", message)
        if company_id is not None:
            redis.publish(f"{CHANNEL_PREFIX}:company:{company_id}", message)
        # Dedicated low-latency channel for live workforce tracking consumers.
        if str(body.get("type", "")).startswith("access."):
            redis.publish(
                f"{CHANNEL_PREFIX}:workforce:tracking",
                json.dumps(
                    {
                        "id": body.get("id"),
                        "type": body.get("type"),
                        "company_id": company_id,
                        "created_at": body.get("created_at"),
                        "payload": body.get("payload") or {},
                    },
                    ensure_ascii=False,
                ),
            )
    except Exception as exc:
        logger.debug("redis publish skipped: %s", exc)


def _websocket_broadcast(body: dict[str, Any]) -> None:
    try:
        from backend.app.platform.realtime.websocket import broadcast_event

        broadcast_event(body.get("company_id"), body)
    except Exception as exc:
        logger.debug("websocket broadcast skipped: %s", exc)


def list_recent_events(company_id: str | int | None, limit: int = 50, since_id: str | None = None) -> list[dict]:
    try:
        from backend.app.db.connection import get_read_connection

        with get_read_connection() as db:
            return _list_recent_events_with_db(db, company_id, limit, since_id)
    except Exception as exc:
        logger.debug("list_recent_events failed: %s", exc)
        return []


def _list_recent_events_with_db(db, company_id: str | int | None, limit: int, since_id: str | None) -> list[dict]:
    try:
        params: list[Any] = []
        where = "1=1"
        if company_id is not None:
            where += " AND (company_id = ? OR company_id IS NULL)"
            params.append(company_id)
        if since_id:
            row = db.execute("SELECT created_at FROM platform_events WHERE id = ?", (since_id,)).fetchone()
            if row:
                where += " AND created_at > ?"
                params.append(row["created_at"])
        params.append(max(1, min(limit, 200)))
        rows = db.execute(
            f"""
            SELECT id, event_type, company_id, actor_id, payload_json, created_at
            FROM platform_events
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        out = []
        for row in rows:
            out.append(
                {
                    "id": row["id"],
                    "type": row["event_type"],
                    "company_id": row["company_id"],
                    "actor_id": row["actor_id"],
                    "payload": json.loads(row["payload_json"] or "{}"),
                    "created_at": row["created_at"],
                }
            )
        return list(reversed(out))
    except Exception as exc:
        logger.debug("_list_recent_events_with_db failed: %s", exc)
        return []


def generate_webhook_secret() -> str:
    return secrets.token_urlsafe(32)
