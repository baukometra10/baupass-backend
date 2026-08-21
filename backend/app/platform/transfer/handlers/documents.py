"""Worker documents + binary files."""
from __future__ import annotations

from typing import Any

from ..archive import write_file_under
from .base import (
    ApplyContext,
    DomainResult,
    decide_row_action,
    docs_root,
    fetch_by_id,
    fingerprint_match,
    g,
    utc_now_iso,
)


DOC_FIELDS = [
    ("worker_id", "workerId"),
    ("company_id", "companyId"),
    ("doc_type", "docType"),
    ("filename",),
]


def _archive_rel(item: dict[str, Any], did: str, filename: str) -> str:
    rel = str(g(item, "archive_file", "archiveFile", default="") or "").replace("\\", "/").lstrip("/")
    if rel:
        return rel
    for cand in (
        f"worker_documents/{did}/{filename}",
        f"worker_documents/{did}",
        f"documents/{did}/{filename}",
    ):
        return cand  # first convention; caller checks package
    return f"worker_documents/{did}/{filename}"


def apply_worker_documents(ctx: ApplyContext, rows: list[dict[str, Any]]) -> DomainResult:
    result = DomainResult(domain="worker_documents")
    pending: list[tuple] = []
    for item in rows:
        did = str(g(item, "id", default="")).strip()
        wid = str(g(item, "worker_id", "workerId", default="")).strip()
        cid = str(g(item, "company_id", "companyId", default=ctx.company_id) or ctx.company_id).strip()
        filename = str(g(item, "filename", default="document.bin") or "document.bin")
        if not did or not wid:
            result.skipped_invalid += 1
            continue
        file_path = str(g(item, "file_path", "filePath", default="") or "")
        file_size = int(g(item, "file_size", "fileSize", default=0) or 0)
        candidates = [
            str(g(item, "archive_file", "archiveFile", default="") or "").replace("\\", "/").lstrip("/"),
            f"worker_documents/{did}/{filename}",
            f"worker_documents/{did}",
            f"documents/{did}/{filename}",
        ]
        for rel in candidates:
            if not rel:
                continue
            if rel in ctx.package_files:
                data = ctx.package_files[rel]
                file_size = len(data)
                if not ctx.dry_run:
                    stored = write_file_under(docs_root() / wid, f"{did}_{filename}", data)
                    file_path = str(stored)
                    ctx.written_files[rel] = file_path
                else:
                    file_path = f"pending:{rel}"
                break
        existing = fetch_by_id(ctx.db, "worker_documents", did)
        same = bool(existing) and fingerprint_match(existing, {**item, "company_id": cid, "worker_id": wid}, DOC_FIELDS)
        action = decide_row_action(exists=bool(existing), same=same, merge_mode=ctx.merge_mode)
        if action == "unchanged":
            result.unchanged += 1
            continue
        if action == "skip":
            result.conflicts += 1
            result.conflict_ids.append(did)
            continue
        if action == "fail":
            result.conflicts += 1
            result.conflict_ids.append(did)
            result.error = f"conflict:worker_documents:{did}"
            return result
        pending.append(
            (
                did,
                wid,
                cid,
                str(g(item, "doc_type", "docType", default="other") or "other"),
                filename,
                file_path,
                file_size,
                str(g(item, "source_email_from", "sourceEmailFrom", default="")),
                g(item, "source_inbox_id", "sourceInboxId", default=None),
                g(item, "uploaded_by_user_id", "uploadedByUserId", default=ctx.actor_user_id or None),
                str(g(item, "created_at", "createdAt", default=utc_now_iso())),
                str(g(item, "notes", default="")),
            )
        )
        result.accepted += 1
    if not ctx.dry_run and pending:
        ctx.db.executemany(
            """
            INSERT OR REPLACE INTO worker_documents (
                id, worker_id, company_id, doc_type, filename, file_path, file_size,
                source_email_from, source_inbox_id, uploaded_by_user_id, created_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            pending,
        )
    return result
