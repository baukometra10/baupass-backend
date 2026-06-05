"""Documents domain — inbox, IMAP, payroll export."""
from __future__ import annotations

from flask import Blueprint, Flask

documents_core_bp = Blueprint("documents_domain_core", __name__)


def _register_core_document_routes() -> None:
    from .._routes import mark_routes_mounted, routes_already_mounted, register_blueprint_once

    if routes_already_mounted("documents"):
        return
    from backend.server import (
        assign_attachment_to_worker,
        datev_oauth_callback,
        dismiss_inbox_email,
        export_payroll_datev_csv,
        list_document_inbox,
        list_expiring_documents,
        mark_inbox_email_read,
        rematch_document_inbox_links,
        reply_to_inbox_email,
        set_document_inbox_company_match,
        trigger_imap_poll,
    )

    rules = (
        ("/documents/expiring", list_expiring_documents, ("GET",)),
        ("/documents/imap/trigger", trigger_imap_poll, ("POST",)),
        ("/documents/inbox", list_document_inbox, ("GET",)),
        ("/documents/payroll/datev-export", export_payroll_datev_csv, ("GET",)),
        ("/documents/inbox/rematch-company-links", rematch_document_inbox_links, ("POST",)),
        ("/documents/inbox/<inbox_id>/match-company", set_document_inbox_company_match, ("POST",)),
        ("/documents/inbox/<inbox_id>/dismiss", dismiss_inbox_email, ("POST",)),
        ("/documents/inbox/<inbox_id>/mark-read", mark_inbox_email_read, ("POST",)),
        ("/documents/inbox/<inbox_id>/reply", reply_to_inbox_email, ("POST",)),
        (
            "/documents/inbox/<inbox_id>/attachments/<attachment_id>/assign",
            assign_attachment_to_worker,
            ("POST",),
        ),
        ("/integrations/datev/oauth/callback", datev_oauth_callback, ("GET",)),
    )
    for path, view_func, methods in rules:
        documents_core_bp.add_url_rule(path, view_func=view_func, methods=list(methods))
    mark_routes_mounted("documents")


def register_documents_blueprint(flask_app: Flask) -> None:
    _register_core_document_routes()
    register_blueprint_once(flask_app, documents_core_bp, url_prefix="/api")
    print("[baupass] domain/documents: inbox, imap, payroll export", flush=True)
