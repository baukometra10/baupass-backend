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


def test_worker_contract_pdf_rejects_ciphertext_without_cache(tmp_path):
    db = _db(tmp_path)
    bad = tmp_path / "bad.pdf"
    # Mimic ReportLab PDF that accidentally contains an E2E envelope fragment.
    bad.write_bytes(b'%PDF-1.4\nBT /F1 12 Tf ("e2e":true "ct":"AAAA" X25519-AES-GCM) Tj ET\n%%EOF\n')
    envelope = (
        '{"e2e":true,"v":1,"alg":"X25519-AES-GCM","epk":"x","iv":"y","ct":"z"}'
    )
    db.execute(
        "UPDATE employment_contracts SET pdf_file_path = ?, final_text = ? WHERE id = 'c-ready'",
        (str(bad), envelope),
    )
    db.commit()
    try:
        ContractsService(db).worker_contract_pdf_bytes(
            "c-ready", "w1", "co1", prefer_stored=True, storage_root=tmp_path
        )
        assert False, "expected regenerate error"
    except ValueError as exc:
        assert str(exc) == "contract_pdf_needs_employer_regenerate"


def test_worker_contract_pdf_uses_render_cache(tmp_path):
    db = _db(tmp_path)
    envelope = (
        '{"e2e":true,"v":1,"alg":"X25519-AES-GCM","epk":"x","iv":"y","ct":"z"}'
    )
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b'%PDF-1.4\nBT ("e2e":true "ct":"AAAA" X25519-AES-GCM) Tj ET\n%%EOF\n')
    db.execute(
        "UPDATE employment_contracts SET pdf_file_path = ?, final_text = ? WHERE id = 'c-ready'",
        (str(bad), envelope),
    )
    db.commit()
    svc = ContractsService(db)
    svc._save_pdf_render_cache(tmp_path, "co1", "c-ready", "Klartext Arbeitsvertrag Klausel 1.")
    # build_preview needs branding helpers — patch via monkeypatch in integration;
    # here only assert resolve body works.
    body = svc._resolve_pdf_body_text(
        dict(db.execute("SELECT * FROM employment_contracts WHERE id='c-ready'").fetchone()),
        company_id="co1",
        storage_root=tmp_path,
        payload={},
    )
    assert "Klartext" in body


def test_worker_contract_pdf_rejects_other_worker(tmp_path):
    db = _db(tmp_path)
    try:
        ContractsService(db).worker_contract_pdf_bytes("c-ready", "w-other", "co1")
        assert False, "expected contract_not_found"
    except ValueError as exc:
        assert str(exc) == "contract_not_found"
