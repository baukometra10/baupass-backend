"""Business logic: hours export, statement ingest, human approval + worker release."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from . import repository as repo
from .auth import sign_payload
from .hours_service import aggregate_company_hours, normalize_period
from .keys import invoice_storage_key, payroll_storage_key, require_company_id
from .schema import ensure_accounting_schema

from backend.app.platform.worker_documents import (
    WORKER_PAYROLL_DOC_TYPES,
    doc_type_label,
    is_payroll_doc_type,
    resolve_payroll_doc_type,
)


PAYROLL_BATCH_FORMAT = "platform.payroll.batch.v1"


def _statement_doc_type(stmt: dict[str, Any] | None = None, item: dict[str, Any] | None = None) -> str:
    """Canonical payroll document type stored on a statement (default Lohnabrechnung)."""
    meta: dict[str, Any] = {}
    if isinstance(stmt, dict):
        try:
            raw_meta = stmt.get("meta_json") or stmt.get("meta") or {}
            if isinstance(raw_meta, str):
                meta = json.loads(raw_meta or "{}")
            elif isinstance(raw_meta, dict):
                meta = raw_meta
        except Exception:
            meta = {}
    doc = meta.get("document") if isinstance(meta.get("document"), dict) else {}
    return resolve_payroll_doc_type(item or {}, stmt or {}, meta, doc)


def _default_payroll_filename(doc_type: str, period: str, worker_key: str) -> str:
    label = str(doc_type or "lohnabrechnung").strip().lower() or "lohnabrechnung"
    period_s = str(period or "period").strip() or "period"
    worker_s = str(worker_key or "worker").strip() or "worker"
    return f"{label}_{period_s}_{worker_s}.pdf"
PAYROLL_BATCH_PATH = "/v1/payroll/batch"

# Process-local debounce so Lohn webhook storms cannot saturate Waitress/SQLite.
_AUTO_FULFILL_RECENT: dict[str, float] = {}
_AUTO_FULFILL_INFLIGHT: set[str] = set()
_AUTO_FULFILL_LOCK = threading.Lock()
_AUTO_FULFILL_DEBOUNCE_SEC = 120.0


def _db_commit(db) -> None:
    """Release SQLite write locks before any outbound HTTP."""
    try:
        db.commit()
    except Exception:
        pass


def _auto_fulfill_gate(key: str) -> str | None:
    """
    Return None if this key may run now.
    Otherwise return a skip reason: 'inflight' | 'debounced'.
    """
    now = time.time()
    with _AUTO_FULFILL_LOCK:
        # Drop stale debounce entries
        stale = [k for k, ts in _AUTO_FULFILL_RECENT.items() if now - ts > _AUTO_FULFILL_DEBOUNCE_SEC]
        for k in stale:
            _AUTO_FULFILL_RECENT.pop(k, None)
        if key in _AUTO_FULFILL_INFLIGHT:
            return "inflight"
        last = _AUTO_FULFILL_RECENT.get(key)
        if last is not None and (now - last) < _AUTO_FULFILL_DEBOUNCE_SEC:
            return "debounced"
        _AUTO_FULFILL_INFLIGHT.add(key)
        return None


def _auto_fulfill_ungate(key: str, *, mark_done: bool) -> None:
    with _AUTO_FULFILL_LOCK:
        _AUTO_FULFILL_INFLIGHT.discard(key)
        if mark_done:
            _AUTO_FULFILL_RECENT[key] = time.time()


def prepare_hour_export(
    db,
    *,
    company_id: str,
    period: str,
    mark_sent: bool = False,
    worker_ids: list[str] | None = None,
) -> dict[str, Any]:
    payload = aggregate_company_hours(db, company_id=company_id, period=period, worker_ids=worker_ids)
    status = "sent" if mark_sent else "queued"
    meta = repo.save_hour_export(db, company_id=company_id, period=payload["period"], payload=payload, status=status)
    payload["exportId"] = meta["id"]
    payload["fingerprint"] = meta["fingerprint"]
    payload["exportStatus"] = meta["status"]
    return payload


def prepare_payroll_batch(
    db,
    *,
    company_id: str,
    period: str,
    mark_sent: bool = False,
    worker_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Capability platform.payroll.batch.v1 — same hours rows, packaged for Lohn pull/push.
    Body contract: { companyId, period } → full batch with employees[].
    Each employees[] entry includes nested employee + attendance for WorkPass Lohn.
    """
    hours = prepare_hour_export(
        db,
        company_id=company_id,
        period=period,
        mark_sent=mark_sent,
        worker_ids=worker_ids,
    )
    company_id = require_company_id(company_id)
    period = normalize_period(period)
    company = hours.get("company") or {"id": company_id}
    if isinstance(company, dict) and not company.get("name"):
        company = {**company, "name": hours.get("companyName") or ""}
    company_name = str((company or {}).get("name") or hours.get("companyName") or "").strip()
    company_ref = {"id": company_id, "name": company_name}
    employees = []
    for row in hours.get("rows") or []:
        wage_items = (
            row.get("wageItems")
            or row.get("lohnarten")
            or row.get("wageTypes")
            or []
        )
        bank = row.get("bank") if isinstance(row.get("bank"), dict) else {
            "name": row.get("bankName") or "",
            "iban": row.get("iban") or "",
        }
        entry = {
            **row,
            "employeeId": row.get("employeeId") or row.get("workerId"),
            "workerId": row.get("workerId") or row.get("employeeId"),
            "company": company_ref,
            "companyName": company_name,
            # Lohn ingestPayrollBatch reads these top-level keys only:
            "attendance": row.get("attendance") or {"hours": row.get("hours") or 0, "days": row.get("days") or 0},
            "bank": bank,
            "wageItems": wage_items,
            "lohnarten": wage_items,
            "wageTypes": wage_items,
            "brutto": row.get("brutto") or row.get("gross") or row.get("grossEstimate") or 0,
        }
        employees.append(entry)
    return {
        "ok": True,
        "kind": PAYROLL_BATCH_FORMAT,
        "capability": PAYROLL_BATCH_FORMAT,
        "format": PAYROLL_BATCH_FORMAT,
        "product": "WorkPass Lohn",
        "companyId": company_id,
        "company": company_ref,
        "companyName": company_name or hours.get("companyName") or "",
        "period": period,
        "periodStart": hours.get("periodStart"),
        "periodEnd": hours.get("periodEnd"),
        "rowCount": hours.get("rowCount") or len(employees),
        "employeeCount": hours.get("employeeCount") or len(employees),
        "payrollReadyCount": hours.get("payrollReadyCount"),
        "incompleteCount": hours.get("incompleteCount"),
        "incompleteEmployees": hours.get("incompleteEmployees") or [],
        "totalHours": hours.get("totalHours"),
        "totalDays": hours.get("totalDays"),
        "totalGrossEstimate": hours.get("totalGrossEstimate"),
        "currency": hours.get("currency") or "EUR",
        "tenantIsolation": "companyId::employeeId::period",
        "exportId": hours.get("exportId"),
        "fingerprint": hours.get("fingerprint"),
        "exportStatus": hours.get("exportStatus"),
        "rows": hours.get("rows") or [],
        "employees": employees,
        "hoursFormat": "suppix_workpass_lohn_hours_v1",
        "includesMasterData": True,
        "includesAttendance": True,
        "note": (
            "Full employee master + attendance for period. "
            "Brutto hint = hours × hourlyRate when hourly. "
            "WorkPass Lohn computes official payroll."
        ),
    }


