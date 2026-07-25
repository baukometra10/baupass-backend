"""OnlyOffice Document Server bridge for WorkPass docs editor."""
from __future__ import annotations

import base64
import hashlib
import hmac
import html as html_lib
import io
import json
import os
import re
import time
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TABLE_RE = re.compile(r"<table\b[^>]*>[\s\S]*?</table>", re.I)


def onlyoffice_enabled() -> bool:
    flag = (os.getenv("ONLYOFFICE_ENABLED") or "").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    if flag in {"1", "true", "yes", "on"}:
        return True
    # Auto-enable when URL is configured
    return bool((os.getenv("ONLYOFFICE_URL") or "").strip())


def onlyoffice_browser_url() -> str:
    return (os.getenv("ONLYOFFICE_URL") or "http://127.0.0.1:8081").rstrip("/")


def probe_document_server(timeout: float = 2.5) -> dict[str, Any]:
    """Best-effort reachability check against the Document Server."""
    base = onlyoffice_browser_url()
    if not onlyoffice_enabled():
        return {
            "reachable": False,
            "checkedUrl": "",
            "error": "disabled",
            "hint": "ONLYOFFICE_URL setzen und Document Server starten (deploy/start-onlyoffice.ps1).",
        }
    candidates = (
        f"{base}/healthcheck",
        f"{base}/web-apps/apps/api/documents/api.js",
        f"{base}/",
    )
    last_err = ""
    for url in candidates:
        try:
            req = Request(url, headers={"User-Agent": "WorkPass-OnlyOffice/1.0"})
            with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — operator-configured OnlyOffice URL
                code = int(getattr(resp, "status", 200) or 200)
                if 200 <= code < 500:
                    return {
                        "reachable": True,
                        "checkedUrl": url,
                        "statusCode": code,
                        "hint": None,
                    }
                last_err = f"HTTP {code}"
        except Exception as exc:
            last_err = str(exc)[:180]
            continue
    return {
        "reachable": False,
        "checkedUrl": candidates[0],
        "error": last_err or "unreachable",
        "hint": (
            f"Document Server unter {base} nicht erreichbar. "
            "Docker starten (deploy/start-onlyoffice.ps1) und ONLYOFFICE_URL prüfen."
        ),
    }


def onlyoffice_jwt_secret() -> str:
    return (os.getenv("ONLYOFFICE_JWT_SECRET") or "workpass-onlyoffice-dev-secret").strip()


def app_public_url() -> str:
    return (os.getenv("PUBLIC_BASE_URL") or "http://127.0.0.1:8080").rstrip("/")


def app_url_for_onlyoffice() -> str:
    """URL that the OnlyOffice container uses to reach the WorkPass API."""
    return (
        os.getenv("ONLYOFFICE_APP_URL")
        or os.getenv("PUBLIC_BASE_URL")
        or "http://host.docker.internal:8080"
    ).rstrip("/")


