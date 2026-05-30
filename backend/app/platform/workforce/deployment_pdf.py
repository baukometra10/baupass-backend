"""Premium monthly Einsatzplan PDF per worker."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any


MONTH_NAMES = {
    "de": [
        "",
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ],
    "en": [
        "",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],
    "ar": [
        "",
        "يناير",
        "فبراير",
        "مارس",
        "أبريل",
        "مايو",
        "يونيو",
        "يوليو",
        "أغسطس",
        "سبتمبر",
        "أكتوبر",
        "نوفمبر",
        "ديسمبر",
    ],
}

TITLE = {
    "de": "Einsatzplan / Arbeitsorte",
    "en": "Deployment plan / Work sites",
    "ar": "خطة التوزيع / مواقع العمل",
}


def build_deployment_plan_pdf(
    *,
    company_name: str,
    worker_name: str,
    badge_id: str | None,
    year: int,
    month: int,
    days: list[dict[str, Any]],
    lang: str = "de",
    plan_tier: str = "professional",
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    lang_key = (lang or "de")[:2]
    month_label = MONTH_NAMES.get(lang_key, MONTH_NAMES["de"])[month]
    title = TITLE.get(lang_key, TITLE["de"])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title=f"Einsatzplan {worker_name} {month_label} {year}",
    )
    styles = getSampleStyleSheet()
    accent = colors.HexColor("#0f4c5c")
    accent_light = colors.HexColor("#1a8aad")
    muted = colors.HexColor("#5a6a78")
    weekend_bg = colors.HexColor("#f0f4f8")

    header_style = ParagraphStyle(
        "BpHeader",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=colors.white,
        spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        "BpSub",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#d0e8ef"),
    )

    meta_lines = [
        f"<b>{company_name or 'BauPass'}</b>",
        f"{title}",
        f"<font size='14'><b>{worker_name}</b></font>",
    ]
    if badge_id:
        meta_lines.append(f"Badge: {badge_id}")
    meta_lines.append(f"<font color='#b8d4de'>{month_label} {year}</font>")
    meta_lines.append(
        f"<font size='8'>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</font>"
    )

    header_table = Table(
        [[Paragraph("<br/>".join(meta_lines), sub_style)]],
        colWidths=[doc.width],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), accent),
                ("BOX", (0, 0), (-1, -1), 0, accent),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )

    col_date = "Datum" if lang_key == "de" else ("Date" if lang_key == "en" else "التاريخ")
    col_day = "Tag" if lang_key == "de" else ("Day" if lang_key == "en" else "اليوم")
    col_loc = "Einsatzort" if lang_key == "de" else ("Site" if lang_key == "en" else "الموقع")
    col_time = "Zeit" if lang_key == "de" else ("Time" if lang_key == "en" else "الوقت")
    col_note = "Hinweis" if lang_key == "de" else ("Note" if lang_key == "en" else "ملاحظة")

    table_data: list[list] = [[col_date, col_day, col_loc, col_time, col_note]]
    row_styles: list[tuple] = []

    for i, day in enumerate(days, start=1):
        loc = str(day.get("location") or "").strip()
        if not loc:
            loc = "—" if lang_key != "ar" else "—"
        t_start = str(day.get("shiftStart") or "").strip()
        t_end = str(day.get("shiftEnd") or "").strip()
        time_cell = ""
        if t_start or t_end:
            time_cell = f"{t_start[11:16] if len(t_start) > 11 else t_start} – {t_end[11:16] if len(t_end) > 11 else t_end}".strip(" –")
        table_data.append(
            [
                str(day.get("date") or "")[8:10] + "." + str(day.get("date") or "")[5:7] + ".",
                str(day.get("weekday") or "")[:12],
                loc[:48],
                time_cell[:14],
                str(day.get("notes") or "")[:36],
            ]
        )
        if day.get("isWeekend"):
            row_styles.append(("BACKGROUND", (0, i), (-1, i), weekend_bg))

    col_widths = [22 * mm, 28 * mm, 68 * mm, 22 * mm, doc.width - 22 * mm - 28 * mm - 68 * mm - 22 * mm]
    data_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), accent_light),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c5d0da")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafbfc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]
    style_commands.extend(row_styles)
    data_table.setStyle(TableStyle(style_commands))

    footer = ParagraphStyle("footer", parent=styles["Normal"], fontSize=7, textColor=muted)
    footer_text = {
        "de": "Erstellt mit BauPass · Vertraulich — nur für den genannten Mitarbeiter bestimmt.",
        "en": "Generated by BauPass · Confidential — for the named employee only.",
        "ar": "صادر من BauPass · سري — للموظف المذكور فقط.",
    }
    story = [
        header_table,
        Spacer(1, 8 * mm),
        data_table,
        Spacer(1, 6 * mm),
        Paragraph(footer_text.get(lang_key, footer_text["de"]), footer),
    ]
    if plan_tier == "enterprise":
        story.insert(
            2,
            Paragraph(
                "<font color='#1a8aad'><b>Enterprise</b> — Multi-Site Deployment Plan</font>",
                ParagraphStyle("ent", parent=styles["Normal"], fontSize=8),
            ),
        )

    doc.build(story)
    return buffer.getvalue()
