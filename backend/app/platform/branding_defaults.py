"""Default customer-facing platform branding (tenant overrides per company)."""
from __future__ import annotations

import os

PLATFORM_DISPLAY_NAME = (
    os.getenv("BAUPASS_PLATFORM_DISPLAY_NAME", "SUPPIX").strip() or "SUPPIX"
)
OPERATOR_DISPLAY_NAME = (
    os.getenv("BAUPASS_OPERATOR_DISPLAY_NAME", "Suppix Technologie UG").strip()
    or "Suppix Technologie UG"
)
