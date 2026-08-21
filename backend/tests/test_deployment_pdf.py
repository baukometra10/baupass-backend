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
            "accent": "#06b6d4",
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


def test_logo_image_flowable_caps_wide_logo_width():
    """Wide logos must not exceed max_width (prevents painting over company name)."""
    import base64
    import struct
    import zlib

    from reportlab.lib.units import mm

    from backend.app.platform.workforce.deployment_branding import logo_image_flowable

    # Minimal valid 200x40 RGB PNG (wide banner).
    width, height = 200, 40
    raw_rows = b"".join(b"\x00" + (b"\xff\x00\x00" * width) for _ in range(height))
    compressed = zlib.compress(raw_rows, 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    img = logo_image_flowable(data_url, max_height_mm=18.0, max_width_mm=26.0)
    assert img is not None
    assert img.drawWidth <= 26.0 * mm + 0.01
    assert img.drawHeight <= 18.0 * mm + 0.01


def test_deployment_pdf_with_wide_logo_stays_single_page():
    import base64
    import struct
    import zlib

    width, height = 400, 80
    raw_rows = b"".join(b"\x00" + (b"\x00\x00\x80" * width) for _ in range(height))
    compressed = zlib.compress(raw_rows, 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    pdf = build_deployment_plan_pdf(
        company_name="Lufthansa",
        worker_name="Muster",
        badge_id="VORSCHAU",
        year=2026,
        month=8,
        days=_sample_days(2026, 8),
        lang="de",
        plan_tier="enterprise",
        branding={
            "companyName": "Lufthansa",
            "accent": "#8b5a2b",
            "accentLight": "#7c3aed",
            "logoData": data_url,
            "sectorLabel": "Premium",
        },
    )
    assert pdf[:4] == b"%PDF"
    text = pdf.decode("latin-1", errors="ignore")
    assert len(re.findall(r"/Type\s*/Page[^s]", text)) == 1
    assert "Lufthansa" in text or "L" in text

