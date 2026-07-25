"""Tests for integrated editor docs domain (S1–S3)."""
from __future__ import annotations


def _superadmin_headers(client):
    resp = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def _create_company(client, headers, name: str) -> str:
    response = client.post(
        "/api/companies",
        json={
            "name": name,
            "contact": "x",
            "adminPassword": "1234",
            "turnstilePassword": "1234",
            "turnstileCount": 0,
        },
        headers=headers,
    )
    assert response.status_code in (200, 201)
    payload = response.get_json() or {}
    company = payload.get("company") or {}
    return str(company.get("id") or payload.get("id") or "")


def test_docs_crud_general_mode(client_and_db):
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "DocsEditorCo")

    created = client.post(
        f"/api/v2/docs?company_id={cid}",
        headers=headers,
        json={
            "company_id": cid,
            "title": "Brief",
            "mode": "general",
            "contentHtml": "<p>Hallo Welt</p>",
            "contentText": "Hallo Welt",
        },
    )
    assert created.status_code == 201, created.get_json()
    doc = created.get_json()["document"]
    assert doc["title"] == "Brief"
    assert doc["mode"] == "general"
    assert "Hallo" in (doc.get("content_text") or "")

    listed = client.get(f"/api/v2/docs?company_id={cid}", headers=headers)
    assert listed.status_code == 200
    assert any(i["id"] == doc["id"] for i in listed.get_json().get("items") or [])

    updated = client.put(
        f"/api/v2/docs/{doc['id']}?company_id={cid}",
        headers=headers,
        json={"company_id": cid, "title": "Brief 2", "contentHtml": "<p>Updated</p>"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["document"]["title"] == "Brief 2"

    deleted = client.delete(f"/api/v2/docs/{doc['id']}?company_id={cid}", headers=headers)
    assert deleted.status_code == 200


def test_docs_from_contract_reuses_same_doc(client_and_db):
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "DocsContractLinkCo")
    contract_id = "ctr-docs-link-1"

    first = client.post(
        f"/api/v2/docs/from-contract?company_id={cid}",
        headers=headers,
        json={"company_id": cid, "contractId": contract_id, "title": "AV", "text": "§1 Vertrag"},
    )
    assert first.status_code == 200, first.get_json()
    doc_id = first.get_json()["document"]["id"]

    second = client.post(
        f"/api/v2/docs/from-contract?company_id={cid}",
        headers=headers,
        json={"company_id": cid, "contractId": contract_id, "title": "AV", "text": "other"},
    )
    assert second.status_code == 200
    assert second.get_json()["document"]["id"] == doc_id


def test_docs_merge_fill_and_versions_export(client_and_db):
    import sqlite3
    from contextlib import closing

    client, db_path = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "DocsMergeCo")

    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, subcompany_id, first_name, last_name, insurance_number, role, site, valid_until,
                status, photo_data, badge_id, badge_id_lookup, badge_pin_hash, worker_type
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', 'worker')
            """,
            (
                "w-docs-merge-1",
                cid,
                "Ali",
                "Hassan",
                "12 345678 A 001",
                "Maler",
                "Testsite",
                "2026-12-31",
                "aktiv",
                "",
                "B-42",
                "B42",
            ),
        )
        db.commit()

    created = client.post(
        f"/api/v2/docs?company_id={cid}",
        headers=headers,
        json={
            "company_id": cid,
            "title": "Hinweis",
            "mode": "workforce",
            "workerId": "w-docs-merge-1",
            "contentHtml": "<p>Firma {{company.name}} · MA {{worker.name}} · {{date.today}}</p>",
        },
    )
    assert created.status_code == 201, created.get_json()
    doc = created.get_json()["document"]

    ctx = client.get(
        f"/api/v2/docs/merge-context?company_id={cid}&worker_id=w-docs-merge-1",
        headers=headers,
    )
    assert ctx.status_code == 200
    fields = ctx.get_json().get("fields") or {}
    assert "DocsMergeCo" in str(fields.get("company.name") or "")
    assert "Ali" in str(fields.get("worker.name") or "")

    filled = client.post(
        f"/api/v2/docs/fill-merge?company_id={cid}",
        headers=headers,
        json={
            "company_id": cid,
            "workerId": "w-docs-merge-1",
            "contentHtml": doc["content_html"],
        },
    )
    assert filled.status_code == 200
    html = filled.get_json().get("contentHtml") or ""
    assert "DocsMergeCo" in html
    assert "Ali Hassan" in html
    assert "{{company.name}}" not in html

    updated = client.put(
        f"/api/v2/docs/{doc['id']}?company_id={cid}",
        headers=headers,
        json={"company_id": cid, "contentHtml": html, "versionNote": "after-merge"},
    )
    assert updated.status_code == 200

    versions = client.get(f"/api/v2/docs/{doc['id']}/versions?company_id={cid}", headers=headers)
    assert versions.status_code == 200
    items = versions.get_json().get("items") or []
    assert len(items) >= 2

    oldest = items[-1]
    restored = client.post(
        f"/api/v2/docs/{doc['id']}/versions/{oldest['id']}/restore?company_id={cid}",
        headers=headers,
        json={"company_id": cid},
    )
    assert restored.status_code == 200
    assert restored.get_json()["document"]["id"] == doc["id"]

    suggest = client.post(
        f"/api/v2/docs/suggest?company_id={cid}",
        headers=headers,
        json={
            "company_id": cid,
            "action": "shorten",
            "contentHtml": "<p>Eins. Zwei. Drei. Vier. Fünf.</p>",
        },
    )
    assert suggest.status_code == 200
    assert suggest.get_json().get("ok") is True

    export_html = client.get(
        f"/api/v2/docs/{doc['id']}/export?company_id={cid}&format=html",
        headers=headers,
    )
    assert export_html.status_code == 200
    assert "text/html" in (export_html.headers.get("Content-Type") or "")
    assert b"<html" in export_html.data.lower()

    merge_ctx = client.get(
        f"/api/v2/docs/merge-context?company_id={cid}",
        headers=headers,
    )
    assert merge_ctx.status_code == 200
    merge_body = merge_ctx.get_json()
    assert merge_body.get("branding", {}).get("companyName")
    assert "headerHtml" in (merge_body.get("letterhead") or {})
    assert "company.address" in (merge_body.get("fields") or {})

    export_doc = client.get(
        f"/api/v2/docs/{doc['id']}/export?company_id={cid}&format=doc",
        headers=headers,
    )
    assert export_doc.status_code == 200
    ctype_doc = (export_doc.headers.get("Content-Type") or "").lower()
    assert "msword" in ctype_doc or "wordprocessingml" in ctype_doc or "officedocument" in ctype_doc
    assert len(export_doc.data) > 20

    export_pdf = client.get(
        f"/api/v2/docs/{doc['id']}/export?company_id={cid}&format=pdf",
        headers=headers,
    )
    assert export_pdf.status_code == 200
    assert "pdf" in (export_pdf.headers.get("Content-Type") or "").lower()
    assert export_pdf.data[:4] == b"%PDF"

def test_docs_publish_requires_worker(client_and_db):
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "DocsPublishCo")

    created = client.post(
        f"/api/v2/docs?company_id={cid}",
        headers=headers,
        json={
            "company_id": cid,
            "title": "Hinweis",
            "mode": "workforce",
            "contentHtml": "<p>Hallo</p>",
        },
    )
    assert created.status_code == 201
    doc_id = created.get_json()["document"]["id"]

    missing = client.post(
        f"/api/v2/docs/{doc_id}/publish?company_id={cid}",
        headers=headers,
        json={"company_id": cid},
    )
    assert missing.status_code == 400
    assert missing.get_json().get("error") == "worker_required"


def test_docs_status_and_publish_to_worker(client_and_db):
    import sqlite3
    from contextlib import closing

    client, db_path = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "DocsPublishWorkerCo")

    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, subcompany_id, first_name, last_name, insurance_number, role, site, valid_until,
                status, photo_data, badge_id, badge_id_lookup, badge_pin_hash, worker_type
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', 'worker')
            """,
            (
                "w-docs-pub-1",
                cid,
                "Sam",
                "Writer",
                "12 345678 A 009",
                "Maler",
                "Testsite",
                "2026-12-31",
                "aktiv",
                "",
                "P-9",
                "P9",
            ),
        )
        db.commit()

    created = client.post(
        f"/api/v2/docs?company_id={cid}",
        headers=headers,
        json={
            "company_id": cid,
            "title": "Schreiben Sam",
            "mode": "workforce",
            "workerId": "w-docs-pub-1",
            "contentHtml": "<p>Freigabe-Test</p>",
        },
    )
    assert created.status_code == 201, created.get_json()
    doc_id = created.get_json()["document"]["id"]

    status = client.post(
        f"/api/v2/docs/{doc_id}/status?company_id={cid}",
        headers=headers,
        json={"company_id": cid, "status": "in_review"},
    )
    assert status.status_code == 200
    assert status.get_json()["document"]["status"] == "in_review"

    published = client.post(
        f"/api/v2/docs/{doc_id}/publish?company_id={cid}",
        headers=headers,
        json={"company_id": cid, "workerId": "w-docs-pub-1", "notify": False},
    )
    assert published.status_code == 200, published.get_json()
    body = published.get_json()
    assert body.get("ok") is True
    assert body.get("workerDocumentId")
    assert body["document"]["status"] == "archived"

    with closing(sqlite3.connect(db_path)) as db:
        row = db.execute(
            "SELECT filename, file_size FROM worker_documents WHERE id = ?",
            (body["workerDocumentId"],),
        ).fetchone()
        assert row is not None
        assert str(row[0]).lower().endswith(".pdf")
        assert int(row[1] or 0) > 20


