"""Camera recording legal readiness gate (separate from GPS / face-match)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(raw: str | None) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _validity_state(valid_until: str) -> tuple[bool, str | None]:
    """Return (expired_or_invalid, reason). Empty valid_until means no expiry."""
    text = str(valid_until or "").strip()
    if not text:
        return False, None
    dt = _parse_iso(text)
    if dt is None:
        return True, "camera_recording_legal_ack_invalid_until"
    if dt < datetime.now(timezone.utc):
        return True, "camera_recording_legal_ack_expired"
    return False, None


def ensure_camera_legal_schema(db) -> None:
    try:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS company_camera_legal (
                company_id TEXT PRIMARY KEY,
                recording_enabled INTEGER NOT NULL DEFAULT 0,
                legal_ack INTEGER NOT NULL DEFAULT 0,
                legal_basis_text TEXT NOT NULL DEFAULT '',
                legal_basis_version TEXT NOT NULL DEFAULT '1',
                scope_json TEXT NOT NULL DEFAULT '[]',
                acknowledged_by TEXT NOT NULL DEFAULT '',
                acknowledged_at TEXT NOT NULL DEFAULT '',
                valid_until TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        db.commit()
    except Exception:
        pass


def get_camera_legal(db, company_id: str) -> dict[str, Any]:
    ensure_camera_legal_schema(db)
    cid = str(company_id or "").strip()
    if not cid:
        return {"ok": False, "recordingAllowed": False, "reason": "missing_company"}
    row = db.execute(
        "SELECT * FROM company_camera_legal WHERE company_id = ?",
        (cid,),
    ).fetchone()
    if not row:
        return {
            "ok": True,
            "companyId": cid,
            "recordingEnabled": False,
            "legalAck": False,
            "recordingAllowed": False,
            "reason": "camera_recording_legal_ack_required",
        }
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    def g(k, default=""):
        return row[k] if k in keys else default

    enabled = str(g("recording_enabled", 0)) in {"1", "true", "True"}
    ack = str(g("legal_ack", 0)) in {"1", "true", "True"}
    valid_until = str(g("valid_until", "") or "")
    expired, expiry_reason = _validity_state(valid_until)
    allowed = enabled and ack and not expired
    reason = None
    if not ack:
        reason = "camera_recording_legal_ack_required"
    elif not enabled:
        reason = "camera_recording_disabled"
    elif expired:
        reason = expiry_reason
    return {
        "ok": True,
        "companyId": cid,
        "recordingEnabled": enabled,
        "legalAck": ack,
        "legalBasisText": str(g("legal_basis_text", "") or ""),
        "legalBasisVersion": str(g("legal_basis_version", "1") or "1"),
        "scopeJson": str(g("scope_json", "[]") or "[]"),
        "acknowledgedBy": str(g("acknowledged_by", "") or ""),
        "acknowledgedAt": str(g("acknowledged_at", "") or ""),
        "validUntil": valid_until,
        "expired": expired,
        "recordingAllowed": allowed,
        "reason": reason,
    }


def set_camera_legal(
    db,
    company_id: str,
    *,
    recording_enabled: bool,
    legal_ack: bool,
    actor: str,
    legal_basis_text: str = "",
    legal_basis_version: str = "1",
    scope_json: str = "[]",
    valid_until: str = "",
) -> dict[str, Any]:
    ensure_camera_legal_schema(db)
    cid = str(company_id or "").strip()
    if not cid:
        return {"ok": False, "error": "missing_company"}
    if recording_enabled and not legal_ack:
        return {"ok": False, "error": "camera_recording_legal_ack_required"}
    basis = str(legal_basis_text or "").strip()
    if recording_enabled and legal_ack and len(basis) < 8:
        return {"ok": False, "error": "legal_basis_text_required"}
    until = str(valid_until or "").strip()
    if until:
        bad, why = _validity_state(until)
        # Reject already-expired or unparseable dates at write time.
        if bad:
            return {"ok": False, "error": why or "camera_recording_legal_ack_invalid_until"}
    now = _now_iso()
    db.execute(
        """
        INSERT INTO company_camera_legal (
            company_id, recording_enabled, legal_ack, legal_basis_text, legal_basis_version,
            scope_json, acknowledged_by, acknowledged_at, valid_until, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(company_id) DO UPDATE SET
            recording_enabled = excluded.recording_enabled,
            legal_ack = excluded.legal_ack,
            legal_basis_text = excluded.legal_basis_text,
            legal_basis_version = excluded.legal_basis_version,
            scope_json = excluded.scope_json,
            acknowledged_by = excluded.acknowledged_by,
            acknowledged_at = excluded.acknowledged_at,
            valid_until = excluded.valid_until,
            updated_at = excluded.updated_at
        """,
        (
            cid,
            1 if recording_enabled else 0,
            1 if legal_ack else 0,
            str(legal_basis_text or "")[:4000],
            str(legal_basis_version or "1")[:64],
            str(scope_json or "[]")[:4000],
            str(actor or "")[:200],
            now if legal_ack else "",
            until[:64],
            now,
        ),
    )
    db.commit()
    return get_camera_legal(db, cid)


def allow_camera_evidence(db, company_id: str) -> tuple[bool, str | None]:
    status = get_camera_legal(db, company_id)
    if status.get("recordingAllowed"):
        return True, None
    return False, str(status.get("reason") or "camera_recording_not_allowed")
