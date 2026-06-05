"""Einsatzplan PDF: portrait A4, single page, branded header."""
from __future__ import annotations

import calendar
import re
from datetime import date

from backend.app.platform.workforce.deployment_pdf import (
    branding_preview_sample_days,
    build_deployment_plan_pdf,
)


def _sample_days(year: int, month: int) -> list[dict]:
    days = []
    for day_num in range(1, calendar.monthrange(year, month)[1] + 1):
        dt = date(year, month, day_num)
        days.append(
            {
                "date": dt.isoformat(),
                "weekday": "Mo",
                "weekdayIndex": dt.weekday(),
                "location": "Baustelle Nord" if day_num % 2 else "",
                "shiftStart": "2026-06-01T07:00:00Z" if day_num % 2 else "",
                "shiftEnd": "2026-06-01T16:00:00Z" if day_num % 2 else "",
                "notes": "",
                "isWeekend": dt.weekday() >= 5,
            }
        )
    return days


def test_deployment_pdf_portrait_single_page():
    pdf = build_deployment_plan_pdf(
        company_name="Test GmbH",
        worker_name="Max Mustermann",
        badge_id="W-1",
        year=2026,
        month=6,
        days=_sample_days(2026, 6),
        lang="de",
        branding={
            "companyName": "Test GmbH",
            "accent": "#0f4c5c",
            "accentLight": "#1a8aad",
        },
    )
    assert pdf[:4] == b"%PDF"
    text = pdf.decode("latin-1", errors="ignore")
    page_markers = len(re.findall(r"/Type\s*/Page[^s]", text))
    assert page_markers == 1, f"expected 1 page, found {page_markers}"
    mbox = re.search(r"/MediaBox\s*\[([^\]]+)\]", text)
    assert mbox, "MediaBox missing"
    parts = [float(x) for x in mbox.group(1).split()]
    width = parts[2] - parts[0]
    height = parts[3] - parts[1]
    assert height > width, f"expected portrait, got {width}x{height}"
    assert 580 < width < 610
    assert 830 < height < 860


def test_merge_pdf_branding_override():
    from backend.app.platform.workforce.deployment_branding import merge_pdf_branding_override

    base = {"companyName": "Alt", "accent": "#111111", "logoData": ""}
    merged = merge_pdf_branding_override(base, {"companyName": "Neu", "accent": "#abcdef"})
    assert merged["companyName"] == "Neu"
    assert merged["accent"] == "#abcdef"


def test_branding_preview_sample_days_has_entries():
    days = branding_preview_sample_days(2026, 6, "de")
    assert len(days) >= 28
    assert any(str(d.get("location") or "").strip() for d in days)
