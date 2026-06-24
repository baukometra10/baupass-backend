"""
Outbound webhooks — register endpoints, sign payloads, deliver with retry.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib import request as urlrequest

from backend.app.platform.observability.metrics import WEBHOOK_DELIVERIES

logger = logging.getLogger("baupass.webhooks")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def _retry_iso(attempt: int) -> str:
    delay = min(900, 30 * (2 ** max(0, attempt - 1)))
    return (datetime.now(timezone.utc) + timedelta(seconds=delay)).strftime("%Y-%m-%dT%H:%M:%fZ")


def create_webhook_endpoint(
    db,
    *,
    company_id: str,
    url: str,
    events: list[str],
    secret: str | None = None,
) -> dict[str, Any]:
    from backend.app.platform.events.bus import generate_webhook_secret

    endpoint_id = f"wh-{uuid.uuid4().hex[:12]}"
    wh_secret = secret or generate_webhook_secret()
    db.execute(
        """
        INSERT INTO webhook_endpoints (id, company_id, url, secret, events_json, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'active', ?)
        """,
        (endpoint_id, company_id, url.strip(), wh_secret, json.dumps(events), _now_iso()),
    )
    db.commit()
    return {"id": endpoint_id, "url": url, "events": events, "secret": wh_secret}


def list_webhook_endpoints(db, company_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT id, company_id, url, events_json, status, created_at
        FROM webhook_endpoints
        WHERE company_id = ?
        ORDER BY created_at DESC
        """,
        (company_id,),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["events"] = json.loads(item.pop("events_json") or "[]")
        out.append(item)
    return out


def delete_webhook_endpoint(db, company_id: str, endpoint_id: str) -> bool:
    cur = db.execute(
        "UPDATE webhook_endpoints SET status = 'disabled' WHERE id = ? AND company_id = ?",
        (endpoint_id, company_id),
    )
    db.commit()
    return cur.rowcount > 0


def schedule_webhook_deliveries(event_type: str, company_id: str | int | None, body: dict[str, Any]) -> None:
    if company_id is None:
        return
    try:
        from backend.server import get_db

        db = get_db()
        rows = db.execute(
            """
            SELECT id, url, secret, events_json
            FROM webhook_endpoints
            WHERE company_id = ? AND status = 'active'
            """,
            (company_id,),
        ).fetchall()
        for row in rows:
            events = json.loads(row["events_json"] or "[]")
            if events and event_type not in events and "*" not in events:
                continue
            delivery_id = f"whd-{uuid.uuid4().hex[:14]}"
            db.execute(
                """
                INSERT INTO webhook_deliveries
                    (id, endpoint_id, company_id, event_type, payload_json, status, attempt_count, next_retry_at, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?)
                """,
                (
                    delivery_id,
                    row["id"],
                    company_id,
                    event_type,
                    json.dumps(body, ensure_ascii=False),
                    _now_iso(),
                    _now_iso(),
                ),
            )
        db.commit()
        _enqueue_pending_deliveries(company_id)
    except Exception as exc:
        logger.warning("schedule_webhook_deliveries failed: %s", exc)


def _enqueue_pending_deliveries(company_id: str) -> None:
    try:
        from backend.app.tasks import enqueue

        enqueue("low", process_webhook_delivery_batch, company_id=company_id)
    except Exception:
        process_webhook_delivery_batch(company_id=company_id)


def process_webhook_delivery_batch(company_id: str, limit: int = 20) -> dict[str, int]:
    from backend.server import get_db

    db = get_db()
    rows = db.execute(
        """
        SELECT d.id, d.endpoint_id, d.payload_json, d.attempt_count, e.url, e.secret
        FROM webhook_deliveries d
        JOIN webhook_endpoints e ON e.id = d.endpoint_id
        WHERE d.company_id = ? AND d.status IN ('pending', 'retry')
          AND (d.next_retry_at IS NULL OR d.next_retry_at <= ?)
        ORDER BY d.created_at ASC
        LIMIT ?
        """,
        (company_id, _now_iso(), limit),
    ).fetchall()
    ok = failed = 0
    for row in rows:
        success = _deliver_one(db, row)
        if success:
            ok += 1
        else:
            failed += 1
    return {"delivered": ok, "failed": failed}


def _sign_payload(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _deliver_one(db, row) -> bool:
    delivery_id = row["id"]
    payload_bytes = (row["payload_json"] or "{}").encode("utf-8")
    signature = _sign_payload(row["secret"], payload_bytes)
    attempt = int(row["attempt_count"] or 0) + 1
    status_code = 0
    response_body = ""
    try:
        req = urlrequest.Request(
            row["url"],
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-SUPPIX-Signature": f"sha256={signature}",
                "X-SUPPIX-Delivery": delivery_id,
            },
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=15) as resp:
            status_code = resp.status
            response_body = (resp.read(2048) or b"").decode("utf-8", errors="replace")
        if 200 <= status_code < 300:
            db.execute(
                """
                UPDATE webhook_deliveries
                SET status = 'delivered', attempt_count = ?, response_status = ?, response_body = ?, completed_at = ?
                WHERE id = ?
                """,
                (attempt, status_code, response_body[:2000], _now_iso(), delivery_id),
            )
            db.commit()
            WEBHOOK_DELIVERIES.labels(status="delivered").inc()
            return True
    except Exception as exc:
        response_body = str(exc)[:2000]

    new_status = "retry" if attempt < 5 else "failed"
    db.execute(
        """
        UPDATE webhook_deliveries
        SET status = ?, attempt_count = ?, next_retry_at = ?, response_status = ?, response_body = ?
        WHERE id = ?
        """,
        (new_status, attempt, _retry_iso(attempt), status_code, response_body[:2000], delivery_id),
    )
    db.commit()
    WEBHOOK_DELIVERIES.labels(status=new_status).inc()
    return False
