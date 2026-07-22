"""Notify company admins (inbox, system alert, e-mail) about worker events."""
from __future__ import annotations

import html
import json
from typing import Any

# Attendance denials that mean "not supposed to work right now".
OUTSIDE_HOURS_NOTIFY_REASONS = frozenset(
    {
        "outside_work_hours",
        "outside_shift_window",
        "not_scheduled_today",
        "not_a_workday",
    }
)

_CHANNEL_LABELS = {
    "de": {
        "gps": "GPS",
        "gate": "Gate/Reader",
        "nfc": "NFC (App)",
        "manual": "manuell (App)",
        "proximity": "GPS (Standort-Login)",
    },
    "en": {
        "gps": "GPS",
        "gate": "Gate/Reader",
        "nfc": "NFC (App)",
        "manual": "manual (App)",
        "proximity": "GPS (site login)",
    },
    "ar": {
        "gps": "GPS",
        "gate": "بوابة/قارئ",
        "nfc": "NFC (التطبيق)",
        "manual": "يدوي (التطبيق)",
        "proximity": "GPS (تسجيل الموقع)",
    },
    "fr": {
        "gps": "GPS",
        "gate": "Portail/lecteur",
        "nfc": "NFC (App)",
        "manual": "manuel (App)",
        "proximity": "GPS (connexion site)",
    },
    "tr": {
        "gps": "GPS",
        "gate": "Kapı/Okuyucu",
        "nfc": "NFC (Uygulama)",
        "manual": "manuel (Uygulama)",
        "proximity": "GPS (saha girişi)",
    },
}

_OUTSIDE_HOURS_COPY = {
    "de": {
        "title": "Anmeldung außerhalb der Arbeitszeit",
        "body": "{name} hat versucht, sich außerhalb der Arbeitszeit anzumelden ({channel}{gate}).{window}",
        "window": " Geplante Zeit: {start}–{end}.",
        "reason": "Grund",
        "channel": "Kanal",
        "footer": "Der Check-in wurde abgelehnt. Bitte Schicht- und Arbeitszeiten im Betrieb-Portal prüfen.",
        "subject": "WorkPass: Anmeldung außerhalb der Arbeitszeit — {name}",
    },
    "en": {
        "title": "Sign-in outside working hours",
        "body": "{name} tried to sign in outside working hours ({channel}{gate}).{window}",
        "window": " Scheduled time: {start}–{end}.",
        "reason": "Reason",
        "channel": "Channel",
        "footer": "The check-in was rejected. Please review shift and working hours in the company portal.",
        "subject": "WorkPass: Sign-in outside working hours — {name}",
    },
    "ar": {
        "title": "تسجيل دخول خارج ساعات العمل",
        "body": "حاول {name} تسجيل الدخول خارج ساعات العمل ({channel}{gate}).{window}",
        "window": " الوقت المجدول: {start}–{end}.",
        "reason": "السبب",
        "channel": "القناة",
        "footer": "تم رفض تسجيل الدخول. يرجى مراجعة أوقات الوردية والعمل في بوابة الشركة.",
        "subject": "WorkPass: تسجيل دخول خارج ساعات العمل — {name}",
    },
    "fr": {
        "title": "Connexion hors heures de travail",
        "body": "{name} a tenté de se connecter hors des heures de travail ({channel}{gate}).{window}",
        "window": " Horaire prévu : {start}–{end}.",
        "reason": "Motif",
        "channel": "Canal",
        "footer": "Le pointage a été refusé. Veuillez vérifier les horaires dans le portail entreprise.",
        "subject": "WorkPass: Connexion hors heures de travail — {name}",
    },
    "tr": {
        "title": "Çalışma saatleri dışında giriş",
        "body": "{name} çalışma saatleri dışında giriş yapmayı denedi ({channel}{gate}).{window}",
        "window": " Planlanan saat: {start}–{end}.",
        "reason": "Neden",
        "channel": "Kanal",
        "footer": "Giriş reddedildi. Lütfen şirket portalında vardiya ve çalışma saatlerini kontrol edin.",
        "subject": "WorkPass: Çalışma saatleri dışında giriş — {name}",
    },
}

# Keep DE labels for backward-compatible imports/tests.
_CHANNEL_LABELS_DE = _CHANNEL_LABELS["de"]