def _post_webhook(
    url: str,
    body: dict[str, Any],
    *,
    signing_secret: str = "",
    api_key: str = "",
) -> dict[str, Any]:
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    ts = str(int(__import__("time").time()))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SUPPIX-WorkPass-Lohn-Bridge/1.0",
        "X-Suppix-Timestamp": ts,
        "X-Suppix-Event": str(body.get("event") or "hours.ready"),
        "X-Suppix-Product": "WorkPass Lohn",
        "X-WorkPass-Company-Id": str(body.get("companyId") or ""),
    }
    if api_key:
        headers["X-WorkPass-Key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"
        headers["X-WorkPass-Master-Key"] = api_key
    if signing_secret:
        headers["X-Suppix-Signature"] = sign_payload(signing_secret, timestamp=ts, body=raw)
    req = urlrequest.Request(url, data=raw, headers=headers, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=8) as resp:
            return {"ok": True, "status": int(resp.status), "body": resp.read()[:500].decode("utf-8", errors="replace")}
    except urlerror.HTTPError as exc:
        return {"ok": False, "status": int(exc.code), "error": str(exc)[:200]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def push_payroll_batch_to_lohn(
    db,
    *,
    company_id: str,
    period: str,
    batch: dict[str, Any] | None = None,
    worker_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Platform → Lohn POST /v1/payroll/batch with platform.payroll.batch.v1 payload.
    Use when Lohn cannot pull; after success Lohn only needs «Freigabe offener Jobs».
    """
    from .company_opt_in import is_workpass_lohn_enabled
    from .platform_link import _post_lohn_json, get_platform_link

    if not is_workpass_lohn_enabled(db, company_id):
        return {"ok": False, "error": "workpass_lohn_disabled", "skipped": True}
    integration = repo.get_integration(db, company_id)
    if not integration or not int(integration.get("enabled") or 0):
        return {"ok": False, "error": "integration_disabled"}
    link = get_platform_link(db)
    if not link.get("enabled") or not str(link.get("base_url") or "").strip():
        return {
            "ok": False,
            "error": "platform_link_disabled",
            "hint": "Admin → WorkPass Lohn Plattform-Link prüfen",
            "skipped": True,
        }
    if batch is None:
        batch = prepare_payroll_batch(
            db,
            company_id=company_id,
            period=period,
            mark_sent=True,
            worker_ids=worker_ids,
        )
    platform_url = str(link.get("platform_public_url") or "").rstrip("/")
    body = {
        **batch,
        "kind": PAYROLL_BATCH_FORMAT,
        "event": "payroll.batch",
        "pullUrl": (
            f"{platform_url}/api/v2/accounting/payroll-batch?period={batch['period']}"
            if platform_url
            else f"/api/v2/accounting/payroll-batch?period={batch['period']}"
        ),
        "hoursPullUrl": (
            f"{platform_url}/api/v2/accounting/hours?period={batch['period']}"
            if platform_url
            else f"/api/v2/accounting/hours?period={batch['period']}"
        ),
        "employeesPullUrl": (
            f"{platform_url}/api/v2/accounting/employees"
            if platform_url
            else "/api/v2/accounting/employees"
        ),
        "statementsStatusUrl": (
            f"{platform_url}/api/v2/accounting/statements?period={batch['period']}"
            if platform_url
            else f"/api/v2/accounting/statements?period={batch['period']}"
        ),
    }
    _db_commit(db)
    result = _post_lohn_json(
        link,
        path=PAYROLL_BATCH_PATH,
        body=body,
        event="payroll.batch",
        timeout=8,
    )
    if not result.get("ok"):
        db.execute(
            "UPDATE payroll_hour_exports SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
            (
                str(result.get("error") or result.get("status") or "payroll_batch_push_failed")[:200],
                __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ"),
                batch.get("exportId"),
            ),
        )
        db.commit()
    return {
        "ok": bool(result.get("ok")),
        "capability": PAYROLL_BATCH_FORMAT,
        "kind": PAYROLL_BATCH_FORMAT,
        "path": PAYROLL_BATCH_PATH,
        "push": result,
        "batch": {
            "companyId": company_id,
            "period": batch["period"],
            "exportId": batch.get("exportId"),
            "fingerprint": batch.get("fingerprint"),
            "employeeCount": batch.get("employeeCount"),
            "payrollReadyCount": batch.get("payrollReadyCount"),
            "incompleteCount": batch.get("incompleteCount"),
            "totalHours": batch.get("totalHours"),
            "totalDays": batch.get("totalDays"),
            "totalGrossEstimate": batch.get("totalGrossEstimate"),
            "employees": batch.get("employees") or [],
        },
    }


def notify_hours_ready(db, *, company_id: str, period: str) -> dict[str, Any]:
    from .company_opt_in import is_workpass_lohn_enabled
    from .platform_link import get_platform_link

    if not is_workpass_lohn_enabled(db, company_id):
        return {"ok": False, "error": "workpass_lohn_disabled", "skipped": True}
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
    link = get_platform_link(db)
    master = str(link.get("master_api_key") or "")
    platform_url = str(link.get("platform_public_url") or "").rstrip("/")

    # Always build payroll batch (marks hour export sent) — Lohn may pull or receive push.
    batch = prepare_payroll_batch(db, company_id=company_id, period=period, mark_sent=True)
    period_norm = batch["period"]
    payroll_pull = (
        f"{platform_url}/api/v2/accounting/payroll-batch?period={period_norm}"
        if platform_url
        else f"/api/v2/accounting/payroll-batch?period={period_norm}"
    )
    hours_pull = (
        f"{platform_url}/api/v2/accounting/hours?period={period_norm}"
        if platform_url
        else f"/api/v2/accounting/hours?period={period_norm}"
    )

    webhook_result: dict[str, Any] = {"skipped": "no_webhook_url"}
    if webhook:
        event = {
            "event": "hours.ready",
            "product": "WorkPass Lohn",
            "capability": PAYROLL_BATCH_FORMAT,
            "format": PAYROLL_BATCH_FORMAT,
            "companyId": company_id,
            "company": {"id": company_id},
            "period": period_norm,
            "exportId": batch.get("exportId"),
            "fingerprint": batch.get("fingerprint"),
            "rowCount": batch.get("rowCount"),
            "employeeCount": batch.get("employeeCount"),
            "payrollReadyCount": batch.get("payrollReadyCount"),
            "incompleteCount": batch.get("incompleteCount"),
            "totalHours": batch.get("totalHours"),
            "pullUrl": hours_pull,
            "payrollBatchPullUrl": payroll_pull,
            "employeesPullUrl": (
                f"{platform_url}/api/v2/accounting/employees"
                if platform_url
                else "/api/v2/accounting/employees"
            ),
            "tenantIsolation": "companyId::employeeId::period",
        }
        _db_commit(db)
        webhook_result = _post_webhook(
            webhook,
            event,
            signing_secret=str(full["signing_secret"] or "") if full else "",
            api_key=master,
        )

    # Push full batch to Lohn so open jobs appear without pull URL config.
    push_result = push_payroll_batch_to_lohn(
        db, company_id=company_id, period=period_norm, batch=batch
    )

    # Pull-ready counts as success even if outbound push/webhook is unavailable.
    ok = bool(webhook_result.get("ok") or push_result.get("ok") or batch.get("exportId"))
    if webhook and not webhook_result.get("ok") and not push_result.get("ok"):
        db.execute(
            "UPDATE payroll_hour_exports SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
            (
                str(webhook_result.get("error") or webhook_result.get("status") or "webhook_failed")[:200],
                __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ"),
                batch.get("exportId"),
            ),
        )
        db.commit()
    return {
        "ok": ok,
        "webhook": webhook_result,
        "payrollBatchPush": push_result,
        "payrollBatchPullUrl": payroll_pull,
        "export": {"id": batch.get("exportId"), "period": period_norm},
        "capability": PAYROLL_BATCH_FORMAT,
        "batch": {
            "companyId": company_id,
            "period": period_norm,
            "exportId": batch.get("exportId"),
            "fingerprint": batch.get("fingerprint"),
            "employeeCount": batch.get("employeeCount"),
            "payrollReadyCount": batch.get("payrollReadyCount"),
            "incompleteCount": batch.get("incompleteCount"),
            "totalHours": batch.get("totalHours"),
            "totalGrossEstimate": batch.get("totalGrossEstimate"),
        },
        "employeeCount": batch.get("employeeCount"),
        "payrollReadyCount": batch.get("payrollReadyCount"),
        "incompleteCount": batch.get("incompleteCount"),
        "totalHours": batch.get("totalHours"),
    }


def push_employees_to_lohn(
    db,
    *,
    company_id: str,
    timeout: float = 12,
) -> dict[str, Any]:
    """Platform → Lohn POST /v1/employees/import with full employee master."""
    from .company_opt_in import is_workpass_lohn_enabled
    from .hours_service import build_employee_master_list
    from .platform_link import _post_lohn_json, get_platform_link

    company_id = require_company_id(company_id)
    if not is_workpass_lohn_enabled(db, company_id):
        return {"ok": False, "error": "workpass_lohn_disabled", "skipped": True}
    link = get_platform_link(db)
    if not link.get("enabled") or not str(link.get("base_url") or "").strip():
        return {
            "ok": False,
            "error": "platform_link_disabled",
            "hint": "Admin → WorkPass Lohn Plattform-Link prüfen",
            "skipped": True,
        }
    employees = build_employee_master_list(db, company_id=company_id)
    body = {
        **employees,
        "event": "employees.import",
        "companyId": company_id,
        "id": company_id,
    }
    _db_commit(db)
    result = _post_lohn_json(
        link,
        path="/v1/employees/import",
        body=body,
        event="employees.import",
        timeout=min(float(timeout or 12), 8.0),
    )
    return {
        "ok": bool(result.get("ok")),
        "path": "/v1/employees/import",
        "push": result,
        "employeeCount": employees.get("employeeCount"),
        "companyId": company_id,
    }


def push_stammdaten_to_lohn(
    db,
    *,
    company_id: str,
    period: str | None = None,
    include_payroll: bool = False,
) -> dict[str, Any]:
    """
    Platform → Lohn: company upsert + full employee/contract master.
    Use when Lohn cannot pull GET /api/contracts or /api/v1/company (401 loop).
    """
    from .hours_service import normalize_period as _norm_period
    from .platform_link import notify_company_lohn_status

    company_id = require_company_id(company_id)
    out: dict[str, Any] = {"companyId": company_id, "ok": False}
    _db_commit(db)
    try:
        out["companyUpsert"] = notify_company_lohn_status(db, company_id, enabled=True)
    except Exception as exc:
        out["companyUpsert"] = {"ok": False, "error": str(exc)[:160]}
    out["employeesImport"] = push_employees_to_lohn(db, company_id=company_id, timeout=8)
    if include_payroll and period:
        try:
            period_norm = _norm_period(str(period).strip()[:7])
        except ValueError:
            period_norm = str(period or "").strip()[:7]
        if period_norm:
            out["payrollBatch"] = push_payroll_batch_to_lohn(
                db, company_id=company_id, period=period_norm
            )
    out["ok"] = bool(
        (out.get("employeesImport") or {}).get("ok")
        or (out.get("companyUpsert") or {}).get("ok")
        or (out.get("payrollBatch") or {}).get("ok")
    )
    out["message"] = (
        "Stammdaten an WorkPass Lohn übergeben"
        if out["ok"]
        else "Stammdaten-Push teilweise fehlgeschlagen"
    )
    return out


def notify_employee_data_resolved(
    db,
    *,
    company_id: str,
    worker_id: str,
    actor_user_id: str = "",
    source: str = "contracts",
    timeout: float = 10,
) -> dict[str, Any]:
    """
    After admin fills missing payroll stammdaten: push this employee back to Lohn,
    clear open data alerts, and ack related missing-data inbox messages.
    """
    from .company_opt_in import is_workpass_lohn_enabled
    from .hours_service import get_employee_master_item
    from .messages_inbox import ack_message_to_lohn
    from .platform_link import _post_lohn_json, get_platform_link
    from .schema import ensure_accounting_schema

    company_id = require_company_id(company_id)
    worker_id = str(worker_id or "").strip()
    if not worker_id:
        return {"ok": False, "error": "worker_id_required"}

    ensure_accounting_schema(db)
    employee = get_employee_master_item(db, company_id=company_id, worker_id=worker_id)
    if not employee:
        return {"ok": False, "error": "worker_not_found"}

    company = db.execute("SELECT id, name FROM companies WHERE id = ?", (company_id,)).fetchone()
    company_name = (company["name"] if company else "") or ""
    missing = list(employee.get("missingFields") or [])
    payroll_ready = bool(employee.get("payrollReady"))

    # Clear alerts for fields that are now present; if fully ready, clear all for worker.
    alerts = dismiss_related_data_alerts_for_worker_if_improved(
        db,
        company_id=company_id,
        worker_id=worker_id,
        still_missing=missing,
        actor_user_id=actor_user_id,
    )

    message_acks: list[dict[str, Any]] = []
    try:
        rows = db.execute(
            """
            SELECT id FROM accounting_messages
            WHERE company_id = ?
              AND worker_id = ?
              AND status = 'pending'
              AND lower(COALESCE(kind, '')) IN (
                    'missing_data', 'missing_employee_data', 'employee_data', 'data_gap'
                  )
            ORDER BY received_at DESC
            LIMIT 20
            """,
            (company_id, worker_id),
        ).fetchall()
        for row in rows:
            message_acks.append(
                ack_message_to_lohn(
                    db,
                    message_id=str(row["id"]),
                    actor_user_id=actor_user_id,
                    company_id=company_id,
                    fulfill=False,
                )
            )
    except Exception as exc:
        message_acks.append({"ok": False, "error": str(exc)[:160]})

    if not is_workpass_lohn_enabled(db, company_id):
        return {
            "ok": True,
            "skipped": True,
            "error": "workpass_lohn_disabled",
            "companyId": company_id,
            "workerId": worker_id,
            "payrollReady": payroll_ready,
            "missingFields": missing,
            "employee": employee,
            "push": {"ok": False, "skipped": True, "error": "workpass_lohn_disabled"},
            "alerts": alerts,
            "messageAcks": message_acks,
            "path": "/v1/employees/import",
        }

    link = get_platform_link(db)
    push: dict[str, Any] = {"ok": False, "skipped": True, "error": "platform_link_disabled"}
    payroll_push: dict[str, Any] = {"ok": False, "skipped": True}
    if link.get("enabled") and str(link.get("base_url") or "").strip():
        body = {
            "ok": True,
            "format": "platform.employees.v1",
            "capability": "platform.employees.v1",
            "product": "WorkPass Lohn",
            "event": "employees.updated",
            "reason": "missing_data_resolved",
            "source": str(source or "platform")[:40],
            "companyId": company_id,
            "id": company_id,
            "company": {"id": company_id, "name": company_name},
            "companyName": company_name,
            "employeeCount": 1,
            "payrollReadyCount": 1 if payroll_ready else 0,
            "incompleteCount": 0 if payroll_ready else 1,
            "employees": [employee],
            "resolvedWorkerIds": [worker_id],
            "payrollReady": payroll_ready,
            "missingFields": missing,
            "actorUserId": str(actor_user_id or "")[:80],
        }
        _db_commit(db)
        push = _post_lohn_json(
            link,
            path="/v1/employees/import",
            body=body,
            event="employees.updated",
            timeout=min(float(timeout or 10), 8.0),
        )
        # Also push hours/Brutto for the active payroll month so Lohn does not stay on «Brutto fehlt».
        try:
            from .monthly_job import previous_period

            period_for_batch = previous_period()
            open_alert = db.execute(
                """
                SELECT period FROM lohn_data_alerts
                WHERE company_id = ? AND worker_id = ? AND status = 'open'
                  AND COALESCE(period, '') != ''
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (company_id, worker_id),
            ).fetchone()
            if open_alert and str(open_alert["period"] or "").strip():
                period_for_batch = str(open_alert["period"]).strip()[:7]
            else:
                msg_period = db.execute(
                    """
                    SELECT period FROM accounting_messages
                    WHERE company_id = ? AND worker_id = ?
                      AND COALESCE(period, '') != ''
                    ORDER BY received_at DESC
                    LIMIT 1
                    """,
                    (company_id, worker_id),
                ).fetchone()
                if msg_period and str(msg_period["period"] or "").strip():
                    period_for_batch = str(msg_period["period"]).strip()[:7]
            single_batch = prepare_payroll_batch(
                db,
                company_id=company_id,
                period=period_for_batch,
                mark_sent=True,
                worker_ids=[worker_id],
            )
            payroll_push = push_payroll_batch_to_lohn(
                db,
                company_id=company_id,
                period=period_for_batch,
                batch=single_batch,
                worker_ids=[worker_id],
            )
        except Exception as exc:
            payroll_push = {"ok": False, "error": str(exc)[:160]}

    return {
        "ok": bool(push.get("ok"))
        or bool(payroll_push.get("ok"))
        or int(alerts.get("dismissed") or 0) > 0
        or any(bool(a.get("ok")) for a in message_acks if isinstance(a, dict)),
        "companyId": company_id,
        "workerId": worker_id,
        "payrollReady": payroll_ready,
        "missingFields": missing,
        "employee": employee,
        "push": push,
        "payrollBatchPush": payroll_push,
        "alerts": alerts,
        "messageAcks": message_acks,
        "path": "/v1/employees/import",
    }


def dismiss_related_data_alerts_for_worker_if_improved(
    db,
    *,
    company_id: str,
    worker_id: str,
    still_missing: list[str] | None = None,
    actor_user_id: str = "",
) -> dict[str, Any]:
    """
    Dismiss open Lohn data alerts for a worker when previously missing fields are filled.
    If the worker is fully payroll-ready, dismiss all open alerts for that worker.
    """
    from .schema import ensure_accounting_schema

    ensure_accounting_schema(db)
    company_id = str(company_id or "").strip()
    worker_id = str(worker_id or "").strip()
    if not company_id or not worker_id:
        return {"ok": True, "dismissed": 0}
    from datetime import datetime, timezone

    still = {str(f).strip() for f in (still_missing or []) if str(f).strip()}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    open_rows = db.execute(
        """
        SELECT id, missing_fields_json FROM lohn_data_alerts
        WHERE company_id = ? AND status = 'open' AND worker_id = ?
        """,
        (company_id, worker_id),
    ).fetchall()
    dismissed = 0
    for row in open_rows:
        fields: list[str] = []
        try:
            import json as _json

            raw = row["missing_fields_json"] or "[]"
            parsed = _json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(parsed, list):
                fields = [str(f).strip() for f in parsed if str(f).strip()]
        except Exception:
            fields = []
        # Dismiss when all alerted fields are no longer missing (or alert had no field list).
        if fields and any(f in still for f in fields):
            # Update remaining missing fields on the alert instead of dismissing.
            remaining = [f for f in fields if f in still]
            try:
                import json as _json

                db.execute(
                    """
                    UPDATE lohn_data_alerts
                    SET missing_fields_json = ?, message = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        _json.dumps(remaining, ensure_ascii=False),
                        f"Fehlende Daten: {', '.join(remaining)}"[:1000],
                        now,
                        str(row["id"]),
                    ),
                )
            except Exception:
                pass
            continue
        db.execute(
            """
            UPDATE lohn_data_alerts
            SET status = 'dismissed', dismissed_at = ?, dismissed_by_user_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, str(actor_user_id or "")[:80], now, str(row["id"])),
        )
        dismissed += 1
    try:
        db.commit()
    except Exception:
        pass
    # Prefer dedicated helper when fully ready (covers period variants).
    if not still:
        from .messages_inbox import dismiss_related_data_alerts_for_message

        extra = dismiss_related_data_alerts_for_message(
            db,
            company_id=company_id,
            worker_id=worker_id,
            actor_user_id=actor_user_id,
        )
        dismissed = max(dismissed, int(extra.get("dismissed") or 0))
    return {"ok": True, "dismissed": dismissed}


def auto_fulfill_lohn_data_request(
    db,
    *,
    company_id: str,
    period: str | None = None,
    source: str = "lohn_webhook",
    note: str = "",
    external_ref: str = "",
    want_employees: bool = True,
    want_payroll: bool = True,
    want_branding: bool = True,
    worker_id: str = "",
) -> dict[str, Any]:
    """
    Immediate Platform → Lohn handoff when accounting asks for data.

    Always scoped to a single companyId (no cross-tenant bleed).
    Pushes company branding/master, full employee+contract master, and/or
    hours/payroll-batch for the requested period — without waiting for Ops confirm.

    Payslip release to workers stays human-gated elsewhere (ingest → pending_approval).
    """
    from .company_opt_in import is_workpass_lohn_enabled
    from .hours_service import normalize_period as _norm_period
    from .platform_link import notify_company_lohn_status

    company_id = require_company_id(company_id)
    if not is_workpass_lohn_enabled(db, company_id):
        return {"ok": False, "error": "workpass_lohn_disabled", "companyId": company_id}

    # Emergency kill-switch (Railway): WORKPASS_LOHN_AUTO_FULFILL=0
    import os

    flag = str(os.getenv("WORKPASS_LOHN_AUTO_FULFILL", "1")).strip().lower()
    if flag in {"0", "false", "no", "off"}:
        period_for_queue = str(period or "").strip()[:7]
        if period_for_queue:
            try:
                queued = request_period_handoff(
                    db,
                    company_id=company_id,
                    period=period_for_queue,
                    source=source,
                    note=(note or "auto_fulfill_disabled")[:500],
                    external_ref=external_ref,
                    notify_inbox=False,
                )
            except Exception as exc:
                queued = {"ok": False, "error": str(exc)[:120]}
        else:
            queued = {"ok": True, "skipped": "no_period"}
        return {
            "ok": True,
            "status": "queued_only",
            "skipped": "auto_fulfill_disabled",
            "companyId": company_id,
            "period": period_for_queue or None,
            "queued": queued,
            "message": "Auto-fulfill disabled — request queued only",
            "tenantIsolation": "companyId",
        }

    period_norm = ""
    if period:
        try:
            period_norm = _norm_period(str(period).strip()[:7])
        except ValueError:
            period_norm = str(period or "").strip()[:7]

    worker_id = str(worker_id or "").strip()
    gate_key = f"{company_id}|{period_norm or 'master'}|{int(want_employees)}|{int(want_payroll)}|{worker_id}"
    skip = _auto_fulfill_gate(gate_key)
    if skip:
        return {
            "ok": True,
            "status": "skipped",
            "skipped": skip,
            "companyId": company_id,
            "period": period_norm or None,
            "message": f"Auto-fulfill skipped ({skip}) to protect platform capacity",
            "tenantIsolation": "companyId",
        }

    replies: dict[str, Any] = {
        "companyId": company_id,
        "period": period_norm or None,
        "tenantIsolation": "companyId",
    }
    mark_done = False
    try:
        if want_branding:
            try:
                _db_commit(db)
                replies["companyUpsert"] = notify_company_lohn_status(
                    db, company_id, enabled=True
                )
            except Exception as exc:
                replies["companyUpsert"] = {"ok": False, "error": str(exc)[:160]}
            try:
                from .platform_link import push_company_logo_to_lohn

                _db_commit(db)
                replies["logoPush"] = push_company_logo_to_lohn(db, company_id)
            except Exception as exc:
                replies["logoPush"] = {"ok": False, "error": str(exc)[:160]}
            if not want_employees and not want_payroll:
                mark_done = bool(
                    (replies.get("companyUpsert") or {}).get("ok")
                    or (replies.get("logoPush") or {}).get("ok")
                )
                return {
                    "ok": mark_done,
                    "status": "delivered" if mark_done else "partial",
                    "mode": "branding",
                    "replies": replies,
                    "message": "Firmenlogo und Stammdaten an WorkPass Lohn übergeben",
                    "error": None
                    if mark_done
                    else (
                        (replies.get("logoPush") or {}).get("error")
                        or (replies.get("companyUpsert") or {}).get("error")
                    ),
                }

        if worker_id and not period_norm and not want_payroll:
            # Single-employee data repair from Lohn missing_data prompts
            try:
                replies["employeeResolved"] = notify_employee_data_resolved(
                    db,
                    company_id=company_id,
                    worker_id=worker_id,
                    actor_user_id="system-lohn-auto",
                    source=source,
                )
            except Exception as exc:
                replies["employeeResolved"] = {"ok": False, "error": str(exc)[:160]}
            mark_done = bool((replies.get("employeeResolved") or {}).get("ok"))
            employee_payload = (replies.get("employeeResolved") or {}).get("employee")
            return {
                "ok": mark_done,
                "status": "delivered" if mark_done else "partial",
                "mode": "employee",
                "replies": replies,
                "payload": {
                    "companyId": company_id,
                    "workerId": worker_id,
                    "employees": [employee_payload] if employee_payload else [],
                },
                "message": "Employee master pushed to WorkPass Lohn",
            }

        if worker_id and period_norm and want_payroll:
            # Single-person payroll repair: hours/SV/KK for one employee only
            single_batch: dict[str, Any] = {
                "ok": False,
                "kind": PAYROLL_BATCH_FORMAT,
                "companyId": company_id,
                "period": period_norm,
                "employees": [],
            }
            try:
                replies["employeeResolved"] = notify_employee_data_resolved(
                    db,
                    company_id=company_id,
                    worker_id=worker_id,
                    actor_user_id="system-lohn-auto",
                    source=source,
                )
            except Exception as exc:
                replies["employeeResolved"] = {"ok": False, "error": str(exc)[:160]}
            try:
                single_batch = prepare_payroll_batch(
                    db,
                    company_id=company_id,
                    period=period_norm,
                    mark_sent=True,
                    worker_ids=[worker_id],
                )
                replies["payrollBatch"] = push_payroll_batch_to_lohn(
                    db,
                    company_id=company_id,
                    period=period_norm,
                    batch=single_batch,
                    worker_ids=[worker_id],
                )
            except Exception as exc:
                replies["payrollBatch"] = {"ok": False, "error": str(exc)[:160]}
            mark_done = bool(
                (replies.get("payrollBatch") or {}).get("ok")
                or (replies.get("employeeResolved") or {}).get("ok")
            )
            return {
                "ok": mark_done,
                "status": "delivered" if mark_done else "partial",
                "mode": "employee_period",
                "replies": replies,
                "payload": single_batch,
                "message": "Single-employee payroll batch pushed to WorkPass Lohn",
            }

        if period_norm and (want_employees or want_payroll):
            # Track request row, then auto-confirm + push (no human gate for outbound data)
            req = request_period_handoff(
                db,
                company_id=company_id,
                period=period_norm,
                source=source,
                note=note or "auto_fulfill",
                external_ref=external_ref,
                notify_inbox=False,
            )
            replies["periodRequest"] = req
            if not req.get("ok"):
                return {
                    "ok": False,
                    "status": "error",
                    "mode": "period",
                    "replies": replies,
                    "error": req.get("error") or "period_request_failed",
                }

            # Critical: do NOT re-push on every Lohn retry once already delivered
            if req.get("alreadyReleased"):
                mark_done = True
                return {
                    "ok": True,
                    "status": "already_delivered",
                    "mode": "period",
                    "replies": replies,
                    "message": "Period already delivered — skipped re-push",
                    "skipped": "already_delivered",
                }

            delivery = confirm_period_handoff(
                db,
                company_id=company_id,
                period=period_norm,
                request_id=str((req.get("request") or {}).get("id") or "") or None,
                actor_user_id="system-lohn-auto",
            )
            replies["delivery"] = delivery

            # Ops audit trail — delivered, not "please confirm"
            inbox = None
            try:
                from .messages_inbox import create_test_accounting_message

                emp_n = (delivery.get("employees") or {}).get("employeeCount")
                inbox = create_test_accounting_message(
                    db,
                    company_id=company_id,
                    subject=f"Daten an Lohn übergeben · {period_norm}",
                    body=(
                        f"WorkPass Lohn hat Periode {period_norm} angefragt. "
                        f"Die Plattform hat Stammdaten"
                        f"{f' ({emp_n} MA)' if emp_n is not None else ''} "
                        f"und Abrechnungsstunden automatisch übergeben "
                        f"(Firma {company_id}, Isolation companyId)."
                    ),
                    period=period_norm,
                    kind="data_delivered",
                )
            except Exception as exc:
                inbox = {"ok": False, "error": str(exc)[:120]}
            replies["inbox"] = inbox
            mark_done = True

            return {
                "ok": bool(delivery.get("ok")),
                "status": delivery.get("status") or "delivered",
                "mode": "period",
                "replies": replies,
                "payload": {
                    "kind": PAYROLL_BATCH_FORMAT,
                    "companyId": company_id,
                    "period": period_norm,
                    "delivery": delivery,
                },
                "message": delivery.get("message")
                or "Mitarbeiter und Abrechnungsdaten automatisch an WorkPass Lohn übergeben",
                "error": delivery.get("error"),
            }

        # Master sync without month — company + employees (bypass Lohn GET 401 loops)
        if want_employees or want_branding:
            _db_commit(db)
            replies["stammdatenPush"] = push_stammdaten_to_lohn(
                db,
                company_id=company_id,
                period=None,
                include_payroll=False,
            )
            if not replies.get("companyUpsert"):
                replies["companyUpsert"] = (replies.get("stammdatenPush") or {}).get(
                    "companyUpsert"
                )
            replies["employeesImport"] = (replies.get("stammdatenPush") or {}).get(
                "employeesImport"
            ) or replies.get("employeesImport")
        mark_done = bool(
            (replies.get("stammdatenPush") or {}).get("ok")
            or (replies.get("employeesImport") or {}).get("ok")
            or (replies.get("companyUpsert") or {}).get("ok")
        )
        return {
            "ok": mark_done,
            "status": "delivered",
            "mode": "employees",
            "replies": replies,
            "message": "Company/employees master pushed to WorkPass Lohn",
        }
    finally:
        _auto_fulfill_ungate(gate_key, mark_done=mark_done)


def request_period_handoff(
    db,
    *,
    company_id: str,
    period: str,
    source: str = "lohn",
    note: str = "",
    external_ref: str = "",
    notify_inbox: bool = True,
) -> dict[str, Any]:
    """
    WorkPass Lohn asks: employees + Abrechnung inputs for company/period.

    Creates/updates the period request row. Prefer auto_fulfill_lohn_data_request()
    for webhook/poll paths that should push immediately. Ops can still confirm
    manually via confirm_period_handoff when notify_inbox left a pending request.
    """
    from .company_opt_in import is_workpass_lohn_enabled
    from .hours_service import aggregate_company_hours, build_employee_master_list

    company_id = require_company_id(company_id)
    period = normalize_period(period)
    if not is_workpass_lohn_enabled(db, company_id):
        return {"ok": False, "error": "workpass_lohn_disabled"}

    employees = build_employee_master_list(db, company_id=company_id)
    hours = aggregate_company_hours(db, company_id=company_id, period=period)
    req = repo.upsert_period_request(
        db,
        company_id=company_id,
        period=period,
        source=source,
        want_employees=True,
        want_payroll=True,
        note=note,
        external_ref=external_ref,
        employee_count=int(employees.get("employeeCount") or 0),
        total_hours=float(hours.get("totalHours") or 0),
    )
    if req.get("alreadyReleased"):
        return {
            "ok": True,
            "status": req.get("status"),
            "request": req,
            "alreadyReleased": True,
            "message": "Period already confirmed — pull employees/hours/payroll-batch",
            "pull": {
                "employees": "/api/v2/accounting/employees",
                "hours": f"/api/v2/accounting/hours?period={period}",
                "payrollBatch": f"/api/v2/accounting/payroll-batch?period={period}",
            },
        }

    inbox = None
    if notify_inbox and (req.get("created") or req.get("reopened")):
        try:
            from .messages_inbox import create_test_accounting_message

            inbox = create_test_accounting_message(
                db,
                company_id=company_id,
                subject=f"Lohn-Anfrage: Mitarbeiter & Abrechnung {period}",
                body=(
                    f"WorkPass Lohn möchte für Periode {period} die Mitarbeiterstammdaten "
                    f"und Abrechnungsdaten ({int(employees.get('employeeCount') or 0)} MA, "
                    f"{float(hours.get('totalHours') or 0)} Std.). "
                    "Bitte im Ops Center bestätigen — erst dann werden die Daten übergeben."
                ),
                period=period,
                kind="period_request",
            )
        except Exception as exc:
            inbox = {"ok": False, "error": str(exc)[:120]}

    return {
        "ok": True,
        "status": "pending_confirmation",
        "request": req,
        "preview": {
            "employeeCount": employees.get("employeeCount"),
            "payrollReadyCount": employees.get("payrollReadyCount"),
            "incompleteCount": employees.get("incompleteCount"),
            "totalHours": hours.get("totalHours"),
            "totalGrossEstimate": hours.get("totalGrossEstimate"),
        },
        "message": "Warte auf Bestätigung der Plattform — danach werden Mitarbeiter und Abrechnungsdaten übergeben",
        "inbox": inbox,
    }


def confirm_period_handoff(
    db,
    *,
    company_id: str | None = None,
    period: str | None = None,
    request_id: str | None = None,
    actor_user_id: str = "",
) -> dict[str, Any]:
    """
    Human confirmation: release employees + payroll batch for the period to WorkPass Lohn.
    """
    scope = str(company_id or "").strip() or None
    if request_id:
        req = repo.get_period_request_by_id(db, request_id)
        if not req:
            return {"ok": False, "error": "not_found"}
        if scope and str(req["companyId"]) != str(scope):
            return {"ok": False, "error": "forbidden_company"}
        company_id = str(req["companyId"])
        period = str(req["period"])
    else:
        company_id = require_company_id(company_id or "")
        period = normalize_period(period or "")
        # Ensure a request row exists (platform-initiated confirm)
        req = repo.upsert_period_request(
            db,
            company_id=company_id,
            period=period,
            source="platform",
            note="Confirmed from platform Ops",
        )
        request_id = str(req.get("id") or "")

    confirmed = repo.confirm_period_request(
        db,
        request_id=str(request_id),
        actor_user_id=actor_user_id,
        company_id=None,
    )
    if not confirmed.get("ok"):
        return confirmed

    # Release write locks before outbound HTTP (prevents platform-wide SQLite stalls)
    _db_commit(db)

    # Deliver full package to Lohn (employees import + payroll batch)
    employees_push = push_employees_to_lohn(db, company_id=str(company_id), timeout=6)
    delivery = notify_hours_ready(db, company_id=str(company_id), period=str(period))
    push_ok = bool(
        employees_push.get("ok")
        or (delivery.get("payrollBatchPush") or {}).get("ok")
    )
    # Fall back: local export ready still counts if outbound host unreachable
    delivered_ok = push_ok or bool(delivery.get("ok") and delivery.get("export"))
    if delivered_ok:
        repo.mark_period_request_delivered(db, request_id=str(request_id))
    else:
        err = (
            str((employees_push.get("push") or {}).get("error") or employees_push.get("error") or "")
            or str((delivery.get("payrollBatchPush") or {}).get("error") or "")
            or str(delivery.get("error") or "")
            or "delivery_failed"
        )
        repo.mark_period_request_delivered(
            db,
            request_id=str(request_id),
            error=err,
        )

    employees = None
    try:
        from .hours_service import build_employee_master_list

        employees = build_employee_master_list(db, company_id=str(company_id))
    except Exception:
        employees = None

    final = repo.get_period_request_by_id(db, str(request_id))
    err_hint = ""
    if not push_ok:
        err_hint = (
            str((employees_push.get("push") or {}).get("error") or employees_push.get("error") or "")
            or str(((delivery.get("payrollBatchPush") or {}).get("push") or {}).get("error") or "")
            or str((delivery.get("payrollBatchPush") or {}).get("error") or "")
            or ""
        )

    inbox_clear: dict[str, Any] = {"ok": False, "cleared": 0}
    try:
        from .messages_inbox import clear_period_handoff_messages

        inbox_clear = clear_period_handoff_messages(
            db,
            company_id=str(company_id),
            period=str(period),
            actor_user_id=str(actor_user_id or ""),
        )
    except Exception as exc:
        inbox_clear = {"ok": False, "error": str(exc)[:120], "cleared": 0}

    return {
        "ok": delivered_ok,
        "status": (final or {}).get("status") or "confirmed",
        "request": final,
        "employeesPush": employees_push,
        "delivery": delivery,
        "inboxCleared": inbox_clear,
        "employees": {
            "employeeCount": (employees or {}).get("employeeCount"),
            "payrollReadyCount": (employees or {}).get("payrollReadyCount"),
        }
        if employees
        else None,
        "message": (
            "Bestätigt — Mitarbeiter und Abrechnungsdaten an WorkPass Lohn übergeben"
            if push_ok
            else (
                f"Bestätigt, aber Lohn antwortet nicht: {err_hint[:160]}"
                if err_hint
                else "Bestätigt — Daten bereit (Lohn-Push prüfen)"
            )
        ),
        "error": None if push_ok else ("lohn_push_failed" if err_hint else None),
        "pull": {
            "employees": "/api/v2/accounting/employees",
            "hours": f"/api/v2/accounting/hours?period={period}",
            "payrollBatch": f"/api/v2/accounting/payroll-batch?period={period}",
        },
    }


def reject_period_handoff(
    db,
    *,
    request_id: str,
    actor_user_id: str = "",
    company_id: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """Reject period handoff and clear matching Lohn request inbox messages."""
    result = repo.reject_period_request(
        db,
        request_id=request_id,
        actor_user_id=actor_user_id,
        company_id=company_id,
        reason=reason,
    )
    if not result.get("ok"):
        return result
    inbox_clear: dict[str, Any] = {"ok": False, "cleared": 0}
    try:
        from .messages_inbox import clear_period_handoff_messages

        inbox_clear = clear_period_handoff_messages(
            db,
            company_id=str(result.get("companyId") or ""),
            period=str(result.get("period") or ""),
            actor_user_id=str(actor_user_id or ""),
        )
    except Exception as exc:
        inbox_clear = {"ok": False, "error": str(exc)[:120], "cleared": 0}
    return {**result, "inboxCleared": inbox_clear}


def period_handoff_gate(db, *, company_id: str, period: str) -> dict[str, Any] | None:
    """
    Return error payload if Lohn must not pull yet; None if pull allowed.
    """
    period = normalize_period(period)
    company_id = require_company_id(company_id)
    if repo.is_period_confirmed_for_lohn(db, company_id=company_id, period=period):
        return None
    req = repo.get_period_request(db, company_id=company_id, period=period)
    if req and str(req.get("status") or "") == "rejected":
        return {
            "error": "period_rejected",
            "status": "rejected",
            "period": period,
            "companyId": company_id,
            "requestId": req.get("id"),
            "message": "Plattform hat die Übergabe für diese Periode abgelehnt",
            "hint": "POST /api/v2/accounting/period-request erneut senden",
        }
    return {
        "error": "period_not_confirmed",
        "status": (req or {}).get("status") or "missing",
        "period": period,
        "companyId": company_id,
        "requestId": (req or {}).get("id"),
        "message": "Warte auf Bestätigung der Plattform — danach werden Mitarbeiter und Abrechnungsdaten übergeben",
        "hint": "POST /api/v2/accounting/period-request then wait for Ops confirm",
    }


def _storage_dir(company_id: str, period: str) -> Path:
    try:
        from backend.server import DOCS_UPLOAD_DIR

        base = Path(DOCS_UPLOAD_DIR)
    except Exception:
        base = Path("backend") / "uploads" / "documents"
    target = base / "payroll" / company_id / period
    target.mkdir(parents=True, exist_ok=True)
    return target


def _delivery_pdf_filename(stmt: dict[str, Any], period: str) -> str:
    last = str(stmt.get("last_name") or "").strip()
    first = str(stmt.get("first_name") or "").strip()
    who = last or first or "Mitarbeiter"
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in who)[:40].strip("-") or "Mitarbeiter"
    per = str(period or stmt.get("period") or "periode").replace("/", "-")[:7]
    return f"Lohnabrechnung_{per}_{safe}.pdf"


def _meta_dict(stmt: dict[str, Any] | None) -> dict[str, Any]:
    try:
        meta = json.loads((stmt or {}).get("meta_json") or "{}")
    except Exception:
        meta = {}
    return meta if isinstance(meta, dict) else {}


def statement_delivery_locked(stmt: dict[str, Any] | None, meta: dict[str, Any] | None = None) -> bool:
    """True only after send/reject — a Stammdaten snapshot during review is not a lock."""
    status = str((stmt or {}).get("status") or "")
    if status in {"released", "rejected"}:
        return True
    blob = meta if isinstance(meta, dict) else _meta_dict(stmt)
    return bool(blob.get("deliveryLocked"))


def _lock_statement_delivery(db, stmt: dict[str, Any], now: str) -> dict[str, Any]:
    meta = _meta_dict(stmt)
    meta["deliveryLocked"] = True
    meta["lockedAt"] = meta.get("lockedAt") or now
    dumped = json.dumps(meta, ensure_ascii=False)
    db.execute(
        "UPDATE payroll_statements SET meta_json = ? WHERE id = ?",
        (dumped, stmt["id"]),
    )
    stmt["meta_json"] = dumped
    return meta


def resolve_statement_sheet(
    db,
    stmt: dict[str, Any],
    batch: dict[str, Any] | None = None,
    *,
    enrich: bool = True,
) -> dict[str, Any]:
    """Live Lohn payslip + DatevSheet. When enrich=False, return Lohn HTML unchanged."""
    from urllib.parse import quote as _q

    from .hours_service import get_employee_master_item
    from .lohn_sheet import (
        apply_sheet_chrome,
        build_payslip_print_html,
        enrich_payslip_with_master,
        fill_empty_sheet_fields,
        overlay_stammdaten,
        payslip_document_from_meta,
        payslip_to_sheet_data,
        snapshot_stammdaten,
        stammdaten_warnings,
    )
    from .platform_link import get_platform_link

    batch = batch if isinstance(batch, dict) else {}
    try:
        meta = json.loads(stmt.get("meta_json") or "{}")
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    payslip = payslip_document_from_meta(meta)
    job_id = str(meta.get("jobId") or "").strip()
    badge = str(meta.get("externalEmployeeId") or meta.get("employeeId") or stmt.get("badge_id") or "").strip()
    period = str(
        (payslip or {}).get("period") or stmt.get("period") or batch.get("period") or ""
    ).strip()[:7]
    company_id = str(stmt.get("company_id") or batch.get("company_id") or "")
    if not job_id and company_id and badge and period:
        job_id = f"{company_id}::{badge}::{period}"
    lock = meta.get("lockedStammdaten") if isinstance(meta.get("lockedStammdaten"), dict) else {}
    delivery_locked = statement_delivery_locked(stmt, meta)

    if job_id and not delivery_locked:
        link = get_platform_link(db)
        if link.get("configured"):
            fetched = _lohn_http_get(
                link,
                path=f"/v1/payroll/{_q(job_id, safe='')}/payslip",
                company_id=company_id,
                event="payroll.payslip.sheet",
            )
            body = fetched.get("body") if isinstance(fetched.get("body"), dict) else {}
            if isinstance(body.get("payslip"), dict):
                payslip = body["payslip"]
                period = str(payslip.get("period") or period).strip()[:7]

    master = None
    try:
        if company_id and not delivery_locked and enrich:
            master = get_employee_master_item(
                db,
                company_id=company_id,
                worker_id=str(stmt.get("worker_id") or ""),
                badge_id=badge,
            )
    except Exception:
        master = None
    if delivery_locked and lock:
        payslip = overlay_stammdaten(payslip, lock, overwrite=True)
    elif enrich:
        if lock:
            payslip = overlay_stammdaten(payslip, lock, overwrite=False)
        payslip = enrich_payslip_with_master(payslip, master)
    sheet_data = payslip_to_sheet_data(
        payslip or {},
        job={"period": period, "employee": (payslip or {}).get("employee") or {}},
    )
    warnings = [] if delivery_locked or not enrich else stammdaten_warnings(sheet_data, master)
    html_doc = ""
    lohn_html = False
    if job_id and not delivery_locked:
        link = get_platform_link(db)
        if link.get("configured"):
            printed = _lohn_http_get(
                link,
                path=f"/v1/payroll/{_q(job_id, safe='')}/payslip-print",
                company_id=company_id,
                event="payroll.payslip.print",
            )
            pbody = printed.get("body") if isinstance(printed.get("body"), dict) else {}
            if printed.get("ok") and isinstance(pbody.get("html"), str) and len(pbody["html"]) > 200:
                # Forward Lohn DatevSheet HTML exactly — do not inject platform fields.
                html_doc = pbody["html"]
                lohn_html = True
                if enrich:
                    html_doc = fill_empty_sheet_fields(html_doc, sheet_data)
                html_doc = apply_sheet_chrome(html_doc, theme="light")
    if not html_doc:
        html_doc = build_payslip_print_html(
            payslip or {},
            job={"period": period, "employee": (payslip or {}).get("employee") or {}},
            theme="light",
        )
    return {
        "payslip": payslip or {},
        "sheet_data": sheet_data,
        "period": period,
        "job_id": job_id,
        "html": html_doc,
        "company_id": company_id,
        "lohnHtml": lohn_html,
        "warnings": warnings,
        "lock": lock,
        "deliveryLocked": delivery_locked,
    }


def ensure_statement_delivery_pdf(
    db,
    stmt: dict[str, Any],
    batch: dict[str, Any] | None = None,
    *,
    force: bool = False,
    html_override: str | None = None,
) -> dict[str, Any]:
    """Prefer the original WorkPass Lohn PDF; only remake when none exists."""
    from .lohn_sheet_pdf import (
        is_exact_lohn_pdf_source,
        is_high_fidelity_pdf_source,
        render_datev_sheet_pdf_with_source,
    )

    try:
        existing_meta = json.loads(stmt.get("meta_json") or "{}")
    except Exception:
        existing_meta = {}
    if not isinstance(existing_meta, dict):
        existing_meta = {}
    existing_source = str(existing_meta.get("pdfSource") or "")
    existing_size = int(stmt.get("file_size") or 0)
    path = str(stmt.get("file_path") or "").strip()
    # Never replace the authentic Lohn PDF / html2canvas capture with a remake.
    if (
        not force
        and is_exact_lohn_pdf_source(existing_source)
        and existing_size >= 8000
        and path
        and Path(path).is_file()
    ):
        return {
            "ok": True,
            "path": path,
            "fileSize": existing_size,
            "filename": stmt.get("filename") or "",
            "period": str(stmt.get("period") or ""),
            "pdfSource": existing_source,
            "skipped": "exact_lohn",
        }
    # Locked high-fidelity deliveries stay immutable.
    already_html = is_high_fidelity_pdf_source(existing_source) and existing_size >= 12000
    if not force and statement_delivery_locked(stmt, existing_meta) and already_html:
        if path and Path(path).is_file():
            return {
                "ok": True,
                "path": path,
                "fileSize": existing_size,
                "filename": stmt.get("filename") or "",
                "period": str(stmt.get("period") or ""),
                "skipped": "locked",
            }
    if (
        not force
        and not statement_delivery_locked(stmt, existing_meta)
        and is_high_fidelity_pdf_source(existing_source)
        and existing_size >= 12000
        and not str(html_override or "").strip()
        and path
        and Path(path).is_file()
    ):
        return {
            "ok": True,
            "path": path,
            "fileSize": existing_size,
            "filename": stmt.get("filename") or "",
            "period": str(stmt.get("period") or ""),
            "pdfSource": existing_source,
            "skipped": "cached",
        }

    resolved = resolve_statement_sheet(db, stmt, batch, enrich=False)
    period = str(resolved.get("period") or stmt.get("period") or (batch or {}).get("period") or "unknown")[:7]
    html_doc = str(html_override or "").strip() or str(resolved.get("html") or "")
    pdf_bytes, pdf_source = render_datev_sheet_pdf_with_source(
        resolved.get("sheet_data") or {}, html=html_doc
    )
    if not pdf_bytes.startswith(b"%PDF"):
        return {"ok": False, "error": "pdf_render_failed"}
    dest = _storage_dir(str(stmt.get("company_id") or resolved.get("company_id") or "unknown"), period)
    filename = _delivery_pdf_filename(stmt, period)
    path = str(dest / f"{stmt.get('id')}_{filename}")
    Path(path).write_bytes(pdf_bytes)
    try:
        meta = json.loads(stmt.get("meta_json") or "{}")
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    meta["pdfSource"] = pdf_source
    meta["documentPeriod"] = period
    already_locked = statement_delivery_locked(stmt, meta)
    if not already_locked:
        from .lohn_sheet import snapshot_stammdaten

        meta["lockedStammdaten"] = snapshot_stammdaten(resolved.get("sheet_data"), resolved.get("payslip"))
        meta["stammdatenWarnings"] = list(resolved.get("warnings") or [])
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        """
        UPDATE payroll_statements
        SET file_path = ?, file_size = ?, filename = ?, meta_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (path, len(pdf_bytes), filename, json.dumps(meta, ensure_ascii=False), now, stmt["id"]),
    )
    db.commit()
    stmt["file_path"] = path
    stmt["file_size"] = len(pdf_bytes)
    stmt["filename"] = filename
    stmt["meta_json"] = json.dumps(meta, ensure_ascii=False)
    if str(stmt.get("worker_document_id") or "").strip():
        _refresh_worker_document_pdf(
            db,
            stmt,
            file_path=path,
            file_size=len(pdf_bytes),
            filename=filename,
            period=period,
        )
    return {
        "ok": True,
        "path": path,
        "fileSize": len(pdf_bytes),
        "filename": filename,
        "period": period,
        "pdfSource": pdf_source,
    }


def ingest_statements(
    db,
    *,
    company_id: str,
    period: str,
    statements: list[dict[str, Any]],
    external_ref: str = "",
    notes: str = "",
) -> dict[str, Any]:
    try:
        company_id = require_company_id(company_id)
    except ValueError:
        return {"ok": False, "error": "company_id_required"}
    period = normalize_period(period)
    if not statements:
        return {"ok": False, "error": "statements_required"}
    batch_id = repo.create_statement_batch(
        db, company_id=company_id, period=period, external_ref=external_ref, notes=notes
    )
    created: list[str] = []
    errors: list[dict[str, Any]] = []
    for idx, item in enumerate(statements):
        item_company = str(
            item.get("companyId") or item.get("company_id") or (item.get("company") or {}).get("id") or ""
        ).strip()
        if item_company and item_company != company_id:
            errors.append({"index": idx, "error": "company_id_mismatch", "companyId": item_company})
            continue
        if not item_company:
            # company.id is mandatory on every payroll row — reject if caller omitted it
            errors.append({"index": idx, "error": "company_id_required"})
            continue
        worker_raw = str(
            item.get("workerId") or item.get("worker_id") or item.get("employeeId") or item.get("employee_id") or ""
        ).strip()
        if not worker_raw:
            errors.append({"index": idx, "error": "employee_id_required"})
            continue
        from .messages_inbox import resolve_company_worker

        resolved = resolve_company_worker(db, company_id, worker_raw)
        matched_by = ""
        match_confidence = ""
        stmt_status = "pending"
        if resolved:
            worker_id = str(resolved.get("id") or "").strip()
            matched_by = str(resolved.get("matchedBy") or "id")
            match_confidence = str(resolved.get("matchConfidence") or "exact")
        else:
            # Keep PDF for human assignment — never auto-release unmatched
            worker_id = ""
            matched_by = ""
            match_confidence = ""
            stmt_status = "unmatched"
        try:
            storage_key = str(item.get("storageKey") or "").strip() or payroll_storage_key(
                company_id=company_id,
                employee_id=worker_id or worker_raw,
                period=period,
            )
        except ValueError as exc:
            errors.append({"index": idx, "error": str(exc)})
            continue
        pdf_b64 = item.get("pdfBase64") or item.get("pdf_base64") or ""
        doc_type = resolve_payroll_doc_type(item, item.get("document") if isinstance(item.get("document"), dict) else {})
        filename = str(
            item.get("filename")
            or _default_payroll_filename(doc_type, period, worker_id or worker_raw)
        ).strip()
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"
        file_path = ""
        file_size = 0
        if pdf_b64:
            try:
                raw = base64.b64decode(pdf_b64)
            except Exception:
                errors.append({"index": idx, "error": "invalid_pdf_base64", "employeeId": worker_raw})
                continue
            if len(raw) < 20 or not raw.startswith(b"%PDF"):
                errors.append({"index": idx, "error": "not_a_pdf", "employeeId": worker_raw})
                continue
            if len(raw) > 15 * 1024 * 1024:
                errors.append({"index": idx, "error": "pdf_too_large", "employeeId": worker_raw})
                continue
            dest_dir = _storage_dir(company_id, period)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"{(worker_id or 'unmatched')}_{secrets.token_hex(4)}.pdf"
            dest.write_bytes(raw)
            file_path = str(dest)
            file_size = len(raw)
        invoice_number = str(item.get("invoiceNumber") or item.get("invoice_number") or "").strip()
        invoice_key = ""
        if invoice_number:
            try:
                invoice_key = invoice_storage_key(company_id=company_id, invoice_number=invoice_number)
            except ValueError as exc:
                errors.append({"index": idx, "error": str(exc)})
                continue
        meta = {k: v for k, v in item.items() if k not in {"pdfBase64", "pdf_base64"}}
        meta["storageKey"] = storage_key
        meta["companyId"] = company_id
        meta["employeeId"] = worker_id or worker_raw
        meta["externalEmployeeId"] = worker_raw
        meta["matchedBy"] = matched_by
        meta["matchConfidence"] = match_confidence
        meta["docType"] = doc_type
        meta["documentType"] = doc_type
        if file_path and file_size:
            meta["pdfSource"] = str(item.get("pdfSource") or meta.get("pdfSource") or "lohn_original")
        else:
            meta["pdfSource"] = str(item.get("pdfSource") or meta.get("pdfSource") or "pending_lohn_capture")
        if invoice_key:
            meta["invoiceStorageKey"] = invoice_key
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
            external_ref=str(item.get("externalRef") or item.get("external_ref") or storage_key)[:120],
            meta=meta,
            status=stmt_status,
            matched_by=matched_by,
            match_confidence=match_confidence,
        )
        created.append(stmt_id)
        if stmt_status == "unmatched":
            errors.append(
                {
                    "index": idx,
                    "error": "worker_unmatched",
                    "employeeId": worker_raw,
                    "statementId": stmt_id,
                    "hint": "PDF gespeichert — Mitarbeiter manuell zuweisen",
                }
            )
    return {
        "ok": True,
        "batchId": batch_id,
        "companyId": company_id,
        "period": period,
        "status": "pending_approval",
        "createdCount": len(created),
        "statementIds": created,
        "errors": errors,
        "tenantIsolation": "companyId::employeeId::period",
    }


def _eur(value: Any) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if n < 0 else ""
    n = abs(n)
    whole = int(n)
    cents = int(round((n - whole) * 100))
    if cents == 100:
        whole += 1
        cents = 0
    whole_s = f"{whole:,}".replace(",", ".")
    return f"{sign}{whole_s},{cents:02d} €"


def _generate_payslip_pdf_base64(
    *,
    employee_name: str,
    employee_id: str,
    company_name: str,
    period: str,
    gross: Any = None,
    net: Any = None,
    title: str = "",
    document: dict[str, Any] | None = None,
) -> str:
    """
    Render a German Entgeltabrechnung-style PDF from Lohn payslip JSON.
    Lohn itself only has client-side html2canvas PDFs — no server PDF bytes.
    """
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    doc = document if isinstance(document, dict) else {}
    totals = doc.get("totals") if isinstance(doc.get("totals"), dict) else {}
    bank = doc.get("bank") if isinstance(doc.get("bank"), dict) else {}
    attendance = doc.get("attendance") if isinstance(doc.get("attendance"), dict) else {}
    wage_items = doc.get("wageItems") or doc.get("lines") or doc.get("lohnarten") or []
    if not isinstance(wage_items, list):
        wage_items = []
    emp = doc.get("employee") if isinstance(doc.get("employee"), dict) else {}
    co = doc.get("company") if isinstance(doc.get("company"), dict) else {}

    employee_name = str(employee_name or emp.get("name") or "").strip()
    employee_id = str(employee_id or emp.get("id") or emp.get("badgeId") or "").strip()
    company_name = str(company_name or co.get("name") or "").strip()
    period = str(period or doc.get("period") or "").strip()
    if gross is None:
        gross = totals.get("gross")
    if net is None:
        net = totals.get("net")

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    left = 16 * mm
    right = width - 16 * mm
    y = height - 16 * mm

    def line(x1: float, y1: float, x2: float, y2: float, w: float = 0.6) -> None:
        c.setStrokeColor(colors.HexColor("#111111"))
        c.setLineWidth(w)
        c.line(x1, y1, x2, y2)

    def text(x: float, yy: float, s: str, *, size: float = 9, bold: bool = False, color="#111111") -> None:
        c.setFillColor(colors.HexColor(color))
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x, yy, str(s)[:110])

    def text_right(x: float, yy: float, s: str, *, size: float = 9, bold: bool = False) -> None:
        c.setFillColor(colors.HexColor("#111111"))
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawRightString(x, yy, str(s)[:40])

    # Header
    text(left, y, company_name or "Arbeitgeber", size=12, bold=True)
    text_right(right, y, "Entgeltabrechnung", size=12, bold=True)
    y -= 14
    text(left, y, f"Mitarbeiter: {employee_name or '—'}", size=10)
    text_right(right, y, f"Periode {period or '—'}", size=10, bold=True)
    y -= 12
    text(left, y, f"Personal-/Badge-Nr.: {employee_id or '—'}", size=9, color="#333333")
    if attendance:
        hours = attendance.get("hours") or attendance.get("totalHours") or attendance.get("workedHours")
        days = attendance.get("days") or attendance.get("workedDays")
        bits = []
        if hours is not None:
            bits.append(f"Stunden: {hours}")
        if days is not None:
            bits.append(f"Tage: {days}")
        if bits:
            text_right(right, y, " · ".join(bits), size=9)
    y -= 8
    line(left, y, right, y, 1.1)
    y -= 16

    # Wage items table
    text(left, y, "Bezüge / Lohnarten", size=10, bold=True)
    y -= 12
    cols = [left, left + 28 * mm, left + 95 * mm, left + 118 * mm, left + 140 * mm]
    headers = ["Code", "Bezeichnung", "Menge", "Faktor", "Betrag"]
    for i, h in enumerate(headers):
        (text if i < 2 else text_right)(cols[i] if i < 2 else (cols[i] + (22 * mm if i > 2 else 18 * mm)), y, h, size=8, bold=True)
    y -= 4
    line(left, y, right, y, 0.5)
    y -= 12
    if not wage_items and gross is not None:
        wage_items = [{"code": "STD", "label": "Stundenlohn", "quantity": "", "factor": "", "amount": gross}]
    for item in wage_items[:24]:
        if not isinstance(item, dict):
            continue
        if y < 40 * mm:
            c.showPage()
            y = height - 20 * mm
        code = str(item.get("code") or item.get("lohnart") or "")
        label = str(item.get("label") or item.get("name") or item.get("bezeichnung") or "")
        qty = item.get("quantity") if item.get("quantity") is not None else item.get("menge")
        factor = item.get("factor") if item.get("factor") is not None else item.get("satz")
        amount = item.get("amount") if item.get("amount") is not None else item.get("betrag")
        text(cols[0], y, code, size=8)
        text(cols[1], y, label or ("Stundenlohn" if code == "STD" else "—"), size=8)
        text_right(cols[2] + 18 * mm, y, "" if qty in (None, "") else str(qty), size=8)
        text_right(cols[3] + 18 * mm, y, "" if factor in (None, "") else _eur(factor).replace(" €", ""), size=8)
        text_right(right, y, _eur(amount), size=8)
        y -= 11

    y -= 4
    line(left, y, right, y, 0.5)
    y -= 14

    # Totals block
    text(left, y, "Abrechnung Brutto / Netto", size=10, bold=True)
    y -= 14

    def row(label: str, value: Any, *, bold: bool = False, emphasize: bool = False) -> None:
        nonlocal y
        if y < 28 * mm:
            c.showPage()
            y = height - 20 * mm
        text(left, y, label, size=9, bold=bold)
        text_right(right, y, _eur(value), size=9, bold=bold or emphasize)
        y -= 12

    row("Abrechnungs-Brutto", gross if gross is not None else totals.get("gross"), bold=True)
    row("Lohnsteuer", totals.get("payrollTax"))
    row("Solidaritätszuschlag", totals.get("solidarity"))
    row("Kirchensteuer", totals.get("churchTax"))
    row("Krankenversicherung", totals.get("health"))
    row("Rentenversicherung", totals.get("pension"))
    row("Pflegeversicherung", totals.get("care"))
    row("Arbeitslosenversicherung", totals.get("unemployment"))
    row("SV gesamt (AN)", totals.get("svTotal"))
    y -= 2
    line(left, y, right, y, 0.8)
    y -= 14
    row("Abrechnungs-Netto", net if net is not None else totals.get("net"), bold=True, emphasize=True)
    y -= 6
    row("AG-Anteil SV", totals.get("employerShare"))
    row("Umlagen gesamt", totals.get("umlagenTotal"))

    y -= 8
    line(left, y, right, y, 0.5)
    y -= 14
    text(left, y, "Bankverbindung", size=10, bold=True)
    y -= 12
    iban = str(bank.get("iban") or bank.get("IBAN") or "—")
    holder = str(bank.get("holder") or bank.get("accountHolder") or bank.get("name") or "—")
    bank_name = str(bank.get("bankName") or bank.get("name") or bank.get("bank") or "")
    text(left, y, f"Kontoinhaber: {holder}", size=9)
    y -= 11
    text(left, y, f"IBAN: {iban}", size=9)
    if bank_name:
        y -= 11
        text(left, y, f"Bank: {bank_name}", size=9)

    y = 18 * mm
    text(
        left,
        y,
        "Entgeltabrechnung nach § 108 Abs. 3 GewO · Datenquelle: WorkPass Lohn",
        size=7,
        color="#555555",
    )
    c.showPage()
    c.save()
    return base64.b64encode(buf.getvalue()).decode("ascii")


def lohn_delivery_to_statement(delivery: dict[str, Any] | None) -> dict[str, Any] | None:
    """Map Lohn platform.employee.delivery.v1 (payslip / tax docs) → ingest_statements row."""
    if not isinstance(delivery, dict):
        return None
    dtype = str(delivery.get("type") or "").strip().lower()
    kind = str(delivery.get("kind") or "").strip().lower()
    if dtype in {"invoice", "invoices"}:
        return None
    # Accept classic payslip types and any platform employee delivery (tax/earnings PDFs).
    if dtype and dtype not in {"payslip", "payroll", "statement", "document"}:
        if kind != "platform.employee.delivery.v1":
            # Still allow known payroll document type names without the kind field.
            if not is_payroll_doc_type(dtype) and resolve_payroll_doc_type(delivery) == "lohnabrechnung" and dtype not in {
                "lohnsteuerbescheinigung",
                "verdienstabrechnung",
                "verdienstbescheinigung",
                "tax_certificate",
                "earnings_statement",
            }:
                return None
    company = delivery.get("company") if isinstance(delivery.get("company"), dict) else {}
    employee = delivery.get("employee") if isinstance(delivery.get("employee"), dict) else {}
    summary = delivery.get("summary") if isinstance(delivery.get("summary"), dict) else {}
    document = delivery.get("document") if isinstance(delivery.get("document"), dict) else {}
    doc_emp = document.get("employee") if isinstance(document.get("employee"), dict) else {}
    doc_co = document.get("company") if isinstance(document.get("company"), dict) else {}
    totals = document.get("totals") if isinstance(document.get("totals"), dict) else {}

    company_id = str(
        company.get("id") or doc_co.get("id") or delivery.get("companyId") or ""
    ).strip()
    employee_id = str(
        employee.get("id")
        or employee.get("badgeId")
        or doc_emp.get("id")
        or doc_emp.get("badgeId")
        or delivery.get("employeeId")
        or ""
    ).strip()
    if not company_id or not employee_id:
        return None
    period = str(
        delivery.get("period") or document.get("period") or summary.get("period") or ""
    ).strip()[:7]
    if not period:
        return None
    try:
        period = normalize_period(period)
    except ValueError:
        return None

    gross = summary.get("gross")
    if gross is None:
        gross = totals.get("gross")
    net = summary.get("net")
    if net is None:
        net = totals.get("net")
    hours = (
        document.get("hours")
        or document.get("totalHours")
        or (document.get("attendance") or {}).get("hours")
        or (document.get("attendance") or {}).get("totalHours")
        or summary.get("hours")
        or 0
    )
    hourly = document.get("hourlyRate") or document.get("hourly_rate") or 0
    if not hourly:
        for wi in document.get("wageItems") or []:
            if isinstance(wi, dict) and wi.get("factor") and (wi.get("code") or "") in {"STD", "STDLOHN", ""}:
                try:
                    hourly = float(wi.get("factor") or 0)
                    break
                except (TypeError, ValueError):
                    pass
    name = str(employee.get("name") or doc_emp.get("name") or "").strip()
    company_name = str(company.get("name") or doc_co.get("name") or "").strip()
    doc_type = resolve_payroll_doc_type(delivery, document, summary)
    title = str(
        delivery.get("title")
        or f"{doc_type_label(doc_type, 'de')} {period}"
    ).strip()
    delivery_id = str(delivery.get("deliveryId") or delivery.get("jobId") or "").strip()
    job_id = str(delivery.get("jobId") or document.get("jobId") or "").strip()
    pdf_b64 = (
        delivery.get("pdfBase64")
        or delivery.get("pdf_base64")
        or document.get("pdfBase64")
        or document.get("pdf_base64")
        or ""
    )
    # Never invent a platform stub PDF — employee must get the real WorkPass Lohn document.
    return {
        "companyId": company_id,
        "employeeId": employee_id,
        "workerId": employee_id,
        "period": period,
        "hours": float(hours or 0),
        "hourlyRate": float(hourly or 0),
        "grossAmount": float(gross or 0) if gross is not None else 0,
        "netAmount": float(net) if net is not None else None,
        "currency": str(summary.get("currency") or document.get("currency") or "EUR"),
        "filename": str(delivery.get("filename") or f"WorkPass-Lohn-{doc_type}-{period}.pdf"),
        "pdfBase64": pdf_b64,
        "externalRef": delivery_id[:120],
        "employeeName": name,
        "companyName": company_name,
        "deliveryId": delivery_id,
        "jobId": job_id or str(delivery.get("jobId") or ""),
        "source": "lohn_delivery",
        "pdfSource": "lohn_original" if pdf_b64 else "pending_lohn_capture",
        "document": document or None,
        "docType": doc_type,
        "documentType": doc_type,
        "title": title,
    }


def statements_from_lohn_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract ingestable statements from webhook/pull payloads (statements or delivery)."""
    if not isinstance(data, dict):
        return []
    out: list[dict[str, Any]] = []
    raw_list = data.get("statements") or data.get("items") or data.get("payslips") or []
    if isinstance(data.get("statement"), dict):
        raw_list = [data["statement"]]
    if isinstance(raw_list, list):
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            # Already platform-shaped
            if item.get("pdfBase64") or item.get("pdf_base64") or item.get("employeeId") or item.get("workerId"):
                if not (item.get("companyId") or item.get("company_id")):
                    cid = str(
                        data.get("companyId")
                        or data.get("company_id")
                        or (data.get("company") or {}).get("id")
                        or ""
                    ).strip()
                    if cid:
                        item = {**item, "companyId": cid}
                doc_type = resolve_payroll_doc_type(
                    item,
                    item.get("document") if isinstance(item.get("document"), dict) else {},
                    data,
                )
                item = {**item, "docType": item.get("docType") or doc_type, "documentType": item.get("documentType") or doc_type}
                out.append(item)
                continue
            converted = lohn_delivery_to_statement(item)
            if converted:
                out.append(converted)

    deliveries: list[Any] = []
    if isinstance(data.get("delivery"), dict):
        deliveries.append(data["delivery"])
    if isinstance(data.get("deliveries"), list):
        deliveries.extend(data["deliveries"])
    for d in deliveries:
        converted = lohn_delivery_to_statement(d if isinstance(d, dict) else None)
        if converted:
            out.append(converted)
    return out


def _lohn_http_get(link: dict[str, Any], *, path: str, company_id: str = "", event: str = "delivery.pull") -> dict[str, Any]:
    from .platform_link import primary_lohn_api_key, resolve_lohn_api_keys

    base = str(link.get("base_url") or "").rstrip("/")
    keys = resolve_lohn_api_keys(link) or []
    if not keys:
        primary = primary_lohn_api_key(link)
        if primary:
            keys = [primary]
    if not base:
        return {"ok": False, "error": "lohn_base_url_missing"}
    if not keys:
        return {"ok": False, "error": "master_api_key_missing"}
    if not path.startswith("/"):
        path = "/" + path
    url = f"{base}{path}"
    last: dict[str, Any] = {"ok": False, "error": "lohn_unauthorized"}
    for key_try in keys:
        ts = str(int(time.time()))
        headers = {
            "Accept": "application/json",
            "User-Agent": "SUPPIX-WorkPass-Lohn-Bridge/1.0",
            "X-WorkPass-Key": key_try,
            "Authorization": f"Bearer {key_try}",
            "X-WorkPass-Master-Key": key_try,
            "X-WorkPass-Company-Id": company_id,
            "X-Suppix-Timestamp": ts,
            "X-Suppix-Event": event,
            "X-Suppix-Product": "WorkPass Lohn",
            "X-Suppix-Signature": sign_payload(key_try, timestamp=ts, body=b""),
        }
        req = urlrequest.Request(url, headers=headers, method="GET")
        try:
            with urlrequest.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(raw) if raw else {}
                except Exception:
                    parsed = {"raw": raw[:500]}
                return {"ok": True, "status": int(resp.status), "url": url, "body": parsed}
        except urlerror.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read()[:400].decode("utf-8", errors="replace")
            except Exception:
                detail = str(exc)
            last = {"ok": False, "status": int(exc.code), "url": url, "error": detail or str(exc)[:200]}
            if int(exc.code) not in {401, 403}:
                return last
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200], "url": url}
    return last


