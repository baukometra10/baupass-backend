"""Build a transfer ZIP from a live company (Phase C minimal — matching import)."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from .archive import build_transfer_zip
from .handlers.base import row_dict


def _photo_to_bytes(photo_data: str) -> tuple[bytes, str] | None:
    raw = (photo_data or "").strip()
    if not raw:
        return None
    if raw.lower().startswith("data:") and "," in raw:
        header, b64 = raw.split(",", 1)
        ext = ".jpg"
        if "png" in header:
            ext = ".png"
        elif "webp" in header:
            ext = ".webp"
        try:
            return base64.b64decode(b64), ext
        except Exception:
            return None
    return None


def export_company_package(db, company_id: str) -> tuple[bytes, dict[str, Any]]:
    company_id = str(company_id or "").strip()
    if not company_id:
        raise ValueError("missing_company_id")

    def q(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        try:
            return [row_dict(r) for r in db.execute(sql, params).fetchall()]
        except Exception:
            return []

    companies = q("SELECT * FROM companies WHERE id = ?", (company_id,))
    if not companies:
        raise ValueError("company_not_found")

    workers = q("SELECT * FROM workers WHERE company_id = ? ORDER BY last_name, first_name", (company_id,))
    worker_ids = [w["id"] for w in workers if w.get("id")]
    access_logs: list[dict[str, Any]] = []
    if worker_ids:
        placeholders = ",".join("?" for _ in worker_ids)
        access_logs = q(
            f"SELECT * FROM access_logs WHERE worker_id IN ({placeholders}) ORDER BY timestamp DESC",
            tuple(worker_ids),
        )

    domains: dict[str, list[dict[str, Any]]] = {
        "companies": companies,
        "subcompanies": q("SELECT * FROM subcompanies WHERE company_id = ? ORDER BY name", (company_id,)),
        "workers": workers,
        "contract_templates": q(
            "SELECT * FROM contract_templates WHERE company_id = ? ORDER BY updated_at DESC",
            (company_id,),
        ),
        "employment_contracts": q(
            "SELECT * FROM employment_contracts WHERE company_id = ? ORDER BY updated_at DESC",
            (company_id,),
        ),
        "worker_documents": q(
            "SELECT * FROM worker_documents WHERE company_id = ? ORDER BY created_at DESC",
            (company_id,),
        ),
        "access_logs": access_logs,
        "invoices": q("SELECT * FROM invoices WHERE company_id = ? ORDER BY created_at DESC", (company_id,)),
        "deployment_days": q(
            "SELECT * FROM worker_deployment_days WHERE company_id = ? ORDER BY work_date",
            (company_id,),
        ),
        "leave_requests": q(
            "SELECT * FROM leave_requests WHERE company_id = ? ORDER BY created_at DESC",
            (company_id,),
        ),
    }

    files: dict[str, bytes] = {}

    # Worker photos from data URLs
    for w in workers:
        wid = str(w.get("id") or "")
        packed = _photo_to_bytes(str(w.get("photo_data") or ""))
        if wid and packed:
            data, ext = packed
            files[f"worker_photos/{wid}{ext}"] = data
            # Keep photo_data in JSON too for lossless UI restore; file is canonical binary.

    # Document binaries
    for doc in domains["worker_documents"]:
        did = str(doc.get("id") or "")
        filename = str(doc.get("filename") or "document.bin")
        path = str(doc.get("file_path") or "")
        if not did or not path:
            continue
        try:
            p = Path(path)
            if p.is_file():
                data = p.read_bytes()
                rel = f"worker_documents/{did}/{filename}"
                files[rel] = data
                doc["archive_file"] = rel
                doc["file_size"] = len(data)
        except Exception:
            continue

    # Contract PDFs
    for contract in domains["employment_contracts"]:
        eid = str(contract.get("id") or "")
        path = str(contract.get("pdf_file_path") or "")
        if not eid or not path:
            continue
        try:
            p = Path(path)
            if p.is_file():
                rel = f"contracts/{eid}.pdf"
                files[rel] = p.read_bytes()
        except Exception:
            continue

    blob = build_transfer_zip(company_id=company_id, domains=domains, files=files)
    meta = {
        "companyId": company_id,
        "counts": {k: len(v) for k, v in domains.items() if v},
        "fileCount": len(files),
        "bytes": len(blob),
    }
    return blob, meta
