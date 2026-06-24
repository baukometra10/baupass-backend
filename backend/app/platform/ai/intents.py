"""Fast intent routing before LLM — contact, help, and common navigation."""
from __future__ import annotations

import os
import re
from typing import Any

_FOUNDER_PATTERNS = re.compile(
    r"(gründer|gründung|gegründet|entwickelt|who (?:founded|created|built|made)|"
    r"founder|creator|built this|who is behind|who made|"
    r"wer hat (?:das|dieses|diesen)? ?(?:system|plattform|programm|portal|tool|ki|ai)?|"
    r"wer steckt hinter|wer ist der (?:gründer|eigentümer|inhaber|boss|chef)|"
    r"من (?:أسس|أسّس|أنشأ|طوّر|طور|بنى|صنع|قام)|"
    r"من الذي|مَن الذي|مؤسس|مالك (?:النظام|المنصة)|صاحب (?:الشركة|النظام|المنصة)|"
    r"تأسيس (?:هذا )?(?:النظام|المنصة)|"
    r"wer hat bau ?pass|who founded bau ?pass|who created bau ?pass)",
    re.I,
)

_CONTACT_PATTERNS = re.compile(
    r"(kontakt|contact|support|hotline|telefon|phone|e-mail|email|"
    r"erreichen|anrufen|zuständig|zustaendig|wer ist mein|meine daten|"
    r"(?:ich brauche )?hilfe(?: bei)?(?: kontakt| support| beim admin)?|"
    r"اتصل|تواصل|مساعدة|دعم|مدير|بريد)",
    re.I,
)

_ANALYTICAL_PATTERNS = re.compile(
    r"\b(wer|wie viele|wieviele|warum|wann|welche|welcher|welches|"
    r"ist|sind|hat|haben|gibt|liste|status|überblick|ueberblick|"
    r"wer ist|wo ist|how many|who is|why|count|analyze|analysier)\b",
    re.I,
)

_NAV_COMMAND_PATTERNS = re.compile(
    r"\b(öffne|open|zeig(?:e)?(?: mir)?(?: die)? (?:seite|ansicht|übersicht|uebersicht)|"
    r"geh(?:e)? zu|navigier|bring mich|wechsel(?:e)? zu|switch to|open the)\b",
    re.I,
)

_NAV_RULES: list[tuple[re.Pattern[str], str, dict[str, str]]] = [
    (
        re.compile(r"(auf der baustelle|on site|on-site|wer ist drinnen|anwesend|موقع|حاضر)", re.I),
        "/index.html?view=ops-center",
        {"de": "Ops-Zentrale öffnen", "en": "Open ops center", "ar": "فتح مركز العمليات"},
    ),
    (
        re.compile(r"(notfall|emergency|evaku|طوارئ)", re.I),
        "/ops-command-center.html?embed=1",
        {"de": "Notfall / Ops öffnen", "en": "Open emergency ops", "ar": "فتح الطوارئ"},
    ),
    (
        re.compile(r"(sicherheit|security|alarm|تنبيه|أمن)", re.I),
        "/index.html?view=admin-v2",
        {"de": "Betrieb & Sicherheit", "en": "Operations & security", "ar": "التشغيل والأمن"},
    ),
    (
        re.compile(r"(urlaub|leave|abwesen|إجاز)", re.I),
        "/index.html?view=leave",
        {"de": "Urlaubsanträge", "en": "Leave requests", "ar": "طلبات الإجازة"},
    ),
    (
        re.compile(r"(dokument|document|ablauf|compliance|وثائق|مستند)", re.I),
        "/index.html?view=documents",
        {"de": "Dokumente", "en": "Documents", "ar": "المستندات"},
    ),
    (
        re.compile(r"(mitarbeiter|worker|personal|موظف)", re.I),
        "/index.html?view=workers",
        {"de": "Mitarbeiter", "en": "Workers", "ar": "الموظفون"},
    ),
    (
        re.compile(r"(zutritt|access|gate|drehkreuz|دخول)", re.I),
        "/index.html?view=access",
        {"de": "Zutritt", "en": "Access", "ar": "الدخول"},
    ),
    (
        re.compile(r"(ki|copilot|assistent|assistant|مساعد)", re.I),
        "/enterprise-hub.html?embed=1#ai-panel",
        {"de": "KI-Assistent", "en": "AI assistant", "ar": "مساعد AI"},
    ),
]


def _label(labels: dict[str, str], lang: str) -> str:
    return labels.get(lang[:2]) or labels.get("de") or labels.get("en") or ""


