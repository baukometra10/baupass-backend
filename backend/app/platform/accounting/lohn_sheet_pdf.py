"""A4 Entgeltabrechnung PDF from the same DatevSheet HTML shown in the studio."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas

PDF_SOURCE_HTML = "datev_sheet_html"
PDF_SOURCE_CHROMIUM = "datev_sheet_chromium"
PDF_SOURCE_WEASY = "datev_sheet_weasyprint"
PDF_SOURCE_REPORTLAB = "datev_sheet_reportlab"
GOOD_HTML_PDF_SOURCES = frozenset({PDF_SOURCE_HTML, PDF_SOURCE_CHROMIUM, PDF_SOURCE_WEASY})

NAVY = colors.HexColor("#1e3a5f")
INK = colors.HexColor("#151a22")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#1a2a33")
GRID = colors.HexColor("#b8c2c8")
PALE = colors.HexColor("#f8fafc")
PAY = colors.HexColor("#152a45")


def _s(value: Any) -> str:
    return str(value or "").strip()


def is_high_fidelity_pdf_source(source: str | None) -> bool:
    return str(source or "").strip() in GOOD_HTML_PDF_SOURCES


def render_datev_sheet_pdf(data: dict[str, Any] | None, html: str | None = None) -> bytes:
    """Prefer the studio DatevSheet HTML; fall back to a full-page reportlab layout."""
    raw, _source = render_datev_sheet_pdf_with_source(data, html)
    return raw


def render_datev_sheet_pdf_with_source(
    data: dict[str, Any] | None, html: str | None = None
) -> tuple[bytes, str]:
    doc = _prepare_print_document(html, data)
    if doc:
        chromium_pdf = _render_chromium_pdf(doc)
        if chromium_pdf.startswith(b"%PDF") and len(chromium_pdf) > 1500:
            return chromium_pdf, PDF_SOURCE_CHROMIUM
        weasy_pdf = _render_weasyprint_pdf(doc)
        if weasy_pdf.startswith(b"%PDF") and len(weasy_pdf) > 1500:
            return weasy_pdf, PDF_SOURCE_WEASY
    return _render_reportlab_fallback(data if isinstance(data, dict) else {}), PDF_SOURCE_REPORTLAB


def _prepare_print_document(html: str | None, data: dict[str, Any] | None) -> str:
    try:
        from .lohn_sheet import _CSS, build_sheet_body_html, prepare_sheet_html_for_pdf
    except Exception:
        return ""
    doc = str(html or "").strip()
    if len(doc) < 200:
        body = build_sheet_body_html(data or {})
        doc = (
            "<!DOCTYPE html><html lang='de'><head><meta charset='UTF-8'/>"
            f"<style>{_CSS}</style></head><body>{body}</body></html>"
        )
    return prepare_sheet_html_for_pdf(doc)


def _chromium_candidates() -> list[str]:
    env = str(os.environ.get("CHROME_BIN") or os.environ.get("CHROMIUM_PATH") or "").strip()
    candidates = [env] if env else []
    which = shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("msedge")
    if which:
        candidates.append(which)
    candidates.extend(
        [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ]
    )
    seen: set[str] = set()
    out: list[str] = []
    for path in candidates:
        p = str(path or "").strip()
        if not p or p in seen:
            continue
        seen.add(p)
        if Path(p).is_file() or shutil.which(p):
            out.append(p)
    return out


def _render_chromium_pdf(html_doc: str) -> bytes:
    """Print the exact DatevSheet HTML via headless Chromium/Edge — matches the studio view."""
    browsers = _chromium_candidates()
    if not browsers:
        return b""
    with tempfile.TemporaryDirectory(prefix="baupass-payslip-") as tmp:
        tmp_path = Path(tmp)
        html_path = tmp_path / "sheet.html"
        pdf_path = tmp_path / "sheet.pdf"
        html_path.write_text(html_doc, encoding="utf-8")
        file_url = html_path.resolve().as_uri()
        for browser in browsers:
            try:
                if pdf_path.exists():
                    pdf_path.unlink()
                cmd = [
                    browser,
                    "--headless=new",
                    "--disable-gpu",
                    "--no-pdf-header-footer",
                    "--print-to-pdf-no-header",
                    f"--print-to-pdf={pdf_path}",
                    file_url,
                ]
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=45,
                    check=False,
                )
                if pdf_path.is_file() and pdf_path.stat().st_size > 1500:
                    raw = pdf_path.read_bytes()
                    if raw.startswith(b"%PDF"):
                        return raw
                # Older Chrome builds use --headless without =new
                if proc.returncode != 0:
                    cmd[1] = "--headless"
                    proc = subprocess.run(cmd, capture_output=True, timeout=45, check=False)
                    if pdf_path.is_file() and pdf_path.stat().st_size > 1500:
                        raw = pdf_path.read_bytes()
                        if raw.startswith(b"%PDF"):
                            return raw
            except Exception as exc:
                print(f"[lohn_sheet_pdf] chromium_failed {browser}: {exc}", flush=True)
                continue
    return b""


def _render_weasyprint_pdf(html_doc: str) -> bytes:
    try:
        from weasyprint import HTML
    except Exception:
        return b""
    if not html_doc:
        return b""
    try:
        raw = HTML(string=html_doc, base_url=".").write_pdf()
    except Exception as exc:
        print(f"[lohn_sheet_pdf] weasyprint_failed {exc}", flush=True)
        return b""
    return bytes(raw) if raw else b""


def _render_html_pdf(html: str | None, data: dict[str, Any] | None) -> bytes:
    """Backward-compatible helper used by older tests/callers."""
    doc = _prepare_print_document(html, data)
    if not doc:
        return b""
    chromium = _render_chromium_pdf(doc)
    if chromium.startswith(b"%PDF"):
        return chromium
    return _render_weasyprint_pdf(doc)


def _render_reportlab_fallback(d: dict[str, Any]) -> bytes:
    buf = BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    left = 12 * mm
    right = width - 12 * mm
    usable = right - left
    y = height - 12 * mm

    def font(name: str = "Helvetica", size: float = 8) -> None:
        c.setFont(name, size)

    def ink(color=INK) -> None:
        c.setFillColor(color)

    def stroke(color=LINE, w: float = 0.4) -> None:
        c.setStrokeColor(color)
        c.setLineWidth(w)

    def text(x: float, yy: float, s: str, *, size: float = 8, bold: bool = False, color=INK) -> None:
        ink(color)
        font("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x, yy, _s(s)[:90])

    def text_right(x: float, yy: float, s: str, *, size: float = 8, bold: bool = False, color=INK) -> None:
        ink(color)
        font("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawRightString(x, yy, _s(s)[:40])

    text(left, y, d.get("companyName") or d.get("sender") or "Arbeitgeber", size=11, bold=True)
    text_right(right, y, "Entgeltabrechnung", size=11, bold=True, color=NAVY)
    y -= 5 * mm
    text(left, y, "Abrechnung der Brutto/Netto-Bezüge", size=9, bold=True)
    text_right(right, y, _s(d.get("headPage") or "Blatt: 1"), size=7, color=MUTED)
    y -= 4 * mm
    text(left, y, _s(d.get("titleMonth")), size=8, color=NAVY)
    text_right(right, y, "  ".join(p for p in (_s(d.get("usa")), _s(d.get("headDate"))) if p), size=7, color=MUTED)
    y -= 3 * mm
    stroke(LINE, 0.8)
    c.line(left, y, right, y)
    y -= 5 * mm

    cells = [
        ("Personal-Nr.", d.get("persNr")),
        ("Geburtsdatum", d.get("birth")),
        ("StKl", d.get("stkl")),
        ("Konf", d.get("konf")),
        ("St-Tg", d.get("stTg")),
        ("PGRS", d.get("pgrs")),
        ("BGRS", d.get("bgrs")),
        ("SV-Tg", d.get("svTg")),
        ("SV-Nummer", d.get("svNr"), 2),
        ("Krankenkasse", d.get("kkName"), 3),
        ("KK %", d.get("kkPct")),
        ("Arbeitstage", d.get("workDays")),
        ("Stunden", d.get("workHours")),
    ]
    col_w = usable / 8.0
    row_h = 9.2 * mm
    x = left
    row_top = y
    cols_used = 0
    for item in cells:
        lab, val = item[0], item[1]
        span = int(item[2]) if len(item) > 2 else 1
        if cols_used + span > 8:
            y -= row_h
            x = left
            cols_used = 0
            row_top = y
        w = col_w * span
        stroke(GRID, 0.3)
        c.setFillColor(colors.white)
        c.rect(x, row_top - row_h, w, row_h, fill=1, stroke=1)
        text(x + 1.4 * mm, row_top - 3.2 * mm, lab.upper(), size=5, color=MUTED)
        text(x + 1.4 * mm, row_top - 7.0 * mm, val, size=8)
        x += w
        cols_used += span
    y = row_top - row_h - 3.5 * mm

    box_h = 28 * mm
    mid_gap = 3 * mm
    left_w = usable * 0.58
    right_w = usable - left_w - mid_gap
    stroke(LINE, 0.45)
    c.setFillColor(colors.white)
    c.rect(left, y - box_h, left_w, box_h, fill=1, stroke=1)
    c.rect(left + left_w + mid_gap, y - box_h, right_w, box_h, fill=1, stroke=1)
    text(left + 2 * mm, y - 4 * mm, "ARBEITGEBER / MITARBEITER", size=6, bold=True, color=NAVY)
    addr_y = y - 8 * mm
    for line in (
        d.get("sender"),
        d.get("empMeta"),
        d.get("empName"),
        d.get("empAddr"),
        f"Eintritt: {_s(d.get('entry'))}  ·  Steuer-ID: {_s(d.get('taxIdMid'))}" if (d.get("entry") or d.get("taxIdMid")) else "",
    ):
        if _s(line):
            text(left + 2 * mm, addr_y, line, size=7.5)
            addr_y -= 3.6 * mm
    text(left + left_w + mid_gap + 2 * mm, y - 4 * mm, "HINWEISE ZUR ABRECHNUNG", size=6, bold=True, color=NAVY)
    hint = _s(d.get("hints") or d.get("footerNote"))
    if hint:
        text(left + left_w + mid_gap + 2 * mm, y - 8 * mm, hint[:80], size=7)
    y -= box_h + 3.5 * mm

    text(left, y, "Bezüge", size=7, bold=True, color=NAVY)
    y -= 2 * mm
    headers = ["Code", "Bezeichnung", "Menge", "Betrag", "St/SV"]
    col_widths = [usable * 0.10, usable * 0.42, usable * 0.16, usable * 0.20, usable * 0.12]
    row_h = 6.2 * mm
    stroke(GRID, 0.35)
    c.setFillColor(PALE)
    c.rect(left, y - row_h, usable, row_h, fill=1, stroke=1)
    cx = left
    for i, h in enumerate(headers):
        (text if i < 2 else text_right)(
            cx + 1.5 * mm if i < 2 else cx + col_widths[i] - 1.5 * mm,
            y - 4.2 * mm,
            h,
            size=6,
            bold=True,
            color=NAVY,
        )
        cx += col_widths[i]
    y -= row_h
    rows = [r for r in (d.get("wageRows") or []) if isinstance(r, dict)][:5]
    while len(rows) < 5:
        rows.append({})
    for r in rows:
        c.setFillColor(colors.white)
        c.rect(left, y - row_h, usable, row_h, fill=1, stroke=1)
        vals = [
            _s(r.get("code")),
            _s(r.get("label")),
            _s(r.get("qty")),
            _s(r.get("amount")),
            f"{_s(r.get('taxFlag'))}/{_s(r.get('svFlag'))}" if (r.get("code") or r.get("amount")) else "",
        ]
        cx = left
        for i, val in enumerate(vals):
            (text if i < 2 else text_right)(
                cx + 1.5 * mm if i < 2 else cx + col_widths[i] - 1.5 * mm,
                y - 4.2 * mm,
                val,
                size=7.5,
            )
            cx += col_widths[i]
        y -= row_h
    c.setFillColor(PALE)
    c.rect(left, y - row_h, usable, row_h, fill=1, stroke=1)
    text(left + 1.5 * mm, y - 4.2 * mm, "Brutto gesamt", size=7.5, bold=True)
    text_right(right - 1.5 * mm, y - 4.2 * mm, d.get("grossTotal"), size=8, bold=True)
    y -= row_h + 4 * mm

    split = usable * 0.58
    kv = [
        ("Steuerbrutto", d.get("stBrutto")),
        ("Lohnsteuer", d.get("lst")),
        ("Kirchensteuer", d.get("kist")),
        ("Soli", d.get("vbSoli")),
        ("KV", d.get("kvBeitrag")),
        ("RV", d.get("rvBeitrag")),
        ("AV", d.get("avBeitrag")),
        ("PV", d.get("pvBeitrag")),
    ]
    kv_h = 3.6 * mm * len(kv) + 4 * mm
    net_h = max(kv_h, 28 * mm)
    foot_h = 28 * mm
    # Pin totals + payout to the bottom of A4 so the sheet is not a short strip.
    y = min(y, foot_h + net_h + 8 * mm)
    stroke(LINE, 0.45)
    c.setFillColor(colors.white)
    c.rect(left, y - net_h, split, net_h, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#f3f8f9"))
    c.rect(left + split + mid_gap, y - net_h, usable - split - mid_gap, net_h, fill=1, stroke=1)
    ky = y - 5 * mm
    for lab, val in kv:
        text(left + 2 * mm, ky, lab, size=7, color=MUTED)
        text_right(left + split - 2 * mm, ky, val, size=7.5)
        ky -= 3.6 * mm
    ny = y - 8 * mm
    net_left = left + split + mid_gap
    net_right = right
    text(net_left + 2.5 * mm, ny, "Netto-Verdienst", size=7, color=MUTED)
    text_right(net_right - 2.5 * mm, ny, d.get("netVerdienst") or d.get("netTotal"), size=12, bold=True, color=NAVY)
    ny -= 8 * mm
    text(net_left + 2.5 * mm, ny, "Auszahlungsbetrag", size=7, color=MUTED)
    text_right(net_right - 2.5 * mm, ny, d.get("payout") or d.get("netTotal"), size=11, bold=True, color=NAVY)
    ny -= 7 * mm
    text(net_left + 2.5 * mm, ny, d.get("payHint") or "Überweisung auf das angegebene Konto", size=6.5, color=MUTED)
    y -= net_h + 5 * mm

    third = (usable - 2 * mid_gap) / 3.0
    c.setFillColor(colors.white)
    stroke(LINE, 0.7)
    c.line(left, y + 2 * mm, right, y + 2 * mm)
    y -= 2 * mm
    text(left, y - 4 * mm, _s(d.get("bank")), size=7.5)
    text(left, y - 8 * mm, _s(d.get("konto")), size=7.5)
    text(left + third + mid_gap, y - 4 * mm, "AG-Anteil SV", size=6.5, color=MUTED)
    text_right(left + 2 * third + mid_gap, y - 4 * mm, d.get("agSv"), size=8)
    text(left + third + mid_gap, y - 8 * mm, "Umlagen", size=6.5, color=MUTED)
    text_right(left + 2 * third + mid_gap, y - 8 * mm, d.get("agExtra"), size=8)
    c.setFillColor(PAY)
    c.roundRect(left + 2 * third + 2 * mid_gap, y - foot_h + 4 * mm, third, foot_h - 4 * mm, 2 * mm, fill=1, stroke=0)
    ink(colors.white)
    font("Helvetica", 6.5)
    c.drawString(left + 2 * third + 2 * mid_gap + 3 * mm, y - 6 * mm, "Auszahlung")
    font("Helvetica-Bold", 11)
    c.drawRightString(right - 3 * mm, y - 12 * mm, _s(d.get("payout") or d.get("netTotal") or "0,00"))
    text(left, 10 * mm, "WorkPass Lohn · Entgeltbescheinigung nach § 108 Abs. 3 Satz 1 GewO", size=6, color=MUTED)

    c.showPage()
    c.save()
    return buf.getvalue()
