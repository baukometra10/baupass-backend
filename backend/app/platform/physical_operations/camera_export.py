"""Export camera escalation packs as PDF or ZIP evidence bundle."""
from __future__ import annotations

import base64
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

from .camera_escalation import get_escalation
from .camera_watch import get_watch_settings


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
    watch = get_watch_settings(db, company_id)
    privacy = str(watch.get("privacyNotice") or "")[:500]
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
        privacy_notice=privacy or None,
    )


def build_escalation_export_zip(db, company_id: str, escalation_id: str) -> bytes:
    """Build ZIP with incident.pdf, optional snapshot.jpg / clip.mp4, and meta.json."""
    item = get_escalation(db, company_id, escalation_id, include_media=True)
    if not item:
        raise ValueError("escalation_not_found")

    pdf_bytes = _build_incident_pdf_for_escalation(db, company_id, item)
    snap = _decode_media(item.get("snapshotBase64"))
    clip = _decode_media(item.get("clipBase64"))

    watch = get_watch_settings(db, company_id)
    privacy = str(watch.get("privacyNotice") or "")[:500]
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
        "privacyNotice": privacy,
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


def _parse_range_bound(raw: str | None, *, end: bool = False) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return f"{text}T23:59:59.999999Z" if end else f"{text}T00:00:00.000000Z"
    return text


def build_audit_export(
    db,
    company_id: str,
    *,
    from_ts: str | None = None,
    to_ts: str | None = None,
    fmt: str = "json",
    include_media: bool = False,
) -> tuple[bytes, str, str]:
    """Insurer-friendly audit export of escalations in range (no huge media by default).

    Returns (bytes, mimetype, filename).
    """
    cid = str(company_id)
    start = _parse_range_bound(from_ts, end=False)
    end = _parse_range_bound(to_ts, end=True)
    watch = get_watch_settings(db, cid)
    privacy = str(watch.get("privacyNotice") or "")[:500]

    try:
        sql = "SELECT id FROM camera_escalations WHERE company_id = ?"
        params: list[Any] = [cid]
        if start:
            sql += " AND created_at >= ?"
            params.append(start)
        if end:
            sql += " AND created_at <= ?"
            params.append(end)
        sql += " ORDER BY created_at ASC LIMIT 500"
        id_rows = db.execute(sql, tuple(params)).fetchall()
    except Exception:
        id_rows = []

    items: list[dict[str, Any]] = []
    for r in id_rows:
        item = get_escalation(db, cid, str(r["id"]), include_media=bool(include_media))
        if not item:
            continue
        details = item.get("details") or {}
        police = details.get("police") or {
            "station": {
                "name": item.get("policeName"),
                "address": item.get("policeAddress"),
                "phone": item.get("policePhone"),
                "city": item.get("policeCity"),
                "country": item.get("policeCountry"),
            }
        }
        items.append(
            {
                "id": item.get("id"),
                "companyId": cid,
                "cameraId": item.get("cameraId"),
                "cameraName": item.get("cameraName") or details.get("cameraName"),
                "eventId": item.get("eventId"),
                "eventType": item.get("eventType") or details.get("eventType"),
                "severity": item.get("severity"),
                "status": item.get("status"),
                "siteKey": item.get("siteKey"),
                "createdAt": item.get("createdAt"),
                "ageSeconds": item.get("ageSeconds"),
                "chainStage": item.get("chainStage"),
                "chainNextAt": item.get("chainNextAt"),
                "slaLabel": item.get("slaLabel"),
                "hasSnapshot": bool(item.get("hasSnapshot")),
                "hasClip": bool(item.get("hasClip")),
                "falsePositive": bool(item.get("falsePositive")),
                "test": bool(item.get("test") or details.get("test")),
                "policeSuggestion": police,
                "history": item.get("history") or [],
                "ackCount": item.get("ackCount"),
                "ackUsers": item.get("ackUsers"),
                "autoDial": False,
            }
        )

    meta = {
        "companyId": cid,
        "from": start,
        "to": end,
        "exportedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "count": len(items),
        "privacyNotice": privacy,
        "autoDial": False,
        "includeMedia": bool(include_media),
    }
    payload = {"meta": meta, "escalations": items}
    fmt_l = str(fmt or "json").lower()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    if fmt_l == "zip":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("audit.json", json.dumps(payload, ensure_ascii=False, indent=2))
            zf.writestr(
                "README.txt",
                (
                    "WorkPass camera watch audit export\n"
                    "No automatic police dial — assisted suggestion only.\n"
                    f"Privacy notice (excerpt):\n{privacy}\n"
                ),
            )
        return (
            buf.getvalue(),
            "application/zip",
            f"camera-watch-audit-{cid}-{stamp}.zip",
        )
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return raw, "application/json", f"camera-watch-audit-{cid}-{stamp}.json"
