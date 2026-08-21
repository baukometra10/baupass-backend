"""Zapier / Make iPaaS surface — triggers, actions, signed webhook subscriptions."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any


def zapier_feature_enabled() -> bool:
    return (os.getenv("BAUPASS_ZAPIER_ENABLED") or "0").strip().lower() in {"1", "true", "yes"}


def ensure_ipaas_schema(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS ipaas_subscriptions (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            event_type TEXT NOT NULL,
            target_url TEXT NOT NULL,
            secret TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_delivery_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    db.commit()


def list_triggers() -> list[dict[str, Any]]:
    return [
        {"key": "worker.created", "label": "Worker created", "direction": "trigger"},
        {"key": "access.checkin", "label": "Access check-in", "direction": "trigger"},
        {"key": "leave.requested", "label": "Leave requested", "direction": "trigger"},
        {"key": "invoice.paid", "label": "Invoice paid", "direction": "trigger"},
    ]


def list_actions() -> list[dict[str, Any]]:
    return [
        {"key": "worker.upsert", "label": "Upsert worker", "direction": "action"},
        {"key": "leave.create", "label": "Create leave request", "direction": "action"},
    ]


def create_subscription(
    db,
    *,
    company_id: str,
    provider: str,
    event_type: str,
    target_url: str,
) -> dict[str, Any]:
    ensure_ipaas_schema(db)
    cid = str(company_id or "").strip()
    url = str(target_url or "").strip()
    event = str(event_type or "").strip()
    if not cid or not url or not event:
        return {"ok": False, "error": "missing_fields"}
    from backend.app.platform.security.outbound_url import assert_safe_outbound_url

    safe = assert_safe_outbound_url(url, require_https=True)
    if not safe.get("ok"):
        return {"ok": False, "error": str(safe.get("error") or "unsafe_url")}
    sub_id = f"ipaas-{secrets.token_hex(8)}"
    secret = secrets.token_urlsafe(24)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    db.execute(
        """
        INSERT INTO ipaas_subscriptions
        (id, company_id, provider, event_type, target_url, secret, active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (sub_id, cid, str(provider or "zapier"), event, url, secret, now),
    )
    db.commit()
    return {"ok": True, "id": sub_id, "secret": secret, "eventType": event, "targetUrl": url}


def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def deliver_event(db, *, company_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Fan-out signed POSTs to active Zapier/Make subscriptions."""
    from urllib import request as urlrequest

    from backend.app.platform.security.outbound_url import assert_safe_outbound_url

    ensure_ipaas_schema(db)
    rows = db.execute(
        """
        SELECT id, target_url, secret FROM ipaas_subscriptions
        WHERE company_id = ? AND event_type = ? AND active = 1
        """,
        (str(company_id), str(event_type)),
    ).fetchall()
    body = json.dumps({"event": event_type, "companyId": company_id, "data": payload}, ensure_ascii=False).encode("utf-8")
    delivered = 0
    errors: list[str] = []
    for row in rows:
        target = str(row["target_url"])
        safe = assert_safe_outbound_url(target, require_https=True)
        if not safe.get("ok"):
            errors.append(f"{row['id']}:unsafe_url")
            continue
        sig = sign_payload(str(row["secret"]), body)
        req = urlrequest.Request(
            target,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Baupass-Signature": sig,
                "X-Baupass-Event": str(event_type),
            },
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=12) as resp:
                if 200 <= resp.status < 300:
                    delivered += 1
                    db.execute(
                        "UPDATE ipaas_subscriptions SET last_delivery_at = ? WHERE id = ?",
                        (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), row["id"]),
                    )
                else:
                    errors.append(f"{row['id']}:{resp.status}")
        except Exception as exc:
            errors.append(f"{row['id']}:{exc}")
    try:
        db.commit()
    except Exception:
        pass
    return {"ok": not errors, "delivered": delivered, "errors": errors}


def ipaas_catalog() -> dict[str, Any]:
    return {
        "provider": "zapier_make",
        "featureEnabled": zapier_feature_enabled(),
        "triggers": list_triggers(),
        "actions": list_actions(),
        "auth": "api_key_or_session",
        "docs": "docs/integrations/zapier-make.md",
    }
