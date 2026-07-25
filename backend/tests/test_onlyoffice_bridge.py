"""OnlyOffice bridge unit tests (no Docker required)."""
from __future__ import annotations

from backend.app.domains.docs import onlyoffice as oo


def test_sign_and_verify_jwt_roundtrip():
    token = oo.sign_jwt({"purpose": "oo_file", "doc_id": "d1", "company_id": "c1"}, ttl_sec=120)
    payload = oo.verify_jwt(token)
    assert payload is not None
    assert payload["purpose"] == "oo_file"
    assert payload["doc_id"] == "d1"


def test_build_docx_bytes_contains_ooxml():
    data = oo.build_docx_bytes(title="Brief", html="<p>Hallo <strong>Welt</strong></p><p>Zeile 2</p>")
    assert data[:2] == b"PK"
    assert len(data) > 200


def test_html_to_paragraphs():
    paras = oo.html_to_paragraphs("<p>Eins</p><p>Zwei</p>")
    assert "Eins" in paras
    assert "Zwei" in paras
