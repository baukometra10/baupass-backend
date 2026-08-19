"""Tests: WorkPass Lohn tax/earnings docs accepted like Lohnabrechnung."""
from __future__ import annotations

import base64
import json

import pytest

from backend.app.platform.worker_documents import (
    WORKER_PAYROLL_DOC_TYPES,
    normalize_doc_type,
    resolve_payroll_doc_type,
)


MINIMAL_PDF = base64.b64encode(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n").decode()


def test_normalize_doc_type_tax_aliases():
    assert normalize_doc_type("lohnsteuerbescheinigung") == "lohnsteuerbescheinigung"
    assert normalize_doc_type("tax_certificate") == "lohnsteuerbescheinigung"
    assert normalize_doc_type("Lohnsteuer") == "lohnsteuerbescheinigung"
    assert normalize_doc_type("verdienstbescheinigung") == "verdienstabrechnung"
    assert normalize_doc_type("earnings_statement") == "verdienstabrechnung"
    assert normalize_doc_type("payslip") == "lohnabrechnung"
    assert normalize_doc_type("vordienstbescheinigung") == "vordienstbescheinigung"
    assert normalize_doc_type("jahresabrechnung") == "jahresabrechnung"


def test_infer_payroll_doc_type_from_title():
    from backend.app.platform.worker_documents import infer_payroll_doc_type_from_title

    assert infer_payroll_doc_type_from_title("Vordienstbescheinigung Max Mustermann") == "vordienstbescheinigung"
    assert infer_payroll_doc_type_from_title("Jahresabrechnung 2025") == "jahresabrechnung"
    assert infer_payroll_doc_type_from_title("Monatsabrechnung März 2026") == "lohnabrechnung"
    assert infer_payroll_doc_type_from_title("كشف حساب سنوي") == "jahresabrechnung"


def test_resolve_preserves_exact_title():
    from backend.app.platform.worker_documents import display_document_label, resolve_document_title

    assert resolve_document_title({"title": "Vordienstbescheinigung"}) == "Vordienstbescheinigung"
    assert (
        display_document_label({"title": "Jahresabrechnung 2025"}, doc_type="jahresabrechnung")
        == "Jahresabrechnung 2025"
    )


def test_resolve_payroll_doc_type_from_delivery():
    assert resolve_payroll_doc_type({"documentType": "lohnsteuerbescheinigung"}) == "lohnsteuerbescheinigung"
    assert resolve_payroll_doc_type({"type": "verdienstbescheinigung"}) == "verdienstabrechnung"
    assert resolve_payroll_doc_type({"type": "payslip"}) == "lohnabrechnung"
    assert resolve_payroll_doc_type({"type": "invoice"}) == "lohnabrechnung"
    assert "lohnsteuerbescheinigung" in WORKER_PAYROLL_DOC_TYPES
    assert "verdienstabrechnung" in WORKER_PAYROLL_DOC_TYPES


def test_lohn_delivery_title_maps_vordienst():
    from backend.app.platform.accounting.service import lohn_delivery_to_statement

    stmt = lohn_delivery_to_statement(
        {
            "kind": "platform.employee.delivery.v1",
            "type": "document",
            "title": "Vordienstbescheinigung",
            "company": {"id": "cmp-test"},
            "employee": {"id": "emp-1", "name": "Max Mustermann"},
            "period": "2026-01",
            "pdfBase64": MINIMAL_PDF,
            "deliveryId": "del-vd-1",
        }
    )
    assert stmt is not None
    assert stmt["title"] == "Vordienstbescheinigung"
    assert stmt["docType"] == "vordienstbescheinigung"
    assert stmt["pdfSource"] == "lohn_original"
    assert stmt["pdfImmutable"] is True


def test_ensure_statement_keeps_original_pdf(tmp_path, monkeypatch):
    from backend.app.platform.accounting.service import ensure_statement_delivery_pdf

    pdf_path = tmp_path / "orig.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 small original from Lohn\n%%EOF\n")
    stmt = {
        "id": "stmt-1",
        "company_id": "cmp-test",
        "period": "2026-01",
        "file_path": str(pdf_path),
        "file_size": pdf_path.stat().st_size,
        "filename": "Vordienstbescheinigung.pdf",
        "meta_json": json.dumps({"pdfSource": "lohn_original", "pdfImmutable": True, "title": "Vordienstbescheinigung"}),
    }

    class _FakeDb:
        def execute(self, *a, **k):
            raise AssertionError("must not rewrite original Lohn PDF")

        def commit(self):
            raise AssertionError("must not rewrite original Lohn PDF")

    out = ensure_statement_delivery_pdf(_FakeDb(), stmt, {"period": "2026-01"}, force=False)
    assert out.get("ok") is True
    assert out.get("skipped") == "exact_lohn"
    assert out.get("path") == str(pdf_path)
    assert pdf_path.read_bytes().startswith(b"%PDF")


