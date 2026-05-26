"""Billing domain service."""
from __future__ import annotations

from .repository import BillingRepository


class BillingService:
    def __init__(self) -> None:
        self.repo = BillingRepository()

    def subscription_overview(self, db, company_id: str) -> dict:
        from backend.server import get_company_plan, get_plan_features

        plan = get_company_plan(db, company_id)
        return {
            "plan": plan,
            "features": get_plan_features(plan),
            "invoices": self.repo.invoice_summary(db, company_id),
            "recent": self.repo.recent_invoices(db, company_id),
        }