def _normalize_notify_lang(lang: str | None) -> str:
    code = str(lang or "de").strip().lower()[:2] or "de"
    if code in _OUTSIDE_HOURS_COPY:
        return code
    return "de"


def _company_notify_lang(db, company_id: str) -> str:
    try:
        row = db.execute(
            "SELECT invoice_email_lang FROM companies WHERE id = ?",
            (str(company_id),),
        ).fetchone()
        if row and "invoice_email_lang" in row.keys():
            return _normalize_notify_lang(row["invoice_email_lang"])
    except Exception:
        pass
    return "de"


def _outside_hours_channel_label(channel: str, lang: str) -> str:
    packs = _CHANNEL_LABELS.get(lang) or _CHANNEL_LABELS["de"]
    key = str(channel or "gps").strip().lower() or "gps"
    return packs.get(key, key)


def build_outside_hours_alert_copy(
    *,
    worker_name: str,
    reason: str,
    channel: str,
    gate: str = "",
    shift_start: str = "",
    shift_end: str = "",
    lang: str = "de",
) -> dict[str, str]:
    """Localized title/body/subject for outside-hours check-in alerts."""
    lang_key = _normalize_notify_lang(lang)
    copy = _OUTSIDE_HOURS_COPY.get(lang_key) or _OUTSIDE_HOURS_COPY["de"]
    channel_label = _outside_hours_channel_label(channel, lang_key)
    gate_clean = str(gate or "").strip()
    gate_bit = f" ({gate_clean})" if gate_clean else ""
    start = str(shift_start or "").strip()[:5]
    end = str(shift_end or "").strip()[:5]
    window = ""
    if start and end:
        window = copy["window"].format(start=start, end=end)
    body = copy["body"].format(
        name=str(worker_name or "").strip() or "—",
        channel=channel_label,
        gate=gate_bit,
        window=window,
    ).strip()
    return {
        "lang": lang_key,
        "title": copy["title"],
        "body": body,
        "subject": copy["subject"].format(name=str(worker_name or "").strip() or "—"),
        "reasonLabel": copy["reason"],
        "channelLabel": copy["channel"],
        "channelValue": channel_label,
        "footer": copy["footer"],
        "reason": str(reason or "").strip(),
    }


def _company_admin_recipients(db, company_id: str) -> list[str]:
    emails: list[str] = []
    seen: set[str] = set()
    try:
        company = db.execute(
            "SELECT billing_email FROM companies WHERE id = ?",
            (str(company_id),),
        ).fetchone()
        if company:
            billing = str(company["billing_email"] or "").strip()
            if billing and "@" in billing and billing.lower() not in seen:
                seen.add(billing.lower())
                emails.append(billing)
    except Exception:
        pass
    try:
        rows = db.execute(
            """
            SELECT email FROM users
            WHERE company_id = ? AND role = 'company-admin'
              AND COALESCE(email, '') <> ''
            """,
            (str(company_id),),
        ).fetchall()
        for row in rows:
            addr = str(row["email"] or "").strip()
            if addr and "@" in addr and addr.lower() not in seen:
                seen.add(addr.lower())
                emails.append(addr)
    except Exception:
        pass
    return emails


