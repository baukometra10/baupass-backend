"""Shared fake E2E payloads for pytest (structure only — no real crypto)."""
from __future__ import annotations

import base64
import io
import json


def fake_e2e_envelope() -> str:
    payload = {
        "e2e": True,
        "v": 1,
        "alg": "X25519-AES-GCM",
        "epk": base64.b64encode(b"\x30" + b"\x01" * 40).decode("ascii"),
        "iv": base64.b64encode(b"\x00" * 12).decode("ascii"),
        "ct": base64.b64encode(b"cipher").decode("ascii"),
    }
    return json.dumps(payload)


def fake_e2e_attachment_meta() -> str:
    payload = {
        "e2e": True,
        "v": 1,
        "kind": "attachment",
        "iv": base64.b64encode(b"\x00" * 12).decode("ascii"),
        "wrappedKey": fake_e2e_envelope(),
        "filename": "upload.bin",
        "mime": "application/pdf",
    }
    return json.dumps(payload)


def e2e_document_upload_form(
    *,
    doc_type: str,
    file_bytes: bytes,
    filename: str,
    mimetype: str,
    notes: str = "",
    expiry_date: str = "",
) -> dict:
    """Build multipart form fields for E2E-enforced document upload tests."""
    return {
        "docType": doc_type,
        "notes": notes,
        "expiryDate": expiry_date,
        "e2e_meta": fake_e2e_attachment_meta(),
        "e2e_encrypted": "1",
        "file": (io.BytesIO(file_bytes), f"{filename}.e2e", "application/vnd.suppix.e2e+binary"),
    }
