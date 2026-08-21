"""Personio HRIS adapter — employee / absence sync via Personio API."""
from __future__ import annotations

import json
import os
import time
import urllib.parse
from typing import Any
from urllib import request as urlrequest

PERSONIO_TOKEN_URL = "https://api.personio.de/v1/auth"
PERSONIO_EMPLOYEES_URL = "https://api.personio.de/v1/company/employees"
PERSONIO_ABSENCES_URL = "https://api.personio.de/v1/company/time-offs"


def personio_env_configured() -> bool:
    return bool(
        (os.getenv("PERSONIO_CLIENT_ID") or "").strip()
        and (os.getenv("PERSONIO_CLIENT_SECRET") or "").strip()
    )


def personio_feature_enabled() -> bool:
    return (os.getenv("BAUPASS_PERSONIO_ENABLED") or "0").strip().lower() in {"1", "true", "yes"}


def _request_json(url: str, *, method: str = "GET", headers: dict | None = None, body: bytes | None = None) -> dict[str, Any]:
    req = urlrequest.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urlrequest.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return {"ok": 200 <= resp.status < 300, "status": resp.status, "data": json.loads(raw)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def obtain_personio_token(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(config or {})
    client_id = str(cfg.get("client_id") or os.getenv("PERSONIO_CLIENT_ID") or "").strip()
    client_secret = str(cfg.get("client_secret") or os.getenv("PERSONIO_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret:
        return {"ok": False, "error": "personio_not_configured"}
    body = urllib.parse.urlencode({"client_id": client_id, "client_secret": client_secret}).encode("utf-8")
    result = _request_json(
        PERSONIO_TOKEN_URL,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        body=body,
    )
    if not result.get("ok"):
        return result
    token = ((result.get("data") or {}).get("data") or {}).get("token") or (result.get("data") or {}).get("token")
    if not token:
        return {"ok": False, "error": "personio_token_missing", "raw": result.get("data")}
    return {"ok": True, "token": token, "obtained_at": int(time.time())}


def fetch_personio_employees(token: str, *, limit: int = 100) -> dict[str, Any]:
    url = f"{PERSONIO_EMPLOYEES_URL}?limit={max(1, min(200, int(limit)))}"
    return _request_json(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})


def fetch_personio_absences(token: str, *, limit: int = 100) -> dict[str, Any]:
    url = f"{PERSONIO_ABSENCES_URL}?limit={max(1, min(200, int(limit)))}"
    return _request_json(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})


def map_personio_employee(item: dict[str, Any]) -> dict[str, Any]:
    attrs = dict((item or {}).get("attributes") or item or {})
    email = ""
    first = ""
    last = ""
    for key, val in attrs.items():
        if isinstance(val, dict) and "value" in val:
            val = val.get("value")
        lk = str(key).lower()
        if lk in {"email", "work_email"} and val:
            email = str(val)
        if lk in {"first_name", "firstname"} and val:
            first = str(val)
        if lk in {"last_name", "lastname"} and val:
            last = str(val)
    return {
        "externalId": str((item or {}).get("id") or attrs.get("id") or ""),
        "email": email,
        "firstName": first,
        "lastName": last,
        "displayName": f"{first} {last}".strip(),
        "raw": item,
    }


def sync_personio_preview(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dry-run sync: authenticate and map employees/absences without writing workers."""
    cfg = dict(config or {})
    if cfg.get("dry_run_sample"):
        return {
            "ok": True,
            "dryRun": True,
            "employees": [
                {
                    "externalId": "1",
                    "email": "a@example.com",
                    "firstName": "Ada",
                    "lastName": "Lovelace",
                    "displayName": "Ada Lovelace",
                }
            ],
            "absences": [],
        }
    if not personio_feature_enabled() and not personio_env_configured():
        return {
            "ok": False,
            "error": "personio_disabled",
            "hint": "Set BAUPASS_PERSONIO_ENABLED=1 and PERSONIO_CLIENT_ID/SECRET",
        }
    token_res = obtain_personio_token(cfg)
    if not token_res.get("ok"):
        return token_res
    employees = fetch_personio_employees(str(token_res.get("token")))
    absences = fetch_personio_absences(str(token_res.get("token")))
    emp_data = ((employees.get("data") or {}).get("data") or []) if employees.get("ok") else []
    abs_data = ((absences.get("data") or {}).get("data") or []) if absences.get("ok") else []
    mapped = [map_personio_employee(x if isinstance(x, dict) else {}) for x in emp_data]
    return {
        "ok": True,
        "employeeCount": len(mapped),
        "absenceCount": len(abs_data),
        "employees": mapped[:200],
        "absences": abs_data[:200],
    }


def upsert_personio_workers(db, company_id: str, employees: list[dict[str, Any]]) -> dict[str, Any]:
    """Write mapped Personio employees into workers (match by contact_email)."""
    import secrets
    import time

    cid = str(company_id or "").strip()
    if not cid:
        return {"ok": False, "error": "missing_company"}
    created = 0
    updated = 0
    skipped = 0
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for emp in employees or []:
        email = str(emp.get("email") or "").strip().lower()
        first = str(emp.get("firstName") or "").strip() or "Personio"
        last = str(emp.get("lastName") or "").strip() or "Import"
        external = str(emp.get("externalId") or "").strip()
        if not email and not external:
            skipped += 1
            continue
        existing = None
        if email:
            try:
                existing = db.execute(
                    """
                    SELECT id FROM workers
                    WHERE company_id = ? AND lower(contact_email) = ? AND deleted_at IS NULL
                    LIMIT 1
                    """,
                    (cid, email),
                ).fetchone()
            except Exception:
                existing = None
        if existing:
            wid = str(existing["id"])
            try:
                db.execute(
                    """
                    UPDATE workers
                    SET first_name = ?, last_name = ?, contact_email = COALESCE(NULLIF(?, ''), contact_email),
                        updated_at = ?
                    WHERE id = ? AND company_id = ?
                    """,
                    (first, last, email, now, wid, cid),
                )
            except Exception:
                db.execute(
                    "UPDATE workers SET first_name = ?, last_name = ? WHERE id = ? AND company_id = ?",
                    (first, last, wid, cid),
                )
            updated += 1
        else:
            wid = f"w-personio-{secrets.token_hex(6)}"
            try:
                db.execute(
                    """
                    INSERT INTO workers (
                        id, company_id, first_name, last_name, contact_email, status, role, site, valid_until, photo_data, badge_id
                    ) VALUES (?, ?, ?, ?, ?, 'aktiv', 'worker', '', '', '', ?)
                    """,
                    (wid, cid, first, last, email, f"PN-{external or secrets.token_hex(3)}"),
                )
            except Exception:
                db.execute(
                    """
                    INSERT INTO workers (
                        id, company_id, first_name, last_name, status, role, site, valid_until, photo_data, badge_id
                    ) VALUES (?, ?, ?, ?, 'aktiv', 'worker', '', '', '', ?)
                    """,
                    (wid, cid, first, last, f"PN-{external or secrets.token_hex(3)}"),
                )
            created += 1
    try:
        db.commit()
    except Exception:
        pass
    return {"ok": True, "created": created, "updated": updated, "skipped": skipped}


def map_personio_absence(item: dict[str, Any]) -> dict[str, Any]:
    attrs = dict((item or {}).get("attributes") or item or {})
    def _val(key: str) -> Any:
        raw = attrs.get(key)
        if isinstance(raw, dict) and "value" in raw:
            return raw.get("value")
        return raw

    start = str(_val("start_date") or _val("start") or "")[:10]
    end = str(_val("end_date") or _val("end") or start)[:10]
    status_raw = str(_val("status") or "approved").lower()
    if status_raw in {"approved", "granted", "accepted"}:
        status = "genehmigt"
    elif status_raw in {"declined", "rejected", "denied"}:
        status = "abgelehnt"
    else:
        status = "ausstehend"
    employee = _val("employee") or {}
    emp_id = ""
    if isinstance(employee, dict):
        emp_id = str(employee.get("id") or (employee.get("attributes") or {}).get("id") or "")
    elif employee:
        emp_id = str(employee)
    return {
        "externalId": str((item or {}).get("id") or _val("id") or ""),
        "employeeExternalId": emp_id,
        "startDate": start,
        "endDate": end,
        "type": str(_val("time_off_type") or _val("type") or "urlaub")[:64] or "urlaub",
        "status": status,
        "note": f"personio:{str((item or {}).get('id') or '')}",
        "raw": item,
    }


def upsert_personio_absences(db, company_id: str, absences: list[dict[str, Any]]) -> dict[str, Any]:
    """Write Personio time-offs into leave_requests; skip conflicting local approvals."""
    import secrets
    import time

    cid = str(company_id or "").strip()
    if not cid:
        return {"ok": False, "error": "missing_company"}
    created = 0
    updated = 0
    skipped = 0
    conflicts: list[dict[str, Any]] = []
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for abs_item in absences or []:
        mapped = abs_item if abs_item.get("startDate") else map_personio_absence(abs_item if isinstance(abs_item, dict) else {})
        start = str(mapped.get("startDate") or "")[:10]
        end = str(mapped.get("endDate") or start)[:10]
        external = str(mapped.get("externalId") or "").strip()
        emp_ext = str(mapped.get("employeeExternalId") or "").strip()
        note_marker = f"personio:{external}" if external else ""
        if not start or not (external or emp_ext):
            skipped += 1
            continue
        worker = None
        if emp_ext:
            try:
                worker = db.execute(
                    """
                    SELECT id FROM workers
                    WHERE company_id = ? AND (badge_id = ? OR badge_id = ?) AND deleted_at IS NULL
                    LIMIT 1
                    """,
                    (cid, f"PN-{emp_ext}", emp_ext),
                ).fetchone()
            except Exception:
                worker = None
        if not worker:
            skipped += 1
            continue
        wid = str(worker["id"])
        existing = None
        if note_marker:
            try:
                existing = db.execute(
                    """
                    SELECT id, status, start_date, end_date FROM leave_requests
                    WHERE company_id = ? AND worker_id = ? AND note LIKE ?
                    LIMIT 1
                    """,
                    (cid, wid, f"%{note_marker}%"),
                ).fetchone()
            except Exception:
                existing = None
        if not existing:
            try:
                existing = db.execute(
                    """
                    SELECT id, status, start_date, end_date FROM leave_requests
                    WHERE company_id = ? AND worker_id = ? AND start_date = ? AND end_date = ?
                    LIMIT 1
                    """,
                    (cid, wid, start, end),
                ).fetchone()
            except Exception:
                existing = None
        if existing:
            local_status = str(existing["status"] or "")
            remote_status = str(mapped.get("status") or "ausstehend")
            if local_status in {"genehmigt", "abgelehnt"} and remote_status != local_status:
                conflicts.append(
                    {
                        "leaveId": str(existing["id"]),
                        "workerId": wid,
                        "localStatus": local_status,
                        "remoteStatus": remote_status,
                        "startDate": start,
                        "endDate": end,
                        "resolution": "keep_local",
                    }
                )
                skipped += 1
                continue
            try:
                db.execute(
                    """
                    UPDATE leave_requests
                    SET type = ?, status = ?, note = ?, end_date = ?
                    WHERE id = ? AND company_id = ?
                    """,
                    (
                        str(mapped.get("type") or "urlaub")[:64],
                        remote_status,
                        note_marker or str(existing["id"]),
                        end,
                        str(existing["id"]),
                        cid,
                    ),
                )
                updated += 1
            except Exception:
                skipped += 1
            continue
        lid = f"lr-personio-{secrets.token_hex(6)}"
        try:
            db.execute(
                """
                INSERT INTO leave_requests (
                    id, worker_id, company_id, type, start_date, end_date, days_count, note, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    lid,
                    wid,
                    cid,
                    str(mapped.get("type") or "urlaub")[:64],
                    start,
                    end,
                    note_marker or "personio-import",
                    str(mapped.get("status") or "ausstehend"),
                    now,
                ),
            )
            created += 1
        except Exception:
            skipped += 1
    try:
        db.commit()
    except Exception:
        pass
    return {"ok": True, "created": created, "updated": updated, "skipped": skipped, "conflicts": conflicts}


def sync_personio_to_workers(db, company_id: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch Personio employees/absences and upsert into workers + leave_requests."""
    preview = sync_personio_preview(config)
    if not preview.get("ok"):
        return preview
    employees = list(preview.get("employees") or [])
    write = upsert_personio_workers(db, company_id, employees)
    abs_raw = list(preview.get("absences") or [])
    mapped_abs = [map_personio_absence(x if isinstance(x, dict) else {}) for x in abs_raw]
    abs_write = upsert_personio_absences(db, company_id, mapped_abs)
    return {
        **preview,
        **write,
        "absencesWrite": abs_write,
        "synced": True,
        "conflictCount": len(abs_write.get("conflicts") or []),
    }


def personio_status(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "provider": "personio",
        "featureEnabled": personio_feature_enabled(),
        "envConfigured": personio_env_configured(),
        "connected": bool((config or {}).get("oauth", {}).get("token") or (config or {}).get("token")),
        "live": bool(personio_feature_enabled() and personio_env_configured()),
        "writeback": True,
    }
