"""Billing domain — invoice routes + v2 overview + Stripe."""
from __future__ import annotations

from flask import Blueprint, Flask, g, jsonify, request

from .._routes import register_blueprint_once
from ..shared import company_id_from_user, forbidden_company
from .service import BillingService
from . import stripe_service

billing_core_bp = Blueprint("billing_domain_core", __name__)
billing_v2_bp = Blueprint("billing_domain_v2", __name__)
_service = BillingService()


def _register_core_billing_routes() -> None:
    from .._routes import mark_routes_mounted, routes_already_mounted

    if routes_already_mounted("billing"):
        return
    from backend.server import (
        bulk_mark_invoices_paid,
        decide_invoice_approval,
        export_all_invoices_csv,
        export_invoice_incidents_csv,
        export_invoice_retry_queue_csv,
        get_invoice_ops_metrics_endpoint,
        get_invoice_send_attempts,
        get_monthly_invoice_cycle_status_endpoint,
        get_next_invoice_number,
        invoice_access_line_items,
        invoice_reminder_letter_pdf,
        list_invoice_dead_letters,
        list_invoices,
        list_pending_invoice_approvals_endpoint,
        mark_invoice_paid,
        resolve_invoice_dead_letter,
        retry_send_invoice,
        retry_send_invoices_bulk,
        send_invoice,
        simulate_monthly_invoice_cycle_endpoint,
        trigger_dunning_run,
        trigger_monthly_invoice_cycle_endpoint,
    )

    rules = (
        ("/invoices/access-line-items", invoice_access_line_items, ("GET",)),
        ("/invoices/export.csv", export_all_invoices_csv, ("GET",)),
        ("/invoices", list_invoices, ("GET",)),
        ("/invoices/ops-metrics", get_invoice_ops_metrics_endpoint, ("GET",)),
        ("/invoices/monthly-cycle-status", get_monthly_invoice_cycle_status_endpoint, ("GET",)),
        ("/invoices/dead-letters", list_invoice_dead_letters, ("GET",)),
        ("/invoices/next-number", get_next_invoice_number, ("GET",)),
        ("/invoices/send", send_invoice, ("POST",)),
        ("/invoices/<invoice_id>/retry-send", retry_send_invoice, ("POST",)),
        ("/invoices/<invoice_id>/attempts", get_invoice_send_attempts, ("GET",)),
        ("/invoices/<invoice_id>/dead-letter/resolve", resolve_invoice_dead_letter, ("PUT",)),
        ("/invoices/retry-send-bulk", retry_send_invoices_bulk, ("POST",)),
        ("/invoices/approvals/pending", list_pending_invoice_approvals_endpoint, ("GET",)),
        ("/invoices/approvals/<approval_id>/decision", decide_invoice_approval, ("POST",)),
        ("/invoices/retry-queue/export.csv", export_invoice_retry_queue_csv, ("GET",)),
        ("/invoices/incidents/export.csv", export_invoice_incidents_csv, ("GET",)),
        ("/invoices/<invoice_id>/pay", mark_invoice_paid, ("PUT",)),
        ("/invoices/bulk-mark-paid", bulk_mark_invoices_paid, ("POST",)),
        ("/invoices/trigger-dunning", trigger_dunning_run, ("POST",)),
        ("/invoices/trigger-monthly-cycle", trigger_monthly_invoice_cycle_endpoint, ("POST",)),
        ("/invoices/simulate-monthly-cycle", simulate_monthly_invoice_cycle_endpoint, ("POST",)),
        ("/invoices/<invoice_id>/reminder-letter.pdf", invoice_reminder_letter_pdf, ("GET",)),
    )
    for path, view_func, methods in rules:
        billing_core_bp.add_url_rule(path, view_func=view_func, methods=list(methods))
    mark_routes_mounted("billing")


