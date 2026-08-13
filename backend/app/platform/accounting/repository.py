"""Persistence helpers for accounting bridge."""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from .auth import generate_api_key, generate_signing_secret, hash_api_key
from .schema import ensure_accounting_schema


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def get_integration(db, company_id: str) -> dict[str, Any] | None:
    ensure_accounting_schema(db)
    try:
        row = db.execute(
            """
            SELECT id, company_id, enabled, webhook_url, api_key_prefix, run_day,
                   last_export_period, created_at, updated_at,
                   COALESCE(lohn_login_username, '') AS lohn_login_username,
                   COALESCE(lohn_login_password_enc, '') AS lohn_login_password_enc
            FROM accounting_integrations WHERE company_id = ? LIMIT 1
            """,
            (company_id,),
        ).fetchone()
    except Exception:
        row = db.execute(
            """
            SELECT id, company_id, enabled, webhook_url, api_key_prefix, run_day,
                   last_export_period, created_at, updated_at
            FROM accounting_integrations WHERE company_id = ? LIMIT 1
            """,
            (company_id,),
        ).fetchone()
    return dict(row) if row else None


def store_lohn_login(
    db,
    company_id: str,
    *,
    username: str,
    password: str,
) -> dict[str, Any]:
    """Persist company-admin credentials for WorkPass Lohn (password encrypted when possible)."""
    ensure_accounting_schema(db)
    company_id = (company_id or "").strip()
    username = (username or "").strip()
    password = str(password or "")
    if not company_id or not username or not password:
        return {"ok": False, "error": "credentials_required"}
    from backend.app.platform.security.field_encryption import maybe_encrypt_field

    enc = maybe_encrypt_field(password, company_id=company_id)
    now = _now()
    existing = db.execute(
        "SELECT id FROM accounting_integrations WHERE company_id = ?",
        (company_id,),
    ).fetchone()
    if existing:
        db.execute(
            """
            UPDATE accounting_integrations
            SET lohn_login_username = ?, lohn_login_password_enc = ?, updated_at = ?
            WHERE company_id = ?
            """,
            (username, enc, now, company_id),
        )
    else:
        # Integration row may not exist yet — caller should upsert_integration first.
        return {"ok": False, "error": "integration_missing"}
    db.commit()
    return {"ok": True, "username": username, "passwordStored": True}


def get_lohn_login(db, company_id: str) -> dict[str, Any] | None:
    """Return plaintext login for bridge use (Lohn pull / outbound upsert)."""
    row = get_integration(db, company_id)
    if not row:
        return None
    username = str(row.get("lohn_login_username") or "").strip()
    enc = str(row.get("lohn_login_password_enc") or "")
    if not username or not enc:
        return None
    from backend.app.platform.security.field_encryption import maybe_decrypt_field

    password = maybe_decrypt_field(enc, company_id=company_id)
    if not password:
        return None
    return {"username": username, "password": password}


def upsert_integration(
    db,
    *,
    company_id: str,
    webhook_url: str = "",
    enabled: bool = True,
    run_day: int = 1,
    rotate_key: bool = False,
) -> dict[str, Any]:
    ensure_accounting_schema(db)
    now = _now()
    existing = db.execute(
        "SELECT id, api_key_hash, api_key_prefix, signing_secret FROM accounting_integrations WHERE company_id = ?",
        (company_id,),
    ).fetchone()
    raw_key = None
    signing_secret = None
    if existing and not rotate_key:
        integration_id = existing["id"]
        api_key_hash = existing["api_key_hash"]
        api_key_prefix = existing["api_key_prefix"]
        signing_secret_stored = existing["signing_secret"]
        db.execute(
            """
            UPDATE accounting_integrations
            SET enabled = ?, webhook_url = ?, run_day = ?, updated_at = ?
            WHERE id = ?
            """,
            (1 if enabled else 0, (webhook_url or "").strip(), max(1, min(28, int(run_day or 1))), now, integration_id),
        )
    else:
        integration_id = existing["id"] if existing else f"accint-{uuid.uuid4().hex[:12]}"
        raw_key = generate_api_key()
        signing_secret = generate_signing_secret()
        api_key_hash = hash_api_key(raw_key)
        api_key_prefix = raw_key[:16]
        if existing:
            db.execute(
                """
                UPDATE accounting_integrations
                SET enabled = ?, webhook_url = ?, api_key_hash = ?, api_key_prefix = ?,
                    signing_secret = ?, run_day = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    1 if enabled else 0,
                    (webhook_url or "").strip(),
                    api_key_hash,
                    api_key_prefix,
                    signing_secret,
                    max(1, min(28, int(run_day or 1))),
                    now,
                    integration_id,
                ),
            )
        else:
            db.execute(
                """
                INSERT INTO accounting_integrations
                (id, company_id, enabled, webhook_url, api_key_hash, api_key_prefix, signing_secret, run_day, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    integration_id,
                    company_id,
                    1 if enabled else 0,
                    (webhook_url or "").strip(),
                    api_key_hash,
                    api_key_prefix,
                    signing_secret,
                    max(1, min(28, int(run_day or 1))),
                    now,
                    now,
                ),
            )
        signing_secret_stored = signing_secret
    db.commit()
    out = get_integration(db, company_id) or {}
    if raw_key:
        out["apiKey"] = raw_key
        out["signingSecret"] = signing_secret_stored
        out["warning"] = "Store apiKey and signingSecret now; they will not be shown again."
    return out


