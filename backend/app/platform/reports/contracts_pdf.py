from __future__ import annotations

import base64
import io
import os
from datetime import datetime, timezone
from typing import Any

from backend.app.domains.contracts.contract_locales import (
    build_fallback_contract_body,
    contract_intro_html,
    default_currency_for_jurisdiction,
    document_title,
    employee_cover_html,
    employer_cover_html,
    footer_text,
    is_section_heading,
    normalize_jurisdiction,
    normalize_lang,
    signing_note,
    signature_labels,
    split_body_blocks,
)

FIRST_PAGE_SECTIONS = 2
SECTION_SPACER_MM = 7.0


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


def _decode_logo_blob(logo_data: str) -> bytes | None:
    raw = str(logo_data or "").strip()
    if not raw.lower().startswith("data:image/"):
        return None
    try:
        _header, payload = raw.split(",", 1)
        blob = base64.b64decode(payload, validate=False)
        return blob or None
    except Exception:
        return None


def _make_page_logo_drawer(logo_data: str, *, max_height_mm: float = 12.0):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader

    blob = _decode_logo_blob(logo_data)
    if not blob:
        return None

    try:
        img = ImageReader(io.BytesIO(blob))
        iw, ih = img.getSize()
    except Exception:
        return None

    page_w, _page_h = A4
    max_h = max_height_mm * mm
    if ih > max_h:
        ratio = max_h / float(ih)
        draw_w = iw * ratio
        draw_h = max_h
    else:
        draw_w, draw_h = float(iw), float(ih)

    def _draw(canvas, doc) -> None:
        x = (page_w - draw_w) / 2.0
        y = doc.pagesize[1] - doc.topMargin + 2 * mm
        canvas.saveState()
        try:
            canvas.drawImage(img, x, y, width=draw_w, height=draw_h, mask="auto", preserveAspectRatio=True)
        except Exception:
            pass
        canvas.restoreState()

    return _draw


def _signature_cell(signature: dict[str, Any] | None, font_name: str, fallback_line: str):
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Image, Paragraph

    sig = signature or {}
    raw = str(sig.get("signature_data") or "").strip()
    typed_name = str(sig.get("signer_name") or "").strip()

    if raw.lower().startswith("data:image/"):
        try:
            from reportlab.lib.units import mm

            _header, payload = raw.split(",", 1)
            blob = base64.b64decode(payload, validate=False)
            if blob:
                bio = io.BytesIO(blob)
                img = Image(bio, width=55 * mm, height=18 * mm)
                img.hAlign = "CENTER"
                return img
        except Exception:
            pass

    if typed_name:
        styles = getSampleStyleSheet()
        return Paragraph(
            f"<para align='center'><i><font size='14'>{_escape_pdf_text(typed_name)}</font></i></para>",
            styles["Normal"],
        )

    return fallback_line


