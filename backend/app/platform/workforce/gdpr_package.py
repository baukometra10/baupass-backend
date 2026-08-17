"""DSGVO access export (Art. 15) for a worker."""
from __future__ import annotations

from typing import Any

from .location_privacy import _row_get

_WORKER_EXPORT_KEYS = (
    "id",
    "company_id",
    "first_name",
    "last_name",
    "email",
    "phone",
    "status",
    "created_at",
    "updated_at",
    "role",
    "job_title",
    "nationality",
    "birth_date",
    "address",
    "city",
    "postal_code",
    "country",
)


def _safe_row(row) -> dict[str, Any]:
    if row is None:
        return {}
    try:
        return {str(k): row[k] for k in row.keys()}
    except Exception:
        return {}


def _query_dicts(db, sql: str, params: tuple[Any, ...], limit: int = 500) -> list[dict[str, Any]]:
    try:
        rows = db.execute(sql, params).fetchall()
    except Exception:
        return []
    out = []
    for row in rows or []:
        out.append(_safe_row(row))
        if len(out) >= limit:
            break
    return out


def build_access_export(db, *, company_id: str, worker_id: str) -> dict[str, Any]:
    cid = str(company_id or "").strip()
    wid = str(worker_id or "").strip()
    profile: dict[str, Any] = {}
    try:
        row = db.execute(
            "SELECT * FROM workers WHERE id = ? AND CAST(company_id AS TEXT) = ?",
            (wid, cid),
        ).fetchone()
        raw = _safe_row(row)
        for key in _WORKER_EXPORT_KEYS:
            if key in raw:
                profile[key] = raw[key]
        profile["hasPhoto"] = bool(str(raw.get("photo_data") or "").strip())
        profile["hasDocumentScan"] = bool(str(raw.get("document_scan") or raw.get("id_document_b64") or "").strip())
    except Exception:
        profile = {"id": wid, "company_id": cid}
    consents = _query_dicts(
        db,
        """
        SELECT consent_type, granted, granted_at, revoked_at, version
        FROM data_consents WHERE worker_id = ?
        ORDER BY granted_at DESC
        """,
        (wid,),
    )
    access_logs = _query_dicts(
        db,
        """
        SELECT id, direction, gate, timestamp, note
        FROM access_logs WHERE worker_id = ?
        ORDER BY timestamp DESC
        """,
        (wid,),
        limit=200,
    )
    for item in access_logs:
        note = str(item.get("note") or "")
        if "deviceLat" in note or "deviceLng" in note:
            item["note"] = "[GPS in original log — included below in locationSamples if retained]"
    leave = _query_dicts(
        db,
        """
        SELECT id, type, status, start_date, end_date, created_at, note
        FROM leave_requests WHERE worker_id = ?
        ORDER BY created_at DESC
        """,
        (wid,),
        limit=200,
    )
    gps = _query_dicts(
        db,
        """
        SELECT lat, lng, accuracy_m, recorded_at, geofence_id, zone_kind
        FROM worker_location_samples
        WHERE worker_id = ? AND CAST(company_id AS TEXT) = ?
        ORDER BY recorded_at DESC
        """,
        (wid, cid),
        limit=500,
    )
    chats = _query_dicts(
        db,
        """
        SELECT id, thread_id, sender_type, body, created_at
        FROM chat_messages
        WHERE worker_id = ? AND CAST(company_id AS TEXT) = ?
        ORDER BY created_at DESC
        """,
        (wid, cid),
        limit=200,
    )
    for item in chats:
        body = str(item.get("body") or "")
        if body.startswith("@location|"):
            item["body"] = "@location|(coordinates included as location share)"
            item["kind"] = "location"
    return {
        "ok": True,
        "companyId": cid,
        "workerId": wid,
        "profile": profile,
        "consents": consents,
        "accessLogs": access_logs,
        "leaveRequests": leave,
        "locationSamples": gps,
        "chatMessages": chats,
        "retentionNote": "GPS-Spuren werden nach der Firmen-Aufbewahrungsfrist automatisch gelöscht.",
    }


def apply_gdpr_access_if_needed(db, request_row) -> dict[str, Any] | None:
    kind = str(_row_get(request_row, "request_type", "") or "").strip().lower()
    if kind not in {"access", "auskunft"}:
        return None
    return build_access_export(
        db,
        company_id=str(_row_get(request_row, "company_id", "") or ""),
        worker_id=str(_row_get(request_row, "worker_id", "") or ""),
    )
