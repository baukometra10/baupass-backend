"""Workers domain — CSV/PDF export builders."""
from __future__ import annotations

import base64
import io
import textwrap
from datetime import datetime
from typing import Any


def _reportlab_missing() -> dict[str, Any]:
    return {
        "error": {
            "error": "pdf_dependency_missing",
            "message": "Bitte reportlab installieren.",
        },
        "status": 503,
    }


def build_workers_csv_bytes(rows: list[Any]) -> bytes:
    import csv

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "company_id",
            "company_name",
            "subcompany_id",
            "subcompany_name",
            "first_name",
            "last_name",
            "worker_type",
            "insurance_number",
            "role",
            "site",
            "valid_until",
            "visitor_company",
            "visit_purpose",
            "host_name",
            "visit_end_at",
            "status",
            "badge_id",
            "physical_card_id",
            "deleted_at",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["company_id"],
                row["company_name"],
                row["subcompany_id"],
                row["subcompany_name"],
                row["first_name"],
                row["last_name"],
                row["worker_type"],
                row["insurance_number"],
                row["role"],
                row["site"],
                row["valid_until"],
                row["visitor_company"],
                row["visit_purpose"],
                row["host_name"],
                row["visit_end_at"],
                row["status"],
                row["badge_id"],
                row["physical_card_id"],
                row["deleted_at"],
            ]
        )
    return output.getvalue().encode("utf-8-sig")


