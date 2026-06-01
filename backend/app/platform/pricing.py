"""
Market-aligned SaaS pricing for BauPass (DE construction workforce + access control).

Benchmarks (2025–2026):
- Crewly: 49 €/mo + 4,99 €/worker (10 incl.) — attendance, NFC, DATEV
- 123erfasst: 7–12 €/user/mo — personnel/time modules
- Ditio: ~17 €/active user/mo — construction ERP-lite
- Access control cloud: 3,50–15 €/door/mo

BauPass bundles access control, badges (QR/NFC/Wallet), worker app, invoicing, dunning,
real-time ops and enterprise integrations — priced at a fair premium over point solutions,
not below commodity trackers and not at legacy flat-rate extremes.
"""
from __future__ import annotations

from typing import Any

PLAN_ORDER = ("tageskarte", "starter", "professional", "enterprise")

# Monthly net base fee (EUR, excl. VAT)
PLAN_NET_PRICE_EUR: dict[str, float] = {
    "tageskarte": 29.0,       # per day / short-term site
    "starter": 69.0,
    "professional": 249.0,
    "enterprise": 599.0,
}

# Per active worker beyond included quota (EUR/mo, excl. VAT)
PLAN_WORKER_PRICE_EUR: dict[str, float] = {
    "tageskarte": 0.0,
    "starter": 5.99,
    "professional": 7.50,
    "enterprise": 9.50,
}

PLAN_WORKER_FREE_INCLUDED: dict[str, int] = {
    "tageskarte": 0,
    "starter": 10,
    "professional": 25,
    "enterprise": 50,
}

# Annual prepay: ~2 months free on base fee
ANNUAL_DISCOUNT_PERCENT = 17.0

# Stripe Checkout trial for first subscription (days). Override: BAUPASS_STRIPE_TRIAL_DAYS=0 to disable.
DEFAULT_CHECKOUT_TRIAL_DAYS = 14


def checkout_trial_days() -> int:
    import os

    raw = (os.getenv("BAUPASS_STRIPE_TRIAL_DAYS") or "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return DEFAULT_CHECKOUT_TRIAL_DAYS

PLAN_MARKETING: dict[str, dict[str, Any]] = {
    "tageskarte": {
        "label": "Tageskarte",
        "labelAr": "بطاقة يومية",
        "priceEur": 29,
        "priceUnit": "day",
        "priceUnitAr": "يوم",
        "taglineDe": "Besucher & Kurzzeit-Zutritt",
        "taglineEn": "Visitors and short-term site access",
        "taglineAr": "زوار ودخول مؤقت للموقع",
        "benchmarkNoteDe": "Vergleich: Tages-Pass-Lösungen ab ~25 €/Tag",
    },
    "starter": {
        "label": "Starter",
        "labelAr": "مبتدئ",
        "priceEur": 69,
        "priceUnit": "month",
        "priceUnitAr": "شهر",
        "workersIncluded": 10,
        "workerOverageEur": 5.99,
        "taglineDe": "Worker-App, NFC, Urlaub — bis 10 MA inkl.",
        "taglineEn": "Worker app, NFC, leave — 10 workers included",
        "taglineAr": "تطبيق الموظف + NFC + إجازات — 10 موظفين مشمولين",
        "benchmarkNoteDe": "Vergleich: Crewly 49 € + 4,99 €/MA",
    },
    "professional": {
        "label": "Professional",
        "labelAr": "احترافي",
        "priceEur": 249,
        "priceUnit": "month",
        "priceUnitAr": "شهر",
        "workersIncluded": 25,
        "workerOverageEur": 7.50,
        "taglineDe": "Echtzeit, Automatisierung, Fakturierung & Mahnwesen",
        "taglineEn": "Real-time ops, automation, invoicing & dunning",
        "taglineAr": "تشغيل لحظي + أتمتة + فوترة + تذكيرات",
        "benchmarkNoteDe": "Vergleich: 123erfasst Pro ~12 €/MA",
    },
    "enterprise": {
        "label": "Enterprise",
        "labelAr": "مؤسسي",
        "priceEur": 599,
        "priceUnit": "month",
        "priceUnitAr": "شهر",
        "workersIncluded": 50,
        "workerOverageEur": 9.50,
        "taglineDe": "KI, Wallet-Pässe, Integrationen, Command Center",
        "taglineEn": "AI, wallet passes, integrations, command center",
        "taglineAr": "AI + محافظ رقمية + تكاملات + قيادة مركزية",
        "benchmarkNoteDe": "Vergleich: Enterprise-HR/Access ab ~500 €/Mo",
    },
}


def stripe_price_env_key(plan: str, *, annual: bool = False) -> str:
    suffix = "_ANNUAL" if annual else ""
    return f"STRIPE_PRICE_{plan.upper()}{suffix}"


def resolve_stripe_price_id(plan: str, *, annual: bool = False) -> str:
    import os

    key = stripe_price_env_key(plan, annual=annual)
    return (os.getenv(key) or os.getenv(f"STRIPE_PRICE_{plan.upper()}") or "").strip()


def calculate_monthly_net(plan: str, worker_count: int = 0, *, annual: bool = False) -> dict[str, Any]:
    normalized = str(plan or "starter").strip().lower()
    if normalized not in PLAN_NET_PRICE_EUR:
        normalized = "starter"
    base = float(PLAN_NET_PRICE_EUR[normalized])
    if annual and normalized != "tageskarte":
        base = round(base * (1 - ANNUAL_DISCOUNT_PERCENT / 100), 2)
    free = int(PLAN_WORKER_FREE_INCLUDED.get(normalized, 0))
    billable = max(0, int(worker_count or 0) - free)
    overage_rate = float(PLAN_WORKER_PRICE_EUR.get(normalized, 0.0))
    worker_fee = round(billable * overage_rate, 2)
    total = round(base + worker_fee, 2)
    return {
        "plan": normalized,
        "baseEur": base,
        "workersIncluded": free,
        "workerCount": int(worker_count or 0),
        "billableWorkers": billable,
        "workerOverageEur": overage_rate,
        "workerFeeEur": worker_fee,
        "totalNetEur": total,
        "annual": bool(annual),
        "annualDiscountPercent": ANNUAL_DISCOUNT_PERCENT if annual else 0,
    }


def pricing_catalog() -> dict[str, Any]:
    import os

    plans = []
    for plan in PLAN_ORDER:
        meta = dict(PLAN_MARKETING.get(plan, {}))
        meta["plan"] = plan
        meta["monthlyQuote"] = calculate_monthly_net(plan, worker_count=meta.get("workersIncluded") or 0)
        meta["stripePriceId"] = resolve_stripe_price_id(plan, annual=False)
        meta["stripePriceIdAnnual"] = resolve_stripe_price_id(plan, annual=True)
        plans.append(meta)
    return {
        "plans": plans,
        "planOrder": list(PLAN_ORDER),
        "annualDiscountPercent": ANNUAL_DISCOUNT_PERCENT,
        "checkoutTrialDays": checkout_trial_days(),
        "stripeConfigured": bool((os.getenv("STRIPE_SECRET_KEY") or "").strip()),
        "currency": "EUR",
        "vatNoteDe": "Alle Preise netto zzgl. 19 % MwSt.",
    }
