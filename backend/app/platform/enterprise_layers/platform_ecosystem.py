"""
Platform Ecosystem Layer — APIs, SDK, plugins, marketplace.
"""
from __future__ import annotations

import os
from typing import Any


def build_platform_ecosystem_layer() -> dict[str, Any]:
    return {
        "layer": "platform_ecosystem",
        "status": "active",
        "public_api": {
            "versions": ["v1", "v2"],
            "health": "/api/v1/public/health",
            "docs": "/api/marketplace/apis",
        },
        "developer": {
            "api_keys": "/api/developer/api-keys",
            "webhooks": "/api/developer/webhooks",
        },
        "sdk": {
            "python": "sdk/baupass_client.py",
            "install": "copy sdk/baupass_client.py into your project",
        },
        "marketplace": {
            "plugins": "/api/marketplace/plugins",
            "apis": "/api/marketplace/apis",
            "sandbox": "/api/marketplace/plugins/sandbox-policy",
        },
        "plugin_architecture": True,
        "extensions_enabled": os.getenv("BAUPASS_PLATFORM_ENABLED", "1") not in {"0", "false", "no"},
    }
