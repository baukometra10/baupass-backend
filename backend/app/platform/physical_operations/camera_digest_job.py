"""Nightly camera digest — violations + offline summary per company."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.platform.notifications.company_mitteilung import _company_admin_recipients
from backend.app.platform.physical_operations.camera_registry import serialize_camera


def _night_window_utc(hours_back: int = 12) -> tuple[str, str]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=max(1, hours_back))
    return start.strftime("%Y-%m-%dT%H:%M:%S"), end.strftime("%Y-%m-%dT%H:%M:%S")


def _parse_payload(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(str(raw or "{}"))
    except Exception:
        return {}


def run_camera_nightly_digest(db, *, hours_back: int | None = None) -> dict[str, Any]:
    if str(os.getenv("BAUPASS_CAMERA_NIGHTLY_DIGEST", "1")).strip().lower() in {"0", "false", "off", "no"}:
        return {"ok": True, "skipped": True}

    hb = hours_back
    if hb is None:
        hb = max(6, int(os.getenv("BAUPASS_CAMERA_DIGEST_HOURS", "12")))
    start_iso, end_iso = _night_window_utc(hb)
    period_label = f"{start_iso[:16]} UTC – {end_iso[:16]} UTC"

    companies = db.execute(
        """
        SELECT DISTINCT company_id FROM site_cameras
        UNION
        SELECT DISTINCT company_id FROM camera_ai_events
        WHERE created_at >= ?
        """,
        (start_iso,),
    ).fetchall()

    reports_sent = 0
    for crow in companies:
        company_id = str(crow["company_id"])
        if not _company_admin_recipients(db, company_id):
            continue

        company = db.execute("SELECT name FROM companies WHERE id = ?", (company_id,)).fetchone()
        company_name = str(company["name"] if company else company_id)

        event_rows = db.execute(
            """
            SELECT e.*, c.name AS camera_name, c.location AS camera_location
            FROM camera_ai_events e
            LEFT JOIN site_cameras c ON c.id = e.camera_id AND c.company_id = e.company_id
            WHERE e.company_id = ? AND e.created_at >= ?
              AND (e.zone_violation = 1 OR e.ppe_compliant = 0 OR e.event_type IN (
                    'unknown_person', 'tailgating', 'forced_entry', 'ppe_missing', 'restricted_zone'
                  ))
            ORDER BY e.created_at DESC
            LIMIT 100
            """,
            (company_id, start_iso),
        ).fetchall()

        incidents: list[dict[str, Any]] = []
        for er in event_rows:
            payload = _parse_payload(er["payload_json"] if "payload_json" in er.keys() else {})
            analysis = payload.get("analysis") or {}
            alerts = analysis.get("alerts") or []
            if not alerts and int(er["zone_violation"] or 0) == 0 and er["ppe_compliant"] not in (0, False):
                continue
            incidents.append(
                {
                    "camera_id": er["camera_id"],
                    "camera_name": er["camera_name"] if "camera_name" in er.keys() else er["camera_id"],
                    "event_type": er["event_type"],
                    "created_at": er["created_at"],
                    "alerts": alerts,
                }
            )

        cam_rows = db.execute(
            "SELECT * FROM site_cameras WHERE company_id = ?",
            (company_id,),
        ).fetchall()
        offline_cameras = [serialize_camera(r) for r in cam_rows if not serialize_camera(r).get("online")]

        if not incidents and not offline_cameras:
            continue

        try:
            from backend.app.platform.reports.camera_pdf import build_camera_digest_pdf
            from backend.app.platform.reports.email_delivery import send_pdf_report_email

            pdf_bytes = build_camera_digest_pdf(
                company_name=company_name,
                period_label=period_label,
                incidents=incidents,
                offline_cameras=offline_cameras,
            )
            summary_lines = []
            for inc in incidents[:5]:
                cam = inc.get("camera_name") or inc.get("camera_id")
                summary_lines.append(f"- {inc.get('created_at', '')[:16]} {cam}: {inc.get('event_type')}")
            if offline_cameras:
                summary_lines.append(f"- {len(offline_cameras)} Kamera(s) offline")
            text_body = (
                f"Kamera-Nachtbericht für {company_name}\n"
                f"Zeitraum: {period_label}\n\n"
                + "\n".join(summary_lines)
                + "\n\nDetails im PDF-Anhang."
            )
            subject = f"WorkPass Kamera-Bericht — {company_name} ({start_iso[:10]})"
            for recipient in _company_admin_recipients(db, company_id):
                ok, _ = send_pdf_report_email(
                    to=recipient,
                    subject=subject,
                    body_text=text_body,
                    pdf_bytes=pdf_bytes,
                    filename=f"camera-digest-{company_id}-{start_iso[:10]}.pdf",
                )
                if ok:
                    reports_sent += 1
            try:
                from backend.app.platform.inbox.events import notify_inbox_changed

                notify_inbox_changed(
                    company_id,
                    source="camera_digest",
                    alert_title="Kamera-Nachtbericht",
                    alert_message=text_body[:240],
                    severity="info",
                )
            except Exception:
                pass
        except Exception:
            continue

    return {"ok": True, "reportsSent": reports_sent, "period": period_label}
