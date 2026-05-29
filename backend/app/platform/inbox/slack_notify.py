"""Slack/Teams alerts for critical operations inbox events."""
from __future__ import annotations

import os
import time
from typing import Any

_last_sent: dict[str, float] = {}
_COOLDOWN_SEC = 300


def _webhook_urls() -> list[str]:
    urls: list[str] = []
    for key in (
        "BAUPASS_OPS_SLACK_WEBHOOK_URL",
        "BAUPASS_AI_SLACK_WEBHOOK_URL",
        "SLACK_WEBHOOK_URL",
    ):
        u = (os.getenv(key) or "").strip()
        if u and u not in urls:
            urls.append(u)
    teams = (os.getenv("BAUPASS_OPS_TEAMS_WEBHOOK_URL") or os.getenv("BAUPASS_AI_TEAMS_WEBHOOK_URL") or "").strip()
    if teams and teams not in urls:
        urls.append(teams)
    return urls


def maybe_notify_inbox_slack(
    company_id: str,
    *,
    source: str,
    title: str,
    message: str,
    severity: str = "high",
) -> dict[str, Any]:
    """Rate-limited webhook when critical/high inbox events occur."""
    cid = str(company_id or "").strip()
    if not cid:
        return {"sent": 0, "skipped": "no_company"}
    if (severity or "").lower() not in {"critical", "high"}:
        return {"sent": 0, "skipped": "severity"}
    urls = _webhook_urls()
    if not urls:
        return {"sent": 0, "skipped": "no_webhook"}

    key = f"{cid}:{source}:{title[:40]}"
    now = time.time()
    if now - _last_sent.get(key, 0) < _COOLDOWN_SEC:
        return {"sent": 0, "skipped": "cooldown"}

    from backend.app.platform.ai.notifications import send_webhook_notification

    text = f"*{title}*\n{message}\n_Firma:_ `{cid}` · _Quelle:_ `{source}`"
    sent = 0
    for url in urls:
        ok, _ = send_webhook_notification(url, text, title="BauPass Ops Posteingang")
        if ok:
            sent += 1
    if sent:
        _last_sent[key] = now
    return {"sent": sent, "total": len(urls)}
