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
    row = db.execute(
        """
        SELECT id, company_id, enabled, webhook_url, api_key_prefix, run_day,
               last_export_period, created_at, updated_at
        FROM accounting_integrations WHERE company_id = ? LIMIT 1
        """,
        (company_id,),
    ).fetchone()
    return dict(row) if row else None


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
        VALUES (?, ?, ?, 'pending_approval', 'accounting_app', ?, 0, ?, ?, ?)
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
) -> str:
    ensure_accounting_schema(db)
    stmt_id = f"pst-{uuid.uuid4().hex[:12]}"
    now = _now()
    db.execute(
        """
        INSERT INTO payroll_statements
        (id, batch_id, company_id, worker_id, period, hours, hourly_rate, gross_amount, net_amount,
         currency, filename, file_path, file_size, status, external_ref, meta_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
        """,
        (
            stmt_id,
            batch_id,
            company_id,
            worker_id,
            period,
            float(hours or 0),
            float(hourly_rate or 0),
            float(gross_amount or 0),
            net_amount,
            (currency or "EUR")[:8],
            (filename or "")[:255],
            file_path or "",
            int(file_size or 0),
            (external_ref or "")[:120],
            json.dumps(meta or {}, ensure_ascii=False),
            now,
            now,
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


def get_batch(db, batch_id: str) -> dict[str, Any] | None:
    ensure_accounting_schema(db)
    row = db.execute("SELECT * FROM payroll_statement_batches WHERE id = ?", (batch_id,)).fetchone()
    return dict(row) if row else None


def list_batch_statements(db, batch_id: str) -> list[dict[str, Any]]:
    ensure_accounting_schema(db)
    rows = db.execute(
        """
        SELECT s.*, w.first_name, w.last_name, w.badge_id
        FROM payroll_statements s
        LEFT JOIN workers w ON w.id = s.worker_id
        WHERE s.batch_id = ?
        ORDER BY w.last_name, w.first_name
        """,
        (batch_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_enabled_integrations(db) -> list[dict[str, Any]]:
    ensure_accounting_schema(db)
    rows = db.execute(
        """
        SELECT id, company_id, enabled, webhook_url, signing_secret, run_day, last_export_period
        FROM accounting_integrations WHERE enabled = 1
        """
    ).fetchall()
    return [dict(r) for r in rows]
