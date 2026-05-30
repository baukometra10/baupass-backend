"""Reporting API routes (migrated from backend/server.py)."""
from __future__ import annotations

from flask import Blueprint, Flask

reporting_domain_bp = Blueprint("reporting_domain", __name__)


def register_reporting_blueprint(flask_app: Flask) -> None:
    """Attach legacy reporting handlers; logic stays in server until fully extracted."""
    from backend.server import (
        reporting_daily_pdf_run,
        reporting_email_companies_pdf,
        reporting_email_datev_csv,
        reporting_email_enterprise_pdf,
        reporting_email_executive_pdf,
        reporting_email_incidents_visits_pdf,
        reporting_email_invoices_pdf,
        reporting_email_pdf,
        reporting_summary,
    )

    rules = (
        ("/reporting/summary", reporting_summary, ("GET",)),
        ("/reporting/email-pdf", reporting_email_pdf, ("POST",)),
        ("/reporting/email-datev-csv", reporting_email_datev_csv, ("POST",)),
        ("/reporting/daily-pdf/run", reporting_daily_pdf_run, ("POST",)),
        ("/reporting/email-invoices-pdf", reporting_email_invoices_pdf, ("POST",)),
        ("/reporting/email-companies-pdf", reporting_email_companies_pdf, ("POST",)),
        ("/reporting/email-enterprise-pdf", reporting_email_enterprise_pdf, ("POST",)),
        ("/reporting/email-executive-pdf", reporting_email_executive_pdf, ("POST",)),
        ("/reporting/email-incidents-visits-pdf", reporting_email_incidents_visits_pdf, ("POST",)),
    )
    for path, view_func, methods in rules:
        reporting_domain_bp.add_url_rule(path, view_func=view_func, methods=list(methods))

    flask_app.register_blueprint(reporting_domain_bp, url_prefix="/api")
    print("[baupass] domain/reporting: 9 routes registered", flush=True)
