"""Outbound alerts for Platform Guardian — owner first, before customers notice."""
from __future__ import annotations

import os
import time
from typing import Any

from backend.app.core.platform_env import platform_env

from .env import guardian_env, guardian_flag, guardian_int

_last_sent_at: float = 0.0
_last_failed_fingerprint: str = ""


def guardian_webhook_urls() -> list[str]:
    urls: list[str] = []

    def _add(value: str) -> None:
        v = (value or "").strip()
        if v and v not in urls:
            urls.append(v)

    _add(guardian_env("OWNER_WEBHOOK_URL", ""))
    _add(guardian_env("WEBHOOK_URL", ""))
    for part in guardian_env("WEBHOOK_URLS", "").split(","):
        _add(part)
    _add(guardian_env("TEAMS_WEBHOOK_URL", ""))
    _add(platform_env("OPS_SLACK_WEBHOOK_URL", ""))
    _add(platform_env("AI_SLACK_WEBHOOK_URL", ""))
    _add(platform_env("OPS_TEAMS_WEBHOOK_URL", ""))
    _add(platform_env("AI_TEAMS_WEBHOOK_URL", ""))
    _add((os.getenv("SLACK_WEBHOOK_URL") or "").strip())
    return urls


def guardian_owner_emails() -> list[str]:
    raw = guardian_env("OWNER_EMAIL", "") or guardian_env("OWNER_EMAILS", "")
    if not raw:
        raw = platform_env("CONTACT_EMAIL", "")
    emails: list[str] = []
    for part in raw.replace(";", ",").split(","):
        addr = part.strip()
        if addr and "@" in addr and addr not in emails:
            emails.append(addr)
    return emails


def guardian_alert_cooldown_seconds() -> int:
    return guardian_int("ALERT_COOLDOWN_SECONDS", 180, minimum=30)


def notify_recovery_enabled() -> bool:
    return guardian_flag("NOTIFY_RECOVERY", "1")


def _failed_fingerprint(failed: list[str]) -> str:
    return "|".join(sorted(str(x) for x in (failed or [])))


def _build_alert_text(snapshot: dict[str, Any], *, is_recovery: bool) -> str:
    failed = snapshot.get("failedProbes") or []
    host = ((snapshot.get("cloud") or {}).get("host") or "").strip()
    rem = snapshot.get("remediation") or {}
    applied = int(rem.get("appliedCount") or 0)
    actions = rem.get("actions") or []
    action_ids = [
        str(a.get("id") or "")
        for a in actions
        if isinstance(a, dict) and a.get("ok") and not a.get("skipped")
    ][:8]
    re_probe = snapshot.get("reProbe") or {}
    recovered = re_probe.get("recovered") or []

    if is_recovery:
        return (
            "*Status wieder OK*\n"
            "Platform Guardian meldet: alle kritischen Probes wieder grün.\n"
            f"Auto-Reparatur zuletzt: {applied} Aktion(en)"
            + (f" ({', '.join(action_ids)})" if action_ids else "")
            + "\n"
            f"_Host:_ `{host or '—'}` · _Zeit:_ {snapshot.get('timestamp', '—')}"
        )

    failed_text = ", ".join(failed) if failed else "—"
    lines = [
        f"*SOFORT · Status: {str(snapshot.get('status') or '?').upper()}*",
        "_Du wirst benachrichtigt, bevor Kunden das merken sollen._",
        f"Betroffene Module: {failed_text}",
        f"Datenbank ready: {'ja' if snapshot.get('ready') else 'NEIN'}",
        f"Auto-Reparatur: {applied} Aktion(en)"
        + (f" → {', '.join(action_ids)}" if action_ids else ""),
    ]
    if recovered:
        lines.append(f"Nach Reparatur wieder OK: {', '.join(recovered)}")
    still = re_probe.get("after") if re_probe.get("ran") else failed
    if still:
        lines.append(f"Noch offen: {', '.join(still)}")
    lines.append(f"_Host:_ `{host or '—'}` · _Zeit:_ {snapshot.get('timestamp', '—')}")
    lines.append("Ops: `/ops-command-center.html` · API: `POST /api/guardian/remediate`")
    return "\n".join(lines)


def _send_owner_email(subject: str, text: str) -> dict[str, Any]:
    emails = guardian_owner_emails()
    if not emails:
        return {"sent": 0, "skipped": "no_owner_email"}
    sent = 0
    errors: list[str] = []
    try:
        from backend.server import _send_email_api_then_smtp
    except Exception as exc:
        return {"sent": 0, "error": str(exc)[:160]}
    html = "<br>".join(text.replace("*", "").split("\n"))
    for addr in emails:
        try:
            ok, err, _provider = _send_email_api_then_smtp(
                to_addrs=[addr],
                subject=subject,
                text_body=text,
                html_body=f"<p>{html}</p>",
            )
            if ok:
                sent += 1
            elif err:
                errors.append(str(err)[:80])
        except Exception as exc:
            errors.append(str(exc)[:80])
    return {"sent": sent, "total": len(emails), "errors": errors[:3]}


def maybe_notify_guardian(
    snapshot: dict[str, Any],
    *,
    previous_status: str,
    force: bool = False,
) -> dict[str, Any]:
    global _last_sent_at, _last_failed_fingerprint

    status = str(snapshot.get("status") or "unknown").lower()
    failed = list(snapshot.get("failedProbes") or [])
    fingerprint = _failed_fingerprint(failed)
    urls = guardian_webhook_urls()
    emails = guardian_owner_emails()
    if not urls and not emails:
        return {"sent": 0, "skipped": "no_webhook_or_email"}

    now = time.time()
    cooldown = guardian_alert_cooldown_seconds()
    status_changed = previous_status != status
    new_failures = bool(failed) and fingerprint != _last_failed_fingerprint and status in {"degraded", "down"}
    is_bad = status in {"degraded", "down"}
    is_recovery = previous_status in {"degraded", "down"} and status == "ok"

    if is_recovery and not notify_recovery_enabled():
        return {"sent": 0, "skipped": "recovery_disabled"}
    if not is_bad and not is_recovery:
        return {"sent": 0, "skipped": "status_ok"}

    urgent = force or status_changed or new_failures or is_recovery
    if not urgent and now - _last_sent_at < cooldown:
        return {"sent": 0, "skipped": "cooldown"}

    from backend.app.platform.ai.notifications import send_webhook_notification

    title = "SUPPIX Platform Guardian · Owner Alert"
    text = _build_alert_text(snapshot, is_recovery=is_recovery)
    subject = (
        "[SUPPIX Guardian] wieder OK"
        if is_recovery
        else f"[SUPPIX Guardian] {status.upper()} — bitte prüfen (vor Kunden)"
    )

    sent = 0
    for url in urls:
        ok, _ = send_webhook_notification(url, text, title=title)
        if ok:
            sent += 1

    email_result = _send_owner_email(subject, text)
    sent += int(email_result.get("sent") or 0)

    if sent:
        _last_sent_at = now
        _last_failed_fingerprint = fingerprint if is_bad else ""
    return {
        "sent": sent,
        "webhooks": len(urls),
        "email": email_result,
        "status": status,
        "recovery": is_recovery,
        "urgent": urgent,
        "newFailures": new_failures,
    }


def reset_notify_state_for_tests() -> None:
    global _last_sent_at, _last_failed_fingerprint
    _last_sent_at = 0.0
    _last_failed_fingerprint = ""
