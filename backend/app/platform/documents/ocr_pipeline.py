"""
Document OCR pipeline — tesseract, PDF text, optional AI summary.
"""
from __future__ import annotations

import io
from typing import Any


def extract_text_from_bytes(raw: bytes, filename: str = "") -> dict[str, Any]:
    name = (filename or "").lower()
    engines: list[str] = []

    if name.endswith(".pdf"):
        text = _pdf_text(raw)
        if text:
            engines.append("pdf_text")
            return {"text": text[:8000], "engines": engines}

    text = _tesseract(raw)
    if text:
        engines.append("tesseract")
        return {"text": text[:8000], "engines": engines}

    return {
        "text": f"[binary {len(raw)} bytes — enable pytesseract or upload PDF with extractable text]",
        "engines": [],
    }


def _tesseract(raw: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(raw))
        return (pytesseract.image_to_string(img) or "").strip()
    except Exception:
        return ""


def _pdf_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        parts = []
        for page in reader.pages[:20]:
            parts.append(page.extract_text() or "")
        return "\n".join(parts).strip()
    except Exception:
        try:
            import PyPDF2

            reader = PyPDF2.PdfReader(io.BytesIO(raw))
            parts = []
            for page in reader.pages[:20]:
                parts.append(page.extract_text() or "")
            return "\n".join(parts).strip()
        except Exception:
            return ""
