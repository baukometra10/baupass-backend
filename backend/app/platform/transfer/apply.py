"""Orchestrate domain handlers with merge modes, backup, and abort-on-fail."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .archive import TransferPackage
from .handlers.base import ApplyContext, MergeMode
from .handlers.companies import apply_companies, apply_subcompanies
from .handlers.contracts import apply_contract_templates, apply_employment_contracts
from .handlers.documents import apply_worker_documents
from .handlers.ops import apply_access_logs, apply_deployment_days, apply_invoices, apply_leave_requests
from .handlers.workers import apply_workers
from .schema import PHASE_A_DOMAINS


ProgressCb = Callable[[str, int, str], None]

DOMAIN_STEPS: list[tuple[str, Any, int]] = [
    ("companies", apply_companies, 8),
    ("subcompanies", apply_subcompanies, 16),
    ("workers", apply_workers, 32),
    ("contract_templates", apply_contract_templates, 40),
    ("employment_contracts", apply_employment_contracts, 52),
    ("worker_documents", apply_worker_documents, 64),
    ("access_logs", apply_access_logs, 74),
    ("invoices", apply_invoices, 82),
    ("deployment_days", apply_deployment_days, 90),
    ("leave_requests", apply_leave_requests, 94),
]


def resolve_target_company_id(package: TransferPackage, override: str | None = None) -> str:
    if override and str(override).strip():
        return str(override).strip()
    mid = str(package.manifest.get("companyId") or package.manifest.get("company_id") or "").strip()
    if mid:
        return mid
    companies = package.domains.get("companies") or []
    if companies:
        return str(companies[0].get("id") or "").strip()
    workers = package.domains.get("workers") or []
    if workers:
        return str(workers[0].get("company_id") or workers[0].get("companyId") or "").strip()
    return ""


def parse_merge_mode(value: str | None) -> MergeMode:
    raw = str(value or "skip").strip().lower()
    if raw in {"replace", "overwrite", "force"}:
        return MergeMode.REPLACE
    if raw in {"fail", "strict", "abort"}:
        return MergeMode.FAIL
    return MergeMode.SKIP


def create_transfer_rollback_backup(db, company_id: str) -> str:
    """Company-scoped JSON snapshot covering Phase A tables."""
    try:
        from backend.server import BASE_DIR, row_to_dict
    except Exception:
        BASE_DIR = Path(".")

        def row_to_dict(row):  # type: ignore
            return dict(row) if hasattr(row, "keys") else {}

    backup_dir = Path(BASE_DIR) / "backend" / "backups" / "transfer"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = backup_dir / f"transfer-backup-{company_id}-{stamp}-{secrets.token_hex(3)}.json"

    workers = [
        row_to_dict(r)
        for r in db.execute("SELECT * FROM workers WHERE company_id = ?", (company_id,)).fetchall()
    ]
    worker_ids = [w["id"] for w in workers if w.get("id")]
    access_logs = []
    if worker_ids:
        placeholders = ",".join("?" for _ in worker_ids)
        access_logs = [
            row_to_dict(r)
            for r in db.execute(
                f"SELECT * FROM access_logs WHERE worker_id IN ({placeholders})",
                worker_ids,
            ).fetchall()
        ]

    def safe_select(sql: str, params: tuple = ()) -> list[dict]:
        try:
            return [row_to_dict(r) for r in db.execute(sql, params).fetchall()]
        except Exception:
            return []

    payload = {
        "meta": {
            "type": "transfer-rollback-backup",
            "schemaVersion": "2026-08-transfer-v1",
            "companyId": company_id,
            "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "companies": safe_select("SELECT * FROM companies WHERE id = ?", (company_id,)),
        "subcompanies": safe_select("SELECT * FROM subcompanies WHERE company_id = ?", (company_id,)),
        "workers": workers,
        "contract_templates": safe_select("SELECT * FROM contract_templates WHERE company_id = ?", (company_id,)),
        "employment_contracts": safe_select("SELECT * FROM employment_contracts WHERE company_id = ?", (company_id,)),
        "worker_documents": safe_select("SELECT * FROM worker_documents WHERE company_id = ?", (company_id,)),
        "access_logs": access_logs,
        "invoices": safe_select("SELECT * FROM invoices WHERE company_id = ?", (company_id,)),
        "deployment_days": safe_select("SELECT * FROM worker_deployment_days WHERE company_id = ?", (company_id,)),
        "leave_requests": safe_select("SELECT * FROM leave_requests WHERE company_id = ?", (company_id,)),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def apply_package(
    db,
    package: TransferPackage,
    *,
    company_id: str,
    actor_user_id: str = "",
    dry_run: bool = False,
    merge_mode: MergeMode | str = MergeMode.SKIP,
    progress: ProgressCb | None = None,
    create_backup: bool = True,
) -> dict[str, Any]:
    mode = merge_mode if isinstance(merge_mode, MergeMode) else parse_merge_mode(str(merge_mode))
    ctx = ApplyContext(
        db=db,
        company_id=company_id,
        actor_user_id=actor_user_id,
        dry_run=dry_run,
        merge_mode=mode,
        package_files=dict(package.files or {}),
        progress=progress,
    )

    backup_path = None
    if not dry_run and create_backup:
        if progress:
            progress("backup", 3, "Rollback-Backup wird erstellt…")
        backup_path = create_transfer_rollback_backup(db, company_id)

    accepted: dict[str, int] = {}
    unchanged: dict[str, int] = {}
    conflicts: dict[str, int] = {}
    conflict_ids: dict[str, list[str]] = {}
    skipped_invalid = 0
    domain_errors: dict[str, str] = {}
    aborted = False
    abort_reason = None

    # Use a savepoint so FAIL mode can roll back writes in this transaction.
    if not dry_run:
        try:
            db.execute("BEGIN")
        except Exception:
            pass

    for name, handler, pct in DOMAIN_STEPS:
        rows = package.domains.get(name) or []
        if not rows:
            accepted[name] = 0
            unchanged[name] = 0
            conflicts[name] = 0
            continue
        if progress:
            progress(name, pct, f"{name}: {len(rows)} Datensätze…")
        result = handler(ctx, rows)
        accepted[name] = result.accepted
        unchanged[name] = result.unchanged
        conflicts[name] = result.conflicts
        if result.conflict_ids:
            conflict_ids[name] = result.conflict_ids
        skipped_invalid += result.skipped_invalid
        if result.error:
            domain_errors[name] = result.error
            if mode == MergeMode.FAIL or str(result.error).startswith("conflict:"):
                aborted = True
                abort_reason = result.error
                break

    if aborted and not dry_run:
        try:
            db.execute("ROLLBACK")
        except Exception:
            pass
        return {
            "accepted": {k: 0 for k in PHASE_A_DOMAINS},
            "unchanged": unchanged,
            "conflicts": conflicts,
            "conflictIds": conflict_ids,
            "skippedInvalid": skipped_invalid,
            "writtenFiles": {},
            "dryRun": False,
            "companyId": company_id,
            "mergeMode": mode.value,
            "backupPath": backup_path,
            "aborted": True,
            "abortReason": abort_reason,
            "domainErrors": domain_errors,
        }

    if not dry_run:
        try:
            db.commit()
        except Exception:
            try:
                db.execute("COMMIT")
            except Exception:
                pass

    if progress:
        progress("done", 96, "Datenbank geschrieben")

    return {
        "accepted": accepted,
        "unchanged": unchanged,
        "conflicts": conflicts,
        "conflictIds": conflict_ids,
        "skippedInvalid": skipped_invalid,
        "writtenFiles": dict(ctx.written_files),
        "dryRun": dry_run,
        "companyId": company_id,
        "mergeMode": mode.value,
        "backupPath": backup_path,
        "aborted": False,
        "abortReason": None,
        "domainErrors": domain_errors,
    }
