"""Canonical WorkPass / Suppix AI branding for LLM answers (no legacy product names)."""
from __future__ import annotations

import re
from typing import Any

# Legacy names that must never appear in AI answers.
_LEGACY_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Ba[uü]Pass\s+Control", re.I), "WorkPass"),
    (re.compile(r"BauPass\s+Control", re.I), "WorkPass"),
    (re.compile(r"Control\s+Pass(?:\s+KI|\s+AI)?", re.I), "WorkPass"),
    (re.compile(r"Baupass\s+Control", re.I), "WorkPass"),
    (re.compile(r"Baukontrolle", re.I), "WorkPass"),
    (re.compile(r"\bBaupass\b(?!\s*AI)", re.I), "WorkPass"),
)

_BRANDING_RULES: dict[str, str] = {
    "de": (
        "MARKENREGELN (verbindlich): Das Produkt heißt **WorkPass** von **Suppix AI** "
        "(Betreiber: Suppix Technologie UG). Verwende NIEMALS alte Namen wie "
        "BauPass Control, Control Pass oder Baupass Control. "
        "Bei Fragen nach Gründer, Eigentümer oder wer das System entwickelt hat: "
        "nutze ausschließlich den Gründer-Profil-Block im Kontext — erfinde nichts."
    ),
    "en": (
        "BRANDING (mandatory): The product is **WorkPass** by **Suppix AI** "
        "(operator: Suppix Technologie UG). NEVER use legacy names such as "
        "BauPass Control, Control Pass, or Baupass Control. "
        "When asked who founded, owns, or built the platform, use ONLY the founder "
        "profile block in context — do not invent facts."
    ),
    "ar": (
        "قواعد العلامة (إلزامية): المنتج **WorkPass** من **Suppix AI** "
        "(المشغّل: Suppix Technologie UG). لا تستخدم أبداً الأسماء القديمة مثل "
        "BauPass Control أو Control Pass. "
        "عند السؤال عن المؤسس أو مالك الشركة أو من طوّر النظام: استخدم فقط "
        "كتلة ملف المؤسّس في السياق — لا تختلق معلومات."
    ),
}


def sanitize_legacy_brand(text: str) -> str:
    """Replace outdated product names in model output."""
    out = str(text or "")
    if not out.strip():
        return out
    for pattern, replacement in _LEGACY_REPLACEMENTS:
        out = pattern.sub(replacement, out)
    return out


def ai_branding_system_block(lang: str = "de") -> str:
    lang = (lang or "de")[:2]
    return _BRANDING_RULES.get(lang) or _BRANDING_RULES["de"]


def sanitize_ai_answer(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = sanitize_legacy_brand(str(text))
    return cleaned


def enrich_founder_context(profile: dict[str, Any], lang: str = "de") -> str:
    """Founder block with explicit anti-legacy guard for LLM system prompts."""
    from .founder_profile import _resolve_bio, _resolve_title

    lang = (lang or "de")[:2]
    name = profile.get("name") or "—"
    company = profile.get("company") or "Suppix AI"
    platform = profile.get("platform") or "WorkPass"
    title = _resolve_title(profile, lang)
    bio = _resolve_bio(profile, lang)
    guard = ai_branding_system_block(lang)
    if lang == "ar":
        return (
            f"{guard}\n\n"
            f"ملف المؤسّس (مصدر رسمي وحيد لهذه الأسئلة): "
            f"{name}، {title}، {company}. المنصة: {platform}. {bio}"
        )
    if lang == "en":
        return (
            f"{guard}\n\n"
            f"Founder profile (single authoritative source for founder/owner questions): "
            f"{name}, {title}, {company}. Platform: {platform}. {bio}"
        )
    return (
        f"{guard}\n\n"
        f"Gründer-Profil (einzige offizielle Quelle für Gründer-/Inhaber-Fragen): "
        f"{name}, {title}, {company}. Plattform: {platform}. {bio}"
    )
