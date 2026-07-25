"""Allowlisted UI pilot — safe tab/page clicks for admin operator (no arbitrary RPA)."""
from __future__ import annotations

import re
from typing import Any

# Only these targets may be clicked/navigated by the AI operator.
UI_TARGETS: dict[str, dict[str, Any]] = {
    "overview": {
        "tab": "overview",
        "selector": '.tab[data-tab="overview"]',
        "url": "/admin-v2/index.html?tab=overview",
        "labels": {"de": "Übersicht öffnen", "en": "Open overview", "ar": "فتح النظرة العامة"},
    },
    "inbox": {
        "tab": "inbox",
        "selector": '.tab[data-tab="inbox"]',
        "url": "/admin-v2/index.html?tab=inbox",
        "labels": {"de": "Inbox öffnen", "en": "Open inbox", "ar": "فتح الوارد"},
    },
    "workers": {
        "tab": "workers",
        "selector": '.tab[data-tab="workers"]',
        "url": "/admin-v2/index.html?tab=workers",
        "labels": {"de": "Mitarbeiter öffnen", "en": "Open workers", "ar": "فتح الموظفين"},
    },
    "access": {
        "tab": "access",
        "selector": '.tab[data-tab="access"]',
        "url": "/admin-v2/index.html?tab=access",
        "labels": {"de": "Anwesenheit öffnen", "en": "Open attendance", "ar": "فتح الحضور"},
    },
    "operations": {
        "tab": "operations",
        "selector": '.tab[data-tab="operations"]',
        "url": "/admin-v2/index.html?tab=operations",
        "labels": {"de": "Betrieb öffnen", "en": "Open operations", "ar": "فتح التشغيل"},
    },
    "copilot": {
        "tab": "copilot",
        "selector": '.tab[data-tab="copilot"]',
        "url": "/admin-v2/index.html?tab=copilot",
        "labels": {"de": "Copilot öffnen", "en": "Open Copilot", "ar": "فتح Copilot"},
    },
    "billing": {
        "tab": "billing",
        "selector": '.tab[data-tab="billing"]',
        "url": "/admin-v2/index.html?tab=billing",
        "labels": {"de": "Rechnungen öffnen", "en": "Open billing", "ar": "فتح الفواتير"},
    },
    "contracts": {
        "tab": "contracts",
        "selector": None,
        "url": "/admin-v2/contracts.html",
        "labels": {"de": "Verträge öffnen", "en": "Open contracts", "ar": "فتح العقود"},
    },
    "docs": {
        "tab": "docs",
        "selector": None,
        "url": "/admin-v2/docs.html",
        "labels": {"de": "Docs öffnen", "en": "Open docs", "ar": "فتح الوثائق"},
    },
    "chat": {
        "tab": "chat",
        "selector": None,
        "url": "/admin-v2/chat.html",
        "labels": {"de": "Chat öffnen", "en": "Open chat", "ar": "فتح المحادثة"},
    },
    "deployment": {
        "tab": "workers",
        "selector": '.tab[data-tab="workers"]',
        "url": "/admin-v2/index.html?tab=workers&einsatzplan=1",
        "focus": "deployment",
        "labels": {"de": "Einsatzplan öffnen", "en": "Open deployment plan", "ar": "فتح خطة الانتشار"},
    },
    "hub": {
        "tab": None,
        "selector": None,
        "url": "/enterprise-hub.html",
        "labels": {"de": "Enterprise Hub öffnen", "en": "Open Enterprise Hub", "ar": "فتح Enterprise Hub"},
    },
    "ops": {
        "tab": None,
        "selector": None,
        "url": "/ops-command-center.html",
        "labels": {"de": "Ops Command Center öffnen", "en": "Open Ops Command Center", "ar": "فتح مركز العمليات"},
    },
    "ai_center": {
        "tab": None,
        "selector": None,
        "url": "/ai-command-center.html",
        "labels": {"de": "AI Command Center öffnen", "en": "Open AI Command Center", "ar": "فتح مركز الذكاء الاصطناعي"},
    },
}

_CLICK_RE = re.compile(
    r"(klick|click|tippe|öffne(?:\s+tab)?|open(?:\s+tab)?|gehe\s+zu|go\s+to|navigier|"
    r"ouvre|ouvrir|abre|abrir|apri|otwórz|aç|"
    r"افتح\s*تبويب|انقر|انتقل|افتح)",
    re.I,
)

