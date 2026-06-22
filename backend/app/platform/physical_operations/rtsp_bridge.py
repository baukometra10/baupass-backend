"""RTSP / NVR bridge → camera_ai_events (local agent or webhook)."""
from __future__ import annotations

import os
import secrets
from typing import Any


def authorize_rtsp_bridge_request(request, db) -> tuple[dict[str, Any] | None, str | None, int | None]:
    """Device API key, bridge token, or admin session (via caller)."""
    from werkzeug.security import check_password_hash

    from backend.server import clean_id_input

    expected = (os.getenv("BAUPASS_RTSP_BRIDGE_TOKEN") or "").strip()
    token = (request.headers.get("X-WorkPass-Rtsp-Token") or request.headers.get("X-WorkPass-Camera-Token") or "").strip()
    if expected and token and secrets.compare_digest(expected, token):
        company_id = clean_id_input(request.headers.get("X-WorkPass-Company-Id") or "")
        return (
            {"role": "rtsp-bridge", "id": "rtsp-bridge", "company_id": company_id or None},
            company_id or None,
            None,
        )

    raw_key = (request.headers.get("X-Device-API-Key") or "").strip()
    if raw_key:
        for dev in db.execute("SELECT * FROM devices WHERE COALESCE(api_key_hash, '') != ''").fetchall():
            if check_password_hash(dev["api_key_hash"], raw_key):
                return (
                    {"role": "device", "id": str(dev["id"]), "company_id": str(dev["company_id"])},
                    str(dev["company_id"]),
                    None,
                )
        return None, None, 401

    from flask import g

    user = getattr(g, "current_user", None)
    if user and str(user.get("role") or "") in {"superadmin", "company-admin", "turnstile"}:
        cid = str(user.get("company_id") or "").strip() or None
        if user.get("role") == "superadmin":
            cid = clean_id_input(request.headers.get("X-WorkPass-Company-Id") or request.args.get("company_id") or "") or cid
        return user, cid, None

    return None, None, 401


def _enrich_face_match(db, company_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    worker_id = str(data.get("worker_id") or data.get("workerId") or "").strip()
    snapshot_b64 = str(
        data.get("image_base64") or data.get("snapshot_base64") or data.get("photo_base64") or ""
    ).strip()
    if worker_id:
        row = db.execute(
            "SELECT id, photo_data FROM workers WHERE id = ? AND company_id = ? AND deleted_at IS NULL",
            (worker_id, company_id),
        ).fetchone()
        data["worker_id"] = worker_id
        photo = str(row["photo_data"] or "").strip() if row else ""
        if snapshot_b64 and photo:
            try:
                from backend.app.platform.physical_operations.azure_face import verify_worker_snapshot

                azure_match = verify_worker_snapshot(photo, snapshot_b64)
                if azure_match is not None:
                    data["face_match"] = azure_match
                    data["face_match_source"] = "azure"
                    return data
            except Exception:
                pass
        data["face_match"] = bool(row and photo)
        if data["face_match"]:
            data["face_match_source"] = "worker_photo"
    elif "face_match" not in data:
        data["face_match"] = None
    return data


def ingest_rtsp_camera_event(db, company_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from backend.app.platform.physical_operations.camera_ai import ingest_camera_event

    company_id = str(company_id or "").strip()
    if not company_id:
        return {"ok": False, "error": "missing_company_id"}
    enriched = _enrich_face_match(db, company_id, payload)
    result = ingest_camera_event(db, company_id, enriched)
    return {"ok": True, **result}
