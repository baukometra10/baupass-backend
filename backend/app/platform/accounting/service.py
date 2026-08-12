"""Business logic: hours export, statement ingest, human approval + worker release."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
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


PAYROLL_BATCH_FORMAT = "platform.payroll.batch.v1"
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


def prepare_hour_export(db, *, company_id: str, period: str, mark_sent: bool = False) -> dict[str, Any]:
    payload = aggregate_company_hours(db, company_id=company_id, period=period)
    status = "sent" if mark_sent else "queued"
    meta = repo.save_hour_export(db, company_id=company_id, period=payload["period"], payload=payload, status=status)
    payload["exportId"] = meta["id"]
    payload["fingerprint"] = meta["fingerprint"]
    payload["exportStatus"] = meta["status"]
    return payload


def prepare_payroll_batch(db, *, company_id: str, period: str, mark_sent: bool = False) -> dict[str, Any]:
    """
    Capability platform.payroll.batch.v1 — same hours rows, packaged for Lohn pull/push.
    Body contract: { companyId, period } → full batch with employees[].
    """
    hours = prepare_hour_export(db, company_id=company_id, period=period, mark_sent=mark_sent)
    company_id = require_company_id(company_id)
    period = normalize_period(period)
    employees = []
    for row in hours.get("rows") or []:
        employees.append(
            {
                **row,
                "employeeId": row.get("employeeId") or row.get("workerId"),
                "workerId": row.get("workerId") or row.get("employeeId"),
            }
        )
    return {
        "ok": True,
        "capability": PAYROLL_BATCH_FORMAT,
        "format": PAYROLL_BATCH_FORMAT,
        "product": "WorkPass Lohn",
        "companyId": company_id,
        "company": hours.get("company") or {"id": company_id},
        "companyName": hours.get("companyName") or "",
        "period": period,
        "periodStart": hours.get("periodStart"),
        "periodEnd": hours.get("periodEnd"),
        "rowCount": hours.get("rowCount") or len(employees),
        "employeeCount": hours.get("employeeCount") or len(employees),
        "payrollReadyCount": hours.get("payrollReadyCount"),
        "incompleteCount": hours.get("incompleteCount"),
        "incompleteEmployees": hours.get("incompleteEmployees") or [],
        "totalHours": hours.get("totalHours"),
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
        "note": "Full employee master + hours for period. grossEstimate is platform hint only; WorkPass Lohn computes official payroll",
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
        batch = prepare_payroll_batch(db, company_id=company_id, period=period, mark_sent=True)
    platform_url = str(link.get("platform_public_url") or "").rstrip("/")
    body = {
        **batch,
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
            "totalGrossEstimate": batch.get("totalGrossEstimate"),
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

    return {
        "ok": bool(push.get("ok")) or int(alerts.get("dismissed") or 0) > 0 or any(
            bool(a.get("ok")) for a in message_acks if isinstance(a, dict)
        ),
        "companyId": company_id,
        "workerId": worker_id,
        "payrollReady": payroll_ready,
        "missingFields": missing,
        "employee": employee,
        "push": push,
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
            return {
                "ok": mark_done,
                "status": "delivered" if mark_done else "partial",
                "mode": "employee",
                "replies": replies,
                "message": "Employee master pushed to WorkPass Lohn",
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
                "message": delivery.get("message")
                or "Mitarbeiter und Abrechnungsdaten automatisch an WorkPass Lohn übergeben",
                "error": delivery.get("error"),
            }

        # Master sync without month
        if want_employees:
            _db_commit(db)
            replies["employeesImport"] = push_employees_to_lohn(
                db, company_id=company_id, timeout=6
            )
        mark_done = bool(
            (replies.get("employeesImport") or {}).get("ok")
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
        worker_id = str(
            item.get("workerId") or item.get("worker_id") or item.get("employeeId") or item.get("employee_id") or ""
        ).strip()
        if not worker_id:
            errors.append({"index": idx, "error": "employee_id_required"})
            continue
        try:
            storage_key = str(item.get("storageKey") or "").strip() or payroll_storage_key(
                company_id=company_id, employee_id=worker_id, period=period
            )
        except ValueError as exc:
            errors.append({"index": idx, "error": str(exc)})
            continue
        worker = db.execute(
            "SELECT id FROM workers WHERE id = ? AND company_id = ? AND deleted_at IS NULL",
            (worker_id, company_id),
        ).fetchone()
        if not worker:
            errors.append({"index": idx, "error": "worker_not_found", "employeeId": worker_id, "storageKey": storage_key})
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
                errors.append({"index": idx, "error": "invalid_pdf_base64", "employeeId": worker_id})
                continue
            if len(raw) < 20 or not raw.startswith(b"%PDF"):
                errors.append({"index": idx, "error": "not_a_pdf", "employeeId": worker_id})
                continue
            if len(raw) > 15 * 1024 * 1024:
                errors.append({"index": idx, "error": "pdf_too_large", "employeeId": worker_id})
                continue
            dest_dir = _storage_dir(company_id, period)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"{worker_id}_{secrets.token_hex(4)}.pdf"
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
        meta["employeeId"] = worker_id
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
        )
        created.append(stmt_id)
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
    return {"ok": True, "batchId": batch_id, "status": "rejected", "inboxCleared": inbox_clear}


def fingerprint_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]
