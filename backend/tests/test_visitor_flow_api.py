import sqlite3
import io
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pytest

from backend import server  # noqa: E402


def _auth_headers(client):
    response = client.post(
        "/api/login",
        json={
            "username": "superadmin",
            "password": "1234",
            "loginScope": "server-admin",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    return {"Authorization": f"Bearer {payload['token']}"}


def _company_admin_auth_headers(client, **extra_login_payload):
    login_payload = {
        "username": "firma",
        "password": "1234",
        "loginScope": "company-admin",
    }
    login_payload.update(extra_login_payload)
    response = client.post("/api/login", json=login_payload)
    assert response.status_code == 200
    payload = response.get_json()
    return {"Authorization": f"Bearer {payload['token']}"}, payload


def _visitor_payload(visit_end_at, **overrides):
    payload = {
        "companyId": "cmp-default",
        "firstName": "Lena",
        "lastName": "Gast",
        "workerType": "visitor",
        "role": "Besucher",
        "site": "Nordtor",
        "status": "aktiv",
        "photoData": "data:image/png;base64,AAA",
        "visitorCompany": "Muster AG",
        "visitPurpose": "Sicherheitsbegehung",
        "hostName": "Herr Bauleiter",
        "visitEndAt": visit_end_at,
    }
    payload.update(overrides)
    return payload


def _worker_payload(company_id, physical_card_id, **overrides):
    payload = {
        "companyId": company_id,
        "firstName": "Max",
        "lastName": "Muster",
        "insuranceNumber": "A123456789",
        "workerType": "worker",
        "role": "Monteur",
        "site": "Nordtor",
        "validUntil": "2026-12-31",
        "status": "aktiv",
        "photoData": "data:image/png;base64,AAA",
        "badgePin": "1234",
        "complianceSignatureData": "data:image/png;base64,AAA",
        "physicalCardId": physical_card_id,
    }
    payload.update(overrides)
    return payload


def _issue_turnstile_api_key(db_path, user_id="usr-turnstile"):
    api_key = server.create_turnstile_api_key()
    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            "UPDATE users SET api_key_hash = ? WHERE id = ?",
            (server.hash_turnstile_api_key(api_key), user_id),
        )
        db.commit()
    return api_key


def _local_datetime_string(delta_hours):
    target = datetime.now() + timedelta(hours=delta_hours)
    return target.strftime("%Y-%m-%dT%H:%M")


def test_create_visitor_requires_domain_fields(client_and_db):
    client, _ = client_and_db
    headers = _auth_headers(client)

    invalid_payload = _visitor_payload(_local_datetime_string(3), visitorCompany="")
    response = client.post("/api/workers", json=invalid_payload, headers=headers)

    assert response.status_code == 400
    assert response.get_json()["error"] == "visitor_company_required"


def test_visitor_access_token_is_one_time(client_and_db):
    client, _ = client_and_db
    headers = _auth_headers(client)

    create_response = client.post(
        "/api/workers",
        json=_visitor_payload(_local_datetime_string(5)),
        headers=headers,
    )
    assert create_response.status_code == 201
    worker_id = create_response.get_json()["id"]

    access_response = client.post(f"/api/workers/{worker_id}/app-access", headers=headers)
    assert access_response.status_code == 200
    access_token = access_response.get_json()["accessToken"]

    login_response = client.post("/api/worker-app/login", json={"accessToken": access_token})
    assert login_response.status_code == 200
    assert "token" in login_response.get_json()

    second_login_response = client.post("/api/worker-app/login", json={"accessToken": access_token})
    assert second_login_response.status_code == 401
    assert second_login_response.get_json()["error"] == "access_token_already_used"


def test_expired_visitor_cannot_get_app_access(client_and_db):
    client, _ = client_and_db
    headers = _auth_headers(client)

    create_response = client.post(
        "/api/workers",
        json=_visitor_payload(_local_datetime_string(-2)),
        headers=headers,
    )
    assert create_response.status_code == 201
    worker_id = create_response.get_json()["id"]

    access_response = client.post(f"/api/workers/{worker_id}/app-access", headers=headers)
    assert access_response.status_code == 400
    assert access_response.get_json()["error"] == "visitor_visit_expired"


def test_expired_visitor_is_auto_checked_out_in_summary(client_and_db):
    client, db_path = client_and_db
    headers = _auth_headers(client)

    create_response = client.post(
        "/api/workers",
        json=_visitor_payload(_local_datetime_string(5)),
        headers=headers,
    )
    assert create_response.status_code == 201
    worker_id = create_response.get_json()["id"]

    check_in_response = client.post(
        "/api/access-logs",
        json={
            "workerId": worker_id,
            "direction": "check-in",
            "gate": "Nordtor",
            "note": "Testeintritt",
        },
        headers=headers,
    )
    assert check_in_response.status_code == 201

    past_visit_end = (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with closing(sqlite3.connect(db_path)) as db:
        db.execute("UPDATE workers SET visit_end_at = ? WHERE id = ?", (past_visit_end, worker_id))
        db.commit()

    summary_response = client.get("/api/access-logs/summary", headers=headers)
    assert summary_response.status_code == 200

    with closing(sqlite3.connect(db_path)) as db:
        row = db.execute(
            """
            SELECT COUNT(*)
            FROM access_logs
            WHERE worker_id = ?
              AND direction = 'check-out'
              AND note = 'Automatischer Austritt nach Besucher-Ende'
            """,
            (worker_id,),
        ).fetchone()
        checkout_count = int(row[0]) if row is not None else 0

    assert checkout_count >= 1


def test_visitor_end_to_end_lifecycle(client_and_db):
    client, db_path = client_and_db
    admin_headers = _auth_headers(client)

    create_response = client.post(
        "/api/workers",
        json=_visitor_payload(_local_datetime_string(6)),
        headers=admin_headers,
    )
    assert create_response.status_code == 201
    worker_id = create_response.get_json()["id"]

    access_response = client.post(f"/api/workers/{worker_id}/app-access", headers=admin_headers)
    assert access_response.status_code == 200
    access_token = access_response.get_json()["accessToken"]

    login_response = client.post("/api/worker-app/login", json={"accessToken": access_token})
    assert login_response.status_code == 200
    login_payload = login_response.get_json()
    worker_session_token = login_payload["token"]
    assert login_payload["cardType"] == "visitor"

    worker_headers = {"Authorization": f"Bearer {worker_session_token}"}
    me_response = client.get("/api/worker-app/me", headers=worker_headers)
    assert me_response.status_code == 200
    me_payload = me_response.get_json()
    assert me_payload["worker"]["id"] == worker_id
    assert me_payload["worker"]["workerType"] == "visitor"

    check_in_response = client.post(
        "/api/access-logs",
        json={
            "workerId": worker_id,
            "direction": "check-in",
            "gate": "Nordtor",
            "note": "Lifecycle-Test",
        },
        headers=admin_headers,
    )
    assert check_in_response.status_code == 201

    past_visit_end = (datetime.now(timezone.utc) - timedelta(minutes=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with closing(sqlite3.connect(db_path)) as db:
        db.execute("UPDATE workers SET visit_end_at = ? WHERE id = ?", (past_visit_end, worker_id))
        db.commit()

    summary_response = client.get("/api/access-logs/summary", headers=admin_headers)
    assert summary_response.status_code == 200

    with closing(sqlite3.connect(db_path)) as db:
        checkout_row = db.execute(
            """
            SELECT COUNT(*)
            FROM access_logs
            WHERE worker_id = ?
              AND direction = 'check-out'
              AND note = 'Automatischer Austritt nach Besucher-Ende'
            """,
            (worker_id,),
        ).fetchone()
        checkout_count = int(checkout_row[0]) if checkout_row is not None else 0
    assert checkout_count >= 1

    new_access_response = client.post(f"/api/workers/{worker_id}/app-access", headers=admin_headers)
    assert new_access_response.status_code == 400
    assert new_access_response.get_json()["error"] == "visitor_visit_expired"

    with closing(sqlite3.connect(db_path)) as db:
        expired_session = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        db.execute("UPDATE worker_app_sessions SET expires_at = ? WHERE token = ?", (expired_session, worker_session_token))
        db.commit()

    expired_session_response = client.get("/api/worker-app/me", headers=worker_headers)
    assert expired_session_response.status_code == 401
    assert expired_session_response.get_json()["error"] in {"worker_session_expired", "invalid_worker_session"}


def test_gate_api_key_is_scoped_to_turnstile_company(client_and_db):
    client, _ = client_and_db
    headers = _auth_headers(client)

    first_company_response = client.post(
        "/api/companies",
        json={"name": "Firma Eins", "contact": "A", "adminPassword": "1234", "turnstilePassword": "1234", "turnstileCount": 1},
        headers=headers,
    )
    assert first_company_response.status_code == 201
    first_company_payload = first_company_response.get_json()

    second_company_response = client.post(
        "/api/companies",
        json={"name": "Firma Zwei", "contact": "B", "adminPassword": "1234", "turnstilePassword": "1234", "turnstileCount": 1},
        headers=headers,
    )
    assert second_company_response.status_code == 201
    second_company_payload = second_company_response.get_json()

    own_worker_response = client.post(
        "/api/workers",
        json=_worker_payload(first_company_payload["company"]["id"], "CARD-OWN-1"),
        headers=headers,
    )
    assert own_worker_response.status_code == 201

    foreign_worker_response = client.post(
        "/api/workers",
        json=_worker_payload(second_company_payload["company"]["id"], "CARD-OTHER-1"),
        headers=headers,
    )
    assert foreign_worker_response.status_code == 201

    gate_headers = {"X-Gate-Key": first_company_payload["turnstileCredentials"]["apiKey"]}

    own_gate_response = client.post(
        "/api/gates/tap",
        json={"physicalCardId": "CARD-OWN-1", "direction": "check-in", "gate": "Gate 1"},
        headers=gate_headers,
    )
    assert own_gate_response.status_code == 201

    foreign_gate_response = client.post(
        "/api/gates/tap",
        json={"physicalCardId": "CARD-OTHER-1", "direction": "check-in", "gate": "Gate 1"},
        headers=gate_headers,
    )
    assert foreign_gate_response.status_code == 403
    assert foreign_gate_response.get_json()["error"] == "forbidden_worker_company"


def test_worker_with_expired_required_document_is_auto_locked_and_access_blocked(client_and_db):
    client, db_path = client_and_db
    headers = _auth_headers(client)

    create_response = client.post(
        "/api/workers",
        json=_worker_payload("cmp-default", "CARD-LOCK-1"),
        headers=headers,
    )
    assert create_response.status_code == 201
    worker_id = create_response.get_json()["id"]

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            """
            INSERT INTO worker_documents (
                id, worker_id, company_id, doc_type, filename, file_path, file_size,
                source_email_from, source_inbox_id, uploaded_by_user_id, created_at, notes, expiry_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "doc-mindest-1",
                worker_id,
                "cmp-default",
                "mindestlohnnachweis",
                "mindestlohn.pdf",
                "backend/e2e-doc-uploads/mindestlohn.pdf",
                123,
                "",
                None,
                "usr-superadmin",
                now,
                "",
                "",
            ),
        )
        db.execute(
            """
            INSERT INTO worker_documents (
                id, worker_id, company_id, doc_type, filename, file_path, file_size,
                source_email_from, source_inbox_id, uploaded_by_user_id, created_at, notes, expiry_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "doc-expired-1",
                worker_id,
                "cmp-default",
                "personalausweis",
                "id-expired.pdf",
                "backend/e2e-doc-uploads/id-expired.pdf",
                123,
                "",
                None,
                "usr-superadmin",
                now,
                "",
                "2020-01-01",
            ),
        )
        db.commit()

    list_response = client.get("/api/workers", headers=headers)
    assert list_response.status_code == 200
    workers = list_response.get_json() or []
    worker_row = next((row for row in workers if row.get("id") == worker_id), None)
    assert worker_row is not None
    assert worker_row.get("status") == "gesperrt"
    assert worker_row.get("lockReasonCode") == "expired_documents"

    access_response = client.post(
        "/api/access-logs",
        json={
            "workerId": worker_id,
            "direction": "check-in",
            "gate": "Nordtor",
            "note": "Blocked by expired docs",
        },
        headers=headers,
    )
    assert access_response.status_code == 400
    assert access_response.get_json().get("error") == "worker_documents_expired"


def test_worker_with_missing_required_documents_is_auto_locked_and_access_blocked(client_and_db):
    client, _db_path = client_and_db
    headers = _auth_headers(client)

    create_response = client.post(
        "/api/workers",
        json=_worker_payload("cmp-default", "CARD-MISS-1"),
        headers=headers,
    )
    assert create_response.status_code == 201
    worker_id = create_response.get_json()["id"]

    list_response = client.get("/api/workers", headers=headers)
    assert list_response.status_code == 200
    workers = list_response.get_json() or []
    worker_row = next((row for row in workers if row.get("id") == worker_id), None)
    assert worker_row is not None
    assert worker_row.get("status") == "gesperrt"
    assert worker_row.get("lockReasonCode") == "missing_documents"

    access_response = client.post(
        "/api/access-logs",
        json={
            "workerId": worker_id,
            "direction": "check-in",
            "gate": "Nordtor",
            "note": "Blocked by missing docs",
        },
        headers=headers,
    )
    assert access_response.status_code == 400
    assert access_response.get_json().get("error") == "worker_documents_missing"


def test_worker_is_auto_unlocked_after_uploading_new_valid_required_document(client_and_db):
    client, db_path = client_and_db
    headers = _auth_headers(client)

    create_response = client.post(
        "/api/workers",
        json=_worker_payload("cmp-default", "CARD-UNLOCK-1"),
        headers=headers,
    )
    assert create_response.status_code == 201
    worker_id = create_response.get_json()["id"]

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            """
            INSERT INTO worker_documents (
                id, worker_id, company_id, doc_type, filename, file_path, file_size,
                source_email_from, source_inbox_id, uploaded_by_user_id, created_at, notes, expiry_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "doc-mindest-2",
                worker_id,
                "cmp-default",
                "mindestlohnnachweis",
                "mindestlohn.pdf",
                "backend/e2e-doc-uploads/mindestlohn-2.pdf",
                123,
                "",
                None,
                "usr-superadmin",
                now,
                "",
                "",
            ),
        )
        db.execute(
            """
            INSERT INTO worker_documents (
                id, worker_id, company_id, doc_type, filename, file_path, file_size,
                source_email_from, source_inbox_id, uploaded_by_user_id, created_at, notes, expiry_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "doc-expired-2",
                worker_id,
                "cmp-default",
                "personalausweis",
                "id-expired.pdf",
                "backend/e2e-doc-uploads/id-expired-2.pdf",
                123,
                "",
                None,
                "usr-superadmin",
                now,
                "",
                "2020-01-01",
            ),
        )
        db.commit()

    _ = client.get("/api/workers", headers=headers)

    upload_response = client.post(
        f"/api/workers/{worker_id}/documents/upload",
        data={
            "docType": "personalausweis",
            "notes": "Renewed ID",
            "expiryDate": "2030-12-31",
            "file": (io.BytesIO(b"%PDF-1.4 renewed"), "id-renewed.pdf", "application/pdf"),
        },
        headers=headers,
        content_type="multipart/form-data",
    )
    assert upload_response.status_code == 200

    refreshed_workers = client.get("/api/workers", headers=headers)
    assert refreshed_workers.status_code == 200
    worker_row = next((row for row in (refreshed_workers.get_json() or []) if row.get("id") == worker_id), None)
    assert worker_row is not None
    assert worker_row.get("status") == "aktiv"
    assert not worker_row.get("lockReasonCode")


def test_company_admin_cannot_use_photo_override_flag(client_and_db):
    client, _ = client_and_db
    admin_headers = _auth_headers(client)
    company_headers, _ = _company_admin_auth_headers(client)

    create_response = client.post(
        "/api/workers",
        json=_worker_payload("cmp-default", "CARD-OVR-1"),
        headers=admin_headers,
    )
    assert create_response.status_code == 201
    worker_id = create_response.get_json()["id"]

    update_response = client.put(
        f"/api/workers/{worker_id}",
        json={
            "photoData": "data:image/png;base64,BBB",
            "photoMatchOverride": True,
            "photoMatchSimilarity": 0.31,
            "photoMatchOverrideReason": "False positive simulation",
        },
        headers=company_headers,
    )
    assert update_response.status_code == 403
    assert update_response.get_json().get("error") == "photo_override_forbidden"


def test_superadmin_photo_override_requires_reason_and_is_audited(client_and_db):
    client, db_path = client_and_db
    headers = _auth_headers(client)

    create_response = client.post(
        "/api/workers",
        json=_worker_payload("cmp-default", "CARD-OVR-2"),
        headers=headers,
    )
    assert create_response.status_code == 201
    worker_id = create_response.get_json()["id"]

    missing_reason_response = client.put(
        f"/api/workers/{worker_id}",
        json={
            "photoData": "data:image/png;base64,CCC",
            "photoMatchOverride": True,
            "photoMatchSimilarity": 0.29,
            "photoMatchOverrideReason": "kurz",
        },
        headers=headers,
    )
    assert missing_reason_response.status_code == 400
    assert missing_reason_response.get_json().get("error") == "photo_override_reason_required"

    # Valid override now returns 202 (approval required – 4-Augen-Prinzip)
    ok_response = client.put(
        f"/api/workers/{worker_id}",
        json={
            "photoData": "data:image/png;base64,DDD",
            "photoMatchOverride": True,
            "photoMatchSimilarity": 0.29,
            "photoMatchOverrideReason": "Supervisor verified in person",
        },
        headers=headers,
    )
    assert ok_response.status_code == 202
    ok_body = ok_response.get_json()
    assert ok_body.get("approvalRequested") is True
    assert ok_body.get("approvalId") is not None


def test_photo_override_4_eyes_requires_different_superadmin_and_executes_on_approve(client_and_db):
    """Full 4-Augen flow: request by SA1, self-approve blocked, approved by SA2 executes write + audit."""
    client, db_path = client_and_db
    headers_sa1 = _auth_headers(client)

    # Create worker
    create_resp = client.post(
        "/api/workers",
        json=_worker_payload("cmp-default", "CARD-4EYES-1"),
        headers=headers_sa1,
    )
    assert create_resp.status_code == 201
    worker_id = create_resp.get_json()["id"]

    # SA1 requests a photo override
    override_resp = client.put(
        f"/api/workers/{worker_id}",
        json={
            "photoData": "data:image/png;base64,NEWPHOTO",
            "photoMatchOverride": True,
            "photoMatchSimilarity": 0.31,
            "photoMatchOverrideReason": "Identity confirmed on site by supervisor",
        },
        headers=headers_sa1,
    )
    assert override_resp.status_code == 202
    approval_id = override_resp.get_json()["approvalId"]

    # SA1 cannot approve their own request
    self_approve_resp = client.post(
        f"/api/workers/photo-override-approvals/{approval_id}/decision",
        json={"decision": "approve"},
        headers=headers_sa1,
    )
    assert self_approve_resp.status_code == 403
    assert self_approve_resp.get_json().get("error") == "approver_must_be_different_user"

    # Insert a second superadmin directly in the DB
    from werkzeug.security import generate_password_hash as _hash
    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            "INSERT INTO users (id, username, password_hash, name, role, company_id) VALUES (?, ?, ?, ?, ?, ?)",
            ("usr-sa2", "superadmin2", _hash("5678"), "SA2", "superadmin", None),
        )
        db.commit()

    login_sa2 = client.post(
        "/api/login",
        json={"username": "superadmin2", "password": "5678", "loginScope": "server-admin"},
    )
    assert login_sa2.status_code == 200
    headers_sa2 = {"Authorization": f"Bearer {login_sa2.get_json()['token']}"}

    # SA2 approves
    approve_resp = client.post(
        f"/api/workers/photo-override-approvals/{approval_id}/decision",
        json={"decision": "approve", "note": ""},
        headers=headers_sa2,
    )
    assert approve_resp.status_code == 200
    approve_body = approve_resp.get_json()
    assert approve_body.get("status") == "approved"

    # Worker photo should now be updated
    workers_resp = client.get("/api/workers", headers=headers_sa2)
    assert workers_resp.status_code == 200
    worker_data = next((w for w in workers_resp.get_json() if w["id"] == worker_id), None)
    assert worker_data is not None
    assert worker_data["photoData"] == "data:image/png;base64,NEWPHOTO"

    # Audit log entry should exist for security.worker_photo_override
    with closing(sqlite3.connect(db_path)) as db:
        row = db.execute(
            "SELECT message FROM audit_logs WHERE event_type = 'security.worker_photo_override' AND target_id = ? ORDER BY created_at DESC LIMIT 1",
            (worker_id,),
        ).fetchone()
        assert row is not None
        assert "Identity confirmed on site by supervisor" in str(row[0] or "")


def test_photo_override_4_eyes_reject_cancels_write(client_and_db):
    """Rejecting a photo override approval prevents the photo from being written."""
    client, db_path = client_and_db
    headers_sa1 = _auth_headers(client)

    create_resp = client.post(
        "/api/workers",
        json=_worker_payload("cmp-default", "CARD-4EYES-2"),
        headers=headers_sa1,
    )
    assert create_resp.status_code == 201
    worker_id = create_resp.get_json()["id"]

    override_resp = client.put(
        f"/api/workers/{worker_id}",
        json={
            "photoData": "data:image/png;base64,REJECTEDPHOTO",
            "photoMatchOverride": True,
            "photoMatchSimilarity": 0.28,
            "photoMatchOverrideReason": "Override that will be rejected",
        },
        headers=headers_sa1,
    )
    assert override_resp.status_code == 202, override_resp.get_json()
    approval_id = override_resp.get_json()["approvalId"]

    # Insert SA2
    from werkzeug.security import generate_password_hash as _hash
    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            "INSERT INTO users (id, username, password_hash, name, role, company_id) VALUES (?, ?, ?, ?, ?, ?)",
            ("usr-sa2-rej", "superadmin2rej", _hash("5678"), "SA2", "superadmin", None),
        )
        db.commit()

    login_sa2 = client.post(
        "/api/login",
        json={"username": "superadmin2rej", "password": "5678", "loginScope": "server-admin"},
    )
    assert login_sa2.status_code == 200
    headers_sa2 = {"Authorization": f"Bearer {login_sa2.get_json()['token']}"}

    # SA2 rejects
    reject_resp = client.post(
        f"/api/workers/photo-override-approvals/{approval_id}/decision",
        json={"decision": "reject", "note": "Photo does not look like the worker"},
        headers=headers_sa2,
    )
    assert reject_resp.status_code == 200
    assert reject_resp.get_json().get("status") == "rejected"

    # Worker photo should still be the original
    workers_resp = client.get("/api/workers", headers=headers_sa2)
    worker_data = next((w for w in workers_resp.get_json() if w["id"] == worker_id), None)
    assert worker_data["photoData"] == "data:image/png;base64,AAA"


