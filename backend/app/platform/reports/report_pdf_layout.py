"""Shared branded layout for Reporting PDF exports (per-company logo & colors)."""
from __future__ import annotations

import html
import io
import re
from datetime import datetime, timezone
from typing import Any, Sequence

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _escape(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def slugify_filename_part(text: str, *, max_len: int = 28) -> str:
    raw = str(text or "").strip().lower()
    raw = raw.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    raw = re.sub(r"[^a-z0-9]+", "-", raw)
    raw = re.sub(r"-+", "-", raw).strip("-")
    return (raw[:max_len] or "bericht").strip("-")


def build_report_filename(
    *,
    company_name: str,
    report_kind: str,
    period: str,
    ext: str = "pdf",
) -> str:
    company_slug = slugify_filename_part(company_name or "mandant")
    kind_slug = slugify_filename_part(report_kind or "report", max_len=24)
    period_slug = re.sub(r"[^0-9a-zA-Z-]", "-", str(period or "").strip())[:16] or datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d")
    return f"{company_slug}-{kind_slug}-{period_slug}.{ext.lstrip('.')}"


def resolve_report_branding(db, company_id: str | None = None) -> dict[str, Any]:
    """Company tenant branding, or platform defaults for superadmin exports."""
    from backend.app.platform.workforce.deployment_branding import resolve_company_pdf_branding
    from backend.server import DEFAULT_BRAND_ACCENT, DEFAULT_OPERATOR_NAME, DEFAULT_PLATFORM_NAME

    settings = db.execute(
        """
        SELECT platform_name, operator_name, invoice_primary_color, invoice_accent_color,
               invoice_logo_data
        FROM settings WHERE id = 1
        """
    ).fetchone()
    platform_name = str(settings["platform_name"] if settings else DEFAULT_PLATFORM_NAME).strip() or DEFAULT_PLATFORM_NAME
    operator_name = str(settings["operator_name"] if settings else DEFAULT_OPERATOR_NAME).strip() or DEFAULT_OPERATOR_NAME
    platform_primary = str(settings["invoice_primary_color"] if settings else "#06b6d4").strip() or "#06b6d4"
    platform_accent = str(settings["invoice_accent_color"] if settings else DEFAULT_BRAND_ACCENT).strip() or DEFAULT_BRAND_ACCENT

    if company_id:
        brand = resolve_company_pdf_branding(db, str(company_id))
        brand["platformName"] = platform_name
        brand["operatorName"] = operator_name
        return brand

    logo_data = ""
    if settings and str(settings["invoice_logo_data"] or "").strip():
        logo_data = str(settings["invoice_logo_data"]).strip()
    if not logo_data:
        from backend.app.platform.workforce.deployment_branding import _default_logo_data_url

        logo_data = _default_logo_data_url()

    return {
        "companyName": platform_name,
        "platformName": platform_name,
        "operatorName": operator_name,
        "logoData": logo_data,
        "accent": platform_primary,
        "accentLight": platform_accent,
        "preset": "construction",
        "sectorLabel": "Reporting",
    }


def _footer_text(branding: dict[str, Any]) -> str:
    platform = str(branding.get("platformName") or branding.get("companyName") or "WorkPass")
    operator = str(branding.get("operatorName") or platform)
    return f"Erstellt mit {platform} · {operator} · Vertraulich"


def _header_flowables(
    branding: dict[str, Any],
    *,
    report_title: str,
    subtitle: str = "",
    doc_width: float,
) -> list[Any]:
    from backend.app.platform.workforce.deployment_branding import logo_image_flowable

    styles = getSampleStyleSheet()
    accent = colors.HexColor(str(branding.get("accent") or "#06b6d4"))
    display_name = str(branding.get("companyName") or "WorkPass")
    sector = str(branding.get("sectorLabel") or "").strip()

    meta_style = ParagraphStyle(
        "ReportMeta",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#475569"),
    )
    stamp = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    meta_html = f"<b>{_escape(report_title)}</b>"
    if subtitle:
        meta_html += f"<br/>{_escape(subtitle)}"
    if sector:
        meta_html = f"<font size='8' color='#64748b'>{_escape(sector)}</font><br/>{meta_html}"
    meta_html += f"<br/><font size='7' color='#94a3b8'>{stamp}</font>"

    logo_img = logo_image_flowable(str(branding.get("logoData") or ""), max_height_mm=22.0)
    title_para = Paragraph(
        f"<font size='14'><b>{_escape(display_name)}</b></font><br/>{meta_html}",
        meta_style,
    )
    if logo_img:
        header_table = Table(
            [[logo_img, title_para]],
            colWidths=[26 * mm, doc_width - 26 * mm],
        )
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 10),
                    ("LEFTPADDING", (1, 0), (1, 0), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
    else:
        header_table = Table([[title_para]], colWidths=[doc_width])

    accent_bar = Table([[""]], colWidths=[doc_width], rowHeights=[2.8 * mm])
    accent_bar.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), accent),
                ("BOX", (0, 0), (-1, -1), 0, accent),
            ]
        )
    )
    return [header_table, accent_bar, Spacer(1, 5 * mm)]


