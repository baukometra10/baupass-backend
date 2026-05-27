"""
Cloud / region profile for global deployments (Railway, Render, Docker, K8s).
"""
from __future__ import annotations

import os
import socket
from typing import Any


def _detect_provider() -> str:
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_GIT_COMMIT_SHA"):
        return "railway"
    if os.getenv("RENDER"):
        return "render"
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        return "kubernetes"
    if os.getenv("AWS_EXECUTION_ENV") or os.getenv("AWS_REGION"):
        return "aws"
    if os.getenv("AZURE_FUNCTIONS_ENVIRONMENT") or os.getenv("WEBSITE_SITE_NAME"):
        return "azure"
    if os.getenv("GOOGLE_CLOUD_PROJECT"):
        return "gcp"
    if os.getenv("FLY_APP_NAME"):
        return "fly"
    return "generic"


def get_cloud_profile() -> dict[str, Any]:
    """Runtime profile exposed in health and logs (no secrets)."""
    region = (
        os.getenv("BAUPASS_REGION")
        or os.getenv("RAILWAY_REPLICA_REGION")
        or os.getenv("AWS_REGION")
        or os.getenv("AZURE_REGION")
        or os.getenv("GOOGLE_CLOUD_REGION")
        or ""
    ).strip()
    raw_regions = (os.getenv("BAUPASS_ACTIVE_REGIONS") or "").strip()
    active_regions = [r.strip() for r in raw_regions.split(",") if r.strip()]
    strategy = (os.getenv("BAUPASS_REGION_STRATEGY") or "single").strip().lower()
    return {
        "provider": _detect_provider(),
        "region": region or "unknown",
        "activeRegions": active_regions or ([region] if region else []),
        "regionStrategy": strategy,
        "timezone": os.getenv("BAUPASS_DEFAULT_TIMEZONE", "UTC").strip() or "UTC",
        "hostname": socket.gethostname(),
        "environment": (
            os.getenv("BAUPASS_ENV")
            or os.getenv("RAILWAY_ENVIRONMENT")
            or os.getenv("FLASK_ENV")
            or "production"
        ).strip(),
        "gitCommit": (
            os.getenv("RAILWAY_GIT_COMMIT_SHA")
            or os.getenv("RENDER_GIT_COMMIT")
            or os.getenv("GIT_COMMIT")
            or ""
        ).strip(),
        "publicBaseUrl": (os.getenv("PUBLIC_BASE_URL") or "").strip(),
    }
