"""Send system satisfaction survey invites after sufficient product usage."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

USAGE_DAYS_BEFORE_INVITE = 30
SURVEY_COOLDOWN_DAYS = 90


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _since_iso(days: int) -> str:
    return (_utc_now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")


def _user_usage_age_days(db, user_id: str, company_id: str = "") -> int:
    uid = str(user_id or "").strip()
    if not uid:
        return 0
    params: list[Any] = [uid]
    company_clause = ""
    if company_id:
        company_clause = " AND company_id = ?"
        params.append(company_id)

    row = db.execute(
        f"""
        SELECT MIN(ts) AS first_ts FROM (
            SELECT created_at AS ts FROM audit_logs
            WHERE actor_user_id = ? AND event_type LIKE 'login.success%'{company_clause}
            UNION ALL
            SELECT created_at AS ts FROM feature_usage_events
            WHERE user_id = ?{company_clause}
        )
        """,
        (uid, *([company_id] if company_id else []), uid, *([company_id] if company_id else [])),
    ).fetchone()
    first_ts = str((row["first_ts"] if row else "") or "").strip()
    if not first_ts or len(first_ts) < 10:
        return 0
    try:
        first = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
        if first.tzinfo is None:
            first = first.replace(tzinfo=timezone.utc)
        delta = _utc_now() - first.astimezone(timezone.utc)
        return max(0, delta.days)
    except ValueError:
        return 0


def _recent_survey_invite(db, user_id: str) -> bool:
    since = _since_iso(SURVEY_COOLDOWN_DAYS)
    row = db.execute(
        """
        SELECT id FROM audit_logs
        WHERE actor_user_id = ? AND event_type = 'survey.invite.sent'
          AND created_at >= ?
        LIMIT 1
        """,
        (user_id, since),
    ).fetchone()
    return row is not None


def _recent_survey_submission(db, user_id: str) -> bool:
    since = _since_iso(SURVEY_COOLDOWN_DAYS)
    row = db.execute(
        """
        SELECT id FROM system_satisfaction_surveys
        WHERE user_id = ? AND created_at >= ?
        LIMIT 1
        """,
        (user_id, since),
    ).fetchone()
    return row is not None


def _survey_url() -> str:
    try:
        from backend.server import get_public_base_url

        base = str(get_public_base_url() or "").rstrip("/")
        if base:
            return f"{base}/satisfaction-survey.html"
    except Exception:
        pass
    return "/satisfaction-survey.html"


def check_mail_provider_ready(db) -> dict[str, Any]:
    """Whether outbound API mail can send survey invites (Resend/Brevo). SMTP is reported separately."""
    providers: list[str] = []
    try:
        from backend.server import _get_brevo_api_key, _get_resend_api_key_and_source

        resend_key, _ = _get_resend_api_key_and_source()
        if resend_key:
            providers.append("resend")
        if _get_brevo_api_key():
            providers.append("brevo")
    except Exception:
        pass

    settings_row = db.execute(
        "SELECT smtp_sender_email, smtp_host FROM settings WHERE id = 1"
    ).fetchone()
    settings = dict(settings_row) if settings_row else {}
    smtp_ready = bool(
        str(settings.get("smtp_host") or "").strip()
        and str(settings.get("smtp_sender_email") or "").strip()
    )
    if smtp_ready:
        providers.append("smtp")

    configured = bool(providers)
    return {
        "configured": configured,
        "providers": providers,
        "primaryProvider": providers[0] if providers else None,
        "hint": (
            "Bereit — Umfrage-E-Mails können versendet werden."
            if configured
            else "Noch nicht bereit — bitte Resend- oder Brevo-API-Key in den Einstellungen hinterlegen (oder SMTP konfigurieren)."
        ),
        "surveyUrl": _survey_url(),
    }


def _build_survey_bodies(name: str, usage_days: int, survey_link: str) -> tuple[str, str, str]:
    subject = "SUPPIX — Kurze System-Bewertung (2 Minuten)"
    text_body = (
        f"Hallo {name},\n\n"
        f"Sie nutzen SUPPIX seit etwa {usage_days} Tagen. "
        f"Helfen Sie uns mit einer kurzen Bewertung (1 = sehr gut, 5 = sehr schlecht):\n\n"
        f"{survey_link}\n\n"
        "Fragen: Zufriedenheit, Weiterempfehlung, beste Funktion, Zeitersparnis, Kosteneinsparung.\n\n"
        "Vielen Dank!\nIhr SUPPIX-Team"
    )
    inner_html = (
        f"<p>Hallo <strong>{name}</strong>,</p>"
        f"<p>Sie nutzen SUPPIX seit etwa <strong>{usage_days} Tagen</strong>. "
        f"Bitte nehmen Sie sich 2 Minuten für eine kurze System-Bewertung "
        f"(<em>1 = sehr gut · 5 = sehr schlecht</em>).</p>"
        f'<p style="margin:24px 0;"><a href="{survey_link}" '
        f'style="display:inline-block;background:#1d4ed8;color:#fff;padding:12px 22px;'
        f'border-radius:8px;text-decoration:none;font-weight:600;">Jetzt bewerten</a></p>'
        f'<p class="muted" style="font-size:0.9em;color:#666;">Oder Link kopieren: {survey_link}</p>'
    )
    try:
        from backend.server import _build_email_html

        html_body = _build_email_html(
            "WorkPass",
            "#1B5E8C",
            "#A66A3D",
            "Ihre Meinung zählt",
            inner_html,
            "SUPPIX-Team",
        )
    except Exception:
        html_body = inner_html + "<p>Danke!<br>SUPPIX-Team</p>"
    return subject, text_body, html_body


def send_survey_invite_email(
    db,
    user: dict[str, Any],
    *,
    skip_usage_check: bool = False,
    skip_cooldown: bool = False,
) -> dict[str, Any]:
    user_id = str(user.get("id") or "").strip()
    email = str(user.get("email") or "").strip()
    role = str(user.get("role") or "").strip()
    company_id = str(user.get("company_id") or "").strip()

    if role not in {"company-admin", "foreman", "superadmin"}:
        return {"ok": False, "skipped": True, "reason": "role_not_eligible"}
    if not user_id or not email:
        return {"ok": False, "skipped": True, "reason": "missing_user_or_email"}

    usage_days = _user_usage_age_days(db, user_id, company_id)
    if not skip_usage_check and usage_days < USAGE_DAYS_BEFORE_INVITE:
        return {"ok": False, "skipped": True, "reason": "usage_too_short", "usageDays": usage_days}
    if _recent_survey_submission(db, user_id):
        return {"ok": False, "skipped": True, "reason": "recent_submission"}
    if not skip_cooldown and _recent_survey_invite(db, user_id):
        return {"ok": False, "skipped": True, "reason": "recent_invite"}

    mail_status = check_mail_provider_ready(db)
    if not mail_status.get("configured"):
        return {
            "ok": False,
            "error": "mail_not_configured",
            "hint": mail_status.get("hint"),
            "surveyUrl": mail_status.get("surveyUrl"),
        }

    name = str(user.get("name") or user.get("username") or "Admin").strip()
    survey_link = _survey_url()
    display_days = max(usage_days, USAGE_DAYS_BEFORE_INVITE if skip_usage_check else usage_days)
    subject, text_body, html_body = _build_survey_bodies(name, display_days, survey_link)

    provider = None
    try:
        from backend.app.core.platform_env import default_noreply_email
        from backend.server import _send_via_any_api

        settings_row = db.execute(
            "SELECT smtp_sender_email, smtp_sender_name FROM settings WHERE id = 1"
        ).fetchone()
        settings = dict(settings_row) if settings_row else {}
        sender_email = (settings.get("smtp_sender_email") or "").strip() or default_noreply_email()
        sender_name = (settings.get("smtp_sender_name") or "WorkPass").strip()
        ok, err, provider = _send_via_any_api(
            subject, sender_email, sender_name, email, text_body, html_body
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}

    if not ok:
        err_text = str(err or "send_failed")
        if "no_api_provider" in err_text:
            return {
                "ok": False,
                "error": "mail_not_configured",
                "hint": check_mail_provider_ready(db).get("hint"),
                "surveyUrl": survey_link,
            }
        return {"ok": False, "error": err_text[:200]}

    now = _utc_now().isoformat().replace("+00:00", "Z")
    try:
        from backend.server import log_audit

        log_audit(
            "survey.invite.sent",
            f"System-Bewertung eingeladen: {email}",
            target_type="user",
            target_id=user_id,
            company_id=company_id or None,
            actor=user,
        )
    except Exception:
        db.execute(
            """
            INSERT INTO audit_logs (id, event_type, actor_user_id, actor_role, company_id, target_type, target_id, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"aud-{uuid.uuid4().hex[:8]}",
                "survey.invite.sent",
                user_id,
                role,
                company_id,
                "user",
                user_id,
                f"Survey invite {email}"[:500],
                now,
            ),
        )
        db.commit()

    return {
        "ok": True,
        "email": email,
        "usageDays": usage_days,
        "provider": provider,
        "surveyUrl": survey_link,
    }