def save_hour_export(db, *, company_id: str, period: str, payload: dict[str, Any], status: str = "queued") -> dict[str, Any]:
    ensure_accounting_schema(db)
    now = _now()
    fingerprint = secrets.token_hex(8)
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    row_count = int(payload.get("rowCount") or len(payload.get("rows") or []))
    existing = db.execute(
        "SELECT id FROM payroll_hour_exports WHERE company_id = ? AND period = ?",
        (company_id, period),
    ).fetchone()
    export_id = existing["id"] if existing else f"phe-{uuid.uuid4().hex[:12]}"
    if existing:
        db.execute(
            """
            UPDATE payroll_hour_exports
            SET status = ?, payload_json = ?, fingerprint = ?, row_count = ?, error = '',
                updated_at = ?, sent_at = CASE WHEN ? = 'sent' THEN ? ELSE sent_at END
            WHERE id = ?
            """,
            (status, payload_json, fingerprint, row_count, now, status, now, export_id),
        )
    else:
        db.execute(
            """
            INSERT INTO payroll_hour_exports
            (id, company_id, period, status, payload_json, fingerprint, row_count, created_at, updated_at, sent_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (export_id, company_id, period, status, payload_json, fingerprint, row_count, now, now, now if status == "sent" else None),
        )
    db.execute(
        "UPDATE accounting_integrations SET last_export_period = ?, updated_at = ? WHERE company_id = ?",
        (period, now, company_id),
    )
    db.commit()
    return {"id": export_id, "fingerprint": fingerprint, "status": status, "rowCount": row_count}


def get_hour_export(db, *, company_id: str, period: str) -> dict[str, Any] | None:
    ensure_accounting_schema(db)
    row = db.execute(
        """
        SELECT id, company_id, period, status, payload_json, fingerprint, row_count, error, sent_at, acked_at, created_at, updated_at
        FROM payroll_hour_exports WHERE company_id = ? AND period = ?
        """,
        (company_id, period),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        data["payload"] = json.loads(data.pop("payload_json") or "{}")
    except Exception:
        data["payload"] = {}
    return data


def ack_hour_export(db, *, company_id: str, period: str, fingerprint: str = "") -> dict[str, Any]:
    ensure_accounting_schema(db)
    row = get_hour_export(db, company_id=company_id, period=period)
    if not row:
        return {"ok": False, "error": "export_not_found"}
    if fingerprint and fingerprint != row.get("fingerprint"):
        return {"ok": False, "error": "fingerprint_mismatch"}
    now = _now()
    db.execute(
        "UPDATE payroll_hour_exports SET status = 'acked', acked_at = ?, updated_at = ? WHERE id = ?",
        (now, now, row["id"]),
    )
    db.commit()
    return {"ok": True, "id": row["id"], "period": period, "status": "acked"}


def create_statement_batch(
    db,
    *,
    company_id: str,
    period: str,
    external_ref: str = "",
    notes: str = "",
) -> str:
    ensure_accounting_schema(db)
    batch_id = f"psb-{uuid.uuid4().hex[:12]}"
    now = _now()
    db.execute(
        """
        INSERT INTO payroll_statement_batches
        (id, company_id, period, status, source, external_ref, statement_count, notes, created_at, updated_at)
        VALUES (?, ?, ?, 'pending_approval', 'workpass_lohn', ?, 0, ?, ?, ?)
        """,
        (batch_id, company_id, period, (external_ref or "")[:120], (notes or "")[:500], now, now),
    )
    db.commit()
    return batch_id


def add_statement(
    db,
    *,
    batch_id: str,
    company_id: str,
    worker_id: str,
    period: str,
    hours: float,
    hourly_rate: float,
    gross_amount: float,
    net_amount: float | None,
    currency: str,
    filename: str,
    file_path: str,
    file_size: int,
    external_ref: str = "",
    meta: dict[str, Any] | None = None,
    status: str = "pending",
    matched_by: str = "",
    match_confidence: str = "",
) -> str:
    ensure_accounting_schema(db)
    stmt_id = f"pst-{uuid.uuid4().hex[:12]}"
    now = _now()
    status_norm = str(status or "pending").strip() or "pending"
    db.execute(
        """
        INSERT INTO payroll_statements
        (id, batch_id, company_id, worker_id, period, hours, hourly_rate, gross_amount, net_amount,
         currency, filename, file_path, file_size, status, external_ref, meta_json, created_at, updated_at,
         matched_by, match_confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stmt_id,
            batch_id,
            company_id,
            worker_id or "",
            period,
            float(hours or 0),
            float(hourly_rate or 0),
            float(gross_amount or 0),
            net_amount,
            (currency or "EUR")[:8],
            (filename or "")[:255],
            file_path or "",
            int(file_size or 0),
            status_norm[:32],
            (external_ref or "")[:120],
            json.dumps(meta or {}, ensure_ascii=False),
            now,
            now,
            (matched_by or "")[:40],
            (match_confidence or "")[:20],
        ),
    )
    db.execute(
        """
        UPDATE payroll_statement_batches
        SET statement_count = (SELECT COUNT(*) FROM payroll_statements WHERE batch_id = ?),
            updated_at = ?
        WHERE id = ?
        """,
        (batch_id, now, batch_id),
    )
    db.commit()
    return stmt_id