def _section_heading(text: str, accent_hex: str) -> Paragraph:
    styles = getSampleStyleSheet()
    style = ParagraphStyle(
        "ReportSection",
        parent=styles["Heading2"],
        fontSize=11,
        leading=13,
        textColor=colors.HexColor(accent_hex),
        spaceBefore=6,
        spaceAfter=4,
        fontName="Helvetica-Bold",
    )
    return Paragraph(_escape(text), style)


def _body_line(text: str, *, bold: bool = False) -> Paragraph:
    styles = getSampleStyleSheet()
    style = ParagraphStyle(
        "ReportLine",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1e293b"),
        fontName="Helvetica-Bold" if bold else "Helvetica",
        leftIndent=0,
    )
    return Paragraph(_escape(text), style)


def _kpi_cards(kpis: dict[str, Any], labels: Sequence[tuple[str, str]], accent_hex: str) -> Table | None:
    items: list[list[str]] = []
    for key, label in labels:
        if key not in kpis:
            continue
        val = kpis.get(key)
        if val is None:
            continue
        items.append([label, str(val)])

    if not items:
        return None

    accent = colors.HexColor(accent_hex)
    light = colors.HexColor("#f8fafc")
    data = [[Paragraph(f"<b>{_escape(l)}</b>", ParagraphStyle("k", fontSize=8, textColor=colors.HexColor("#64748b"))),
             Paragraph(f"<font size='11'><b>{_escape(v)}</b></font>", ParagraphStyle("v", fontSize=11))]
            for l, v in items]

    table = Table(data, colWidths=[55 * mm, 35 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), light),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#e2e8f0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBEFORE", (0, 0), (0, -1), 2, accent),
            ]
        )
    )
    return table


def build_branded_narrative_report_pdf(
    *,
    report_title: str,
    subtitle: str,
    branding: dict[str, Any],
    sections: list[dict[str, Any]],
    landscape_mode: bool = False,
) -> bytes:
    """Build a multi-section narrative PDF (KPIs, bullet lists, guidance)."""
    page_size = landscape(A4) if landscape_mode else A4
    buffer = io.BytesIO()
    brand = branding or {}
    accent_hex = str(brand.get("accent") or "#06b6d4")
    footer = _footer_text(brand)

    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title=report_title[:80],
    )

    def on_page(canv, _doc):
        canv.saveState()
        canv.setFont("Helvetica", 7)
        canv.setFillColor(colors.HexColor("#94a3b8"))
        canv.drawString(14 * mm, 8 * mm, footer[:120])
        canv.drawRightString(page_size[0] - 14 * mm, 8 * mm, f"Seite {canv.getPageNumber()}")
        canv.restoreState()

    story: list[Any] = _header_flowables(
        brand,
        report_title=report_title,
        subtitle=subtitle,
        doc_width=doc.width,
    )

    for section in sections:
        heading = str(section.get("title") or "").strip()
        if heading:
            story.append(_section_heading(heading, accent_hex))

        kpi_labels = section.get("kpi_labels")
        kpi_data = section.get("kpis")
        if isinstance(kpi_data, dict) and kpi_labels:
            card = _kpi_cards(kpi_data, kpi_labels, accent_hex)
            if card:
                story.append(card)
                story.append(Spacer(1, 3 * mm))

        for line in section.get("lines") or []:
            story.append(_body_line(str(line)))

        for item in section.get("bullets") or []:
            story.append(_body_line(f"• {item}"))

        story.append(Spacer(1, 4 * mm))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buffer.getvalue()


