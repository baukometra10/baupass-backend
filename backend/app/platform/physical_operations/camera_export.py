"""Export camera escalation packs as PDF or ZIP evidence bundle."""
from __future__ import annotations

import base64
import io
import json
import zipfile
from typing import Any

from .camera_escalation import get_escalation


def _decode_media(b64: str | None) -> bytes | None:
    raw = str(b64 or "").strip()
    if not raw:
        return None
    if raw.startswith("data:"):
        comma = raw.find(",")
        raw = raw[comma + 1 :] if comma >= 0 else raw
    try:
        data = base64.b64decode(raw, validate=False)
        return data if data else None
    except Exception:
        return None


def _build_incident_pdf_for_escalation(
    db,
    company_id: str,
    item: dict[str, Any],
) -> bytes:
    from backend.app.platform.reports.camera_pdf import build_camera_incident_pdf

    company = db.execute("SELECT name FROM companies WHERE id = ?", (str(company_id),)).fetchone()
    company_name = str(company["name"] if company else company_id)
    details = item.get("details") or {}
    analysis = details.get("analysis") or {}
    alerts = list(analysis.get("alerts") or [])
    police = details.get("police") or {
        "station": {
            "name": item.get("policeName"),
            "address": item.get("policeAddress"),
            "phone": item.get("policePhone"),
            "city": item.get("policeCity"),
            "country": item.get("policeCountry"),
        }
    }
    return build_camera_incident_pdf(
        company_name=company_name,
        camera_id=str(item.get("cameraId") or ""),
        camera_name=str(details.get("cameraName") or item.get("cameraId") or ""),
        location=str(details.get("location") or item.get("siteKey") or ""),
        event_type=str(details.get("eventType") or item.get("severity") or "critical"),
        created_at=str(item.get("createdAt") or ""),
        alerts=alerts,
        snapshot_b64=item.get("snapshotBase64"),
        worker_id=None,
        police_suggestion=police,
        history=item.get("history") or [],
        disclaimer="Kein automatischer Notruf — menschliche Freigabe erforderlich. / No auto police dial.",
    )


def build_escalation_export_zip(db, company_id: str, escalation_id: str) -> bytes:
    """Build ZIP with incident.pdf, optional snapshot.jpg / clip.mp4, and meta.json."""
    item = get_escalation(db, company_id, escalation_id, include_media=True)
    if not item:
        raise ValueError("escalation_not_found")

    pdf_bytes = _build_incident_pdf_for_escalation(db, company_id, item)
    snap = _decode_media(item.get("snapshotBase64"))
    clip = _decode_media(item.get("clipBase64"))

    meta = {
        "escalationId": item.get("id"),
        "companyId": company_id,
        "cameraId": item.get("cameraId"),
        "eventId": item.get("eventId"),
        "severity": item.get("severity"),
        "status": item.get("status"),
        "siteKey": item.get("siteKey"),
        "createdAt": item.get("createdAt"),
        "policeName": item.get("policeName"),
        "policePhone": item.get("policePhone"),
        "policeAddress": item.get("policeAddress"),
        "ackCount": item.get("ackCount"),
        "ackUsers": item.get("ackUsers"),
        "chainStage": item.get("chainStage"),
        "dualAckRequired": item.get("dualAckRequired"),
        "hasSnapshot": bool(snap),
        "hasClip": bool(clip),
        "autoDial": False,
        "history": item.get("history") or [],
        "details": {
            k: v
            for k, v in (item.get("details") or {}).items()
            if k != "analysis" or True
        },
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("incident.pdf", pdf_bytes)
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
        if snap:
            zf.writestr("snapshot.jpg", snap)
        if clip:
            zf.writestr("clip.mp4", clip)
    return buf.getvalue()


def build_escalation_export_pdf(db, company_id: str, escalation_id: str) -> bytes:
    item = get_escalation(db, company_id, escalation_id, include_media=True)
    if not item:
        raise ValueError("escalation_not_found")
    return _build_incident_pdf_for_escalation(db, company_id, item)