def notify_company_deployment_day_declined(
    db,
    *,
    company_id: str,
    worker_id: str,
    worker_name: str,
    work_date: str,
    location: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """Alert Betrieb when a worker declines a scheduled deployment day."""
    loc = str(location or "").strip() or "—"
    reason_clean = str(reason or "").strip()
    reason_line = f"\nGrund: {reason_clean}" if reason_clean else ""
    message = (
        f"{worker_name} kann am {work_date} nicht arbeiten "
        f"(Einsatz: {loc}).{reason_line}"
    ).strip()

    alert_id = None
    try:
        from backend.server import create_system_alert

        alert_id = create_system_alert(
            db,
            code="deployment_worker_declined",
            severity="warning",
            message=message[:500],
            details=json.dumps(
                {
                    "companyId": str(company_id),
                    "workerId": str(worker_id),
                    "workDate": work_date,
                    "location": loc,
                    "reason": reason_clean,
                },
                ensure_ascii=False,
            ),
            dedup_minutes=5,
        )
    except Exception:
        pass

    try:
        from backend.app.platform.inbox.events import notify_inbox_changed

        notify_inbox_changed(
            str(company_id),
            source="deployment_decline",
            alert_title="Einsatz abgelehnt",
            alert_message=message[:240],
            severity="warning",
        )
    except Exception:
        pass

    try:
        from backend.app.platform.workforce.deployment_month import mark_month_edited

        parts = str(work_date)[:10].split("-")
        if len(parts) >= 2:
            mark_month_edited(db, str(company_id), int(parts[0]), int(parts[1]))
    except Exception:
        pass

    emails_sent = 0
    recipients = _company_admin_recipients(db, company_id)
    if recipients:
        try:
            from backend.app.core.platform_env import default_noreply_email
            from backend.server import _send_via_any_api, get_public_base_url

            settings = db.execute("SELECT smtp_sender_email, smtp_sender_name FROM settings WHERE id = 1").fetchone()
            sender_email = (settings["smtp_sender_email"] if settings else "") or default_noreply_email()
            sender_name = (settings["smtp_sender_name"] if settings else "") or "WorkPass"
            base = get_public_base_url().rstrip("/")
            admin_hint = f"{base}/admin-v2/index.html" if base else ""
            subject = f"WorkPass: Einsatz abgelehnt — {worker_name} ({work_date})"
            text_body = (
                f"{message}\n\n"
                f"Bitte Einsatzplan im Betrieb-Portal prüfen und ggf. anpassen.\n"
                f"{admin_hint}\n"
            )
            msg_safe = html.escape(message).replace("\n", "<br>")
            reason_html = (
                f'<p style="color:#555;"><strong>Grund:</strong> {html.escape(reason_clean)}</p>'
                if reason_clean
                else ""
            )
            html_body = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f4f6f8;margin:0;padding:24px;">
<table width="100%"><tr><td align="center">
<table width="560" style="background:#fff;border-radius:10px;padding:24px;max-width:560px;">
  <tr><td>
    <h2 style="margin:0 0 12px;color:#b45309;">Einsatztag abgelehnt</h2>
    <p style="color:#333;line-height:1.5;">{msg_safe}</p>
    {reason_html}
    <p style="margin-top:20px;color:#666;font-size:13px;">
      Bitte den Monats-Einsatzplan prüfen und bei Bedarf umplanen.
    </p>
  </td></tr>
</table></td></tr></table></body></html>"""
            for recipient in recipients:
                ok, _, _provider = _send_via_any_api(
                    subject,
                    sender_email,
                    sender_name,
                    recipient,
                    text_body,
                    html_body,
                )
                if ok:
                    emails_sent += 1
        except Exception:
            pass

    return {
        "ok": True,
        "alertId": alert_id,
        "emailsSent": emails_sent,
        "recipientCount": len(recipients),
    }


def notify_company_shift_swap_accepted(
    db,
    *,
    company_id: str,
    from_worker_id: str,
    from_worker_name: str,
    to_worker_id: str,
    to_worker_name: str,
    start_time: str = "",
    end_time: str = "",
    site: str = "",
    target_start_time: str = "",
    target_end_time: str = "",
    target_site: str = "",
    mutual: bool = False,
) -> dict[str, Any]:
    """Alert Betrieb when two workers complete a shift handoff/swap."""
    window = f"{(start_time or '')[:16]} – {(end_time or '')[:16]}".strip(" –")
    loc = str(site or "").strip()
    loc_bit = f" · {loc}" if loc else ""
    if mutual and (target_start_time or target_end_time):
        other = f"{(target_start_time or '')[:16]} – {(target_end_time or '')[:16]}".strip(" –")
        other_loc = f" · {str(target_site or '').strip()}" if str(target_site or "").strip() else ""
        message = (
            f"Schichttausch: {from_worker_name} ↔ {to_worker_name}. "
            f"{from_worker_name} übernimmt {other}{other_loc}; "
            f"{to_worker_name} übernimmt {window}{loc_bit}."
        ).strip()
    else:
        message = (
            f"Schicht abgegeben: {from_worker_name} → {to_worker_name} "
            f"({window}{loc_bit})."
        ).strip()

    alert_id = None
    try:
        from backend.server import create_system_alert

        alert_id = create_system_alert(
            db,
            code="shift_swap_accepted",
            severity="info",
            message=message[:500],
            details=json.dumps(
                {
                    "companyId": str(company_id),
                    "fromWorkerId": str(from_worker_id),
                    "toWorkerId": str(to_worker_id),
                    "mutual": bool(mutual),
                    "startTime": start_time,
                    "endTime": end_time,
                    "site": loc,
                },
                ensure_ascii=False,
            ),
            dedup_minutes=2,
        )
    except Exception:
        pass

    try:
        from backend.app.platform.inbox.events import notify_inbox_changed

        notify_inbox_changed(
            str(company_id),
            source="shift_swap",
            alert_title="Schichttausch",
            alert_message=message[:240],
            severity="info",
        )
    except Exception:
        pass

    emails_sent = 0
    recipients = _company_admin_recipients(db, company_id)
    if recipients:
        try:
            from backend.app.core.platform_env import default_noreply_email
            from backend.server import _send_via_any_api, get_public_base_url

            settings = db.execute("SELECT smtp_sender_email, smtp_sender_name FROM settings WHERE id = 1").fetchone()
            sender_email = (settings["smtp_sender_email"] if settings else "") or default_noreply_email()
            sender_name = (settings["smtp_sender_name"] if settings else "") or "WorkPass"
            base = get_public_base_url().rstrip("/")
            admin_hint = f"{base}/admin-v2/index.html" if base else ""
            subject = f"WorkPass: Schichttausch — {from_worker_name} / {to_worker_name}"
            text_body = f"{message}\n\nBitte Schichten im Betrieb-Portal prüfen.\n{admin_hint}\n"
            msg_safe = html.escape(message)
            html_body = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f4f6f8;margin:0;padding:24px;">
<table width="100%"><tr><td align="center">
<table width="560" style="background:#fff;border-radius:10px;padding:24px;max-width:560px;">
  <tr><td>
    <h2 style="margin:0 0 12px;color:#0f766e;">Schichttausch</h2>
    <p style="color:#333;line-height:1.5;">{msg_safe}</p>
    <p style="margin-top:20px;color:#666;font-size:13px;">Bitte den Schichtplan prüfen.</p>
  </td></tr>
</table></td></tr></table></body></html>"""
            for recipient in recipients:
                ok, _, _provider = _send_via_any_api(
                    subject,
                    sender_email,
                    sender_name,
                    recipient,
                    text_body,
                    html_body,
                )
                if ok:
                    emails_sent += 1
        except Exception:
            pass

    return {
        "ok": True,
        "alertId": alert_id,
        "emailsSent": emails_sent,
        "recipientCount": len(recipients),
    }


def notify_company_outside_hours_checkin_attempt(
    db,
    *,
    company_id: str,
    worker_id: str,
    worker_name: str,
    reason: str,
    channel: str = "gps",
    gate: str = "",
    shift_start: str = "",
    shift_end: str = "",
    message: str = "",
    lang: str | None = None,
) -> dict[str, Any]:
    """Alert Betrieb when a worker tries to check in outside shift/work hours."""
    reason_clean = str(reason or "").strip() or "outside_work_hours"
    channel_key = str(channel or "gps").strip().lower() or "gps"
    gate_clean = str(gate or "").strip()
    shift_start_clean = str(shift_start or "").strip()[:5]
    shift_end_clean = str(shift_end or "").strip()[:5]
    lang_key = _normalize_notify_lang(lang) if lang else _company_notify_lang(db, company_id)
    # Stable DE body for create_system_alert dedup (language-independent).
    stable = build_outside_hours_alert_copy(
        worker_name=worker_name,
        reason=reason_clean,
        channel=channel_key,
        gate=gate_clean,
        shift_start=shift_start_clean,
        shift_end=shift_end_clean,
        lang="de",
    )
    localized = build_outside_hours_alert_copy(
        worker_name=worker_name,
        reason=reason_clean,
        channel=channel_key,
        gate=gate_clean,
        shift_start=shift_start_clean,
        shift_end=shift_end_clean,
        lang=lang_key,
    )
    detail = str(message or "").strip()
    alert_message = stable["body"]
    if detail and detail not in alert_message:
        alert_message = f"{alert_message} {detail}".strip()
    display_message = localized["body"]
    if detail and detail not in display_message:
        display_message = f"{display_message} {detail}".strip()

    alert_id = None
    try:
        from backend.server import create_system_alert

        # Stable DE message enables 15-min spam dedup on retries.
        alert_id = create_system_alert(
            db,
            code="outside_hours_checkin_attempt",
            severity="warning",
            message=alert_message[:500],
            details=json.dumps(
                {
                    "companyId": str(company_id),
                    "workerId": str(worker_id),
                    "workerName": str(worker_name or ""),
                    "reason": reason_clean,
                    "channel": channel_key,
                    "gate": gate_clean,
                    "shiftStart": shift_start_clean,
                    "shiftEnd": shift_end_clean,
                    "lang": lang_key,
                    "i18nKey": "outside_hours_checkin_attempt",
                },
                ensure_ascii=False,
            ),
            dedup_minutes=15,
        )
    except Exception:
        pass

    # Deduped: skip inbox/email/push so GPS retries do not flood the Betrieb.
    if alert_id is None:
        return {
            "ok": True,
            "deduped": True,
            "alertId": None,
            "emailsSent": 0,
            "recipientCount": 0,
        }

    try:
        from backend.app.platform.inbox.events import notify_inbox_changed

        notify_inbox_changed(
            str(company_id),
            source="outside_hours_checkin",
            alert_title=localized["title"],
            alert_message=display_message[:240],
            severity="warning",
        )
    except Exception:
        pass

    try:
        from backend.app.platform.push.admin_delivery import deliver_admin_push

        deliver_admin_push(
            db,
            str(company_id),
            localized["title"],
            display_message[:180],
            tag=f"outside-hours-{worker_id}",
            extra={
                "workerId": str(worker_id),
                "reason": reason_clean,
                "channel": channel_key,
                "url": "/admin-v2/index.html",
                "i18nKey": "outside_hours_checkin_attempt",
            },
        )
    except Exception:
        pass

    emails_sent = 0
    recipients = _company_admin_recipients(db, company_id)
    if recipients:
        try:
            from backend.app.core.platform_env import default_noreply_email
            from backend.server import _send_via_any_api, get_public_base_url

            settings = db.execute(
                "SELECT smtp_sender_email, smtp_sender_name FROM settings WHERE id = 1"
            ).fetchone()
            sender_email = (settings["smtp_sender_email"] if settings else "") or default_noreply_email()
            sender_name = (settings["smtp_sender_name"] if settings else "") or "WorkPass"
            base = get_public_base_url().rstrip("/")
            admin_hint = f"{base}/admin-v2/index.html" if base else ""
            subject = localized["subject"]
            text_body = (
                f"{display_message}\n\n"
                f"{localized['reasonLabel']}: {reason_clean}\n"
                f"{localized['channelLabel']}: {localized['channelValue']}\n\n"
                f"{localized['footer']}\n"
                f"{admin_hint}\n"
            )
            msg_safe = html.escape(display_message)
            html_body = f"""<!DOCTYPE html>
<html lang="{html.escape(lang_key)}"><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f4f6f8;margin:0;padding:24px;">
<table width="100%"><tr><td align="center">
<table width="560" style="background:#fff;border-radius:10px;padding:24px;max-width:560px;">
  <tr><td>
    <h2 style="margin:0 0 12px;color:#b45309;">{html.escape(localized["title"])}</h2>
    <p style="color:#333;line-height:1.5;">{msg_safe}</p>
    <p style="color:#555;"><strong>{html.escape(localized["reasonLabel"])}:</strong> {html.escape(reason_clean)}</p>
    <p style="color:#555;"><strong>{html.escape(localized["channelLabel"])}:</strong> {html.escape(localized["channelValue"])}</p>
    <p style="margin-top:20px;color:#666;font-size:13px;">
      {html.escape(localized["footer"])}
    </p>
  </td></tr>
</table></td></tr></table></body></html>"""
            for recipient in recipients:
                ok, _, _provider = _send_via_any_api(
                    subject,
                    sender_email,
                    sender_name,
                    recipient,
                    text_body,
                    html_body,
                )
                if ok:
                    emails_sent += 1
        except Exception:
            pass

    return {
        "ok": True,
        "deduped": False,
        "alertId": alert_id,
        "emailsSent": emails_sent,
        "recipientCount": len(recipients),
        "lang": lang_key,
    }


def maybe_notify_outside_hours_attempt(
    db,
    worker: Any,
    attendance: dict[str, Any] | None,
    *,
    channel: str,
    gate: str = "",
) -> dict[str, Any] | None:
    """Fire employer alert when eligibility denies check-in for outside-hours reasons."""
    if not attendance or attendance.get("ok"):
        return None
    reason = str(attendance.get("reason") or "").strip()
    if reason not in OUTSIDE_HOURS_NOTIFY_REASONS:
        return None
    try:
        worker_id = str(worker["id"])
        company_id = str(worker["company_id"])
        first = str(worker["first_name"] or "").strip()
        last = str(worker["last_name"] or "").strip()
        worker_name = f"{first} {last}".strip() or worker_id
    except Exception:
        return None
    return notify_company_outside_hours_checkin_attempt(
        db,
        company_id=company_id,
        worker_id=worker_id,
        worker_name=worker_name,
        reason=reason,
        channel=channel,
        gate=gate,
        shift_start=str(attendance.get("shiftStart") or ""),
        shift_end=str(attendance.get("shiftEnd") or ""),
        message=str(attendance.get("message") or ""),
    )


_REPEATED_LATE_COPY = {
    "de": {
        "title": "Wiederholte Verspätung",
        "body": "{name} war {streak} Mal hintereinander zu spät.",
        "footer": "Bitte mit dem Mitarbeiter sprechen und Schichtzeiten prüfen.",
        "subject": "WorkPass: Wiederholte Verspätung — {name}",
    },
    "en": {
        "title": "Repeated lateness",
        "body": "{name} was late {streak} times in a row.",
        "footer": "Please speak with the worker and review shift times.",
        "subject": "WorkPass: Repeated lateness — {name}",
    },
    "ar": {
        "title": "تأخير متكرر",
        "body": "تأخر {name} {streak} مرات متتالية.",
        "footer": "يرجى التواصل مع الموظف ومراجعة أوقات الوردية.",
        "subject": "WorkPass: تأخير متكرر — {name}",
    },
    "fr": {
        "title": "Retards répétés",
        "body": "{name} a été en retard {streak} fois de suite.",
        "footer": "Veuillez parler au collaborateur et vérifier les horaires.",
        "subject": "WorkPass: Retards répétés — {name}",
    },
    "tr": {
        "title": "Tekrarlayan gecikme",
        "body": "{name} art arda {streak} kez geç kaldı.",
        "footer": "Lütfen çalışanla görüşün ve vardiya saatlerini kontrol edin.",
        "subject": "WorkPass: Tekrarlayan gecikme — {name}",
    },
}


def build_repeated_late_alert_copy(
    *,
    worker_name: str,
    streak: int,
    lang: str = "de",
) -> dict[str, str]:
    lang_key = _normalize_notify_lang(lang)
    copy = _REPEATED_LATE_COPY.get(lang_key) or _REPEATED_LATE_COPY["de"]
    name = str(worker_name or "").strip() or "—"
    body = copy["body"].format(name=name, streak=int(streak or 0))
    return {
        "lang": lang_key,
        "title": copy["title"],
        "body": body,
        "footer": copy["footer"],
        "subject": copy["subject"].format(name=name),
    }


def notify_company_repeated_late_checkin(
    db,
    *,
    company_id: str,
    worker_id: str,
    worker_name: str,
    streak: int,
    lang: str | None = None,
) -> dict[str, Any]:
    """Alert Betrieb when a worker reaches a consecutive late streak threshold."""
    streak_n = max(1, int(streak or 0))
    lang_key = _normalize_notify_lang(lang) if lang else _company_notify_lang(db, company_id)
    # Stable DE body (no streak count) so 24h dedup stays per worker.
    stable_body = f"{str(worker_name or '').strip() or 'Mitarbeiter'} war wiederholt hintereinander zu spät."
    localized = build_repeated_late_alert_copy(
        worker_name=worker_name, streak=streak_n, lang=lang_key
    )

    alert_id = None
    try:
        from backend.server import create_system_alert

        # Dedup 24h per worker via stable DE message + code.
        alert_id = create_system_alert(
            db,
            code="repeated_late_checkin",
            severity="warning",
            message=stable_body[:500],
            details=json.dumps(
                {
                    "companyId": str(company_id),
                    "workerId": str(worker_id),
                    "workerName": str(worker_name or ""),
                    "streak": streak_n,
                    "lang": lang_key,
                    "i18nKey": "repeated_late_checkin",
                },
                ensure_ascii=False,
            ),
            dedup_minutes=60 * 24,
        )
    except Exception:
        pass

    if alert_id is None:
        return {
            "ok": True,
            "deduped": True,
            "alertId": None,
            "emailsSent": 0,
            "recipientCount": 0,
        }

    try:
        from backend.app.platform.inbox.events import notify_inbox_changed

        notify_inbox_changed(
            str(company_id),
            source="repeated_late",
            alert_title=localized["title"],
            alert_message=localized["body"][:240],
            severity="warning",
        )
    except Exception:
        pass

    try:
        from backend.app.platform.push.admin_delivery import deliver_admin_push

        deliver_admin_push(
            db,
            str(company_id),
            localized["title"],
            localized["body"][:180],
            tag=f"repeated-late-{worker_id}",
            extra={
                "workerId": str(worker_id),
                "streak": streak_n,
                "url": "/admin-v2/index.html",
                "i18nKey": "repeated_late_checkin",
            },
        )
    except Exception:
        pass

    emails_sent = 0
    recipients = _company_admin_recipients(db, company_id)
    if recipients:
        try:
            from backend.app.core.platform_env import default_noreply_email
            from backend.server import _send_via_any_api, get_public_base_url

            settings = db.execute(
                "SELECT smtp_sender_email, smtp_sender_name FROM settings WHERE id = 1"
            ).fetchone()
            sender_email = (settings["smtp_sender_email"] if settings else "") or default_noreply_email()
            sender_name = (settings["smtp_sender_name"] if settings else "") or "WorkPass"
            base = get_public_base_url().rstrip("/")
            admin_hint = f"{base}/admin-v2/index.html" if base else ""
            text_body = (
                f"{localized['body']}\n\n{localized['footer']}\n{admin_hint}\n"
            )
            html_body = f"""<!DOCTYPE html>
<html lang="{html.escape(lang_key)}"><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f4f6f8;margin:0;padding:24px;">
<table width="100%"><tr><td align="center">
<table width="560" style="background:#fff;border-radius:10px;padding:24px;max-width:560px;">
  <tr><td>
    <h2 style="margin:0 0 12px;color:#b45309;">{html.escape(localized["title"])}</h2>
    <p style="color:#333;line-height:1.5;">{html.escape(localized["body"])}</p>
    <p style="margin-top:20px;color:#666;font-size:13px;">{html.escape(localized["footer"])}</p>
  </td></tr>
</table></td></tr></table></body></html>"""
            for recipient in recipients:
                ok, _, _provider = _send_via_any_api(
                    localized["subject"],
                    sender_email,
                    sender_name,
                    recipient,
                    text_body,
                    html_body,
                )
                if ok:
                    emails_sent += 1
        except Exception:
            pass

    return {
        "ok": True,
        "deduped": False,
        "alertId": alert_id,
        "emailsSent": emails_sent,
        "recipientCount": len(recipients),
        "lang": lang_key,
    }


_FORECAST_COPY = {
    "de": {
        "title": "Prognose für morgen",
        "body": "Morgen ({date}): ca. {onSite} vor Ort, {absent} Ausfallrisiko.",
        "footer": "Bitte Personalplanung prüfen — Details im Dashboard.",
        "subject": "WorkPass: Prognose morgen — {onSite} vor Ort / {absent} Risiko",
    },
    "en": {
        "title": "Tomorrow forecast",
        "body": "Tomorrow ({date}): about {onSite} on site, {absent} absence risk.",
        "footer": "Please review staffing — details in the dashboard.",
        "subject": "WorkPass: Tomorrow forecast — {onSite} on site / {absent} risk",
    },
    "ar": {
        "title": "توقعات الغد",
        "body": "غداً ({date}): حوالي {onSite} في الموقع، {absent} خطر غياب.",
        "footer": "يرجى مراجعة تخطيط القوى العاملة — التفاصيل في لوحة التحكم.",
        "subject": "WorkPass: توقعات الغد — {onSite} في الموقع / {absent} خطر",
    },
}


def notify_company_tomorrow_forecast(
    db,
    *,
    company_id: str,
    forecast: dict[str, Any],
    lang: str | None = None,
) -> dict[str, Any]:
    """Proactive employer alert when tomorrow forecast shows absence risk."""
    expected_absent = int(forecast.get("expectedAbsent") or 0)
    if expected_absent <= 0:
        return {"ok": True, "skipped": True, "reason": "no_absent_risk"}
    lang_key = _normalize_notify_lang(lang) if lang else _company_notify_lang(db, company_id)
    copy = _FORECAST_COPY.get(lang_key) or _FORECAST_COPY["de"]
    on_site = int(forecast.get("expectedOnSite") or 0)
    day = str(forecast.get("date") or "")
    body = copy["body"].format(date=day, onSite=on_site, absent=expected_absent)
    title = copy["title"]
    # Include top driver names for richer inbox message.
    names: list[str] = []
    for driver in forecast.get("drivers") or []:
        for item in (driver.get("items") or [])[:4]:
            nm = str(item.get("name") or "").strip()
            if nm and nm not in names:
                names.append(nm)
        if len(names) >= 5:
            break
    if names:
        body = f"{body} {', '.join(names[:5])}"

    alert_id = None
    try:
        from backend.server import create_system_alert

        # One alert per company per forecast date (via message + code + 20h dedup).
        alert_id = create_system_alert(
            db,
            code="tomorrow_attendance_forecast",
            severity="info" if expected_absent < 4 else "warning",
            message=body[:500],
            details=json.dumps(
                {
                    "companyId": str(company_id),
                    "date": day,
                    "expectedOnSite": on_site,
                    "expectedAbsent": expected_absent,
                    "i18nKey": "tomorrow_attendance_forecast",
                    "names": names[:8],
                },
                ensure_ascii=False,
            ),
            dedup_minutes=60 * 20,
        )
    except Exception:
        pass

    if alert_id is None:
        return {"ok": True, "deduped": True, "alertId": None}

    try:
        from backend.app.platform.inbox.events import notify_inbox_changed

        notify_inbox_changed(
            str(company_id),
            source="tomorrow_forecast",
            alert_title=title,
            alert_message=body[:240],
            severity="warning" if expected_absent >= 4 else "info",
        )
    except Exception:
        pass

    emails_sent = 0
    recipients = _company_admin_recipients(db, company_id)
    if recipients:
        try:
            from backend.app.core.platform_env import default_noreply_email
            from backend.server import _send_via_any_api, get_public_base_url

            settings = db.execute(
                "SELECT smtp_sender_email, smtp_sender_name FROM settings WHERE id = 1"
            ).fetchone()
            sender_email = (settings["smtp_sender_email"] if settings else "") or default_noreply_email()
            sender_name = (settings["smtp_sender_name"] if settings else "") or "WorkPass"
            base = get_public_base_url().rstrip("/")
            admin_hint = f"{base}/admin-v2/index.html" if base else ""
            subject = copy["subject"].format(onSite=on_site, absent=expected_absent)
            text_body = f"{body}\n\n{copy['footer']}\n{admin_hint}\n"
            html_body = f"""<!DOCTYPE html>
<html lang="{html.escape(lang_key)}"><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f4f6f8;margin:0;padding:24px;">
<table width="100%"><tr><td align="center">
<table width="560" style="background:#fff;border-radius:10px;padding:24px;max-width:560px;">
  <tr><td>
    <h2 style="margin:0 0 12px;color:#0f766e;">{html.escape(title)}</h2>
    <p style="color:#333;line-height:1.5;">{html.escape(body)}</p>
    <p style="margin-top:20px;color:#666;font-size:13px;">{html.escape(copy["footer"])}</p>
  </td></tr>
</table></td></tr></table></body></html>"""
            for recipient in recipients:
                ok, _, _provider = _send_via_any_api(
                    subject,
                    sender_email,
                    sender_name,
                    recipient,
                    text_body,
                    html_body,
                )
                if ok:
                    emails_sent += 1
        except Exception:
            pass

    return {
        "ok": True,
        "deduped": False,
        "alertId": alert_id,
        "emailsSent": emails_sent,
        "recipientCount": len(recipients),
    }