def _load_help_context(db, company_id: str) -> dict[str, Any]:
    company = db.execute(
        "SELECT id, name, contact, plan, status FROM companies WHERE id = ? AND deleted_at IS NULL",
        (company_id,),
    ).fetchone()
    settings = db.execute(
        """
        SELECT platform_name, operator_name, invoice_operator_phone,
               invoice_operator_website, smtp_sender_email
        FROM settings WHERE id = 1
        """
    ).fetchone()
    public_base = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    platform = (settings["platform_name"] if settings else "") or "SUPPIX"
    operator = (settings["operator_name"] if settings else "") or "Support"
    phone = (settings["invoice_operator_phone"] if settings else "") or ""
    website = (settings["invoice_operator_website"] if settings else "") or public_base
    mail = (settings["smtp_sender_email"] if settings else "") or ""
    return {
        "companyName": company["name"] if company else "",
        "companyContact": (company["contact"] if company else "") or "",
        "companyPlan": (company["plan"] if company else "") or "",
        "companyStatus": (company["status"] if company else "") or "",
        "platformName": platform,
        "operatorName": operator,
        "supportPhone": phone,
        "supportWebsite": website,
        "supportEmail": mail,
        "portalUrl": public_base or website,
    }


def _format_contact_answer(ctx: dict[str, Any], lang: str) -> str:
    cn = ctx.get("companyName") or "—"
    cc = ctx.get("companyContact") or "—"
    op = ctx.get("operatorName") or "SUPPIX Support"
    phone = ctx.get("supportPhone") or "—"
    mail = ctx.get("supportEmail") or "—"
    web = ctx.get("portalUrl") or ctx.get("supportWebsite") or "—"
    if lang == "ar":
        return (
            f"**شركتك ({cn})**\n"
            f"• جهة اتصال الشركة: {cc}\n\n"
            f"**دعم {ctx.get('platformName') or 'SUPPIX'}**\n"
            f"• المشغّل: {op}\n"
            f"• هاتف: {phone}\n"
            f"• بريد: {mail}\n"
            f"• البوابة: {web}"
        )
    if lang == "en":
        return (
            f"**Your company ({cn})**\n"
            f"• Company contact: {cc}\n\n"
            f"**{ctx.get('platformName') or 'SUPPIX'} support**\n"
            f"• Operator: {op}\n"
            f"• Phone: {phone}\n"
            f"• Email: {mail}\n"
            f"• Portal: {web}"
        )
    return (
        f"**Ihre Firma ({cn})**\n"
        f"• Firmen-Kontakt: {cc}\n\n"
        f"**{ctx.get('platformName') or 'SUPPIX'} Support**\n"
        f"• Betreiber: {op}\n"
        f"• Telefon: {phone}\n"
        f"• E-Mail: {mail}\n"
        f"• Portal: {web}"
    )


def _format_worker_contact_answer(ctx: dict[str, Any], lang: str) -> str:
    cn = ctx.get("companyName") or "—"
    cc = ctx.get("companyContact") or "—"
    we = ctx.get("workerEmail") or "—"
    op = ctx.get("operatorName") or "SUPPIX Support"
    mail = ctx.get("supportEmail") or "—"
    if lang == "ar":
        return (
            f"**شركتك ({cn})**\n"
            f"• جهة اتصال الشركة: {cc}\n"
            f"• بريدك المسجّل: {we}\n\n"
            f"**الدعم ({op})**\n"
            f"• بريد الدعم: {mail}"
        )
    if lang == "en":
        return (
            f"**Your company ({cn})**\n"
            f"• Company contact: {cc}\n"
            f"• Your email on file: {we}\n\n"
            f"**{op} support**\n"
            f"• Support email: {mail}"
        )
    return (
        f"**Ihre Firma ({cn})**\n"
        f"• Firmen-Kontakt / Admin: {cc}\n"
        f"• Ihre hinterlegte E-Mail: {we}\n\n"
        f"**{op} Support**\n"
        f"• Support-E-Mail: {mail}"
    )


