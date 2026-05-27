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
        live = self._access.live_access_feed(db, company_id)
        zones = self._access.geofence_zones(db, company_id)
        return {
            "workforce": {
                "onSite": workforce.get("on_site", 0),
                "totalActive": workforce.get("total_active", 0),
            },
            "recentAccess": live.get("access_logs", []),
            "zonesCount": len(zones.get("zones") or []),
        }
