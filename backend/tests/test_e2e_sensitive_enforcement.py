"""Tests for enforced E2E on leave notes, documents, and contracts."""
from __future__ import annotations

import io

from backend.tests.e2e_test_helpers import (
    e2e_document_upload_form,
    fake_e2e_attachment_meta,
    fake_e2e_envelope,
)
from backend.tests.test_e2e_identity_routes import (
    _create_company,
    _superadmin_headers,
    _worker_session_headers,
)


def _create_worker(client, headers, badge_suffix: str = "DOC"):
    response = client.post(
        "/api/workers",
        json={
            "companyId": "cmp-default",
            "firstName": "E2E",
            "lastName": "Tester",
            "insuranceNumber": f"A{badge_suffix}1234567",
            "workerType": "worker",
            "role": "Monteur",
            "site": "Nordtor",
            "validUntil": "2028-12-31",
            "status": "aktiv",
            "photoData": "data:image/png;base64,AAA",
            "badgePin": "1234",
            "complianceSignatureData": "data:image/png;base64,AAA",
            "physicalCardId": f"NFC-E2E-{badge_suffix}",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def test_leave_rejects_plaintext_note_when_e2e_required(client_and_db):
    client, db_path = client_and_db
    admin_headers = _superadmin_headers(client)
    company_id = _create_company(client, admin_headers, "E2ELeaveCo")
    worker_headers, _worker_id = _worker_session_headers(client, db_path, company_id)

    blocked = client.post(
        "/api/worker-app/leave-requests",
        json={
            "type": "urlaub",
            "start_date": "2026-08-01",
            "end_date": "2026-08-05",
            "note": "Familienurlaub Klartext",
        },
        headers=worker_headers,
    )
    assert blocked.status_code == 400
    assert blocked.get_json().get("error") == "e2e_required_note"

    allowed = client.post(
        "/api/worker-app/leave-requests",
        json={
            "type": "urlaub",
            "start_date": "2026-08-01",
            "end_date": "2026-08-05",
            "note": fake_e2e_envelope(),
        },
        headers=worker_headers,
    )
    assert allowed.status_code == 201


def test_document_upload_rejects_missing_e2e_meta(client_and_db, monkeypatch):
    client, _db_path = client_and_db
    headers = _superadmin_headers(client)
    worker_id = _create_worker(client, headers, "UPLOAD1")
    monkeypatch.setattr(
        "backend.app.platform.security.e2e_policy.is_e2e_attachment_required",
        lambda *a, **k: True,
    )

    pdf_bytes = b"%PDF-1.4\n" + (b"x" * 1200)
    blocked = client.post(
        f"/api/workers/{worker_id}/documents/upload",
        data={
            "docType": "mindestlohnnachweis",
            "notes": "",
            "expiryDate": "",
            "file": (io.BytesIO(pdf_bytes), "mindestlohn.pdf", "application/pdf"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert blocked.status_code == 400
    assert blocked.get_json().get("error") == "e2e_attachment_required"

    allowed = client.post(
        f"/api/workers/{worker_id}/documents/upload",
        data=e2e_document_upload_form(
            doc_type="mindestlohnnachweis",
            file_bytes=pdf_bytes,
            filename="mindestlohn.pdf",
            mimetype="application/pdf",
        ),
        headers=headers,
        content_type="multipart/form-data",
    )
    assert allowed.status_code == 200
    assert allowed.get_json().get("ok") is True


def test_document_upload_rejects_plaintext_notes(client_and_db, monkeypatch):
    client, _db_path = client_and_db
    headers = _superadmin_headers(client)
    worker_id = _create_worker(client, headers, "UPLOAD2")
    monkeypatch.setattr(
        "backend.app.platform.security.e2e_policy.is_e2e_attachment_required",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(
        "backend.app.platform.security.e2e_policy.is_e2e_sensitive_required",
        lambda *a, **k: True,
    )

    pdf_bytes = b"%PDF-1.4\n" + (b"x" * 1200)
    blocked = client.post(
        f"/api/workers/{worker_id}/documents/upload",
        data={
            **e2e_document_upload_form(
                doc_type="mindestlohnnachweis",
                file_bytes=pdf_bytes,
                filename="mindestlohn.pdf",
                mimetype="application/pdf",
            ),
            "notes": "Klartext-Notiz",
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert blocked.status_code == 400
    assert blocked.get_json().get("error") == "e2e_required_notes"


def test_contract_update_rejects_plaintext_final_text(client_and_db):
    client, _db_path = client_and_db
    headers = _superadmin_headers(client)
    company_id = _create_company(client, headers, "E2EContractCo")

    templates = client.get(f"/api/contracts/templates?company_id={company_id}", headers=headers)
    assert templates.status_code == 200
    template_rows = templates.get_json().get("templates") or []
    assert template_rows

    draft = client.post(
        "/api/contracts/draft",
        json={
            "company_id": company_id,
            "template_id": template_rows[0]["id"],
            "title": "E2E Vertrag",
            "language": "de",
            "notes": fake_e2e_envelope(),
        },
        headers=headers,
    )
    assert draft.status_code == 200
    contract_id = draft.get_json()["contract"]["id"]

    blocked = client.put(
        f"/api/contracts/{contract_id}",
        json={"company_id": company_id, "final_text": "Klartext Vertragstext"},
        headers=headers,
    )
    assert blocked.status_code == 400
    assert blocked.get_json().get("error") == "e2e_required_final_text"

    allowed = client.put(
        f"/api/contracts/{contract_id}",
        json={"company_id": company_id, "final_text": fake_e2e_envelope()},
        headers=headers,
    )
    assert allowed.status_code == 200
    assert allowed.get_json().get("ok") is True

    client.delete(f"/api/contracts/{contract_id}?company_id={company_id}", headers=headers)


def test_attachment_meta_validation():
    from backend.app.platform.security.e2e_envelope import is_e2e_attachment_meta

    assert is_e2e_attachment_meta(fake_e2e_attachment_meta()) is True
    assert is_e2e_attachment_meta("{}") is False


def test_e2e_attachment_rejects_audio_mime_when_encrypted():
    from backend.app.platform.security.e2e_envelope import assert_e2e_attachment

    meta = fake_e2e_attachment_meta()
    try:
        assert_e2e_attachment(e2e_meta=meta, content_type="audio/mp4", encrypted=True)
        raise AssertionError("expected e2e_attachment_content_type_invalid")
    except ValueError as exc:
        assert str(exc) == "e2e_attachment_content_type_invalid"

    assert_e2e_attachment(
        e2e_meta=meta,
        content_type="application/vnd.suppix.e2e+binary",
        encrypted=True,
    )
