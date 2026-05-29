"""Enterprise runtime flags — no demo/mock surfaces in hosted production by default."""
from __future__ import annotations

import os
from typing import Any


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def demo_features_allowed() -> bool:
    """Demo seed/UI only when explicitly allowed or local dev (not Railway/Render prod)."""
    if _env_flag("BAUPASS_ALLOW_DEMO"):
        return True
    if os.getenv("BAUPASS_ALLOW_DEMO", "").strip().lower() in {"0", "false", "no", "off"}:
        return False
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RENDER") or os.getenv("PUBLIC_BASE_URL"):
        return False
    env = (
        os.getenv("BAUPASS_ENV") or os.getenv("FLASK_ENV") or os.getenv("RAILWAY_ENVIRONMENT") or ""
    ).strip().lower()
    if env in {"production", "prod", "staging"}:
        return False
    return True


def copilot_configured() -> bool:
    return bool((os.getenv("OPENAI_API_KEY") or "").strip())


def enterprise_runtime_flags() -> dict[str, Any]:
    from backend.app.core.cloud_profile import get_cloud_profile

    cloud = get_cloud_profile()
    return {
        "demoAllowed": demo_features_allowed(),
        "copilotConfigured": copilot_configured(),
        "environment": cloud.get("environment") or "production",
        "provider": cloud.get("provider") or "generic",
    }