def docs_storage_dir() -> Path:
    root = Path(os.getenv("BAUPASS_DOCS_STORAGE") or "").strip()
    if not root:
        root = Path(__file__).resolve().parents[3] / "data" / "editor_docs"
    else:
        root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def docx_path_for(doc_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(doc_id))[:80] or "doc"
    return docs_storage_dir() / f"{safe}.docx"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._skip = True
        if tag in {"br", "p", "div", "h1", "h2", "h3", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self._skip = False
        if tag in {"p", "div", "h1", "h2", "h3", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


class _RichBlockExtractor(HTMLParser):
    """Extract structured blocks for DOCX (heading / list / normal)."""

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[dict[str, Any]] = []
        self._buf: list[str] = []
        self._style = "Normal"
        self._skip = False
        self._bold = 0
        self._runs: list[dict[str, Any]] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._skip = True
            return
        if tag in {"h1", "h2", "h3", "p", "li", "div", "blockquote"}:
            self._flush()
            if tag == "h1":
                self._style = "Heading1"
            elif tag == "h2":
                self._style = "Heading2"
            elif tag == "h3":
                self._style = "Heading3"
            elif tag == "li":
                self._style = "ListParagraph"
            else:
                self._style = "Normal"
        if tag == "br":
            self._push_run("\n", False)
        if tag in {"strong", "b"}:
            self._flush_run_buffer()
            self._bold += 1
        if tag in {"em", "i"}:
            self._flush_run_buffer()

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self._skip = False
            return
        if tag in {"strong", "b"} and self._bold:
            self._flush_run_buffer()
            self._bold -= 1
        if tag in {"h1", "h2", "h3", "p", "li", "div", "blockquote"}:
            self._flush()

    def handle_data(self, data):
        if not self._skip and data:
            self._buf.append(data)

    def _flush_run_buffer(self):
        text = "".join(self._buf)
        self._buf = []
        if text:
            self._push_run(text, self._bold > 0)

    def _push_run(self, text: str, bold: bool):
        if not text:
            return
        if self._runs and self._runs[-1]["bold"] == bold and not text.startswith("\n"):
            self._runs[-1]["text"] += text
        else:
            self._runs.append({"text": text, "bold": bold})

    def _flush(self):
        self._flush_run_buffer()
        runs = [r for r in self._runs if str(r.get("text") or "").strip() or "\n" in str(r.get("text") or "")]
        self._runs = []
        text = "".join(str(r.get("text") or "") for r in runs).strip()
        if text:
            self.blocks.append({"style": self._style, "runs": runs or [{"text": text, "bold": False}]})
        self._style = "Normal"


def html_to_rich_blocks(html: str) -> list[dict[str, Any]]:
    parser = _RichBlockExtractor()
    try:
        parser.feed(html or "")
        parser._flush()
    except Exception:
        return [{"style": "Normal", "runs": [{"text": p, "bold": False}]} for p in html_to_paragraphs(html)]
    return parser.blocks or [{"style": "Normal", "runs": [{"text": "", "bold": False}]}]


def html_to_paragraphs(html: str) -> list[str]:
    parser = _TextExtractor()
    try:
        parser.feed(html or "")
    except Exception:
        text = _HTML_TAG_RE.sub(" ", html or "")
        return [p.strip() for p in text.splitlines() if p.strip()] or [""]
    raw = "".join(parser.parts)
    paras = [re.sub(r"[ \t]+", " ", p).strip() for p in raw.splitlines()]
    paras = [p for p in paras if p]
    return paras or [""]


def _xml_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _mm_to_twips(mm_val: float) -> int:
    # 1 mm ≈ 56.7 twips
    return max(400, int(float(mm_val) * 56.7))


def _cell_text(fragment: str) -> str:
    text = _HTML_TAG_RE.sub(" ", fragment or "")
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_html_table(table_html: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in re.finditer(r"<tr\b[^>]*>([\s\S]*?)</tr>", table_html or "", re.I):
        cells: list[str] = []
        for cell in re.finditer(r"<t[dh]\b[^>]*>([\s\S]*?)</t[dh]>", tr.group(1), re.I):
            cells.append(_cell_text(cell.group(1)))
        if cells:
            rows.append(cells)
    return rows or [[""]]


def _extract_html_tables(html: str) -> tuple[str, list[list[list[str]]]]:
    tables: list[list[list[str]]] = []

    def _repl(match: re.Match) -> str:
        idx = len(tables)
        tables.append(_parse_html_table(match.group(0)))
        return f"<p>[[WPTABLE:{idx}]]</p>"

    cleaned = _TABLE_RE.sub(_repl, html or "")
    return cleaned, tables


def _table_to_ooxml(rows: list[list[str]], *, usable_twips: int = 9000) -> str:
    cols = max((len(r) for r in rows), default=1) or 1
    col_w = max(720, int(usable_twips // cols))
    grid = "".join(f'<w:gridCol w:w="{col_w}"/>' for _ in range(cols))
    border = 'w:val="single" w:sz="4" w:space="0" w:color="666666"'
    trs: list[str] = []
    for row in rows:
        tcs: list[str] = []
        for i in range(cols):
            cell = row[i] if i < len(row) else ""
            tcs.append(
                f'<w:tc><w:tcPr><w:tcW w:w="{col_w}" w:type="dxa"/></w:tcPr>'
                f"<w:p><w:r><w:t>{_xml_escape(cell)}</w:t></w:r></w:p></w:tc>"
            )
        trs.append(f"<w:tr>{''.join(tcs)}</w:tr>")
    return (
        "<w:tbl>"
        "<w:tblPr>"
        '<w:tblW w:w="0" w:type="auto"/>'
        "<w:tblBorders>"
        f"<w:top {border}/><w:left {border}/><w:bottom {border}/><w:right {border}/>"
        f"<w:insideH {border}/><w:insideV {border}/>"
        "</w:tblBorders>"
        "</w:tblPr>"
        f"<w:tblGrid>{grid}</w:tblGrid>"
        f"{''.join(trs)}"
        "</w:tbl>"
    )


def build_docx_bytes(*, title: str, html: str, layout: dict[str, Any] | None = None) -> bytes:
    """OOXML .docx from HTML with headings/bold, page layout, and embedded images/signatures."""
    img_store: list[tuple[str, bytes]] = []

    def _take_img(match: re.Match) -> str:
        src = match.group(1)
        m = re.match(r"data:(image/[a-zA-Z0-9.+-]+);base64,(.+)", src, re.I | re.S)
        if not m:
            return ""
        mime = m.group(1).lower()
        try:
            raw = base64.b64decode(m.group(2), validate=False)
        except Exception:
            return ""
        if not raw or len(raw) > 3_500_000:
            return ""
        ext = "png"
        if "jpeg" in mime or "jpg" in mime:
            ext = "jpg"
        elif "gif" in mime:
            ext = "gif"
        elif "webp" in mime:
            ext = "webp"
        idx = len(img_store)
        img_store.append((ext, raw))
        return f"[[WPIMG:{idx}]]"

    cleaned = re.sub(
        r'<img[^>]+src=["\'](data:image/[^"\']+)["\'][^>]*/?>',
        _take_img,
        html or "",
        flags=re.I,
    )
    cleaned, table_store = _extract_html_tables(cleaned)
    blocks = html_to_rich_blocks(cleaned)
    body_parts: list[str] = []
    media_files: list[tuple[str, bytes]] = []
    rel_extra: list[str] = []
    ctype_extra: set[str] = {
        '<Default Extension="png" ContentType="image/png"/>',
        '<Default Extension="jpg" ContentType="image/jpeg"/>',
        '<Default Extension="jpeg" ContentType="image/jpeg"/>',
    }
    next_rid = 3

    def _drawing_xml(rid: str, cx: int = 3048000, cy: int = 1143000) -> str:
        return (
            f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="1" name="Picture"/>'
            f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="img"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            f"</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>"
        )

    def _runs_to_xml(runs: list[dict[str, Any]]) -> str:
        nonlocal next_rid
        out: list[str] = []
        for run in runs or []:
            text_val = str(run.get("text") or "")
            if not text_val:
                continue
            parts = re.split(r"(\[\[WPIMG:\d+\]\])", text_val)
            for part in parts:
                m = re.fullmatch(r"\[\[WPIMG:(\d+)\]\]", part)
                if m:
                    idx = int(m.group(1))
                    if idx < 0 or idx >= len(img_store):
                        continue
                    ext, raw = img_store[idx]
                    name = f"image{idx + 1}.{ext}"
                    media_files.append((f"word/media/{name}", raw))
                    rid = f"rId{next_rid}"
                    next_rid += 1
                    rel_extra.append(
                        f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/>'
                    )
                    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
                    ctype_extra.add(f'<Default Extension="{ext}" ContentType="{mime}"/>')
                    cx, cy = (3800000, 2200000) if len(raw) > 80000 else (3048000, 1143000)
                    out.append(_drawing_xml(rid, cx, cy))
                    continue
                space_attr = ' xml:space="preserve"' if part.startswith(" ") or part.endswith(" ") else ""
                rpr = "<w:rPr><w:b/></w:rPr>" if run.get("bold") else ""
                chunks = part.split("\n")
                for i, chunk in enumerate(chunks):
                    if i:
                        out.append("<w:r><w:br/></w:r>")
                    if chunk:
                        sa = ' xml:space="preserve"' if chunk.startswith(" ") or chunk.endswith(" ") else space_attr
                        out.append(f"<w:r>{rpr}<w:t{sa}>{_xml_escape(chunk)}</w:t></w:r>")
        return "".join(out)

    if title:
        body_parts.append(
            f'<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr>'
            f"<w:r><w:t>{_xml_escape(title)}</w:t></w:r></w:p>"
        )
    for block in blocks:
        runs = block.get("runs") or []
        plain = "".join(str(r.get("text") or "") for r in runs).strip()
        tm = re.fullmatch(r"\[\[WPTABLE:(\d+)\]\]", plain)
        if tm:
            tidx = int(tm.group(1))
            if 0 <= tidx < len(table_store):
                body_parts.append(_table_to_ooxml(table_store[tidx]))
            continue
        style = str(block.get("style") or "Normal")
        runs_xml = _runs_to_xml(runs)
        if not runs_xml:
            continue
        p_style = f'<w:pPr><w:pStyle w:val="{_xml_escape(style)}"/></w:pPr>' if style != "Normal" else "<w:pPr/>"
        if style == "ListParagraph":
            p_style = (
                '<w:pPr><w:pStyle w:val="ListParagraph"/>'
                '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
            )
        body_parts.append(f"<w:p>{p_style}{runs_xml}</w:p>")
    if not body_parts:
        body_parts.append("<w:p><w:r><w:t></w:t></w:r></w:p>")

    lay = layout or {}
    page = str(lay.get("pageSize") or "a4").lower()
    if page == "a3":
        pg_w, pg_h = 16838, 23811
    elif page == "a1":
        pg_w, pg_h = 33676, 47622
    else:
        pg_w, pg_h = 11906, 16838

    def _m(key: str, default: float) -> int:
        try:
            return _mm_to_twips(float(lay.get(key) if lay.get(key) is not None else default))
        except (TypeError, ValueError):
            return _mm_to_twips(default)

    mt, mr, mb, ml = _m("marginTopMm", 22), _m("marginRightMm", 20), _m("marginBottomMm", 22), _m("marginLeftMm", 25)

    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>
    {''.join(body_parts)}
    <w:sectPr>
      <w:pgSz w:w="{pg_w}" w:h="{pg_h}"/>
      <w:pgMar w:top="{mt}" w:right="{mr}" w:bottom="{mb}" w:left="{ml}"/>
    </w:sectPr>
  </w:body>
</w:document>"""

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n  '
        + "\n  ".join(
            sorted(
                {
                    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
                    '<Default Extension="xml" ContentType="application/xml"/>',
                    *ctype_extra,
                }
            )
        )
        + '\n  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        + '\n  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
        + '\n  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        + "\n</Types>"
    )

    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>\n'
        '  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>\n'
        + "".join(f"  {r}\n" for r in rel_extra)
        + "</Relationships>"
    )

    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="Normal" w:default="1"><w:name w:val="Normal"/><w:qFormat/></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:qFormat/>
    <w:rPr><w:b/><w:sz w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:qFormat/></w:style>
</w:styles>"""

    numbering_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0">
    <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/><w:lvlJc w:val="left"/>
      <w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/_rels/document.xml.rels", doc_rels)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/styles.xml", styles_xml)
        zf.writestr("word/numbering.xml", numbering_xml)
        for path, raw in media_files:
            zf.writestr(path, raw)
    return buf.getvalue()



def ensure_docx_file(doc: dict[str, Any], *, force: bool = False) -> Path:
    path = docx_path_for(str(doc.get("id") or "doc"))
    if path.exists() and not force and path.stat().st_size > 64:
        return path
    layout = None
    try:
        raw = doc.get("content_json") or ""
        parsed = json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("{") else None
        if isinstance(parsed, dict):
            layout = parsed.get("layout") if isinstance(parsed.get("layout"), dict) else None
    except Exception:
        layout = None
    payload = build_docx_bytes(
        title=str(doc.get("title") or "Dokument"),
        html=str(doc.get("content_html") or doc.get("content_text") or ""),
        layout=layout,
    )
    path.write_bytes(payload)
    return path


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def sign_jwt(payload: dict[str, Any], *, secret: str | None = None, ttl_sec: int = 3600) -> str:
    secret = secret or onlyoffice_jwt_secret()
    header = {"alg": "HS256", "typ": "JWT"}
    body = dict(payload)
    now = int(time.time())
    body.setdefault("iat", now)
    body.setdefault("exp", now + max(60, int(ttl_sec)))
    head_b = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    body_b = _b64url(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{head_b}.{body_b}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{head_b}.{body_b}.{_b64url(sig)}"


def verify_jwt(token: str, *, secret: str | None = None) -> dict[str, Any] | None:
    secret = secret or onlyoffice_jwt_secret()
    try:
        head_b, body_b, sig_b = token.split(".")
    except ValueError:
        return None
    signing_input = f"{head_b}.{body_b}".encode("ascii")
    expected = _b64url(hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig_b):
        return None
    pad = "=" * (-len(body_b) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(body_b + pad).decode("utf-8"))
    except Exception:
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    return payload


def file_access_token(doc_id: str, company_id: str, *, ttl_sec: int = 7200) -> str:
    return sign_jwt(
        {"purpose": "oo_file", "doc_id": doc_id, "company_id": company_id},
        ttl_sec=ttl_sec,
    )


def build_editor_config(
    *,
    doc: dict[str, Any],
    company_id: str,
    user_id: str,
    user_name: str,
    mode: str = "edit",
) -> dict[str, Any]:
    doc_id = str(doc.get("id") or "")
    ensure_docx_file(doc, force=False)
    token = file_access_token(doc_id, company_id)
    base = app_url_for_onlyoffice()
    file_url = f"{base}/api/v2/docs/{doc_id}/onlyoffice/file?company_id={company_id}&oo_token={token}"
    callback_url = f"{base}/api/v2/docs/{doc_id}/onlyoffice/callback?company_id={company_id}"
    key_src = f"{doc_id}:{doc.get('updated_at') or ''}:{docx_path_for(doc_id).stat().st_mtime_ns}"
    document_key = hashlib.sha256(key_src.encode("utf-8")).hexdigest()[:20]
    title = str(doc.get("title") or "Dokument")
    filename = f"{re.sub(r'[^a-zA-Z0-9_\-]+', '_', title)[:60] or 'dokument'}.docx"

    config: dict[str, Any] = {
        "documentType": "word",
        "type": "desktop",
        "document": {
            "title": filename,
            "url": file_url,
            "fileType": "docx",
            "key": document_key,
            "permissions": {
                "edit": mode != "view",
                "download": True,
                "print": True,
                "review": True,
                "comment": True,
            },
        },
        "editorConfig": {
            "mode": "view" if mode == "view" else "edit",
            "lang": "de",
            "callbackUrl": callback_url,
            "user": {
                "id": str(user_id or "user")[:64],
                "name": str(user_name or "Editor")[:120],
            },
            "customization": {
                "autosave": True,
                "forcesave": True,
                "compactHeader": False,
                "toolbarNoTabs": False,
                "unit": "cm",
            },
        },
    }
    token_payload = {k: v for k, v in config.items()}
    config["token"] = sign_jwt(token_payload, ttl_sec=3600)
    return {
        "ok": True,
        "enabled": True,
        "documentServerUrl": onlyoffice_browser_url(),
        "scriptUrl": f"{onlyoffice_browser_url()}/web-apps/apps/api/documents/api.js",
        "config": config,
        "documentId": doc_id,
        "documentKey": document_key,
    }


def download_bytes(url: str, timeout: int = 60) -> bytes:
    req = Request(url, headers={"User-Agent": "WorkPass-OnlyOffice/1.0"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — controlled OnlyOffice callback URL
        return resp.read()


def apply_saved_docx(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def docx_to_plain_preview(path: Path, limit: int = 20000) -> str:
    """Best-effort plain text from docx for DB content_text sync."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
    except Exception:
        return ""
    text = re.sub(r"</w:p>", "\n", xml)
    text = _HTML_TAG_RE.sub("", text)
    text = (
        text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
    )
    return text.strip()[:limit]


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def docx_bytes_to_html(data: bytes) -> str:
    """Convert OOXML .docx bytes to Quill-friendly HTML (paragraphs, headings, lists, tables, images)."""
    import xml.etree.ElementTree as ET

    if not data:
        return "<p><br></p>"

    R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
    R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            xml = zf.read("word/document.xml")
            rel_map: dict[str, str] = {}
            try:
                rels_root = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
                for rel in rels_root:
                    if _local(rel.tag) != "Relationship":
                        continue
                    rid = str(rel.attrib.get("Id") or "").strip()
                    target = str(rel.attrib.get("Target") or "").strip()
                    if rid and target:
                        rel_map[rid] = target
            except Exception:
                rel_map = {}

            media_bytes: dict[str, bytes] = {}
            for rid, target in rel_map.items():
                t = target.replace("\\", "/").lstrip("/")
                candidates = []
                if t.startswith("word/"):
                    candidates.append(t)
                else:
                    candidates.append(f"word/{t}")
                    candidates.append(t)
                for cand in candidates:
                    try:
                        media_bytes[rid] = zf.read(cand)
                        break
                    except Exception:
                        continue
    except Exception:
        return "<p><br></p>"

    try:
        root = ET.fromstring(xml)
    except Exception:
        return "<p><br></p>"

    W_VAL = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val"

    def attr_val(el, key: str = "val") -> str:
        return str(el.attrib.get(W_VAL) or el.attrib.get(key) or "")

    def mime_for(raw: bytes) -> str:
        if raw.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if raw.startswith(b"GIF8"):
            return "image/gif"
        if raw.startswith(b"RIFF") and b"WEBP" in raw[:16]:
            return "image/webp"
        if raw.startswith(b"BM"):
            return "image/bmp"
        return "image/png"

    def image_html_from_tree(el) -> str:
        for node in el.iter():
            ln = _local(node.tag)
            if ln not in {"blip", "imagedata"}:
                continue
            rid = (
                node.attrib.get(R_EMBED)
                or node.attrib.get(R_ID)
                or node.attrib.get("embed")
                or node.attrib.get("id")
                or ""
            ).strip()
            raw = media_bytes.get(rid)
            if not raw:
                continue
            # Cap very large embeds (~2.5MB decoded) to keep editor responsive.
            if len(raw) > 2_500_000:
                continue
            b64 = base64.b64encode(raw).decode("ascii")
            return f'<img src="data:{mime_for(raw)};base64,{b64}" alt="" class="wp-img-md" />'
        return ""

    def run_html(r_el) -> str:
        bold = italic = underline = False
        parts: list[str] = []
        for child in r_el:
            name = _local(child.tag)
            if name == "rPr":
                for pr in child:
                    pn = _local(pr.tag)
                    if pn == "b":
                        bold = True
                    elif pn == "i":
                        italic = True
                    elif pn == "u":
                        underline = True
            elif name == "t":
                parts.append(_xml_escape(child.text or "").replace("\n", "<br>"))
            elif name == "tab":
                parts.append("\t")
            elif name == "br":
                parts.append("<br>")
            elif name in {"drawing", "pict", "object"}:
                img = image_html_from_tree(child)
                if img:
                    parts.append(img)
        out = "".join(parts)
        if not out:
            return ""
        # Don't wrap pure image runs in strong/em (still ok, but skip for cleanliness).
        if out.startswith("<img ") and out.endswith("/>") and "<" not in out[1:-2]:
            return out
        if bold:
            out = f"<strong>{out}</strong>"
        if italic:
            out = f"<em>{out}</em>"
        if underline:
            out = f"<u>{out}</u>"
        return out

    def p_to_html(p_el) -> str:
        tag = "p"
        for child in p_el:
            if _local(child.tag) != "pPr":
                continue
            for pr in child:
                pn = _local(pr.tag)
                if pn == "pStyle":
                    low = attr_val(pr).lower()
                    if "heading1" in low or low == "title":
                        tag = "h1"
                    elif "heading2" in low:
                        tag = "h2"
                    elif "heading3" in low:
                        tag = "h3"
                    elif "list" in low:
                        tag = "li"
                if pn == "numPr":
                    tag = "li"
        runs: list[str] = []
        for child in p_el:
            ln = _local(child.tag)
            if ln == "r":
                piece = run_html(child)
                if piece:
                    runs.append(piece)
            elif ln in {"drawing", "pict"}:
                img = image_html_from_tree(child)
                if img:
                    runs.append(img)
        inner = "".join(runs).strip() or "<br>"
        if tag == "li":
            return f"<ul><li>{inner}</li></ul>"
        return f"<{tag}>{inner}</{tag}>"

    def tbl_to_html(tbl_el) -> str:
        rows_html: list[str] = []
        for tr in tbl_el:
            if _local(tr.tag) != "tr":
                continue
            cells: list[str] = []
            for tc in tr:
                if _local(tc.tag) != "tc":
                    continue
                cell_parts: list[str] = []
                for p in tc:
                    if _local(p.tag) == "p":
                        raw = p_to_html(p)
                        raw = re.sub(r"^<(?:p|h1|h2|h3|ul)>(?:<li>)?", "", raw)
                        raw = re.sub(r"(?:</li>)?</(?:p|h1|h2|h3|ul)>$", "", raw)
                        cell_parts.append(raw)
                cells.append(f"<td>{' '.join(cell_parts) or '&nbsp;'}</td>")
            if cells:
                rows_html.append(f"<tr>{''.join(cells)}</tr>")
        if not rows_html:
            return ""
        return f'<table class="wp-table"><tbody>{"".join(rows_html)}</tbody></table>'

    body = None
    for el in root.iter():
        if _local(el.tag) == "body":
            body = el
            break
    if body is None:
        body = root

    parts: list[str] = []
    for child in list(body):
        name = _local(child.tag)
        if name == "p":
            parts.append(p_to_html(child))
        elif name == "tbl":
            html = tbl_to_html(child)
            if html:
                parts.append(html)

    if not parts:
        return "<p><br></p>"
    merged: list[str] = []
    for part in parts:
        if part.startswith("<ul>") and merged and merged[-1].startswith("<ul>") and merged[-1].endswith("</ul>"):
            merged[-1] = merged[-1][:-5] + part[4:]
        else:
            merged.append(part)
    return "".join(merged)



def new_share_token() -> str:
    import secrets

    return secrets.token_urlsafe(24)


def public_share_url(token: str) -> str:
    base = app_public_url()
    return f"{base}/admin-v2/docs-share.html?t={token}"


# Legacy JWT helpers kept for older links
def share_jwt_secret() -> str:
    return (
        (os.getenv("DOCS_SHARE_SECRET") or "").strip()
        or (os.getenv("BAUPASS_SECRET") or "").strip()
        or onlyoffice_jwt_secret()
    )


def create_share_token(*, doc_id: str, company_id: str, ttl_sec: int = 72 * 3600) -> str:
    return sign_jwt(
        {"purpose": "doc_share", "doc_id": str(doc_id), "company_id": str(company_id)},
        secret=share_jwt_secret(),
        ttl_sec=max(3600, int(ttl_sec)),
    )


def verify_share_token(token: str) -> dict[str, Any] | None:
    payload = verify_jwt(token, secret=share_jwt_secret())
    if not payload or payload.get("purpose") != "doc_share":
        return None
    return payload

