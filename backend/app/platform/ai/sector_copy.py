"""Apply company operating-sector vocabulary to AI operator and ops copy."""
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


def _title(value: str) -> str:
    if not value:
        return value
    return value[:1].upper() + value[1:]


def apply_sector_text(
    text: str,
    *,
    workers: str,
    site: str,
    lang: str = "de",
    gate: str = "",
    worker_singular: str = "",
    company: str = "",
    sites: str = "",
) -> str:
    """Rewrite construction defaults to company sector nouns."""
    if not text:
        return text
    out = str(text)
    code = (lang or "de")[:2]
    gate = (gate or "").strip()
    singular = (worker_singular or "").strip() or workers
    company = (company or "").strip()
    sites = (sites or "").strip() or site

    # German construction defaults used across templates (longest forms first)
    if code == "de":
        out = out.replace("Baustellenkontrolle", site + "-Kontrolle")
        out = out.replace("Baustellen-Ausweis", f"{site}-Ausweis")
        out = out.replace("Baustellenordnung", f"{site}ordnung")
        out = out.replace("Auf allen Baustellen", f"In allen {sites}")
        out = out.replace("auf allen Baustellen", f"in allen {sites}")
        out = out.replace("Auf der Baustelle", f"Am {site}")
        out = out.replace("auf der Baustelle", f"am {site}")
        out = out.replace("Auf Baustelle", f"Am {site}")
        out = out.replace("auf Baustelle", f"am {site}")
        if company:
            out = out.replace("Bauunternehmen", company)
            out = out.replace("Baufirma", company)
            out = out.replace("Baubetrieb", company)
        out = out.replace("Bauleitung", "Einsatzleitung")
        out = out.replace("Baustellen", sites).replace("Baustelle", site)
        out = out.replace("Mitarbeiter-App", f"{singular}-App")
        out = out.replace("Mitarbeiter", workers)
        out = out.replace("vor Ort", f"am {site}")
        if gate:
            out = out.replace("Drehkreuz / Tor", gate).replace("Drehkreuz", gate)
            out = out.replace("am Tor", f"am {gate}").replace("Am Tor", f"Am {gate}")
            out = out.replace(" Tor/", f" {gate}/").replace(" Tor ", f" {gate} ")
            out = out.replace("Tor=", f"{gate}=").replace("(Tor)", f"({gate})")
            if out.endswith(" Tor"):
                out = out[: -len(" Tor")] + f" {gate}"
            if out.startswith("Tor ") or out.startswith("Tor/"):
                out = gate + out[3:]
        # Common short labels
        out = out.replace("Fehlende MA", f"Fehlende {workers}")
        out = out.replace("Dokument an Mitarbeiter", f"Dokument an {workers}")
    elif code == "en":
        if company:
            out = out.replace("construction companies", company if company.endswith("s") else company + "s")
            out = out.replace("Construction companies", _title(company if company.endswith("s") else company + "s"))
            out = out.replace("construction company", company)
            out = out.replace("Construction company", _title(company))
        out = out.replace("construction sites", sites)
        out = out.replace("Construction sites", _title(sites))
        out = out.replace("construction site", site).replace("Construction site", _title(site))
        out = out.replace("on site", f"at {site}").replace("On site", f"At {site}")
        out = out.replace("Who is on site", f"Who is at {site}")
        out = out.replace("Workers", _title(workers))
        out = out.replace("workers", workers)
        out = out.replace("Worker", _title(singular))
        out = out.replace("worker", singular)
        if gate:
            out = out.replace("turnstile", gate).replace("Turnstile", _title(gate))
            out = out.replace(" gate", f" {gate}").replace("Gate/", f"{gate}/")
    elif code == "ar":
        if company:
            out = out.replace("شركة إنشاءات باوشتلا", company)
            out = out.replace("شركات البناء", company)
            out = out.replace("شركة إنشاءات", company)
            out = out.replace("شركة بناء", company)
        out = out.replace("مواقع البناء", sites)
        out = out.replace("موقع البناء", site)
        out = out.replace("باوشتلا", site)
        out = out.replace("في الموقع", f"في {site}").replace("الموقع", site)
        out = out.replace("العمال", workers).replace("عمال", workers)
        if gate:
            out = out.replace("البوابة", gate).replace("بوابة", gate)
    elif code == "tr":
        if company:
            out = out.replace("inşaat firmaları", company)
            out = out.replace("inşaat firması", company)
            out = out.replace("İnşaat Firması", _title(company))
        out = out.replace("sahada", f"{site} üzerinde").replace("Sahada", f"{site} üzerinde")
        out = out.replace("şantiyede", f"{site} üzerinde")
        out = out.replace("şantiye", site).replace("çalışanlar", workers)
    elif code == "pl":
        if company:
            out = out.replace("firmom budowlanym", company)
            out = out.replace("firma budowlana", company)
            out = out.replace("firmę budowlaną", company)
        out = out.replace("na budowie", f"na {site}").replace("placu budowy", site)
        out = out.replace("budowie", site)
        out = out.replace("pracownicy", workers)
    elif code == "es":
        if company:
            out = out.replace("empresas de construcción", company)
            out = out.replace("empresa de construcción", company)
        out = out.replace("en la obra", f"en {site}").replace("en obra", f"en {site}")
        out = out.replace("obra", site)
        out = out.replace("trabajadores", workers)
    elif code == "it":
        if company:
            out = out.replace("imprese edili", company)
            out = out.replace("impresa edile", company)
        out = out.replace("in cantiere", f"in {site}").replace("cantiere", site)
        out = out.replace("lavoratori", workers)
    elif code == "fr":
        if company:
            out = out.replace("entreprises de construction", company)
            out = out.replace("entreprise de construction", company)
        out = out.replace("sur chantier", f"sur {site}").replace("Sur chantier", f"Sur {site}")
        out = out.replace("chantier", site)
        out = out.replace("sur site", f"sur {site}").replace("Sur site", f"Sur {site}")
        out = out.replace("collaborateurs", workers)
    return out