def build_employment_contract_pdf(
    *,
    contract: dict[str, Any],
    branding: dict[str, Any] | None = None,
    signatures: dict[str, Any] | None = None,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    branding = branding or {}
    signatures = signatures or {}
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
    employee_birth_date = str(form.get("employee_birth_date") or form.get("birth_date") or "").strip()
    employee_gender = str(form.get("employee_gender") or "").strip()
    body_text = str(contract.get("final_text") or contract.get("draft_text") or "").strip()
    contract_title = document_title(lang, jurisdiction, contract.get("title"))

    logo_data = str(branding.get("logoData") or "")
    logo_drawer = _make_page_logo_drawer(logo_data)
    top_margin = 28 * mm if logo_drawer else 18 * mm

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=top_margin,
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
    cover_style = ParagraphStyle(
        "ContractEmployeeCover",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=11,
        leading=16,
        alignment=TA_CENTER,
        spaceBefore=2,
        spaceAfter=10,
        textColor=text_color,
    )
    employer_cover_style = ParagraphStyle(
        "ContractEmployerCover",
        parent=cover_style,
        fontSize=10.5,
        spaceAfter=8,
    )
    intro_style = ParagraphStyle(
        "ContractIntro",
        parent=preamble_style,
        alignment=TA_CENTER if lang != "ar" else TA_CENTER,
        spaceAfter=10,
        fontSize=10,
    )

    story: list[Any] = []
    story.append(Paragraph(_escape_pdf_text(contract_title), title_style))
    story.append(Spacer(1, 5 * mm))
    story.append(
        Paragraph(
            employee_cover_html(
                lang=lang,
                employee_name=_escape_pdf_text(employee_name),
                employee_birth_date=employee_birth_date,
                employee_address=_escape_pdf_text(employee_address),
                employee_gender=employee_gender,
            ),
            cover_style,
        )
    )
    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            employer_cover_html(lang=lang, company_name=_escape_pdf_text(company_name)),
            employer_cover_style,
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            contract_intro_html(lang=lang, jurisdiction=jurisdiction),
            intro_style,
        )
    )
    story.append(Spacer(1, 6 * mm))

    blocks = split_body_blocks(body_text, lang)
    if not blocks:
        fallback = build_fallback_contract_body(
            lang=lang,
            jurisdiction=jurisdiction,
            form={**form, "currency": form.get("currency") or default_currency_for_jurisdiction(jurisdiction)},
            notes=str(input_data.get("notes") or "").strip(),
        )
        blocks = split_body_blocks(fallback, lang)

    section_heading_style.spaceBefore = 10
    section_heading_style.spaceAfter = 6
    section_style.spaceAfter = 10

    for index, block in enumerate(blocks):
        if index == FIRST_PAGE_SECTIONS:
            story.append(PageBreak())
        elif index > 0:
            story.append(Spacer(1, SECTION_SPACER_MM * mm))
        lines = block.split("\n", 1)
        heading = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        if is_section_heading(heading, lang):
            parts = [Paragraph(_escape_pdf_text(heading), section_heading_style)]
            if body:
                parts.append(Paragraph(_escape_pdf_text(body).replace("\n", "<br/>"), section_style))
            if index < FIRST_PAGE_SECTIONS:
                story.append(KeepTogether(parts))
            else:
                story.extend(parts)
        else:
            story.append(Paragraph(_escape_pdf_text(block).replace("\n", "<br/>"), section_style))

    place_date_label, employer_sign, employee_sign = signature_labels(lang, employee_gender)
    employer_sig = signatures.get("employer") if isinstance(signatures.get("employer"), dict) else None
    employee_sig = signatures.get("employee") if isinstance(signatures.get("employee"), dict) else None
    sign_place = str(
        (employer_sig or {}).get("sign_place")
        or (employee_sig or {}).get("sign_place")
        or form.get("work_location")
        or ""
    ).strip()
    signed_dates = [
        str((employer_sig or {}).get("signed_at") or "")[:10],
        str((employee_sig or {}).get("signed_at") or "")[:10],
    ]
    signed_dates = [d for d in signed_dates if d]
    place_date_text = place_date_label
    if sign_place or signed_dates:
        place_date_text = f"{place_date_label}: {sign_place or '—'}"
        if signed_dates:
            place_date_text += f" · {signed_dates[-1]}"

    story.append(PageBreak())
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(signing_note(lang), note_style))
    story.append(Spacer(1, 10 * mm))

    sign_line = "……………………………………………………………………………………"
    employer_cell = _signature_cell(employer_sig, font_name, sign_line)
    employee_cell = _signature_cell(employee_sig, font_name, sign_line)
    sign_table = Table(
        [
            [place_date_text],
            ["", ""],
            [employer_cell, employee_cell],
            [employer_sign, employee_sign],
        ],
        colWidths=[doc.width / 2.0 - 4 * mm, doc.width / 2.0 - 4 * mm],
        rowHeights=[None, 10 * mm, None, None],
    )
    sign_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (1, 0)),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (0, 0), (-1, 0), font_name),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("FONTNAME", (0, 3), (-1, 3), font_name),
                ("FONTSIZE", (0, 2), (-1, 2), 10),
                ("TOPPADDING", (0, 2), (-1, 2), 12),
                ("BOTTOMPADDING", (0, 3), (-1, 3), 0),
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

    if logo_drawer:
        doc.build(story, onFirstPage=logo_drawer, onLaterPages=logo_drawer)
    else:
        doc.build(story)
    return buffer.getvalue()
