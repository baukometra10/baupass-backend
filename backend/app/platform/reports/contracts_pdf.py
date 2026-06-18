from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from typing import Any

from backend.app.domains.contracts.contract_locales import (
    build_fallback_contract_body,
    default_currency_for_jurisdiction,
    document_title,
    footer_text,
    is_section_heading,
    normalize_jurisdiction,
    normalize_lang,
    preamble_html,
    signing_note,
    signature_labels,
    split_body_blocks,
)


def _parse_input_data(contract: dict[str, Any]) -> dict[str, Any]:
    import json

    raw = contract.get("input_data")
    if isinstance(raw, dict):
        return raw
    raw_json = contract.get("input_json")
    if isinstance(raw_json, dict):
        return raw_json
    if isinstance(raw_json, str) and raw_json.strip():
        try:
            return json.loads(raw_json)
        except json.JSONDecodeError:
            return {}
    return {}


def _escape_pdf_text(value: str) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


_PDF_FONT_REGISTERED = False
_PDF_FONT_NAME = "Helvetica"


def _resolve_pdf_font(lang: str) -> str:
    global _PDF_FONT_REGISTERED, _PDF_FONT_NAME
    if normalize_lang(lang) != "ar":
        return "Helvetica"
    if _PDF_FONT_REGISTERED:
        return _PDF_FONT_NAME
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        os.environ.get("BAUPASS_CONTRACT_FONT"),
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\tradbdo.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if not path or not os.path.isfile(path):
            continue
        try:
            pdfmetrics.registerFont(TTFont("ContractLocaleFont", path))
            _PDF_FONT_REGISTERED = True
            _PDF_FONT_NAME = "ContractLocaleFont"
            return _PDF_FONT_NAME
        except Exception:
            continue
    return "Helvetica"


def build_employment_contract_pdf(*, contract: dict[str, Any], branding: dict[str, Any] | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from backend.app.platform.workforce.deployment_branding import logo_image_flowable

    branding = branding or {}
    input_data = _parse_input_data(contract)
    form = input_data.get("form") or {}
    company = input_data.get("company") or {}
    worker = input_data.get("worker") or {}

    lang = normalize_lang(contract.get("language"))
    jurisdiction = normalize_jurisdiction(form.get("jurisdiction") or form.get("jurisdiction_country"))
    font_name = _resolve_pdf_font(lang)
    text_align = TA_RIGHT if lang == "ar" else TA_JUSTIFY
    title_align = TA_CENTER

    company_name = str(
        branding.get("companyName")
        or company.get("portal_display_name")
        or company.get("name")
        or contract.get("companyName")
        or ("صاحب العمل" if lang == "ar" else "Employer" if lang == "en" else "Arbeitgeber")
    ).strip()
    employee_name = (
        str(form.get("employee_name") or "").strip()
        or f"{str(worker.get('first_name') or '').strip()} {str(worker.get('last_name') or '').strip()}".strip()
        or ("الموظف/ة" if lang == "ar" else "Employee" if lang == "en" else "Arbeitnehmer/-in")
    )
    employee_address = str(form.get("employee_address") or "").strip()
    body_text = str(contract.get("final_text") or contract.get("draft_text") or "").strip()
    contract_title = document_title(lang, jurisdiction, contract.get("title"))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=contract_title,
    )
    styles = getSampleStyleSheet()
    text_color = colors.HexColor("#111827")
    muted = colors.HexColor("#4b5563")

    title_style = ParagraphStyle(
        "ContractDocTitle",
        parent=styles["Heading1"],
        fontName=f"{font_name}-Bold" if font_name == "Helvetica" else font_name,
        fontSize=14,
        leading=18,
        alignment=title_align,
        spaceAfter=10,
        textColor=text_color,
    )
    preamble_style = ParagraphStyle(
        "ContractPreamble",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10.5,
        leading=15,
        alignment=text_align,
        spaceAfter=6,
        textColor=text_color,
    )
    section_style = ParagraphStyle(
        "ContractSection",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=10.5,
        leading=15,
        alignment=text_align,
        spaceBefore=4,
        spaceAfter=6,
        textColor=text_color,
    )
    section_heading_style = ParagraphStyle(
        "ContractSectionHeading",
        parent=section_style,
        fontName=f"{font_name}-Bold" if font_name == "Helvetica" else font_name,
        spaceBefore=8,
        spaceAfter=4,
    )
    note_style = ParagraphStyle(
        "ContractNote",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9,
        leading=12,
        textColor=muted,
        alignment=text_align,
        spaceAfter=6,
    )
    sign_label_style = ParagraphStyle(
        "ContractSignLabel",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9.5,
        leading=12,
        alignment=TA_CENTER,
        textColor=text_color,
    )

    story: list[Any] = []
    logo = logo_image_flowable(str(branding.get("logoData") or ""), max_height_mm=14)
    if logo:
        logo_table = Table([[logo]], colWidths=[doc.width])
        logo_table.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        story.extend([logo_table, Spacer(1, 2 * mm)])

    story.append(Paragraph(_escape_pdf_text(contract_title), title_style))
    story.append(
        Paragraph(
            preamble_html(
                lang=lang,
                jurisdiction=jurisdiction,
                company_name=_escape_pdf_text(company_name),
                employee_name=_escape_pdf_text(employee_name),
                employee_address=_escape_pdf_text(employee_address),
            ),
            preamble_style,
        )
    )

    blocks = split_body_blocks(body_text, lang)
    if not blocks:
        fallback = build_fallback_contract_body(
            lang=lang,
            jurisdiction=jurisdiction,
            form={**form, "currency": form.get("currency") or default_currency_for_jurisdiction(jurisdiction)},
            notes=str(input_data.get("notes") or "").strip(),
        )
        blocks = split_body_blocks(fallback, lang)

    for block in blocks:
        lines = block.split("\n", 1)
        heading = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        if is_section_heading(heading, lang):
            parts = [Paragraph(_escape_pdf_text(heading), section_heading_style)]
            if body:
                parts.append(Paragraph(_escape_pdf_text(body).replace("\n", "<br/>"), section_style))
            story.append(KeepTogether(parts))
        else:
            story.append(Paragraph(_escape_pdf_text(block).replace("\n", "<br/>"), section_style))

    place_date_label, employer_sign, employee_sign = signature_labels(lang)
    story.append(PageBreak())
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(signing_note(lang), note_style))
    story.append(Spacer(1, 10 * mm))

    sign_line = "……………………………………………………………………………………"
    sign_table = Table(
        [
            [sign_line],
            [place_date_label],
            ["", ""],
            [sign_line, sign_line],
            [employer_sign, employee_sign],
        ],
        colWidths=[doc.width / 2.0 - 4 * mm, doc.width / 2.0 - 4 * mm],
        rowHeights=[None, None, 10 * mm, None, None],
    )
    sign_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (1, 0)),
                ("SPAN", (0, 1), (1, 1)),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (0, 3), (-1, 4), font_name),
                ("FONTSIZE", (0, 3), (-1, 3), 10),
                ("TOPPADDING", (0, 3), (-1, 3), 18),
                ("BOTTOMPADDING", (0, 4), (-1, 4), 0),
            ]
        )
    )
    story.append(sign_table)
    story.append(Spacer(1, 6 * mm))
    story.append(
        Paragraph(
            f"<font size='8' color='#6b7280'>{footer_text(lang)} · {datetime.now(timezone.utc).strftime('%d.%m.%Y')}</font>",
            sign_label_style,
        )
    )

    doc.build(story)
    return buffer.getvalue()
