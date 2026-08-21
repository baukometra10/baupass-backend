"""Orchestrate validate → apply → verify for company system transfer."""
from __future__ import annotations

import threading
from typing import Any

from .apply import apply_package, parse_merge_mode, resolve_target_company_id
from .archive import open_transfer_bytes, remap_package_company_ids
from .job_store import create_job, get_job, update_job
from .schema import PHASE_A_DOMAINS, SCHEMA_VERSION
from .verifier import verify_package


def validate_package_bytes(blob: bytes, *, filename: str = "") -> dict[str, Any]:
    package = open_transfer_bytes(blob, filename=filename)
    company_id = resolve_target_company_id(package)
    counts = {name: len(package.domains.get(name) or []) for name in PHASE_A_DOMAINS}
    present = [name for name, n in counts.items() if n]
    warnings: list[str] = []
    if not present:
        warnings.append("empty_package")
    if not company_id and "companies" not in present:
        warnings.append("missing_company_id")
    if package.files and "worker_documents" not in present and "employment_contracts" not in present:
        warnings.append("orphan_files")
    return {
        "ok": len([w for w in warnings if w != "orphan_files"]) == 0,
        "schemaVersion": package.schema_version or SCHEMA_VERSION,
        "sourceFormat": package.source_format,
        "companyId": company_id,
        "domains": present,
        "counts": {k: v for k, v in counts.items() if v},
        "fileCount": len(package.files),
        "warnings": warnings,
        "manifest": package.manifest,
        "mergeModes": ["skip", "replace", "fail"],
    }


def run_import(
    db,
    blob: bytes,
    *,
    filename: str = "",
    dry_run: bool = False,
    company_id_override: str | None = None,
    actor_user_id: str = "",
    merge_mode: str = "skip",
    remap_to_company_id: str | None = None,
    progress=None,
) -> dict[str, Any]:
    package = open_transfer_bytes(blob, filename=filename)
    remap_info = None
    if remap_to_company_id:
        remap_info = remap_package_company_ids(package, remap_to_company_id)
        company_id = str(remap_to_company_id).strip()
    else:
        company_id = resolve_target_company_id(package, company_id_override)
    if not company_id:
        raise ValueError("missing_company_id")
    mode = parse_merge_mode(merge_mode)

    apply_result = apply_package(
        db,
        package,
        company_id=company_id,
        actor_user_id=actor_user_id,
        dry_run=dry_run,
        merge_mode=mode,
        progress=progress,
    )
    summary = {
        "accepted": apply_result["accepted"],
        "unchanged": apply_result.get("unchanged") or {},
        "conflicts": apply_result.get("conflicts") or {},
        "conflictIds": apply_result.get("conflictIds") or {},
        "skippedInvalid": apply_result["skippedInvalid"],
        "fileCount": len(package.files),
        "writtenFiles": len(apply_result.get("writtenFiles") or {}),
        "domains": [k for k, v in (apply_result["accepted"] or {}).items() if v]
        + [k for k, v in (apply_result.get("unchanged") or {}).items() if v],
        "mergeMode": apply_result.get("mergeMode"),
        "backupPath": apply_result.get("backupPath"),
        "aborted": apply_result.get("aborted"),
        "abortReason": apply_result.get("abortReason"),
        "remap": remap_info,
    }
    if dry_run:
        return {
            "ok": True,
            "dryRun": True,
            "companyId": company_id,
            "schemaVersion": package.schema_version,
            "summary": summary,
            "verification": None,
            "completionPercent": None,
        }

    if apply_result.get("aborted"):
        return {
            "ok": False,
            "dryRun": False,
            "companyId": company_id,
            "schemaVersion": package.schema_version,
            "summary": summary,
            "verification": {
                "completionPercent": 0,
                "status": "failed",
                "message": f"Import abgebrochen: {apply_result.get('abortReason')}",
            },
            "completionPercent": 0,
        }

    verification = verify_package(
        db,
        package,
        company_id=company_id,
        written_files=apply_result.get("writtenFiles") or {},
        apply_summary=apply_result,
    )
    if progress:
        progress("verify", verification.get("completionPercent") or 100, verification.get("message") or "")
    return {
        "ok": verification.get("status") in {"complete", "partial"},
        "dryRun": False,
        "companyId": company_id,
        "schemaVersion": package.schema_version,
        "summary": summary,
        "verification": verification,
        "completionPercent": verification.get("completionPercent"),
    }


def start_import_job(
    get_db,
    blob: bytes,
    *,
    filename: str = "",
    dry_run: bool = False,
    company_id_override: str | None = None,
    actor_user_id: str = "",
    actor_name: str = "",
    merge_mode: str = "skip",
    remap_to_company_id: str | None = None,
    company_scope: str | None = None,
    flask_app=None,
) -> str:
    job_id = create_job(
        actor=actor_name or actor_user_id or "system",
        mode="dry-run" if dry_run else f"apply:{merge_mode}",
        filename=filename,
        company_id=company_scope or remap_to_company_id or company_id_override or "",
    )

    def _worker() -> None:
        try:
            update_job(job_id, status="running", phase="open", percent=2, message="Paket wird gelesen…")

            def progress(domain: str, percent: int, message: str = "") -> None:
                update_job(
                    job_id,
                    status="running",
                    phase=domain,
                    domain=domain,
                    percent=max(0, min(99, int(percent))),
                    message=message or domain,
                )

            def _run_with_db() -> dict[str, Any]:
                db = get_db()
                return run_import(
                    db,
                    blob,
                    filename=filename,
                    dry_run=dry_run,
                    company_id_override=company_id_override,
                    actor_user_id=actor_user_id,
                    merge_mode=merge_mode,
                    remap_to_company_id=remap_to_company_id,
                    progress=progress,
                )

            if flask_app is not None:
                with flask_app.app_context():
                    result = _run_with_db()
            else:
                result = _run_with_db()
            pct = 100 if dry_run else int(result.get("completionPercent") or 0)
            update_job(
                job_id,
                status="done" if result.get("ok", True) else "error",
                phase="done",
                percent=pct if not dry_run else 100,
                message=(result.get("verification") or {}).get("message") or "Import abgeschlossen",
                result=result,
                error=None if result.get("ok", True) else (result.get("summary") or {}).get("abortReason"),
            )
        except Exception as exc:
            update_job(
                job_id,
                status="error",
                phase="error",
                percent=0,
                message=str(exc),
                error=str(exc),
            )

    threading.Thread(target=_worker, name=f"transfer-{job_id}", daemon=True).start()
    return job_id


def job_status(job_id: str) -> dict[str, Any] | None:
    return get_job(job_id)
