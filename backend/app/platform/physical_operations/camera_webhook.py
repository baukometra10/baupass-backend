"""Signed security webhooks + retry queue for camera watch. Never auto-dials police."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ._common import now_iso


def sign_webhook_body(secret: str, body: bytes) -> str:
    """Return X-WorkPass-Signature value: sha256=<hex>."""
    dig = hmac.new(str(secret or "").encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={dig}"


def build_webhook_headers(
    *,
    body: bytes,
    secret: str = "",
    event: str = "camera.critical_escalation",
    delivery_id: str = "",
) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "X-WorkPass-Event": str(event or "camera.event")[:120],
        "X-WorkPass-Delivery-Id": str(delivery_id or f"cwd-{uuid.uuid4().hex[:12]}")[:80],
    }
    if str(secret or "").strip():
        headers["X-WorkPass-Signature"] = sign_webhook_body(secret, body)
    return headers


def post_signed_webhook(
    url: str,
    payload: dict[str, Any],
    *,
    secret: str = "",
    event: str = "camera.critical_escalation",
    delivery_id: str = "",
    timeout: float = 8.0,
) -> tuple[bool, str, str]:
    """POST JSON with optional HMAC signature. Returns (ok, delivery_id, error)."""
    if not str(url or "").startswith("http"):
        return False, "", "invalid_url"
    did = str(delivery_id or f"cwd-{uuid.uuid4().hex[:12]}")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = build_webhook_headers(body=body, secret=secret, event=event, delivery_id=did)
    try:
        req = Request(str(url), data=body, headers=headers, method="POST")
        with urlopen(req, timeout=timeout) as resp:
            ok = 200 <= int(resp.status) < 300
            if ok:
                return True, did, ""
            return False, did, f"http_{resp.status}"
    except HTTPError as exc:
        return False, did, f"http_{getattr(exc, 'code', 'err')}"
    except URLError as exc:
        return False, did, f"timeout_or_network:{exc.reason}"
    except Exception as exc:
        return False, did, str(exc)[:300]


def _backoff_seconds(attempts: int) -> int:
    # 30, 60, 120, 240… capped at 1h
    return min(3600, 30 * (2 ** max(0, int(attempts) - 1)))


def enqueue_webhook_delivery(
    db,
    *,
    company_id: str,
    url: str,
    payload: dict[str, Any],
    escalation_id: str = "",
    attempts: int = 0,
    last_error: str = "",
    status: str = "pending",
) -> str | None:
    did = f"cwd-{uuid.uuid4().hex[:12]}"
    ts = now_iso()
    next_at = (datetime.now(timezone.utc) + timedelta(seconds=_backoff_seconds(max(1, attempts)))).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    try:
        db.execute(
            """
            INSERT INTO camera_webhook_deliveries (
                id, company_id, escalation_id, url, status, attempts,
                last_error, next_retry_at, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                did,
                str(company_id),
                str(escalation_id or ""),
                str(url or "")[:500],
                str(status or "pending")[:40],
                int(attempts),
                str(last_error or "")[:500],
                next_at,
                json.dumps(payload or {}, ensure_ascii=False),
                ts,
                ts,
            ),
        )
        db.commit()
        return did
    except Exception:
        return None


def deliver_or_enqueue_webhook(
    db,
    *,
    company_id: str,
    url: str,
    payload: dict[str, Any],
    secret: str = "",
    event: str = "camera.critical_escalation",
    escalation_id: str = "",
    retry_max: int = 3,
) -> dict[str, Any]:
    """Try once; on failure enqueue for background retry (up to retry_max)."""
    ok, did, err = post_signed_webhook(
        url,
        payload,
        secret=secret,
        event=event,
        timeout=8.0,
    )
    if ok:
        return {"ok": True, "deliveryId": did, "queued": False, "autoDial": False}
    retry_max = max(0, min(20, int(retry_max or 0)))
    queued_id = None
    if retry_max > 0:
        queued_id = enqueue_webhook_delivery(
            db,
            company_id=company_id,
            url=url,
            payload=payload,
            escalation_id=escalation_id,
            attempts=1,
            last_error=err or "delivery_failed",
            status="pending",
        )
        # Persist secret/event on payload envelope for retry job
        if queued_id:
            try:
                wrapped = dict(payload or {})
                wrapped["_meta"] = {
                    "event": event,
                    "secret": str(secret or ""),
                    "retryMax": retry_max,
                }
                db.execute(
                    "UPDATE camera_webhook_deliveries SET payload_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(wrapped, ensure_ascii=False), now_iso(), queued_id),
                )
                db.commit()
            except Exception:
                pass
    return {
        "ok": False,
        "deliveryId": did or queued_id,
        "queued": bool(queued_id),
        "error": err,
        "autoDial": False,
    }


