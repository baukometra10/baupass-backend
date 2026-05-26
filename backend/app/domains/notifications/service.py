"""Notifications domain service."""
from __future__ import annotations

from .repository import NotificationsRepository


class NotificationsService:
    def __init__(self) -> None:
        self.repo = NotificationsRepository()

    def inbox(self, db, company_id: str) -> dict:
        try:
            items = self.repo.list_for_company(db, company_id)
        except Exception:
            items = []
        return {"notifications": items}
