"""Worker-facing morning brief — personal + company-safe summary."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


def _today() -> str:
    return date.today().isoformat()


def build_worker_morning_brief(db, *, worker_id: str, company_id: str) -> dict[str, Any]:
    """Slim morning card for the mobile home screen (no admin-only PII dumps)."""
    wid = str(worker_id or "").strip()
    cid = str(company_id or "").strip()
    today = _today()
    out: dict[str, Any] = {
        "ok": True,
        "date": today,
        "checkedInToday": False,
        "onSiteNow": False,
        "colleaguesOnSite": 0,
        "unreadNotifications": 0,
        "pendingLeave": 0,
        "expiringDocuments": 0,
        "unreadChat": 0,
        "lines": [],
        "updatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
    if not wid or not cid:
        return out

    try:
        row = db.execute(
            """
            SELECT COUNT(*) AS c FROM access_logs
            WHERE worker_id = ? AND direction = 'check-in' AND timestamp LIKE ?
            """,
            (wid, f"{today}%"),
        ).fetchone()
        out["checkedInToday"] = int((row["c"] if row else 0) or 0) > 0
    except Exception:
        pass

    try:
        from backend.app.platform.physical_operations._common import count_on_site, list_on_site_workers

        out["colleaguesOnSite"] = int(count_on_site(db, cid, today) or 0)
        on_site_ids = {str(w.get("id") or "") for w in (list_on_site_workers(db, cid, today) or [])}
        out["onSiteNow"] = wid in on_site_ids
    except Exception:
        pass

    try:
        row = db.execute(
            """
            SELECT COUNT(*) AS c FROM notifications
            WHERE worker_id = ? AND COALESCE(read_at, '') = ''
            """,
            (wid,),
        ).fetchone()
        out["unreadNotifications"] = int((row["c"] if row else 0) or 0)
    except Exception:
        pass

    try:
        row = db.execute(
            """
            SELECT COUNT(*) AS c FROM leave_requests
            WHERE worker_id = ? AND status IN ('pending', 'ausstehend')
            """,
            (wid,),
        ).fetchone()
        out["pendingLeave"] = int((row["c"] if row else 0) or 0)
    except Exception:
        pass

    try:
        row = db.execute(
            """
            SELECT COUNT(*) AS c FROM worker_documents
            WHERE worker_id = ?
              AND COALESCE(valid_until, '') <> ''
              AND date(valid_until) <= date(?, '+14 day')
              AND date(valid_until) >= date(?)
            """,
            (wid, today, today),
        ).fetchone()
        out["expiringDocuments"] = int((row["c"] if row else 0) or 0)
    except Exception:
        try:
            row = db.execute(
                """
                SELECT COUNT(*) AS c FROM documents
                WHERE worker_id = ?
                  AND COALESCE(expires_at, valid_until, '') <> ''
                """,
                (wid,),
            ).fetchone()
            out["expiringDocuments"] = int((row["c"] if row else 0) or 0)
        except Exception:
            pass

    try:
        row = db.execute(
            """
            SELECT COUNT(*) AS c
            FROM chat_messages m
            JOIN chat_threads t ON t.id = m.thread_id
            WHERE t.worker_id = ?
              AND m.sender_role IN ('admin', 'company-admin', 'employer', 'system')
              AND COALESCE(m.read_at, '') = ''
            """,
            (wid,),
        ).fetchone()
        out["unreadChat"] = int((row["c"] if row else 0) or 0)
    except Exception:
        pass

    lines: list[str] = []
    if out["checkedInToday"] or out["onSiteNow"]:
        lines.append("checked_in")
    else:
        lines.append("not_checked_in")
    if out["colleaguesOnSite"] > 0:
        lines.append("colleagues")
    if out["unreadChat"] > 0:
        lines.append("chat")
    if out["pendingLeave"] > 0:
        lines.append("leave")
    if out["expiringDocuments"] > 0:
        lines.append("docs")
    if out["unreadNotifications"] > 0:
        lines.append("notifications")
    out["lines"] = lines
    return out
