"""Operations domain — incidents, messages, media evidence, snapshot."""
from __future__ import annotations

from flask import Blueprint, Flask

operations_core_bp = Blueprint("operations_domain_core", __name__)


def _register_core_operations_routes() -> None:
    from .._routes import mark_routes_mounted, routes_already_mounted, register_blueprint_once

    if routes_already_mounted("operations"):
        return
    from backend.server import (
        incidents_assign,
        incidents_get,
        incidents_report,
        incidents_resolve,
        media_evidence_get,
        media_evidence_upload,
        messages_get,
        messages_mark_read,
        messages_send,
        operations_guidance,
        operations_snapshot,
    )

    rules = (
        ("/ops/guidance", operations_guidance, ("GET",)),
        ("/operations/snapshot", operations_snapshot, ("GET",)),
        ("/messages", messages_send, ("POST",)),
        ("/messages", messages_get, ("GET",)),
        ("/messages/<msg_id>/mark-read", messages_mark_read, ("POST",)),
        ("/incidents", incidents_get, ("GET",)),
        ("/incidents", incidents_report, ("POST",)),
        ("/incidents/<incident_id>/assign", incidents_assign, ("POST",)),
        ("/incidents/<incident_id>/resolve", incidents_resolve, ("POST",)),
        ("/media-evidence", media_evidence_upload, ("POST",)),
        ("/media-evidence/<incident_id>", media_evidence_get, ("GET",)),
    )
    for path, view_func, methods in rules:
        operations_core_bp.add_url_rule(path, view_func=view_func, methods=list(methods))
    mark_routes_mounted("operations")


def register_operations_blueprint(flask_app: Flask) -> None:
    _register_core_operations_routes()
    register_blueprint_once(flask_app, operations_core_bp, url_prefix="/api")
    print("[baupass] domain/operations: snapshot, messages, incidents, media-evidence", flush=True)
