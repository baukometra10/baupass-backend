"""
Operational Experience Layer — UX / performance / real-time posture.
"""
from __future__ import annotations

import os
from typing import Any


def build_operational_experience_layer() -> dict[str, Any]:
    from backend.app.platform.realtime.websocket import websocket_status

    return {
        "layer": "operational_experience",
        "status": "active",
        "mobile_first": {
            "pwa": "/emp-app.html",
            "hybrid_flutter": "mobile/",
            "distribution": "/api/v2/mobile/distribution",
        },
        "design_system": "/design-tokens.css",
        "real_time": {
            "websocket": websocket_status(),
            "sse": "/api/v1/stream/events",
            "live_dashboard": "/api/dashboard/live",
        },
        "performance": {
            "edge_timing_header": True,
            "api_cache_control": "no-store",
            "pwa_shell_cache_seconds": int(os.getenv("BAUPASS_PWA_SHELL_CACHE_SECONDS", "300")),
        },
        "ux_principles": [
            "instant_feedback",
            "minimal_taps",
            "offline_worker_queue",
            "qr_fast_login",
        ],
    }
