"""Tests for company system transfer import/export (hardened)."""
from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from pathlib import Path

from backend.app.platform.transfer.archive import open_transfer_bytes, package_from_zip
from backend.app.platform.transfer.schema import SCHEMA_VERSION
from backend.app.platform.transfer.service import validate_package_bytes
from backend import server


def _superadmin_headers(client):
    resp = client.post(
        "/api/login",
        json={"username": "superadmin", "password": "1234", "loginScope": "server-admin"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def _build_zip(domains: dict, files: dict[str, bytes] | None = None, company_id: str = "co-transfer-1") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "schemaVersion": SCHEMA_VERSION,
            "companyId": company_id,
            "domains": list(domains.keys()),
            "counts": {k: len(v) for k, v in domains.items()},
        }
        zf.writestr("manifest.json", json.dumps(manifest))
        for name, rows in domains.items():
            zf.writestr(f"domains/{name}.json", json.dumps(rows))
        for rel, data in (files or {}).items():
            zf.writestr(f"files/{rel}", data)
    return buf.getvalue()


def _full_package_blob() -> bytes:
    doc_bytes = b"%PDF-1.4 transfer-doc"
    return _build_zip(
        {
            "companies": [
                {
                    "id": "co-transfer-1",
                    "name": "Transfer GmbH",
                    "contact": "a@b.de",
                    "billing_email": "a@b.de",
                    "status": "aktiv",
                }
            ],
            "workers": [
                {
                    "id": "w-tr-1",
                    "company_id": "co-transfer-1",
                    "first_name": "Anna",
                    "last_name": "Muster",
                    "badge_id": "TR-1",
                    "status": "aktiv",
                }
            ],
            "employment_contracts": [
                {
                    "id": "ec-1",
                    "company_id": "co-transfer-1",
                    "worker_id": "w-tr-1",
                    "contract_type": "employment",
                    "title": "Arbeitsvertrag Anna",
                    "status": "final",
                    "final_text": "Vertragstext",
                }
            ],
            "worker_documents": [
                {
                    "id": "wd-1",
                    "company_id": "co-transfer-1",
                    "worker_id": "w-tr-1",
                    "doc_type": "ausweis",
                    "filename": "ausweis.pdf",
                    "archive_file": "worker_documents/wd-1/ausweis.pdf",
                }
            ],
            "access_logs": [
                {
                    "id": "al-1",
                    "worker_id": "w-tr-1",
                    "direction": "check-in",
                    "gate": "Tor A",
                    "timestamp": "2026-08-01T08:00:00Z",
                }
            ],
            "deployment_days": [
                {
                    "id": "dd-1",
                    "company_id": "co-transfer-1",
                    "worker_id": "w-tr-1",
                    "work_date": "2026-08-01",
                    "location_label": "Baustelle Nord",
                }
            ],
        },
        files={"worker_documents/wd-1/ausweis.pdf": doc_bytes},
    )


def test_open_zip_package_counts():
    blob = _build_zip(
        {
            "companies": [{"id": "co-transfer-1", "name": "Transfer GmbH"}],
            "workers": [
                {
                    "id": "w1",
                    "company_id": "co-transfer-1",
                    "first_name": "Anna",
                    "last_name": "Test",
                    "badge_id": "B1",
                }
            ],
        }
    )
    package = package_from_zip(blob)
    assert package.schema_version == SCHEMA_VERSION
    assert len(package.domains["workers"]) == 1
    assert validate_package_bytes(blob, filename="x.zip")["ok"] is True


def test_transfer_import_sync_with_contracts_and_docs(client_and_db, tmp_path, monkeypatch):
    client, db_path = client_and_db
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(server, "DOCS_UPLOAD_DIR", docs_dir)
    headers = _superadmin_headers(client)
    blob = _full_package_blob()

    resp = client.post(
        "/api/transfer/import/start?sync=1",
        data={"file": (io.BytesIO(blob), "company-transfer.zip"), "dryRun": "0", "mergeMode": "skip"},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["ok"] is True
    assert body["companyId"] == "co-transfer-1"
    assert body["summary"]["accepted"]["workers"] == 1
    assert body["summary"]["accepted"]["employment_contracts"] == 1
    assert body["summary"]["accepted"]["worker_documents"] == 1
    assert body["summary"].get("backupPath")
    assert int(body["completionPercent"]) >= 90

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    assert con.execute("SELECT name FROM companies WHERE id = ?", ("co-transfer-1",)).fetchone()["name"] == "Transfer GmbH"
    doc = con.execute("SELECT * FROM worker_documents WHERE id = ?", ("wd-1",)).fetchone()
    assert doc is not None
    assert Path(doc["file_path"]).read_bytes() == b"%PDF-1.4 transfer-doc"
    con.close()


def test_conflict_skip_keeps_existing(client_and_db, tmp_path, monkeypatch):
    client, db_path = client_and_db
    monkeypatch.setattr(server, "DOCS_UPLOAD_DIR", tmp_path / "docs")
    headers = _superadmin_headers(client)
    blob = _full_package_blob()
    assert client.post(
        "/api/transfer/import/start?sync=1",
        data={"file": (io.BytesIO(blob), "a.zip"), "dryRun": "0", "mergeMode": "skip"},
        headers=headers,
        content_type="multipart/form-data",
    ).status_code == 200

    # Change company name in package → conflict under skip
    conflict_blob = _build_zip(
        {
            "companies": [
                {
                    "id": "co-transfer-1",
                    "name": "ANDERE Firma",
                    "contact": "a@b.de",
                    "billing_email": "a@b.de",
                    "status": "aktiv",
                }
            ],
            "workers": [
                {
                    "id": "w-tr-1",
                    "company_id": "co-transfer-1",
                    "first_name": "Anna",
                    "last_name": "Muster",
                    "badge_id": "TR-1",
                    "status": "aktiv",
                }
            ],
        }
    )
    resp = client.post(
        "/api/transfer/import/start?sync=1",
        data={"file": (io.BytesIO(conflict_blob), "b.zip"), "dryRun": "0", "mergeMode": "skip"},
        headers=headers,
        content_type="multipart/form-data",
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["summary"]["conflicts"]["companies"] >= 1
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT name FROM companies WHERE id = ?", ("co-transfer-1",)).fetchone()[0] == "Transfer GmbH"
    con.close()


def test_conflict_replace_overwrites(client_and_db, tmp_path, monkeypatch):
    client, db_path = client_and_db
    monkeypatch.setattr(server, "DOCS_UPLOAD_DIR", tmp_path / "docs")
    headers = _superadmin_headers(client)
    blob = _full_package_blob()
    client.post(
        "/api/transfer/import/start?sync=1",
        data={"file": (io.BytesIO(blob), "a.zip"), "dryRun": "0", "mergeMode": "skip"},
        headers=headers,
        content_type="multipart/form-data",
    )
    conflict_blob = _build_zip(
        {
            "companies": [
                {
                    "id": "co-transfer-1",
                    "name": "Neu GmbH",
                    "contact": "a@b.de",
                    "billing_email": "a@b.de",
                    "status": "aktiv",
                }
            ],
        }
    )
    resp = client.post(
        "/api/transfer/import/start?sync=1",
        data={"file": (io.BytesIO(conflict_blob), "b.zip"), "dryRun": "0", "mergeMode": "replace"},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["summary"]["accepted"]["companies"] == 1
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT name FROM companies WHERE id = ?", ("co-transfer-1",)).fetchone()[0] == "Neu GmbH"
    con.close()


def test_export_roundtrip(client_and_db, tmp_path, monkeypatch):
    client, db_path = client_and_db
    monkeypatch.setattr(server, "DOCS_UPLOAD_DIR", tmp_path / "docs")
    headers = _superadmin_headers(client)
    blob = _full_package_blob()
    assert client.post(
        "/api/transfer/import/start?sync=1",
        data={"file": (io.BytesIO(blob), "a.zip"), "dryRun": "0", "mergeMode": "skip"},
        headers=headers,
        content_type="multipart/form-data",
    ).status_code == 200

    exported = client.get("/api/transfer/export?companyId=co-transfer-1", headers=headers)
    assert exported.status_code == 200, exported.get_data(as_text=True)
    assert exported.mimetype == "application/zip"
    assert exported.data[:2] == b"PK"
    package = package_from_zip(exported.data)
    assert package.domains["workers"]
    assert package.domains["employment_contracts"]
    assert any(k.startswith("worker_documents/") for k in package.files)


def test_legacy_json_still_opens_as_transfer_package():
    raw = json.dumps(
        {
            "meta": {"schemaVersion": "2026-04-export-v2"},
            "companies": [{"id": "c1", "name": "Alt"}],
            "workers": [{"id": "w1", "company_id": "c1", "first_name": "X", "last_name": "Y"}],
            "accessLogs": [],
            "invoices": [],
            "subcompanies": [],
        }
    ).encode("utf-8")
    package = open_transfer_bytes(raw, filename="legacy.json")
    assert "companies" in package.domains
    assert package.source_format == "json"


def test_run_import_dry_run_does_not_write(client_and_db):
    client, db_path = client_and_db
    headers = _superadmin_headers(client)
    blob = _build_zip(
        {
            "companies": [{"id": "co-dry", "name": "Dry GmbH"}],
            "workers": [
                {
                    "id": "w-dry",
                    "company_id": "co-dry",
                    "first_name": "Dry",
                    "last_name": "Run",
                    "badge_id": "D1",
                }
            ],
        },
        company_id="co-dry",
    )
    resp = client.post(
        "/api/transfer/import/start?sync=1",
        data={"file": (io.BytesIO(blob), "dry.zip"), "dryRun": "1"},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["dryRun"] is True
    assert body["summary"]["accepted"]["workers"] == 1
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT COUNT(1) FROM companies WHERE id = ?", ("co-dry",)).fetchone()[0] == 0
    con.close()


def _company_admin_headers(client):
    resp = client.post(
        "/api/login",
        json={"username": "firma", "password": "1234", "loginScope": "company-admin"},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return {"Authorization": f"Bearer {resp.get_json()['token']}"}


def test_enterprise_company_admin_can_import_with_remap(client_and_db, tmp_path, monkeypatch):
    client, db_path = client_and_db
    monkeypatch.setattr(server, "DOCS_UPLOAD_DIR", tmp_path / "docs")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE companies SET plan = 'enterprise' WHERE id = 'cmp-default'")
    con.commit()
    con.close()

    headers = _company_admin_headers(client)
    # Package from a foreign/old company id — must remap into cmp-default
    blob = _build_zip(
        {
            "companies": [{"id": "old-co", "name": "Alt GmbH", "status": "aktiv"}],
            "workers": [
                {
                    "id": "w-old-1",
                    "company_id": "old-co",
                    "first_name": "Ali",
                    "last_name": "Restore",
                    "badge_id": "R1",
                    "status": "aktiv",
                }
            ],
            "employment_contracts": [
                {
                    "id": "ec-old",
                    "company_id": "old-co",
                    "worker_id": "w-old-1",
                    "contract_type": "employment",
                    "title": "Vertrag",
                    "status": "final",
                    "final_text": "Text",
                }
            ],
        },
        company_id="old-co",
    )
    resp = client.post(
        "/api/transfer/import/start?sync=1",
        data={"file": (io.BytesIO(blob), "restore.zip"), "dryRun": "0", "mergeMode": "replace"},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["companyId"] == "cmp-default"
    assert body["summary"]["remap"]["targetCompanyId"] == "cmp-default"
    assert body["summary"]["accepted"]["workers"] == 1

    con = sqlite3.connect(db_path)
    assert con.execute("SELECT COUNT(1) FROM workers WHERE id = ? AND company_id = ?", ("w-old-1", "cmp-default")).fetchone()[0] == 1
    assert con.execute("SELECT COUNT(1) FROM employment_contracts WHERE company_id = ?", ("cmp-default",)).fetchone()[0] >= 1
    assert con.execute("SELECT COUNT(1) FROM companies WHERE id = ?", ("old-co",)).fetchone()[0] == 0
    con.close()


def test_non_enterprise_company_admin_denied(client_and_db):
    client, db_path = client_and_db
    con = sqlite3.connect(db_path)
    con.execute("UPDATE companies SET plan = 'professional' WHERE id = 'cmp-default'")
    con.commit()
    con.close()
    headers = _company_admin_headers(client)
    blob = _build_zip(
        {
            "companies": [{"id": "cmp-default", "name": "X"}],
            "workers": [{"id": "w1", "company_id": "cmp-default", "first_name": "A", "last_name": "B", "badge_id": "1"}],
        },
        company_id="cmp-default",
    )
    resp = client.post(
        "/api/transfer/import/start?sync=1",
        data={"file": (io.BytesIO(blob), "x.zip"), "dryRun": "1"},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403
    body = resp.get_json()
    assert body.get("error") == "feature_not_available"
    assert body.get("feature") == "system_transfer"


def test_enterprise_company_admin_export_own_company_only(client_and_db, tmp_path, monkeypatch):
    client, db_path = client_and_db
    monkeypatch.setattr(server, "DOCS_UPLOAD_DIR", tmp_path / "docs")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE companies SET plan = 'enterprise' WHERE id = 'cmp-default'")
    con.commit()
    con.close()
    headers = _company_admin_headers(client)
    # Seed via superadmin into another company — company-admin must not export it
    sa = _superadmin_headers(client)
    other = _full_package_blob()
    client.post(
        "/api/transfer/import/start?sync=1",
        data={"file": (io.BytesIO(other), "other.zip"), "dryRun": "0", "mergeMode": "skip"},
        headers=sa,
        content_type="multipart/form-data",
    )
    # Even if they pass another companyId, API forces own company
    resp = client.get("/api/transfer/export?companyId=co-transfer-1", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("X-Transfer-Company-Id") == "cmp-default"
