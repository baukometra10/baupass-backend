"""Tests for market-aligned pricing and billing helpers."""
from __future__ import annotations

import sqlite3
from unittest.mock import patch

from backend.app.platform.pricing import (
    PLAN_NET_PRICE_EUR,
    calculate_monthly_net,
    pricing_catalog,
)


def test_plan_prices_are_market_aligned_not_legacy_flat():
    assert PLAN_NET_PRICE_EUR["starter"] == 69.0
    assert PLAN_NET_PRICE_EUR["professional"] == 249.0
    assert PLAN_NET_PRICE_EUR["enterprise"] == 599.0
    assert PLAN_NET_PRICE_EUR["professional"] < 999.0


def test_calculate_monthly_net_includes_worker_overage():
    quote = calculate_monthly_net("starter", worker_count=15)
    assert quote["baseEur"] == 69.0
    assert quote["billableWorkers"] == 5
    assert quote["totalNetEur"] == round(69.0 + 5 * 5.99, 2)


def test_pricing_catalog_exposes_all_plans():
    catalog = pricing_catalog()
    plan_ids = [p["plan"] for p in catalog["plans"]]
    assert plan_ids == ["tageskarte", "starter", "professional", "enterprise"]


def test_webhook_idempotency_skips_duplicate_event():
    from backend.app.domains.billing import stripe_service

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE companies (
            id TEXT PRIMARY KEY, name TEXT, plan TEXT, status TEXT,
            billing_email TEXT, contact TEXT, trial_ends_at TEXT,
            stripe_customer_id TEXT, stripe_subscription_id TEXT,
            stripe_subscription_status TEXT, billing_cycle TEXT
        );
        CREATE TABLE invoices (
            id TEXT PRIMARY KEY, invoice_number TEXT, company_id TEXT,
            status TEXT, paid_at TEXT, payment_note TEXT, total_amount REAL,
            last_reminder_error TEXT, auto_suspend_triggered_at TEXT
        );
        CREATE TABLE stripe_billing_events (id TEXT PRIMARY KEY, event_type TEXT, processed_at TEXT);
        """
    )
    db.execute(
        "INSERT INTO companies (id, name, plan, status, billing_email, contact, trial_ends_at, billing_cycle) VALUES ('c1','Test','starter','aktiv','a@b.de','','','monthly')"
    )
    event = {"id": "evt_1", "type": "customer.subscription.deleted", "data": {"object": {"metadata": {"company_id": "c1"}}}}
    with patch("backend.app.platform.events.bus.publish_event"):
        first = stripe_service.handle_webhook_event(db, event)
        second = stripe_service.handle_webhook_event(db, event)
    assert first.get("duplicate") is not True
    assert second.get("duplicate") is True
