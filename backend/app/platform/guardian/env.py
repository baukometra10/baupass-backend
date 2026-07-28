"""Guardian env helpers — SUPPIX_* preferred, BAUPASS_* legacy."""
from __future__ import annotations

from backend.app.core.platform_env import platform_env


def guardian_env(suffix: str, default: str = "") -> str:
    """Read SUPPIX_GUARDIAN_{suffix} / BAUPASS_GUARDIAN_{suffix}."""
    return platform_env(f"GUARDIAN_{suffix}", default)


def guardian_flag(suffix: str, default: str = "1") -> bool:
    return guardian_env(suffix, default).strip().lower() not in {"0", "false", "no", "off"}


def guardian_int(suffix: str, default: int, *, minimum: int = 0) -> int:
    raw = guardian_env(suffix, str(default))
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        return max(minimum, default)