def test_ensure_statement_does_not_remake_missing_immutable():
    from backend.app.platform.accounting.service import ensure_statement_delivery_pdf

    stmt = {
        "id": "stmt-missing",
        "company_id": "cmp-test",
        "period": "2026-01",
        "file_path": "/no/such/vordienst.pdf",
        "file_size": 0,
        "filename": "Vordienstbescheinigung.pdf",
        "meta_json": json.dumps({"pdfSource": "lohn_original", "pdfImmutable": True}),
    }

    class _FakeDb:
        def execute(self, *a, **k):
            raise AssertionError("must not remake empty Datev PDF for immutable docs")

        def commit(self):
            raise AssertionError("must not remake empty Datev PDF for immutable docs")

    out = ensure_statement_delivery_pdf(_FakeDb(), stmt, {"period": "2026-01"}, force=False)
    assert out.get("ok") is False
    assert out.get("error") == "missing_pdf"


def test_lohn_delivery_payslip_regression():
    from backend.app.platform.accounting.service import lohn_delivery_to_statement

    stmt = lohn_delivery_to_statement(
        {
            "kind": "platform.employee.delivery.v1",
            "type": "payslip",
            "company": {"id": "cmp-test"},
            "employee": {"id": "emp-1", "name": "Max Mustermann"},
            "period": "2026-01",
            "pdfBase64": MINIMAL_PDF,
            "deliveryId": "del-pay-1",
        }
    )
    assert stmt is not None
    assert stmt["docType"] == "lohnabrechnung"


