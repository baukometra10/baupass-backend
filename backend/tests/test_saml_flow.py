"""SAML SP helpers — redirect URL, metadata, and strict XML signature."""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from backend.app.platform.auth.saml_flow import (
    build_authn_redirect,
    sp_metadata_xml,
    validate_saml_response_xml,
)
from backend.app.platform.auth.saml_signature import (
    sign_saml_xml_for_tests,
    verify_saml_xml_signature,
)


def _idp_material():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-idp")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(Encoding.PEM).decode("ascii")
    return key, cert, pem


def _unsigned_response(*, req_id: str, assertion_id: str, entity: str, acs: str, audience: str | None = None) -> bytes:
    now = datetime.now(timezone.utc)
    instant = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    later = (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    earlier = (now - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    aud = audience if audience is not None else entity
    return f"""<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
      xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
      ID="_r1" Version="2.0" IssueInstant="{instant}"
      Destination="{acs}" InResponseTo="{req_id}">
      <saml:Assertion ID="{assertion_id}" Version="2.0" IssueInstant="{instant}">
        <saml:Issuer>https://idp.example</saml:Issuer>
        <saml:Subject>
          <saml:NameID>admin@example.com</saml:NameID>
          <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
            <saml:SubjectConfirmationData Recipient="{acs}" NotOnOrAfter="{later}" InResponseTo="{req_id}"/>
          </saml:SubjectConfirmation>
        </saml:Subject>
        <saml:Conditions NotBefore="{earlier}" NotOnOrAfter="{later}">
          <saml:AudienceRestriction>
            <saml:Audience>{aud}</saml:Audience>
          </saml:AudienceRestriction>
        </saml:Conditions>
      </saml:Assertion>
    </samlp:Response>""".encode("utf-8")


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


class SamlSignatureTest(unittest.TestCase):
    def setUp(self):
        os.environ.pop("BAUPASS_SAML_ALLOW_UNSIGNED", None)
        os.environ.pop("BAUPASS_SAML_SKIP_SIGNATURE_VERIFY", None)
        os.environ.pop("BAUPASS_ENV", None)
        self.key, self.cert, self.pem = _idp_material()
        self.cfg = {
            "entity_id": "https://app.example/sp",
            "acs_url": "https://app.example/api/auth/saml/acs",
            "idp_sso_url": "https://idp.example/sso",
            "idp_cert_pem": self.pem,
        }

    def test_unsigned_rejected(self):
        xml = _unsigned_response(
            req_id="_req1",
            assertion_id="_a-unsigned",
            entity=self.cfg["entity_id"],
            acs=self.cfg["acs_url"],
        )
        self.assertEqual(verify_saml_xml_signature(xml, self.pem), "unsigned_assertion_rejected")
        err = validate_saml_response_xml(xml, self.cfg, expected_request_id="_req1")
        self.assertEqual(err, "unsigned_assertion_rejected")

    def test_signed_assertion_accepted(self):
        xml = _unsigned_response(
            req_id="_req2",
            assertion_id="_a-ok",
            entity=self.cfg["entity_id"],
            acs=self.cfg["acs_url"],
        )
        signed = sign_saml_xml_for_tests(xml, self.key, self.cert)
        self.assertIsNone(verify_saml_xml_signature(signed, self.pem))
        self.assertIsNone(validate_saml_response_xml(signed, self.cfg, expected_request_id="_req2"))

    def test_audience_mismatch(self):
        xml = _unsigned_response(
            req_id="_req3",
            assertion_id="_a-aud",
            entity=self.cfg["entity_id"],
            acs=self.cfg["acs_url"],
            audience="https://other.example/sp",
        )
        signed = sign_saml_xml_for_tests(xml, self.key, self.cert)
        err = validate_saml_response_xml(signed, self.cfg, expected_request_id="_req3")
        self.assertEqual(err, "audience_mismatch")

    def test_in_response_to_mismatch(self):
        xml = _unsigned_response(
            req_id="_req4",
            assertion_id="_a-irt",
            entity=self.cfg["entity_id"],
            acs=self.cfg["acs_url"],
        )
        signed = sign_saml_xml_for_tests(xml, self.key, self.cert)
        err = validate_saml_response_xml(signed, self.cfg, expected_request_id="_other")
        self.assertEqual(err, "in_response_to_mismatch")

    def test_assertion_replay_rejected(self):
        xml = _unsigned_response(
            req_id="_req5",
            assertion_id="_a-replay",
            entity=self.cfg["entity_id"],
            acs=self.cfg["acs_url"],
        )
        signed = sign_saml_xml_for_tests(xml, self.key, self.cert)
        self.assertIsNone(validate_saml_response_xml(signed, self.cfg, expected_request_id="_req5"))
        self.assertEqual(
            validate_saml_response_xml(signed, self.cfg, expected_request_id="_req5"),
            "assertion_replay",
        )

    def test_wrapping_unsigned_sibling_rejected(self):
        now = datetime.now(timezone.utc)
        instant = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        later = (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        earlier = (now - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        xml = f"""<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
          xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
          ID="_rwrap" Version="2.0" IssueInstant="{instant}"
          Destination="{self.cfg['acs_url']}" InResponseTo="_reqw">
          <saml:Assertion ID="_a-evil" Version="2.0" IssueInstant="{instant}">
            <saml:Issuer>https://idp.example</saml:Issuer>
            <saml:Subject><saml:NameID>attacker@evil</saml:NameID></saml:Subject>
            <saml:Conditions NotBefore="{earlier}" NotOnOrAfter="{later}">
              <saml:AudienceRestriction><saml:Audience>{self.cfg['entity_id']}</saml:Audience></saml:AudienceRestriction>
            </saml:Conditions>
          </saml:Assertion>
          <saml:Assertion ID="_a-good" Version="2.0" IssueInstant="{instant}">
            <saml:Issuer>https://idp.example</saml:Issuer>
            <saml:Subject>
              <saml:NameID>admin@example.com</saml:NameID>
              <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
                <saml:SubjectConfirmationData Recipient="{self.cfg['acs_url']}" NotOnOrAfter="{later}" InResponseTo="_reqw"/>
              </saml:SubjectConfirmation>
            </saml:Subject>
            <saml:Conditions NotBefore="{earlier}" NotOnOrAfter="{later}">
              <saml:AudienceRestriction><saml:Audience>{self.cfg['entity_id']}</saml:Audience></saml:AudienceRestriction>
            </saml:Conditions>
          </saml:Assertion>
        </samlp:Response>""".encode("utf-8")
        # Sign only the good assertion — evil sibling remains unsigned → wrapping reject.
        signed = sign_saml_xml_for_tests(xml, self.key, self.cert)
        self.assertEqual(verify_saml_xml_signature(signed, self.pem), "assertion_wrapping_rejected")


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