def test_support_login_requires_matching_company(client_and_db):
    client, _ = client_and_db

    mismatch_response = client.post(
        "/api/login",
        json={
            "username": "firma",
            "password": "1234",
            "loginScope": "company-admin",
            "supportCompanyId": "cmp-other",
            "supportActorName": "Systemleitung",
        },
    )

    assert mismatch_response.status_code == 200
    payload = mismatch_response.get_json()
    assert payload["ok"] is False
    assert payload["error"] == "support_company_mismatch"


def test_support_session_is_read_only_but_allows_read_and_logout(client_and_db):
    client, _ = client_and_db
    headers, login_payload = _company_admin_auth_headers(
        client,
        supportCompanyId="cmp-default",
        supportActorName="Systemleitung",
    )

    assert bool(login_payload["user"].get("support_read_only")) is True
    assert login_payload["user"].get("support_company_name")
    assert login_payload["user"].get("support_actor_name") == "Systemleitung"

    read_response = client.get("/api/workers", headers=headers)
    assert read_response.status_code == 200

    blocked_write_response = client.post(
        "/api/access-logs",
        json={
            "workerId": "wrk-does-not-matter",
            "direction": "check-in",
            "gate": "Nordtor",
            "note": "Read-only test",
        },
        headers=headers,
    )
    assert blocked_write_response.status_code == 403
    assert blocked_write_response.get_json()["error"] == "support_session_read_only"

    logout_response = client.post("/api/logout", headers=headers)
    assert logout_response.status_code == 200


