"""Unified SSO provider catalog for enterprise buyers and admin UI."""
from __future__ import annotations

import os

from flask import Flask, jsonify


def register_sso_catalog_routes(flask_app: Flask) -> None:
    @flask_app.get("/api/auth/sso/catalog")
    def sso_catalog():
        from .entra_oidc import entra_config
        from .google_oidc import google_config
        from .keycloak_oidc import keycloak_config
        from .saml_sp import saml_config

        entra = entra_config()
        google = google_config()
        keycloak = keycloak_config()
        saml = saml_config()
        ad_via_entra = bool(entra)  # Entra ID + AD Connect is the supported AD path today

        providers = [
            {
                "id": "entra",
                "protocol": "oidc",
                "label": "Microsoft Entra ID",
                "status": "active" if entra else "available",
                "loginPath": "/api/auth/entra/start" if entra else None,
                "notes": "Includes Microsoft 365; maps to on-prem AD via Entra Connect.",
            },
            {
                "id": "google",
                "protocol": "oidc",
                "label": "Google Workspace",
                "status": "active" if google else "available",
                "loginPath": "/api/auth/google/start" if google else None,
            },
            {
                "id": "keycloak",
                "protocol": "oidc",
                "label": "Keycloak / Generic OIDC",
                "status": "active" if keycloak else "available",
                "loginPath": "/api/auth/keycloak/start" if keycloak else None,
            },
            {
                "id": "saml",
                "protocol": "saml2",
                "label": "SAML 2.0",
                "status": "active" if saml else "planned",
                "loginPath": "/api/auth/saml/start" if saml else None,
            },
            {
                "id": "active_directory",
                "protocol": "federation",
                "label": "Active Directory",
                "status": "active" if ad_via_entra else "planned",
                "loginPath": "/api/auth/entra/start" if ad_via_entra else None,
                "notes": "Use Entra ID with AD Connect, or Keycloak LDAP federation.",
            },
        ]
        return jsonify(
            {
                "providers": providers,
                "recommendedOrder": ["entra", "keycloak", "saml", "google"],
                "redisStateRecommended": bool(
                    os.getenv("REDIS_URL", "").strip()
                    or os.getenv("BAUPASS_SSO_STATE_REDIS", "").strip().lower() in {"1", "true", "yes"}
                ),
            }
        )