def build_workers_pdf_bytes(
    rows: list[Any],
    *,
    include_photos: bool,
    period_label: str,
) -> dict[str, Any] | bytes:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas as rl_canvas
    except Exception:
        return _reportlab_missing()

    buffer = io.BytesIO()
    page_width, page_height = A4
    pdf = rl_canvas.Canvas(buffer, pagesize=A4)

    row_height = 44 if include_photos else 13
    photo_size = 36

    def draw_worker_page_header(y):
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(36, y, "SUPPIX - Mitarbeiterliste")
        y -= 16
        pdf.setFont("Helvetica", 9)
        pdf.drawString(
            36,
            y,
            f"Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M')}{period_label} | {len(rows)} Mitarbeiter",
        )
        y -= 20
        pdf.setFont("Helvetica-Bold", 9)
        x_name = 36 + (photo_size + 6 if include_photos else 0)
        pdf.drawString(x_name, y, "Name")
        pdf.drawString(x_name + 170, y, "Firma")
        pdf.drawString(x_name + 310, y, "Subunternehmen")
        pdf.drawString(x_name + 430, y, "Status")
        y -= 10
        pdf.line(36, y, page_width - 36, y)
        y -= 12
        return y

    y = page_height - 42
    y = draw_worker_page_header(y)
    pdf.setFont("Helvetica", 9)

    for row in rows:
        if y < (row_height + 12):
            pdf.showPage()
            y = page_height - 42
            y = draw_worker_page_header(y)
            pdf.setFont("Helvetica", 9)

        x_text = 36
        if include_photos:
            photo_bytes = None
            pd = row["photo_data"] or ""
            if pd.startswith("data:image/") and "," in pd:
                try:
                    b64 = pd.split(",", 1)[1]
                    photo_bytes = base64.b64decode(b64.strip())
                except Exception:
                    photo_bytes = None
            if photo_bytes:
                try:
                    img_buf = io.BytesIO(photo_bytes)
                    img_reader = ImageReader(img_buf)
                    pdf.drawImage(
                        img_reader,
                        36,
                        y - photo_size + 4,
                        width=photo_size,
                        height=photo_size,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
                except Exception:
                    pass
            x_text = 36 + photo_size + 6

        text_y = y - (photo_size // 2 - 4 if include_photos else 0)
        full_name = f"{(row['last_name'] or '').strip()}, {(row['first_name'] or '').strip()}".strip(", ")
        pdf.drawString(x_text, text_y, full_name[:28])
        pdf.drawString(x_text + 170, text_y, str(row["company_name"] or "-")[:22])
        pdf.drawString(x_text + 310, text_y, str(row["subcompany_name"] or "-")[:18])
        pdf.drawString(x_text + 430, text_y, str(row["status"] or "-")[:10])
        y -= row_height

    if not rows:
        pdf.drawString(36, y, "Keine Mitarbeiter gefunden.")

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


def build_attendance_pdf_bytes(
    *,
    date_param: str,
    open_entries: list[dict[str, Any]],
    worker_id_to_company: dict[str, str],
    platform_label: str,
    primary_color: str,
) -> dict[str, Any] | bytes:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as rl_canvas
    except Exception:
        return _reportlab_missing()

    buffer = io.BytesIO()
    page_width, page_height = A4
    pdf = rl_canvas.Canvas(buffer, pagesize=A4)

    def hex_to_rgb(h):
        h = h.lstrip("#")
        return tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))

    try:
        pr, pg, pb = hex_to_rgb(primary_color)
    except Exception:
        pr, pg, pb = 0.059, 0.298, 0.361

    row_height = 16

    def draw_header(y):
        pdf.setFillColorRGB(pr, pg, pb)
        pdf.rect(0, page_height - 56, page_width, 56, fill=1, stroke=0)
        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(36, page_height - 28, f"{platform_label} – Anwesenheitsliste")
        pdf.setFont("Helvetica", 9)
        pdf.drawString(
            36,
            page_height - 44,
            f"Datum: {date_param}  |  Erstellt: {datetime.now().strftime('%d.%m.%Y %H:%M')}  |  {len(open_entries)} aktive Eintritte",
        )

        y = page_height - 72
        pdf.setFillColorRGB(0.95, 0.95, 0.95)
        pdf.rect(36, y - 2, page_width - 72, row_height, fill=1, stroke=0)
        pdf.setFillColorRGB(pr, pg, pb)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(40, y + 2, "Name")
        pdf.drawString(180, y + 2, "Firma")
        pdf.drawString(310, y + 2, "Badge-ID")
        pdf.drawString(390, y + 2, "Eintritt (UTC)")
        pdf.drawString(490, y + 2, "Tor")
        pdf.drawString(550, y + 2, "Dauer (Min)")
        return y - row_height - 4

    y = draw_header(page_height)
    pdf.setFont("Helvetica", 8)
    pdf.setFillColorRGB(0.1, 0.1, 0.1)

    severity_colors = {
        "green": (0.1, 0.6, 0.3),
        "yellow": (0.8, 0.55, 0.0),
        "red": (0.75, 0.1, 0.1),
    }

    for entry in open_entries:
        if y < 40:
            pdf.showPage()
            y = draw_header(page_height)
            pdf.setFont("Helvetica", 8)
            pdf.setFillColorRGB(0.1, 0.1, 0.1)

        sr, sg, sb = severity_colors.get(entry.get("severity", "green"), (0.1, 0.6, 0.3))
        pdf.setFillColorRGB(sr, sg, sb)
        pdf.circle(38, y + 5, 3, fill=1, stroke=0)
        pdf.setFillColorRGB(0.1, 0.1, 0.1)

        pdf.drawString(44, y + 2, str(entry.get("name", ""))[:26])
        company_name = worker_id_to_company.get(entry.get("workerId", ""), "")
        pdf.drawString(184, y + 2, str(company_name)[:20])
        pdf.drawString(314, y + 2, str(entry.get("badgeId", ""))[:14])
        ts = str(entry.get("timestamp", ""))[:16]
        pdf.drawString(394, y + 2, ts)
        pdf.drawString(494, y + 2, str(entry.get("gate", ""))[:12])
        pdf.drawString(554, y + 2, str(entry.get("openMinutes", "")))

        y -= row_height

    if not open_entries:
        pdf.setFont("Helvetica", 10)
        pdf.setFillColorRGB(0.4, 0.4, 0.4)
        pdf.drawString(36, y + 20, "Keine aktiven Eintritte für dieses Datum.")

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