def try_intent_response(
    db,
    company_id: str,
    question: str,
    *,
    role: str = "company-admin",
    lang: str = "de",
    worker: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    q = (question or "").strip()
    if not q or not company_id:
        return None
    lang = (lang or "de")[:2]

    if _FOUNDER_PATTERNS.search(q):
        from .founder_profile import format_founder_answer, load_founder_profile

        profile = load_founder_profile(db)
        actions: list[dict[str, Any]] = []
        if profile.get("website"):
            actions.append(
                {
                    "id": "founder_website",
                    "type": "navigate",
                    "url": str(profile["website"]),
                    "labelDe": "Website öffnen",
                    "labelEn": "Open website",
                    "labelAr": "فتح الموقع",
                }
            )
        if profile.get("email") and "@" in str(profile["email"]):
            actions.append(
                {
                    "id": "founder_email",
                    "type": "navigate",
                    "url": f"mailto:{profile['email']}",
                    "labelDe": "E-Mail senden",
                    "labelEn": "Send email",
                    "labelAr": "إرسال بريد",
                }
            )
        return {
            "answer": format_founder_answer(profile, lang),
            "intent": "platform_founder",
            "configured": True,
            "sources": ["platform_founder_profile"],
            "actions": actions,
            "suggestedActions": actions,
        }

    if _CONTACT_PATTERNS.search(q):
        ctx = _load_help_context(db, company_id)
        if worker:
            ctx["workerEmail"] = (
                worker.get("contact_email")
                or worker.get("contactEmail")
                or ""
            )
        actions: list[dict[str, Any]] = []
        if ctx.get("companyContact"):
            contact = str(ctx["companyContact"])
            if "@" in contact:
                actions.append(
                    {
                        "id": "mail_company",
                        "type": "navigate",
                        "url": f"mailto:{contact}",
                        "labelDe": "E-Mail an Firma",
                        "labelEn": "Email company",
                        "labelAr": "مراسلة الشركة",
                    }
                )
        if ctx.get("supportEmail"):
            actions.append(
                {
                    "id": "mail_support",
                    "type": "navigate",
                    "url": f"mailto:{ctx['supportEmail']}",
                    "labelDe": "Support kontaktieren",
                    "labelEn": "Contact support",
                    "labelAr": "مراسلة الدعم",
                }
            )
        actions.append(
            {
                "id": "nav_admin",
                "type": "navigate",
                "url": "/index.html?view=admin-v2",
                "labelDe": "Admin v2 öffnen",
                "labelEn": "Open admin v2",
                "labelAr": "فتح Admin v2",
            }
        )
        answer_fn = _format_worker_contact_answer if worker else _format_contact_answer
        if worker:
            if ctx.get("companyContact") and "@" in str(ctx["companyContact"]):
                actions.append(
                    {
                        "id": "mail_boss",
                        "type": "navigate",
                        "url": f"mailto:{ctx['companyContact']}",
                        "labelDe": "Chef / Admin mailen",
                        "labelEn": "Email admin",
                        "labelAr": "مراسلة المدير",
                    }
                )
            actions.append(
                {
                    "id": "worker_leave",
                    "type": "worker_tab",
                    "tab": "leaveRequestCard",
                    "labelDe": "Urlaubsantrag",
                    "labelEn": "Leave request",
                    "labelAr": "طلب إجازة",
                }
            )
        return {
            "answer": answer_fn(ctx, lang),
            "intent": "contact_help",
            "configured": True,
            "sources": ["company_directory", "platform_settings"],
            "actions": actions,
            "suggestedActions": actions,
        }

    if worker:
        wnav = [
            (re.compile(r"(urlaub|krank|abwesen|leave|إجاز)", re.I), "leaveRequestCard", {"de": "Urlaubsantrag", "en": "Leave", "ar": "إجازة"}),
            (re.compile(r"(dokument|document|nachweis|وثائق)", re.I), "documentsCard", {"de": "Dokumente", "en": "Documents", "ar": "مستندات"}),
            (re.compile(r"(stunden|zeiten|timesheet|ساعات)", re.I), "timesheetCard", {"de": "Stunden", "en": "Hours", "ar": "ساعات"}),
            (re.compile(r"(ausweis|badge|qr|بطاقة)", re.I), "sessionInfoCard", {"de": "Ausweis", "en": "Badge", "ar": "البطاقة"}),
        ]
        for pattern, tab, labels in wnav:
            if pattern.search(q):
                action = {
                    "id": f"tab_{tab}",
                    "type": "worker_tab",
                    "tab": tab,
                    "labelDe": labels["de"],
                    "labelEn": labels["en"],
                    "labelAr": labels["ar"],
                }
                return {
                    "answer": _label(labels, lang) + (" öffnen." if lang == "de" else ""),
                    "intent": "worker_navigate",
                    "configured": True,
                    "sources": ["intent_router"],
                    "actions": [action],
                    "suggestedActions": [action],
                }

    for pattern, url, labels in _NAV_RULES:
        if not worker and _ANALYTICAL_PATTERNS.search(q):
            continue
        if not worker and not _NAV_COMMAND_PATTERNS.search(q):
            continue
        if pattern.search(q):
            action = {
                "id": f"nav_{pattern.pattern[:12]}",
                "type": "navigate",
                "url": url,
                "labelDe": labels["de"],
                "labelEn": labels["en"],
                "labelAr": labels["ar"],
            }
            answer_de = f"Ich leite Sie weiter: {_label(labels, lang)}."
            if lang == "en":
                answer = f"Opening: {_label(labels, lang)}."
            elif lang == "ar":
                answer = f"سأفتح: {_label(labels, lang)}."
            else:
                answer = answer_de
            return {
                "answer": answer,
                "intent": "navigate",
                "configured": True,
                "sources": ["intent_router"],
                "actions": [action],
                "suggestedActions": [action],
            }

    return None
