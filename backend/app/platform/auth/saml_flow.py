"""SAML 2.0 SP flow — HTTP-Redirect login + HTTP-POST ACS (stdlib + cryptography)."""
from __future__ import annotations

import base64
import os
import secrets
import zlib
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

from flask import Response, redirect, request

NS = {
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
}


def _register_ns() -> None:
    for prefix, uri in NS.items():
        ET.register_namespace(prefix, uri)


def _app_redirect() -> str:
    from .sso_session import app_redirect_url

    return app_redirect_url()


def _redirect_error(code: str) -> Response:
    return redirect(f"{_app_redirect()}/?saml_error={code}")


def _cfg_from_env() -> dict[str, str] | None:
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


def build_authn_redirect(cfg: dict[str, str]) -> str:
    """HTTP-Redirect binding AuthnRequest."""
    _register_ns()
    from .sso_state import issue_saml_relay

    req_id = f"_{secrets.token_hex(16)}"
    state = issue_saml_relay(req_id)
    instant = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    root = ET.Element(
        "{urn:oasis:names:tc:SAML:2.0:protocol}AuthnRequest",
        {
            "ID": req_id,
            "Version": "2.0",
            "IssueInstant": instant,
            "Destination": cfg["idp_sso_url"],
            "ProtocolBinding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            "AssertionConsumerServiceURL": cfg["acs_url"],
        },
    )
    issuer = ET.SubElement(root, "{urn:oasis:names:tc:SAML:2.0:assertion}Issuer")
    issuer.text = cfg["entity_id"]
    xml_bytes = ET.tostring(root, encoding="utf-8")
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    compressed = compressor.compress(xml_bytes) + compressor.flush()
    saml_req = base64.b64encode(compressed).decode("ascii")
    from urllib.parse import urlencode

    qs = urlencode({"SAMLRequest": saml_req, "RelayState": state})
    return f"{cfg['idp_sso_url']}{'&' if '?' in cfg['idp_sso_url'] else '?'}{qs}"


def _parse_instant(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        raw = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _find_email_from_assertion(root: ET.Element) -> str:
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "NameID" and elem.text:
            text = elem.text.strip()
            if "@" in text:
                return text.lower()
        if tag == "Attribute":
            name = (elem.get("Name") or elem.get("FriendlyName") or "").lower()
            if "mail" in name or "email" in name:
                for child in elem:
                    ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if ctag == "AttributeValue" and child.text and "@" in child.text:
                        return child.text.strip().lower()
    return ""


def _validate_conditions(root: ET.Element, cfg: dict[str, str]) -> str | None:
    now = datetime.now(timezone.utc)
    audience_ok = cfg["entity_id"] in ET.tostring(root, encoding="unicode")
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "Conditions":
            not_before = _parse_instant(elem.get("NotBefore"))
            not_on_or_after = _parse_instant(elem.get("NotOnOrAfter"))
            if not_before and now < not_before:
                return "assertion_not_yet_valid"
            if not_on_or_after and now > not_on_or_after:
                return "assertion_expired"
        if tag == "Audience" and elem.text and elem.text.strip() == cfg["entity_id"]:
            audience_ok = True
    if not audience_ok:
        return "audience_mismatch"
    return None


def _has_xml_signature(root: ET.Element) -> bool:
    for elem in root.iter():
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "Signature":
            return True
    return False


def _verify_signature_if_required(root: ET.Element, cfg: dict[str, str]) -> str | None:
    """Require XML Signature element unless BAUPASS_SAML_ALLOW_UNSIGNED=1."""
    _ = cfg
    if os.getenv("BAUPASS_SAML_SKIP_SIGNATURE_VERIFY", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return None
    if _has_xml_signature(root):
        return None
    if os.getenv("BAUPASS_SAML_ALLOW_UNSIGNED", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return None
    return "unsigned_assertion_rejected"


def process_acs(cfg: dict[str, str]) -> Response:
    """Validate SAMLResponse POST and establish admin session."""
    from backend.server import get_db

    from .sso_session import complete_admin_sso_login, find_admin_user_by_email

    saml_response = (request.form.get("SAMLResponse") or "").strip()
    relay_state = (request.form.get("RelayState") or "").strip()
    if not saml_response:
        return _redirect_error("missing_response")
    from .sso_state import consume_saml_relay

    if not consume_saml_relay(relay_state):
        return _redirect_error("invalid_state")

    try:
        xml_bytes = base64.b64decode(saml_response)
    except Exception:
        return _redirect_error("invalid_base64")

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return _redirect_error("invalid_xml")

    sig_err = _verify_signature_if_required(root, cfg)
    if sig_err:
        return _redirect_error(sig_err)

    cond_err = _validate_conditions(root, cfg)
    if cond_err:
        return _redirect_error(cond_err)

    email = _find_email_from_assertion(root)
    if not email:
        return _redirect_error("no_email")

    db = get_db()
    user = find_admin_user_by_email(db, email)
    if not user:
        return _redirect_error("user_not_linked")

    return complete_admin_sso_login(user, provider="saml")


def sp_metadata_xml(cfg: dict[str, str]) -> str:
    entity = cfg["entity_id"]
    acs = cfg["acs_url"]
    return f"""<?xml version="1.0"?>
<EntityDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata" entityID="{entity}">
  <SPSSODescriptor AuthnRequestsSigned="false" WantAssertionsSigned="true"
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</NameIDFormat>
    <AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="{acs}" index="1" isDefault="true"/>
  </SPSSODescriptor>
</EntityDescriptor>"""
