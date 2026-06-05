"""Companies domain — legacy /api/companies/* routes."""
from __future__ import annotations

from flask import Blueprint, Flask

from .._routes import register_blueprint_once

companies_core_bp = Blueprint("companies_domain_core", __name__)


def _register_core_company_routes() -> None:
    from .._routes import mark_routes_mounted, routes_already_mounted, register_blueprint_once

    if routes_already_mounted("companies"):
        return
    from backend.server import (
        add_company_turnstile,
        company_worker_hours_summary,
        company_worker_timeline,
        companies_collection,
        create_company_mail_settings_endpoint,
        delete_company,
        export_company_document_emails_csv,
        get_company_admin_security,
        get_company_mail_settings_endpoint,
        get_company_plan_features,
        get_company_work_times,
        create_subcompany,
        list_company_turnstiles,
        list_subcompanies,
        repair_company,
        reset_turnstile_password,
        restore_company,
        rotate_turnstile_api_key,
        set_company_admin_password,
        set_company_admin_security,
        test_company_mail_inbound_endpoint,
        test_company_mail_outbound_endpoint,
        toggle_company_review_access,
        toggle_turnstile_active,
        update_company,
        update_company_mail_settings_endpoint,
        update_company_work_times,
    )

    rules = (
        ("/companies/document-emails/export", export_company_document_emails_csv, ("GET",)),
        ("/subcompanies", list_subcompanies, ("GET",)),
        ("/subcompanies", create_subcompany, ("POST",)),
        ("/companies", companies_collection, ("GET", "POST")),
        ("/companies/<company_id>", update_company, ("PUT",)),
        ("/companies/<company_id>", delete_company, ("DELETE",)),
        ("/companies/<company_id>/mail-settings", get_company_mail_settings_endpoint, ("GET",)),
        ("/companies/<company_id>/mail-settings", create_company_mail_settings_endpoint, ("POST",)),
        ("/companies/<company_id>/mail-settings", update_company_mail_settings_endpoint, ("PUT",)),
        (
            "/companies/<company_id>/mail-settings/test-inbound",
            test_company_mail_inbound_endpoint,
            ("POST",),
        ),
        (
            "/companies/<company_id>/mail-settings/test-outbound",
            test_company_mail_outbound_endpoint,
            ("POST",),
        ),
        ("/companies/<company_id>/work-times", get_company_work_times, ("GET",)),
        ("/companies/<company_id>/work-times", update_company_work_times, ("PUT",)),
        ("/companies/<company_id>/admin-security", set_company_admin_security, ("PUT",)),
        ("/companies/<company_id>/admin-security", get_company_admin_security, ("GET",)),
        ("/companies/<company_id>/set-admin-password", set_company_admin_password, ("POST",)),
        ("/companies/<company_id>/add-turnstile", add_company_turnstile, ("POST",)),
        ("/companies/<company_id>/turnstiles", list_company_turnstiles, ("GET",)),
        (
            "/companies/<company_id>/turnstiles/<user_id>/reset-password",
            reset_turnstile_password,
            ("POST",),
        ),
        (
            "/companies/<company_id>/turnstiles/<user_id>/rotate-api-key",
            rotate_turnstile_api_key,
            ("POST",),
        ),
        (
            "/companies/<company_id>/turnstiles/<user_id>/toggle-active",
            toggle_turnstile_active,
            ("POST",),
        ),
        ("/companies/<company_id>/repair", repair_company, ("POST",)),
        ("/companies/<company_id>/restore", restore_company, ("POST",)),
        ("/companies/<company_id>/review-access", toggle_company_review_access, ("PUT",)),
        ("/companies/<company_id>/worker-hours-summary", company_worker_hours_summary, ("GET",)),
        (
            "/companies/<company_id>/workers/<worker_id>/timeline",
            company_worker_timeline,
            ("GET",),
        ),
        ("/companies/<company_id>/plan-features", get_company_plan_features, ("GET",)),
    )
    for path, view_func, methods in rules:
        companies_core_bp.add_url_rule(path, view_func=view_func, methods=list(methods))
    mark_routes_mounted("companies")


def register_companies_blueprint(flask_app: Flask) -> None:
    _register_core_company_routes()
    register_blueprint_once(flask_app, companies_core_bp, url_prefix="/api")
    print("[baupass] domain/companies: all /api/companies/* routes on companies_core_bp", flush=True)
