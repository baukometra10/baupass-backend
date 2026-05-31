"""QR code API — public + authenticated share one URL."""
from __future__ import annotations

import io

import qrcode
from flask import Response, jsonify, request


def _public_qr_image(data: str, size: int) -> Response:
    qr = qrcode.QRCode(border=1, box_size=10)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img = img.resize((size, size))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return Response(buffer.getvalue(), mimetype="image/png")


def api_qr_png():
    """GET /api/qr.png — public QR or stricter admin session payload."""
    from backend.server import (
        _qr_png_response,
        get_auth_token_from_request,
        get_user_from_session_token,
    )

    data = (request.args.get("data") or "").strip()
    token = get_auth_token_from_request()
    user = get_user_from_session_token(token) if token else None

    if user:
        if not data or len(data) > 2048:
            return jsonify({"error": "invalid_qr_data"}), 400
        return _qr_png_response(data)

    if not data:
        return jsonify({"error": "missing_data"}), 400
    try:
        size = int(request.args.get("size") or 280)
    except ValueError:
        size = 280
    size = max(120, min(size, 1024))
    return _public_qr_image(data, size)


def api_qr_hex():
    """GET /api/qr — PNG bytes as hex JSON (no auth)."""
    data = (request.args.get("data") or "").strip()
    if not data:
        return jsonify({"error": "missing_data"}), 400
    try:
        size = int(request.args.get("size") or 280)
    except ValueError:
        size = 280
    size = max(120, min(size, 1024))
    resp = _public_qr_image(data, size)
    return jsonify({"pngHex": resp.get_data().hex()})