def list_invite_candidates(db, company_id: str | None = None) -> dict[str, Any]:
    params: list[Any] = []
    where = " WHERE role IN ('company-admin', 'foreman', 'superadmin')"
    if company_id:
        where += " AND company_id = ?"
        params.append(company_id)
    where += " AND COALESCE(email, '') != ''"

    rows = db.execute(
        f"""
        SELECT id, username, name, role, company_id, email
        FROM users
        {where}
        ORDER BY role, username
        LIMIT 100
        """,
        tuple(params),
    ).fetchall()

    candidates = []
    for row in rows:
        user = dict(row)
        uid = str(user.get("id") or "")
        usage_days = _user_usage_age_days(db, uid, str(user.get("company_id") or ""))
        eligible = True
        reason = ""
        if _recent_survey_submission(db, uid):
            eligible = False
            reason = "recent_submission"
        elif _recent_survey_invite(db, uid):
            eligible = False
            reason = "recent_invite"
        elif usage_days < USAGE_DAYS_BEFORE_INVITE:
            eligible = False
            reason = "usage_too_short"

        candidates.append(
            {
                "id": uid,
                "username": user.get("username") or "",
                "name": user.get("name") or "",
                "email": user.get("email") or "",
                "role": user.get("role") or "",
                "usageDays": usage_days,
                "eligible": eligible,
                "ineligibleReason": reason,
            }
        )

    return {
        "mail": check_mail_provider_ready(db),
        "usageDaysRequired": USAGE_DAYS_BEFORE_INVITE,
        "cooldownDays": SURVEY_COOLDOWN_DAYS,
        "candidates": candidates,
    }


