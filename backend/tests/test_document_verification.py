"""Worker document verification hardening tests."""
from __future__ import annotations

from backend.app.platform.documents.verify import (
    sniff_mime,
    verify_worker_document_upload,
)


def _pdf_with_text(text: str) -> bytes:
    # Minimal PDF with extractable text (enough bytes + %PDF header).
    # pypdf may or may not extract this; we also pad size for min-bytes check.
    payload = text.encode("latin-1", errors="replace")
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj<<>>endobj\n"
        b"2 0 obj<< /Length "
        + str(len(payload) + 20).encode()
        + b" >>stream\nBT /F1 12 Tf 100 700 Td ("
        + payload
        + b") Tj ET\nendstream\nendobj\n"
        b"trailer<<>>\n%%EOF\n"
    )
    if len(body) < 900:
        body = body + b"\n%" + (b"x" * (900 - len(body)))
    return body


def test_sniff_rejects_html_as_pdf():
    assert sniff_mime(b"<!DOCTYPE html><html>fake</html>", "id.pdf") is None
    assert sniff_mime(b"%PDF-1.7\n...", "id.pdf") == "application/pdf"
    assert sniff_mime(b"\xff\xd8\xff\xe0" + b"\x00" * 100, "x.jpg") == "image/jpeg"


def test_reject_tiny_or_wrong_magic():
    bad = verify_worker_document_upload(
        doc_type="personalausweis",
        filename="id.pdf",
        claimed_mime="application/pdf",
        file_data=b"%PDF-1.4 tiny",
    )
    assert bad["ok"] is False

    html = verify_worker_document_upload(
        doc_type="personalausweis",
        filename="ausweis.pdf",
        claimed_mime="application/pdf",
        file_data=b"<!DOCTYPE html><html><body>Personalausweis</body></html>" + b"x" * 900,
    )
    assert html["ok"] is False


def test_reject_id_type_when_content_is_unrelated(monkeypatch):
    monkeypatch.setenv("BAUPASS_DOC_VERIFY", "1")
    monkeypatch.setenv("BAUPASS_DOC_VERIFY_STRICT", "1")

    def fake_extract(raw, filename=""):
        return {"text": "Lorem ipsum hello world untitled document invoice only", "engines": ["pdf_text"]}

    monkeypatch.setattr(
        "backend.app.platform.documents.verify.extract_document_text",
        fake_extract,
    )
    result = verify_worker_document_upload(
        doc_type="personalausweis",
        filename="ausweis.pdf",
        claimed_mime="application/pdf",
        file_data=_pdf_with_text("invoice"),
    )
    assert result["ok"] is False
    assert result["error"] in {"document_type_mismatch", "document_unreadable"}


def test_accept_passport_like_content(monkeypatch):
    monkeypatch.setenv("BAUPASS_DOC_VERIFY", "1")
    monkeypatch.setenv("BAUPASS_DOC_VERIFY_STRICT", "1")

    def fake_extract(raw, filename=""):
        return {
            "text": "BUNDESREPUBLIK DEUTSCHLAND Personalausweis Geburtsdatum P<DEUMUSTERMANN<<ERIKA",
            "engines": ["pdf_text"],
        }

    monkeypatch.setattr(
        "backend.app.platform.documents.verify.extract_document_text",
        fake_extract,
    )
    result = verify_worker_document_upload(
        doc_type="personalausweis",
        filename="ausweis.pdf",
        claimed_mime="application/pdf",
        file_data=_pdf_with_text("Personalausweis"),
    )
    assert result["ok"] is True
    assert result["status"] == "accepted"
    assert result["score"] >= 0.34


def test_accept_birth_certificate(monkeypatch):
    monkeypatch.setenv("BAUPASS_DOC_VERIFY", "1")

    def fake_extract(raw, filename=""):
        return {
            "text": "Geburtsurkunde Standesamt geboren Vater Mutter",
            "engines": ["pdf_text"],
        }

    monkeypatch.setattr(
        "backend.app.platform.documents.verify.extract_document_text",
        fake_extract,
    )
    result = verify_worker_document_upload(
        doc_type="geburtsurkunde",
        filename="birth.pdf",
        claimed_mime="application/pdf",
        file_data=_pdf_with_text("Geburtsurkunde"),
    )
    assert result["ok"] is True


def test_sonstiges_accepts_valid_pdf_without_keywords(monkeypatch):
    monkeypatch.setenv("BAUPASS_DOC_VERIFY", "1")

    def fake_extract(raw, filename=""):
        return {"text": "some notes", "engines": ["pdf_text"]}

    monkeypatch.setattr(
        "backend.app.platform.documents.verify.extract_document_text",
        fake_extract,
    )
    result = verify_worker_document_upload(
        doc_type="sonstiges",
        filename="other.pdf",
        claimed_mime="application/pdf",
        file_data=_pdf_with_text("notes"),
    )
    assert result["ok"] is True
