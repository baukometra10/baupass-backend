"""Generic tabular PDF reports (invoices, companies, exports)."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any, Sequence

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas as rl_canvas


def build_table_report_pdf(
    *,
    title: str,
    subtitle: str = "",
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    landscape_mode: bool = False,
) -> bytes:
    page_size = landscape(A4) if landscape_mode else A4
    pw, ph = page_size
    buffer = io.BytesIO()
    pdf = rl_canvas.Canvas(buffer, pagesize=page_size)
    margin = 36
    col_count = max(1, len(headers))
    col_width = (pw - 2 * margin) / col_count

    def draw_header(y_pos: float) -> float:
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(margin, y_pos, str(title)[:90])
        y_pos -= 14
        if subtitle:
            pdf.setFont("Helvetica", 8)
            pdf.drawString(margin, y_pos, str(subtitle)[:120])
            y_pos -= 14
        pdf.setFont("Helvetica-Bold", 7)
        for idx, header in enumerate(headers):
            pdf.drawString(margin + idx * col_width, y_pos, str(header)[:28])
        y_pos -= 8
        pdf.line(margin, y_pos, pw - margin, y_pos)
        return y_pos - 10

    y = ph - margin
    y = draw_header(y)
    pdf.setFont("Helvetica", 7)
    for row in rows:
        if y < 48:
            pdf.showPage()
            y = ph - margin
            y = draw_header(y)
            pdf.setFont("Helvetica", 7)
        for idx, cell in enumerate(row[:col_count]):
            pdf.drawString(margin + idx * col_width, y, str(cell if cell is not None else "")[:32])
        y -= 11
    if not rows:
        pdf.drawString(margin, y, "—")
    pdf.save()
    return buffer.getvalue()