def test_company_admin_can_access_reporting_and_invoices_scoped(client_and_db):
    client, _ = client_and_db
    headers, login_payload = _company_admin_auth_headers(client)

    user_company_id = login_payload["user"]["company_id"]
    assert user_company_id

    invoices_response = client.get("/api/invoices", headers=headers)
    assert invoices_response.status_code == 200
    invoices = invoices_response.get_json() or []
    assert all(str(row.get("company_id") or "") == user_company_id for row in invoices)

    reporting_response = client.get("/api/reporting/summary", headers=headers)
    assert reporting_response.status_code == 200
    reporting_payload = reporting_response.get_json() or {}
    assert isinstance(reporting_payload, dict)


def test_company_admin_turnstiles_access_limited_to_own_company(client_and_db):
    client, _ = client_and_db
    headers, login_payload = _company_admin_auth_headers(client)

    own_company_id = login_payload["user"]["company_id"]
    assert own_company_id

    own_response = client.get(f"/api/companies/{own_company_id}/turnstiles", headers=headers)
    assert own_response.status_code == 200

    other_company_id = "cmp-other" if own_company_id != "cmp-other" else "cmp-default"
    foreign_response = client.get(f"/api/companies/{other_company_id}/turnstiles", headers=headers)
    assert foreign_response.status_code == 403
    assert foreign_response.get_json().get("error") == "forbidden"


