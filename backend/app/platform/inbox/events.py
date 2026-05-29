"""Inbox change notifications for live admin UI."""
from __future__ import annotations


def notify_inbox_changed(
    company_id: str | None,
    *,
    source: str = "inbox",
    alert_title: str | None = None,
    alert_message: str | None = None,
    severity: str | None = None,
) -> None:
    cid = str(company_id or "").strip()
    if not cid:
        return
    try:
        from backend.app.platform.events.bus import publish_event

        publish_event("inbox.changed", cid, {"source": source})
    except Exception:
        pass
    if alert_title and severity:
        try:
            from .slack_notify import maybe_notify_inbox_slack

            maybe_notify_inbox_slack(
                cid,
                source=source,
                title=alert_title,
                message=alert_message or alert_title,
                severity=severity,
            )
        except Exception:
            pass
