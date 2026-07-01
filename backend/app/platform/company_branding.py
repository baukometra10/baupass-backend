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


BRANDING_LOGO_MAX_LEN = 180_000


def validate_branding_logo_data(value: str, *, max_len: int = BRANDING_LOGO_MAX_LEN) -> tuple[str, str | None]:
    """Return (normalized_value, error_code). error_code is logo_too_large or logo_invalid_format."""
    raw = str(value or "").strip()
    if not raw:
        return "", None
    lowered = raw.lower()
    if not (
        lowered.startswith("data:image/")
        or lowered.startswith("http://")
        or lowered.startswith("https://")
    ):
        return "", "logo_invalid_format"
    if len(raw) > max_len:
        return "", "logo_too_large"
    return raw, None


def normalize_branding_logo_data(value: str, *, max_len: int = BRANDING_LOGO_MAX_LEN) -> str:
    normalized, _error = validate_branding_logo_data(value, max_len=max_len)
    return normalized


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

    portal = _get("portal_display_name")
    if not portal and "name" in keys:
        portal = _get("name")
    return {
        "portalDisplayName": portal,
        "brandingAccentColor": _get("branding_accent_color"),
        "brandingLogoData": _get("branding_logo_data"),
    }
