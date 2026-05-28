"""AI-suggested and executable safe actions."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


ALLOWED_EXECUTE = frozenset(
    {
        "resolve_security_alert",
        "send_briefing_email",
        "send_briefing_webhook",
        "export_briefing_markdown",
    }
)


def suggest_actions(
    ctx: dict[str, Any],
    *,
    company_id: str,
    tools_used: list[str] | None = None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    sec = ctx.get("security") or {}
    findings = sec.get("topFindings") or []
    em = ctx.get("emergency") or {}

    if int(sec.get("openFindings") or 0) > 0:
        actions.append(
            {
                "id": "nav_security",
                "type": "navigate",
                "labelDe": "Security-Befunde im Hub öffnen",
                "labelEn": "Open security findings in hub",
                "url": "/enterprise-hub.html",
            }
        )
    if em.get("active"):
        actions.append(
            {
                "id": "nav_emergency",
                "type": "navigate",
                "labelDe": "Notfall-Status prüfen",
                "labelEn": "Check emergency status",
                "url": "/ops-command-center.html",
            }
        )
    if "get_expired_documents" in (tools_used or []) or int(
        (ctx.get("intelligence") or {}).get("risk", {}).get("expired_documents") or 0
    ) > 0:
        actions.append(
            {
                "id": "nav_workers",
                "type": "navigate",
                "labelDe": "Mitarbeiter & Dokumente in Admin",
                "labelEn": "Workers & documents in admin",
                "url": "/admin-v2/index.html",
            }
        )

    for i, f in enumerate(findings[:3]):
        aid = f.get("workerId") or f.get("alert_id")
        if f.get("type") == "high_frequency_taps" and f.get("workerId"):
            actions.append(
                {
                    "id": f"profile_{i}",
                    "type": "navigate",
                    "labelDe": f"Mitarbeiter {f.get('workerId')} prüfen",
                    "url": f"/admin-v2/index.html#workers",
                }
            )

    actions.append(
        {
            "id": "email_briefing",
            "type": "execute",
            "action": "send_briefing_email",
            "labelDe": "Tagesbriefing per E-Mail senden",
            "labelEn": "Email daily briefing",
            "labelAr": "إرسال الملخص بالبريد",
            "paramsSchema": {"to": "email"},
        }
    )
    actions.append(
        {
            "id": "webhook_briefing",
            "type": "execute",
            "action": "send_briefing_webhook",
            "labelDe": "Briefing an Slack/Teams Webhook",
            "labelEn": "Post briefing to Slack/Teams",
            "labelAr": "إرسال إلى Webhook",
        }
    )
    actions.append(
        {
            "id": "export_md",
            "type": "execute",
            "action": "export_briefing_markdown",
                "labelDe": "Briefing als Markdown exportieren",
                "labelEn": "Export briefing as markdown",
                "labelAr": "تصدير Markdown",
            "params": {},
        }
    )
    return actions[:8]


def execute_action(
    db,
    *,
    company_id: str,
    user_id: str,
    action: str,
    params: dict | None = None,
    briefing_text: str | None = None,
) -> dict[str, Any]:
    params = params or {}
    action = (action or "").strip()
    if action not in ALLOWED_EXECUTE:
        return {"ok": False, "error": "action_not_allowed", "action": action}

    if action == "resolve_security_alert":
        alert_id = str(params.get("alert_id") or "").strip()
        if not alert_id:
            return {"ok": False, "error": "alert_id_required"}
        row = db.execute(
            "SELECT id, status FROM security_alerts WHERE id = ? AND company_id = ?",
            (alert_id, company_id),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "alert_not_found"}
        db.execute(
            "UPDATE security_alerts SET status = 'resolved', resolved_at = ? WHERE id = ?",
            (_now(), alert_id),
        )
        db.commit()
        return {"ok": True, "alertId": alert_id, "status": "resolved"}

    if action == "export_briefing_markdown":
        text = (briefing_text or params.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "briefing_text_required"}
        return {"ok": True, "format": "markdown", "content": text}

    if action == "send_briefing_webhook":
        from .notifications import dispatch_briefing_notifications

        text = (briefing_text or params.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "briefing_text_required"}
        dispatch = dispatch_briefing_notifications(text, company_id=company_id)
        return {"ok": dispatch.get("sent", 0) > 0, **dispatch}

    if action == "send_briefing_email":
        from .mailer import send_ai_briefing_email

        to = str(params.get("to") or "").strip()
        subject = str(params.get("subject") or "BauPass KI Tagesbriefing").strip()
        body = (briefing_text or params.get("body") or "").strip()
        if not to or not body:
            return {"ok": False, "error": "to_and_body_required"}
        ok, err = send_ai_briefing_email(to=to, subject=subject, body_text=body)
        return {"ok": ok, "to": to, "error": err or None}

    return {"ok": False, "error": "unknown"}
