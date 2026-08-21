"""SAML XML signature verify (RSA-SHA256) using the IdP certificate.

Fail-closed: unsigned assertions are rejected unless an explicit test flag is set.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
from xml.etree import ElementTree as ET

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
from cryptography.hazmat.primitives.serialization import Encoding

DS_NS = "http://www.w3.org/2000/09/xmldsig#"
_ID_ATTRS = ("ID", "Id", "id")


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _find_all(root: ET.Element, local: str) -> list[ET.Element]:
    return [el for el in root.iter() if _local(el.tag) == local]


def load_idp_cert(pem: str) -> x509.Certificate:
    text = str(pem or "").strip()
    if "BEGIN CERTIFICATE" not in text:
        text = "-----BEGIN CERTIFICATE-----\n" + text + "\n-----END CERTIFICATE-----"
    return x509.load_pem_x509_certificate(text.encode("ascii"))


def cert_fingerprint(cert: x509.Certificate) -> str:
    return cert.fingerprint(hashes.SHA256()).hex()


def _element_by_id(root: ET.Element, ident: str) -> ET.Element | None:
    want = ident.lstrip("#")
    for el in root.iter():
        for attr in _ID_ATTRS:
            if el.get(attr) == want:
                return el
    return None


def _exc_c14n(elem: ET.Element, *, inherited_ns: dict[str, str] | None = None) -> bytes:
    """Exclusive C14N subset sufficient for SAML SignedInfo / Assertion."""
    inherited_ns = dict(inherited_ns or {})
    ns, local = ("", elem.tag)
    if elem.tag.startswith("{"):
        ns, local = elem.tag[1:].split("}", 1)
    used: dict[str, str] = {}
    if ns:
        prefix = ""
        for pfx, uri in inherited_ns.items():
            if uri == ns:
                prefix = pfx
                break
        if prefix:
            used[prefix] = ns
        else:
            used[""] = ns
    attrs = []
    for key, val in elem.attrib.items():
        if key == "xmlns" or key.startswith("xmlns:"):
            continue
        if key.startswith("{"):
            ans, aname = key[1:].split("}", 1)
            attrs.append((ans, aname, val))
            if ans not in used.values():
                used[f"ns{len(used)}"] = ans
        else:
            attrs.append(("", key, val))
    ns_decls = []
    for pfx, uri in sorted(used.items(), key=lambda kv: kv[0]):
        if pfx:
            ns_decls.append(f' xmlns:{pfx}="{uri}"')
        else:
            ns_decls.append(f' xmlns="{uri}"')
    prefix_for = {uri: pfx for pfx, uri in used.items()}
    qname = local if not ns or not prefix_for.get(ns) else f"{prefix_for[ns]}:{local}"
    attr_xml = []
    for ans, aname, val in sorted(attrs, key=lambda t: (t[0], t[1])):
        if ans:
            pfx = prefix_for.get(ans) or ""
            attr_xml.append(f' {pfx}:{aname}="{_esc(val)}"' if pfx else f' {aname}="{_esc(val)}"')
        else:
            attr_xml.append(f' {aname}="{_esc(val)}"')
    open_tag = f"<{qname}{''.join(ns_decls)}{''.join(attr_xml)}>"
    parts = [open_tag.encode("utf-8")]
    if elem.text:
        parts.append(_esc(elem.text).encode("utf-8"))
    child_inherited = dict(inherited_ns)
    child_inherited.update(used)
    for child in list(elem):
        parts.append(_exc_c14n(child, inherited_ns=child_inherited))
        if child.tail:
            parts.append(_esc(child.tail).encode("utf-8"))
    parts.append(f"</{qname}>".encode("utf-8"))
    return b"".join(parts)


def _esc(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\r", "&#xD;")
    )


def _strip_signatures(elem: ET.Element) -> ET.Element:
    clone = ET.fromstring(ET.tostring(elem, encoding="utf-8"))
    for parent in clone.iter():
        for child in list(parent):
            if _local(child.tag) == "Signature":
                parent.remove(child)
    return clone


def verify_saml_xml_signature(xml_bytes: bytes, idp_cert_pem: str) -> str | None:
    """Return an error code, or None when the signature is valid.

    Hardening beyond basic RSA-SHA256:
    - reject responses with multiple unsigned sibling Assertions (wrapping)
    - require Signature Reference to target an Assertion (or Response) ID
    - reject empty URI references that would hash the whole document ambiguously
      when more than one Assertion exists
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return "invalid_xml"
    assertions = _find_all(root, "Assertion")
    if len(assertions) > 1:
        # Classic wrapping: only one assertion may be present unless every assertion is signed.
        signed_ids = set()
        for sig in _find_all(root, "Signature"):
            for ref in _find_all(sig, "Reference"):
                uri = (ref.get("URI") or "").strip()
                if uri.startswith("#"):
                    signed_ids.add(uri.lstrip("#"))
        for assertion in assertions:
            aid = ""
            for attr in _ID_ATTRS:
                if assertion.get(attr):
                    aid = assertion.get(attr) or ""
                    break
            if not aid or aid not in signed_ids:
                return "assertion_wrapping_rejected"
    sigs = _find_all(root, "Signature")
    if not sigs:
        return "unsigned_assertion_rejected"
    try:
        idp_cert = load_idp_cert(idp_cert_pem)
    except Exception:
        return "idp_cert_invalid"
    idp_fp = cert_fingerprint(idp_cert)
    sig = sigs[0]
    for assertion in assertions:
        for child in list(assertion):
            if _local(child.tag) == "Signature":
                sig = child
                break
    signed_info = next((c for c in list(sig) if _local(c.tag) == "SignedInfo"), None)
    sig_val_el = next((c for c in list(sig) if _local(c.tag) == "SignatureValue"), None)
    if signed_info is None or sig_val_el is None or not (sig_val_el.text or "").strip():
        return "signature_incomplete"
    embedded = None
    for el in sig.iter():
        if _local(el.tag) == "X509Certificate" and el.text:
            embedded = el.text.strip()
            break
    if embedded:
        try:
            emb_cert = load_idp_cert(embedded)
            if cert_fingerprint(emb_cert) != idp_fp:
                return "signing_cert_mismatch"
        except Exception:
            return "signing_cert_invalid"
    try:
        signature = base64.b64decode(re.sub(r"\s+", "", sig_val_el.text or ""), validate=False)
        digest = hashlib.sha256(_exc_c14n(signed_info)).digest()
        idp_cert.public_key().verify(  # type: ignore[union-attr]
            signature,
            digest,
            padding.PKCS1v15(),
            Prehashed(hashes.SHA256()),
        )
    except Exception:
        return "signature_invalid"
    refs = _find_all(signed_info, "Reference")
    if not refs:
        return "signed_reference_missing"
    for ref in refs:
        uri = (ref.get("URI") or "").strip()
        if not uri:
            if len(assertions) > 1:
                return "ambiguous_empty_reference"
            target = assertions[0] if assertions else root
        elif uri.startswith("#"):
            target = _element_by_id(root, uri)
        else:
            return "unsupported_reference_uri"
        if target is None:
            return "signed_reference_missing"
        digest_el = next((c for c in ref.iter() if _local(c.tag) == "DigestValue"), None)
        if digest_el is None or not (digest_el.text or "").strip():
            return "digest_missing"
        hashed = hashlib.sha256(_exc_c14n(_strip_signatures(target))).digest()
        expected = base64.b64decode(re.sub(r"\s+", "", digest_el.text or ""), validate=False)
        if hashed != expected:
            return "digest_mismatch"
    # Require at least one signed Assertion reference (not only Response).
    if assertions:
        assertion_ids = set()
        for assertion in assertions:
            for attr in _ID_ATTRS:
                if assertion.get(attr):
                    assertion_ids.add(assertion.get(attr))
                    break
        referenced = set()
        for ref in refs:
            uri = (ref.get("URI") or "").strip()
            if uri.startswith("#"):
                referenced.add(uri.lstrip("#"))
        if assertion_ids and referenced.isdisjoint(assertion_ids):
            # Allow Response-level signature only when a single Assertion is nested
            # and enveloped transform covers it — still require assertion ID present.
            if len(assertions) != 1:
                return "assertion_not_referenced"
    # Optional stronger verifier when signxml is installed.
    if (os.getenv("BAUPASS_SAML_USE_SIGNXML") or "").strip().lower() in {"1", "true", "yes"}:
        try:
            from signxml import XMLVerifier  # type: ignore

            XMLVerifier().verify(xml_bytes, x509_cert=idp_cert_pem)
        except ImportError:
            return "signxml_not_installed"
        except Exception:
            return "signxml_verify_failed"
    return None


