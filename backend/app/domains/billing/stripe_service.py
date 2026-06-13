"""Stripe billing: checkout, portal, payment links, webhooks, reconciliation."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any
from urllib import parse, request as urlrequest

from backend.app.platform.pricing import (
    PLAN_MARKETING,
    PLAN_NET_PRICE_EUR,
    PLAN_ORDER,
    PLAN_WORKER_PRICE_EUR,
    ANNUAL_DISCOUNT_PERCENT,
    calculate_monthly_net,
    checkout_trial_days,
    resolve_stripe_price_id,
    resolve_stripe_worker_price_id,
)

STRIPE_API = "https://api.stripe.com/v1"


def _stripe_key() -> str:
    return (os.getenv("STRIPE_SECRET_KEY") or "").strip()


def _webhook_secret() -> str:
    return (os.getenv("STRIPE_WEBHOOK_SECRET") or "").strip()


def _public_base_url() -> str:
    return (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")


def stripe_configured() -> bool:
    return bool(_stripe_key())


def webhook_signature_required() -> bool:
    """Require signed Stripe webhooks when Stripe is configured (opt-out for local dev)."""
    if not stripe_configured():
        return False
    allow = (os.getenv("BAUPASS_ALLOW_UNSIGNED_STRIPE_WEBHOOKS") or "").strip().lower()
    return allow not in ("1", "true", "yes")


def _stripe_request(method: str, path: str, payload: dict[str, str] | None = None, timeout_s: int = 30) -> dict:
    key = _stripe_key()
    if not key:
        raise RuntimeError("stripe_not_configured")
    url = f"{STRIPE_API}{path}"
    headers = {"Authorization": f"Bearer {key}"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = parse.urlencode({k: v for k, v in payload.items() if v is not None}).encode()
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            req = urlrequest.Request(url, data=data, headers=headers, method=method)
            with urlrequest.urlopen(req, timeout=timeout_s) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:
            last_err = exc
            if attempt < 2:
                time.sleep(0.35 * (attempt + 1))
    raise RuntimeError(f"stripe_upstream_failed: {last_err}")


def verify_webhook_signature(payload: bytes, sig_header: str, tolerance: int = 300) -> bool:
    secret = _webhook_secret()
    if not secret or not sig_header:
        return False
    parts = {}
    for item in sig_header.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            parts[k.strip()] = v.strip()
    timestamp = parts.get("t")
    signature = parts.get("v1")
    if not timestamp or not signature:
        return False
    try:
        if abs(int(time.time()) - int(timestamp)) > tolerance:
            return False
    except ValueError:
        return False
    signed = f"{timestamp}.{payload.decode('utf-8')}".encode()
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _normalize_plan(value: str) -> str:
    plan = str(value or "starter").strip().lower()
    return plan if plan in PLAN_ORDER else "starter"


def _company_row(db, company_id: str):
    return db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()


def _worker_count(db, company_id: str) -> int:
    row = db.execute(
        "SELECT COUNT(*) AS c FROM workers WHERE company_id = ? AND deleted_at IS NULL",
        (company_id,),
    ).fetchone()
    return int((row["c"] if row else 0) or 0)


def _company_trial_eligible(db, company_id: str) -> bool:
    """First Stripe subscription checkout may include a free trial."""
    if checkout_trial_days() <= 0:
        return False
    company = _company_row(db, company_id)
    if not company:
        return False
    sub_id = str(company["stripe_subscription_id"] if "stripe_subscription_id" in company.keys() else "").strip()
    sub_status = str(company["stripe_subscription_status"] if "stripe_subscription_status" in company.keys() else "").strip().lower()
    if sub_id or sub_status in {"active", "trialing", "past_due"}:
        return False
    return True


def _sync_trial_end_from_subscription(db, company_id: str, subscription_obj: dict[str, Any]) -> None:
    trial_end = subscription_obj.get("trial_end")
    if not trial_end:
        return
    try:
        from datetime import datetime, timezone

        trial_iso = datetime.fromtimestamp(int(trial_end), tz=timezone.utc).date().isoformat()
        db.execute("UPDATE companies SET trial_ends_at = ? WHERE id = ?", (trial_iso, company_id))
    except (TypeError, ValueError, OSError):
        return


def get_or_create_customer(db, company_id: str, *, email: str = "") -> str:
    company = _company_row(db, company_id)
    if not company:
        raise ValueError("company_not_found")
    existing = str(company["stripe_customer_id"] if "stripe_customer_id" in company.keys() else "").strip()
    if existing:
        return existing
    billing_email = email or str(company["billing_email"] or company["contact"] or "").strip()
    payload = {
        "name": str(company["name"] or ""),
        "email": billing_email,
        "metadata[company_id]": company_id,
        "metadata[platform]": "baupass",
    }
    customer = _stripe_request("POST", "/customers", payload)
    customer_id = str(customer.get("id") or "")
    if not customer_id:
        raise RuntimeError("stripe_customer_create_failed")
    db.execute("UPDATE companies SET stripe_customer_id = ? WHERE id = ?", (customer_id, company_id))
    db.commit()
    return customer_id


def create_checkout_session(
    db,
    company_id: str,
    *,
    plan: str,
    annual: bool = False,
    success_url: str = "",
    cancel_url: str = "",
) -> dict[str, Any]:
    normalized = _normalize_plan(plan)
    if normalized == "tageskarte":
        raise ValueError("tageskarte_use_payment_link")
    price_id = resolve_stripe_price_id(normalized, annual=annual)
    if not price_id:
        raise ValueError("stripe_price_not_configured")
    customer_id = get_or_create_customer(db, company_id)
    base = _public_base_url() or success_url.rsplit("?", 1)[0] or "/"
    ok_url = success_url or f"{base}/?billing=success&plan={normalized}"
    no_url = cancel_url or f"{base}/?billing=cancel"
    payload = {
        "mode": "subscription",
        "customer": customer_id,
        "client_reference_id": company_id,
        "success_url": ok_url,
        "cancel_url": no_url,
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "subscription_data[metadata][company_id]": company_id,
        "subscription_data[metadata][plan]": normalized,
        "subscription_data[metadata][billing_cycle]": "annual" if annual else "monthly",
        "metadata[company_id]": company_id,
        "metadata[plan]": normalized,
        "allow_promotion_codes": "true",
        "billing_address_collection": "required",
        "tax_id_collection[enabled]": "true",
    }
    if normalized != "tageskarte":
        payload["payment_method_types[0]"] = "card"
        payload["payment_method_types[1]"] = "sepa_debit"
    trial_days = checkout_trial_days()
    trial_eligible = _company_trial_eligible(db, company_id)
    if trial_eligible and trial_days > 0:
        payload["subscription_data[trial_period_days]"] = str(trial_days)
        payload["metadata[trial_days]"] = str(trial_days)
    worker_count = _worker_count(db, company_id)
    quote = calculate_monthly_net(normalized, worker_count, annual=annual)
    billable_workers = int(quote.get("billableWorkers") or 0)
    if billable_workers > 0:
        worker_price_id = resolve_stripe_worker_price_id(normalized)
        if worker_price_id:
            payload["line_items[1][price]"] = worker_price_id
            payload["line_items[1][quantity]"] = str(billable_workers)
            payload["metadata[billable_workers]"] = str(billable_workers)
            payload["subscription_data[metadata][billable_workers]"] = str(billable_workers)
    session = _stripe_request("POST", "/checkout/sessions", payload)
    return {
        "sessionId": session.get("id"),
        "url": session.get("url"),
        "plan": normalized,
        "annual": annual,
        "priceId": price_id,
        "workerCount": worker_count,
        "billableWorkers": billable_workers,
        "trialDays": trial_days if trial_eligible else 0,
        "trialEligible": trial_eligible,
    }


def create_customer_portal_session(db, company_id: str, *, return_url: str = "") -> dict[str, Any]:
    customer_id = get_or_create_customer(db, company_id)
    ret = return_url or f"{_public_base_url()}/?billing=portal"
    session = _stripe_request(
        "POST",
        "/billing_portal/sessions",
        {"customer": customer_id, "return_url": ret},
    )
    return {"url": session.get("url")}


def create_invoice_payment_link(db, invoice_id: str) -> dict[str, Any]:
    invoice = db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not invoice:
        raise ValueError("invoice_not_found")
    if str(invoice["paid_at"] or "").strip():
        raise ValueError("invoice_already_paid")
    company_id = str(invoice["company_id"] or "")
    company = _company_row(db, company_id)
    if not company:
        raise ValueError("company_not_found")
    customer_id = get_or_create_customer(db, company_id)
    amount_cents = max(1, int(round(float(invoice["total_amount"] or 0) * 100)))
    product = _stripe_request(
        "POST",
        "/products",
        {
            "name": f"Rechnung {invoice['invoice_number']}",
            "metadata[invoice_id]": invoice_id,
            "metadata[company_id]": company_id,
        },
    )
    price = _stripe_request(
        "POST",
        "/prices",
        {
            "product": str(product.get("id") or ""),
            "unit_amount": str(amount_cents),
            "currency": "eur",
        },
    )
    link = _stripe_request(
        "POST",
        "/payment_links",
        {
            "line_items[0][price]": str(price.get("id") or ""),
            "line_items[0][quantity]": "1",
            "metadata[invoice_id]": invoice_id,
            "metadata[company_id]": company_id,
            "after_completion[type]": "redirect",
            "after_completion[redirect][url]": f"{_public_base_url()}/?billing=invoice_paid",
        },
    )
    link_id = str(link.get("id") or "")
    link_url = str(link.get("url") or "")
    db.execute(
        """
        UPDATE invoices
        SET stripe_payment_link_id = ?, stripe_payment_link_url = ?
        WHERE id = ?
        """,
        (link_id, link_url, invoice_id),
    )
    db.commit()
    return {"paymentLinkId": link_id, "url": link_url, "invoiceId": invoice_id}


def _event_seen(db, event_id: str) -> bool:
    row = db.execute("SELECT id FROM stripe_billing_events WHERE id = ?", (event_id,)).fetchone()
    return bool(row)


def _mark_event(db, event_id: str, event_type: str) -> None:
    db.execute(
        "INSERT OR IGNORE INTO stripe_billing_events (id, event_type, processed_at) VALUES (?, ?, ?)",
        (event_id, event_type, _now_iso()),
    )


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def _apply_company_plan(db, company_id: str, plan: str, *, subscription_id: str = "", status: str = "active", billing_cycle: str = "monthly") -> None:
    from backend.server import log_audit, normalize_company_plan

    normalized = normalize_company_plan(plan)
    db.execute(
        """
        UPDATE companies
        SET plan = ?,
            stripe_subscription_id = COALESCE(NULLIF(?, ''), stripe_subscription_id),
            stripe_subscription_status = ?,
            billing_cycle = ?
        WHERE id = ?
        """,
        (normalized, subscription_id, status, billing_cycle, company_id),
    )
    log_audit(
        "billing.plan_updated",
        f"Plan auf {normalized} gesetzt (Stripe: {status})",
        target_type="company",
        target_id=company_id,
        company_id=company_id,
    )


def _mark_invoice_paid_from_stripe(db, invoice_id: str, *, payment_ref: str = "", note: str = "") -> bool:
    from backend.server import log_audit, now_iso

    invoice = db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not invoice or str(invoice["paid_at"] or "").strip():
        return False
    payment_date = now_iso().split("T")[0]
    payment_note = note or f"Stripe: {payment_ref}".strip()
    db.execute(
        """
        UPDATE invoices
        SET status = 'bezahlt', paid_at = ?, payment_note = ?, last_reminder_error = ''
        WHERE id = ?
        """,
        (payment_date, payment_note, invoice_id),
    )
    company_id = str(invoice["company_id"] or "")
    company = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    log_audit(
        "invoice.paid_stripe",
        f"Rechnung {invoice['invoice_number']} via Stripe bezahlt",
        target_type="invoice",
        target_id=invoice_id,
        company_id=company_id,
    )
    remaining = db.execute(
        """
        SELECT COUNT(*) AS c FROM invoices
        WHERE company_id = ? AND paid_at IS NULL AND auto_suspend_triggered_at IS NOT NULL
        """,
        (company_id,),
    ).fetchone()
    if company and str(company["status"] or "") == "gesperrt" and int(remaining["c"] or 0) == 0:
        db.execute("UPDATE companies SET status = 'aktiv' WHERE id = ?", (company_id,))
        log_audit(
            "company.auto_unsuspended_invoices_paid",
            f"Firma '{company['name']}' entsperrt nach Stripe-Zahlung",
            target_type="company",
            target_id=company_id,
            company_id=company_id,
        )
    return True


def handle_webhook_event(db, event: dict[str, Any]) -> dict[str, Any]:
    from backend.app.platform.events.bus import publish_event

    event_id = str(event.get("id") or uuid.uuid4())
    event_type = str(event.get("type") or "")
    if _event_seen(db, event_id):
        return {"duplicate": True, "type": event_type}
    data_obj = (event.get("data") or {}).get("object") or {}
    handled = False

    if event_type == "checkout.session.completed":
        company_id = str(data_obj.get("client_reference_id") or (data_obj.get("metadata") or {}).get("company_id") or "")
        plan = _normalize_plan((data_obj.get("metadata") or {}).get("plan") or "starter")
        subscription_id = str(data_obj.get("subscription") or "")
        billing_cycle = str((data_obj.get("metadata") or {}).get("billing_cycle") or "monthly")
        customer_id = str(data_obj.get("customer") or "")
        mode = str(data_obj.get("mode") or "subscription")
        invoice_id = str((data_obj.get("metadata") or {}).get("invoice_id") or "")
        if mode == "payment" and invoice_id:
            _mark_invoice_paid_from_stripe(
                db,
                invoice_id,
                payment_ref=str(data_obj.get("payment_intent") or data_obj.get("id") or ""),
            )
            handled = True
        elif company_id:
            if customer_id:
                db.execute("UPDATE companies SET stripe_customer_id = ? WHERE id = ?", (customer_id, company_id))
            if subscription_id:
                _apply_company_plan(db, company_id, plan, subscription_id=subscription_id, status="active", billing_cycle=billing_cycle)
            if invoice_id:
                _mark_invoice_paid_from_stripe(db, invoice_id, payment_ref=str(data_obj.get("payment_intent") or data_obj.get("id") or ""))
            handled = True

    elif event_type in ("customer.subscription.updated", "customer.subscription.created"):
        meta = data_obj.get("metadata") or {}
        company_id = str(meta.get("company_id") or "")
        plan = _normalize_plan(meta.get("plan") or "starter")
        status = str(data_obj.get("status") or "active")
        subscription_id = str(data_obj.get("id") or "")
        billing_cycle = str(meta.get("billing_cycle") or "monthly")
        if company_id:
            if status in ("active", "trialing"):
                _apply_company_plan(db, company_id, plan, subscription_id=subscription_id, status=status, billing_cycle=billing_cycle)
                _sync_trial_end_from_subscription(db, company_id, data_obj)
            elif status in ("past_due", "unpaid"):
                db.execute(
                    "UPDATE companies SET stripe_subscription_status = ? WHERE id = ?",
                    (status, company_id),
                )
            handled = True

    elif event_type == "customer.subscription.deleted":
        meta = data_obj.get("metadata") or {}
        company_id = str(meta.get("company_id") or "")
        if company_id:
            db.execute(
                """
                UPDATE companies
                SET stripe_subscription_id = '', stripe_subscription_status = 'canceled', plan = 'starter'
                WHERE id = ?
                """,
                (company_id,),
            )
            handled = True

    elif event_type == "invoice.paid":
        meta = data_obj.get("metadata") or {}
        invoice_id = str(meta.get("invoice_id") or meta.get("baupass_invoice_id") or "")
        if invoice_id:
            _mark_invoice_paid_from_stripe(db, invoice_id, payment_ref=str(data_obj.get("id") or ""))
            handled = True

    elif event_type == "invoice.payment_failed":
        meta = data_obj.get("metadata") or {}
        company_id = str(meta.get("company_id") or "")
        if company_id:
            db.execute(
                "UPDATE companies SET stripe_subscription_status = 'past_due' WHERE id = ?",
                (company_id,),
            )
            handled = True

    elif event_type == "payment_intent.succeeded":
        meta = data_obj.get("metadata") or {}
        invoice_id = str(meta.get("invoice_id") or meta.get("baupass_invoice_id") or "")
        if invoice_id:
            _mark_invoice_paid_from_stripe(db, invoice_id, payment_ref=str(data_obj.get("id") or ""))
            handled = True

    _mark_event(db, event_id, event_type)
    db.commit()
    publish_event(event_type, None, event)
    return {"handled": handled, "type": event_type, "eventId": event_id}


def subscription_overview(db, company_id: str) -> dict[str, Any]:
    from backend.app.platform.pricing import pricing_catalog
    from backend.server import get_company_plan, normalize_company_plan

    company = _company_row(db, company_id)
    if not company:
        raise ValueError("company_not_found")
    plan = normalize_company_plan(get_company_plan(db, company_id))
    workers = _worker_count(db, company_id)
    quote = calculate_monthly_net(plan, workers)
    open_invoices = db.execute(
        """
        SELECT COUNT(*) AS c, COALESCE(SUM(total_amount), 0) AS total
        FROM invoices
        WHERE company_id = ? AND paid_at IS NULL AND status IN ('sent', 'overdue', 'send_failed')
        """,
        (company_id,),
    ).fetchone()
    return {
        "companyId": company_id,
        "plan": plan,
        "status": str(company["status"] or ""),
        "trialEndsAt": str(company["trial_ends_at"] or ""),
        "billingCycle": str(company["billing_cycle"] if "billing_cycle" in company.keys() else "monthly"),
        "stripe": {
            "configured": stripe_configured(),
            "customerId": str(company["stripe_customer_id"] if "stripe_customer_id" in company.keys() else ""),
            "subscriptionId": str(company["stripe_subscription_id"] if "stripe_subscription_id" in company.keys() else ""),
            "subscriptionStatus": str(company["stripe_subscription_status"] if "stripe_subscription_status" in company.keys() else ""),
        },
        "trial": {
            "endsAt": str(company["trial_ends_at"] or ""),
            "checkoutTrialDays": checkout_trial_days(),
            "eligibleForCheckoutTrial": _company_trial_eligible(db, company_id),
            "isTrialing": str(company["stripe_subscription_status"] if "stripe_subscription_status" in company.keys() else "").lower() == "trialing",
        },
        "workers": {"active": workers, **quote},
        "openInvoices": {
            "count": int((open_invoices["c"] if open_invoices else 0) or 0),
            "totalEur": round(float((open_invoices["total"] if open_invoices else 0) or 0), 2),
        },
        "pricing": pricing_catalog(),
    }


def revenue_metrics(db) -> dict[str, Any]:
    paid_rows = db.execute(
        """
        SELECT COUNT(*) AS c, COALESCE(SUM(total_amount), 0) AS total
        FROM invoices WHERE paid_at IS NOT NULL
        """
    ).fetchone()
    open_rows = db.execute(
        """
        SELECT COUNT(*) AS c, COALESCE(SUM(total_amount), 0) AS total
        FROM invoices WHERE paid_at IS NULL AND status IN ('sent', 'overdue')
        """
    ).fetchone()
    by_plan = db.execute(
        """
        SELECT plan, COUNT(*) AS companies
        FROM companies
        WHERE deleted_at IS NULL
        GROUP BY plan
        """
    ).fetchall()
    mrr_estimate = 0.0
    for row in db.execute("SELECT id, plan FROM companies WHERE deleted_at IS NULL").fetchall():
        cid = str(row["id"])
        plan = _normalize_plan(row["plan"])
        workers = _worker_count(db, cid)
        mrr_estimate += calculate_monthly_net(plan, workers)["totalNetEur"]
    return {
        "paidInvoices": {
            "count": int((paid_rows["c"] if paid_rows else 0) or 0),
            "totalEur": round(float((paid_rows["total"] if paid_rows else 0) or 0), 2),
        },
        "openInvoices": {
            "count": int((open_rows["c"] if open_rows else 0) or 0),
            "totalEur": round(float((open_rows["total"] if open_rows else 0) or 0), 2),
        },
        "estimatedMrrNetEur": round(mrr_estimate, 2),
        "companiesByPlan": {str(r["plan"]): int(r["companies"]) for r in by_plan},
        "stripeConfigured": stripe_configured(),
    }


def bootstrap_stripe_catalog(*, dry_run: bool = False) -> dict[str, Any]:
    """
    Create BauPass subscription products/prices in Stripe (test or live key).
    Returns env var lines for Railway — does not write .env automatically.
    """
    if not stripe_configured():
        raise RuntimeError("stripe_not_configured")

    env_lines: dict[str, str] = {}
    created: list[dict[str, Any]] = []

    for plan in ("starter", "professional", "enterprise"):
        monthly_eur = float(PLAN_NET_PRICE_EUR[plan])
        annual_eur = round(monthly_eur * 12 * (1 - ANNUAL_DISCOUNT_PERCENT / 100), 2)
        meta = PLAN_MARKETING.get(plan, {})
        product_name = f"BauPass {meta.get('label', plan.title())}"
        product_desc = str(meta.get("taglineDe") or meta.get("taglineEn") or "")

        if dry_run:
            worker_eur = float(PLAN_WORKER_PRICE_EUR.get(plan, 0.0))
            created.append(
                {
                    "plan": plan,
                    "productName": product_name,
                    "monthlyEur": monthly_eur,
                    "annualEur": annual_eur,
                    "workerEur": worker_eur if worker_eur > 0 else None,
                    "dryRun": True,
                }
            )
            env_lines[f"STRIPE_PRICE_{plan.upper()}"] = f"price_DRYRUN_{plan}_monthly"
            env_lines[f"STRIPE_PRICE_{plan.upper()}_ANNUAL"] = f"price_DRYRUN_{plan}_annual"
            if worker_eur > 0:
                env_lines[f"STRIPE_PRICE_{plan.upper()}_WORKER"] = f"price_DRYRUN_{plan}_worker"
            continue

        product = _stripe_request(
            "POST",
            "/products",
            {
                "name": product_name,
                "description": product_desc[:500],
                "metadata[plan]": plan,
                "metadata[platform]": "baupass",
            },
        )
        product_id = str(product.get("id") or "")

        monthly = _stripe_request(
            "POST",
            "/prices",
            {
                "product": product_id,
                "unit_amount": str(int(round(monthly_eur * 100))),
                "currency": "eur",
                "recurring[interval]": "month",
                "tax_behavior": "exclusive",
                "metadata[plan]": plan,
                "metadata[billing_cycle]": "monthly",
            },
        )
        annual = _stripe_request(
            "POST",
            "/prices",
            {
                "product": product_id,
                "unit_amount": str(int(round(annual_eur * 100))),
                "currency": "eur",
                "recurring[interval]": "year",
                "tax_behavior": "exclusive",
                "metadata[plan]": plan,
                "metadata[billing_cycle]": "annual",
            },
        )
        monthly_id = str(monthly.get("id") or "")
        annual_id = str(annual.get("id") or "")
        env_lines[f"STRIPE_PRICE_{plan.upper()}"] = monthly_id
        env_lines[f"STRIPE_PRICE_{plan.upper()}_ANNUAL"] = annual_id
        worker_eur = float(PLAN_WORKER_PRICE_EUR.get(plan, 0.0))
        worker_price_id = ""
        if worker_eur > 0:
            worker = _stripe_request(
                "POST",
                "/prices",
                {
                    "product": product_id,
                    "unit_amount": str(int(round(worker_eur * 100))),
                    "currency": "eur",
                    "recurring[interval]": "month",
                    "tax_behavior": "exclusive",
                    "metadata[plan]": plan,
                    "metadata[billing_cycle]": "worker_overage",
                },
            )
            worker_price_id = str(worker.get("id") or "")
            env_lines[f"STRIPE_PRICE_{plan.upper()}_WORKER"] = worker_price_id
        created.append(
            {
                "plan": plan,
                "productId": product_id,
                "monthlyPriceId": monthly_id,
                "monthlyEur": monthly_eur,
                "annualPriceId": annual_id,
                "annualEur": annual_eur,
                "workerPriceId": worker_price_id or None,
                "workerEur": worker_eur if worker_eur > 0 else None,
            }
        )

    return {
        "ok": True,
        "dryRun": dry_run,
        "created": created,
        "env": env_lines,
        "railwayHint": "Paste env vars into Railway → Variables, then redeploy.",
        "trialDays": checkout_trial_days(),
    }
