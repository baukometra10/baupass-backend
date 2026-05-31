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
    branding: dict[str, Any] | None = None,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    lang_key = (lang or "de")[:2]
    month_label = MONTH_NAMES.get(lang_key, MONTH_NAMES["de"])[month]
    title = TITLE.get(lang_key, TITLE["de"])

    buffer = io.BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=8 * mm,
        rightMargin=8 * mm,
        topMargin=6 * mm,
        bottomMargin=8 * mm,
        title=f"Einsatzplan {worker_name} {month_label} {year}",
    )
    from .deployment_branding import logo_image_flowable

    brand = branding or {}
    styles = getSampleStyleSheet()
    accent = colors.HexColor(str(brand.get("accent") or "#0f4c5c"))
    accent_light = colors.HexColor(str(brand.get("accentLight") or "#1a8aad"))
    muted = colors.HexColor("#5a6a78")
    display_company = str(brand.get("companyName") or company_name or "BauPass")
    sector_label = str(brand.get("sectorLabel") or "").strip()
    weekend_bg = colors.HexColor("#f0f4f8")

    sub_style = ParagraphStyle(
        "BpSub",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=10,
        textColor=colors.HexColor("#d0e8ef"),
    )

    meta_lines = [
        f"<b>{display_company}</b>",
    ]
    if sector_label:
        meta_lines.append(f"<font size='9'>{sector_label}</font>")
    meta_lines.extend(
        [
            f"{title}",
            f"<font size='11'><b>{worker_name}</b></font>",
        ]
    )
    if badge_id:
        meta_lines.append(f"Badge: {badge_id}")
    meta_lines.append(f"<font color='#b8d4de'>{month_label} {year}</font>")
    meta_lines.append(
        f"<font size='8'>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</font>"
    )

    logo_img = logo_image_flowable(str(brand.get("logoData") or ""))
    if logo_img:
        header_table = Table(
            [[logo_img, Paragraph("<br/>".join(meta_lines), sub_style)]],
            colWidths=[28 * mm, doc.width - 28 * mm],
        )
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (0, 0), 4),
                    ("RIGHTPADDING", (0, 0), (0, 0), 10),
                ]
            )
        )
    else:
        header_table = Table(
            [[Paragraph("<br/>".join(meta_lines), sub_style)]],
            colWidths=[doc.width],
        )
    header_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), accent),
                ("BOX", (0, 0), (-1, -1), 0, accent),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
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
                loc[:42],
                time_cell[:12],
                str(day.get("notes") or "")[:28],
            ]
        )
        if day.get("isWeekend"):
            row_styles.append(("BACKGROUND", (0, i), (-1, i), weekend_bg))

    col_date = 16 * mm
    col_day = 22 * mm
    col_time = 18 * mm
    col_note = 32 * mm
    col_loc = doc.width - col_date - col_day - col_time - col_note
    col_widths = [col_date, col_day, col_loc, col_time, col_note]
    data_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), accent_light),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTSIZE", (0, 1), (-1, -1), 6.5),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.2, colors.HexColor("#c5d0da")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafbfc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
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
        Spacer(1, 3 * mm),
        data_table,
        Spacer(1, 2 * mm),
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
