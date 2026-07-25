"""PDF export for the integrated docs editor (ReportLab) — layout-aware."""
from __future__ import annotations

import base64
import io
import os
import re
from html.parser import HTMLParser
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A3, A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_TAG_RE = re.compile(r"<[^>]+>")
_FONT_REGISTERED = False
_FONT_NAME = "Helvetica"

# ISO sizes in points (1 pt = 1/72 in)
_A1 = (1683.78, 2383.94)  # 594mm × 841mm


def _escape(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _resolve_font() -> str:
    global _FONT_REGISTERED, _FONT_NAME
    if _FONT_REGISTERED:
        return _FONT_NAME
    candidates = [
        os.environ.get("BAUPASS_CONTRACT_FONT"),
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if not path or not os.path.isfile(path):
            continue
        try:
            pdfmetrics.registerFont(TTFont("EditorDocFont", path))
            _FONT_REGISTERED = True
            _FONT_NAME = "EditorDocFont"
            return _FONT_NAME
        except Exception:
            continue
    _FONT_REGISTERED = True
    return _FONT_NAME


def _pagesize_from_layout(layout: dict[str, Any] | None):
    key = str((layout or {}).get("pageSize") or "a4").strip().lower()
    if key == "a3":
        return A3
    if key == "a1":
        return _A1
    return A4


def _margins_mm(layout: dict[str, Any] | None) -> tuple[float, float, float, float]:
    lay = layout or {}

    def _n(key: str, default: float) -> float:
        try:
            return max(8.0, min(50.0, float(lay.get(key) if lay.get(key) is not None else default)))
        except (TypeError, ValueError):
            return default

    return (
        _n("marginLeftMm", 22),
        _n("marginRightMm", 18),
        _n("marginTopMm", 18),
        _n("marginBottomMm", 18),
    )


def _image_from_src(src: str, max_w: float) -> Image | None:
    raw = str(src or "").strip()
    if not raw:
        return None
    try:
        if raw.startswith("data:") and "," in raw:
            header, b64 = raw.split(",", 1)
            data = base64.b64decode(b64)
            img = Image(io.BytesIO(data))
        elif raw.startswith("http://") or raw.startswith("https://"):
            from urllib.request import Request, urlopen

            req = Request(raw, headers={"User-Agent": "WorkPass-DocsPDF/1.0"})
            with urlopen(req, timeout=8) as resp:  # noqa: S310
                data = resp.read()
            img = Image(io.BytesIO(data))
        else:
            return None
        iw, ih = float(img.imageWidth), float(img.imageHeight)
        if iw <= 0 or ih <= 0:
            return None
        scale = min(1.0, max_w / iw)
        img.drawWidth = iw * scale
        img.drawHeight = ih * scale
        return img
    except Exception:
        return None


class _FlowExtractor(HTMLParser):
    """Extract flow items: paragraphs, lists, tables, images, page breaks."""

    def __init__(self) -> None:
        super().__init__()
        self.items: list[dict[str, Any]] = []
        self._buf: list[str] = []
        self._kind = "p"
        self._skip = False
        self._bold = 0
        self._italic = 0
        self._in_table = False
        self._table_rows: list[list[str]] = []
        self._row: list[str] = []
        self._cell_buf: list[str] = []
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs or [])
        if tag in {"script", "style"}:
            self._skip = True
            return
        cls = str(attrs_d.get("class") or "")
        if tag in {"div", "p"} and ("wp-page-break" in cls or "page-break" in cls):
            self._flush_text()
            self.items.append({"type": "pagebreak"})
            return
        if tag == "hr":
            self._flush_text()
            self.items.append({"type": "hr"})
            return
        if tag == "img":
            self._flush_text()
            self.items.append({"type": "image", "src": attrs_d.get("src") or ""})
            return
        if tag == "table":
            self._flush_text()
            self._in_table = True
            self._table_rows = []
            return
        if self._in_table and tag == "tr":
            self._row = []
            return
        if self._in_table and tag in {"td", "th"}:
            self._in_cell = True
            self._cell_buf = []
            return
        if self._in_cell:
            if tag == "br":
                self._cell_buf.append("\n")
            elif tag in {"strong", "b"}:
                self._cell_buf.append("<b>")
            elif tag in {"em", "i"}:
                self._cell_buf.append("<i>")
            return
        if tag in {"h1", "h2", "h3", "p", "li", "div", "header", "footer", "blockquote"}:
            self._flush_text()
            if tag in {"h1", "h2", "h3", "li"}:
                self._kind = tag
            elif tag == "blockquote":
                self._kind = "quote"
            else:
                self._kind = "p"
        if tag == "br":
            self._buf.append("<br/>")
        if tag in {"strong", "b"}:
            self._bold += 1
            self._buf.append("<b>")
        if tag in {"em", "i"}:
            self._italic += 1
            self._buf.append("<i>")
        if tag == "u":
            self._buf.append("<u>")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self._skip = False
            return
        if self._in_table and tag in {"td", "th"}:
            cell = re.sub(r"[ \t]+", " ", "".join(self._cell_buf)).strip()
            self._row.append(cell)
            self._in_cell = False
            self._cell_buf = []
            return
        if self._in_table and tag == "tr":
            if self._row:
                self._table_rows.append(self._row)
            self._row = []
            return
        if tag == "table" and self._in_table:
            self.items.append({"type": "table", "rows": self._table_rows[:]})
            self._in_table = False
            self._table_rows = []
            return
        if self._in_cell:
            if tag in {"strong", "b"}:
                self._cell_buf.append("</b>")
            elif tag in {"em", "i"}:
                self._cell_buf.append("</i>")
            return
        if tag in {"strong", "b"} and self._bold:
            self._bold -= 1
            self._buf.append("</b>")
        if tag in {"em", "i"} and self._italic:
            self._italic -= 1
            self._buf.append("</i>")
        if tag == "u":
            self._buf.append("</u>")
        if tag in {"h1", "h2", "h3", "p", "li", "div", "header", "footer", "blockquote"}:
            self._flush_text()

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_cell:
            self._cell_buf.append(_escape(data))
            return
        self._buf.append(_escape(data))

    def _flush_text(self):
        text = re.sub(r"[ \t]+", " ", "".join(self._buf)).strip()
        text = re.sub(r"</?(?:b|i|u)>\s*</?(?:b|i|u)>", "", text)
        self._buf = []
        if text and text not in {"<b></b>", "<i></i>", "<u></u>"}:
            self.items.append({"type": "text", "kind": self._kind, "text": text})
        self._kind = "p"


def html_to_flow_items(html: str) -> list[dict[str, Any]]:
    parser = _FlowExtractor()
    try:
        parser.feed(html or "")
        parser._flush_text()
    except Exception:
        plain = _TAG_RE.sub(" ", html or "")
        return [{"type": "text", "kind": "p", "text": _escape(p.strip())} for p in plain.splitlines() if p.strip()] or [
            {"type": "text", "kind": "p", "text": ""}
        ]
    return parser.items or [{"type": "text", "kind": "p", "text": ""}]


def html_to_blocks(html: str) -> list[tuple[str, str]]:
    """Backward-compatible block list (text only)."""
    out: list[tuple[str, str]] = []
    for item in html_to_flow_items(html):
        if item.get("type") == "text":
            out.append((str(item.get("kind") or "p"), str(item.get("text") or "")))
        elif item.get("type") == "pagebreak":
            out.append(("p", "—"))
    return out or [("p", "")]


def build_editor_pdf_bytes(
    *,
    title: str,
    content_html: str = "",
    content_text: str = "",
    header_html: str = "",
    footer_html: str = "",
    branding: dict[str, Any] | None = None,
    layout: dict[str, Any] | None = None,
) -> bytes:
    font = _resolve_font()
    styles = getSampleStyleSheet()
    leading_mul = 1.15
    try:
        leading_mul = float((layout or {}).get("lineSpacing") or 1.15)
    except (TypeError, ValueError):
        leading_mul = 1.15
    leading_mul = max(1.0, min(2.0, leading_mul))

    title_style = ParagraphStyle(
        "EditorTitle",
        parent=styles["Heading1"],
        fontName=font,
        fontSize=18,
        leading=22,
        spaceAfter=10,
        alignment=TA_CENTER,
    )
    h1 = ParagraphStyle("EditorH1", parent=styles["Heading1"], fontName=font, fontSize=15, leading=19, spaceBefore=10, spaceAfter=6)
    h2 = ParagraphStyle("EditorH2", parent=styles["Heading2"], fontName=font, fontSize=13, leading=17, spaceBefore=8, spaceAfter=4)
    h3 = ParagraphStyle("EditorH3", parent=styles["Heading3"], fontName=font, fontSize=11.5, leading=15, spaceBefore=6, spaceAfter=3)
    body = ParagraphStyle(
        "EditorBody",
        parent=styles["Normal"],
        fontName=font,
        fontSize=10.5,
        leading=10.5 * leading_mul,
        alignment=TA_JUSTIFY,
        spaceAfter=3,
    )
    quote = ParagraphStyle("EditorQuote", parent=body, leftIndent=12, textColor="#334155", fontSize=10)
    meta = ParagraphStyle("EditorMeta", parent=styles["Normal"], fontName=font, fontSize=8.5, leading=11, textColor="#555555", spaceAfter=6)
    bullet = ParagraphStyle("EditorBullet", parent=body, leftIndent=14, bulletIndent=4)
    cell_style = ParagraphStyle("EditorCell", parent=body, fontSize=9, leading=11, spaceAfter=0)

    brand = branding or {}
    company_name = str(brand.get("companyName") or "").strip()
    story: list[Any] = []

    left_mm, right_mm, top_mm, bottom_mm = _margins_mm(layout)
    pagesize = _pagesize_from_layout(layout)
    page_w, page_h = pagesize
    content_w = page_w - (left_mm + right_mm) * mm

    try:
        from backend.app.platform.workforce.deployment_branding import logo_image_flowable

        logo_img = logo_image_flowable(str(brand.get("logoData") or ""), max_height_mm=16.0)
        if logo_img or company_name:
            name_para = Paragraph(
                _escape(company_name or "Dokument"),
                ParagraphStyle("BrandName", parent=meta, fontName=font, fontSize=11, leading=14, textColor="#0f172a"),
            )
            addr = " · ".join(
                p
                for p in (
                    str(brand.get("address") or "").strip(),
                    str(brand.get("email") or "").strip(),
                )
                if p and p != "—"
            )
            addr_para = Paragraph(_escape(addr), meta) if addr else Spacer(1, 1)
            if logo_img:
                story.append(Table([[logo_img, [name_para, addr_para]]], colWidths=[32 * mm, max(40 * mm, content_w - 32 * mm)]))
            else:
                story.append(name_para)
                if addr:
                    story.append(addr_para)
            story.append(Spacer(1, 4 * mm))
    except Exception:
        pass

    if header_html:
        header_text = " ".join(
            str(it.get("text") or "") for it in html_to_flow_items(header_html) if it.get("type") == "text"
        )
        if header_text:
            story.append(Paragraph(header_text, meta))

    items = html_to_flow_items(content_html) if str(content_html or "").strip() else []
    if not items and str(content_text or "").strip():
        items = [{"type": "text", "kind": "p", "text": _escape(line.strip())} for line in content_text.splitlines() if line.strip()]
    if not items:
        items = [{"type": "text", "kind": "p", "text": "—"}]

    first_text = next((it for it in items if it.get("type") == "text"), None)
    first_plain = _TAG_RE.sub("", str((first_text or {}).get("text") or "")).strip().lower()
    title_plain = str(title or "").strip().lower()
    skip_title = bool(
        title_plain and first_plain and (first_plain == title_plain or (first_text or {}).get("kind") == "h1")
    )
    if title and not skip_title:
        story.append(Paragraph(_escape(title), title_style))
        story.append(Spacer(1, 3 * mm))

    for item in items:
        typ = item.get("type")
        if typ == "pagebreak":
            story.append(PageBreak())
            continue
        if typ == "hr":
            story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#94a3b8"), spaceBefore=4, spaceAfter=6))
            continue
        if typ == "image":
            img = _image_from_src(str(item.get("src") or ""), max_w=content_w)
            if img:
                story.append(KeepTogether([Spacer(1, 2 * mm), img, Spacer(1, 2 * mm)]))
            continue
        if typ == "table":
            rows = item.get("rows") or []
            if not rows:
                continue
            col_n = max(len(r) for r in rows)
            data = []
            for r in rows:
                padded = list(r) + [""] * (col_n - len(r))
                data.append([Paragraph(c or " ", cell_style) for c in padded[:col_n]])
            col_w = content_w / max(1, col_n)
            tbl = Table(data, colWidths=[col_w] * col_n, hAlign="LEFT")
            tbl.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94a3b8")),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            story.append(Spacer(1, 2 * mm))
            story.append(tbl)
            story.append(Spacer(1, 3 * mm))
            continue
        kind = str(item.get("kind") or "p")
        text = str(item.get("text") or "")
        if kind == "h1":
            story.append(Paragraph(text, h1))
        elif kind == "h2":
            story.append(Paragraph(text, h2))
        elif kind == "h3":
            story.append(Paragraph(text, h3))
        elif kind == "li":
            story.append(Paragraph(f"• {text}", bullet))
        elif kind == "quote":
            story.append(Paragraph(text, quote))
        else:
            story.append(Paragraph(text, body))

    footer_text = ""
    if footer_html:
        footer_text = " ".join(
            str(it.get("text") or "") for it in html_to_flow_items(footer_html) if it.get("type") == "text"
        )
    elif company_name or brand.get("address") or brand.get("email"):
        footer_text = " · ".join(
            p
            for p in (
                company_name,
                str(brand.get("address") or "").strip(),
                str(brand.get("contact") or "").strip(),
                str(brand.get("email") or "").strip(),
            )
            if p and p != "—"
        )

    def _draw_page(canvas, doc_tmpl):
        wm = str((layout or {}).get("watermark") or "").strip().lower()
        if wm:
            labels = {
                "draft": "ENTWURF",
                "confidential": "VERTRAULICH",
                "copy": "KOPIE",
            }
            text = labels.get(wm, wm.upper())
            canvas.saveState()
            canvas.setFillColorRGB(0.78, 0.81, 0.85)
            canvas.setFont(font, 54)
            canvas.translate(page_w / 2.0, page_h / 2.0)
            canvas.rotate(38)
            canvas.drawCentredString(0, 0, text)
            canvas.restoreState()
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColorRGB(0.4, 0.45, 0.5)
        y = max(8 * mm, bottom_mm * mm * 0.45)
        if footer_text:
            canvas.drawString(left_mm * mm, y, str(footer_text)[:90])
        canvas.drawRightString(page_w - right_mm * mm, y, str(canvas.getPageNumber()))
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=pagesize,
        leftMargin=left_mm * mm,
        rightMargin=right_mm * mm,
        topMargin=top_mm * mm,
        bottomMargin=max(bottom_mm, 14) * mm,
        title=str(title or "Dokument")[:120],
    )
    doc.build(story, onFirstPage=_draw_page, onLaterPages=_draw_page)
    return buf.getvalue()
