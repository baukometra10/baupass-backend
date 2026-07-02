"""OpenAPI document route."""
from __future__ import annotations

from flask import Blueprint, Flask, jsonify, request

from .openapi_spec import build_openapi_document

openapi_bp = Blueprint("openapi_api", __name__)


@openapi_bp.get("/v1/openapi.json")
def openapi_json():
    base = request.url_root.rstrip("/")
    return jsonify(build_openapi_document(base))


def register_openapi_blueprint(flask_app: Flask) -> None:
    flask_app.register_blueprint(openapi_bp, url_prefix="/api")
    print("[baupass] api/openapi: GET /api/v1/openapi.json", flush=True)