def run_camera_webhook_retries(db) -> dict[str, Any]:
    """Retry pending webhook deliveries with exponential backoff."""
    if str(os.getenv("BAUPASS_CAMERA_WEBHOOK_RETRY_JOB", "1")).strip().lower() in {
        "0",
        "false",
        "off",
        "no",
    }:
        return {"ok": True, "skipped": True, "reason": "disabled", "autoDial": False}

    now_s = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    processed = 0
    sent = 0
    failed = 0
    dead = 0
    try:
        rows = db.execute(
            """
            SELECT * FROM camera_webhook_deliveries
            WHERE status = 'pending'
              AND next_retry_at IS NOT NULL
              AND next_retry_at <= ?
            ORDER BY next_retry_at ASC
            LIMIT 40
            """,
            (now_s,),
        ).fetchall()
    except Exception as exc:
        return {"ok": False, "error": str(exc), "autoDial": False}

    for row in rows:
        processed += 1
        try:
            payload = {}
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except Exception:
                payload = {}
            meta = payload.pop("_meta", {}) if isinstance(payload, dict) else {}
            if not isinstance(meta, dict):
                meta = {}
            secret = str(meta.get("secret") or "")
            event = str(meta.get("event") or "camera.critical_escalation")
            try:
                retry_max = max(1, min(20, int(meta.get("retryMax") or 3)))
            except Exception:
                retry_max = 3
            attempts = int(row["attempts"] or 0) + 1
            ok, _did, err = post_signed_webhook(
                str(row["url"] or ""),
                payload if isinstance(payload, dict) else {},
                secret=secret,
                event=event,
                delivery_id=str(row["id"]),
            )
            ts = now_iso()
            if ok:
                db.execute(
                    """
                    UPDATE camera_webhook_deliveries
                    SET status = 'sent', attempts = ?, last_error = '', updated_at = ?, next_retry_at = NULL
                    WHERE id = ?
                    """,
                    (attempts, ts, str(row["id"])),
                )
                db.commit()
                sent += 1
                continue
            if attempts >= retry_max:
                db.execute(
                    """
                    UPDATE camera_webhook_deliveries
                    SET status = 'failed', attempts = ?, last_error = ?, updated_at = ?, next_retry_at = NULL
                    WHERE id = ?
                    """,
                    (attempts, str(err or "max_retries")[:500], ts, str(row["id"])),
                )
                db.commit()
                dead += 1
            else:
                next_at = (
                    datetime.now(timezone.utc) + timedelta(seconds=_backoff_seconds(attempts))
                ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                # Keep _meta for subsequent retries
                store = dict(payload) if isinstance(payload, dict) else {}
                store["_meta"] = meta
                db.execute(
                    """
                    UPDATE camera_webhook_deliveries
                    SET status = 'pending', attempts = ?, last_error = ?, next_retry_at = ?,
                        payload_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        attempts,
                        str(err or "delivery_failed")[:500],
                        next_at,
                        json.dumps(store, ensure_ascii=False),
                        ts,
                        str(row["id"]),
                    ),
                )
                db.commit()
                failed += 1
        except Exception:
            failed += 1

    return {
        "ok": True,
        "processed": processed,
        "sent": sent,
        "requeued": failed,
        "failed": dead,
        "autoDial": False,
        "checkedAt": now_iso(),
    }


def fire_test_webhook(
    db,
    company_id: str,
    *,
    url: str | None = None,
    secret: str | None = None,
    watch_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send a sample webhook payload only (no escalation)."""
    from .camera_watch import resolve_watch_settings

    cfg = watch_cfg or resolve_watch_settings(db, company_id)
    target = str(url or cfg.get("securityWebhookUrl") or "").strip()
    sec = str(secret if secret is not None else cfg.get("webhookSecret") or "").strip()
    if not target.startswith("http"):
        return {"ok": False, "error": "webhook_url_required", "autoDial": False}
    payload = {
        "type": "camera.test_webhook",
        "companyId": str(company_id),
        "test": True,
        "autoDial": False,
        "message": "WorkPass camera watch test webhook",
        "ts": now_iso(),
    }
    ok, did, err = post_signed_webhook(
        target,
        payload,
        secret=sec,
        event="camera.test_webhook",
    )
    return {
        "ok": ok,
        "deliveryId": did,
        "error": err or None,
        "url": target,
        "signed": bool(sec),
        "test": True,
        "autoDial": False,
    }
