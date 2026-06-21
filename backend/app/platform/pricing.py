"""
Canonical WorkPass SaaS pricing — single source of truth for admin, billing, Stripe, and UI.

Plans (net EUR, excl. VAT):
- Tageskarte: 19/day
- Starter: 149/month (10 workers included)
- Professional: 999/month + 2.50/worker
- Enterprise: 2,490/month + 3.00/worker
"""
from __future__ import annotations

from typing import Any

PLAN_ORDER = ("tageskarte", "starter", "professional", "enterprise")
PLAN_RANK = {p: i for i, p in enumerate(PLAN_ORDER)}

# Monthly net base fee (EUR, excl. VAT). Tageskarte is per day.
PLAN_NET_PRICE_EUR: dict[str, float] = {
    "tageskarte": 19.0,
    "starter": 149.0,
    "professional": 999.0,
    "enterprise": 2490.0,
}

# Per active worker beyond included quota (EUR/mo, excl. VAT)
PLAN_WORKER_PRICE_EUR: dict[str, float] = {
    "tageskarte": 0.0,
    "starter": 0.0,
    "professional": 2.50,
    "enterprise": 3.00,
}

PLAN_WORKER_FREE_INCLUDED: dict[str, int] = {
    "tageskarte": 0,
    "starter": 10,
    "professional": 0,
    "enterprise": 0,
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
        "priceUnit": "day",
        "priceUnitAr": "يوم",
        "taglineDe": "Besucher & Kurzzeit-Zutritt",
        "taglineEn": "Visitors and short-term site access",
        "taglineAr": "زوار ودخول مؤقت للموقع",
        "taglineTr": "Ziyaretçiler ve kısa süreli şantiye erişimi",
        "taglineFr": "Visiteurs et accès court terme au chantier",
        "taglineEs": "Visitantes y acceso temporal a la obra",
        "taglineIt": "Visitatori e accesso temporaneo al cantiere",
        "taglinePl": "Goście i krótkoterminowy dostęp do placu budowy",
        "benchmarkNoteDe": "Kurzzeit-Zutritt für Besucher und Subunternehmer",
    },
    "starter": {
        "label": "Starter",
        "labelAr": "مبتدئ",
        "priceUnit": "month",
        "priceUnitAr": "شهر",
        "taglineDe": "Worker-App, NFC, Urlaub — bis 10 MA inkl.",
        "taglineEn": "Worker app, NFC, leave — 10 workers included",
        "taglineAr": "تطبيق الموظف + NFC + إجازات — 10 موظفين مشمولين",
        "taglineTr": "Worker uygulaması, NFC, izin — 10 çalışan dahil",
        "taglineFr": "App worker, NFC, congés — 10 salariés inclus",
        "taglineEs": "App del trabajador, NFC, permisos — 10 trabajadores incluidos",
        "taglineIt": "App worker, NFC, ferie — 10 lavoratori inclusi",
        "taglinePl": "Aplikacja pracownika, NFC, urlopy — 10 pracowników w cenie",
        "benchmarkNoteDe": "Kleine Baustellen & Subunternehmer",
    },
    "professional": {
        "label": "Professional",
        "labelAr": "احترافي",
        "priceUnit": "month",
        "priceUnitAr": "شهر",
        "taglineDe": "Echtzeit, Automatisierung, Fakturierung & Mahnwesen",
        "taglineEn": "Real-time ops, automation, invoicing & dunning",
        "taglineAr": "تشغيل لحظي + أتمتة + فوترة + تذكيرات",
        "taglineTr": "Gerçek zamanlı operasyon, otomasyon, faturalama ve tahsilat",
        "taglineFr": "Ops temps réel, automatisation, facturation et relances",
        "taglineEs": "Operación en tiempo real, automatización, facturación y recordatorios",
        "taglineIt": "Operatività in tempo reale, automazione, fatturazione e solleciti",
        "taglinePl": "Operacje w czasie rzeczywistym, automatyzacja, fakturowanie i windykacja",
        "benchmarkNoteDe": "999 €/Monat + 2,50 € pro aktivem Mitarbeiter",
    },
    "enterprise": {
        "label": "Enterprise",
        "labelAr": "مؤسسي",
        "priceUnit": "month",
        "priceUnitAr": "شهر",
        "taglineDe": "KI, Wallet-Pässe, SAP/Oracle, Command Center",
        "taglineEn": "AI, wallet passes, SAP/Oracle, command center",
        "taglineAr": "AI + محافظ رقمية + SAP/Oracle + قيادة مركزية",
        "taglineTr": "Yapay zeka, cüzdan kartları, SAP/Oracle, komuta merkezi",
        "taglineFr": "IA, passes wallet, SAP/Oracle, centre de commande",
        "taglineEs": "IA, pases wallet, SAP/Oracle, centro de mando",
        "taglineIt": "IA, pass wallet, SAP/Oracle, command center",
        "taglinePl": "AI, karty wallet, SAP/Oracle, centrum dowodzenia",
        "benchmarkNoteDe": "2.490 €/Monat + 3,00 € pro aktivem Mitarbeiter",
    },
}


