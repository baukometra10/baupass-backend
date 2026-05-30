"""SAML 2.0 Service Provider — metadata + ACS scaffold (full IdP wiring in progress)."""
from __future__ import annotations

import os

from flask import Flask, jsonify, request


def saml_config() -> dict[str, str] | None:
    entity_id = (os.getenv("BAUPASS_SAML_ENTITY_ID") or "").strip()
    acs_url = (os.getenv("BAUPASS_SAML_ACS_URL") or "").strip()
    idp_sso_url = (os.getenv("BAUPASS_SAML_IDP_SSO_URL") or "").strip()
    idp_cert = (os.getenv("BAUPASS_SAML_IDP_CERT_PEM") or "").strip()
    if not (entity_id and acs_url and idp_sso_url and idp_cert):
        return None
    return {
        "entity_id": entity_id,
        "acs_url": acs_url,
        "idp_sso_url": idp_sso_url,
        "idp_cert_pem": idp_cert,
    }


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
                "implementation": "scaffold",
            }
        )

    @flask_app.get("/api/auth/saml/metadata")
    def saml_metadata():
        cfg = saml_config()
        if not cfg:
            return jsonify({"error": "saml_not_configured"}), 503
        # Minimal SP metadata placeholder — replace with signed XML when python3-saml is enabled.
        return jsonify(
            {
                "entityId": cfg["entity_id"],
                "assertionConsumerServiceURL": cfg["acs_url"],
                "note": "Use env BAUPASS_SAML_* ; full SAML response validation ships in next enterprise release.",
            }
        )

    @flask_app.post("/api/auth/saml/acs")
    def saml_acs():
        cfg = saml_config()
        if not cfg:
            return jsonify({"error": "saml_not_configured"}), 503
        return jsonify(
            {
                "ok": False,
                "error": "saml_acs_not_implemented",
                "message": "SAML ACS validation is in progress. Use Entra/Google/Keycloak OIDC meanwhile.",
            }
        ), 501

    @flask_app.get("/api/auth/saml/start")
    def saml_start():
        cfg = saml_config()
        if not cfg:
            return jsonify({"error": "saml_not_configured"}), 503
        return jsonify(
            {
                "ok": False,
                "error": "saml_redirect_not_implemented",
                "idpSsoUrl": cfg["idp_sso_url"],
                "message": "Configure OIDC via Entra or Keycloak until SAML redirect is released.",
            }
        ), 501
