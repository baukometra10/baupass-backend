"""Billing domain — invoice routes + v2 overview."""
from __future__ import annotations

from flask import Blueprint, Flask

from ..shared import company_id_from_user, forbidden_company
from .service import BillingService

billing_core_bp = Blueprint("billing_domain_core", __name__)
billing_v2_bp = Blueprint("billing_domain_v2", __name__)
_service = BillingService()


def _register_core_billing_routes() -> None:
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
        return _service.subscription_overview(get_db(), cid)

    flask_app.register_blueprint(billing_core_bp, url_prefix="/api")
    flask_app.register_blueprint(billing_v2_bp, url_prefix="/api/v2")
    print("[baupass] domain/billing: all /api/invoices/* routes on billing_core_bp", flush=True)
