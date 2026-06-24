"""Canonical SUPPIX_* environment variables with BAUPASS_* legacy mirror."""
from __future__ import annotations

import os

CANONICAL_PREFIX = "SUPPIX_"
LEGACY_PREFIX = "BAUPASS_"
DEFAULT_PLATFORM_EMAIL = "suppix-workpass-ai@outlook.de"
_MIRRORED = False


def mirror_platform_env() -> None:
    """Expose each platform env under both SUPPIX_* and BAUPASS_* (SUPPIX wins)."""
    global _MIRRORED
    if _MIRRORED:
        return

    suffixes: set[str] = set()
    for key in os.environ:
        if key.startswith(CANONICAL_PREFIX):
            suffixes.add(key[len(CANONICAL_PREFIX) :])
        elif key.startswith(LEGACY_PREFIX):
            suffixes.add(key[len(LEGACY_PREFIX) :])

    for suffix in suffixes:
        canonical = f"{CANONICAL_PREFIX}{suffix}"
        legacy = f"{LEGACY_PREFIX}{suffix}"
        canonical_val = (os.environ.get(canonical) or "").strip()
        legacy_val = (os.environ.get(legacy) or "").strip()
        if canonical_val:
            os.environ[canonical] = canonical_val
            os.environ[legacy] = canonical_val
        elif legacy_val:
            os.environ[legacy] = legacy_val
            os.environ[canonical] = legacy_val

    _MIRRORED = True


def platform_env(suffix: str, default: str = "") -> str:
    """Read SUPPIX_{suffix}, then BAUPASS_{suffix}."""
    mirror_platform_env()
    for prefix in (CANONICAL_PREFIX, LEGACY_PREFIX):
        raw = os.environ.get(f"{prefix}{suffix}")
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return default


def default_noreply_email() -> str:
    """Sender fallback for outbound mail — never baupass.*."""
    mirror_platform_env()
    for key in (
        "SMTP_SENDER_EMAIL",
        f"{CANONICAL_PREFIX}CONTACT_EMAIL",
        f"{LEGACY_PREFIX}CONTACT_EMAIL",
        f"{CANONICAL_PREFIX}DEFAULT_NOREPLY_EMAIL",
        f"{LEGACY_PREFIX}DEFAULT_NOREPLY_EMAIL",
    ):
        value = (os.environ.get(key) or "").strip()
        if value and "@" in value and "baupass" not in value.lower():
            return value
    custom = platform_env("DEFAULT_NOREPLY_EMAIL", "")
    if custom and "@" in custom:
        return custom
    return DEFAULT_PLATFORM_EMAIL