def test_superadmin_preview_session_scopes_workers_and_companies(client_and_db):
    client, db_path = client_and_db
    headers = _auth_headers(client)

    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, subcompany_id, first_name, last_name, insurance_number,
                worker_type, role, site, valid_until, visitor_company, visit_purpose,
                host_name, visit_end_at, status, photo_data, badge_id, badge_pin_hash, physical_card_id, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wrk-preview-default",
                "cmp-default",
                None,
                "Preview",
                "Default",
                "SV-PREVIEW-001",
                "worker",
                "Monteur",
                "Nordtor",
                "2030-01-01",
                "",
                "",
                "",
                "",
                "aktiv",
                "data:image/png;base64,AAA",
                "BP-PREVIEW-001",
                "",
                "",
                None,
            ),
        )
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, subcompany_id, first_name, last_name, insurance_number,
                worker_type, role, site, valid_until, visitor_company, visit_purpose,
                host_name, visit_end_at, status, photo_data, badge_id, badge_pin_hash, physical_card_id, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wrk-preview-other",
                "cmp-other",
                None,
                "Preview",
                "Other",
                "SV-PREVIEW-002",
                "worker",
                "Monteur",
                "Nordtor",
                "2030-01-01",
                "",
                "",
                "",
                "",
                "aktiv",
                "data:image/png;base64,AAA",
                "BP-PREVIEW-002",
                "",
                "",
                None,
            ),
        )
        db.commit()

    workers_before = client.get("/api/workers", headers=headers)
    assert workers_before.status_code == 200
    all_worker_ids = {row.get("id") for row in (workers_before.get_json() or [])}
    assert "wrk-preview-default" in all_worker_ids
    assert "wrk-preview-other" in all_worker_ids

    set_preview = client.post(
        "/api/superadmin/preview-session",
        json={"company_id": "cmp-default"},
        headers=headers,
    )
    assert set_preview.status_code == 200
    assert set_preview.get_json().get("preview_company_id") == "cmp-default"

    workers_scoped = client.get("/api/workers", headers=headers)
    assert workers_scoped.status_code == 200
    scoped_ids = {row.get("id") for row in (workers_scoped.get_json() or [])}
    assert "wrk-preview-default" in scoped_ids
    assert "wrk-preview-other" not in scoped_ids

    companies_scoped = client.get("/api/companies", headers=headers)
    assert companies_scoped.status_code == 200
    company_ids = [row.get("id") for row in (companies_scoped.get_json() or [])]
    assert company_ids == ["cmp-default"]

    clear_preview = client.post(
        "/api/superadmin/preview-session",
        json={"company_id": None},
        headers=headers,
    )
    assert clear_preview.status_code == 200
    assert clear_preview.get_json().get("preview_company_id") is None

    workers_after = client.get("/api/workers", headers=headers)
    assert workers_after.status_code == 200
    all_again_ids = {row.get("id") for row in (workers_after.get_json() or [])}
    assert "wrk-preview-default" in all_again_ids
    assert "wrk-preview-other" in all_again_ids


