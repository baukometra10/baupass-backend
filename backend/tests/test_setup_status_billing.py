"""Setup-status billing block — Stripe readiness without exposing secrets."""
from __future__ import annotations

from unittest.mock import patch

from backend.app.platform.setup_status import collect_setup_status


def test_billing_block_reports_stripe_readiness_fields():
    with patch.dict(
        "os.environ",
        {
            "STRIPE_SECRET_KEY": "sk_test_x",
            "STRIPE_WEBHOOK_SECRET": "whsec_x",
            "STRIPE_PRICE_STARTER": "price_starter",
            "STRIPE_PRICE_PROFESSIONAL": "price_pro",
            "STRIPE_PRICE_ENTERPRISE": "price_ent",
            "PUBLIC_BASE_URL": "https://example.test",
        },
        clear=False,
    ):
        status = collect_setup_status()
    billing = status.get("billing") or {}
    assert billing.get("stripe") is True
    assert billing.get("stripeWebhook") is True
    assert billing.get("stripePricesConfigured") is True
    assert billing.get("readyForCheckout") is True
    assert billing.get("readyForWebhooks") is True
    assert "/api/billing/stripe/webhook" in str(billing.get("webhookUrl") or "")


def test_cameras_block_present():
    status = collect_setup_status()
    cameras = status.get("cameras") or {}
    assert "rtspBridgeToken" in cameras
    assert "docs" in cameras
