"""Company branding for Einsatzplan PDFs (logo, colors, sector preset)."""
from __future__ import annotations

import base64
import io
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

BRANDING_DIR = Path(__file__).resolve().parents[4] / "branding"


def _default_logo_data_url() -> str:
    for name in ("suppix-ai-invoice.svg", "suppix-ai-logo.svg", "suppix-ai-mark.svg"):
        path = BRANDING_DIR / name
        if not path.is_file():
            continue
        try:
            svg = path.read_text(encoding="utf-8")
            return f"data:image/svg+xml;charset=utf-8,{quote(svg)}"
        except OSError:
            continue
    return ""

PRESET_THEMES: dict[str, dict[str, str]] = {
    "construction": {
        "accent": "#06b6d4",
        "accent_light": "#22d3ee",
        "sector_de": "Bau & Handwerk",
    },
    "industry": {
        "accent": "#1e3a5f",
        "accent_light": "#2563eb",
        "sector_de": "Industrie",
    },
    "premium": {
        "accent": "#2d1b4e",
        "accent_light": "#7c3aed",
        "sector_de": "Premium",
    },
}


def _normalize_preset(value: str) -> str:
    preset = str(value or "").strip().lower()
    return preset if preset in PRESET_THEMES else "construction"


def merge_pdf_branding_override(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if not override:
        return base
    merged = dict(base)
    for key in ("companyName", "logoData", "accent", "accentLight", "preset", "sectorLabel"):
        value = override.get(key)
        if value is not None and str(value).strip() != "":
            merged[key] = value
    return merged


def resolve_company_pdf_branding(db, company_id: str) -> dict[str, Any]:
    """Logo + colors for deployment PDF header."""
    company = db.execute(
        """
        SELECT name, portal_display_name, branding_logo_data, branding_accent_color, branding_preset
        FROM companies WHERE id = ?
        """,
        (str(company_id),),
    ).fetchone()
    settings = db.execute(
        "SELECT invoice_logo_data, platform_name, invoice_primary_color FROM settings WHERE id = 1"
    ).fetchone()

    preset = _normalize_preset(company["branding_preset"] if company else "construction")
    theme = PRESET_THEMES[preset]

    accent = str(company["branding_accent_color"] if company else "").strip().lower()
    if not re.match(r"^#[0-9a-f]{6}$", accent):
        accent = theme["accent"]

    logo_data = ""
    if company and str(company["branding_logo_data"] or "").strip():
        logo_data = str(company["branding_logo_data"]).strip()
    elif settings and str(settings["invoice_logo_data"] or "").strip():
        logo_data = str(settings["invoice_logo_data"]).strip()
    if not logo_data:
        logo_data = _default_logo_data_url()

    display_name = ""
    if company:
        display_name = str(company["portal_display_name"] or company["name"] or "").strip()
    if not display_name and settings:
        display_name = str(settings["platform_name"] or "WorkPass").strip()

    return {
        "companyName": display_name or "WorkPass",
        "logoData": logo_data,
        "accent": accent,
        "accentLight": theme["accent_light"],
        "preset": preset,
        "sectorLabel": theme["sector_de"],
    }


def logo_image_flowable(logo_data: str, *, max_height_mm: float = 18.0):
    """Reportlab Image from data-URL or None."""
    raw = str(logo_data or "").strip()
    if not raw.lower().startswith("data:image/"):
        return None
    try:
        from reportlab.lib.units import mm
        from reportlab.platypus import Image

        _header, payload = raw.split(",", 1)
        blob = base64.b64decode(payload, validate=False)
        if not blob:
            return None
        bio = io.BytesIO(blob)
        img = Image(bio)
        max_h = max_height_mm * mm
        if img.imageHeight > max_h:
            ratio = max_h / float(img.imageHeight)
            img.drawWidth = img.imageWidth * ratio
            img.drawHeight = max_h
        return img
    except Exception:
        return None