def test_company_admin_cannot_set_superadmin_preview_session(client_and_db):
    client, _ = client_and_db
    headers, _ = _company_admin_auth_headers(client)

    response = client.post(
        "/api/superadmin/preview-session",
        json={"company_id": "cmp-default"},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.get_json().get("error") == "forbidden"


def test_invoice_incident_export_contains_retry_dead_letter_and_alert_rows(client_and_db):
    client, db_path = client_and_db
    headers = _auth_headers(client)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    future_retry = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    with closing(sqlite3.connect(db_path)) as db:
        admin_user = db.execute("SELECT id FROM users WHERE role = 'superadmin' ORDER BY id LIMIT 1").fetchone()
        assert admin_user is not None

        db.execute(
            """
            INSERT INTO invoices (
                id, invoice_number, company_id, recipient_email, invoice_date, invoice_period, description,
                net_amount, vat_rate, vat_amount, total_amount, status, error_message, sent_at,
                rendered_html, created_by_user_id, created_at, due_date, reminder_stage,
                last_reminder_sent_at, last_reminder_error, send_attempt_count, last_send_attempt_at, next_retry_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inv-export-1",
                "RE-EXPORT-1",
                "cmp-default",
                "billing@example.com",
                "2026-04-19",
                "2026-04",
                "Export-Testrechnung",
                100.0,
                19.0,
                19.0,
                119.0,
                "send_failed",
                "SMTP timeout",
                None,
                "<html></html>",
                admin_user[0],
                now,
                "2026-05-03",
                0,
                None,
                "",
                5,
                now,
                future_retry,
            ),
        )
        db.execute(
            """
            INSERT INTO invoice_dead_letters (id, invoice_id, reason, last_error, created_at, resolved_at)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            ("dead-export-1", "inv-export-1", "max_retries_exhausted", "SMTP timeout", now),
        )
        db.execute(
            """
            INSERT INTO invoice_send_attempts (id, invoice_id, attempt_number, outcome, error_message, actor_label, next_retry_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("att-export-1", "inv-export-1", 5, "failed", "SMTP timeout", "system", future_retry, now),
        )
        db.execute(
            """
            INSERT INTO system_alerts (id, code, severity, message, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("alert-export-1", "smtp_circuit_open", "critical", "SMTP Circuit Breaker offen", '{"scope":"billing"}', now),
        )
        db.commit()

    response = client.get("/api/invoices/incidents/export.csv", headers=headers)

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    content_disposition = response.headers.get("Content-Disposition", "")
    assert "invoice-incidents-" in content_disposition
    assert content_disposition.lower().endswith('.pdf"') or ".pdf" in content_disposition.lower()
    content = response.get_data()
    assert content.startswith(b"%PDF-")


def test_invoice_bulk_retry_requires_second_superadmin_approval(client_and_db):
    client, db_path = client_and_db
    requester_headers = _auth_headers(client)

    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            "INSERT INTO users (id, username, password_hash, name, role, company_id) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "usr-superadmin-2",
                "superadmin2",
                server.generate_password_hash("1234"),
                "Zweite Leitung",
                "superadmin",
                None,
            ),
        )
        admin_user = db.execute("SELECT id FROM users WHERE role = 'superadmin' ORDER BY id LIMIT 1").fetchone()
        assert admin_user is not None
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        db.execute(
            """
            INSERT INTO invoices (
                id, invoice_number, company_id, recipient_email, invoice_date, invoice_period, description,
                net_amount, vat_rate, vat_amount, total_amount, status, error_message, sent_at,
                rendered_html, created_by_user_id, created_at, due_date, reminder_stage,
                last_reminder_sent_at, last_reminder_error, send_attempt_count, last_send_attempt_at, next_retry_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inv-approval-1",
                "RE-APPROVAL-1",
                "cmp-default",
                "billing@example.com",
                "2026-04-19",
                "2026-04",
                "Freigabe-Test",
                100.0,
                19.0,
                19.0,
                119.0,
                "send_failed",
                "SMTP timeout",
                None,
                "<html></html>",
                admin_user[0],
                now,
                "2026-05-03",
                0,
                None,
                "",
                2,
                now,
                now,
            ),
        )
        db.commit()

    approval_response = client.post(
        "/api/invoices/retry-send-bulk",
        json={"invoiceIds": ["inv-approval-1"]},
        headers=requester_headers,
    )
    assert approval_response.status_code == 202
    approval_payload = approval_response.get_json()
    assert approval_payload.get("approvalRequested") is True
    approval_id = approval_payload.get("approvalId")
    assert approval_id

    self_approve_response = client.post(
        f"/api/invoices/approvals/{approval_id}/decision",
        json={"decision": "approve"},
        headers=requester_headers,
    )
    assert self_approve_response.status_code == 403
    assert self_approve_response.get_json().get("error") == "approver_must_be_different_user"

    approver_login = client.post(
        "/api/login",
        json={"username": "superadmin2", "password": "1234", "loginScope": "server-admin"},
    )
    assert approver_login.status_code == 200
    approver_headers = {"Authorization": f"Bearer {approver_login.get_json()['token']}"}

    approve_response = client.post(
        f"/api/invoices/approvals/{approval_id}/decision",
        json={"decision": "approve"},
        headers=approver_headers,
    )
    assert approve_response.status_code == 200
    approved_payload = approve_response.get_json()
    assert approved_payload.get("status") == "approved"

    pending_after = client.get("/api/invoices/approvals/pending", headers=requester_headers)
    assert pending_after.status_code == 200
    pending_rows = pending_after.get_json() or []
    assert all(str(row.get("id")) != approval_id for row in pending_rows)


def test_invoice_approval_reject_requires_note_and_expired_approval_cannot_be_decided(client_and_db):
    client, db_path = client_and_db
    requester_headers = _auth_headers(client)

    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            "INSERT INTO users (id, username, password_hash, name, role, company_id) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "usr-superadmin-3",
                "superadmin3",
                server.generate_password_hash("1234"),
                "Dritte Leitung",
                "superadmin",
                None,
            ),
        )
        admin_user = db.execute("SELECT id FROM users WHERE role = 'superadmin' ORDER BY id LIMIT 1").fetchone()
        assert admin_user is not None
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        db.execute(
            """
            INSERT INTO invoices (
                id, invoice_number, company_id, recipient_email, invoice_date, invoice_period, description,
                net_amount, vat_rate, vat_amount, total_amount, status, error_message, sent_at,
                rendered_html, created_by_user_id, created_at, due_date, reminder_stage,
                last_reminder_sent_at, last_reminder_error, send_attempt_count, last_send_attempt_at, next_retry_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inv-approval-2",
                "RE-APPROVAL-2",
                "cmp-default",
                "billing@example.com",
                "2026-04-19",
                "2026-04",
                "Freigabe-Test 2",
                100.0,
                19.0,
                19.0,
                119.0,
                "send_failed",
                "SMTP timeout",
                None,
                "<html></html>",
                admin_user[0],
                now,
                "2026-05-03",
                0,
                None,
                "",
                2,
                now,
                now,
            ),
        )
        db.commit()

    approval_response = client.post(
        "/api/invoices/retry-send-bulk",
        json={"invoiceIds": ["inv-approval-2"]},
        headers=requester_headers,
    )
    assert approval_response.status_code == 202
    approval_id = approval_response.get_json().get("approvalId")
    assert approval_id

    approver_login = client.post(
        "/api/login",
        json={"username": "superadmin3", "password": "1234", "loginScope": "server-admin"},
    )
    assert approver_login.status_code == 200
    approver_headers = {"Authorization": f"Bearer {approver_login.get_json()['token']}"}

    reject_without_note = client.post(
        f"/api/invoices/approvals/{approval_id}/decision",
        json={"decision": "reject", "note": ""},
        headers=approver_headers,
    )
    assert reject_without_note.status_code == 400
    assert reject_without_note.get_json().get("error") == "decision_note_required"

    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with closing(sqlite3.connect(db_path)) as db:
        db.execute("UPDATE operation_approvals SET expires_at = ? WHERE id = ?", (past, approval_id))
        db.commit()

    approve_expired = client.post(
        f"/api/invoices/approvals/{approval_id}/decision",
        json={"decision": "approve"},
        headers=approver_headers,
    )
    assert approve_expired.status_code == 410
    assert approve_expired.get_json().get("error") == "approval_expired"


