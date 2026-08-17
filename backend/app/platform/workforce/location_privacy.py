"""DSGVO gates for live GPS: consent, on-duty only, company switch, erasure."""
from __future__ import annotations

import re
from typing import Any

LOCATION_CONSENT_TYPES = frozenset({"privacy_app", "gps_live_tracking", "location_tracking"})
DEFAULT_GPS_RETENTION_DAYS = 14
ERASURE_REQUEST_TYPES = frozenset({"erasure", "loeschung", "delete", "deletion"})

_DEVICE_COORD_RE = re.compile(
    r"(?:deviceLat|deviceLng|lat|lng)\s*=\s*[-+]?\d+(?:\.\d+)?",
    re.IGNORECASE,
)


def _row_get(row, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        if hasattr(row, "keys") and key in row.keys():
            return row[key]
    except Exception:
        pass
    return default


def has_location_consent(db, worker_id: str) -> bool:
    wid = str(worker_id or "").strip()
    if not wid:
        return False
    try:
        rows = db.execute(
            """
            SELECT consent_type, granted, revoked_at
            FROM data_consents
            WHERE worker_id = ?
            """,
            (wid,),
        ).fetchall()
    except Exception:
        return False
    for row in rows or []:
        kind = str(_row_get(row, "consent_type", "") or "").strip()
        if kind not in LOCATION_CONSENT_TYPES:
            continue
        granted = str(_row_get(row, "granted", 0) or 0).strip().lower()
        if granted not in {"1", "true", "yes"}:
            continue
        revoked = str(_row_get(row, "revoked_at", "") or "").strip()
        if revoked:
            continue
        return True
    return False


def company_location_tracking_enabled(db, company_id: str) -> bool:
    cid = str(company_id or "").strip()
    if not cid:
        return True
    try:
        row = db.execute(
            "SELECT location_tracking_enabled FROM companies WHERE id = ?",
            (cid,),
        ).fetchone()
    except Exception:
        return True
    if row is None:
        return True
    raw = _row_get(row, "location_tracking_enabled", 1)
    if raw is None:
        return True
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def gps_retention_days(db, company_id: str | None = None) -> int:
    cid = str(company_id or "").strip()
    if cid:
        try:
            row = db.execute(
                "SELECT gps_location_days FROM company_retention_policies WHERE company_id = ?",
                (cid,),
            ).fetchone()
            if row is not None and _row_get(row, "gps_location_days") is not None:
                days = int(_row_get(row, "gps_location_days") or DEFAULT_GPS_RETENTION_DAYS)
                return max(1, min(365, days))
        except Exception:
            pass
    return DEFAULT_GPS_RETENTION_DAYS


def company_location_legal_ack(db, company_id: str) -> bool:
    cid = str(company_id or "").strip()
    if not cid:
        return False
    try:
        row = db.execute(
            "SELECT location_tracking_legal_ack FROM companies WHERE id = ?",
            (cid,),
        ).fetchone()
    except Exception:
        return False
    if row is None:
        return False
    raw = _row_get(row, "location_tracking_legal_ack", 0)
    return str(raw or 0).strip().lower() in {"1", "true", "yes", "on"}


def allow_store_live_location(
    db,
    *,
    worker_id: str,
    company_id: str,
    on_duty: bool,
) -> tuple[bool, str]:
    """Privacy by design: store/broadcast only with consent, legal ack, and an open shift."""
    if not company_location_tracking_enabled(db, company_id):
        return False, "company_tracking_disabled"
    if not company_location_legal_ack(db, company_id):
        return False, "location_tracking_legal_ack_required"
    if not has_location_consent(db, worker_id):
        return False, "missing_location_consent"
    if not on_duty:
        return False, "not_checked_in"
    return True, ""


def clear_live_location(db, worker_id: str) -> bool:
    wid = str(worker_id or "").strip()
    if not wid:
        return False
    try:
        db.execute(
            """
            UPDATE worker_presence_state
            SET last_lat = NULL, last_lng = NULL, last_accuracy_m = NULL, last_location_at = ''
            WHERE worker_id = ?
            """,
            (wid,),
        )
        return True
    except Exception:
        return False


def _anonymize_access_log_notes(db, worker_id: str, company_id: str) -> int:
    cleared = 0
    try:
        rows = db.execute(
            """
            SELECT id, note FROM access_logs
            WHERE worker_id = ?
              AND COALESCE(note, '') != ''
            """,
            (str(worker_id),),
        ).fetchall()
    except Exception:
        return 0
    for row in rows or []:
        note = str(_row_get(row, "note", "") or "")
        if "deviceLat" not in note and "deviceLng" not in note:
            continue
        new_note = _DEVICE_COORD_RE.sub("coord=redacted", note)
        try:
            db.execute("UPDATE access_logs SET note = ? WHERE id = ?", (new_note, row["id"]))
            cleared += 1
        except Exception:
            continue
    return cleared


def erase_worker_location_data(db, *, company_id: str, worker_id: str) -> dict[str, Any]:
    """Delete GPS trail/live pin and unlink camera events for a worker."""
    cid = str(company_id or "").strip()
    wid = str(worker_id or "").strip()
    out = {
        "samplesDeleted": 0,
        "liveCleared": False,
        "consentsDeleted": 0,
        "accessNotesRedacted": 0,
        "cameraEventsUnlinked": 0,
        "cameraMediaCleared": 0,
        "chatLocationsRedacted": 0,
    }
    if not cid or not wid:
        return out
    try:
        cur = db.execute(
            "DELETE FROM worker_location_samples WHERE worker_id = ? AND company_id = ?",
            (wid, cid),
        )
        out["samplesDeleted"] = int(getattr(cur, "rowcount", 0) or 0)
    except Exception:
        pass
    out["liveCleared"] = clear_live_location(db, wid)
    try:
        cur = db.execute(
            "DELETE FROM data_consents WHERE worker_id = ? AND company_id = ?",
            (wid, cid),
        )
        out["consentsDeleted"] = int(getattr(cur, "rowcount", 0) or 0)
    except Exception:
        pass
    out["accessNotesRedacted"] = _anonymize_access_log_notes(db, wid, cid)
    try:
        cur = db.execute(
            """
            UPDATE camera_ai_events
            SET worker_id = NULL, payload_json = '{}'
            WHERE worker_id = ? AND CAST(company_id AS TEXT) = ?
            """,
            (wid, cid),
        )
        out["cameraEventsUnlinked"] = int(getattr(cur, "rowcount", 0) or 0)
    except Exception:
        pass
    try:
        like = f"%{wid}%"
        cur = db.execute(
            """
            UPDATE camera_escalations
            SET snapshot_b64 = '', clip_b64 = '', snapshot_clear_b64 = '', clip_clear_b64 = ''
            WHERE company_id = ? AND details_json LIKE ?
            """,
            (cid, like),
        )
        out["cameraMediaCleared"] = int(getattr(cur, "rowcount", 0) or 0)
    except Exception:
        try:
            cur = db.execute(
                """
                UPDATE camera_escalations
                SET snapshot_b64 = '', clip_b64 = ''
                WHERE company_id = ? AND details_json LIKE ?
                """,
                (cid, like),
            )
            out["cameraMediaCleared"] = int(getattr(cur, "rowcount", 0) or 0)
        except Exception:
            pass
    try:
        cur = db.execute(
            """
            UPDATE chat_messages
            SET body = '@location|redacted'
            WHERE company_id = ? AND worker_id = ? AND body LIKE '@location|%'
            """,
            (cid, wid),
        )
        out["chatLocationsRedacted"] = int(getattr(cur, "rowcount", 0) or 0)
    except Exception:
        out["chatLocationsRedacted"] = 0
    return out


def apply_gdpr_erasure_if_needed(db, request_row) -> dict[str, Any] | None:
    kind = str(_row_get(request_row, "request_type", "") or "").strip().lower()
    if kind not in ERASURE_REQUEST_TYPES:
        return None
    return erase_worker_location_data(
        db,
        company_id=str(_row_get(request_row, "company_id", "") or ""),
        worker_id=str(_row_get(request_row, "worker_id", "") or ""),
    )


def grant_location_consent_for_tests(
    db, *, worker_id: str, company_id: str, consent_type: str = "privacy_app"
) -> None:
    wid = str(worker_id)
    cid = str(company_id)
    try:
        db.execute(
            "DELETE FROM data_consents WHERE worker_id = ? AND consent_type = ?",
            (wid, consent_type),
        )
    except Exception:
        pass
    db.execute(
        """
        INSERT INTO data_consents (
            id, worker_id, company_id, consent_type, granted, granted_at, version
        ) VALUES (?, ?, ?, ?, 1, datetime('now'), '1.0')
        """,
        (f"dc-{wid}-{consent_type}"[:64], wid, cid, consent_type),
    )


def grant_location_legal_ack_for_tests(db, *, company_id: str) -> None:
    cid = str(company_id)
    try:
        db.execute(
            "ALTER TABLE companies ADD COLUMN location_tracking_legal_ack INTEGER NOT NULL DEFAULT 0"
        )
    except Exception:
        pass
    try:
        db.execute(
            "ALTER TABLE companies ADD COLUMN location_tracking_enabled INTEGER NOT NULL DEFAULT 1"
        )
    except Exception:
        pass
    db.execute(
        """
        UPDATE companies
        SET location_tracking_enabled = 1, location_tracking_legal_ack = 1
        WHERE id = ?
        """,
        (cid,),
    )


def apply_location_tracking_update(
    db,
    *,
    company_id: str,
    enabled: bool | None = None,
    legal_ack: bool = False,
) -> tuple[bool, str]:
    """Turn live GPS on only with Geschäftsführung / Betriebsrat legal ack."""
    cid = str(company_id or "").strip()
    if not cid:
        return False, "company_id_required"
    prev_on = company_location_tracking_enabled(db, cid)
    prev_ack = company_location_legal_ack(db, cid)
    want = prev_on if enabled is None else bool(enabled)
    ack = bool(legal_ack) or prev_ack
    if want and not ack:
        return False, "location_tracking_legal_ack_required"
    try:
        db.execute(
            """
            UPDATE companies
            SET location_tracking_enabled = ?, location_tracking_legal_ack = ?
            WHERE id = ?
            """,
            (1 if want else 0, 1 if ack else 0, cid),
        )
    except Exception:
        return False, "location_tracking_update_failed"
    return True, ""
