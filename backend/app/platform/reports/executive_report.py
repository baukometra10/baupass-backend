"""Executive summary PDF for leadership (Phase B)."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any


def build_executive_summary_pdf(
    *,
    company_name: str,
    snapshot: dict[str, Any],
    reporting_summary: dict[str, Any] | None = None,
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

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(margin, y, "WorkPass Executive Summary")
    y -= 10 * mm
    line(f"Organization: {company_name or '-'}", size=9)
    line(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", size=9)
    y -= 4 * mm

    kpis = (reporting_summary or {}).get("kpis") or snapshot.get("kpis") or {}
    if kpis:
        line("Financial & compliance KPIs", bold=True, size=12)
        for key, label in (
            ("paidTotal", "Paid total"),
            ("openTotal", "Open total"),
            ("overdueInvoiceCount", "Overdue invoices"),
            ("overdueTotal", "Overdue amount"),
            ("lockedCompanies", "Locked tenants"),
            ("suspensionsLast30d", "Auto-suspensions (30d)"),
        ):
            if key in kpis:
                line(f"  {label}: {kpis[key]}")

    on_site = snapshot.get("workersOnSite") or snapshot.get("onSiteCount")
    if on_site is not None:
        line("Operations", bold=True, size=12)
        line(f"  Personnel on site: {on_site}")

    hr = snapshot.get("hrCompliance") or {}
    if hr:
        line("HR / compliance snapshot", bold=True, size=12)
        for k, v in list(hr.items())[:12]:
            line(f"  {k}: {v}")

    guidance = snapshot.get("guidance") or []
    if isinstance(guidance, list) and guidance:
        line("Top recommendations", bold=True, size=12)
        for item in guidance[:5]:
            if isinstance(item, dict):
                line(f"  - {item.get('title') or item.get('message') or item}")

    line("— End of executive summary —", size=8)
    pdf.save()
    return buffer.getvalue()
