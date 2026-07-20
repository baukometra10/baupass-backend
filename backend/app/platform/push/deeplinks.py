"""FCM data payloads with app deep links for worker mobile."""
from __future__ import annotations

_TAG_ROUTES: dict[str, str] = {
    "leave-request-status": "baupass://app/tasks",
    "leave-approved": "baupass://app/tasks",
    "leave-denied": "baupass://app/tasks",
    "document-expiry": "baupass://app/tasks",
    "attendance-reminder": "baupass://app/shifts",
    "site-checkin": "baupass://app/attendance",
    "foreman-alert": "baupass://app/profile",
    "ops-notify": "baupass://app/profile",
    "ai-briefing": "baupass://app/ai",
    "deployment-plan": "baupass://app/deployment",
    "payroll-document": "baupass://app/documents",
    "worker-document": "baupass://app/documents",
    "notification": "baupass://app/profile",
    "worker-chat": "baupass://app/chat",
    "voice-call": "baupass://app/voice-call",
    "conference-invite": "baupass://app/conference",
    "contract-sign": "baupass://app/contract-sign",
}

_PWA_TAG_PATHS: dict[str, str] = {
    "leave-request-status": "/emp-app.html#leave",
    "leave-approved": "/emp-app.html#leave",
    "leave-denied": "/emp-app.html#leave",
    "document-expiry": "/emp-app.html#leave",
    "deployment-plan": "/emp-app.html#einsatzplan",
    "payroll-document": "/emp-app.html#documents",
    "worker-document": "/emp-app.html#documents",
    "worker-chat": "/emp-app.html#chat",
    "voice-call": "/emp-app.html#chat",
    "conference-invite": "/emp-app.html#chat",
    "contract-sign": "/emp-app.html#documents",
    "notification": "/emp-app.html",
}


def pwa_path_for_tag(tag: str) -> str:
    return _PWA_TAG_PATHS.get(str(tag or "").strip(), "/emp-app.html")


def push_data_payload(*, tag: str, worker_id: str, extra: dict | None = None) -> dict[str, str]:
    route = _TAG_ROUTES.get(tag, "baupass://app/profile")
    if tag == "voice-call" and extra:
        call_id = str(extra.get("callId") or extra.get("call_id") or "").strip()
        if call_id:
            route = f"baupass://app/voice-call?callId={call_id}"
    if tag == "conference-invite" and extra:
        room_id = str(extra.get("roomId") or extra.get("room_id") or "").strip()
        if room_id:
            route = f"baupass://app/conference?roomId={room_id}"
    data = {
        "tag": tag,
        "workerId": str(worker_id),
        "route": route,
        "deeplink": route,
        "url": pwa_path_for_tag(tag),
    }
    if extra:
        for k, v in extra.items():
            data[str(k)] = str(v)[:200]
    return data
