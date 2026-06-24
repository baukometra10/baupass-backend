"""Outbound alerts for Platform Guardian."""
from __future__ import annotations

import os
import time
from typing import Any

_last_sent_at: float = 0.0


def guardian_webhook_urls() -> list[str]:
    urls: list[str] = []
    for key in (
        "BAUPASS_GUARDIAN_WEBHOOK_URL",
        "BAUPASS_OPS_SLACK_WEBHOOK_URL",
        "BAUPASS_AI_SLACK_WEBHOOK_URL",
        "SLACK_WEBHOOK_URL",
    ):
        value = (os.getenv(key) or "").strip()
        if value and value not in urls:
            urls.append(value)
    for key in ("BAUPASS_GUARDIAN_TEAMS_WEBHOOK_URL", "BAUPASS_OPS_TEAMS_WEBHOOK_URL", "BAUPASS_AI_TEAMS_WEBHOOK_URL"):
        value = (os.getenv(key) or "").strip()
        if value and value not in urls:
            urls.append(value)
    extra = (os.getenv("BAUPASS_GUARDIAN_WEBHOOK_URLS") or "").strip()
    for part in extra.split(","):
        value = part.strip()
        if value and value not in urls:
            urls.append(value)
    return urls


def guardian_alert_cooldown_seconds() -> int:
    return max(60, int(os.getenv("BAUPASS_GUARDIAN_ALERT_COOLDOWN_SECONDS", "900")))


def notify_recovery_enabled() -> bool:
    return os.getenv("BAUPASS_GUARDIAN_NOTIFY_RECOVERY", "1").strip().lower() not in {"0", "false", "no"}


def maybe_notify_guardian(
    snapshot: dict[str, Any],
    *,
    previous_status: str,
    force: bool = False,
) -> dict[str, Any]:
    global _last_sent_at
    status = str(snapshot.get("status") or "unknown").lower()
    urls = guardian_webhook_urls()
    if not urls:
        return {"sent": 0, "skipped": "no_webhook"}

    now = time.time()
    cooldown = guardian_alert_cooldown_seconds()
    status_changed = previous_status != status
    is_bad = status in {"degraded", "down"}
    is_recovery = previous_status in {"degraded", "down"} and status == "ok"

    if is_recovery and not notify_recovery_enabled():
        return {"sent": 0, "skipped": "recovery_disabled"}
    if not is_bad and not is_recovery:
        return {"sent": 0, "skipped": "status_ok"}
    if not force and not status_changed and now - _last_sent_at < cooldown:
        return {"sent": 0, "skipped": "cooldown"}

    from backend.app.platform.ai.notifications import send_webhook_notification

    failed = snapshot.get("failedProbes") or []
    host = ((snapshot.get("cloud") or {}).get("host") or "").strip()
    title = "SUPPIX Platform Guardian"
    if is_recovery:
        text = (
            "*Status wieder OK*\n"
            "Alle Plattform-Probes sind wieder grün.\n"
            f"_Host:_ `{host or '—'}` · _Zeit:_ {snapshot.get('timestamp', '—')}"
        )
    else:
        failed_text = ", ".join(failed) if failed else "—"
        text = (
            f"*Status: {status.upper()}*\n"
            f"Betroffene Module: {failed_text}\n"
            f"Datenbank: {'OK' if snapshot.get('ready') else 'FEHLER'}\n"
            f"_Host:_ `{host or '—'}` · _Zeit:_ {snapshot.get('timestamp', '—')}"
        )

    sent = 0
    for url in urls:
        ok, _ = send_webhook_notification(url, text, title=title)
        if ok:
            sent += 1
    if sent:
        _last_sent_at = now
    return {"sent": sent, "total": len(urls), "status": status, "recovery": is_recovery}


def reset_notify_state_for_tests() -> None:
    global _last_sent_at
    _last_sent_at = 0.0
