"""SAML SP helpers — redirect URL and metadata."""
from __future__ import annotations

import os
import unittest

from backend.app.platform.auth.saml_flow import (
    build_authn_redirect,
    sp_metadata_xml,
)


class SamlFlowTest(unittest.TestCase):
    def test_build_authn_redirect_contains_idp_and_request(self):
        cfg = {
            "entity_id": "https://app.example/sp",
            "acs_url": "https://app.example/api/auth/saml/acs",
            "idp_sso_url": "https://idp.example/sso",
            "idp_cert_pem": "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----",
        }
        url = build_authn_redirect(cfg)
        self.assertIn("https://idp.example/sso", url)
        self.assertIn("SAMLRequest=", url)
        self.assertIn("RelayState=", url)

    def test_sp_metadata_xml(self):
        cfg = {
            "entity_id": "https://app.example/sp",
            "acs_url": "https://app.example/api/auth/saml/acs",
            "idp_sso_url": "https://idp.example/sso",
            "idp_cert_pem": "x",
        }
        xml = sp_metadata_xml(cfg)
        self.assertIn("https://app.example/sp", xml)
        self.assertIn("https://app.example/api/auth/saml/acs", xml)


class SamlRoutesTest(unittest.TestCase):
    def test_saml_status_unconfigured(self):
        from backend.server import app

        old = os.environ.pop("BAUPASS_SAML_ENTITY_ID", None)
        try:
            client = app.test_client()
            res = client.get("/api/auth/saml/status")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertFalse(data.get("configured"))
        finally:
            if old is not None:
                os.environ["BAUPASS_SAML_ENTITY_ID"] = old


if __name__ == "__main__":
    unittest.main()
