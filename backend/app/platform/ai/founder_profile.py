"""Platform founder / operator profile for AI founder questions."""
from __future__ import annotations

import os
import re
from typing import Any

_IMPRESSUM_NAME = re.compile(
    r"(?:Vertreten durch|Represented by|Managing director|Geschäftsführer|Geschaeftsfuehrer)\s*:\s*(.+?)(?:\n|$)",
    re.I,
)

_DEFAULT_FOUNDER_NAME = "Sherif Mohamed"
_DEFAULT_FOUNDER_EMAIL = "baupass-control@outlook.de"

_DEFAULT_TITLES = {
    "de": "Gründer und Geschäftsführer",
    "en": "Founder & CEO",
    "ar": "المؤسّس والرئيس التنفيذي",
}

_DEFAULT_BIOS = {
    "de": (
        "{company} ist Betreiber und Entwickler der {platform}-Plattform — "
        "für Unternehmensidentität, Zutrittskontrolle, Compliance und Baustellen-Operations."
    ),
    "en": (
        "{company} operates and built the {platform} platform — "
        "enterprise identity, access control, compliance, and site operations."
    ),
    "ar": (
        "شركة {company} هي المشغّل والمطوّر لمنصة {platform} — "
        "للهوية المؤسسية والتحكم بالدخول والامتثال وعمليات المواقع."
    ),
}


def _parse_impressum_name(text: str) -> str:
    match = _IMPRESSUM_NAME.search(text or "")
    return match.group(1).strip() if match else ""


def load_founder_profile(db) -> dict[str, Any]:
    settings = db.execute(
        """
        SELECT platform_name, operator_name, impressum_text,
               invoice_operator_phone, invoice_operator_website,
               invoice_operator_email, invoice_operator_street,
               invoice_operator_zip_city, smtp_sender_email
        FROM settings WHERE id = 1
        """
    ).fetchone()
    public_base = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    platform = (settings["platform_name"] if settings else "") or "SUPPIX"
    company = (os.getenv("BAUPASS_FOUNDER_COMPANY") or "").strip() or (
        (settings["operator_name"] if settings else "") or "Suppix Technologie UG"
    )
    impressum = (settings["impressum_text"] if settings else "") or ""
    name = (
        (os.getenv("BAUPASS_FOUNDER_NAME") or "").strip()
        or _parse_impressum_name(impressum)
        or _DEFAULT_FOUNDER_NAME
    )
    title = (os.getenv("BAUPASS_FOUNDER_TITLE") or "").strip()
    phone = (settings["invoice_operator_phone"] if settings else "") or ""
    website = (
        (settings["invoice_operator_website"] if settings else "") or public_base or ""
    ).strip()
    email = (
        (os.getenv("BAUPASS_FOUNDER_EMAIL") or "").strip()
        or (settings["invoice_operator_email"] if settings else "")
        or (settings["smtp_sender_email"] if settings else "")
        or _DEFAULT_FOUNDER_EMAIL
    ).strip()
    street = (settings["invoice_operator_street"] if settings else "") or ""
    zip_city = (settings["invoice_operator_zip_city"] if settings else "") or ""
    address = ", ".join(p for p in (street, zip_city) if p).strip()
    bio_env = (os.getenv("BAUPASS_FOUNDER_BIO") or "").strip()
    return {
        "name": name,
        "title": title,
        "company": company,
        "platform": platform,
        "phone": phone,
        "website": website,
        "email": email,
        "address": address,
        "bioEnv": bio_env,
    }


def _resolve_bio(profile: dict[str, Any], lang: str) -> str:
    lang = (lang or "de")[:2]
    if profile.get("bioEnv"):
        return str(profile["bioEnv"])
    lang_bio = (os.getenv(f"BAUPASS_FOUNDER_BIO_{lang.upper()}") or "").strip()
    if lang_bio:
        return lang_bio
    template = _DEFAULT_BIOS.get(lang) or _DEFAULT_BIOS["de"]
    return template.format(
        company=profile.get("company") or "Suppix Technologie UG",
        platform=profile.get("platform") or "SUPPIX",
    )


