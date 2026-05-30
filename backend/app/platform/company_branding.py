"""Per-tenant white-label fields on companies."""
from __future__ import annotations

import re
from typing import Any

_ACCENT_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def normalize_branding_accent(value: str) -> str:
    raw = str(value or "").strip()
    return raw.lower() if _ACCENT_RE.match(raw) else ""


def normalize_portal_display_name(value: str, *, max_len: int = 80) -> str:
    return str(value or "").strip()[:max_len]


def normalize_branding_logo_data(value: str, *, max_len: int = 180_000) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) > max_len:
        raw = raw[:max_len]
    lowered = raw.lower()
    if lowered.startswith("data:image/") or lowered.startswith("http://") or lowered.startswith("https://"):
        return raw
    return ""


def company_white_label_from_row(row: Any) -> dict[str, str]:
    if not row:
        return {
            "portalDisplayName": "",
            "brandingAccentColor": "",
            "brandingLogoData": "",
        }
    keys = row.keys() if hasattr(row, "keys") else []

    def _get(col: str) -> str:
        if col not in keys:
            return ""
        return str(row[col] or "").strip()

    return {
        "portalDisplayName": _get("portal_display_name"),
        "brandingAccentColor": _get("branding_accent_color"),
        "brandingLogoData": _get("branding_logo_data"),
    }
