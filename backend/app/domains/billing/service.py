"""Billing domain service."""
from __future__ import annotations

from .repository import BillingRepository
from . import stripe_service


class BillingService:
    def __init__(self) -> None:
        self.repo = BillingRepository()

    def subscription_overview(self, db, company_id: str) -> dict:
        return stripe_service.subscription_overview(db, company_id)

    def revenue_metrics(self, db) -> dict:
        return stripe_service.revenue_metrics(db)