def _attach_tagline_i18n(meta: dict[str, Any]) -> None:
    meta["taglineI18n"] = {
        "de": str(meta.get("taglineDe") or meta.get("taglineEn") or ""),
        "en": str(meta.get("taglineEn") or meta.get("taglineDe") or ""),
        "ar": str(meta.get("taglineAr") or meta.get("taglineEn") or ""),
        "tr": str(meta.get("taglineTr") or meta.get("taglineEn") or ""),
        "fr": str(meta.get("taglineFr") or meta.get("taglineEn") or ""),
        "es": str(meta.get("taglineEs") or meta.get("taglineEn") or ""),
        "it": str(meta.get("taglineIt") or meta.get("taglineEn") or ""),
        "pl": str(meta.get("taglinePl") or meta.get("taglineEn") or ""),
    }


def build_plan_meta() -> dict[str, dict[str, Any]]:
    """Entitlements-compatible plan metadata derived from canonical pricing."""
    out: dict[str, dict[str, Any]] = {}
    for plan in PLAN_ORDER:
        meta = dict(PLAN_MARKETING.get(plan, {}))
        meta["priceEur"] = PLAN_NET_PRICE_EUR.get(plan, 0)
        meta["workersIncluded"] = PLAN_WORKER_FREE_INCLUDED.get(plan, 0)
        meta["workerOverageEur"] = PLAN_WORKER_PRICE_EUR.get(plan, 0)
        _attach_tagline_i18n(meta)
        out[plan] = meta
    return out


def stripe_price_env_key(plan: str, *, annual: bool = False) -> str:
    suffix = "_ANNUAL" if annual else ""
    return f"STRIPE_PRICE_{plan.upper()}{suffix}"


def stripe_worker_price_env_key(plan: str) -> str:
    return f"STRIPE_PRICE_{plan.upper()}_WORKER"


def resolve_stripe_price_id(plan: str, *, annual: bool = False) -> str:
    import os

    key = stripe_price_env_key(plan, annual=annual)
    value = (os.getenv(key) or "").strip()
    if value or annual:
        return value
    return (os.getenv(f"STRIPE_PRICE_{plan.upper()}") or "").strip()


def resolve_stripe_worker_price_id(plan: str) -> str:
    import os

    return (os.getenv(stripe_worker_price_env_key(plan)) or "").strip()


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
        meta["priceEur"] = PLAN_NET_PRICE_EUR.get(plan, 0)
        meta["workersIncluded"] = PLAN_WORKER_FREE_INCLUDED.get(plan, 0)
        meta["workerOverageEur"] = PLAN_WORKER_PRICE_EUR.get(plan, 0)
        meta["monthlyQuote"] = calculate_monthly_net(plan, worker_count=meta.get("workersIncluded") or 0)
        meta["stripePriceId"] = resolve_stripe_price_id(plan, annual=False)
        meta["stripePriceIdAnnual"] = resolve_stripe_price_id(plan, annual=True)
        meta["stripeWorkerPriceId"] = resolve_stripe_worker_price_id(plan)
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
