"""Access domain service."""
from __future__ import annotations

from .repository import AccessRepository


class AccessService:
    def __init__(self) -> None:
        self.repo = AccessRepository()

    def live_access_feed(self, db, company_id: str) -> dict:
        return {"access_logs": self.repo.recent_logs(db, company_id, limit=30)}

    def geofence_zones(self, db, company_id: str) -> dict:
        return {"zones": self.repo.list_geofences(db, company_id)}
