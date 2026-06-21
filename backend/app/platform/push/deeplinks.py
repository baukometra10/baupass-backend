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
    "contract-sign": "baupass://app/contract-sign",
}


def push_data_payload(*, tag: str, worker_id: str, extra: dict | None = None) -> dict[str, str]:
    route = _TAG_ROUTES.get(tag, "baupass://app/profile")
    data = {"tag": tag, "workerId": str(worker_id), "route": route, "deeplink": route}
    if extra:
        for k, v in extra.items():
            data[str(k)] = str(v)[:200]
    return data
