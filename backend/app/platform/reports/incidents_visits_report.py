"""Incidents + active visitors PDF for email reporting."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas as rl_canvas


def _company_id_filter(user: dict[str, Any]) -> str | None:
    cid = str(user.get("company_id") or "").strip()
    if str(user.get("role") or "") == "superadmin" and not cid:
        return None
    return cid or None


def fetch_incidents_rows(db, company_id: str | None, *, limit: int = 200) -> list[list[str]]:
    if company_id:
        rows = db.execute(
            """
            SELECT incident_type, severity, status, description, created_at, resolved_at
            FROM incidents WHERE company_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT incident_type, severity, status, description, created_at, resolved_at
            FROM incidents ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        [
            str(r["incident_type"] or ""),
            str(r["severity"] or ""),
            str(r["status"] or ""),
            (str(r["description"] or ""))[:72],
            str(r["created_at"] or "")[:19],
            str(r["resolved_at"] or "")[:19] if r["resolved_at"] else "—",
        ]
        for r in rows
    ]


def fetch_visitor_rows(db, company_id: str | None, *, limit: int = 150) -> list[list[str]]:
    sql_base = """
        SELECT first_name, last_name, visitor_company, visit_purpose, host_name, valid_until, site
        FROM workers
        WHERE deleted_at IS NULL
          AND lower(COALESCE(worker_type, '')) = 'visitor'
          AND lower(COALESCE(status, '')) = 'aktiv'
    """
    if company_id:
        rows = db.execute(sql_base + " AND company_id = ? ORDER BY valid_until ASC LIMIT ?", (company_id, limit)).fetchall()
    else:
        rows = db.execute(sql_base + " ORDER BY valid_until ASC LIMIT ?", (limit,)).fetchall()
    return [
        [
            f"{r['first_name'] or ''} {r['last_name'] or ''}".strip(),
            str(r["visitor_company"] or ""),
            (str(r["visit_purpose"] or ""))[:36],
            str(r["host_name"] or ""),
            str(r["valid_until"] or "")[:19],
            str(r["site"] or ""),
        ]
        for r in rows
    ]


def _draw_table(pdf, pw, ph, margin, y_start, title, headers, rows):
    col_count = len(headers)
    col_width = (pw - 2 * margin) / max(1, col_count)
    y = y_start

    def header_block():
        nonlocal y
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(margin, y, title[:90])
        y -= 14
        pdf.setFont("Helvetica-Bold", 7)
        for idx, h in enumerate(headers):
            pdf.drawString(margin + idx * col_width, y, str(h)[:26])
        y -= 10
        pdf.line(margin, y, pw - margin, y)
        y -= 8
        pdf.setFont("Helvetica", 7)

    header_block()
    for row in rows:
        if y < 40:
            pdf.showPage()
            y = ph - margin
            header_block()
        for idx, cell in enumerate(row[:col_count]):
            pdf.drawString(margin + idx * col_width, y, str(cell if cell is not None else "")[:30])
        y -= 10
    if not rows:
        pdf.drawString(margin, y, "—")
        y -= 12
    return y - 8


def build_incidents_visits_pdf(db, user: dict[str, Any], company_name: str) -> bytes:
    company_id = _company_id_filter(user)
    period = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    incidents = fetch_incidents_rows(db, company_id)
    visitors = fetch_visitor_rows(db, company_id)

    page_size = landscape(A4)
    pw, ph = page_size
    buffer = io.BytesIO()
    pdf = rl_canvas.Canvas(buffer, pagesize=page_size)
    margin = 36
    y = ph - margin
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(margin, y, "SUPPIX — Incidents & Visitors")
    y -= 12
    pdf.setFont("Helvetica", 8)
    pdf.drawString(margin, y, f"{company_name} · {period}")
    y -= 18

    y = _draw_table(
        pdf,
        pw,
        ph,
        margin,
        y,
        "Incidents / الحوادث",
        ["Type", "Severity", "Status", "Description", "Created", "Resolved"],
        incidents,
    )
    if y < 80:
        pdf.showPage()
        y = ph - margin
    _draw_table(
        pdf,
        pw,
        ph,
        margin,
        y,
        "Visitors on site / الزوار",
        ["Name", "Company", "Purpose", "Host", "Valid until", "Site"],
        visitors,
    )
    pdf.save()
    return buffer.getvalue()
