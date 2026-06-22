"""Scheduled AI operations briefing — daily Slack/Teams/email dispatch."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger("baupass.ai.scheduler")


def _cron_enabled() -> bool:
    return os.getenv("BAUPASS_AI_BRIEFING_CRON", "").strip().lower() in {"1", "true", "yes", "on"}


def _has_dispatch_channel() -> bool:
    if (os.getenv("BAUPASS_AI_BRIEFING_EMAIL") or "").strip():
        return True
    for key in (
        "BAUPASS_AI_SLACK_WEBHOOK_URL",
        "SLACK_WEBHOOK_URL",
        "BAUPASS_AI_TEAMS_WEBHOOK_URL",
        "BAUPASS_AI_WEBHOOK_URL",
        "BAUPASS_AI_WEBHOOK_URLS",
    ):
        if (os.getenv(key) or "").strip():
            return True
    return False


def seconds_until_next_briefing() -> int:
    """Seconds until next run at BAUPASS_AI_BRIEFING_HOUR in BAUPASS_AI_BRIEFING_TZ."""
    hour = max(0, min(23, int(os.getenv("BAUPASS_AI_BRIEFING_HOUR", "7"))))
    tz_name = (os.getenv("BAUPASS_AI_BRIEFING_TZ") or "Europe/Berlin").strip()
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    now = datetime.now(tz)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return max(60, int((target - now).total_seconds()))


def run_ai_briefing_cycle_once(*, reschedule: bool = True) -> dict[str, Any]:
    """Generate and dispatch daily briefings for enterprise companies."""
    from .assistant import generate_operations_briefing, is_ai_configured
    from .context_builder import build_compact_context
    from .notifications import dispatch_briefing_notifications

    if not _cron_enabled():
        return {"ok": True, "skipped": True, "reason": "cron_disabled"}

    if not is_ai_configured():
        return {"ok": True, "skipped": True, "reason": "ai_not_configured"}

    if not _has_dispatch_channel():
        return {"ok": True, "skipped": True, "reason": "no_dispatch_channel"}

    legacy = __import__("backend.server", fromlist=["get_db", "company_has_feature", "app"])
    lang = (os.getenv("BAUPASS_AI_BRIEFING_LANG") or "de")[:2]
    briefing_email = (os.getenv("BAUPASS_AI_BRIEFING_EMAIL") or "").strip()

    processed = 0
    sent_webhooks = 0
    sent_emails = 0
    errors: list[str] = []

    with legacy.app.app_context():
        db = legacy.get_db()
        rows = db.execute(
            """
            SELECT id, plan, name
            FROM companies
            WHERE deleted_at IS NULL
              AND COALESCE(status, 'aktiv') NOT IN ('gesperrt', 'suspended')
            """
        ).fetchall()

        for row in rows:
            plan = (row["plan"] if row else "starter") or "starter"
            if not legacy.company_has_feature(plan, "ai_assistant"):
                continue
            company_id = str(row["id"])
            try:
                ctx = build_compact_context(db, company_id, "company-admin")
                briefing = generate_operations_briefing(company_id, ctx, lang=lang)
                body = (briefing.get("answer") or "").strip()
                if not body:
                    continue
                processed += 1
                title = f"SUPPIX AI — {row['name'] or company_id}"
                dispatch = dispatch_briefing_notifications(
                    body, company_id=company_id, title=title
                )
                sent_webhooks += int(dispatch.get("sent") or 0)

                if briefing_email:
                    from .mailer import send_ai_briefing_email

                    ok, err = send_ai_briefing_email(
                        to=briefing_email, subject=title, body_text=body
                    )
                    if ok:
                        sent_emails += 1
                    else:
                        errors.append(f"{company_id}:email:{err}")
            except Exception as exc:
                logger.exception("AI briefing failed company=%s", company_id)
                errors.append(f"{company_id}:{exc}"[:120])

    result = {
        "ok": True,
        "processed": processed,
        "sentWebhooks": sent_webhooks,
        "sentEmails": sent_emails,
        "errors": errors[:20],
    }

    if reschedule and _cron_enabled():
        from backend.app.tasks import enqueue_in

        delay = seconds_until_next_briefing()
        enqueue_in(
            delay,
            "scheduled",
            run_ai_briefing_cycle_once_task,
            reschedule=True,
            description="ai.briefing.cycle",
        )
        result["nextInSeconds"] = delay

    return result


def run_ai_briefing_cycle_once_task(*, reschedule: bool = True) -> dict[str, Any]:
    """RQ entrypoint."""
    return run_ai_briefing_cycle_once(reschedule=reschedule)


def bootstrap_ai_briefing_scheduler() -> bool:
    """Enqueue first AI briefing cycle once per deployment (requires Redis RQ)."""
    if not _cron_enabled():
        return False
    import time

    from backend.app.tasks import enqueue_in

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    lock_key = "baupass:rq:ai:briefing:bootstrap"
    delay = seconds_until_next_briefing()

    try:
        import redis

        conn = redis.Redis.from_url(redis_url, decode_responses=True)
        lock_acquired = bool(conn.set(lock_key, str(int(time.time())), nx=True, ex=max(600, delay)))
        if not lock_acquired:
            logger.info("AI briefing scheduler already bootstrapped")
            return False

        enqueue_in(
            min(delay, 120),
            "scheduled",
            run_ai_briefing_cycle_once_task,
            reschedule=True,
            description="ai.briefing.bootstrap",
        )
        logger.info("AI briefing scheduler bootstrapped (next in %ss)", delay)
        return True
    except Exception as exc:
        logger.error("Failed to bootstrap AI briefing scheduler: %s", exc)
        return False