def test_gate_tap_returns_contactless_feedback_for_checkin_and_checkout(client_and_db):
    client, db_path = client_and_db
    api_key = _issue_turnstile_api_key(db_path)

    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, subcompany_id, first_name, last_name, insurance_number,
                worker_type, role, site, valid_until, visitor_company, visit_purpose,
                host_name, visit_end_at, status, photo_data, badge_id, badge_pin_hash, physical_card_id, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wrk-gate-feedback",
                "cmp-default",
                None,
                "Nfc",
                "Tester",
                "SV-TEST-001",
                "worker",
                "Elektriker",
                "Nordtor",
                "2030-01-01",
                "",
                "",
                "",
                "",
                "aktiv",
                "data:image/png;base64,AAA",
                "BP-NFC-001",
                "",
                "NFC-UNIT-001",
                None,
            ),
        )
        db.commit()

    headers = {"X-Gate-Key": api_key}

    checkin_response = client.post(
        "/api/gates/tap",
        json={"physicalCardId": "NFC-UNIT-001", "direction": "check-in", "gate": "Nordtor"},
        headers=headers,
    )
    assert checkin_response.status_code == 201
    checkin_payload = checkin_response.get_json()
    assert checkin_payload.get("feedbackTitle") == "ANMELDUNG ERFOLGREICH"
    assert checkin_payload.get("feedbackMessage") == "Du bist jetzt angemeldet."
    assert checkin_payload.get("feedbackTone") == "success_in"

    checkout_response = client.post(
        "/api/gates/tap",
        json={"physicalCardId": "NFC-UNIT-001", "direction": "check-out", "gate": "Nordtor"},
        headers=headers,
    )
    assert checkout_response.status_code == 201
    checkout_payload = checkout_response.get_json()
    assert checkout_payload.get("feedbackTitle") == "ABMELDUNG ERFOLGREICH"
    assert checkout_payload.get("feedbackMessage") == "Du bist jetzt abgemeldet."
    assert checkout_payload.get("feedbackTone") == "success_out"


