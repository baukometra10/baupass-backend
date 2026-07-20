"""Admin dashboard aggregates (v2)."""
from __future__ import annotations

from ..access.service import AccessService
from ..workers.service import WorkersService


class AdminService:
    def __init__(self) -> None:
        self._workers = WorkersService()
        self._access = AccessService()

    def overview(self, db, company_id: str, today_prefix: str) -> dict:
        workforce = self._workers.workforce_tracking(db, company_id, today_prefix)
        latest = self._access.latest_access_per_worker(db, company_id)
        zones = self._access.geofence_zones(db, company_id)
        forecast = {}
        try:
            from backend.app.platform.predictions.engine import build_tomorrow_forecast

            forecast = build_tomorrow_forecast(db, company_id)
        except Exception:
            pass
        return {
            "workforce": {
                "onSite": workforce.get("on_site", 0),
                "totalActive": workforce.get("total_active", 0),
            },
            "recentAccess": latest.get("access_logs", []),
            "zonesCount": len(zones.get("zones") or []),
            "tomorrowForecast": forecast,
        }
