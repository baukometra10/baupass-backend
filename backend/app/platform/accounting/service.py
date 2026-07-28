"""Business logic: hours export, statement ingest, human approval + worker release."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import uuid
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from . import repository as repo
from .auth import sign_payload
from .hours_service import aggregate_company_hours, normalize_period
from .schema import ensure_accounting_schema


def prepare_hour_export(db, *, company_id: str, period: str, mark_sent: bool = False) -> dict[str, Any]:
    payload = aggregate_company_hours(db, company_id=company_id, period=period)
    status = "sent" if mark_sent else "queued"
    meta = repo.save_hour_export(db, company_id=company_id, period=payload["period"], payload=payload, status=status)
    payload["exportId"] = meta["id"]
    payload["fingerprint"] = meta["fingerprint"]
    payload["exportStatus"] = meta["status"]
    return payload


def _post_webhook(url: str, body: dict[str, Any], *, signing_secret: str = "") -> dict[str, Any]:
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    ts = str(int(__import__("time").time()))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SUPPIX-WorkPass-Lohn-Bridge/1.0",
        "X-Suppix-Timestamp": ts,
        "X-Suppix-Event": str(body.get("event") or "hours.ready"),
        "X-Suppix-Product": "WorkPass Lohn",
    }
    if signing_secret:
        headers["X-Suppix-Signature"] = sign_payload(signing_secret, timestamp=ts, body=raw)
    req = urlrequest.Request(url, data=raw, headers=headers, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            return {"ok": True, "status": int(resp.status), "body": resp.read()[:500].decode("utf-8", errors="replace")}
    except urlerror.HTTPError as exc:
        return {"ok": False, "status": int(exc.code), "error": str(exc)[:200]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def notify_hours_ready(db, *, company_id: str, period: str) -> dict[str, Any]:
    integration = repo.get_integration(db, company_id)
    if not integration or not int(integration.get("enabled") or 0):
        return {"ok": False, "error": "integration_disabled"}
    # Need signing secret from full row
    ensure_accounting_schema(db)
    full = db.execute(
        "SELECT webhook_url, signing_secret FROM accounting_integrations WHERE company_id = ?",
        (company_id,),
    ).fetchone()
    webhook = str((full["webhook_url"] if full else "") or "").strip()
    if not webhook:
        return {"ok": False, "error": "no_webhook_url", "hint": "Accounting app can pull GET /api/v2/accounting/hours"}
    payload = prepare_hour_export(db, company_id=company_id, period=period, mark_sent=True)
    event = {
        "event": "hours.ready",
        "product": "WorkPass Lohn",
        "companyId": company_id,
        "period": payload["period"],
        "exportId": payload.get("exportId"),
        "fingerprint": payload.get("fingerprint"),
        "rowCount": payload.get("rowCount"),
        "totalHours": payload.get("totalHours"),
        "pullUrl": f"/api/v2/accounting/hours?period={payload['period']}",
    }
    result = _post_webhook(webhook, event, signing_secret=str(full["signing_secret"] or "") if full else "")
    if not result.get("ok"):
        db.execute(
            "UPDATE payroll_hour_exports SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
            (
                str(result.get("error") or result.get("status") or "webhook_failed")[:200],
                __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ"),
                payload.get("exportId"),
            ),
        )
        db.commit()
    return {"ok": bool(result.get("ok")), "webhook": result, "export": {"id": payload.get("exportId"), "period": payload["period"]}}


def _storage_dir(company_id: str, period: str) -> Path:
    try:
        from backend.server import DOCS_UPLOAD_DIR

        base = Path(DOCS_UPLOAD_DIR)
    except Exception:
        base = Path("backend") / "uploads" / "documents"
    target = base / "payroll" / company_id / period
    target.mkdir(parents=True, exist_ok=True)
    return target


def ingest_statements(
    db,
    *,
    company_id: str,
    period: str,
    statements: list[dict[str, Any]],
    external_ref: str = "",
    notes: str = "",
) -> dict[str, Any]:
    period = normalize_period(period)
    if not statements:
        return {"ok": False, "error": "statements_required"}
    batch_id = repo.create_statement_batch(
        db, company_id=company_id, period=period, external_ref=external_ref, notes=notes
    )
    created: list[str] = []
    errors: list[dict[str, Any]] = []
    for idx, item in enumerate(statements):
        worker_id = str(item.get("workerId") or item.get("worker_id") or "").strip()
        if not worker_id:
            errors.append({"index": idx, "error": "worker_id_required"})
            continue
        worker = db.execute(
            "SELECT id FROM workers WHERE id = ? AND company_id = ? AND deleted_at IS NULL",
            (worker_id, company_id),
        ).fetchone()
        if not worker:
            errors.append({"index": idx, "error": "worker_not_found", "workerId": worker_id})
            continue
        pdf_b64 = item.get("pdfBase64") or item.get("pdf_base64") or ""
        filename = str(item.get("filename") or f"lohnabrechnung_{period}_{worker_id}.pdf").strip()
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"
        file_path = ""
        file_size = 0
        if pdf_b64:
            try:
                raw = base64.b64decode(pdf_b64)
            except Exception:
                errors.append({"index": idx, "error": "invalid_pdf_base64", "workerId": worker_id})
                continue
            if len(raw) < 20 or not raw.startswith(b"%PDF"):
                errors.append({"index": idx, "error": "not_a_pdf", "workerId": worker_id})
                continue
            if len(raw) > 15 * 1024 * 1024:
                errors.append({"index": idx, "error": "pdf_too_large", "workerId": worker_id})
                continue
            dest_dir = _storage_dir(company_id, period)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"{worker_id}_{secrets.token_hex(4)}.pdf"
            dest.write_bytes(raw)
            file_path = str(dest)
            file_size = len(raw)
        stmt_id = repo.add_statement(
            db,
            batch_id=batch_id,
            company_id=company_id,
            worker_id=worker_id,
            period=period,
            hours=float(item.get("hours") or 0),
            hourly_rate=float(item.get("hourlyRate") or item.get("hourly_rate") or 0),
            gross_amount=float(item.get("grossAmount") or item.get("gross_amount") or 0),
            net_amount=(
                float(item["netAmount"])
                if item.get("netAmount") is not None
                else (float(item["net_amount"]) if item.get("net_amount") is not None else None)
            ),
            currency=str(item.get("currency") or "EUR"),
            filename=filename,
            file_path=file_path,
            file_size=file_size,
            external_ref=str(item.get("externalRef") or item.get("external_ref") or ""),
            meta={k: v for k, v in item.items() if k not in {"pdfBase64", "pdf_base64"}},
        )
        created.append(stmt_id)
    return {
        "ok": True,
        "batchId": batch_id,
        "period": period,
        "status": "pending_approval",
        "createdCount": len(created),
        "statementIds": created,
        "errors": errors,
    }


def _attach_worker_document(
    db,
    *,
    company_id: str,
    worker_id: str,
    filename: str,
    file_path: str,
    file_size: int,
    uploaded_by_user_id: str | None,
    period: str,
) -> str:
    doc_id = f"doc-{uuid.uuid4().hex[:12]}"
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
    notes = f"payroll_period={period}"
    try:
        db.execute(
            """
            INSERT INTO worker_documents
               (id, worker_id, company_id, doc_type, filename, file_path, file_size,
                source_email_from, source_inbox_id, uploaded_by_user_id, created_at, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                doc_id,
                worker_id,
                company_id,
                "lohnabrechnung",
                filename,
                file_path,
                file_size,
                "accounting_bridge",
                None,
                uploaded_by_user_id,
                now,
                notes,
            ),
        )
    except Exception:
        db.execute(
            """
            INSERT INTO worker_documents
               (id, worker_id, company_id, doc_type, filename, file_path, file_size,
                uploaded_by_user_id, created_at, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (doc_id, worker_id, company_id, "lohnabrechnung", filename, file_path, file_size, uploaded_by_user_id, now, notes),
        )
    return doc_id


def approve_batch(db, *, batch_id: str, actor_user_id: str, company_id: str | None = None) -> dict[str, Any]:
    batch = repo.get_batch(db, batch_id)
    if not batch:
        return {"ok": False, "error": "batch_not_found"}
    if company_id and batch["company_id"] != company_id:
        return {"ok": False, "error": "forbidden_company"}
    if batch["status"] not in {"pending_approval", "approved"}:
        return {"ok": False, "error": "invalid_status", "status": batch["status"]}

    statements = repo.list_batch_statements(db, batch_id)
    released = 0
    skipped = 0
    errors: list[dict[str, Any]] = []
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")

    for stmt in statements:
        if stmt.get("status") == "released" and stmt.get("worker_document_id"):
            skipped += 1
            continue
        path = str(stmt.get("file_path") or "")
        if not path or not Path(path).is_file():
            errors.append({"statementId": stmt["id"], "error": "missing_pdf"})
            continue
        try:
            doc_id = _attach_worker_document(
                db,
                company_id=stmt["company_id"],
                worker_id=stmt["worker_id"],
                filename=stmt.get("filename") or "lohnabrechnung.pdf",
                file_path=path,
                file_size=int(stmt.get("file_size") or 0),
                uploaded_by_user_id=actor_user_id,
                period=stmt.get("period") or batch["period"],
            )
            db.execute(
                """
                UPDATE payroll_statements
                SET status = 'released', worker_document_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (doc_id, now, stmt["id"]),
            )
            try:
                from backend.server import _notify_worker_payroll_document

                _notify_worker_payroll_document(
                    db,
                    stmt["worker_id"],
                    stmt.get("filename") or "lohnabrechnung.pdf",
                    doc_type="lohnabrechnung",
                )
            except Exception:
                pass
            released += 1
        except Exception as exc:
            errors.append({"statementId": stmt["id"], "error": str(exc)[:160]})

    new_status = "released" if released and not errors else ("approved" if released else batch["status"])
    if released:
        db.execute(
            """
            UPDATE payroll_statement_batches
            SET status = ?,
                approved_at = COALESCE(approved_at, ?),
                approved_by_user_id = COALESCE(approved_by_user_id, ?),
                released_at = CASE WHEN ? = 'released' THEN ? ELSE released_at END,
                updated_at = ?
            WHERE id = ?
            """,
            (new_status, now, actor_user_id, new_status, now, now, batch_id),
        )
    db.commit()
    refreshed = repo.get_batch(db, batch_id) or {}
    return {
        "ok": True,
        "batchId": batch_id,
        "released": released,
        "skipped": skipped,
        "errors": errors,
        "status": refreshed.get("status") or new_status,
    }


def reject_batch(db, *, batch_id: str, actor_user_id: str, company_id: str | None = None, reason: str = "") -> dict[str, Any]:
    batch = repo.get_batch(db, batch_id)
    if not batch:
        return {"ok": False, "error": "batch_not_found"}
    if company_id and batch["company_id"] != company_id:
        return {"ok": False, "error": "forbidden_company"}
    if batch["status"] != "pending_approval":
        return {"ok": False, "error": "invalid_status", "status": batch["status"]}
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
    notes = (batch.get("notes") or "") + (f"\nreject: {reason}" if reason else "")
    db.execute(
        """
        UPDATE payroll_statement_batches
        SET status = 'rejected', rejected_at = ?, rejected_by_user_id = ?, notes = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, actor_user_id, notes[:1000], now, batch_id),
    )
    db.execute(
        "UPDATE payroll_statements SET status = 'rejected', updated_at = ? WHERE batch_id = ?",
        (now, batch_id),
    )
    db.commit()
    return {"ok": True, "batchId": batch_id, "status": "rejected"}


def fingerprint_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]
