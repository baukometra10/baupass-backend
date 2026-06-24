"""Default customer-facing platform branding (tenant overrides per company)."""
from __future__ import annotations

from backend.app.core.platform_env import DEFAULT_PLATFORM_EMAIL, platform_env

PLATFORM_DISPLAY_NAME = platform_env("PLATFORM_DISPLAY_NAME", "WorkPass") or "WorkPass"
OPERATOR_DISPLAY_NAME = platform_env("OPERATOR_DISPLAY_NAME", "Suppix AI") or "Suppix AI"
