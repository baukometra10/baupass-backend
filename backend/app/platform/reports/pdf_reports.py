"""Generate platform operational reports as PDF (ReportLab)."""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Any


def build_operations_report_pdf(
    *,
    title: str,
    company_name: str,
    snapshot: dict[str, Any],
    guidance: list[dict[str, Any]] | None = None,
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
        pdf.drawString(margin, y, str(text)[:110])
        y -= 5.5 * mm

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(margin, y, title[:80])
    y -= 8 * mm
    line(f"Firma / Company: {company_name or '-'}", size=9)
    line(f"Erstellt / Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", size=9)
    y -= 3 * mm

    kpis = snapshot.get("kpis") or {}
    if kpis:
        line("KPIs", bold=True, size=11)
        for key, label in (
            ("paidTotal", "Bezahlt"),
            ("openTotal", "Offen"),
            ("overdueInvoiceCount", "Überfällige Rechnungen"),
            ("overdueTotal", "Überfällig (Summe)"),
            ("lockedCompanies", "Gesperrte Firmen"),
            ("workersOnSite", "Mitarbeiter auf Baustelle"),
        ):
            if key in kpis or key.replace("workersOnSite", "") == key:
                val = kpis.get(key, snapshot.get(key))
                if val is not None:
                    line(f"  {label}: {val}")

    hr = snapshot.get("hrCompliance") or {}
    if hr:
        line("Lohn & Compliance", bold=True, size=11)
        line(f"  Mitarbeiter gesamt: {hr.get('workersTotal', 0)}", size=9)
        line(f"  Pflichtdokumente fehlend/abgelaufen: {hr.get('workersMissingRequiredDocs', 0)}", size=9)
        line(f"  Abgelaufene Dokumente (Mitarbeiter): {hr.get('workersWithExpiredDocs', 0)}", size=9)
        line(f"  Läuft in 14 Tagen ab: {hr.get('workersExpiringDocs14d', 0)}", size=9)
        line(f"  Lohnabrechnungen ({hr.get('period', '-')}): {hr.get('payrollDocsThisMonth', 0)}", size=9)
        line(f"  Posteingang ungelesen: {hr.get('inboxUnread', 0)}", size=9)
        datev_ok = "ja" if hr.get("datevConnected") else "nein"
        line(f"  DATEV verbunden: {datev_ok}", size=9)
        y -= 2 * mm

    access = snapshot.get("accessDaily") or []
    if access:
        line("Zutritte (7 Tage)", bold=True, size=11)
        for row in access[-7:]:
            line(
                f"  {row.get('day', '-')}: Check-in {row.get('checkIn', 0)} / Check-out {row.get('checkOut', 0)}",
                size=9,
            )

    sec = snapshot.get("security") or {}
    if sec:
        line("Sicherheit", bold=True, size=11)
        line(f"  Offene Findings: {sec.get('openFindings', len(sec.get('findings') or []))}", size=9)

    if guidance:
        line("Empfohlene Maßnahmen / Guidance", bold=True, size=11)
        for item in guidance[:12]:
            pri = str(item.get("priority") or "info").upper()
            title_ar = str(item.get("titleAr") or item.get("title") or "")
            title_de = str(item.get("titleDe") or "")
            line(f"  [{pri}] {title_de or title_ar}", size=9)
            body = str(item.get("detailAr") or item.get("detailDe") or item.get("detail") or "")
            if body:
                line(f"     {body[:100]}", size=8)

    extra = snapshot.get("commandCenter") or snapshot.get("siteIntelligence")
    if extra and not kpis:
        line("Operations Snapshot (JSON excerpt)", bold=True, size=11)
        excerpt = json.dumps(extra, ensure_ascii=False)[:600]
        for chunk in [excerpt[i : i + 90] for i in range(0, len(excerpt), 90)]:
            line(chunk, size=8)

    pdf.save()
    return buffer.getvalue()