def test_docs_fill_letter_template_placeholders(client_and_db):
    """All standard template merge keys resolve without leftover {{…}}."""
    client, _ = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "DocsTplCo")

    letter_html = (
        "<p>{{company.name}}<br>{{company.address}}<br>{{company.email}}</p>"
        "<p>{{worker.name}}<br>{{site.name}}</p>"
        "<p>{{date.today}}</p>"
        "<p>{{manager.name}}<br>{{company.contact}}<br>{{worker.badge}}</p>"
    )
    filled = client.post(
        f"/api/v2/docs/fill-merge?company_id={cid}",
        headers=headers,
        json={"company_id": cid, "contentHtml": letter_html},
    )
    assert filled.status_code == 200, filled.get_json()
    html = filled.get_json().get("contentHtml") or ""
    assert "{{" not in html
    assert "DocsTplCo" in html
    assert filled.get_json().get("unresolved") in (None, [], ())


def test_docs_signature_pin_and_aes_manifest(client_and_db):
    import hashlib
    import json

    client, _ = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "DocsSignPinCo")
    body_html = "<p>Signatur-Inhalt</p>"
    created = client.post(
        f"/api/v2/docs?company_id={cid}",
        headers=headers,
        json={
            "company_id": cid,
            "title": "Sign Doc",
            "mode": "general",
            "contentHtml": body_html,
        },
    )
    assert created.status_code == 201, created.get_json()
    doc_id = created.get_json()["document"]["id"]

    missing_pin = client.post(
        f"/api/v2/docs/{doc_id}/signatures?company_id={cid}",
        headers=headers,
        json={"company_id": cid, "signerName": "Ada", "stamped": True, "pin": "12"},
    )
    assert missing_pin.status_code == 400
    assert missing_pin.get_json().get("error") == "pin_required"

    ok = client.post(
        f"/api/v2/docs/{doc_id}/signatures?company_id={cid}",
        headers=headers,
        json={
            "company_id": cid,
            "signerName": "Ada Lovelace",
            "stamped": True,
            "pin": "1357",
            "lockAfter": True,
            "signatureData": "data:image/png;base64,aaa",
        },
    )
    assert ok.status_code == 200, ok.get_json()
    payload = ok.get_json() or {}
    assert payload.get("ok") is True
    assert payload.get("level") == "aes"
    assert (payload.get("document") or {}).get("status") == "approved"
    sig = payload.get("signature") or {}
    expected_hash = hashlib.sha256(body_html.encode("utf-8", errors="ignore")).hexdigest()
    assert sig.get("content_hash") == expected_hash
    packed = json.loads(sig.get("signature_data") or "{}")
    manifest = packed.get("manifest") or {}
    assert manifest.get("level") == "aes"
    assert manifest.get("contentHashSha256") == expected_hash
    assert manifest.get("signerName") == "Ada Lovelace"
    assert str(manifest.get("pinHash") or "").startswith("pbkdf2:") or ":" in str(
        manifest.get("pinHash") or ""
    )


def test_docs_presence_returns_content_hash(client_and_db):
    import hashlib

    client, _ = client_and_db
    headers = _superadmin_headers(client)
    cid = _create_company(client, headers, "DocsPresenceHashCo")
    body_html = "<p>Presence hash body</p>"
    created = client.post(
        f"/api/v2/docs?company_id={cid}",
        headers=headers,
        json={
            "company_id": cid,
            "title": "Presence Doc",
            "mode": "general",
            "contentHtml": body_html,
        },
    )
    assert created.status_code == 201, created.get_json()
    doc_id = created.get_json()["document"]["id"]

    presence = client.post(
        f"/api/v2/docs/{doc_id}/presence?company_id={cid}",
        headers=headers,
        json={"company_id": cid},
    )
    assert presence.status_code == 200, presence.get_json()
    body = presence.get_json() or {}
    assert body.get("ok") is True
    full = hashlib.sha256(body_html.encode("utf-8", errors="ignore")).hexdigest()
    assert body.get("contentHash") == full[:24]
    assert isinstance(body.get("peers"), list)