def load_company_sector_terms(db, company_id: str, *, lang: str = "de") -> dict[str, str]:
    try:
        from backend.app.platform.sector.catalog import sector_terms_for_company

        return sector_terms_for_company(db, company_id, lang=lang) or {}
    except Exception:
        return {}


def rewrite_text_for_company(db, company_id: str, text: str, *, lang: str = "de") -> str:
    """Convenience: load sector terms and rewrite one string."""
    if not text or not company_id:
        return text
    terms = load_company_sector_terms(db, company_id, lang=lang)
    workers, site, gate = sector_vocab(terms, lang)
    singular = str(terms.get("termWorker") or "").strip()
    company = str(terms.get("termCompany") or "").strip()
    sites = str(terms.get("termSites") or "").strip()
    return apply_sector_text(
        text,
        workers=workers,
        site=site,
        gate=gate,
        worker_singular=singular,
        company=company,
        sites=sites,
        lang=lang,
    )


def apply_sector_to_inbox_items(
    db,
    company_id: str,
    items: list[dict[str, Any]],
    *,
    lang: str = "de",
) -> list[dict[str, Any]]:
    """Rewrite inbox titles/messages/action labels for the company sector."""
    if not company_id or not items:
        return items
    terms = load_company_sector_terms(db, company_id, lang=lang)
    workers, site, gate = sector_vocab(terms, lang)
    singular = str(terms.get("termWorker") or "").strip()
    company = str(terms.get("termCompany") or "").strip()
    sites = str(terms.get("termSites") or "").strip()

    def _rw(value: Any) -> Any:
        if not isinstance(value, str) or not value.strip():
            return value
        return apply_sector_text(
            value,
            workers=workers,
            site=site,
            gate=gate,
            worker_singular=singular,
            company=company,
            sites=sites,
            lang=lang,
        )

    out: list[dict[str, Any]] = []
    for raw in items:
        item = dict(raw)
        item["title"] = _rw(item.get("title"))
        item["message"] = _rw(item.get("message"))
        details = item.get("details")
        if isinstance(details, dict):
            details = dict(details)
            if details.get("reasonSummary"):
                details["reasonSummary"] = _rw(details.get("reasonSummary"))
            item["details"] = details
        actions = item.get("actions")
        if isinstance(actions, list):
            new_actions = []
            for act in actions:
                if not isinstance(act, dict):
                    new_actions.append(act)
                    continue
                a = dict(act)
                if a.get("label"):
                    a["label"] = _rw(a["label"])
                if a.get("prompt"):
                    a["prompt"] = _rw(a["prompt"])
                new_actions.append(a)
            item["actions"] = new_actions
        out.append(item)
    return out


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