def build_branded_table_report_pdf(
    *,
    report_title: str,
    subtitle: str,
    branding: dict[str, Any],
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    landscape_mode: bool = False,
) -> bytes:
    page_size = landscape(A4) if landscape_mode else A4
    buffer = io.BytesIO()
    brand = branding or {}
    accent_hex = str(brand.get("accent") or "#06b6d4")
    accent = colors.HexColor(accent_hex)
    footer = _footer_text(brand)

    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title=report_title[:80],
    )

    def on_page(canv, _doc):
        canv.saveState()
        canv.setFont("Helvetica", 7)
        canv.setFillColor(colors.HexColor("#94a3b8"))
        canv.drawString(12 * mm, 8 * mm, footer[:120])
        canv.drawRightString(page_size[0] - 12 * mm, 8 * mm, f"Seite {canv.getPageNumber()}")
        canv.restoreState()

    col_count = max(1, len(headers))
    col_width = doc.width / col_count
    header_style = ParagraphStyle("Th", fontSize=7.5, fontName="Helvetica-Bold", textColor=colors.white)
    cell_style = ParagraphStyle("Td", fontSize=7, leading=9, textColor=colors.HexColor("#1e293b"))

    table_data: list[list[Any]] = [
        [Paragraph(_escape(str(h)), header_style) for h in headers]
    ]
    for row in rows:
        table_data.append(
            [Paragraph(_escape(str(cell if cell is not None else "")[:48]), cell_style) for cell in row[:col_count]]
        )
    if not rows:
        table_data.append([Paragraph("—", cell_style)] + [Paragraph("", cell_style) for _ in range(col_count - 1)])

    table = Table(table_data, colWidths=[col_width] * col_count, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), accent),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    story: list[Any] = _header_flowables(
        brand,
        report_title=report_title,
        subtitle=subtitle,
        doc_width=doc.width,
    )
    story.append(KeepTogether([table]))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buffer.getvalue()


def build_branded_multi_table_report_pdf(
    *,
    report_title: str,
    subtitle: str,
    branding: dict[str, Any],
    tables: Sequence[dict[str, Any]],
    landscape_mode: bool = False,
) -> bytes:
    """Several table sections in one branded PDF."""
    page_size = landscape(A4) if landscape_mode else A4
    buffer = io.BytesIO()
    brand = branding or {}
    accent_hex = str(brand.get("accent") or "#06b6d4")
    accent = colors.HexColor(accent_hex)
    footer = _footer_text(brand)

    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
        title=report_title[:80],
    )

    def on_page(canv, _doc):
        canv.saveState()
        canv.setFont("Helvetica", 7)
        canv.setFillColor(colors.HexColor("#94a3b8"))
        canv.drawString(12 * mm, 8 * mm, footer[:120])
        canv.drawRightString(page_size[0] - 12 * mm, 8 * mm, f"Seite {canv.getPageNumber()}")
        canv.restoreState()

    header_style = ParagraphStyle("Th", fontSize=7.5, fontName="Helvetica-Bold", textColor=colors.white)
    cell_style = ParagraphStyle("Td", fontSize=7, leading=9, textColor=colors.HexColor("#1e293b"))

    story: list[Any] = _header_flowables(
        brand,
        report_title=report_title,
        subtitle=subtitle,
        doc_width=doc.width,
    )

    for block in tables:
        block_title = str(block.get("title") or "").strip()
        headers = list(block.get("headers") or [])
        rows = list(block.get("rows") or [])
        if block_title:
            story.append(_section_heading(block_title, accent_hex))
        if not headers:
            continue
        col_count = max(1, len(headers))
        col_width = doc.width / col_count
        table_data: list[list[Any]] = [
            [Paragraph(_escape(str(h)), header_style) for h in headers]
        ]
        for row in rows:
            table_data.append(
                [
                    Paragraph(_escape(str(cell if cell is not None else "")[:48]), cell_style)
                    for cell in row[:col_count]
                ]
            )
        if not rows:
            table_data.append([Paragraph("—", cell_style)] + [Paragraph("", cell_style) for _ in range(col_count - 1)])
        table = Table(table_data, colWidths=[col_width] * col_count, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), accent),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 6 * mm))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buffer.getvalue()
