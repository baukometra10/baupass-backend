from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any


def build_employment_contract_pdf(*, contract: dict[str, Any], branding: dict[str, Any] | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from backend.app.platform.workforce.deployment_branding import logo_image_flowable

    branding = branding or {}
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=14 * mm,
        title=str(contract.get("title") or "Arbeitsvertrag"),
    )
    styles = getSampleStyleSheet()
    accent = colors.HexColor(str(branding.get("accent") or "#0f4c5c"))
    company_name = str(branding.get("companyName") or contract.get("companyName") or "BauPass").strip()
    body_text = str(contract.get("final_text") or contract.get("draft_text") or "").strip()

    title_style = ParagraphStyle(
        "ContractTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=accent,
        spaceAfter=8,
    )
    meta_style = ParagraphStyle(
        "ContractMeta",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#475569"),
    )
    body_style = ParagraphStyle(
        "ContractBody",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=15,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=6,
    )

    logo = logo_image_flowable(str(branding.get("logoData") or ""), max_height_mm=18)
    header_text = Paragraph(
        (
            f"<b>{company_name}</b><br/>"
            f"{str(contract.get('title') or 'Arbeitsvertrag')}<br/>"
            f"<font size='8'>Stand: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC</font>"
        ),
        meta_style,
    )
    if logo:
        header = Table([[logo, header_text]], colWidths=[24 * mm, doc.width - 24 * mm])
        header.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
    else:
        header = Table([[header_text]], colWidths=[doc.width])
        header.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0)]))

    accent_bar = Table([[""]], colWidths=[doc.width], rowHeights=[2.4 * mm])
    accent_bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), accent)]))

    story = [
        header,
        Spacer(1, 4 * mm),
        accent_bar,
        Spacer(1, 5 * mm),
        Paragraph(str(contract.get("title") or "Arbeitsvertrag"), title_style),
    ]
    for block in [part.strip() for part in body_text.split("\n\n") if part.strip()]:
        story.append(Paragraph(block.replace("\n", "<br/>"), body_style))

    doc.build(story)
    return buffer.getvalue()
