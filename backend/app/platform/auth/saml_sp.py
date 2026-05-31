"""SAML 2.0 Service Provider — login redirect + ACS session."""
from __future__ import annotations

from flask import Flask, Response, jsonify

from .saml_flow import (
    _cfg_from_env,
    build_authn_redirect,
    process_acs,
    sp_metadata_xml,
)


def saml_config() -> dict[str, str] | None:
    return _cfg_from_env()


def register_saml_auth_routes(flask_app: Flask) -> None:
    @flask_app.get("/api/auth/saml/status")
    def saml_status():
        cfg = saml_config()
        return jsonify(
            {
                "configured": bool(cfg),
                "entityId": cfg["entity_id"] if cfg else None,
                "acsUrl": cfg["acs_url"] if cfg else None,
                "loginPath": "/api/auth/saml/start" if cfg else None,
                "protocol": "saml2",
                "implementation": "native" if cfg else "scaffold",
            }
        )

    @flask_app.get("/api/auth/saml/metadata")
    def saml_metadata():
        cfg = saml_config()
        if not cfg:
            return jsonify({"error": "saml_not_configured"}), 503
        xml = sp_metadata_xml(cfg)
        return Response(xml, mimetype="application/samlmetadata+xml")

    @flask_app.get("/api/auth/saml/metadata.json")
    def saml_metadata_json():
        cfg = saml_config()
        if not cfg:
            return jsonify({"error": "saml_not_configured"}), 503
        return jsonify(
            {
                "entityId": cfg["entity_id"],
                "assertionConsumerServiceURL": cfg["acs_url"],
                "nameIdFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
            }
        )

    @flask_app.post("/api/auth/saml/acs")
    def saml_acs():
        cfg = saml_config()
        if not cfg:
            return jsonify({"error": "saml_not_configured"}), 503
        return process_acs(cfg)

    @flask_app.get("/api/auth/saml/start")
    def saml_start():
        cfg = saml_config()
        if not cfg:
            return jsonify({"error": "saml_not_configured"}), 503
        from flask import redirect

        return redirect(build_authn_redirect(cfg))
