"""PDF reports for camera incidents and nightly digests."""
from __future__ import annotations

import base64
import io
from datetime import datetime, timezone
from typing import Any


def _decode_jpeg(b64: str | None) -> bytes | None:
    raw = str(b64 or "").strip()
    if not raw:
        return None
    if raw.startswith("data:"):
        comma = raw.find(",")
        raw = raw[comma + 1 :] if comma >= 0 else raw
    try:
        data = base64.b64decode(raw, validate=False)
        return data if data[:3] == b"\xff\xd8\xff" or len(data) > 100 else data
    except Exception:
        return None


def build_camera_incident_pdf(
    *,
    company_name: str,
    camera_id: str,
    camera_name: str,
    location: str,
    event_type: str,
    created_at: str,
    alerts: list[dict[str, Any]],
    snapshot_b64: str | None = None,
    worker_id: str | None = None,
    lang: str = "de",
) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    buffer = io.BytesIO()
    page_w, page_h = A4
    pdf = rl_canvas.Canvas(buffer, pagesize=A4)
    y = page_h - 20 * mm
    margin = 18 * mm

    def line(text: str, *, bold: bool = False, size: int = 10) -> None:
        nonlocal y
        if y < 30 * mm:
            pdf.showPage()
            y = page_h - 20 * mm
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        pdf.drawString(margin, y, str(text)[:120])
        y -= 5.5 * mm

    title = "Kamera-Sicherheitsbericht" if lang != "ar" else "تقرير أمن الكاميرا"
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(margin, y, title[:80])
    y -= 8 * mm
    line(f"Firma / Company: {company_name or '-'}", size=9)
    line(f"Erstellt / Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", size=9)
    y -= 3 * mm
    line("Vorfall / Incident", bold=True, size=11)
    line(f"  Kamera: {camera_name or camera_id} ({camera_id})", size=9)
    if location:
        line(f"  Standort: {location}", size=9)
    line(f"  Ereignis: {event_type}", size=9)
    line(f"  Zeit: {created_at}", size=9)
    if worker_id:
        line(f"  Mitarbeiter-ID: {worker_id}", size=9)
    if alerts:
        line("Erkannte Verstöße / Alerts", bold=True, size=11)
        for alert in alerts[:8]:
            sev = str(alert.get("severity") or "info").upper()
            msg = str(alert.get("message") or alert.get("type") or "")
            line(f"  [{sev}] {msg}", size=9)

    jpeg = _decode_jpeg(snapshot_b64)
    if jpeg:
        try:
            img = ImageReader(io.BytesIO(jpeg))
            iw, ih = img.getSize()
            max_w = page_w - 2 * margin
            max_h = 90 * mm
            scale = min(max_w / max(iw, 1), max_h / max(ih, 1), 1.0)
            draw_w, draw_h = iw * scale, ih * scale
            if y - draw_h < 25 * mm:
                pdf.showPage()
                y = page_h - 20 * mm
            y -= 4 * mm
            line("Snapshot", bold=True, size=11)
            y -= draw_h
            pdf.drawImage(img, margin, y, width=draw_w, height=draw_h, preserveAspectRatio=True)
            y -= 6 * mm
        except Exception:
            pass

    pdf.save()
    return buffer.getvalue()


def build_camera_digest_pdf(
    *,
    company_name: str,
    period_label: str,
    incidents: list[dict[str, Any]],
    offline_cameras: list[dict[str, Any]],
    lang: str = "de",
) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas

    buffer = io.BytesIO()
    page_w, page_h = A4
    pdf = rl_canvas.Canvas(buffer, pagesize=A4)
    y = page_h - 20 * mm
    margin = 18 * mm

    def line(text: str, *, bold: bool = False, size: int = 10) -> None:
        nonlocal y
        if y < 25 * mm:
            pdf.showPage()
            y = page_h - 20 * mm
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        pdf.drawString(margin, y, str(text)[:120])
        y -= 5.5 * mm

    title = "Kamera-Nachtbericht" if lang != "ar" else "تقرير الكameras الليلي"
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(margin, y, title[:80])
    y -= 8 * mm
    line(f"Firma: {company_name or '-'}", size=9)
    line(f"Zeitraum: {period_label}", size=9)
    line(f"Erstellt: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", size=9)
    y -= 3 * mm

    line(f"Verstöße / Vorfälle ({len(incidents)})", bold=True, size=11)
    if not incidents:
        line("  Keine sicherheitsrelevanten Kamera-Ereignisse.", size=9)
    else:
        for item in incidents[:40]:
            cam = str(item.get("camera_name") or item.get("camera_id") or "-")
            ev = str(item.get("event_type") or "event")
            ts = str(item.get("created_at") or "")[:19]
            alerts = item.get("alerts") or []
            alert_txt = "; ".join(str(a.get("message") or a.get("type") or "") for a in alerts[:2])
            line(f"  {ts} · {cam} · {ev}", size=9)
            if alert_txt:
                line(f"     {alert_txt[:100]}", size=8)

    y -= 2 * mm
    line(f"Offline-Kameras ({len(offline_cameras)})", bold=True, size=11)
    if not offline_cameras:
        line("  Alle registrierten Kameras meldeten Heartbeats.", size=9)
    else:
        for cam in offline_cameras[:20]:
            line(
                f"  {cam.get('name') or cam.get('id')} — zuletzt {cam.get('lastSeenAt') or 'nie'}",
                size=9,
            )

    pdf.save()
    return buffer.getvalue()