def test_ingest_and_release_preserves_tax_doc_type(tmp_path, monkeypatch):
    pytest.importorskip("flask")
    from backend.app.platform.accounting import repository as repo
    from backend.app.platform.accounting.schema import ensure_accounting_schema
    from backend.app.platform.accounting.service import (
        _attach_worker_document,
        _statement_doc_type,
        ingest_statements,
        lohn_delivery_to_statement,
    )

    # Lightweight in-memory sqlite via the project's test helpers if available.
    try:
        from backend.tests.conftest import make_test_db  # type: ignore
    except Exception:
        import sqlite3

        def make_test_db():
            db = sqlite3.connect(":memory:")
            db.row_factory = sqlite3.Row
            return db

    db = make_test_db()
    ensure_accounting_schema(db)
    try:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS companies (
              id TEXT PRIMARY KEY, name TEXT, plan TEXT DEFAULT 'starter', deleted_at TEXT
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS workers (
              id TEXT PRIMARY KEY, company_id TEXT, first_name TEXT, last_name TEXT,
              badge_id TEXT, site TEXT, contact_email TEXT, deleted_at TEXT
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_documents (
              id TEXT PRIMARY KEY, worker_id TEXT, company_id TEXT, doc_type TEXT,
              filename TEXT, file_path TEXT, file_size INTEGER,
              source_email_from TEXT, source_inbox_id TEXT, uploaded_by_user_id TEXT,
              created_at TEXT, notes TEXT
            )
            """
        )
        db.execute("INSERT OR IGNORE INTO companies (id, name) VALUES ('cmp-test', 'Test GmbH')")
        db.execute(
            "INSERT OR IGNORE INTO workers (id, company_id, first_name, last_name, badge_id) "
            "VALUES ('emp-1', 'cmp-test', 'Max', 'Mustermann', 'B1')"
        )
        db.commit()
    except Exception:
        pass

    storage = tmp_path / "payroll"
    storage.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "backend.app.platform.accounting.service._storage_dir",
        lambda company_id, period: storage / str(company_id) / str(period),
    )

    delivery = lohn_delivery_to_statement(
        {
            "kind": "platform.employee.delivery.v1",
            "type": "verdienstabrechnung",
            "documentType": "verdienstabrechnung",
            "company": {"id": "cmp-test"},
            "employee": {"id": "emp-1"},
            "period": "2026-02",
            "pdfBase64": MINIMAL_PDF,
            "deliveryId": "del-earn-1",
        }
    )
    assert delivery and delivery["docType"] == "verdienstabrechnung"

    result = ingest_statements(
        db,
        company_id="cmp-test",
        period="2026-02",
        statements=[delivery],
        notes="test tax doc",
    )
    assert result.get("ok") is True
    assert result.get("createdCount") == 1
    stmts = repo.list_batch_statements(db, result["batchId"])
    assert len(stmts) == 1
    assert stmts[0]["docType"] == "verdienstabrechnung"
    assert _statement_doc_type(stmts[0]) == "verdienstabrechnung"

    path = stmts[0].get("file_path") or ""
    assert path
    doc_id = _attach_worker_document(
        db,
        company_id="cmp-test",
        worker_id="emp-1",
        filename=stmts[0].get("filename") or "x.pdf",
        file_path=path,
        file_size=int(stmts[0].get("fileSize") or stmts[0].get("file_size") or 0),
        uploaded_by_user_id="user-1",
        period="2026-02",
        doc_type="verdienstabrechnung",
    )
    row = db.execute("SELECT doc_type FROM worker_documents WHERE id = ?", (doc_id,)).fetchone()
    assert row
    assert str(row["doc_type"] if hasattr(row, "keys") else row[0]) == "verdienstabrechnung"


def test_statements_from_lohn_payload_preserves_doc_type():
    from backend.app.platform.accounting.service import statements_from_lohn_payload

    rows = statements_from_lohn_payload(
        {
            "event": "document.released",
            "companyId": "cmp-test",
            "statements": [
                {
                    "companyId": "cmp-test",
                    "employeeId": "emp-1",
                    "period": "2026-03",
                    "documentType": "lohnsteuerbescheinigung",
                    "pdfBase64": MINIMAL_PDF,
                }
            ],
        }
    )
    assert len(rows) == 1
    assert rows[0]["docType"] == "lohnsteuerbescheinigung"
    assert rows[0]["documentType"] == "lohnsteuerbescheinigung"


def test_resolve_company_worker_by_name_unique():
    from backend.app.platform.accounting.messages_inbox import resolve_company_worker_by_name

    class _Row(dict):
        def __getitem__(self, key):
            return dict.get(self, key)

    class _FakeDb:
        def execute(self, *_a, **_k):
            class _R:
                def fetchall(self_inner):
                    return [
                        _Row(
                            id="w1",
                            first_name="Max",
                            last_name="Mustermann",
                            badge_id="B1",
                        ),
                        _Row(
                            id="w2",
                            first_name="Erika",
                            last_name="Muster",
                            badge_id="B2",
                        ),
                    ]

            return _R()

    hit = resolve_company_worker_by_name(_FakeDb(), "cmp-1", "Max Mustermann")
    assert hit is not None
    assert hit["id"] == "w1"
    assert hit["matchedBy"] == "name"
    assert resolve_company_worker_by_name(_FakeDb(), "cmp-1", "Ambiguous") is None


def test_enrich_statement_preview_mode_pdf_for_tax_doc(monkeypatch):
    from backend.app.platform.accounting import repository as repo
    import pathlib

    class _P(pathlib.Path):
        def is_file(self):
            return True

    monkeypatch.setattr(pathlib, "Path", _P)
    row = {
        "id": "s1",
        "batch_id": "b1",
        "company_id": "c1",
        "worker_id": "w1",
        "status": "pending",
        "file_path": "/tmp/x.pdf",
        "file_size": 100,
        "first_name": "Max",
        "last_name": "Mustermann",
        "match_confidence": "exact",
        "matched_by": "id",
        "meta_json": json.dumps(
            {
                "docType": "lohnsteuerbescheinigung",
                "title": "Lohnsteuerbescheinigung 2025",
                "pdfSource": "lohn_original",
                "pdfImmutable": True,
            }
        ),
    }
    out = repo.enrich_statement_row(None, row)
    assert out["previewMode"] == "pdf"
    assert out["docType"] == "lohnsteuerbescheinigung"
    assert out["title"] == "Lohnsteuerbescheinigung 2025"
    assert out["pdfImmutable"] is True
