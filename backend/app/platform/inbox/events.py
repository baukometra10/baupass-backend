"""Inbox change notifications for live admin UI."""
from __future__ import annotations


def notify_inbox_changed(company_id: str | None, *, source: str = "inbox") -> None:
    cid = str(company_id or "").strip()
    if not cid:
        return
    try:
        from backend.app.platform.events.bus import publish_event

        publish_event("inbox.changed", cid, {"source": source})
    except Exception:
        pass
