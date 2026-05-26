"""Workers domain — business logic."""
from __future__ import annotations

from .repository import WorkersRepository


class WorkersService:
    def __init__(self) -> None:
        self.repo = WorkersRepository()

    def list_workers(self, db, company_id: str) -> list[dict]:
        return self.repo.list_active(db, company_id)

    def workforce_tracking(self, db, company_id: str, today_prefix: str) -> dict:
        on_site = self.repo.count_on_site_today(db, company_id, today_prefix)
        workers = self.repo.list_active(db, company_id, limit=1000)
        return {
            "on_site": on_site,
            "total_active": len(workers),
            "workers": workers[:50],
        }