def pull_payslips_from_lohn(
    db,
    *,
    company_id: str,
    period: str | None = None,
    redeliver: bool = False,
) -> dict[str, Any]:
    """
    Pull released payslips from WorkPass Lohn into pending_approval batches.

    1) Optional POST /v1/payroll/deliver-period (re-enqueue released jobs)
    2) GET /v1/delivery/pending?companyId=
    3) ingest + ACK each payslip delivery
    """
    from urllib.parse import urlencode

    from .company_opt_in import is_workpass_lohn_enabled
    from .platform_link import _post_lohn_json, get_platform_link

    try:
        company_id = require_company_id(company_id)
    except ValueError:
        return {"ok": False, "error": "company_id_required"}
    if not is_workpass_lohn_enabled(db, company_id):
        return {"ok": False, "error": "workpass_lohn_disabled", "skipped": True}

    link = get_platform_link(db)
    if not link.get("enabled") or not str(link.get("base_url") or "").strip():
        return {"ok": False, "error": "platform_link_disabled"}

    period_n = ""
    if period:
        try:
            period_n = normalize_period(str(period).strip()[:7])
        except ValueError:
            return {"ok": False, "error": "invalid_period"}

    redeliver_result: dict[str, Any] | None = None
    if redeliver or period_n:
        _db_commit(db)
        redeliver_result = _post_lohn_json(
            link,
            path="/v1/payroll/deliver-period",
            body={
                "companyId": company_id,
                "period": period_n or None,
                "reason": "suppix_pull_payslips",
            },
            event="payroll.deliver-period",
            timeout=45,
        )

    q = urlencode({"companyId": company_id})
    _db_commit(db)
    fetched = _lohn_http_get(
        link,
        path=f"/v1/delivery/pending?{q}",
        company_id=company_id,
        event="delivery.pending",
    )
    if not fetched.get("ok"):
        return {
            "ok": False,
            "error": fetched.get("error") or "delivery_pull_failed",
            "pull": fetched,
            "redeliver": redeliver_result,
        }

    body = fetched.get("body") if isinstance(fetched.get("body"), dict) else {}
    deliveries = body.get("deliveries") or body.get("items") or []
    if not isinstance(deliveries, list):
        deliveries = []

    by_period: dict[str, list[dict[str, Any]]] = {}
    skipped: list[dict[str, Any]] = []
    for d in deliveries:
        if not isinstance(d, dict):
            continue
        if str(d.get("type") or "").lower() in {"invoice", "invoices"}:
            skipped.append({"deliveryId": d.get("deliveryId"), "reason": "invoice_skipped"})
            continue
        # Prefer full payroll JSON from Lohn (delivery.document can be thin).
        job_id = str(d.get("jobId") or "").strip()
        dtype_l = str(d.get("type") or d.get("documentType") or d.get("docType") or "").lower()
        is_payslipish = resolve_payroll_doc_type(d) in {"lohnabrechnung", "gehaltsabrechnung"} or dtype_l in {
            "payslip",
            "payroll",
            "statement",
            "",
        }
        if job_id and is_payslipish:
            from urllib.parse import quote as _q

            _db_commit(db)
            full = _lohn_http_get(
                link,
                path=f"/v1/payroll/{_q(job_id, safe='')}/payslip",
                company_id=company_id,
                event="payroll.payslip",
            )
            body_full = full.get("body") if isinstance(full.get("body"), dict) else {}
            payslip = body_full.get("payslip") if isinstance(body_full.get("payslip"), dict) else None
            if payslip:
                d = {**d, "document": payslip}
        stmt = lohn_delivery_to_statement(d)
        if not stmt:
            skipped.append({"deliveryId": d.get("deliveryId"), "reason": "unmapped"})
            continue
        if period_n and stmt.get("period") != period_n:
            skipped.append({"deliveryId": d.get("deliveryId"), "reason": "period_filter", "period": stmt.get("period")})
            continue
        if str(stmt.get("companyId") or "") != company_id:
            skipped.append({"deliveryId": d.get("deliveryId"), "reason": "company_mismatch"})
            continue
        by_period.setdefault(str(stmt["period"]), []).append(stmt)

    batches: list[dict[str, Any]] = []
    acked: list[str] = []
    ack_errors: list[dict[str, Any]] = []
    for per, stmts in by_period.items():
        ingest = ingest_statements(
            db,
            company_id=company_id,
            period=per,
            statements=stmts,
            external_ref=f"lohn-pull-{per}",
            notes="pull /v1/delivery/pending",
        )
        batches.append(ingest)
        if not ingest.get("ok"):
            continue
        for stmt in stmts:
            did = str(stmt.get("deliveryId") or "").strip()
            if not did:
                continue
            _db_commit(db)
            ack = _post_lohn_json(
                link,
                path=f"/v1/delivery/{did}/ack",
                body={"via": "suppix_pull", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                event="delivery.ack",
                timeout=15,
            )
            if ack.get("ok"):
                acked.append(did)
            else:
                ack_errors.append({"deliveryId": did, "error": ack.get("error") or ack.get("status")})

    created = sum(int(b.get("createdCount") or 0) for b in batches)
    return {
        "ok": True,
        "companyId": company_id,
        "period": period_n or None,
        "pendingCount": len(deliveries),
        "createdCount": created,
        "batches": batches,
        "acked": acked,
        "ackErrors": ack_errors,
        "skipped": skipped,
        "redeliver": redeliver_result,
        "status": "pending_approval",
        "message": (
            f"{created} Lohnabrechnung(en) übernommen — bitte prüfen und freigeben."
            if created
            else "Keine neuen Abrechnungen in der Lohn-Warteschlange."
        ),
        "note": "Never auto-approve payslips to employees",
    }


def refresh_pending_payslip_pdfs_from_lohn(
    db,
    *,
    company_id: str,
    period: str | None = None,
) -> dict[str, Any]:
    """
    Rebuild pending statement PDFs from live Lohn payslip JSON
    (replaces earlier stub one-pagers).
    """
    from urllib.parse import quote as _q

    from .company_opt_in import is_workpass_lohn_enabled
    from .platform_link import get_platform_link

    try:
        company_id = require_company_id(company_id)
    except ValueError:
        return {"ok": False, "error": "company_id_required"}
    if not is_workpass_lohn_enabled(db, company_id):
        return {"ok": False, "error": "workpass_lohn_disabled", "skipped": True}
    link = get_platform_link(db)
    if not link.get("enabled") or not str(link.get("base_url") or "").strip():
        return {"ok": False, "error": "platform_link_disabled"}

    period_n = ""
    if period:
        try:
            period_n = normalize_period(str(period).strip()[:7])
        except ValueError:
            return {"ok": False, "error": "invalid_period"}

    ensure_accounting_schema(db)
    sql = """
        SELECT s.*, w.badge_id, w.first_name, w.last_name
        FROM payroll_statements s
        JOIN payroll_statement_batches b ON b.id = s.batch_id
        LEFT JOIN workers w ON w.id = s.worker_id
        WHERE s.company_id = ?
          AND b.status = 'pending_approval'
          AND s.status IN ('pending', 'unmatched')
    """
    args: list[Any] = [company_id]
    if period_n:
        sql += " AND s.period = ?"
        args.append(period_n)
    rows = db.execute(sql, tuple(args)).fetchall()

    updated: list[str] = []
    errors: list[dict[str, Any]] = []
    for row in rows:
        stmt = dict(row)
        stmt_id = str(stmt.get("id") or "")
        try:
            meta = json.loads(stmt.get("meta_json") or "{}")
        except Exception:
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        job_id = str(meta.get("jobId") or "").strip()
        badge = str(
            meta.get("externalEmployeeId")
            or meta.get("employeeId")
            or stmt.get("badge_id")
            or ""
        ).strip()
        per = str(stmt.get("period") or "").strip()
        if not job_id and badge and per:
            job_id = f"{company_id}::{badge}::{per}"
        if not job_id:
            errors.append({"statementId": stmt_id, "error": "job_id_missing"})
            continue
        _db_commit(db)
        fetched = _lohn_http_get(
            link,
            path=f"/v1/payroll/{_q(job_id, safe='')}/payslip",
            company_id=company_id,
            event="payroll.payslip.refresh",
        )
        body = fetched.get("body") if isinstance(fetched.get("body"), dict) else {}
        payslip = body.get("payslip") if isinstance(body.get("payslip"), dict) else None
        if not payslip:
            errors.append({"statementId": stmt_id, "jobId": job_id, "error": "payslip_not_found"})
            continue
        display = f"{stmt.get('first_name') or ''} {stmt.get('last_name') or ''}".strip()
        # Keep live Lohn JSON for the studio sheet; never write ReportLab stubs here.
        # Exact Chromium PDF is built on download / An Mitarbeiter senden.
        meta = {
            **meta,
            "jobId": job_id,
            "document": payslip,
            "pdfSource": "pending_datev_sheet",
        }
        net_v = (payslip.get("totals") or {}).get("net")
        db.execute(
            """
            UPDATE payroll_statements
            SET meta_json = ?,
                gross_amount = ?, net_amount = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                json.dumps(meta, ensure_ascii=False),
                float((payslip.get("totals") or {}).get("gross") or stmt.get("gross_amount") or 0),
                float(net_v) if net_v is not None else stmt.get("net_amount"),
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                stmt_id,
            ),
        )
        updated.append(stmt_id)
    try:
        db.commit()
    except Exception:
        pass
    return {
        "ok": True,
        "companyId": company_id,
        "updatedCount": len(updated),
        "updated": updated,
        "errors": errors,
        "message": f"{len(updated)} Abrechnung(en) aus WorkPass Lohn aktualisiert (PDF folgt beim Versand).",
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
    doc_type: str = "lohnabrechnung",
) -> str:
    doc_id = f"doc-{uuid.uuid4().hex[:12]}"
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    notes = f"payroll_period={period}"
    stored_path = file_path
    canonical_type = resolve_payroll_doc_type({"docType": doc_type})
    try:
        src = Path(str(file_path or ""))
        if src.is_file():
            dest_dir = _storage_dir(company_id, period) / "delivered"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"{doc_id}_{src.name}"
            shutil.copy2(src, dest)
            stored_path = str(dest)
            file_size = dest.stat().st_size
    except Exception:
        stored_path = file_path
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
                canonical_type,
                filename,
                stored_path,
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
            (
                doc_id,
                worker_id,
                company_id,
                canonical_type,
                filename,
                stored_path,
                file_size,
                uploaded_by_user_id,
                now,
                notes,
            ),
        )
    return doc_id


def _worker_document_delivery_ok(db, *, doc_id: str, worker_id: str) -> bool:
    """True when the worker can actually open the attached payroll document file."""
    doc_id = str(doc_id or "").strip()
    worker_id = str(worker_id or "").strip()
    if not doc_id or not worker_id:
        return False
    placeholders = ",".join("?" for _ in sorted(WORKER_PAYROLL_DOC_TYPES))
    try:
        row = db.execute(
            f"""
            SELECT id, worker_id, file_path, file_size
            FROM worker_documents
            WHERE id = ? AND worker_id = ? AND doc_type IN ({placeholders})
            """,
            (doc_id, worker_id, *sorted(WORKER_PAYROLL_DOC_TYPES)),
        ).fetchone()
    except Exception:
        return False
    if not row:
        return False
    path = str(row["file_path"] or "").strip()
    if not path:
        return False
    p = Path(path)
    if not p.is_file():
        # Some installs store paths relative to repo/backend root.
        for base in (Path.cwd(), Path(__file__).resolve().parents[3], Path("backend")):
            cand = base / path
            if cand.is_file():
                return int(row["file_size"] or 0) > 500 or cand.stat().st_size > 500
        return False
    return int(row["file_size"] or 0) > 500 or p.stat().st_size > 500


def _refresh_worker_document_pdf(
    db,
    stmt: dict[str, Any],
    *,
    file_path: str,
    file_size: int,
    filename: str,
    period: str,
    touch_created_at: bool = False,
) -> None:
    """Replace the worker's stored copy after a visual PDF upgrade (same Stammdaten)."""
    doc_id = str(stmt.get("worker_document_id") or "").strip()
    if not doc_id:
        return
    from datetime import datetime, timezone

    stored_path = file_path
    try:
        src = Path(str(file_path or ""))
        if src.is_file():
            dest_dir = _storage_dir(str(stmt.get("company_id") or ""), period) / "delivered"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"{doc_id}_{src.name}"
            shutil.copy2(src, dest)
            stored_path = str(dest)
            file_size = dest.stat().st_size
    except Exception:
        stored_path = file_path
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    placeholders = ",".join("?" for _ in sorted(WORKER_PAYROLL_DOC_TYPES))
    try:
        if touch_created_at:
            db.execute(
                f"""
                UPDATE worker_documents
                SET file_path = ?, file_size = ?, filename = ?, created_at = ?,
                    notes = COALESCE(notes, '')
                WHERE id = ? AND doc_type IN ({placeholders})
                """,
                (stored_path, file_size, filename, now, doc_id, *sorted(WORKER_PAYROLL_DOC_TYPES)),
            )
        else:
            db.execute(
                f"""
                UPDATE worker_documents
                SET file_path = ?, file_size = ?, filename = ?
                WHERE id = ? AND doc_type IN ({placeholders})
                """,
                (stored_path, file_size, filename, doc_id, *sorted(WORKER_PAYROLL_DOC_TYPES)),
            )
        db.commit()
    except Exception:
        pass


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
        if not str(stmt.get("reviewed_at") or stmt.get("reviewedAt") or "").strip():
            errors.append({"statementId": stmt["id"], "error": "review_required"})
            continue
        if not str(stmt.get("worker_id") or stmt.get("workerId") or "").strip():
            errors.append({"statementId": stmt["id"], "error": "worker_unassigned"})
            continue
        if str(stmt.get("status") or "") == "unmatched":
            errors.append({"statementId": stmt["id"], "error": "worker_unassigned"})
            continue
        built = ensure_statement_delivery_pdf(db, stmt, batch)
        if not built.get("ok"):
            errors.append({"statementId": stmt["id"], "error": built.get("error") or "missing_pdf"})
            continue
        stmt = repo.get_statement(db, stmt["id"]) or stmt
        path = str(stmt.get("file_path") or "")
        if not path or not Path(path).is_file():
            errors.append({"statementId": stmt["id"], "error": "missing_pdf"})
            continue
        try:
            doc_type = _statement_doc_type(stmt)
            default_name = _default_payroll_filename(doc_type, stmt.get("period") or batch["period"], stmt.get("worker_id") or "worker")
            doc_id = _attach_worker_document(
                db,
                company_id=stmt["company_id"],
                worker_id=stmt["worker_id"],
                filename=stmt.get("filename") or default_name,
                file_path=path,
                file_size=int(stmt.get("file_size") or 0),
                uploaded_by_user_id=actor_user_id,
                period=stmt.get("period") or batch["period"],
                doc_type=doc_type,
            )
            db.execute(
                """
                UPDATE payroll_statements
                SET status = 'released', worker_document_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (doc_id, now, stmt["id"]),
            )
            stmt["status"] = "released"
            _lock_statement_delivery(db, stmt, now)
            try:
                from backend.server import _notify_worker_payroll_document

                _notify_worker_payroll_document(
                    db,
                    stmt["worker_id"],
                    stmt.get("filename") or default_name,
                    doc_type=doc_type,
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
    inbox_clear: dict[str, Any] = {"ok": False, "cleared": 0}
    if released:
        try:
            from .messages_inbox import clear_payslip_released_messages

            inbox_clear = clear_payslip_released_messages(
                db,
                company_id=str(batch.get("company_id") or ""),
                period=str(batch.get("period") or ""),
                batch_id=str(batch_id),
                actor_user_id=str(actor_user_id or ""),
            )
        except Exception as exc:
            inbox_clear = {"ok": False, "error": str(exc)[:120], "cleared": 0}
    return {
        "ok": True,
        "batchId": batch_id,
        "released": released,
        "skipped": skipped,
        "errors": errors,
        "status": refreshed.get("status") or new_status,
        "inboxCleared": inbox_clear,
    }


def reject_batch(db, *, batch_id: str, actor_user_id: str, company_id: str | None = None, reason: str = "") -> dict[str, Any]:
    batch = repo.get_batch(db, batch_id)
    if not batch:
        return {"ok": False, "error": "batch_not_found"}
    if company_id and batch["company_id"] != company_id:
        return {"ok": False, "error": "forbidden_company"}
    if batch["status"] not in {"pending_approval", "approved"}:
        return {"ok": False, "error": "invalid_status", "status": batch["status"]}
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
    notes = (batch.get("notes") or "") + (f"\nreject: {reason}" if reason else "")
    db.execute(
        "UPDATE payroll_statement_batches SET notes = ?, updated_at = ? WHERE id = ?",
        (notes[:1000], now, batch_id),
    )
    db.execute(
        """
        UPDATE payroll_statements
        SET status = 'rejected',
            rejected_at = ?,
            rejected_by_user_id = ?,
            reject_reason = ?,
            updated_at = ?
        WHERE batch_id = ? AND status NOT IN ('released', 'rejected')
        """,
        (now, actor_user_id, (reason or "")[:500], now, batch_id),
    )
    for row in repo.list_batch_statements(db, batch_id):
        if str(row.get("status") or "") == "rejected":
            _lock_statement_delivery(db, row, now)
    _refresh_batch_after_statement_change(db, batch_id=batch_id, actor_user_id=actor_user_id, now=now)
    db.commit()
    inbox_clear: dict[str, Any] = {"ok": False, "cleared": 0}
    try:
        from .messages_inbox import clear_payslip_released_messages

        inbox_clear = clear_payslip_released_messages(
            db,
            company_id=str(batch.get("company_id") or ""),
            period=str(batch.get("period") or ""),
            batch_id=str(batch_id),
            actor_user_id=str(actor_user_id or ""),
        )
    except Exception as exc:
        inbox_clear = {"ok": False, "error": str(exc)[:120], "cleared": 0}
    refreshed = repo.get_batch(db, batch_id) or {}
    return {
        "ok": True,
        "batchId": batch_id,
        "status": refreshed.get("status") or "rejected",
        "inboxCleared": inbox_clear,
    }


def _statement_company_guard(
    stmt: dict[str, Any] | None,
    *,
    company_id: str | None,
) -> dict[str, Any] | None:
    if not stmt:
        return {"ok": False, "error": "statement_not_found"}
    if company_id and str(stmt.get("company_id") or "") != str(company_id):
        return {"ok": False, "error": "forbidden_company"}
    return None


def mark_statement_reviewed(
    db,
    *,
    statement_id: str,
    actor_user_id: str,
    company_id: str | None = None,
) -> dict[str, Any]:
    """Record that an admin opened/checked the sheet (required before release).

    PDF rendering is deferred to download/release so the studio sheet view cannot
    trip a gateway timeout (502) while Chromium/WeasyPrint runs.
    """
    from datetime import datetime, timezone

    ensure = repo.get_statement
    stmt = ensure(db, statement_id)
    guard = _statement_company_guard(stmt, company_id=company_id)
    if guard:
        return guard
    assert stmt is not None
    if str(stmt.get("status") or "") in {"released", "rejected"}:
        return {
            "ok": True,
            "skipped": "locked",
            "statement": repo.enrich_statement_row(db, stmt),
        }
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
    db.execute(
        """
        UPDATE payroll_statements
        SET reviewed_at = ?, reviewed_by_user_id = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, actor_user_id, now, statement_id),
    )
    db.commit()
    refreshed = repo.get_statement(db, statement_id) or stmt
    return {
        "ok": True,
        "statement": repo.enrich_statement_row(db, refreshed),
        "reviewedAt": now,
    }


def assign_statement_worker(
    db,
    *,
    statement_id: str,
    worker_id: str,
    actor_user_id: str,
    company_id: str | None = None,
) -> dict[str, Any]:
    """Human rematch: bind payslip PDF to a worker in the same company."""
    from datetime import datetime, timezone

    stmt = repo.get_statement(db, statement_id)
    guard = _statement_company_guard(stmt, company_id=company_id)
    if guard:
        return guard
    assert stmt is not None
    if str(stmt.get("status") or "") in {"released", "rejected"} or statement_delivery_locked(stmt):
        return {"ok": False, "error": "invalid_status", "status": stmt.get("status")}
    worker_id = str(worker_id or "").strip()
    if not worker_id:
        return {"ok": False, "error": "worker_id_required"}
    row = db.execute(
        """
        SELECT id, first_name, last_name, badge_id
        FROM workers
        WHERE id = ? AND company_id = ? AND deleted_at IS NULL
        LIMIT 1
        """,
        (worker_id, stmt["company_id"]),
    ).fetchone()
    if not row:
        return {"ok": False, "error": "worker_not_found"}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
    db.execute(
        """
        UPDATE payroll_statements
        SET worker_id = ?,
            status = 'pending',
            matched_by = 'manual',
            match_confidence = 'exact',
            assigned_at = ?,
            assigned_by_user_id = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (worker_id, now, actor_user_id, now, statement_id),
    )
    db.commit()
    refreshed = repo.get_statement(db, statement_id) or {}
    return {
        "ok": True,
        "statement": repo.enrich_statement_row(db, refreshed),
        "workerId": worker_id,
        "matchedBy": "manual",
    }


def release_statement(
    db,
    *,
    statement_id: str,
    actor_user_id: str,
    company_id: str | None = None,
    require_reviewed: bool = True,
) -> dict[str, Any]:
    """Send one reviewed payslip to the worker app (document + push)."""
    from datetime import datetime, timezone

    stmt = repo.get_statement(db, statement_id)
    guard = _statement_company_guard(stmt, company_id=company_id)
    if guard:
        return guard
    assert stmt is not None
    status = str(stmt.get("status") or "")
    if status == "released":
        worker_id = str(stmt.get("worker_id") or "").strip()
        doc_id = str(stmt.get("worker_document_id") or "").strip()
        batch = repo.get_batch(db, str(stmt.get("batch_id") or "")) or {}
        path = str(stmt.get("file_path") or "").strip()
        # Repair: marked released but worker never got a usable file.
        if not _worker_document_delivery_ok(db, doc_id=doc_id, worker_id=worker_id):
            if not path or not Path(path).is_file():
                built = ensure_statement_delivery_pdf(db, stmt, batch, force=True)
                if not built.get("ok"):
                    return {
                        "ok": False,
                        "error": built.get("error") or "missing_pdf",
                        "hint": "PDF fehlt — Abrechnung erneut öffnen und senden",
                    }
                stmt = repo.get_statement(db, statement_id) or stmt
                path = str(stmt.get("file_path") or "").strip()
            if not path or not Path(path).is_file():
                return {"ok": False, "error": "missing_pdf"}
            if not worker_id:
                return {"ok": False, "error": "worker_unassigned", "hint": "Mitarbeiter zuweisen"}
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            try:
                doc_type = _statement_doc_type(stmt)
                default_name = _default_payroll_filename(doc_type, stmt.get("period") or "", worker_id or "worker")
                new_doc_id = _attach_worker_document(
                    db,
                    company_id=stmt["company_id"],
                    worker_id=worker_id,
                    filename=stmt.get("filename") or default_name,
                    file_path=path,
                    file_size=int(stmt.get("file_size") or 0),
                    uploaded_by_user_id=actor_user_id,
                    period=stmt.get("period") or "",
                    doc_type=doc_type,
                )
                db.execute(
                    """
                    UPDATE payroll_statements
                    SET worker_document_id = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (new_doc_id, now, statement_id),
                )
                try:
                    from backend.server import _notify_worker_payroll_document

                    _notify_worker_payroll_document(
                        db,
                        worker_id,
                        stmt.get("filename") or default_name,
                        doc_type=doc_type,
                    )
                except Exception:
                    pass
                db.commit()
                return {
                    "ok": True,
                    "repaired": True,
                    "statementId": statement_id,
                    "workerDocumentId": new_doc_id,
                    "deliveredAt": now,
                    "message": f"{doc_type_label(doc_type, 'de')} nachgeliefert an Mitarbeiter-App",
                }
            except Exception as exc:
                return {"ok": False, "error": str(exc)[:160]}
        # Already delivered — refresh PDF bytes if a better exact capture exists.
        try:
            meta = json.loads(stmt.get("meta_json") or "{}")
        except Exception:
            meta = {}
        from .lohn_sheet_pdf import is_exact_lohn_pdf_source

        doc_type = _statement_doc_type(stmt)
        default_name = _default_payroll_filename(doc_type, stmt.get("period") or "", worker_id or "worker")
        if is_exact_lohn_pdf_source((meta or {}).get("pdfSource")) and path and Path(path).is_file():
            _refresh_worker_document_pdf(
                db,
                stmt,
                file_path=path,
                file_size=int(stmt.get("file_size") or 0),
                filename=stmt.get("filename") or default_name,
                period=str(stmt.get("period") or ""),
                touch_created_at=True,
            )
            try:
                from backend.server import _notify_worker_payroll_document

                _notify_worker_payroll_document(
                    db,
                    worker_id,
                    stmt.get("filename") or default_name,
                    doc_type=doc_type,
                )
            except Exception:
                pass
            return {
                "ok": True,
                "resent": True,
                "statementId": statement_id,
                "workerDocumentId": doc_id,
                "deliveredAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "message": f"{doc_type_label(doc_type, 'de')} erneut an Mitarbeiter-App gesendet",
            }
        return {
            "ok": True,
            "skipped": "already_released",
            "statementId": statement_id,
            "workerDocumentId": doc_id,
            "message": "Bereits an Mitarbeiter-App gesendet",
        }
    if status in {"rejected"}:
        return {"ok": False, "error": "invalid_status", "status": status}
    if status == "unmatched" or not str(stmt.get("worker_id") or "").strip():
        return {"ok": False, "error": "worker_unassigned", "hint": "Mitarbeiter zuweisen"}
    if require_reviewed and not str(stmt.get("reviewed_at") or "").strip():
        return {"ok": False, "error": "review_required", "hint": "PDF zuerst öffnen und prüfen"}
    batch = repo.get_batch(db, str(stmt.get("batch_id") or "")) or {}
    from .lohn_sheet_pdf import is_exact_lohn_pdf_source, is_high_fidelity_pdf_source

    try:
        meta_now = json.loads(stmt.get("meta_json") or "{}")
    except Exception:
        meta_now = {}
    # Exact Lohn PDF / html2canvas capture must be forwarded unchanged.
    if is_exact_lohn_pdf_source((meta_now or {}).get("pdfSource")):
        built = ensure_statement_delivery_pdf(db, stmt, batch, force=False)
    else:
        force_pdf = not is_high_fidelity_pdf_source((meta_now or {}).get("pdfSource"))
        built = ensure_statement_delivery_pdf(db, stmt, batch, force=force_pdf)
    if not built.get("ok"):
        return {"ok": False, "error": built.get("error") or "missing_pdf"}
    stmt = repo.get_statement(db, statement_id) or stmt
    path = str(stmt.get("file_path") or "")
    if not path or not Path(path).is_file():
        return {"ok": False, "error": "missing_pdf"}

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
    try:
        doc_type = _statement_doc_type(stmt)
        default_name = _default_payroll_filename(doc_type, stmt.get("period") or "", stmt.get("worker_id") or "worker")
        doc_id = _attach_worker_document(
            db,
            company_id=stmt["company_id"],
            worker_id=stmt["worker_id"],
            filename=stmt.get("filename") or default_name,
            file_path=path,
            file_size=int(stmt.get("file_size") or 0),
            uploaded_by_user_id=actor_user_id,
            period=stmt.get("period") or "",
            doc_type=doc_type,
        )
        db.execute(
            """
            UPDATE payroll_statements
            SET status = 'released', worker_document_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (doc_id, now, statement_id),
        )
        stmt["status"] = "released"
        _lock_statement_delivery(db, stmt, now)
        try:
            from backend.server import _notify_worker_payroll_document

            _notify_worker_payroll_document(
                db,
                stmt["worker_id"],
                stmt.get("filename") or default_name,
                doc_type=doc_type,
            )
        except Exception:
            pass
        batch_id = str(stmt.get("batch_id") or "")
        _refresh_batch_after_statement_change(db, batch_id=batch_id, actor_user_id=actor_user_id, now=now)
        db.commit()
        inbox_clear: dict[str, Any] = {"ok": False, "cleared": 0}
        batch = repo.get_batch(db, batch_id) or {}
        if str(batch.get("status") or "") == "released":
            try:
                from .messages_inbox import clear_payslip_released_messages

                inbox_clear = clear_payslip_released_messages(
                    db,
                    company_id=str(stmt.get("company_id") or ""),
                    period=str(stmt.get("period") or ""),
                    batch_id=batch_id,
                    actor_user_id=str(actor_user_id or ""),
                )
            except Exception as exc:
                inbox_clear = {"ok": False, "error": str(exc)[:120], "cleared": 0}
        refreshed = repo.get_statement(db, statement_id) or {}
        return {
            "ok": True,
            "statementId": statement_id,
            "workerDocumentId": doc_id,
            "deliveredAt": now,
            "statement": repo.enrich_statement_row(db, refreshed),
            "batchStatus": (repo.get_batch(db, batch_id) or {}).get("status"),
            "inboxCleared": inbox_clear,
            "message": f"{doc_type_label(doc_type, 'de')} an Mitarbeiter-App gesendet",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:160]}


def reject_statement(
    db,
    *,
    statement_id: str,
    actor_user_id: str,
    company_id: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    from datetime import datetime, timezone

    stmt = repo.get_statement(db, statement_id)
    guard = _statement_company_guard(stmt, company_id=company_id)
    if guard:
        return guard
    assert stmt is not None
    if str(stmt.get("status") or "") == "released":
        return {"ok": False, "error": "already_released"}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
    db.execute(
        """
        UPDATE payroll_statements
        SET status = 'rejected',
            rejected_at = ?,
            rejected_by_user_id = ?,
            reject_reason = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (now, actor_user_id, (reason or "")[:500], now, statement_id),
    )
    stmt["status"] = "rejected"
    _lock_statement_delivery(db, stmt, now)
    batch_id = str(stmt.get("batch_id") or "")
    _refresh_batch_after_statement_change(db, batch_id=batch_id, actor_user_id=actor_user_id, now=now)
    db.commit()
    refreshed = repo.get_statement(db, statement_id) or {}
    return {"ok": True, "statement": repo.enrich_statement_row(db, refreshed), "status": "rejected"}


def release_reviewed_batch(
    db,
    *,
    batch_id: str,
    actor_user_id: str,
    company_id: str | None = None,
) -> dict[str, Any]:
    """Release only statements that were opened (reviewed) and assigned — never blind."""
    batch = repo.get_batch(db, batch_id)
    if not batch:
        return {"ok": False, "error": "batch_not_found"}
    if company_id and batch["company_id"] != company_id:
        return {"ok": False, "error": "forbidden_company"}
    statements = repo.list_batch_statements(db, batch_id)
    released = 0
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for stmt in statements:
        sid = str(stmt.get("id") or stmt.get("statementId") or "")
        if stmt.get("status") == "released":
            skipped.append({"statementId": sid, "reason": "already_released"})
            continue
        if not stmt.get("canRelease"):
            skipped.append(
                {
                    "statementId": sid,
                    "reason": "not_ready",
                    "reviewed": bool(stmt.get("reviewed")),
                    "hasPdf": bool(stmt.get("hasPdf")),
                    "workerId": stmt.get("workerId"),
                    "status": stmt.get("status"),
                }
            )
            continue
        out = release_statement(
            db,
            statement_id=sid,
            actor_user_id=actor_user_id,
            company_id=company_id,
            require_reviewed=True,
        )
        results.append(out)
        if out.get("ok") and not out.get("skipped"):
            released += 1
        elif not out.get("ok"):
            errors.append({"statementId": sid, "error": out.get("error")})
    refreshed = repo.get_batch(db, batch_id) or {}
    return {
        "ok": True,
        "batchId": batch_id,
        "released": released,
        "skipped": skipped,
        "errors": errors,
        "results": results,
        "status": refreshed.get("status"),
        "message": f"{released} geprüfte Lohnabrechnung(en) an Mitarbeiter gesendet",
    }


def _refresh_batch_after_statement_change(
    db,
    *,
    batch_id: str,
    actor_user_id: str,
    now: str,
) -> None:
    if not batch_id:
        return
    rows = db.execute(
        "SELECT status FROM payroll_statements WHERE batch_id = ?",
        (batch_id,),
    ).fetchall()
    if not rows:
        return
    statuses = [str(r["status"] or "") for r in rows]
    all_released = statuses and all(s == "released" for s in statuses)
    all_done = statuses and all(s in {"released", "rejected"} for s in statuses)
    any_released = any(s == "released" for s in statuses)
    if all_released:
        new_status = "released"
    elif all_done and any_released:
        new_status = "released"
    elif all_done:
        new_status = "rejected"
    elif any_released:
        new_status = "approved"
    else:
        return
    db.execute(
        """
        UPDATE payroll_statement_batches
        SET status = ?,
            approved_at = COALESCE(approved_at, ?),
            approved_by_user_id = COALESCE(approved_by_user_id, ?),
            released_at = CASE WHEN ? = 'released' THEN COALESCE(released_at, ?) ELSE released_at END,
            rejected_at = CASE WHEN ? = 'rejected' THEN COALESCE(rejected_at, ?) ELSE rejected_at END,
            updated_at = ?
        WHERE id = ?
        """,
        (new_status, now, actor_user_id, new_status, now, new_status, now, now, batch_id),
    )


def fingerprint_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]
