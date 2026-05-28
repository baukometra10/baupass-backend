"""Outbound notifications — Slack, Teams, generic webhooks for AI briefings."""
from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

logger = logging.getLogger("baupass.ai.notifications")


def _post_json(url: str, payload: dict[str, Any], *, timeout: int = 15) -> tuple[bool, str]:
    url = (url or "").strip()
    if not url:
        return False, "webhook_url_missing"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                return True, ""
            return False, f"http_{resp.status}"
    except urlerror.HTTPError as exc:
        return False, f"http_{exc.code}"
    except Exception as exc:
        return False, str(exc)[:200]


def slack_payload(text: str, *, title: str = "BauPass KI") -> dict[str, Any]:
    """Slack incoming webhook compatible body."""
    return {
        "text": title,
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": title[:150]}},
            {"type": "section", "text": {"type": "mrkdwn", "text": text[:3000]}},
        ],
    }


def teams_payload(text: str, *, title: str = "BauPass KI") -> dict[str, Any]:
    return {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "summary": title,
        "themeColor": "0f4c5c",
        "title": title,
        "text": text[:3000],
    }


def send_webhook_notification(
    url: str,
    text: str,
    *,
    title: str = "BauPass KI Tagesbriefing",
    channel: str = "auto",
) -> tuple[bool, str]:
    """Send to Slack, Teams, or generic JSON webhook."""
    channel = (channel or os.getenv("BAUPASS_AI_WEBHOOK_FORMAT", "auto")).strip().lower()
    if channel == "auto":
        if "hooks.slack.com" in url or "slack.com" in url:
            channel = "slack"
        elif "webhook.office.com" in url or "logic.azure.com" in url:
            channel = "teams"
        else:
            channel = "generic"

    if channel == "slack":
        body = slack_payload(text, title=title)
    elif channel == "teams":
        body = teams_payload(text, title=title)
    else:
        body = {"title": title, "text": text, "source": "baupass_ai"}

    return _post_json(url, body)


def dispatch_briefing_notifications(
    text: str,
    *,
    company_id: str | None = None,
    title: str = "BauPass KI Tagesbriefing",
) -> dict[str, Any]:
    """Send briefing to all configured global webhooks."""
    results: list[dict[str, Any]] = []
    urls: list[tuple[str, str]] = []

    slack = (os.getenv("BAUPASS_AI_SLACK_WEBHOOK_URL") or os.getenv("SLACK_WEBHOOK_URL") or "").strip()
    generic = (os.getenv("BAUPASS_AI_WEBHOOK_URL") or "").strip()
    teams = (os.getenv("BAUPASS_AI_TEAMS_WEBHOOK_URL") or "").strip()

    if slack:
        urls.append(("slack", slack))
    if teams:
        urls.append(("teams", teams))
    if generic and generic not in {u for _, u in urls}:
        urls.append(("generic", generic))

    extra = (os.getenv("BAUPASS_AI_WEBHOOK_URLS") or "").strip()
    for part in extra.split(","):
        u = part.strip()
        if u:
            urls.append(("extra", u))

    for label, url in urls:
        ok, err = send_webhook_notification(url, text, title=title, channel=label)
        results.append({"channel": label, "ok": ok, "error": err or None})

    return {
        "companyId": company_id,
        "sent": sum(1 for r in results if r.get("ok")),
        "total": len(results),
        "results": results,
    }