def send_survey_invites_batch(
    db,
    *,
    company_id: str | None = None,
    user_id: str | None = None,
    send_all: bool = False,
    skip_usage_check: bool = False,
    skip_cooldown: bool = False,
) -> dict[str, Any]:
    mail_status = check_mail_provider_ready(db)
    if not mail_status.get("configured"):
        return {
            "ok": False,
            "error": "mail_not_configured",
            "hint": mail_status.get("hint"),
            "mail": mail_status,
        }

    targets: list[dict[str, Any]] = []
    if user_id:
        row = db.execute(
            "SELECT id, username, name, role, company_id, email FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "user_not_found"}
        targets = [dict(row)]
    else:
        payload = list_invite_candidates(db, company_id)
        for c in payload.get("candidates") or []:
            if send_all or c.get("eligible"):
                row = db.execute(
                    "SELECT id, username, name, role, company_id, email FROM users WHERE id = ?",
                    (c["id"],),
                ).fetchone()
                if row:
                    targets.append(dict(row))

    if not targets:
        return {"ok": False, "error": "no_recipients", "mail": mail_status}

    sent = 0
    skipped = 0
    errors: list[dict[str, str]] = []
    for user in targets:
        result = send_survey_invite_email(
            db,
            user,
            skip_usage_check=skip_usage_check,
            skip_cooldown=skip_cooldown,
        )
        if result.get("ok"):
            sent += 1
        elif result.get("skipped"):
            skipped += 1
        else:
            errors.append(
                {
                    "userId": str(user.get("id") or ""),
                    "email": str(user.get("email") or ""),
                    "error": str(result.get("error") or "send_failed"),
                }
            )
            if result.get("error") == "mail_not_configured":
                break

    return {
        "ok": sent > 0 and not errors,
        "sent": sent,
        "skipped": skipped,
        "errors": errors,
        "mail": mail_status,
    }


def maybe_send_survey_invite_on_login(db, user: dict[str, Any]) -> dict[str, Any]:
    """Non-blocking hook after successful admin login."""
    return send_survey_invite_email(db, user)


def run_survey_invite_cycle(db) -> dict[str, Any]:
    """Daily autopilot: invite eligible company admins who have not been contacted."""
    rows = db.execute(
        """
        SELECT id, username, name, role, company_id, email
        FROM users
        WHERE role IN ('company-admin', 'foreman')
          AND COALESCE(email, '') != ''
          AND COALESCE(status, 'active') NOT IN ('inactive', 'deleted', 'disabled')
        ORDER BY id
        LIMIT 200
        """
    ).fetchall()

    sent = 0
    skipped = 0
    errors = 0
    for row in rows:
        user = dict(row)
        result = send_survey_invite_email(db, user)
        if result.get("ok"):
            sent += 1
        elif result.get("skipped"):
            skipped += 1
        else:
            errors += 1

    return {"ok": True, "sent": sent, "skipped": skipped, "errors": errors, "checked": len(rows)}