def register_billing_blueprint(flask_app: Flask) -> None:
    from backend.server import get_db, require_auth, require_roles

    _register_core_billing_routes()

    @billing_v2_bp.get("/billing/overview")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_billing_overview():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        try:
            return jsonify(_service.subscription_overview(get_db(), cid))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404

    @billing_v2_bp.get("/billing/pricing")
    def v2_billing_pricing():
        from backend.app.platform.pricing import pricing_catalog

        return jsonify(pricing_catalog())

    @billing_v2_bp.get("/billing/stripe/setup-status")
    @require_auth
    @require_roles("superadmin")
    def v2_stripe_setup_status():
        from backend.app.platform.setup_status import collect_setup_status

        status = collect_setup_status()
        billing = status.get("billing") or {}
        return jsonify(
            {
                "billing": billing,
                "docs": "docs/stripe-live-setup.md",
                "bootstrapEndpoint": "/api/v2/billing/stripe/bootstrap",
            }
        )

    @billing_v2_bp.get("/billing/revenue-metrics")
    @require_auth
    @require_roles("superadmin")
    def v2_billing_revenue_metrics():
        return jsonify(_service.revenue_metrics(get_db()))

    @billing_v2_bp.post("/billing/stripe/checkout-session")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_stripe_checkout():
        if not stripe_service.stripe_configured():
            return jsonify({"error": "stripe_not_configured", "hint": "Set STRIPE_SECRET_KEY"}), 503
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        data = request.get_json(silent=True) or {}
        try:
            result = stripe_service.create_checkout_session(
                get_db(),
                cid,
                plan=str(data.get("plan") or "starter"),
                annual=bool(data.get("annual")),
                success_url=str(data.get("success_url") or ""),
                cancel_url=str(data.get("cancel_url") or ""),
            )
            return jsonify(result)
        except ValueError as exc:
            code = str(exc)
            status = 400 if code in ("stripe_price_not_configured", "tageskarte_use_payment_link") else 404
            return jsonify({"error": code}), status
        except RuntimeError as exc:
            return jsonify({"error": "stripe_upstream_failed", "detail": str(exc)}), 502

    @billing_v2_bp.post("/billing/stripe/portal-session")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_stripe_portal():
        if not stripe_service.stripe_configured():
            return jsonify({"error": "stripe_not_configured"}), 503
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        data = request.get_json(silent=True) or {}
        try:
            return jsonify(
                stripe_service.create_customer_portal_session(
                    get_db(), cid, return_url=str(data.get("return_url") or "")
                )
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404
        except RuntimeError as exc:
            return jsonify({"error": "stripe_upstream_failed", "detail": str(exc)}), 502

    @billing_v2_bp.post("/billing/invoices/<invoice_id>/payment-link")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def v2_invoice_payment_link(invoice_id: str):
        if not stripe_service.stripe_configured():
            return jsonify({"error": "stripe_not_configured"}), 503
        db = get_db()
        invoice = db.execute("SELECT company_id FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not invoice:
            return jsonify({"error": "invoice_not_found"}), 404
        if g.current_user["role"] != "superadmin" and str(invoice["company_id"]) != str(g.current_user.get("company_id") or ""):
            return jsonify({"error": "forbidden_company"}), 403
        try:
            return jsonify(stripe_service.create_invoice_payment_link(db, invoice_id))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"error": "stripe_upstream_failed", "detail": str(exc)}), 502

    @billing_v2_bp.post("/billing/stripe/bootstrap")
    @require_auth
    @require_roles("superadmin")
    def v2_stripe_bootstrap():
        if not stripe_service.stripe_configured():
            return jsonify({"error": "stripe_not_configured"}), 503
        data = request.get_json(silent=True) or {}
        dry_run = bool(data.get("dry_run") or data.get("dryRun"))
        try:
            return jsonify(stripe_service.bootstrap_stripe_catalog(dry_run=dry_run))
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 502

    @billing_v2_bp.post("/billing/stripe/webhook")
    def v2_stripe_webhook():
        payload_raw = request.get_data() or b""
        sig = request.headers.get("Stripe-Signature") or ""
        if stripe_service.webhook_signature_required():
            if not stripe_service._webhook_secret():
                return jsonify({"error": "webhook_secret_missing"}), 503
            if not stripe_service.verify_webhook_signature(payload_raw, sig):
                return jsonify({"error": "invalid_signature"}), 400
        elif stripe_service._webhook_secret():
            if not stripe_service.verify_webhook_signature(payload_raw, sig):
                return jsonify({"error": "invalid_signature"}), 400
        try:
            event = request.get_json(silent=True) or {}
            if not event and payload_raw:
                import json

                event = json.loads(payload_raw.decode("utf-8"))
        except Exception:
            return jsonify({"error": "invalid_payload"}), 400
        try:
            result = stripe_service.handle_webhook_event(get_db(), event)
            return jsonify({"received": True, **result})
        except Exception as exc:
            return jsonify({"error": "webhook_processing_failed", "detail": str(exc)}), 500

    register_blueprint_once(flask_app, billing_core_bp, url_prefix="/api")
    register_blueprint_once(flask_app, billing_v2_bp, url_prefix="/api/v2")
    print("[baupass] domain/billing: /api/invoices/* + /api/v2/billing/* registered", flush=True)
