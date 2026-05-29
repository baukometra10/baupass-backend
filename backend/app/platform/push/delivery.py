"""Worker push delivery — FCM/APNs first (Flutter hybrid), Web Push legacy."""
from __future__ import annotations

import json
import os
from typing import Any


def push_platform_status() -> dict[str, Any]:
    from .fcm import fcm_configured, fcm_mode, fcm_v1_only

    vapid = bool(os.getenv("VAPID_PRIVATE_KEY", "").strip())
    fcm = fcm_configured()
    mode = fcm_mode()
    return {
        "workerAppKind": "hybrid_native",
        "primaryChannel": "fcm",
        "fcmConfigured": fcm,
        "fcmMode": mode,
        "fcmV1Only": fcm_v1_only(),
        "webPushConfigured": vapid,
        "legacyWebPush": vapid,
        "anyChannelReady": fcm or vapid,
        "recommendedForWorkers": "fcm",
    }


def deliver_worker_push(
    db,
    worker_id: str,
    title: str,
    body: str,
    *,
    tag: str = "notification",
    company_id: str | None = None,
) -> dict[str, Any]:
    """Send push to worker devices (FCM first, legacy Web Push fallback)."""
    web_push = 0
    fcm = 0

    try:
        from .fcm import send_fcm_notification
        from .deeplinks import push_data_payload

        native_rows = db.execute(
            """
            SELECT push_token FROM worker_bound_devices
            WHERE worker_id = ? AND status = 'active' AND push_token IS NOT NULL AND push_token != ''
            """,
            (worker_id,),
        ).fetchall()
        tokens = list({str(r["push_token"]).strip() for r in native_rows if r["push_token"]})
        if tokens:
            fcm = send_fcm_notification(
                tokens,
                title=title,
                body=body,
                data=push_data_payload(tag=tag, worker_id=str(worker_id)),
            )
    except Exception:
        pass

    if fcm <= 0:
        try:
            from backend.server import _load_pywebpush_client

            webpush, _ = _load_pywebpush_client()
            vapid_private_key = os.getenv("VAPID_PRIVATE_KEY", "").strip()
            vapid_email = (
                os.getenv("VAPID_EMAIL")
                or os.getenv("BAUPASS_CONTACT_EMAIL")
                or ""
            ).strip()
            if not vapid_email:
                vapid_email = ""
            if callable(webpush) and vapid_private_key and vapid_email:
                from .deeplinks import push_data_payload

                payload = push_data_payload(tag=tag, worker_id=str(worker_id))
                subs = db.execute(
                    "SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE worker_id = ?",
                    (worker_id,),
                ).fetchall()
                for sub in subs:
                    try:
                        webpush(
                            subscription_info={
                                "endpoint": sub["endpoint"],
                                "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                            },
                            data=json.dumps(
                                {
                                    "title": title,
                                    "body": body,
                                    "tag": tag,
                                    "route": payload.get("route"),
                                    "deeplink": payload.get("deeplink"),
                                }
                            ),
                            vapid_private_key=vapid_private_key,
                            vapid_claims={"sub": vapid_email},
                        )
                        web_push += 1
                    except Exception:
                        pass
        except Exception:
            pass

    channels: list[str] = []
    if web_push:
        channels.append("web_push")
    if fcm:
        channels.append("fcm")
    total = web_push + fcm

    if total > 0:
        try:
            from backend.app.platform.realtime.websocket import broadcast_event

            cid = company_id
            if not cid:
                row = db.execute("SELECT company_id FROM workers WHERE id = ?", (worker_id,)).fetchone()
                cid = str(row["company_id"]) if row else None
            broadcast_event(
                cid,
                {
                    "type": "push_sent",
                    "workerId": worker_id,
                    "tag": tag,
                    "channels": channels,
                    "total": total,
                },
            )
        except Exception:
            pass

    return {
        "delivered": total > 0,
        "pushSent": total,
        "webPush": web_push,
        "fcm": fcm,
        "channels": channels,
        "hint": None
        if total > 0
        else "Kein FCM-Token — in der Hybrid-App (Flutter) unter Profil Push aktivieren.",
    }
