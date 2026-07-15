"""Web push delivery for admin users (PWA / mobile browser)."""
from __future__ import annotations

import json
import os
from typing import Any


def deliver_admin_push(
    db,
    company_id: str,
    title: str,
    body: str,
    *,
    tag: str = "admin-chat",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send VAPID web push to subscribed company admins."""
    vapid_private_key = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    vapid_email = (
        os.getenv("VAPID_EMAIL", "").strip()
        or os.getenv("VAPID_SUBJECT", "").strip()
        or "mailto:admin@example.com"
    )
    if not vapid_private_key or not vapid_email:
        return {"ok": False, "sent": 0, "reason": "vapid_not_configured"}

    try:
        from backend.server import _load_pywebpush_client

        webpush, _ = _load_pywebpush_client()
    except Exception:
        webpush = None
    if not callable(webpush):
        return {"ok": False, "sent": 0, "reason": "pywebpush_missing"}

    rows = db.execute(
        """
        SELECT endpoint, p256dh, auth
        FROM admin_push_subscriptions
        WHERE company_id = ?
        """,
        (str(company_id or ""),),
    ).fetchall()
    if not rows:
        return {"ok": True, "sent": 0, "reason": "no_subscriptions"}

    payload = {
        "title": title,
        "body": body,
        "tag": tag,
        "url": "/admin-v2/chat.html",
        **(extra or {}),
    }
    sent = 0
    removed = 0
    for row in rows:
        endpoint = str(row["endpoint"] or "").strip()
        if not endpoint:
            continue
        try:
            webpush(
                subscription_info={
                    "endpoint": endpoint,
                    "keys": {"p256dh": row["p256dh"], "auth": row["auth"]},
                },
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": vapid_email},
            )
            sent += 1
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is None:
                status = getattr(exc, "status_code", None)
            if status in (404, 410):
                try:
                    db.execute(
                        "DELETE FROM admin_push_subscriptions WHERE endpoint = ?",
                        (endpoint,),
                    )
                    removed += 1
                except Exception:
                    pass
            continue
    if removed:
        try:
            db.commit()
        except Exception:
            pass
    return {"ok": True, "sent": sent, "removed": removed}