def _resolve_title(profile: dict[str, Any], lang: str) -> str:
    lang = (lang or "de")[:2]
    if profile.get("title"):
        return str(profile["title"])
    lang_title = (os.getenv(f"BAUPASS_FOUNDER_TITLE_{lang.upper()}") or "").strip()
    if lang_title:
        return lang_title
    return _DEFAULT_TITLES.get(lang) or _DEFAULT_TITLES["de"]


def format_founder_answer(profile: dict[str, Any], lang: str) -> str:
    lang = (lang or "de")[:2]
    name = str(profile.get("name") or "").strip()
    company = str(profile.get("company") or "Suppix Technologie UG").strip()
    platform = str(profile.get("platform") or "SUPPIX").strip()
    title = _resolve_title(profile, lang)
    bio = _resolve_bio(profile, lang)
    phone = str(profile.get("phone") or "").strip()
    website = str(profile.get("website") or "").strip()
    email = str(profile.get("email") or "").strip()
    address = str(profile.get("address") or "").strip()

    contact_bits: list[str] = []
    if website:
        contact_bits.append(website)
    if email:
        contact_bits.append(email)
    if phone:
        contact_bits.append(phone)
    contact = " · ".join(contact_bits)

    if lang == "ar":
        if name:
            lead = (
                f"أسّس منصة {platform} صاحب شركة {company} الشهير، {name}، "
                f"وهو {title} في {company}."
            )
        else:
            lead = (
                f"طوّرت شركة {company} الشهيرة منصة {platform} "
                f"للهوية المؤسسية والتحكم بالدخول والامتثال."
            )
        parts = [lead, bio]
        if address:
            parts.append(f"المقر: {address}.")
        if contact:
            parts.append(f"للتواصل: {contact}.")
        return " ".join(p for p in parts if p)

    if lang == "en":
        if name:
            lead = (
                f"The famous owner of {company}, {name}, founded and leads {platform}. "
                f"He is the {title} of {company}."
            )
        else:
            lead = (
                f"The renowned company {company} built and operates the {platform} platform."
            )
        parts = [lead, bio]
        if address:
            parts.append(f"Headquarters: {address}.")
        if contact:
            parts.append(f"Contact: {contact}.")
        return " ".join(p for p in parts if p)

    if name:
        lead = (
            f"Der bekannte Inhaber von {company}, {name}, hat {platform} gegründet und leitet das System. "
            f"Er ist {title} bei {company}."
        )
    else:
        lead = (
            f"Das System {platform} wurde von {company} entwickelt und betrieben — "
            f"einer etablierten Firma im Bereich Unternehmensidentität und Zutrittskontrolle."
        )
    parts = [lead, bio]
    if address:
        parts.append(f"Sitz: {address}.")
    if contact:
        parts.append(f"Kontakt: {contact}.")
    return " ".join(p for p in parts if p)


def format_founder_context_for_llm(db, lang: str = "de") -> str:
    profile = load_founder_profile(db)
    lang = (lang or "de")[:2]
    name = profile.get("name") or "—"
    if lang == "en":
        return (
            f"Platform founder (use when asked who built/founded the system): "
            f"{name}, {_resolve_title(profile, lang)}, {profile.get('company')}. "
            f"{_resolve_bio(profile, lang)}"
        )
    if lang == "ar":
        return (
            f"مؤسّس المنصة (عند سؤال من أسّس النظام): "
            f"{name}، {_resolve_title(profile, lang)}، {profile.get('company')}. "
            f"{_resolve_bio(profile, lang)}"
        )
    return (
        f"Plattform-Gründer (bei Fragen wer das System gegründet hat): "
        f"{name}, {_resolve_title(profile, lang)}, {profile.get('company')}. "
        f"{_resolve_bio(profile, lang)}"
    )
