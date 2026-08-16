"""Worker employment contract visibility + PDF access helpers."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.app.domains.contracts.service import ContractsService


def _db(tmp_path: Path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE workers (
            id TEXT PRIMARY KEY,
            company_id TEXT,
            first_name TEXT,
            last_name TEXT
        );
        CREATE TABLE employment_contracts (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            worker_id TEXT,
            template_id TEXT,
            title TEXT NOT NULL DEFAULT '',
            language TEXT NOT NULL DEFAULT 'de',
            status TEXT NOT NULL DEFAULT 'draft',
            input_json TEXT NOT NULL DEFAULT '{}',
            ai_prompt TEXT NOT NULL DEFAULT '',
            draft_text TEXT NOT NULL DEFAULT '',
            final_text TEXT NOT NULL DEFAULT '',
            pdf_file_path TEXT NOT NULL DEFAULT '',
            parent_contract_id TEXT,
            created_by_user_id TEXT,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE employment_contract_sign_sessions (
            id TEXT PRIMARY KEY,
            contract_id TEXT NOT NULL,
            company_id TEXT NOT NULL,
            role TEXT NOT NULL,
            token TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            expires_at TEXT,
            signed_at TEXT,
            created_by_user_id TEXT,
            created_at TEXT,
            reminder_sent_at TEXT
        );
        """
    )
    pdf = tmp_path / "c1.pdf"
    pdf.write_bytes(b"%PDF-1.4 worker-contract")
    conn.execute(
        "INSERT INTO workers (id, company_id, first_name, last_name) VALUES ('w1','co1','Max','Mustermann')"
    )
    conn.execute(
        """
        INSERT INTO employment_contracts
            (id, company_id, worker_id, title, status, draft_text, final_text, pdf_file_path, updated_at)
        VALUES
            ('c-ready','co1','w1','AV Max','final','','Vollständiger Vertragstext',?, '2026-08-01T00:00:00Z'),
            ('c-empty','co1','w1','Leer','draft','','','', '2026-08-01T00:00:00Z')
        """,
        (str(pdf),),
    )
    conn.commit()
    return conn


def test_list_worker_app_contracts_marks_viewable(tmp_path):
    db = _db(tmp_path)
    rows = ContractsService(db).list_worker_app_contracts("w1", "co1", base_url="https://app.test")
    by_id = {r["id"]: r for r in rows}
    assert by_id["c-ready"]["canView"] is True
    assert by_id["c-ready"]["canDownload"] is True
    assert by_id["c-ready"]["hasPdf"] is True
    assert "/api/worker-app/employment-contracts/c-ready/download.pdf" in by_id["c-ready"]["downloadUrl"]
    assert by_id["c-empty"]["canView"] is False


def test_worker_contract_pdf_bytes_reads_stored(tmp_path):
    db = _db(tmp_path)
    pdf_bytes, source = ContractsService(db).worker_contract_pdf_bytes(
        "c-ready", "w1", "co1", prefer_stored=True
    )
    assert source == "stored"
    assert pdf_bytes.startswith(b"%PDF")


def test_worker_contract_pdf_rejects_other_worker(tmp_path):
    db = _db(tmp_path)
    try:
        ContractsService(db).worker_contract_pdf_bytes("c-ready", "w-other", "co1")
        assert False, "expected contract_not_found"
    except ValueError as exc:
        assert str(exc) == "contract_not_found"