def get_statement(db, statement_id: str) -> dict[str, Any] | None:
    ensure_accounting_schema(db)
    row = db.execute(
        """
        SELECT s.*, w.first_name, w.last_name, w.badge_id, w.site, w.contact_email,
               c.name AS company_name
        FROM payroll_statements s
        LEFT JOIN workers w ON w.id = s.worker_id
        LEFT JOIN companies c ON c.id = s.company_id
        WHERE s.id = ?
        LIMIT 1
        """,
        (statement_id,),
    ).fetchone()
    return dict(row) if row else None


def enrich_statement_row(db, row: dict[str, Any]) -> dict[str, Any]:
    """UI-facing statement with match status and worker identity."""
    from pathlib import Path

    out = dict(row or {})
    worker_id = str(out.get("worker_id") or "").strip()
    status = str(out.get("status") or "").strip()
    path = str(out.get("file_path") or "").strip()
    has_pdf = bool(path and Path(path).is_file())
    first = str(out.get("first_name") or "").strip()
    last = str(out.get("last_name") or "").strip()
    display = f"{first} {last}".strip()
    confidence = str(out.get("match_confidence") or "").strip()
    matched_by = str(out.get("matched_by") or "").strip()

    if status == "unmatched" or not worker_id:
        match_status = "unmatched"
    elif confidence == "weak":
        match_status = "ambiguous"
    else:
        match_status = "matched"

    if not confidence:
        if match_status == "matched" and matched_by in {"", "id", "exact"}:
            confidence = "exact"
        elif match_status == "ambiguous":
            confidence = "weak"
        elif match_status == "matched":
            confidence = "strong"

    reviewed = bool(str(out.get("reviewed_at") or "").strip())
    out.update(
        {
            "statementId": out.get("id"),
            "batchId": out.get("batch_id"),
            "companyId": out.get("company_id"),
            "companyName": out.get("company_name") or "",
            "workerId": worker_id,
            "employeeId": worker_id,
            "period": out.get("period"),
            "firstName": first,
            "lastName": last,
            "displayName": display or worker_id or "—",
            "badgeId": str(out.get("badge_id") or "").strip(),
            "site": str(out.get("site") or "").strip(),
            "email": str(out.get("contact_email") or "").strip(),
            "grossAmount": out.get("gross_amount"),
            "netAmount": out.get("net_amount"),
            "hours": out.get("hours"),
            "hourlyRate": out.get("hourly_rate"),
            "currency": out.get("currency") or "EUR",
            "filename": out.get("filename") or "",
            "hasPdf": has_pdf,
            "fileSize": int(out.get("file_size") or 0),
            "status": status,
            "matchedBy": matched_by,
            "matchConfidence": confidence,
            "matchStatus": match_status,
            "reviewedAt": out.get("reviewed_at"),
            "reviewedByUserId": out.get("reviewed_by_user_id"),
            "reviewed": reviewed,
            "workerDocumentId": out.get("worker_document_id"),
            "canRelease": bool(has_pdf and reviewed and worker_id and status == "pending"),
        }
    )
    return out


