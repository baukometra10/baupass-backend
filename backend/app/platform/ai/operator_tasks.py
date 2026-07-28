"""Deterministic operator tasks — real actions with confirmation, no LLM required."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


_PREPARE_PLAN = re.compile(
    r"(einsatzplan|monatsplan|deployment\s*plan|خطة\s*(?:الانتشار|العمل|الشهر)).{0,40}"
    r"(vorbereiten|vorbreit|erstell|mach|anlegen|vorbereit|prepare|create|جهز|أنشئ|اعمل)|"
    r"(vorbereiten|erstell|mach|prepare|جهز).{0,40}"
    r"(einsatzplan|monatsplan|deployment|خطة)",
    re.I | re.S,
)

_SEND_PLAN = re.compile(
    r"(einsatzplan|monatsplan|deployment|خطة).{0,40}"
    r"(senden|versenden|verschicken|mail|push|send|أرسل|ارسل)|"
    r"(senden|versenden|send|أرسل).{0,40}"
    r"(einsatzplan|monatsplan|deployment|خطة)",
    re.I | re.S,
)

_STATUS_PLAN = re.compile(
    r"(einsatzplan|monatsplan|deployment|خطة).{0,30}"
    r"(status|stand|bereit|ready|konflikt|عرض|حالة)|"
    r"(status|stand).{0,30}(einsatzplan|monatsplan|خطة)",
    re.I | re.S,
)

_NOTIFY = re.compile(
    r"(schreib|nachricht|push|benachrichtig|informier|erinnere|remind|message|notify|notify|"
    r"أرسل|ارسل|ذكّر|ذكر|رسالة).{0,80}"
    r"(an|to|ل|إلى)\s+([A-Za-zÀ-ÿ\u0600-\u06FF][A-Za-zÀ-ÿ\u0600-\u06FF\s\-']{1,40})"
    r"|"
    r"(an|to)\s+([A-Za-zÀ-ÿ\u0600-\u06FF][A-Za-zÀ-ÿ\u0600-\u06FF\s\-']{1,40}).{0,40}"
    r"(schreib|nachricht|push|message|notify|رسالة)",
    re.I | re.S,
)

_LEAVE_APPROVE = re.compile(
    r"(urlaub|leave|abwesen|إجاز).{0,40}(genehmig|freigeb|approv|موافق|اقبل)|"
    r"(genehmig|approv|موافق).{0,40}(urlaub|leave|إجاز)",
    re.I | re.S,
)

_LEAVE_REJECT = re.compile(
    r"(urlaub|leave|abwesen|إجاز).{0,40}(ablehn|zurückweis|reject|رفض)|"
    r"(ablehn|zurückweis|reject|رفض).{0,40}(urlaub|leave|إجاز)",
    re.I | re.S,
)

_LEAVE_LIST = re.compile(
    r"(offene|pending|ausstehend).{0,20}(urlaub|leave|إجاز)|"
    r"(urlaub|leave|إجاز).{0,20}(offen|pending|ausstehend|طلبات)",
    re.I | re.S,
)

_ONSITE = re.compile(
    r"(wer ist|who is|من|qui est|quién|chi è|kim).{0,24}"
    r"(vor ort|on ?site|baustelle|موقع|حاضر|sur site|en obra|in cantiere|sahada)|"
    r"(anwesend|on ?site|vor ort|في الموقع|sur site|en obra|in cantiere)",
    re.I | re.S,
)

_EXPIRED_DOCS = re.compile(
    r"(abgelaufen|expired|fällige|fälligkeit|وثائق?\s*منتهي|مستند.*انته|"
    r"documents?\s*expir|documentos?\s*caduc|documenti\s*scadut|süresi\s*dol|"
    r"dokumente?\s*(erinner|mahn|remind)|erinner.*dokument)",
    re.I | re.S,
)

_LATE = re.compile(
    r"(verspät|zu spät|late\s*worker|pünktlich|تأخ[ير]|متأخر|"
    r"en retard|llega\s*tarde|in ritardo|geç\s*kal)",
    re.I | re.S,
)

_SECURITY = re.compile(
    r"(security|sicherheit|sicherheits.?alert|تنبيه\s*أمن|أمن(?!\s*النظام))",
    re.I | re.S,
)

_SYSTEM_ALERTS = re.compile(
    r"(system.?alert|systemhinweis|systemmeldung|ack.*alert|hinweise?\s*schließ|"
    r"تنبيهات?\s*النظام)",
    re.I | re.S,
)

_BROADCAST = re.compile(
    r"(an\s+alle|broadcast|rundnachricht|teamnachricht|alle\s+mitarbeiter|"
    r"à\s+tous|a\s+todos|a\s+tutti|herkese|"
    r"رسالة\s*للجميع|إلى\s*الجميع|mitteilung\s+an\s+(?:alle|team))",
    re.I | re.S,
)

_INBOX = re.compile(
    r"(inbox|posteingang|aufgaben|offene\s+aufgaben|الوارد|المهام)",
    re.I | re.S,
)

_PRIORITIZE = re.compile(
    r"(priorit|was\s+soll\s+ich|was\s+muss\s+ich|today'?s?\s+priorit|"
    r"empfehlung|recommend|what\s+should\s+i|"
    r"ماذا\s+أفعل|أولوي|ماذا\s+يجب|"
    r"que\s+dois[- ]je|que\s+hacer|ne\s+yapmalıyım|cosa\s+devo)",
    re.I | re.S,
)

_BRIEFING = re.compile(
    r"(briefing|lagebild|tageslage|daily\s*brief|was\s+ist\s+heute|"
    r"résumé\s+du\s+jour|briefing\s+quotidien|resumen\s+diario|günlük\s+özet|"
    r"riepilogo\s+giornaliero|podsumowanie\s+dnia|"
    r"zusammenfassung\s+(heute|tag)|ملخص\s*(اليوم|اليومية)|تقرير\s*اليوم|"
    r"كيف\s*الوضع|wie\s+steht'?s|status\s+heute)",
    re.I | re.S,
)

_FIND_WORKER = re.compile(
    r"(finde|such|zeige|öffne|profil|wer\s+ist|find|search|show|open|"
    r"ابحث|أين|من\s+هو|عرض\s+ملف)\s+"
    r"([A-Za-zÀ-ÿ\u0600-\u06FF][A-Za-zÀ-ÿ\u0600-\u06FF\s\-']{1,40})",
    re.I | re.S,
)

_PRESENCE = re.compile(
    r"(anwesenheits?übersicht|presence\s*summary|anwesenheitsstatus|"
    r"ملخص\s*الحضور|حالة\s*الحضور|wie\s+viele\s+(sind\s+)?(da|anwesend))",
    re.I | re.S,
)

_FORECAST = re.compile(
    r"(morgen|tomorrow|forecast|prognose|غدا|بكرة|vorhersage)",
    re.I | re.S,
)

_OUTSIDE_HOURS = re.compile(
    r"(außerhalb|outside\s*hours|nach\s*dienstende|außer\s*der\s*zeit|"
    r"خارج\s*الدوام|خارج\s*ساعات)",
    re.I | re.S,
)

_RISK = re.compile(
    r"(risiko|risk|workforce\s*risk|attendance\s*risk|gefährdung|"
    r"مخاطر|خطر\s*القوى)",
    re.I | re.S,
)

_TIMELINE = re.compile(
    r"(zutritt|timeline|zugangsprotokoll|access\s*(log|timeline)|"
    r"سجل\s*الدخول|خط\s*الزمن|اليوم\s*wer\s*kam)",
    re.I | re.S,
)

_FRAUD = re.compile(
    r"(betrug|fraud|anomal|hochfrequenz|suspicious|"
    r"احتيال|شذوذ)",
    re.I | re.S,
)

_OPEN_CONTRACTS = re.compile(
    r"(vertr[aä]ge?|contracts?|عقد|عقود)",
    re.I | re.S,
)

_OPEN_DOCS = re.compile(
    r"(dokumenten?editor|docs?\s*editor|dokumentenverwaltung|"
    r"محرر\s*الوثائق|المستندات)",
    re.I | re.S,
)

_OPEN_CHAT = re.compile(
    r"(chat|nachrichten?\s*center|arbeiter\s*chat|محادثة|دردشة)",
    re.I | re.S,
)

_OPEN_WORKERS = re.compile(
    r"(mitarbeiterliste|arbeiter\s*öffnen|workers?\s*(list|öffnen|open)|"
    r"قائمة\s*الموظفين|افتح\s*العمال)",
    re.I | re.S,
)

_OPEN_ACCESS = re.compile(
    r"(anwesenheit\s*öffnen|zutritt\s*öffnen|access\s*(tab|öffnen)|"
    r"افتح\s*الحضور)",
    re.I | re.S,
)


def _lang_text(lang: str, de: str, en: str, ar: str, **extra: str) -> str:
    """Pick operator copy for UI language (all 8 system langs; extras optional)."""
    from .operator_i18n import pick

    return pick(
        lang,
        de=de,
        en=en,
        ar=ar,
        tr=str(extra.get("tr") or ""),
        fr=str(extra.get("fr") or ""),
        es=str(extra.get("es") or ""),
        it=str(extra.get("it") or ""),
        pl=str(extra.get("pl") or ""),
    )


def _labels(*, de: str, en: str, ar: str, **extra: str) -> dict:
    from .operator_i18n import labels

    return labels(
        de=de,
        en=en,
        ar=ar,
        tr=str(extra.get("tr") or ""),
        fr=str(extra.get("fr") or ""),
        es=str(extra.get("es") or ""),
        it=str(extra.get("it") or ""),
        pl=str(extra.get("pl") or ""),
    )


def _nav_deployment() -> dict[str, Any]:
    return {
        "id": "nav_deployment",
        "type": "navigate",
        "tab": "workers",
        "focus": "deployment",
        "url": "/admin-v2/index.html?tab=workers&einsatzplan=1",
        **_labels(
            de="Einsatzplan öffnen",
            en="Open deployment plan",
            ar="فتح خطة الانتشار",
            tr="Görev planını aç",
            fr="Ouvrir le plan de déploiement",
            es="Abrir plan de despliegue",
            it="Apri piano di impiego",
            pl="Otwórz plan wdrożenia",
        ),
    }


def _sensitive_docs_contracts_intent(question: str) -> str | None:
    q = (question or "").strip()
    if not q:
        return None
    if _OPEN_CONTRACTS.search(q) or re.search(r"vertrag|contracts?", q, re.I):
        return "contracts"
    if _OPEN_DOCS.search(q) or re.search(r"\bdocs?\b|dokument", q, re.I):
        return "docs"
    return None


def try_operator_task(
    db,
    company_id: str,
    question: str,
    *,
    role: str = "company-admin",
    lang: str = "de",
) -> dict[str, Any] | None:
    """Return answer + confirmable execute actions for admin operator requests."""
    q = (question or "").strip()
    if not q or not company_id:
        return None
    role = (role or "").strip().lower()
    lang = (lang or "de")[:2]

    # Pförtner: hard-block docs/contracts intents and notify owner.
    if role == "turnstile":
        surface = _sensitive_docs_contracts_intent(q)
        if surface:
            try:
                from flask import g, request

                from backend.app.platform.security.contracts_lock import notify_owner_sensitive_attempt

                notify_owner_sensitive_attempt(
                    db,
                    company_id,
                    actor=getattr(g, "current_user", None),
                    surface=surface,
                    action="ai_operator",
                    path=str(getattr(request, "path", "") or "/api/ai"),
                )
            except Exception:
                pass
            from .operator_i18n import pick

            return {
                "answer": pick(
                    lang,
                    de=(
                        "Dokumente und Verträge sind für die Pförtner-Rolle gesperrt. "
                        "Der Firmeninhaber wurde informiert."
                    ),
                    en=(
                        "Documents and contracts are blocked for the turnstile role. "
                        "The company owner was notified."
                    ),
                    ar="المستندات والعقود محظورة لدور البوابة. تم إبلاغ مالك الشركة.",
                ),
                "source": "sensitive_gate",
                "blocked": True,
                "ownerNotified": True,
                "suggestedActions": [],
            }
        return None

    if role not in {"company-admin", "superadmin", "admin"}:
        return None

    from .ui_pilot import try_ui_pilot_task

    pilot = try_ui_pilot_task(q, lang=lang, role=role)
    if pilot:
        return pilot

    if _PREPARE_PLAN.search(q) or (
        _STATUS_PLAN.search(q) and re.search(r"(vorbereiten|erstell|mach|prepare|جهز)", q, re.I)
    ):
        return _task_prepare_deployment(db, company_id, lang=lang)

    if _SEND_PLAN.search(q):
        return _task_send_deployment(db, company_id, lang=lang)

    if _STATUS_PLAN.search(q):
        return _task_status_deployment(db, company_id, lang=lang)

    notify_match = _NOTIFY.search(q)
    if notify_match:
        name = (notify_match.group(2) or notify_match.group(4) or "").strip(" .,!؟?")
        if name and len(name) >= 2:
            return _task_notify_worker(db, company_id, name, question=q, lang=lang)

    if _LEAVE_REJECT.search(q):
        return _task_leave_queue(db, company_id, lang=lang, mode="reject")

    if _LEAVE_APPROVE.search(q):
        return _task_leave_queue(db, company_id, lang=lang, mode="approve")

    if _LEAVE_LIST.search(q):
        return _task_leave_queue(db, company_id, lang=lang, mode="list")

    if _EXPIRED_DOCS.search(q):
        return _task_expired_docs(db, company_id, lang=lang)

    if _LATE.search(q) and re.search(r"(erinner|mahn|remind|push|nachricht|ذكّر|أرسل|list|zeig|wer)", q, re.I):
        return _task_late_workers(db, company_id, lang=lang)

    if _FRAUD.search(q):
        return _task_fraud(db, company_id, lang=lang)

    if _SECURITY.search(q) and re.search(
        r"(auflös|schließ|resolve|ack|bestätig|erledig|أغلق|حل)", q, re.I
    ):
        return _task_security_resolve(db, company_id, lang=lang)

    if _SECURITY.search(q):
        return _task_security_status(db, company_id, lang=lang)

    if _SYSTEM_ALERTS.search(q):
        return _task_system_alerts(db, company_id, lang=lang)

    if _BROADCAST.search(q):
        return _task_broadcast(db, company_id, question=q, lang=lang)

    if _INBOX.search(q):
        return _task_inbox(db, company_id, lang=lang)

    if _PRIORITIZE.search(q):
        return _task_prioritize(db, company_id, lang=lang)

    if _BRIEFING.search(q):
        return _task_daily_briefing(db, company_id, lang=lang)

    if _FORECAST.search(q) and re.search(r"(morgen|tomorrow|forecast|prognose|غدا|بكرة)", q, re.I):
        return _task_tomorrow_forecast(db, company_id, lang=lang)

    if _OUTSIDE_HOURS.search(q):
        return _task_outside_hours(db, company_id, lang=lang)

    if _RISK.search(q):
        return _task_risk(db, company_id, lang=lang)

    if _TIMELINE.search(q):
        return _task_access_timeline(db, company_id, lang=lang)

    if _PRESENCE.search(q):
        return _task_presence(db, company_id, lang=lang)

    if _OPEN_CONTRACTS.search(q) and re.search(r"(öffne|open|zeig|افتح|عرض)", q, re.I):
        return _task_navigate_page(
            lang,
            nav_key="contracts",
            tab="contracts",
            url="/admin-v2/contracts.html",
            intent="operator_open_contracts",
        )

    if _OPEN_DOCS.search(q) and re.search(r"(öffne|open|zeig|افتح|عرض)", q, re.I):
        return _task_navigate_page(
            lang,
            nav_key="docs",
            tab="docs",
            url="/admin-v2/docs.html",
            intent="operator_open_docs",
        )

    if _OPEN_CHAT.search(q) and re.search(r"(öffne|open|zeig|افتح)", q, re.I):
        return _task_navigate_page(
            lang,
            nav_key="chat",
            tab="chat",
            url="/admin-v2/chat.html",
            intent="operator_open_chat",
        )

    if _OPEN_WORKERS.search(q):
        return _task_navigate_page(
            lang,
            nav_key="workers",
            tab="workers",
            url="/admin-v2/index.html?tab=workers",
            intent="operator_open_workers",
        )

    if _OPEN_ACCESS.search(q):
        return _task_navigate_page(
            lang,
            nav_key="access",
            tab="access",
            url="/admin-v2/index.html?tab=access",
            intent="operator_open_access",
        )

    find_m = _FIND_WORKER.search(q)
    if find_m and not _ONSITE.search(q):
        name = (find_m.group(2) or "").strip(" .,!؟?")
        # Avoid matching generic words as names.
        blocked = {
            "heute", "morgen", "alle", "team", "vor", "ort", "site", "اليوم", "غدا",
            "verträge", "vertrage", "contracts", "dokumente", "docs", "chat",
            "arbeiter", "mitarbeiter", "workers", "anwesenheit", "zutritt",
            "العقود", "الوثائق", "الموظفين", "الحضور",
        }
        if name and len(name) >= 2 and name.lower() not in blocked:
            return _task_find_worker(db, company_id, name, lang=lang)

    if _ONSITE.search(q):
        return _task_onsite(db, company_id, lang=lang)

    # Late list without explicit "remind" verb → still show late workers.
    if _LATE.search(q):
        return _task_late_workers(db, company_id, lang=lang)

    return None


def _task_status_deployment(db, company_id: str, *, lang: str) -> dict[str, Any]:
    from .tools import tool_deployment_month_status

    status = tool_deployment_month_status(db, company_id, {})
    year = status.get("year")
    month = status.get("month")
    ready = status.get("workersReady") or 0
    total = status.get("workersTotal") or 0
    st = status.get("status") or "draft"
    conflicts = status.get("conflictsPreview") or []
    conflict_lines = "\n".join(
        f"• {c.get('name')}: {c.get('daysFilled')}/{c.get('daysInMonth')} Tage"
        + (f", {c.get('declinedDayCount')} Ablehnung(en)" if c.get("declinedDayCount") else "")
        for c in conflicts[:6]
    )
    answer = _lang_text(
        lang,
        f"Einsatzplan {month:02d}/{year}: Status **{st}**, {ready}/{total} bereit."
        + (f"\nKonflikte/Lücken:\n{conflict_lines}" if conflict_lines else "\nKeine groben Konflikte."),
        f"Deployment {month:02d}/{year}: status **{st}**, {ready}/{total} ready."
        + (f"\nConflicts:\n{conflict_lines}" if conflict_lines else "\nNo major conflicts."),
        f"خطة {month:02d}/{year}: الحالة **{st}**, {ready}/{total} جاهزون."
        + (f"\nتعارضات:\n{conflict_lines}" if conflict_lines else "\nلا تعارضات كبيرة."),
    )
    actions = [
        {
            "id": "prep_dep",
            "type": "execute",
            "action": "prepare_deployment_month",
            "risk": "high",
            "params": {"year": year, "month": month},
            "labelDe": "Entwurf vorbereiten (Bestätigung)",
            "labelEn": "Prepare draft (confirm)",
            "labelAr": "تجهيز المسودة (تأكيد)",
        },
        _nav_deployment(),
    ]
    if st != "sent" and ready > 0:
        actions.insert(
            1,
            {
                "id": "send_dep",
                "type": "execute",
                "action": "confirm_send_deployment_month",
                "risk": "critical",
                "params": {"year": year, "month": month, "lang": lang},
                "labelDe": "An Mitarbeiter senden (Bestätigung)",
                "labelEn": "Send to workers (confirm)",
                "labelAr": "إرسال للموظفين (تأكيد)",
            },
        )
    return {
        "answer": answer,
        "intent": "operator_deployment_status",
        "configured": True,
        "sources": ["get_deployment_month_status"],
        "toolsUsed": ["get_deployment_month_status"],
        "actions": actions,
        "suggestedActions": actions,
        "ok": True,
    }


def _task_prepare_deployment(db, company_id: str, *, lang: str) -> dict[str, Any]:
    from .tools import tool_deployment_month_status

    status = tool_deployment_month_status(db, company_id, {})
    year = int(status.get("year") or datetime.now(timezone.utc).year)
    month = int(status.get("month") or datetime.now(timezone.utc).month)
    ready = status.get("workersReady") or 0
    total = status.get("workersTotal") or 0
    answer = _lang_text(
        lang,
        f"Ich kann den Einsatzplan {month:02d}/{year} als **Entwurf** vorbereiten "
        f"(aktuell {ready}/{total} Pläne brauchbar). "
        f"Nach Ihrer Bestätigung wird nur gespeichert — kein Versand.",
        f"I can prepare deployment {month:02d}/{year} as a **draft** "
        f"({ready}/{total} plans usable). Confirm to save — no send yet.",
        f"يمكنني تجهيز خطة {month:02d}/{year} كـ **مسودة** "
        f"({ready}/{total} جاهزة). بعد التأكيد تُحفظ فقط — بدون إرسال.",
    )
    actions = [
        {
            "id": "prep_dep",
            "type": "execute",
            "action": "prepare_deployment_month",
            "risk": "high",
            "params": {},
            "labelDe": "Jetzt Entwurf vorbereiten",
            "labelEn": "Prepare draft now",
            "labelAr": "جهّز المسودة الآن",
        },
        _nav_deployment(),
    ]
    return {
        "answer": answer,
        "intent": "operator_prepare_deployment",
        "configured": True,
        "sources": ["get_deployment_month_status"],
        "toolsUsed": ["get_deployment_month_status"],
        "actions": actions,
        "suggestedActions": actions,
        "ok": True,
    }


def _task_send_deployment(db, company_id: str, *, lang: str) -> dict[str, Any]:
    from .tools import tool_deployment_month_status

    status = tool_deployment_month_status(db, company_id, {})
    year = int(status.get("year") or datetime.now(timezone.utc).year)
    month = int(status.get("month") or datetime.now(timezone.utc).month)
    ready = status.get("workersReady") or 0
    total = status.get("workersTotal") or 0
    answer = _lang_text(
        lang,
        f"Versand Einsatzplan {month:02d}/{year}: {ready}/{total} bereit. "
        f"**Nur nach Ihrer Bestätigung** werden PDF/Push/E-Mail an Mitarbeiter gesendet.",
        f"Send deployment {month:02d}/{year}: {ready}/{total} ready. "
        f"**Only after your confirmation** PDF/push/email go out.",
        f"إرسال خطة {month:02d}/{year}: {ready}/{total} جاهزون. "
        f"**فقط بعد تأكيدك** يُرسل PDF/إشعار/بريد.",
    )
    actions = [
        {
            "id": "send_dep",
            "type": "execute",
            "action": "confirm_send_deployment_month",
            "risk": "critical",
            "params": {"year": year, "month": month, "lang": lang},
            "labelDe": "Jetzt an alle Bereiten senden",
            "labelEn": "Send to all ready workers now",
            "labelAr": "أرسل الآن للجاهزين",
        },
        _nav_deployment(),
    ]
    return {
        "answer": answer,
        "intent": "operator_send_deployment",
        "configured": True,
        "sources": ["get_deployment_month_status"],
        "toolsUsed": ["get_deployment_month_status"],
        "actions": actions,
        "suggestedActions": actions,
        "ok": True,
    }


def _task_notify_worker(
    db,
    company_id: str,
    name: str,
    *,
    question: str,
    lang: str,
) -> dict[str, Any]:
    from .tools import tool_search_workers

    found = tool_search_workers(db, company_id, {"query": name})
    workers = found.get("workers") or found.get("items") or []
    if not workers and isinstance(found.get("results"), list):
        workers = found["results"]
    # normalize shapes from tool_search_workers
    if not workers and "error" not in found:
        # tool returns list under different key — inspect tool
        for key in ("matches", "rows", "data"):
            if isinstance(found.get(key), list):
                workers = found[key]
                break

    if not workers:
        # raw SQL fallback
        rows = db.execute(
            """
            SELECT id, first_name, last_name FROM workers
            WHERE company_id = ? AND deleted_at IS NULL
              AND (first_name LIKE ? OR last_name LIKE ? OR (first_name || ' ' || last_name) LIKE ?)
            LIMIT 5
            """,
            (company_id, f"%{name}%", f"%{name}%", f"%{name}%"),
        ).fetchall()
        workers = [dict(r) for r in rows]

    if not workers:
        return {
            "answer": _lang_text(
                lang,
                f"Keinen Mitarbeiter zu „{name}“ gefunden.",
                f"No worker matching “{name}”.",
                f"لم أجد موظفاً باسم «{name}».",
                tr=f"“{name}” ile eşleşen çalışan bulunamadı.",
                fr=f"Aucun collaborateur correspondant à « {name} ».",
                es=f"No hay trabajador que coincida con “{name}”.",
                it=f"Nessun lavoratore corrispondente a “{name}”.",
                pl=f"Nie znaleziono pracownika „{name}”.",
            ),
            "intent": "operator_notify_miss",
            "configured": True,
            "sources": ["search_workers"],
            "toolsUsed": ["search_workers"],
            "actions": [],
            "suggestedActions": [],
            "ok": True,
        }

    w = workers[0]
    wid = str(w.get("id") or w.get("workerId") or "")
    wname = f"{w.get('first_name', '')} {w.get('last_name', '')}".strip() or name
    # Extract message body after name if present
    body = question
    for token in (name, "schreib", "nachricht", "push", "an ", "message", "notify", "أرسل", "رسالة"):
        body = re.sub(re.escape(token), " ", body, flags=re.I)
    body = re.sub(r"\s+", " ", body).strip(" :,-") or _lang_text(
        lang,
        "Kurzer Hinweis von der Betriebsleitung.",
        "Short note from operations.",
        "ملاحظة قصيرة من الإدارة.",
    )
    body = body[:400]
    answer = _lang_text(
        lang,
        f"Nachricht an **{wname}** vorbereitet. Nach Bestätigung geht ein Push an den Mitarbeiter.",
        f"Message to **{wname}** ready. Confirm to send a push.",
        f"رسالة إلى **{wname}** جاهزة. أكّد لإرسال إشعار.",
    )
    actions = [
        {
            "id": "notify_w",
            "type": "execute",
            "action": "notify_worker",
            "risk": "medium",
            "params": {
                "worker_id": wid,
                "title": "SUPPIX",
                "body": body,
                "tag": "ai-operator",
            },
            "labelDe": f"Push an {wname} senden",
            "labelEn": f"Send push to {wname}",
            "labelAr": f"إرسال إشعار إلى {wname}",
        },
        {
            "id": "nav_workers",
            "type": "navigate",
            "tab": "workers",
            "url": "/admin-v2/index.html?tab=workers",
            "labelDe": "Mitarbeiter öffnen",
            "labelEn": "Open workers",
            "labelAr": "فتح الموظفين",
        },
    ]
    return {
        "answer": answer,
        "intent": "operator_notify_worker",
        "configured": True,
        "sources": ["search_workers"],
        "toolsUsed": ["search_workers"],
        "actions": actions,
        "suggestedActions": actions,
        "ok": True,
    }


def _task_leave_queue(db, company_id: str, *, lang: str, mode: str = "list", approve: bool | None = None) -> dict[str, Any]:
    # Backward-compatible: approve=True/False still accepted by older callers/tests.
    if approve is True:
        mode = "approve"
    elif approve is False and mode == "list":
        mode = "list"
    mode = (mode or "list").lower()
    if mode not in {"list", "approve", "reject"}:
        mode = "list"

    rows = db.execute(
        """
        SELECT id, worker_id, start_date, end_date, type, status
        FROM leave_requests
        WHERE company_id = ? AND status = 'ausstehend'
        ORDER BY start_date ASC
        LIMIT 8
        """,
        (company_id,),
    ).fetchall()
    if not rows:
        return {
            "answer": _lang_text(
                lang,
                "Keine offenen Urlaubsanträge.",
                "No pending leave requests.",
                "لا طلبات إجازة معلّقة.",
                tr="Bekleyen izin talebi yok.",
                fr="Aucune demande de congé en attente.",
                es="No hay solicitudes de ausencia pendientes.",
                it="Nessuna richiesta di ferie in sospeso.",
                pl="Brak oczekujących wniosków urlopowych.",
            ),
            "intent": "operator_leave_empty",
            "configured": True,
            "sources": ["leave_requests"],
            "actions": [
                {
                    "id": "nav_inbox",
                    "type": "navigate",
                    "tab": "inbox",
                    "url": "/admin-v2/index.html?tab=inbox",
                    **_labels(
                        de="Inbox öffnen",
                        en="Open inbox",
                        ar="فتح الوارد",
                        tr="Gelen kutusunu aç",
                        fr="Ouvrir la boîte de réception",
                        es="Abrir bandeja de entrada",
                        it="Apri inbox",
                        pl="Otwórz skrzynkę",
                    ),
                }
            ],
            "suggestedActions": [],
            "ok": True,
        }

    lines = []
    actions: list[dict[str, Any]] = []
    for row in rows:
        lid = str(row["id"])
        wid = str(row["worker_id"])
        w = db.execute(
            "SELECT first_name, last_name FROM workers WHERE id = ? AND company_id = ?",
            (wid, company_id),
        ).fetchone()
        wname = f"{w['first_name']} {w['last_name']}".strip() if w else wid
        lines.append(f"• {wname}: {row['start_date']} → {row['end_date']} ({row['type'] or 'Urlaub'})")
        if mode == "approve":
            actions.append(
                {
                    "id": f"approve_{lid}",
                    "type": "execute",
                    "action": "approve_leave_request",
                    "risk": "medium",
                    "params": {"leave_id": lid},
                    "labelDe": f"Genehmigen: {wname}",
                    "labelEn": f"Approve: {wname}",
                    "labelAr": f"موافقة: {wname}",
                }
            )
        elif mode == "reject":
            actions.append(
                {
                    "id": f"reject_{lid}",
                    "type": "execute",
                    "action": "reject_leave_request",
                    "risk": "medium",
                    "params": {"leave_id": lid},
                    "labelDe": f"Ablehnen: {wname}",
                    "labelEn": f"Reject: {wname}",
                    "labelAr": f"رفض: {wname}",
                }
            )
    if mode == "approve":
        footer = _lang_text(
            lang,
            "\n\nBestätigen Sie eine Genehmigung unten.",
            "\n\nConfirm an approval below.",
            "\n\nأكد الموافقة أدناه.",
        )
    elif mode == "reject":
        footer = _lang_text(
            lang,
            "\n\nBestätigen Sie eine Ablehnung unten.",
            "\n\nConfirm a rejection below.",
            "\n\nأكد الرفض أدناه.",
        )
    else:
        footer = _lang_text(
            lang,
            "\n\nInbox öffnen oder Genehmigung/Ablehnung anfordern.",
            "\n\nOpen inbox or ask to approve/reject.",
            "\n\nافتح الوارد أو اطلب الموافقة/الرفض.",
        )
    answer = _lang_text(
        lang,
        "Offene Urlaubsanträge:\n" + "\n".join(lines) + footer,
        "Pending leave:\n" + "\n".join(lines) + footer,
        "طلبات معلّقة:\n" + "\n".join(lines) + footer,
    )
    actions.append(
        {
            "id": "nav_inbox",
            "type": "navigate",
            "tab": "inbox",
            "url": "/admin-v2/index.html?tab=inbox",
            "labelDe": "Inbox öffnen",
            "labelEn": "Open inbox",
            "labelAr": "فتح الوارد",
        }
    )
    return {
        "answer": answer,
        "intent": "operator_leave_queue",
        "configured": True,
        "sources": ["leave_requests"],
        "actions": actions,
        "suggestedActions": actions,
        "ok": True,
    }


def _task_onsite(db, company_id: str, *, lang: str) -> dict[str, Any]:
    from .tools import tool_get_on_site_workers

    data = tool_get_on_site_workers(db, company_id, {})
    workers = data.get("workers") or data.get("onSite") or data.get("items") or []
    if not workers and isinstance(data.get("names"), list):
        workers = data["names"]
    count = data.get("count")
    if count is None:
        count = len(workers) if isinstance(workers, list) else 0
    lines = []
    if isinstance(workers, list):
        for w in workers[:12]:
            if isinstance(w, dict):
                lines.append(
                    f"• {w.get('name') or ((w.get('first_name') or '') + ' ' + (w.get('last_name') or '')).strip() or w.get('id')}"
                )
            else:
                lines.append(f"• {w}")
    empty = _lang_text(
        lang,
        "Niemand eingecheckt.",
        "Nobody checked in.",
        "لا أحد مسجّل حضور.",
        tr="Kimse giriş yapmamış.",
        fr="Personne n'est pointé.",
        es="Nadie ha fichado.",
        it="Nessuno ha fatto check-in.",
        pl="Nikt nie jest zameldowany.",
    )
    body = "\n".join(lines) if lines else empty
    from .sector_copy import apply_sector_text, load_company_sector_terms, sector_vocab

    terms = load_company_sector_terms(db, company_id, lang=lang)
    _workers, site, _gate = sector_vocab(terms, lang)
    answer = _lang_text(
        lang,
        f"**{count}** aktuell am {site}.\n{body}",
        f"**{count}** currently at {site}.\n{body}",
        f"**{count}** حالياً في {site}.\n{body}",
        tr=f"**{count}** şu an {site}.\n{body}",
        fr=f"**{count}** actuellement sur {site}.\n{body}",
        es=f"**{count}** actualmente en {site}.\n{body}",
        it=f"**{count}** attualmente in {site}.\n{body}",
        pl=f"**{count}** obecnie na {site}.\n{body}",
    )
    answer = apply_sector_text(answer, workers=_workers, site=site, lang=lang)
    return {
        "answer": answer,
        "intent": "operator_onsite",
        "configured": True,
        "sources": ["get_on_site_workers"],
        "toolsUsed": ["get_on_site_workers"],
        "actions": [
            {
                "id": "nav_access",
                "type": "navigate",
                "tab": "access",
                "url": "/admin-v2/index.html?tab=access",
                **_labels(
                    de="Anwesenheit öffnen",
                    en="Open attendance",
                    ar="فتح الحضور",
                    tr="Yoklamayı aç",
                    fr="Ouvrir la présence",
                    es="Abrir asistencia",
                    it="Apri presenza",
                    pl="Otwórz obecność",
                ),
            }
        ],
        "suggestedActions": [],
        "ok": True,
    }


def _task_expired_docs(db, company_id: str, *, lang: str) -> dict[str, Any]:
    from .tools import tool_expired_documents

    data = tool_expired_documents(db, company_id, {"limit": 20})
    rows = data.get("expired") or []
    count = int(data.get("count") or len(rows))
    lines = [
        f"• {(r.get('first_name') or '')} {(r.get('last_name') or '')}: "
        f"{r.get('doc_type')} ({r.get('expiry_date')})"
        for r in rows[:8]
    ]
    answer = _lang_text(
        lang,
        f"**{count}** abgelaufene Dokumente.\n" + ("\n".join(lines) if lines else "Keine Treffer.")
        + "\n\nNach Bestätigung sende ich Erinnerungs-Push an die betroffenen Mitarbeiter.",
        f"**{count}** expired documents.\n" + ("\n".join(lines) if lines else "None.")
        + "\n\nConfirm to send reminder pushes.",
        f"**{count}** وثائق منتهية.\n" + ("\n".join(lines) if lines else "لا يوجد.")
        + "\n\nأكّد لإرسال تذكير Push.",
    )
    actions = [
        {
            "id": "remind_docs",
            "type": "execute",
            "action": "remind_expired_documents",
            "risk": "medium",
            "params": {"limit": 25},
            "labelDe": "Erinnerungen jetzt senden",
            "labelEn": "Send reminders now",
            "labelAr": "أرسل التذكيرات الآن",
        },
        {
            "id": "nav_workers",
            "type": "navigate",
            "tab": "workers",
            "url": "/admin-v2/index.html?tab=workers",
            "labelDe": "Mitarbeiter öffnen",
            "labelEn": "Open workers",
            "labelAr": "فتح الموظفين",
        },
    ]
    return {
        "answer": answer,
        "intent": "operator_expired_docs",
        "configured": True,
        "sources": ["get_expired_documents"],
        "toolsUsed": ["get_expired_documents"],
        "actions": actions,
        "suggestedActions": actions,
        "ok": True,
    }


def _task_late_workers(db, company_id: str, *, lang: str) -> dict[str, Any]:
    from .tools import tool_repeated_late_workers

    data = tool_repeated_late_workers(db, company_id, {"limit": 12})
    workers = data.get("workers") or []
    lines = []
    for w in workers[:8]:
        name = w.get("name") or w.get("workerId") or w.get("id")
        streak = w.get("streak") or w.get("lateStreak") or "?"
        lines.append(f"• {name} — Streak {streak}")
    answer = _lang_text(
        lang,
        f"**{len(workers)}** Mitarbeiter mit Verspätungs-Streak.\n"
        + ("\n".join(lines) if lines else "Keine.")
        + "\n\nBestätigen → Push-Erinnerung an diese Personen.",
        f"**{len(workers)}** workers with late streaks.\n"
        + ("\n".join(lines) if lines else "None.")
        + "\n\nConfirm → push reminders.",
        f"**{len(workers)}** موظفون بتأخير متكرر.\n"
        + ("\n".join(lines) if lines else "لا أحد.")
        + "\n\nأكّد → إرسال تذكير.",
    )
    actions = [
        {
            "id": "remind_late",
            "type": "execute",
            "action": "remind_late_workers",
            "risk": "medium",
            "params": {"limit": 15},
            "labelDe": "Verspätete erinnern",
            "labelEn": "Remind late workers",
            "labelAr": "تذكير المتأخرين",
        },
        {
            "id": "nav_access",
            "type": "navigate",
            "tab": "access",
            "url": "/admin-v2/index.html?tab=access",
            "labelDe": "Anwesenheit öffnen",
            "labelEn": "Open attendance",
            "labelAr": "فتح الحضور",
        },
    ]
    return {
        "answer": answer,
        "intent": "operator_late_workers",
        "configured": True,
        "sources": ["get_repeated_late_workers"],
        "toolsUsed": ["get_repeated_late_workers"],
        "actions": actions,
        "suggestedActions": actions if workers else [actions[1]],
        "ok": True,
    }


def _task_security_status(db, company_id: str, *, lang: str) -> dict[str, Any]:
    from .tools import tool_security_summary

    data = tool_security_summary(db, company_id, {})
    findings = data.get("findings") or []
    alerts = data.get("openAlerts") or []
    answer = _lang_text(
        lang,
        f"Security: {data.get('newFindings', 0)} neue Befunde, {len(alerts)} offene Alerts.\n"
        + "\n".join(f"• {f.get('type') or f.get('message') or f}" for f in findings[:5]),
        f"Security: {data.get('newFindings', 0)} new findings, {len(alerts)} open alerts.",
        f"الأمن: {data.get('newFindings', 0)} نتائج، {len(alerts)} تنبيهات مفتوحة.",
    )
    actions = [
        {
            "id": "resolve_sec",
            "type": "execute",
            "action": "resolve_open_security_alerts",
            "risk": "high",
            "params": {"limit": 15},
            "labelDe": "Offene Security-Alerts auflösen",
            "labelEn": "Resolve open security alerts",
            "labelAr": "إغلاق تنبيهات الأمن",
        },
        {
            "id": "nav_ops",
            "type": "navigate",
            "url": "/ops-command-center.html",
            "labelDe": "Ops Center öffnen",
            "labelEn": "Open ops center",
            "labelAr": "فتح مركز العمليات",
        },
    ]
    return {
        "answer": answer,
        "intent": "operator_security_status",
        "configured": True,
        "sources": ["get_security_summary"],
        "toolsUsed": ["get_security_summary"],
        "actions": actions,
        "suggestedActions": actions,
        "ok": True,
    }


def _task_security_resolve(db, company_id: str, *, lang: str) -> dict[str, Any]:
    base = _task_security_status(db, company_id, lang=lang)
    base["intent"] = "operator_security_resolve"
    base["answer"] = _lang_text(
        lang,
        "Ich kann offene Security-Alerts als erledigt markieren — nur nach Ihrer Bestätigung.",
        "I can mark open security alerts resolved — only after your confirmation.",
        "يمكنني إغلاق تنبيهات الأمن — فقط بعد تأكيدك.",
    ) + "\n\n" + str(base.get("answer") or "")
    return base


def _task_system_alerts(db, company_id: str, *, lang: str) -> dict[str, Any]:
    try:
        rows = db.execute(
            """
            SELECT id, code, message, created_at FROM system_alerts
            WHERE resolved_at IS NULL
            ORDER BY created_at DESC LIMIT 10
            """
        ).fetchall()
    except Exception:
        rows = []
    lines = [f"• {r['code']}: {(r['message'] or '')[:80]}" for r in rows]
    answer = _lang_text(
        lang,
        f"**{len(rows)}** offene System-Hinweise.\n" + ("\n".join(lines) if lines else "Keine."),
        f"**{len(rows)}** open system alerts.\n" + ("\n".join(lines) if lines else "None."),
        f"**{len(rows)}** تنبيهات نظام مفتوحة.\n" + ("\n".join(lines) if lines else "لا شيء."),
    )
    actions = [
        {
            "id": "ack_sys",
            "type": "execute",
            "action": "ack_open_system_alerts",
            "risk": "medium",
            "params": {"limit": 20},
            "labelDe": "System-Hinweise schließen",
            "labelEn": "Ack system alerts",
            "labelAr": "إغلاق تنبيهات النظام",
        }
    ]
    return {
        "answer": answer,
        "intent": "operator_system_alerts",
        "configured": True,
        "sources": ["system_alerts"],
        "actions": actions,
        "suggestedActions": actions if rows else [],
        "ok": True,
    }


def _task_broadcast(db, company_id: str, *, question: str, lang: str) -> dict[str, Any]:
    body = question
    for token in (
        "an alle",
        "broadcast",
        "rundnachricht",
        "teamnachricht",
        "alle mitarbeiter",
        "mitteilung",
        "رسالة للجميع",
        "إلى الجميع",
    ):
        body = re.sub(re.escape(token), " ", body, flags=re.I)
    body = re.sub(r"\s+", " ", body).strip(" :,-") or _lang_text(
        lang,
        "Wichtige Mitteilung der Betriebsleitung.",
        "Important note from operations.",
        "رسالة مهمة من الإدارة.",
    )
    onsite = bool(re.search(r"(vor ort|on ?site|baustelle|في الموقع)", question, re.I))
    scope = "onsite" if onsite else "active"
    scope_label = _lang_text(
        lang,
        "nur Vor-Ort" if onsite else "alle aktiven Mitarbeiter",
        "on-site only" if onsite else "all active workers",
        "في الموقع فقط" if onsite else "كل الموظفين النشطين",
    )
    answer = _lang_text(
        lang,
        f"Broadcast an **{scope_label}** vorbereitet:\n„{body[:200]}“\nNur nach Bestätigung.",
        f"Broadcast to **{scope_label}** ready:\n“{body[:200]}”\nConfirm to send.",
        f"بث إلى **{scope_label}**:\n«{body[:200]}»\nيحتاج تأكيدك.",
    )
    actions = [
        {
            "id": "broadcast",
            "type": "execute",
            "action": "broadcast_worker_message",
            "risk": "critical",
            "params": {"title": "Betriebsmitteilung", "body": body[:500], "scope": scope},
            "labelDe": "Jetzt an Team senden",
            "labelEn": "Send to team now",
            "labelAr": "أرسل للفريق الآن",
        }
    ]
    return {
        "answer": answer,
        "intent": "operator_broadcast",
        "configured": True,
        "sources": ["operator"],
        "actions": actions,
        "suggestedActions": actions,
        "ok": True,
    }


def _task_prioritize(db, company_id: str, *, lang: str) -> dict[str, Any]:
    from .operator_pulse import build_operator_pulse

    pulse = build_operator_pulse(db, company_id, lang=lang)
    recs = pulse.get("recommendations") or []
    lines = []
    for i, rec in enumerate(recs[:5], 1):
        label = str(rec.get("label") or rec.get("prompt") or "").strip()
        reason = str(rec.get("reason") or "").strip()
        if label:
            lines.append(f"{i}. **{label}** — {reason}" if reason else f"{i}. **{label}**")
    answer = _lang_text(
        lang,
        "Prioritäten heute:\n" + ("\n".join(lines) if lines else "Keine kritischen Punkte — Tageslage prüfen."),
        "Priorities today:\n" + ("\n".join(lines) if lines else "Nothing critical — check the daily briefing."),
        "أولويات اليوم:\n" + ("\n".join(lines) if lines else "لا نقاط حرجة — راجع ملخص اليوم."),
    )
    actions = []
    for rec in recs[:5]:
        if rec.get("type") == "execute" and rec.get("action"):
            actions.append(
                {
                    "id": f"pulse_{rec.get('id')}",
                    "type": "execute",
                    "action": rec["action"],
                    "params": rec.get("params") or {},
                    "risk": "medium",
                    "labelDe": rec.get("label"),
                    "labelEn": rec.get("label"),
                    "labelAr": rec.get("label"),
                    "labels": {lang: rec.get("label")},
                }
            )
        elif rec.get("prompt"):
            actions.append(
                {
                    "id": f"pulse_prompt_{rec.get('id')}",
                    "type": "prompt",
                    "prompt": rec.get("prompt"),
                    "labelDe": rec.get("label"),
                    "labelEn": rec.get("label"),
                    "labelAr": rec.get("label"),
                    "labels": {lang: rec.get("label")},
                }
            )
    return {
        "answer": answer,
        "intent": "operator_prioritize",
        "configured": True,
        "sources": ["operator_pulse"],
        "toolsUsed": ["operator_pulse"],
        "actions": actions,
        "suggestedActions": actions,
        "urgency": pulse.get("urgency"),
        "ok": True,
    }


def _task_inbox(db, company_id: str, *, lang: str) -> dict[str, Any]:
    from .tools import tool_browse_inbox

    data = tool_browse_inbox(db, company_id, {"limit": 12})
    items = data.get("items") or []
    pretty = []
    for it in items[:8]:
        if isinstance(it, dict):
            pretty.append(f"• {it.get('title') or it.get('summary') or it.get('id')}")
        else:
            pretty.append(f"• {it}")
    answer = _lang_text(
        lang,
        f"Inbox: **{len(items)}** Einträge.\n" + ("\n".join(pretty) if pretty else "Leer."),
        f"Inbox: **{len(items)}** items.\n" + ("\n".join(pretty) if pretty else "Empty."),
        f"الوارد: **{len(items)}**.\n" + ("\n".join(pretty) if pretty else "فارغ."),
    )
    actions = [
        {
            "id": "nav_inbox",
            "type": "navigate",
            "tab": "inbox",
            "url": "/admin-v2/index.html?tab=inbox",
            "labelDe": "Inbox öffnen",
            "labelEn": "Open inbox",
            "labelAr": "فتح الوارد",
        },
        {
            "id": "remind_docs",
            "type": "execute",
            "action": "remind_expired_documents",
            "risk": "medium",
            "params": {"limit": 25},
            "labelDe": "Dokument-Erinnerungen senden",
            "labelEn": "Send document reminders",
            "labelAr": "تذكير الوثائق",
        },
    ]
    return {
        "answer": answer,
        "intent": "operator_inbox",
        "configured": True,
        "sources": ["browse_inbox"],
        "toolsUsed": ["browse_inbox"],
        "actions": actions,
        "suggestedActions": actions,
        "ok": True,
    }


def _task_navigate_page(
    lang: str,
    *,
    tab: str,
    url: str,
    intent: str,
    nav_key: str,
) -> dict[str, Any]:
    from .operator_i18n import nav_answer, nav_labels

    action = {
        "id": f"nav_{tab or 'page'}",
        "type": "navigate",
        "tab": tab,
        "url": url,
        **nav_labels(nav_key),
    }
    actions = [action]
    return {
        "answer": nav_answer(lang, nav_key),
        "intent": intent,
        "configured": True,
        "sources": ["operator_navigate"],
        "toolsUsed": [],
        "actions": actions,
        "suggestedActions": actions,
        "ok": True,
    }


def _task_daily_briefing(db, company_id: str, *, lang: str) -> dict[str, Any]:
    from .tools import (
        tool_browse_inbox,
        tool_operational_insights,
        tool_presence_summary,
        tool_security_summary,
    )

    presence = tool_presence_summary(db, company_id, {})
    insights = tool_operational_insights(db, company_id, {})
    security = tool_security_summary(db, company_id, {})
    inbox = tool_browse_inbox(db, company_id, {"limit": 8})
    att: dict[str, Any] = {}
    chat: dict[str, Any] = {}
    hr: dict[str, Any] = {}
    sec_brief: dict[str, Any] = {}
    try:
        from backend.app.platform.physical_operations.daily_brief import build_daily_ops_brief

        daily = build_daily_ops_brief(db, company_id) or {}
        att = daily.get("attendance") or {}
        chat = daily.get("chat") or {}
        hr = daily.get("hr") or {}
        sec_brief = daily.get("security") or {}
    except Exception:
        pass

    on_site = int(att.get("onSite") or presence.get("onSiteCount") or 0)
    by_site = presence.get("bySite") or []
    site_line = ", ".join(f"{s.get('site')}: {s.get('count')}" for s in by_site[:4])
    open_alerts = int(sec_brief.get("totalOpen") or len(security.get("openAlerts") or []))
    inbox_n = int(inbox.get("count") or len(inbox.get("items") or []))
    missing_n = int(att.get("missingExpected") or 0)
    late_n = int(att.get("lateToday") or 0)
    chat_n = int(chat.get("totalOpen") or 0)
    hr_n = int(hr.get("totalOpen") or 0)
    leave_n = int(hr.get("pendingLeave") or 0)
    docs_n = int(hr.get("expiringDocuments") or 0)
    review_n = int(hr.get("inReviewDocuments") or 0)
    issues = insights.get("topIssues") or insights.get("issues") or insights.get("priorities") or []
    if isinstance(issues, dict):
        issues = list(issues.values())
    issue_lines = []
    if isinstance(issues, list):
        for it in issues[:4]:
            if isinstance(it, dict):
                issue_lines.append(f"• {it.get('title') or it.get('summary') or it.get('message') or it}")
            else:
                issue_lines.append(f"• {it}")

    brief_extra_de = (
        f"• Fehlt/spät: **{missing_n}** / **{late_n}**\n"
        f"• Chat/Anrufe: **{chat_n}** · HR: **{hr_n}** "
        f"(Urlaub {leave_n}, Docs {docs_n}, Prüfung {review_n})\n"
    )
    brief_extra_en = (
        f"• Missing/late: **{missing_n}** / **{late_n}**\n"
        f"• Chat/calls: **{chat_n}** · HR: **{hr_n}** "
        f"(leave {leave_n}, docs {docs_n}, review {review_n})\n"
    )
    tail_de = (("Schwerpunkte:\n" + "\n".join(issue_lines)) if issue_lines else "Keine kritischen Schwerpunkte gemeldet.")
    tail_en = (("Priorities:\n" + "\n".join(issue_lines)) if issue_lines else "No critical priorities reported.")
    sites = f" ({site_line})" if site_line else ""
    answer = _lang_text(
        lang,
        f"**Tageslage**\n• Vor Ort: **{on_site}**{sites}\n• Inbox: **{inbox_n}** · Security offen: **{open_alerts}**\n{brief_extra_de}{tail_de}",
        f"**Daily briefing**\n• On site: **{on_site}**{sites}\n• Inbox: **{inbox_n}** · Open security: **{open_alerts}**\n{brief_extra_en}{tail_en}",
        f"**ملخص اليوم**\n• في الموقع: **{on_site}**{sites}\n• الوارد: **{inbox_n}** · تنبيهات أمن مفتوحة: **{open_alerts}**\n"
        + f"• غائب/متأخر: **{missing_n}** / **{late_n}**\n"
        + f"• دردشة/مكالمات: **{chat_n}** · موارد بشرية: **{hr_n}**\n"
        + (("أولويات:\n" + "\n".join(issue_lines)) if issue_lines else "لا أولويات حرجة."),
        tr=f"**Günlük özet**\n• Sahada: **{on_site}**{sites}\n• Gelen kutusu: **{inbox_n}** · Açık güvenlik: **{open_alerts}**\n{brief_extra_en}{tail_en}",
        fr=f"**Briefing du jour**\n• Sur site: **{on_site}**{sites}\n• Inbox: **{inbox_n}** · Alertes sécurité: **{open_alerts}**\n{brief_extra_en}{tail_en}",
        es=f"**Resumen del día**\n• En obra: **{on_site}**{sites}\n• Bandeja: **{inbox_n}** · Alertas de seguridad: **{open_alerts}**\n{brief_extra_en}{tail_en}",
        it=f"**Briefing odierno**\n• In cantiere: **{on_site}**{sites}\n• Inbox: **{inbox_n}** · Avvisi sicurezza: **{open_alerts}**\n{brief_extra_en}{tail_en}",
        pl=f"**Podsumowanie dnia**\n• Na budowie: **{on_site}**{sites}\n• Skrzynka: **{inbox_n}** · Alerty bezpieczeństwa: **{open_alerts}**\n{brief_extra_en}{tail_en}",
    )
    actions = [
        {
            "id": "export_brief",
            "type": "execute",
            "action": "export_briefing_markdown",
            "risk": "low",
            "params": {},
            "labelDe": "Briefing als Markdown exportieren",
            "labelEn": "Export briefing markdown",
            "labelAr": "تصدير الملخص Markdown",
        },
        {
            "id": "send_brief",
            "type": "execute",
            "action": "send_briefing_email",
            "risk": "medium",
            "params": {},
            "labelDe": "Briefing per E-Mail senden",
            "labelEn": "Email briefing",
            "labelAr": "إرسال الملخص بالبريد",
        },
        {
            "id": "nav_ops",
            "type": "navigate",
            "url": "/ops-command-center.html",
            "labelDe": "Ops Center öffnen",
            "labelEn": "Open ops center",
            "labelAr": "فتح مركز العمليات",
        },
    ]
    return {
        "answer": answer,
        "intent": "operator_daily_briefing",
        "configured": True,
        "sources": [
            "get_presence_summary",
            "get_operational_insights",
            "get_security_summary",
            "browse_inbox",
            "daily_ops_brief",
        ],
        "toolsUsed": [
            "get_presence_summary",
            "get_operational_insights",
            "get_security_summary",
            "browse_inbox",
            "daily_ops_brief",
        ],
        "actions": actions,
        "suggestedActions": actions,
        "ok": True,
    }


def _task_find_worker(db, company_id: str, name: str, *, lang: str) -> dict[str, Any]:
    from .tools import tool_search_workers, tool_worker_profile

    found = tool_search_workers(db, company_id, {"query": name})
    workers = found.get("workers") or []
    if not workers:
        return {
            "answer": _lang_text(
                lang,
                f"Keinen Mitarbeiter zu „{name}“ gefunden.",
                f"No worker matching “{name}”.",
                f"لم أجد موظفاً باسم «{name}».",
                tr=f"“{name}” ile eşleşen çalışan bulunamadı.",
                fr=f"Aucun collaborateur correspondant à « {name} ».",
                es=f"No hay trabajador que coincida con “{name}”.",
                it=f"Nessun lavoratore corrispondente a “{name}”.",
                pl=f"Nie znaleziono pracownika „{name}”.",
            ),
            "intent": "operator_find_worker_miss",
            "configured": True,
            "sources": ["search_workers"],
            "toolsUsed": ["search_workers"],
            "actions": [],
            "suggestedActions": [],
            "ok": True,
        }

    w0 = workers[0]
    wid = str(w0.get("id") or "")
    wname = f"{(w0.get('first_name') or '')} {(w0.get('last_name') or '')}".strip() or name
    profile = tool_worker_profile(db, company_id, {"worker_id": wid}) if wid else {}
    worker = profile.get("worker") or w0
    docs = profile.get("documents") or []
    recent = profile.get("recentAccess") or []
    last = recent[0] if recent else None
    last_line = ""
    if isinstance(last, dict):
        last_line = f"{last.get('timestamp') or ''} {last.get('direction') or ''} @ {last.get('gate') or '—'}"
    expired_n = sum(
        1
        for d in docs
        if (d.get("expiry_date") or "") and str(d.get("expiry_date")) < datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )
    more = ""
    if len(workers) > 1:
        more = _lang_text(
            lang,
            f"\n(+{len(workers) - 1} weitere Treffer)",
            f"\n(+{len(workers) - 1} more matches)",
            f"\n(+{len(workers) - 1} نتائج أخرى)",
        )
    answer = _lang_text(
        lang,
        f"**{wname}** · Status `{worker.get('status') or '—'}` · Standort `{worker.get('site') or '—'}`\n"
        f"Badge: `{worker.get('badge_id') or '—'}` · Abgelaufene Docs: **{expired_n}**\n"
        + (f"Letzter Zutritt: {last_line}" if last_line else "Kein Zutritt heute geladen.")
        + more,
        f"**{wname}** · status `{worker.get('status') or '—'}` · site `{worker.get('site') or '—'}`\n"
        f"Badge: `{worker.get('badge_id') or '—'}` · expired docs: **{expired_n}**\n"
        + (f"Last access: {last_line}" if last_line else "No recent access loaded.")
        + more,
        f"**{wname}** · الحالة `{worker.get('status') or '—'}` · الموقع `{worker.get('site') or '—'}`\n"
        f"Badge: `{worker.get('badge_id') or '—'}` · وثائق منتهية: **{expired_n}**\n"
        + (f"آخر دخول: {last_line}" if last_line else "لا سجل دخول حديث.")
        + more,
    )
    actions = [
        {
            "id": "nav_worker",
            "type": "navigate",
            "tab": "workers",
            "url": f"/admin-v2/index.html?tab=workers&worker={wid}",
            "labelDe": f"Profil {wname} öffnen",
            "labelEn": f"Open {wname}",
            "labelAr": f"فتح ملف {wname}",
        },
        {
            "id": "notify_w",
            "type": "execute",
            "action": "notify_worker",
            "risk": "medium",
            "params": {
                "worker_id": wid,
                "title": "SUPPIX",
                "body": _lang_text(
                    lang,
                    "Kurzer Hinweis von der Betriebsleitung.",
                    "Short note from operations.",
                    "ملاحظة قصيرة من الإدارة.",
                ),
                "tag": "ai-operator",
            },
            "labelDe": f"Push an {wname}",
            "labelEn": f"Push to {wname}",
            "labelAr": f"إشعار إلى {wname}",
        },
    ]
    return {
        "answer": answer,
        "intent": "operator_find_worker",
        "configured": True,
        "sources": ["search_workers", "get_worker_profile"],
        "toolsUsed": ["search_workers", "get_worker_profile"],
        "actions": actions,
        "suggestedActions": actions,
        "ok": True,
    }


def _task_presence(db, company_id: str, *, lang: str) -> dict[str, Any]:
    from .tools import tool_presence_summary

    data = tool_presence_summary(db, company_id, {})
    by_site = data.get("bySite") or []
    lines = [f"• {s.get('site')}: {s.get('count')}" for s in by_site[:10]]
    answer = _lang_text(
        lang,
        f"Anwesenheit {data.get('date')}: **{data.get('onSiteCount', 0)}** vor Ort, "
        f"**{data.get('openPresenceCount', 0)}** offene Sessions.\n"
        + ("\n".join(lines) if lines else "Keine Standort-Aufschlüsselung."),
        f"Presence {data.get('date')}: **{data.get('onSiteCount', 0)}** on site, "
        f"**{data.get('openPresenceCount', 0)}** open sessions.\n"
        + ("\n".join(lines) if lines else "No site breakdown."),
        f"الحضور {data.get('date')}: **{data.get('onSiteCount', 0)}** في الموقع، "
        f"**{data.get('openPresenceCount', 0)}** جلسات مفتوحة.\n"
        + ("\n".join(lines) if lines else "لا تفصيل بالمواقع."),
    )
    return {
        "answer": answer,
        "intent": "operator_presence",
        "configured": True,
        "sources": ["get_presence_summary"],
        "toolsUsed": ["get_presence_summary"],
        "actions": [
            {
                "id": "nav_access",
                "type": "navigate",
                "tab": "access",
                "url": "/admin-v2/index.html?tab=access",
                "labelDe": "Anwesenheit öffnen",
                "labelEn": "Open attendance",
                "labelAr": "فتح الحضور",
            }
        ],
        "suggestedActions": [],
        "ok": True,
    }


def _task_tomorrow_forecast(db, company_id: str, *, lang: str) -> dict[str, Any]:
    from .tools import tool_tomorrow_forecast

    data = tool_tomorrow_forecast(db, company_id, {})
    summary = data.get("summary") or data.get("headline") or data.get("message")
    risks = data.get("risks") or data.get("alerts") or data.get("items") or []
    lines = []
    if isinstance(risks, list):
        for r in risks[:6]:
            if isinstance(r, dict):
                lines.append(f"• {r.get('title') or r.get('name') or r.get('message') or r}")
            else:
                lines.append(f"• {r}")
    if not summary:
        summary = _lang_text(lang, "Morgen-Prognose geladen.", "Tomorrow forecast loaded.", "تم تحميل توقع الغد.")
    answer = str(summary) + (("\n" + "\n".join(lines)) if lines else "")
    # Compact dict dump fallback when structure is opaque.
    if not lines and isinstance(data, dict) and len(answer) < 40:
        keys = [k for k in ("expectedOnSite", "expectedAbsent", "lateRisk", "staffingGap") if k in data]
        if keys:
            answer += "\n" + "\n".join(f"• {k}: {data.get(k)}" for k in keys)
    return {
        "answer": answer,
        "intent": "operator_tomorrow_forecast",
        "configured": True,
        "sources": ["get_tomorrow_forecast"],
        "toolsUsed": ["get_tomorrow_forecast"],
        "actions": [
            {
                "id": "nav_access",
                "type": "navigate",
                "tab": "access",
                "url": "/admin-v2/index.html?tab=access",
                "labelDe": "Anwesenheit öffnen",
                "labelEn": "Open attendance",
                "labelAr": "فتح الحضور",
            }
        ],
        "suggestedActions": [],
        "ok": True,
    }


def _task_outside_hours(db, company_id: str, *, lang: str) -> dict[str, Any]:
    from .tools import tool_outside_hours_attempts

    data = tool_outside_hours_attempts(db, company_id, {"hours": 24, "limit": 20})
    attempts = data.get("attempts") or []
    lines = [
        f"• {(a.get('body') or a.get('title') or a.get('id'))}"
        + (f" ({a.get('createdAt')})" if a.get("createdAt") else "")
        for a in attempts[:8]
        if isinstance(a, dict)
    ]
    answer = _lang_text(
        lang,
        f"**{data.get('count', len(attempts))}** Outside-Hours-Versuche (24h).\n"
        + ("\n".join(lines) if lines else "Keine."),
        f"**{data.get('count', len(attempts))}** outside-hours attempts (24h).\n"
        + ("\n".join(lines) if lines else "None."),
        f"**{data.get('count', len(attempts))}** محاولات خارج الدوام (24س).\n"
        + ("\n".join(lines) if lines else "لا شيء."),
    )
    actions = [
        {
            "id": "ack_sys",
            "type": "execute",
            "action": "ack_open_system_alerts",
            "risk": "medium",
            "params": {"limit": 20},
            "labelDe": "System-Hinweise schließen",
            "labelEn": "Ack system alerts",
            "labelAr": "إغلاق تنبيهات النظام",
        },
        {
            "id": "nav_ops",
            "type": "navigate",
            "url": "/ops-command-center.html",
            "labelDe": "Ops Center öffnen",
            "labelEn": "Open ops center",
            "labelAr": "فتح مركز العمليات",
        },
    ]
    return {
        "answer": answer,
        "intent": "operator_outside_hours",
        "configured": True,
        "sources": ["get_outside_hours_attempts"],
        "toolsUsed": ["get_outside_hours_attempts"],
        "actions": actions,
        "suggestedActions": actions if attempts else [actions[1]],
        "ok": True,
    }


def _task_risk(db, company_id: str, *, lang: str) -> dict[str, Any]:
    from .tools import tool_attendance_risk, tool_workforce_risk

    att = tool_attendance_risk(db, company_id, {})
    wf = tool_workforce_risk(db, company_id, {})
    att_items = att.get("risks") or att.get("workers") or att.get("items") or []
    wf_items = wf.get("risks") or wf.get("workers") or wf.get("items") or []
    lines = []
    for src, label in ((att_items, "Attendance"), (wf_items, "Workforce")):
        if isinstance(src, list):
            for it in src[:4]:
                if isinstance(it, dict):
                    lines.append(
                        f"• [{label}] {it.get('name') or it.get('title') or it.get('workerId') or it.get('id')}"
                        + (f" — {it.get('risk') or it.get('level') or ''}".rstrip(" —"))
                    )
                else:
                    lines.append(f"• [{label}] {it}")
    score = wf.get("score") or wf.get("riskScore") or att.get("score")
    answer = _lang_text(
        lang,
        f"Risiko-Überblick"
        + (f" (Score {score})" if score is not None else "")
        + ":\n"
        + ("\n".join(lines) if lines else "Keine auffälligen Risiken geladen."),
        f"Risk overview"
        + (f" (score {score})" if score is not None else "")
        + ":\n"
        + ("\n".join(lines) if lines else "No notable risks loaded."),
        f"ملخص المخاطر"
        + (f" (درجة {score})" if score is not None else "")
        + ":\n"
        + ("\n".join(lines) if lines else "لا مخاطر بارزة."),
    )
    return {
        "answer": answer,
        "intent": "operator_risk",
        "configured": True,
        "sources": ["get_attendance_risk", "get_workforce_risk"],
        "toolsUsed": ["get_attendance_risk", "get_workforce_risk"],
        "actions": [
            {
                "id": "nav_workers",
                "type": "navigate",
                "tab": "workers",
                "url": "/admin-v2/index.html?tab=workers",
                "labelDe": "Mitarbeiter öffnen",
                "labelEn": "Open workers",
                "labelAr": "فتح الموظفين",
            }
        ],
        "suggestedActions": [],
        "ok": True,
    }


def _task_access_timeline(db, company_id: str, *, lang: str) -> dict[str, Any]:
    from .tools import tool_access_timeline_today

    data = tool_access_timeline_today(db, company_id, {"limit": 25})
    events = data.get("events") or []
    lines = []
    for e in events[:12]:
        name = f"{(e.get('first_name') or '')} {(e.get('last_name') or '')}".strip() or e.get("worker_id")
        lines.append(
            f"• {e.get('timestamp') or '—'} · {name} · {e.get('direction') or '—'} @ {e.get('gate') or '—'}"
        )
    answer = _lang_text(
        lang,
        f"Zutritt heute ({data.get('date')}): **{len(events)}** Events.\n"
        + ("\n".join(lines) if lines else "Keine Events."),
        f"Access today ({data.get('date')}): **{len(events)}** events.\n"
        + ("\n".join(lines) if lines else "No events."),
        f"الدخول اليوم ({data.get('date')}): **{len(events)}** حدثاً.\n"
        + ("\n".join(lines) if lines else "لا أحداث."),
    )
    return {
        "answer": answer,
        "intent": "operator_access_timeline",
        "configured": True,
        "sources": ["get_access_timeline_today"],
        "toolsUsed": ["get_access_timeline_today"],
        "actions": [
            {
                "id": "nav_access",
                "type": "navigate",
                "tab": "access",
                "url": "/admin-v2/index.html?tab=access",
                "labelDe": "Anwesenheit öffnen",
                "labelEn": "Open attendance",
                "labelAr": "فتح الحضور",
            }
        ],
        "suggestedActions": [],
        "ok": True,
    }


def _task_fraud(db, company_id: str, *, lang: str) -> dict[str, Any]:
    from .tools import tool_fraud_signals

    data = tool_fraud_signals(db, company_id, {})
    signals = data.get("signals") or data.get("findings") or data.get("items") or []
    lines = []
    if isinstance(signals, list):
        for s in signals[:8]:
            if isinstance(s, dict):
                lines.append(f"• {s.get('type') or s.get('title') or s.get('message') or s}")
            else:
                lines.append(f"• {s}")
    count = data.get("count")
    if count is None:
        count = len(signals) if isinstance(signals, list) else 0
    answer = _lang_text(
        lang,
        f"Fraud-/Anomalie-Signale: **{count}**.\n" + ("\n".join(lines) if lines else "Keine Signale."),
        f"Fraud/anomaly signals: **{count}**.\n" + ("\n".join(lines) if lines else "No signals."),
        f"إشارات احتيال/شذوذ: **{count}**.\n" + ("\n".join(lines) if lines else "لا إشارات."),
    )
    actions = [
        {
            "id": "nav_ops",
            "type": "navigate",
            "url": "/ops-command-center.html",
            "labelDe": "Ops Center öffnen",
            "labelEn": "Open ops center",
            "labelAr": "فتح مركز العمليات",
        },
        {
            "id": "resolve_sec",
            "type": "execute",
            "action": "resolve_open_security_alerts",
            "risk": "high",
            "params": {"limit": 15},
            "labelDe": "Security-Alerts auflösen",
            "labelEn": "Resolve security alerts",
            "labelAr": "إغلاق تنبيهات الأمن",
        },
    ]
    return {
        "answer": answer,
        "intent": "operator_fraud",
        "configured": True,
        "sources": ["get_fraud_signals"],
        "toolsUsed": ["get_fraud_signals"],
        "actions": actions,
        "suggestedActions": actions,
        "ok": True,
    }
