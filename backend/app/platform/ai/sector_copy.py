"""Apply company operating-sector vocabulary to AI operator copy."""
from __future__ import annotations

from typing import Any


def sector_vocab(terms: dict[str, str] | None, lang: str = "de") -> tuple[str, str, str]:
    """Return (workers, site, gate) nouns for the company sector."""
    lang = (lang or "de")[:2]
    defaults = {
        "de": ("Mitarbeiter", "Standort", "Tor"),
        "en": ("workers", "site", "gate"),
        "ar": ("عمال", "موقع", "بوابة"),
        "tr": ("çalışanlar", "saha", "kapı"),
        "fr": ("collaborateurs", "site", "porte"),
        "es": ("trabajadores", "obra", "acceso"),
        "it": ("lavoratori", "cantiere", "varco"),
        "pl": ("pracownicy", "teren", "brama"),
    }
    w_fb, s_fb, g_fb = defaults.get(lang, defaults["en"])
    workers = str((terms or {}).get("termWorkers") or w_fb).strip() or w_fb
    site = str((terms or {}).get("termSite") or s_fb).strip() or s_fb
    gate = str((terms or {}).get("termGate") or g_fb).strip() or g_fb
    return workers, site, gate


def apply_sector_text(text: str, *, workers: str, site: str, lang: str = "de") -> str:
    """Rewrite construction defaults to company sector nouns."""
    if not text:
        return text
    out = str(text)
    # German construction defaults used across templates
    out = out.replace("Baustellen", site).replace("Baustelle", site)
    out = out.replace("Mitarbeiter", workers)
    out = out.replace("vor Ort", f"am {site}" if lang == "de" else f"at {site}")
    code = (lang or "de")[:2]
    if code == "en":
        out = out.replace("on site", f"at {site}").replace("On site", f"At {site}")
        out = out.replace("Who is on site", f"Who is at {site}")
        out = out.replace("workers", workers).replace("Workers", workers)
    elif code == "ar":
        out = out.replace("في الموقع", f"في {site}").replace("الموقع", site)
        out = out.replace("عمال", workers)
    elif code == "tr":
        out = out.replace("sahada", f"{site} üzerinde").replace("Sahada", f"{site} üzerinde")
        out = out.replace("budowie", site)
    elif code == "pl":
        out = out.replace("na budowie", f"na {site}").replace("budowie", site)
    elif code == "es":
        out = out.replace("en obra", f"en {site}").replace("obra", site)
    elif code == "it":
        out = out.replace("in cantiere", f"in {site}").replace("cantiere", site)
    elif code == "fr":
        out = out.replace("sur site", f"sur {site}").replace("Sur site", f"Sur {site}")
    return out


def load_company_sector_terms(db, company_id: str, *, lang: str = "de") -> dict[str, str]:
    try:
        from backend.app.platform.sector.catalog import sector_terms_for_company

        return sector_terms_for_company(db, company_id, lang=lang) or {}
    except Exception:
        return {}


def rewrite_pulse_pack(
    pack: dict[str, tuple[str, str]],
    *,
    workers: str,
    site: str,
    lang: str,
) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for key, (label, reason) in pack.items():
        out[key] = (
            apply_sector_text(label, workers=workers, site=site, lang=lang),
            apply_sector_text(reason, workers=workers, site=site, lang=lang),
        )
    return out


def rewrite_prompt_map(
    prompts: dict[str, str],
    *,
    workers: str,
    site: str,
    lang: str,
) -> dict[str, str]:
    return {
        k: apply_sector_text(v, workers=workers, site=site, lang=lang)
        for k, v in prompts.items()
    }


def sector_meta_payload(terms: dict[str, Any] | None, lang: str = "de") -> dict[str, str]:
    workers, site, gate = sector_vocab(terms, lang)
    return {
        "sector": str((terms or {}).get("_sector") or ""),
        "sectorLabel": str((terms or {}).get("_sectorLabel") or ""),
        "termWorkers": workers,
        "termSite": site,
        "termGate": gate,
    }
