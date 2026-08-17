"""DSGVO face/head blur for site-camera stills (privacy by design)."""
from __future__ import annotations

import base64
import io
from typing import Any

from PIL import Image, ImageFilter, ImageDraw

FACE_REVEAL_ROLES = frozenset({"company-admin", "superadmin"})


def can_reveal_faces(role: str) -> bool:
    """Geschäftsführung / platform owner — not office staff."""
    return str(role or "").strip() in FACE_REVEAL_ROLES


def _decode_image(raw_b64: str) -> Image.Image | None:
    data = str(raw_b64 or "").strip()
    if not data:
        return None
    if data.startswith("data:"):
        data = data.split(",", 1)[-1]
    try:
        blob = base64.b64decode(data, validate=False)
    except Exception:
        return None
    if not blob:
        return None
    try:
        img = Image.open(io.BytesIO(blob))
        img.load()
        return img.convert("RGB")
    except Exception:
        return None


def _encode_jpeg(img: Image.Image, *, quality: int = 82) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _detect_faces_cv2(img: Image.Image) -> list[tuple[int, int, int, int]]:
    try:
        import cv2
        import numpy as np
    except Exception:
        return []
    arr = np.array(img)[:, :, ::-1]
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    cascade_path = getattr(getattr(cv2, "data", None), "haarcascades", "") or ""
    xml = f"{cascade_path}haarcascade_frontalface_default.xml" if cascade_path else ""
    faces: list[tuple[int, int, int, int]] = []
    if xml:
        classifier = cv2.CascadeClassifier(xml)
        if not classifier.empty():
            found = classifier.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=4, minSize=(22, 22))
            faces.extend((int(x), int(y), int(w), int(h)) for x, y, w, h in found)
    profile_xml = f"{cascade_path}haarcascade_profileface.xml" if cascade_path else ""
    if profile_xml:
        profile = cv2.CascadeClassifier(profile_xml)
        if not profile.empty():
            found = profile.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=4, minSize=(22, 22))
            faces.extend((int(x), int(y), int(w), int(h)) for x, y, w, h in found)
    return faces


def _detect_faces_skin(img: Image.Image) -> list[tuple[int, int, int, int]]:
    """Fallback when OpenCV is missing: sliding windows over YCbCr skin."""
    w, h = img.size
    if w < 40 or h < 40:
        return []
    ycbcr = img.convert("YCbCr")
    pix = ycbcr.load()
    step = max(8, min(w, h) // 16)
    win = max(28, min(w, h) // 6)
    boxes: list[tuple[int, int, int, int]] = []
    for y in range(0, h - win, step):
        for x in range(0, w - win, step):
            skin = 0
            total = 0
            sample = max(2, win // 10)
            for yy in range(y, y + win, sample):
                for xx in range(x, x + win, sample):
                    _y, cb, cr = pix[xx, yy]
                    total += 1
                    if 77 <= cb <= 127 and 133 <= cr <= 173 and 40 <= _y <= 230:
                        skin += 1
            if total and (skin / total) >= 0.42:
                boxes.append((x, y, win, win))
    return _merge_boxes(boxes, w, h)


def _merge_boxes(
    boxes: list[tuple[int, int, int, int]], width: int, height: int
) -> list[tuple[int, int, int, int]]:
    if not boxes:
        return []
    kept: list[tuple[int, int, int, int]] = []
    for box in sorted(boxes, key=lambda b: b[2] * b[3], reverse=True):
        x, y, w, h = box
        overlap = False
        for kx, ky, kw, kh in kept:
            ix = max(x, kx)
            iy = max(y, ky)
            iw = min(x + w, kx + kw) - ix
            ih = min(y + h, ky + kh) - iy
            if iw > 0 and ih > 0 and (iw * ih) > 0.35 * min(w * h, kw * kh):
                overlap = True
                break
        if not overlap:
            kept.append((max(0, x), max(0, y), min(w, width - x), min(h, height - y)))
        if len(kept) >= 12:
            break
    return kept


def detect_face_boxes(img: Image.Image) -> list[tuple[int, int, int, int]]:
    found = _detect_faces_cv2(img)
    if found:
        return found
    return _detect_faces_skin(img)


def _pad_box(
    x: int, y: int, w: int, h: int, width: int, height: int, *, pad: float = 0.35
) -> tuple[int, int, int, int]:
    dx = int(w * pad)
    dy = int(h * pad)
    nx = max(0, x - dx)
    ny = max(0, y - int(dy * 1.15))
    nw = min(width - nx, w + 2 * dx)
    nh = min(height - ny, h + int(dy * 2.1))
    return nx, ny, nw, nh


def blur_faces_in_image(img: Image.Image) -> tuple[Image.Image, int]:
    boxes = detect_face_boxes(img)
    if not boxes:
        return img, 0
    out = img.copy()
    w, h = out.size
    radius = max(8, min(w, h) // 18)
    for x, y, bw, bh in boxes:
        px, py, pw, ph = _pad_box(x, y, bw, bh, w, h)
        region = out.crop((px, py, px + pw, py + ph)).filter(ImageFilter.GaussianBlur(radius=radius))
        # Oval mask so the blur covers the head, not a harsh rectangle.
        mask = Image.new("L", (pw, ph), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, pw - 1, ph - 1), fill=255)
        out.paste(region, (px, py), mask)
    return out, len(boxes)


def blur_faces_b64(raw_b64: str) -> dict[str, Any]:
    img = _decode_image(raw_b64)
    if img is None:
        return {"ok": False, "blurredB64": "", "faces": 0, "error": "invalid_image"}
    blurred, n = blur_faces_in_image(img)
    return {"ok": True, "blurredB64": _encode_jpeg(blurred), "faces": n}


def protect_camera_image(db, company_id: str, raw_b64: str) -> dict[str, Any]:
    """
    Split a still into public (possibly blurred) and clear vault bytes.

    When face blur is on, the clear copy is stored only for Geschäftsführung reveal.
    """
    from .camera_registry import _trim_snapshot_b64
    from .camera_watch import get_watch_settings

    trimmed = _trim_snapshot_b64(raw_b64)
    if not trimmed:
        return {"public": "", "clear": "", "blurred": False, "faces": 0, "enabled": True}
    enabled = True
    try:
        enabled = bool(get_watch_settings(db, company_id).get("faceBlurEnabled", True))
    except Exception:
        enabled = True
    if not enabled:
        return {"public": trimmed, "clear": "", "blurred": False, "faces": 0, "enabled": False}
    result = blur_faces_b64(trimmed)
    public = str(result.get("blurredB64") or trimmed)
    faces = int(result.get("faces") or 0)
    if not result.get("ok"):
        public = trimmed
    return {
        "public": public or trimmed,
        "clear": trimmed,
        "blurred": bool(faces) or public != trimmed,
        "faces": faces,
        "enabled": True,
    }


def log_face_reveal(
    db,
    *,
    company_id: str,
    actor_user_id: str,
    camera_id: str = "",
    escalation_id: str = "",
    action: str = "reveal",
) -> None:
    try:
        from backend.app.audit.immutable import append_immutable_audit_event

        append_immutable_audit_event(
            db,
            event_type="camera.face_privacy." + str(action or "reveal")[:40],
            payload={
                "cameraId": str(camera_id or "")[:80],
                "escalationId": str(escalation_id or "")[:80],
                "action": str(action or "reveal")[:40],
            },
            company_id=company_id,  # type: ignore[arg-type]
            actor_id=str(actor_user_id or "")[:80],
            source="camera_watch",
        )
        try:
            db.commit()
        except Exception:
            pass
    except Exception:
        pass