def _hex_to_rgb(hex_color: str, fallback=(0.06, 0.35, 0.42)) -> tuple[float, float, float]:
    raw = str(hex_color or "").strip().lstrip("#")
    if len(raw) != 6:
        return fallback
    try:
        return tuple(int(raw[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    except Exception:
        return fallback


def _escape_pdf_text(value: str) -> str:
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_iso_date(value: str) -> str:
    raw = str(value or "").strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
        except Exception:
            pass
    return raw or "—"


def _logo_flowable(logo_data: str, *, max_height_mm: float = 16.0):
    raw = str(logo_data or "").strip()
    if not raw.lower().startswith("data:image/"):
        return None
    try:
        from reportlab.lib.units import mm
        from reportlab.platypus import Image

        _header, payload = raw.split(",", 1)
        blob = base64.b64decode(payload, validate=False)
        if not blob:
            return None
        bio = io.BytesIO(blob)
        img = Image(bio)
        max_h = max_height_mm * mm
        if img.imageHeight > max_h:
            ratio = max_h / float(img.imageHeight)
            img.drawWidth = img.imageWidth * ratio
            img.drawHeight = max_h
        return img
    except Exception:
        return None


def _signature_flowable(signature_data: str, signature_name: str):
    raw = str(signature_data or "").strip()
    if raw.lower().startswith("data:image/"):
        try:
            from reportlab.lib.units import mm
            from reportlab.platypus import Image

            _header, payload = raw.split(",", 1)
            blob = base64.b64decode(payload, validate=False)
            if blob:
                bio = io.BytesIO(blob)
                img = Image(bio, width=62 * mm, height=20 * mm)
                img.hAlign = "CENTER"
                return img
        except Exception:
            pass
    name = str(signature_name or "").strip()
    if name:
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph

        styles = getSampleStyleSheet()
        return Paragraph(
            f"<para align='center'><i><font size='16'>{_escape_pdf_text(name)}</font></i></para>",
            styles["Normal"],
        )
    return None


def build_leave_request_pdf_bytes(data: dict[str, Any]) -> dict[str, Any] | bytes:
    """Professional leave request PDF with company logo and worker signature."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except Exception:
        return _reportlab_missing()

    worker_name = (
        str(data.get("worker_name") or "").strip()
        or f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
        or str(data.get("worker_id") or "—")
    )
    company_name = str(
        data.get("companyName") or data.get("company_name") or data.get("portal_display_name") or "WorkPass"
    ).strip()
    req_type = str(data.get("type") or "-")
    type_label = {
        "urlaub": "Urlaub",
        "krank": "Krankmeldung",
        "sonstiges": "Sonstiger Antrag",
    }.get(req_type, req_type)
    status = str(data.get("status") or "ausstehend")
    status_label = {"ausstehend": "Ausstehend", "genehmigt": "Genehmigt", "abgelehnt": "Abgelehnt"}.get(
        status, status
    )
    accent = str(data.get("accent") or data.get("branding_accent_color") or "#0f4c75")
    pr, pg, pb = _hex_to_rgb(accent)
    logo_data = str(data.get("logoData") or data.get("branding_logo_data") or "")
    signature_data = str(data.get("worker_signature_data") or "")
    signature_name = str(data.get("worker_signature_name") or worker_name).strip()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"Abwesenheitsantrag {worker_name}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "LeaveTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.Color(pr, pg, pb),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "LeaveSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#5a6578"),
    )
    label_style = ParagraphStyle(
        "LeaveLabel",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#6b7280"),
        spaceAfter=2,
    )
    value_style = ParagraphStyle(
        "LeaveValue",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#111827"),
        spaceAfter=8,
    )
    note_style = ParagraphStyle(
        "LeaveNote",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#374151"),
    )

    logo = _logo_flowable(logo_data, max_height_mm=14.0)
    header_left = logo if logo else Paragraph(
        f"<b>{_escape_pdf_text(company_name[:40])}</b>",
        ParagraphStyle("LogoFallback", parent=styles["Normal"], fontSize=12, textColor=colors.Color(pr, pg, pb)),
    )
    header_right = Paragraph(
        f"<para align='right'><font size='8' color='#94a3b8'>Antrags-ID</font><br/>"
        f"<font size='9'><b>{_escape_pdf_text(str(data.get('id') or '—'))}</b></font></para>",
        styles["Normal"],
    )
    header_table = Table([[header_left, header_right]], colWidths=[doc.width * 0.72, doc.width * 0.28])
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    story = [
        header_table,
        Spacer(1, 6 * mm),
        HRFlowable(width="100%", thickness=2, color=colors.Color(pr, pg, pb), spaceAfter=8),
        Paragraph(_escape_pdf_text(company_name), subtitle_style),
        Paragraph("Abwesenheitsantrag", title_style),
        Paragraph(
            f"Eingereicht am {_format_iso_date(str(data.get('created_at') or '')[:10])} · Status: <b>{_escape_pdf_text(status_label)}</b>",
            subtitle_style,
        ),
        Spacer(1, 8 * mm),
    ]

    info_rows = [
        [Paragraph("Mitarbeiter", label_style), Paragraph(_escape_pdf_text(worker_name), value_style)],
        [Paragraph("Badge-ID", label_style), Paragraph(_escape_pdf_text(str(data.get("badge_id") or "—")), value_style)],
        [Paragraph("Art", label_style), Paragraph(_escape_pdf_text(type_label), value_style)],
        [
            Paragraph("Zeitraum", label_style),
            Paragraph(
                f"{_format_iso_date(data.get('start_date', ''))} – {_format_iso_date(data.get('end_date', ''))}",
                value_style,
            ),
        ],
        [Paragraph("Arbeitstage", label_style), Paragraph(str(int(data.get("days_count") or 0)), value_style)],
    ]
    if data.get("reviewer_username") or data.get("reviewed_at"):
        info_rows.append(
            [
                Paragraph("Bearbeitung", label_style),
                Paragraph(
                    f"{_escape_pdf_text(str(data.get('reviewer_username') or '—'))}"
                    f" · {_format_iso_date(str(data.get('reviewed_at') or '')[:10])}",
                    value_style,
                ),
            ]
        )

    info_table = Table(info_rows, colWidths=[34 * mm, doc.width - 34 * mm])
    info_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#dbe3ef")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#eef2f7")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([info_table, Spacer(1, 8 * mm)])

    note = str(data.get("note") or "").strip()
    if note:
        story.extend(
            [
                Paragraph("Begründung / Notiz", label_style),
                Paragraph(_escape_pdf_text(note).replace("\n", "<br/>"), note_style),
                Spacer(1, 6 * mm),
            ]
        )

    review_note = str(data.get("review_note") or "").strip()
    if review_note:
        story.extend(
            [
                Paragraph("Entscheidungsnotiz (Arbeitgeber)", label_style),
                Paragraph(_escape_pdf_text(review_note).replace("\n", "<br/>"), note_style),
                Spacer(1, 6 * mm),
            ]
        )

    story.extend([Spacer(1, 10 * mm), Paragraph("Unterschrift Mitarbeiter/in", label_style)])
    sig_flow = _signature_flowable(signature_data, signature_name)
    sig_table = Table([[sig_flow or Paragraph("—", value_style)]], colWidths=[doc.width * 0.55])
    sig_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#cbd5e1")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.extend(
        [
            sig_table,
            Spacer(1, 4 * mm),
            Paragraph(
                f"<font size='9' color='#64748b'>{_escape_pdf_text(signature_name)}</font>",
                styles["Normal"],
            ),
            Spacer(1, 8 * mm),
            Paragraph(
                f"<para align='center'><font size='8' color='#94a3b8'>"
                f"Dokument erstellt am {datetime.now().strftime('%d.%m.%Y %H:%M')} · {_escape_pdf_text(company_name)}"
                f"</font></para>",
                styles["Normal"],
            ),
        ]
    )

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