def sign_saml_xml_for_tests(xml_bytes: bytes, key: rsa.RSAPrivateKey, cert: x509.Certificate) -> bytes:
    """Attach an enveloped RSA-SHA256 signature (test helper)."""
    root = ET.fromstring(xml_bytes)
    assertion = next((el for el in root.iter() if _local(el.tag) == "Assertion"), root)
    aid = assertion.get("ID") or "_a1"
    assertion.set("ID", aid)
    ds = "{%s}" % DS_NS
    signed_info = ET.Element(ds + "SignedInfo")
    ET.SubElement(
        signed_info,
        ds + "CanonicalizationMethod",
        {"Algorithm": "http://www.w3.org/2001/10/xml-exc-c14n#"},
    )
    ET.SubElement(
        signed_info,
        ds + "SignatureMethod",
        {"Algorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"},
    )
    ref = ET.SubElement(signed_info, ds + "Reference", {"URI": f"#{aid}"})
    transforms = ET.SubElement(ref, ds + "Transforms")
    ET.SubElement(
        transforms,
        ds + "Transform",
        {"Algorithm": "http://www.w3.org/2000/09/xmldsig#enveloped-signature"},
    )
    ET.SubElement(ref, ds + "DigestMethod", {"Algorithm": "http://www.w3.org/2001/04/xmlenc#sha256"})
    digest_val = ET.SubElement(ref, ds + "DigestValue")
    digest_val.text = base64.b64encode(hashlib.sha256(_exc_c14n(_strip_signatures(assertion))).digest()).decode("ascii")
    sig_bytes = key.sign(
        hashlib.sha256(_exc_c14n(signed_info)).digest(),
        padding.PKCS1v15(),
        Prehashed(hashes.SHA256()),
    )
    signature = ET.Element(ds + "Signature")
    signature.append(signed_info)
    ET.SubElement(signature, ds + "SignatureValue").text = base64.b64encode(sig_bytes).decode("ascii")
    key_info = ET.SubElement(signature, ds + "KeyInfo")
    x509data = ET.SubElement(key_info, ds + "X509Data")
    der = cert.public_bytes(Encoding.DER)
    ET.SubElement(x509data, ds + "X509Certificate").text = base64.b64encode(der).decode("ascii")
    assertion.insert(0, signature)
    return ET.tostring(root, encoding="utf-8")
