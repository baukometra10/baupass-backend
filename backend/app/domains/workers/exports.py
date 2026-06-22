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
        pdf.drawString(36, y, "WorkPass - Mitarbeiterliste")
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


def build_leave_request_pdf_bytes(data: dict[str, Any]) -> dict[str, Any] | bytes:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as rl_canvas
    except Exception:
        return _reportlab_missing()

    worker_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or data.get(
        "worker_id", "-"
    )
    type_label = {"urlaub": "Urlaub", "krank": "Krankmeldung", "sonstiges": "Sonstiges"}.get(
        data.get("type"), data.get("type") or "-"
    )

    buffer = io.BytesIO()
    pdf = rl_canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    y = page_height - 48

    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(40, y, "WorkPass - Urlaubsantrag")
    y -= 20
    pdf.setFont("Helvetica", 9)
    pdf.drawString(40, y, f"Exportiert: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

    y -= 24
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, y, "Antragsdaten")
    y -= 14
    pdf.setFont("Helvetica", 10)

    lines = [
        f"ID: {data.get('id', '-')}",
        f"Mitarbeiter: {worker_name}",
        f"Badge-ID: {data.get('badge_id', '-')}",
        f"Art: {type_label}",
        f"Zeitraum: {data.get('start_date', '-')} bis {data.get('end_date', '-')}",
        f"Arbeitstage: {int(data.get('days_count') or 0)}",
        f"Status: {data.get('status', '-')}",
        f"Eingereicht am: {data.get('created_at', '-')}",
        f"Bearbeitet von: {data.get('reviewer_username') or '-'}",
        f"Bearbeitet am: {data.get('reviewed_at') or '-'}",
    ]
    for line in lines:
        pdf.drawString(40, y, line)
        y -= 14

    note = (data.get("note") or "").strip() or "-"
    review_note = (data.get("review_note") or "").strip() or "-"

    y -= 8
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, y, "Notiz")
    y -= 14
    pdf.setFont("Helvetica", 10)
    for chunk in textwrap.wrap(note, width=95)[:10]:
        pdf.drawString(40, y, chunk)
        y -= 13

    y -= 6
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(40, y, "Entscheidungsnotiz")
    y -= 14
    pdf.setFont("Helvetica", 10)
    for chunk in textwrap.wrap(review_note, width=95)[:10]:
        pdf.drawString(40, y, chunk)
        y -= 13

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()