_TARGET_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"übersicht|overview|لوحة", re.I), "overview"),
    (re.compile(r"inbox|posteingang|وارد", re.I), "inbox"),
    (re.compile(r"mitarbeiter|workers?|team|موظفين|عمال|çalışan", re.I), "workers"),
    (re.compile(r"anwesenheit|zutritt|access|حضور|présence|asistencia", re.I), "access"),
    (re.compile(r"betrieb|operations|تشغيل|opérations", re.I), "operations"),
    (re.compile(r"copilot", re.I), "copilot"),
    (re.compile(r"rechnung|billing|فواتير|factur", re.I), "billing"),
    (re.compile(r"vertrag|contracts?|عقود|contrats?", re.I), "contracts"),
    (re.compile(r"\bdocs?\b|dokument|وثائق|documentos?", re.I), "docs"),
    (re.compile(r"\bchat\b|دردشة|محادثة", re.I), "chat"),
    (re.compile(r"einsatzplan|deployment|خطة\s*الانتشار|plan\s+de\s+déploiement", re.I), "deployment"),
    (re.compile(r"enterprise[- ]?hub|\bhub\b", re.I), "hub"),
    # AI Command Center before generic "command center" / Ops.
    (re.compile(r"ai[- ]?command|command[- ]?center\s*ai|\bai\s+command\s+center\b|مركز\s*الذكاء", re.I), "ai_center"),
    (re.compile(r"ops[- ]?command|\bops\b\s*command|مركز\s*العمليات", re.I), "ops"),
]


def match_ui_pilot_target(question: str) -> str | None:
    q = (question or "").strip()
    if not q or not _CLICK_RE.search(q):
        return None
    for pattern, key in _TARGET_HINTS:
        if pattern.search(q):
            return key
    return None


def build_ui_pilot_action(target_key: str, *, lang: str = "de") -> dict[str, Any] | None:
    spec = UI_TARGETS.get(target_key)
    if not spec:
        return None
    labels = spec.get("labels") or {}
    lang = (lang or "de")[:2]
    label = labels.get(lang) or labels.get("en") or labels.get("de") or target_key
    return {
        "id": f"ui_pilot_{target_key}",
        "type": "ui_pilot",
        "target": target_key,
        "tab": spec.get("tab"),
        "url": spec.get("url"),
        "selector": spec.get("selector"),
        "focus": spec.get("focus"),
        "labelDe": labels.get("de") or label,
        "labelEn": labels.get("en") or label,
        "labelAr": labels.get("ar") or label,
        "labels": {
            "de": labels.get("de") or label,
            "en": labels.get("en") or label,
            "ar": labels.get("ar") or label,
            "tr": labels.get("en") or label,
            "fr": labels.get("en") or label,
            "es": labels.get("en") or label,
            "it": labels.get("en") or label,
            "pl": labels.get("en") or label,
        },
    }


def try_ui_pilot_task(
    question: str,
    *,
    lang: str = "de",
    role: str | None = None,
) -> dict[str, Any] | None:
    key = match_ui_pilot_target(question)
    if not key:
        return None
    role_l = str(role or "").strip().lower()
    if role_l == "turnstile" and key in {"contracts", "docs"}:
        return None
    action = build_ui_pilot_action(key, lang=lang)
    if not action:
        return None
    from .operator_i18n import pick

    answer = pick(
        lang,
        de=f"Ich kann die Oberfläche jetzt bedienen: **{action['labelDe']}**.",
        en=f"I can drive the UI now: **{action['labelEn']}**.",
        ar=f"يمكنني تشغيل الواجهة الآن: **{action['labelAr']}**.",
        tr=f"Arayüzü şimdi kullanabilirim: **{action['labelEn']}**.",
        fr=f"Je peux piloter l'interface: **{action['labelEn']}**.",
        es=f"Puedo controlar la interfaz: **{action['labelEn']}**.",
        it=f"Posso guidare l'interfaccia: **{action['labelEn']}**.",
        pl=f"Mogę sterować interfejsem: **{action['labelEn']}**.",
    )
    return {
        "answer": answer,
        "intent": "operator_ui_pilot",
        "configured": True,
        "sources": ["ui_pilot"],
        "toolsUsed": ["ui_pilot"],
        "actions": [action],
        "suggestedActions": [action],
        "ok": True,
    }