def list_batch_statements(db, batch_id: str) -> list[dict[str, Any]]:
    ensure_accounting_schema(db)
    rows = db.execute(
        """
        SELECT s.*, w.first_name, w.last_name, w.badge_id, w.site, w.contact_email,
               c.name AS company_name
        FROM payroll_statements s
        LEFT JOIN workers w ON w.id = s.worker_id
        LEFT JOIN companies c ON c.id = s.company_id
        WHERE s.batch_id = ?
        ORDER BY
          CASE WHEN s.status = 'unmatched' THEN 0 WHEN s.reviewed_at IS NULL OR s.reviewed_at = '' THEN 1 ELSE 2 END,
          w.last_name, w.first_name, s.created_at
        """,
        (batch_id,),
    ).fetchall()
    return [enrich_statement_row(db, dict(r)) for r in rows]


def list_pending_batches(db, *, company_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    ensure_accounting_schema(db)
    limit = max(1, min(200, int(limit or 50)))
    if company_id:
        rows = db.execute(
            """
            SELECT * FROM payroll_statement_batches
            WHERE company_id = ? AND status = 'pending_approval'
            ORDER BY created_at DESC LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT * FROM payroll_statement_batches
            WHERE status = 'pending_approval'
            ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_company_statement_batches(
    db,
    *,
    company_id: str,
    period: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """All recent Abrechnung batches for a company (any status) — for Lohn pull."""
    ensure_accounting_schema(db)
    company_id = str(company_id or "").strip()
    if not company_id:
        return []
    limit = max(1, min(200, int(limit or 50)))
    period = str(period or "").strip()[:7]
    if period:
        rows = db.execute(
            """
            SELECT * FROM payroll_statement_batches
            WHERE company_id = ? AND period = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (company_id, period, limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT * FROM payroll_statement_batches
            WHERE company_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_batch(db, batch_id: str) -> dict[str, Any] | None:
    ensure_accounting_schema(db)
    row = db.execute("SELECT * FROM payroll_statement_batches WHERE id = ?", (batch_id,)).fetchone()
    return dict(row) if row else None


def list_pending_batches_enriched(db, *, company_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    batches = list_pending_batches(db, company_id=company_id, limit=limit)
    out: list[dict[str, Any]] = []
    for batch in batches:
        statements = list_batch_statements(db, batch["id"])
        company_name = ""
        try:
            crow = db.execute(
                "SELECT name FROM companies WHERE id = ?", (batch["company_id"],)
            ).fetchone()
            company_name = str((crow["name"] if crow else "") or "")
        except Exception:
            company_name = ""
        reviewed_n = sum(1 for s in statements if s.get("reviewed"))
        releasable_n = sum(1 for s in statements if s.get("canRelease"))
        unmatched_n = sum(
            1 for s in statements if s.get("matchStatus") == "unmatched" or s.get("status") == "unmatched"
        )
        out.append(
            {
                **batch,
                "companyId": batch.get("company_id"),
                "companyName": company_name,
                "statements": statements,
                "reviewedCount": reviewed_n,
                "releasableCount": releasable_n,
                "unmatchedCount": unmatched_n,
                "pendingReviewCount": max(0, len(statements) - reviewed_n),
            }
        )
    return out


def list_enabled_integrations(db) -> list[dict[str, Any]]:
    ensure_accounting_schema(db)
    from .company_opt_in import ensure_company_lohn_column

    ensure_company_lohn_column(db)
    try:
        rows = db.execute(
            """
            SELECT i.id, i.company_id, i.enabled, i.webhook_url, i.signing_secret, i.run_day, i.last_export_period
            FROM accounting_integrations i
            JOIN companies c ON c.id = i.company_id
            WHERE i.enabled = 1
              AND COALESCE(c.workpass_lohn_enabled, 0) = 1
              AND c.deleted_at IS NULL
            """
        ).fetchall()
    except Exception:
        rows = db.execute(
            """
            SELECT id, company_id, enabled, webhook_url, signing_secret, run_day, last_export_period
            FROM accounting_integrations WHERE enabled = 1
            """
        ).fetchall()
    return [dict(r) for r in rows]


def _alert_row_to_dict(row) -> dict[str, Any]:
    data = dict(row)
    try:
        fields = json.loads(data.get("missing_fields_json") or "[]")
    except Exception:
        fields = []
    if not isinstance(fields, list):
        fields = []
    return {
        "id": data.get("id"),
        "companyId": data.get("company_id"),
        "workerId": data.get("worker_id") or "",
        "employeeId": data.get("employee_id") or data.get("worker_id") or "",
        "period": data.get("period") or "",
        "missingFields": fields,
        "message": data.get("message") or "",
        "externalRef": data.get("external_ref") or "",
        "status": data.get("status") or "open",
        "createdAt": data.get("created_at"),
        "updatedAt": data.get("updated_at"),
        "dismissedAt": data.get("dismissed_at"),
        "dismissedByUserId": data.get("dismissed_by_user_id"),
        "workerFirstName": data.get("first_name") or "",
        "workerLastName": data.get("last_name") or "",
    }


def ingest_lohn_data_alerts(
    db,
    *,
    company_id: str,
    period: str = "",
    issues: list[dict[str, Any]],
    external_ref: str = "",
) -> dict[str, Any]:
    """Upsert open alerts from WorkPass Lohn / Steuer for missing employee fields."""
    ensure_accounting_schema(db)
    company_id = (company_id or "").strip()
    if not company_id:
        return {"ok": False, "error": "company_id_required"}
    if not isinstance(issues, list) or not issues:
        return {"ok": False, "error": "issues_required"}
    period = (period or "").strip()[:7]
    now = _now()
    created_ids: list[str] = []
    updated_ids: list[str] = []
    for item in issues:
        if not isinstance(item, dict):
            continue
        worker_id = str(item.get("workerId") or item.get("employeeId") or item.get("worker_id") or "").strip()
        employee_id = str(item.get("employeeId") or item.get("workerId") or worker_id).strip()
        item_period = str(item.get("period") or period or "").strip()[:7]
        fields = item.get("missingFields") or item.get("missing_fields") or item.get("fields") or []
        if isinstance(fields, str):
            fields = [f.strip() for f in fields.split(",") if f.strip()]
        if not isinstance(fields, list):
            fields = []
        fields = [str(f).strip() for f in fields if str(f).strip()]
        message = str(item.get("message") or item.get("text") or "").strip()
        if not message and fields:
            message = f"Fehlende Daten: {', '.join(fields)}"
        if not message and not fields:
            message = "Mitarbeiterdaten unvollständig"
        ref = str(item.get("externalRef") or item.get("external_ref") or external_ref or "").strip()
        existing = None
        if worker_id or employee_id:
            existing = db.execute(
                """
                SELECT id, status FROM lohn_data_alerts
                WHERE company_id = ?
                  AND period = ?
                  AND (worker_id = ? OR employee_id = ?)
                  AND status IN ('open', 'dismissed')
                ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, updated_at DESC
                LIMIT 1
                """,
                (company_id, item_period, worker_id or employee_id, employee_id or worker_id),
            ).fetchone()
        fields_json = json.dumps(fields, ensure_ascii=False)
        if existing:
            alert_id = str(existing["id"])
            db.execute(
                """
                UPDATE lohn_data_alerts
                SET worker_id = ?, employee_id = ?, missing_fields_json = ?, message = ?,
                    external_ref = ?, status = 'open', updated_at = ?,
                    dismissed_at = NULL, dismissed_by_user_id = NULL
                WHERE id = ?
                """,
                (
                    worker_id or employee_id,
                    employee_id or worker_id,
                    fields_json,
                    message[:1000],
                    ref[:200],
                    now,
                    alert_id,
                ),
            )
            updated_ids.append(alert_id)
        else:
            alert_id = f"lda-{uuid.uuid4().hex[:16]}"
            db.execute(
                """
                INSERT INTO lohn_data_alerts
                (id, company_id, worker_id, employee_id, period, missing_fields_json, message,
                 external_ref, status, created_at, updated_at, dismissed_at, dismissed_by_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, NULL, NULL)
                """,
                (
                    alert_id,
                    company_id,
                    worker_id or employee_id,
                    employee_id or worker_id,
                    item_period,
                    fields_json,
                    message[:1000],
                    ref[:200],
                    now,
                    now,
                ),
            )
            created_ids.append(alert_id)
    db.commit()
    return {
        "ok": True,
        "companyId": company_id,
        "period": period,
        "createdCount": len(created_ids),
        "updatedCount": len(updated_ids),
        "createdIds": created_ids,
        "updatedIds": updated_ids,
    }


def list_open_lohn_data_alerts(db, *, company_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    ensure_accounting_schema(db)
    limit = max(1, min(int(limit or 100), 500))
    if company_id:
        rows = db.execute(
            """
            SELECT a.*, w.first_name, w.last_name
            FROM lohn_data_alerts a
            LEFT JOIN workers w ON w.id = a.worker_id
            WHERE a.company_id = ? AND a.status = 'open'
            ORDER BY a.updated_at DESC
            LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT a.*, w.first_name, w.last_name
            FROM lohn_data_alerts a
            LEFT JOIN workers w ON w.id = a.worker_id
            WHERE a.status = 'open'
            ORDER BY a.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    out = []
    try:
        from .messages_inbox import resolve_company_worker
    except Exception:
        resolve_company_worker = None  # type: ignore
    for r in rows:
        item = _alert_row_to_dict(r)
        wid = str(item.get("workerId") or item.get("employeeId") or "").strip()
        cid = str(item.get("companyId") or "").strip()
        if resolve_company_worker and cid and wid and not (item.get("workerFirstName") or item.get("workerLastName")):
            resolved = resolve_company_worker(db, cid, wid)
            if resolved:
                item["workerId"] = resolved["id"] or wid
                item["workerFirstName"] = resolved["firstName"]
                item["workerLastName"] = resolved["lastName"]
                item["workerDisplayName"] = resolved["displayName"]
                item["workerResolved"] = True
        elif item.get("workerFirstName") or item.get("workerLastName"):
            item["workerDisplayName"] = f"{item.get('workerFirstName') or ''} {item.get('workerLastName') or ''}".strip()
            item["workerResolved"] = True
        else:
            item["workerDisplayName"] = ""
            item["workerResolved"] = False
        out.append(item)
    return out


def dismiss_lohn_data_alert(
    db,
    *,
    alert_id: str,
    actor_user_id: str,
    company_id: str | None = None,
) -> dict[str, Any]:
    ensure_accounting_schema(db)
    row = db.execute("SELECT * FROM lohn_data_alerts WHERE id = ?", (alert_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "not_found"}
    if company_id and str(row["company_id"]) != str(company_id):
        return {"ok": False, "error": "forbidden_company"}
    if str(row["status"] or "") == "dismissed":
        return {"ok": True, "id": alert_id, "status": "dismissed", "already": True}
    now = _now()
    db.execute(
        """
        UPDATE lohn_data_alerts
        SET status = 'dismissed', dismissed_at = ?, dismissed_by_user_id = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, str(actor_user_id or "")[:80], now, alert_id),
    )
    db.commit()
    return {"ok": True, "id": alert_id, "status": "dismissed"}


def _period_request_dict(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "companyId": row["company_id"],
        "period": row["period"],
        "status": row["status"],
        "source": row["source"],
        "wantEmployees": bool(int(row["want_employees"] or 0)),
        "wantPayroll": bool(int(row["want_payroll"] or 0)),
        "note": row["note"] or "",
        "externalRef": row["external_ref"] or "",
        "employeeCount": int(row["employee_count"] or 0),
        "totalHours": float(row["total_hours"] or 0),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "confirmedAt": row["confirmed_at"],
        "confirmedByUserId": row["confirmed_by_user_id"],
        "rejectedAt": row["rejected_at"],
        "rejectedByUserId": row["rejected_by_user_id"],
        "rejectReason": row["reject_reason"] or "",
        "deliveredAt": row["delivered_at"],
        "deliveryError": row["delivery_error"] or "",
    }


def get_period_request(db, *, company_id: str, period: str) -> dict[str, Any] | None:
    ensure_accounting_schema(db)
    row = db.execute(
        """
        SELECT * FROM lohn_period_requests
        WHERE company_id = ? AND period = ?
        LIMIT 1
        """,
        (company_id, period),
    ).fetchone()
    return _period_request_dict(row) if row else None


def get_period_request_by_id(db, request_id: str) -> dict[str, Any] | None:
    ensure_accounting_schema(db)
    row = db.execute("SELECT * FROM lohn_period_requests WHERE id = ?", (request_id,)).fetchone()
    return _period_request_dict(row) if row else None


def is_period_confirmed_for_lohn(db, *, company_id: str, period: str) -> bool:
    """True when platform confirmed handoff for this company/period (pull allowed)."""
    req = get_period_request(db, company_id=company_id, period=period)
    if not req:
        return False
    return str(req.get("status") or "") in {"confirmed", "delivered"}


def upsert_period_request(
    db,
    *,
    company_id: str,
    period: str,
    source: str = "lohn",
    want_employees: bool = True,
    want_payroll: bool = True,
    note: str = "",
    external_ref: str = "",
    employee_count: int = 0,
    total_hours: float = 0.0,
) -> dict[str, Any]:
    """
    Lohn or platform asks for employees + Abrechnung inputs for a month.
    Already confirmed/delivered periods are returned as-is (idempotent).
    """
    ensure_accounting_schema(db)
    company_id = str(company_id or "").strip()
    period = str(period or "").strip()[:7]
    now = _now()
    existing = get_period_request(db, company_id=company_id, period=period)
    if existing and str(existing.get("status") or "") in {"confirmed", "delivered"}:
        return {**existing, "ok": True, "alreadyReleased": True}
    if existing and str(existing.get("status") or "") == "pending_confirmation":
        db.execute(
            """
            UPDATE lohn_period_requests
            SET want_employees = ?, want_payroll = ?, note = ?, external_ref = ?,
                employee_count = ?, total_hours = ?, source = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                1 if want_employees else 0,
                1 if want_payroll else 0,
                (note or "")[:500],
                (external_ref or "")[:120],
                int(employee_count or 0),
                float(total_hours or 0),
                (source or "lohn")[:40],
                now,
                existing["id"],
            ),
        )
        db.commit()
        out = get_period_request_by_id(db, existing["id"]) or existing
        return {**out, "ok": True, "created": False}
    # Re-open rejected → pending, or create new
    if existing and str(existing.get("status") or "") == "rejected":
        db.execute(
            """
            UPDATE lohn_period_requests
            SET status = 'pending_confirmation', want_employees = ?, want_payroll = ?,
                note = ?, external_ref = ?, employee_count = ?, total_hours = ?,
                source = ?, rejected_at = NULL, rejected_by_user_id = NULL,
                reject_reason = '', updated_at = ?
            WHERE id = ?
            """,
            (
                1 if want_employees else 0,
                1 if want_payroll else 0,
                (note or "")[:500],
                (external_ref or "")[:120],
                int(employee_count or 0),
                float(total_hours or 0),
                (source or "lohn")[:40],
                now,
                existing["id"],
            ),
        )
        db.commit()
        out = get_period_request_by_id(db, existing["id"]) or existing
        return {**out, "ok": True, "created": True, "reopened": True}

    request_id = f"lpr-{uuid.uuid4().hex[:12]}"
    db.execute(
        """
        INSERT INTO lohn_period_requests
        (id, company_id, period, status, source, want_employees, want_payroll, note, external_ref,
         employee_count, total_hours, created_at, updated_at)
        VALUES (?, ?, ?, 'pending_confirmation', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request_id,
            company_id,
            period,
            (source or "lohn")[:40],
            1 if want_employees else 0,
            1 if want_payroll else 0,
            (note or "")[:500],
            (external_ref or "")[:120],
            int(employee_count or 0),
            float(total_hours or 0),
            now,
            now,
        ),
    )
    db.commit()
    out = get_period_request_by_id(db, request_id)
    return {**(out or {}), "ok": True, "created": True}


def list_period_requests(
    db,
    *,
    company_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    ensure_accounting_schema(db)
    limit = max(1, min(200, int(limit or 50)))
    status = str(status or "").strip()
    if company_id and status:
        rows = db.execute(
            """
            SELECT * FROM lohn_period_requests
            WHERE company_id = ? AND status = ?
            ORDER BY updated_at DESC LIMIT ?
            """,
            (company_id, status, limit),
        ).fetchall()
    elif company_id:
        rows = db.execute(
            """
            SELECT * FROM lohn_period_requests
            WHERE company_id = ?
            ORDER BY updated_at DESC LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
    elif status:
        rows = db.execute(
            """
            SELECT * FROM lohn_period_requests
            WHERE status = ?
            ORDER BY updated_at DESC LIMIT ?
            """,
            (status, limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT * FROM lohn_period_requests
            ORDER BY updated_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_period_request_dict(r) for r in rows]


def confirm_period_request(
    db,
    *,
    request_id: str,
    actor_user_id: str = "",
    company_id: str | None = None,
) -> dict[str, Any]:
    ensure_accounting_schema(db)
    row = get_period_request_by_id(db, request_id)
    if not row:
        return {"ok": False, "error": "not_found"}
    if company_id and str(row["companyId"]) != str(company_id):
        return {"ok": False, "error": "forbidden_company"}
    if str(row.get("status") or "") in {"confirmed", "delivered"}:
        return {**row, "ok": True, "already": True}
    if str(row.get("status") or "") == "rejected":
        return {"ok": False, "error": "already_rejected", **row}
    now = _now()
    db.execute(
        """
        UPDATE lohn_period_requests
        SET status = 'confirmed', confirmed_at = ?, confirmed_by_user_id = ?,
            updated_at = ?, delivery_error = ''
        WHERE id = ?
        """,
        (now, str(actor_user_id or "")[:80], now, request_id),
    )
    db.commit()
    out = get_period_request_by_id(db, request_id) or row
    return {**out, "ok": True}


def mark_period_request_delivered(
    db,
    *,
    request_id: str,
    error: str = "",
) -> dict[str, Any]:
    ensure_accounting_schema(db)
    now = _now()
    if error:
        db.execute(
            """
            UPDATE lohn_period_requests
            SET delivery_error = ?, updated_at = ?
            WHERE id = ?
            """,
            (str(error)[:200], now, request_id),
        )
    else:
        db.execute(
            """
            UPDATE lohn_period_requests
            SET status = 'delivered', delivered_at = ?, delivery_error = '', updated_at = ?
            WHERE id = ?
            """,
            (now, now, request_id),
        )
    db.commit()
    out = get_period_request_by_id(db, request_id)
    return {**(out or {}), "ok": True}


def reject_period_request(
    db,
    *,
    request_id: str,
    actor_user_id: str = "",
    company_id: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    ensure_accounting_schema(db)
    row = get_period_request_by_id(db, request_id)
    if not row:
        return {"ok": False, "error": "not_found"}
    if company_id and str(row["companyId"]) != str(company_id):
        return {"ok": False, "error": "forbidden_company"}
    if str(row.get("status") or "") in {"confirmed", "delivered"}:
        return {"ok": False, "error": "already_released", **row}
    now = _now()
    db.execute(
        """
        UPDATE lohn_period_requests
        SET status = 'rejected', rejected_at = ?, rejected_by_user_id = ?,
            reject_reason = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, str(actor_user_id or "")[:80], (reason or "")[:500], now, request_id),
    )
    db.commit()
    out = get_period_request_by_id(db, request_id) or row
    return {**out, "ok": True}