def test_gate_tap_auto_toggles_direction_when_not_provided(client_and_db):
    client, db_path = client_and_db
    api_key = _issue_turnstile_api_key(db_path)

    with closing(sqlite3.connect(db_path)) as db:
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, subcompany_id, first_name, last_name, insurance_number,
                worker_type, role, site, valid_until, visitor_company, visit_purpose,
                host_name, visit_end_at, status, photo_data, badge_id, badge_pin_hash, physical_card_id, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wrk-gate-toggle",
                "cmp-default",
                None,
                "Auto",
                "Toggle",
                "SV-TEST-002",
                "worker",
                "Monteur",
                "Nordtor",
                "2030-01-01",
                "",
                "",
                "",
                "",
                "aktiv",
                "data:image/png;base64,AAA",
                "BP-NFC-002",
                "",
                "NFC-UNIT-002",
                None,
            ),
        )
        db.commit()

    headers = {"X-Gate-Key": api_key}

    first_tap = client.post(
        "/api/gates/tap",
        json={"physicalCardId": "NFC-UNIT-002", "gate": "Nordtor"},
        headers=headers,
    )
    assert first_tap.status_code == 201
    first_payload = first_tap.get_json()
    assert first_payload.get("direction") == "check-in"
    assert first_payload.get("feedbackMessage") == "Du bist jetzt angemeldet."

    second_tap = client.post(
        "/api/gates/tap",
        json={"physicalCardId": "NFC-UNIT-002", "gate": "Nordtor"},
        headers=headers,
    )
    assert second_tap.status_code == 201
    second_payload = second_tap.get_json()
    assert second_payload.get("direction") == "check-out"
    assert second_payload.get("feedbackMessage") == "Du bist jetzt abgemeldet."



