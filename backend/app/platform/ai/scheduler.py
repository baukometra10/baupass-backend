"""Scheduled AI operations briefing — per-company hours, Slack/Teams/email."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger("baupass.ai.scheduler")


def _cron_enabled() -> bool:
    return os.getenv("BAUPASS_AI_BRIEFING_CRON", "").strip().lower() in {"1", "true", "yes", "on"}


def _has_global_dispatch_channel() -> bool:
    email = (os.getenv("BAUPASS_AI_BRIEFING_EMAIL") or "").strip()
    if email and email.lower() not in {"auto", "automatic", "automatisch", "*"}:
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


def _zone(tz_name: str):
    try:
        return ZoneInfo((tz_name or "Europe/Berlin").strip() or "Europe/Berlin")
    except Exception:
        return ZoneInfo("UTC")


def seconds_until_next_briefing() -> int:
    """Next tick: top of next hour (per-company hours are checked each run)."""
    now = datetime.now(ZoneInfo("UTC"))
    target = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    return max(60, int((target - now).total_seconds()))


def build_company_morning_dispatch(
    db,
    company_id: str,
    *,
    company_name: str = "",
    lang: str = "de",
    include_llm: bool = True,
) -> dict[str, Any]:
    """Pulse + optional LLM briefing text for one company (cron or manual)."""
    from .assistant import generate_operations_briefing, is_ai_configured
    from .context_builder import build_compact_context
    from .operator_pulse import build_operator_pulse, format_morning_dispatch

    from .langs import normalize_ui_lang

    lang = normalize_ui_lang(lang)
    pulse = build_operator_pulse(db, company_id, role="company-admin", lang=lang, surface="general")
    llm_answer = ""
    if include_llm and is_ai_configured():
        try:
            ctx = build_compact_context(db, company_id, "company-admin")
            briefing = generate_operations_briefing(company_id, ctx, lang=lang)
            llm_answer = str(briefing.get("answer") or "").strip()
        except Exception as exc:
            logger.warning("LLM briefing failed company=%s: %s", company_id, exc)

    body = format_morning_dispatch(
        pulse,
        briefing_answer=llm_answer,
        company_name=company_name or company_id,
    )
    return {
        "companyId": company_id,
        "companyName": company_name,
        "lang": lang,
        "urgency": pulse.get("urgency"),
        "urgent": pulse.get("urgent"),
        "body": body,
        "pulse": pulse,
        "sectorTerms": pulse.get("sectorTerms") or {},
        "hasLlm": bool(llm_answer),
    }


def company_due_hours(
    settings: dict[str, Any],
    *,
    now_utc: datetime | None = None,
    db=None,
    company_id: str | None = None,
) -> list[tuple[int, str, str]]:
    """
    Return list of (hour, send_date, tz_name) that are due right now for this company.
    Due = current local hour matches effective briefing hours (auto from shifts or manual).
    """
    from .operator_settings import resolve_briefing_tz, resolve_effective_briefing_hours

    if settings.get("briefingEnabled") is False:
        return []
    hours = resolve_effective_briefing_hours(settings, db=db, company_id=company_id)
    tz_name = resolve_briefing_tz(settings, db=db, company_id=company_id)
    tz = _zone(tz_name)
    now = (now_utc or datetime.now(timezone.utc)).astimezone(tz)
    # Fire in the first ~50 minutes of the hour (hourly cron).
    if now.minute > 50:
        return []
    if now.hour not in hours:
        return []
    send_date = now.strftime("%Y-%m-%d")
    return [(now.hour, send_date, tz_name)]


def run_ai_briefing_cycle_once(*, reschedule: bool = True) -> dict[str, Any]:
    """Dispatch pulse briefings for companies whose local briefing hour is now."""
    from .notifications import dispatch_briefing_notifications
    from .operator_settings import (
        briefing_already_sent,
        get_settings,
        mark_briefing_sent,
        resolve_briefing_email,
        resolve_briefing_lang,
    )

    if not _cron_enabled():
        return {"ok": True, "skipped": True, "reason": "cron_disabled"}

    legacy = __import__("backend.server", fromlist=["get_db", "company_has_feature", "app"])
    include_llm = os.getenv("BAUPASS_AI_BRIEFING_LLM", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }

    processed = 0
    sent_webhooks = 0
    sent_emails = 0
    skipped_not_due = 0
    errors: list[str] = []
    now_utc = datetime.now(timezone.utc)

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
                settings = get_settings(db, company_id)
                due = company_due_hours(
                    settings, now_utc=now_utc, db=db, company_id=company_id
                )
                if not due:
                    skipped_not_due += 1
                    continue

                company_email = resolve_briefing_email(
                    settings, db=db, company_id=company_id
                )
                if not company_email and not _has_global_dispatch_channel():
                    errors.append(f"{company_id}:no_dispatch_channel")
                    continue

                for hour, send_date, _tz in due:
                    if briefing_already_sent(db, company_id, send_date=send_date, send_hour=hour):
                        continue

                    lang = resolve_briefing_lang(
                        settings, db=db, company_id=company_id
                    )
                    payload = build_company_morning_dispatch(
                        db,
                        company_id,
                        company_name=str(row["name"] or company_id),
                        lang=lang,
                        include_llm=include_llm,
                    )
                    body = (payload.get("body") or "").strip()
                    if not body:
                        continue
                    processed += 1
                    title = f"Suppix AI — {row['name'] or company_id}"
                    dispatch = dispatch_briefing_notifications(
                        body, company_id=company_id, title=title
                    )
                    webhook_ok = int(dispatch.get("sent") or 0) > 0
                    sent_webhooks += int(dispatch.get("sent") or 0)

                    email_ok = False
                    if company_email:
                        from .mailer import send_ai_briefing_email

                        ok, err = send_ai_briefing_email(
                            to=company_email, subject=title, body_text=body
                        )
                        if ok:
                            email_ok = True
                            sent_emails += 1
                        else:
                            errors.append(f"{company_id}:email:{err}")

                    # Only dedupe when at least one channel delivered.
                    if webhook_ok or email_ok:
                        mark_briefing_sent(db, company_id, send_date=send_date, send_hour=hour)
                    elif not company_email and not _has_global_dispatch_channel():
                        errors.append(f"{company_id}:no_delivery")
                    else:
                        errors.append(f"{company_id}:delivery_failed")
            except Exception as exc:
                logger.exception("AI briefing failed company=%s", company_id)
                errors.append(f"{company_id}:{exc}"[:120])

    result = {
        "ok": True,
        "processed": processed,
        "sentWebhooks": sent_webhooks,
        "sentEmails": sent_emails,
        "skippedNotDue": skipped_not_due,
        "errors": errors[:20],
        "mode": "per_company_hours",
    }

    if reschedule and _cron_enabled():
        from backend.app.tasks import enqueue_in_deduped

        delay = seconds_until_next_briefing()
        enqueue_in_deduped(
            delay,
            "scheduled",
            run_ai_briefing_cycle_once_task,
            job_id="baupass:scheduled:ai.briefing",
            reschedule=True,
            description="ai.briefing.cycle",
        )
        result["nextInSeconds"] = delay

    return result


def run_ai_briefing_cycle_once_task(*, reschedule: bool = True) -> dict[str, Any]:
    """RQ entrypoint."""
    from backend.app.tasks.job_health import record_job_run

    try:
        result = run_ai_briefing_cycle_once(reschedule=reschedule)
        record_job_run("ai_briefing", ok=bool(result.get("ok", True)), details=result)
        return result
    except Exception as exc:
        record_job_run("ai_briefing", ok=False, error=str(exc))
        raise


def bootstrap_ai_briefing_scheduler() -> bool:
    """Enqueue first AI briefing cycle once per deployment (requires Redis RQ)."""
    if not _cron_enabled():
        return False
    import time

    from backend.app.tasks import enqueue_in_deduped, scheduled_job_pending

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    lock_key = "baupass:rq:ai:briefing:bootstrap"
    job_id = "baupass:scheduled:ai.briefing"
    delay = seconds_until_next_briefing()

    if scheduled_job_pending(job_id):
        logger.info("AI briefing scheduler already has a pending RQ job")
        return False

    try:
        import redis

        conn = redis.Redis.from_url(redis_url, decode_responses=True)
        lock_acquired = bool(conn.set(lock_key, str(int(time.time())), nx=True, ex=max(3600, delay)))
        if not lock_acquired:
            logger.info("AI briefing scheduler already bootstrapped")
            return False

        enqueue_in_deduped(
            min(delay, 120),
            "scheduled",
            run_ai_briefing_cycle_once_task,
            job_id=job_id,
            reschedule=True,
            description="ai.briefing.bootstrap",
        )
        logger.info("AI briefing scheduler bootstrapped (next in %ss)", delay)
        return True
    except Exception as exc:
        logger.error("Failed to bootstrap AI briefing scheduler: %s", exc)
        return False
