"""Match inbox e-mails to workers and optionally auto-assign attachments."""
from __future__ import annotations

import os
import re
import secrets
from typing import Any

from backend.app.platform.payroll_inbox import suggest_doc_type_from_email
from backend.app.platform.worker_documents import normalize_doc_type


def _inbox_auto_assign_enabled() -> bool:
    raw = (os.getenv("BAUPASS_INBOX_AUTO_ASSIGN") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def suggest_worker_from_inbox_text(
    db,
    company_id: str,
    *,
    subject: str = "",
    body_text: str = "",
    from_addr: str = "",
) -> dict[str, Any]:
    """Heuristic worker match from e-mail metadata."""
    company_id = str(company_id or "").strip()
    if not company_id:
        return {"workerId": "", "confidence": "", "reason": ""}

    combined = "\n".join(part for part in (subject, body_text, from_addr) if part).strip()
    if not combined:
        return {"workerId": "", "confidence": "", "reason": ""}

    rows = db.execute(
        """
        SELECT id, first_name, last_name, insurance_number, badge_id, badge_id_lookup
        FROM workers
        WHERE company_id = ?
          AND deleted_at IS NULL
          AND worker_type = 'worker'
        """,
        (company_id,),
    ).fetchall()

    compact = re.sub(r"\s+", "", combined)

    for row in rows:
        insurance = re.sub(r"\s+", "", str(row["insurance_number"] or ""))
        if len(insurance) >= 8 and insurance in compact:
            return {
                "workerId": str(row["id"]),
                "confidence": "high",
                "reason": "insurance_number",
            }

    badge_match = re.search(r"\b(BP-[A-Z0-9-]{3,})\b", combined, re.IGNORECASE)
    if badge_match:
        badge_token = re.sub(r"[^A-Z0-9-]", "", badge_match.group(1).upper())
        for row in rows:
            stored = str(row["badge_id_lookup"] or row["badge_id"] or "").upper()
            if stored and stored == badge_token:
                return {
                    "workerId": str(row["id"]),
                    "confidence": "high",
                    "reason": "badge_id",
                }

    subject_lower = subject.lower()
    for row in rows:
        first = str(row["first_name"] or "").strip()
        last = str(row["last_name"] or "").strip()
        if len(first) < 2 or len(last) < 2:
            continue
        patterns = (
            f"{first} {last}",
            f"{last}, {first}",
            f"{last} {first}",
            f"{first}-{last}",
        )
        for pattern in patterns:
            if pattern.lower() in subject_lower or pattern.lower() in combined.lower():
                return {
                    "workerId": str(row["id"]),
                    "confidence": "high",
                    "reason": "full_name",
                }

    return {"workerId": "", "confidence": "", "reason": ""}


def _assign_attachment_core(
    db,
    *,
    inbox_row,
    att_row,
    worker_row,
    doc_type: str,
    uploaded_by_user_id: str,
) -> str | None:
    """Persist attachment to worker file store. Returns doc_id or None on failure."""
    from backend.server import (
        DOCS_UPLOAD_DIR,
        MAX_IMAP_ATTACHMENT_BYTES,
        _sanitize_attachment_filename,
        _stored_file_path,
        now_iso,
        unlock_worker_if_documents_valid,
        utc_now,
    )

    doc_type = normalize_doc_type(doc_type)
    if not doc_type:
        return None

    base_upload_root = DOCS_UPLOAD_DIR.resolve()
    worker_id = str(worker_row["id"])
    worker_doc_dir = (DOCS_UPLOAD_DIR / worker_id).resolve()
    if worker_doc_dir != base_upload_root and base_upload_root not in worker_doc_dir.parents:
        return None
    worker_doc_dir.mkdir(parents=True, exist_ok=True)

    ts = utc_now().strftime("%Y%m%d_%H%M%S")
    safe_name = _sanitize_attachment_filename(att_row["filename"] or "anhang.bin")
    file_path = (worker_doc_dir / f"{doc_type}_{ts}_{safe_name}").resolve()
    if worker_doc_dir not in file_path.parents:
        return None

    file_data = att_row["file_data"]
    if not file_data:
        return None
    if isinstance(file_data, memoryview):
        file_data = file_data.tobytes()
    elif isinstance(file_data, bytearray):
        file_data = bytes(file_data)
    elif isinstance(file_data, str):
        file_data = file_data.encode("utf-8", errors="replace")
    else:
        file_data = bytes(file_data)
    if len(file_data) > MAX_IMAP_ATTACHMENT_BYTES:
        return None

    file_path.write_bytes(file_data)
    stored_path = _stored_file_path(file_path)
    doc_id = f"doc-{secrets.token_hex(8)}"
    db.execute(
        """INSERT INTO worker_documents
           (id, worker_id, company_id, doc_type, filename, file_path, file_size,
            source_email_from, source_inbox_id, uploaded_by_user_id, created_at, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            doc_id,
            worker_id,
            worker_row["company_id"],
            doc_type,
            safe_name,
            stored_path,
            len(file_data),
            inbox_row["from_addr"],
            inbox_row["id"],
            uploaded_by_user_id,
            now_iso(),
            "Auto-Zuweisung aus Posteingang",
        ),
    )
    db.execute(
        "UPDATE email_attachments SET assigned_worker_id = ?, assigned_doc_type = ?, saved_path = ? WHERE id = ?",
        (worker_id, doc_type, stored_path, att_row["id"]),
    )
    unlock_worker_if_documents_valid(db, worker_row, actor={"id": uploaded_by_user_id, "role": "system"})
    return doc_id


def try_auto_assign_inbox_message(
    db,
    inbox_id: str,
    *,
    company_id: str,
    subject: str = "",
    body_text: str = "",
    from_addr: str = "",
    uploaded_by_user_id: str = "system-inbox",
) -> dict[str, Any]:
    """Auto-assign unassigned attachments when worker + doc type match confidently."""
    if not _inbox_auto_assign_enabled():
        return {"assigned": 0, "skipped": True}

    company_id = str(company_id or "").strip()
    if not company_id:
        return {"assigned": 0, "reason": "no_company"}

    worker_hit = suggest_worker_from_inbox_text(
        db,
        company_id,
        subject=subject,
        body_text=body_text,
        from_addr=from_addr,
    )
    worker_id = str(worker_hit.get("workerId") or "").strip()
    if not worker_id or worker_hit.get("confidence") != "high":
        return {"assigned": 0, "reason": "no_worker_match", "workerSuggestion": worker_hit}

    worker_row = db.execute(
        "SELECT * FROM workers WHERE id = ? AND company_id = ? AND deleted_at IS NULL",
        (worker_id, company_id),
    ).fetchone()
    if not worker_row:
        return {"assigned": 0, "reason": "worker_not_found"}

    inbox_row = db.execute("SELECT * FROM email_inbox WHERE id = ?", (inbox_id,)).fetchone()
    if not inbox_row:
        return {"assigned": 0, "reason": "inbox_not_found"}

    attachments = db.execute(
        "SELECT * FROM email_attachments WHERE inbox_id = ? AND assigned_worker_id IS NULL",
        (inbox_id,),
    ).fetchall()

    assigned = 0
    for att in attachments:
        suggestion = suggest_doc_type_from_email(
            filename=str(att["filename"] or ""),
            subject=subject,
            from_addr=from_addr,
            body_text=body_text,
        )
        doc_type = str(suggestion.get("docType") or "").strip()
        confidence = str(suggestion.get("confidence") or "").strip()
        if not doc_type:
            continue
        if confidence not in {"high", "medium"}:
            continue
        doc_id = _assign_attachment_core(
            db,
            inbox_row=inbox_row,
            att_row=att,
            worker_row=worker_row,
            doc_type=doc_type,
            uploaded_by_user_id=uploaded_by_user_id,
        )
        if doc_id:
            assigned += 1

    if assigned > 0:
        unassigned = db.execute(
            "SELECT id FROM email_attachments WHERE inbox_id = ? AND assigned_worker_id IS NULL",
            (inbox_id,),
        ).fetchone()
        if not unassigned:
            db.execute("UPDATE email_inbox SET processed = 1 WHERE id = ?", (inbox_id,))

    return {
        "assigned": assigned,
        "workerId": worker_id,
        "workerMatchReason": worker_hit.get("reason") or "",
    }
