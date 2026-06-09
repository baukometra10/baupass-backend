"""Optional Azure Face API verify (BAUPASS_AZURE_FACE_ENDPOINT + BAUPASS_AZURE_FACE_KEY)."""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any


def _azure_config() -> tuple[str, str] | None:
    endpoint = (os.getenv("BAUPASS_AZURE_FACE_ENDPOINT") or "").strip().rstrip("/")
    key = (os.getenv("BAUPASS_AZURE_FACE_KEY") or "").strip()
    if endpoint and key:
        return endpoint, key
    return None


def _decode_image_b64(value: str) -> bytes | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.startswith("data:"):
        comma = raw.find(",")
        raw = raw[comma + 1 :] if comma >= 0 else raw
    try:
        return base64.b64decode(raw, validate=False)
    except Exception:
        return None


def _face_request(endpoint: str, key: str, path: str, body: bytes | None = None) -> Any:
    url = f"{endpoint}/face/v1.0{path}"
    headers = {"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/octet-stream"}
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=12) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _detect_face_id(endpoint: str, key: str, image_bytes: bytes) -> str | None:
    try:
        faces = _face_request(endpoint, key, "/detect?returnFaceId=true&recognitionModel=recognition_04", image_bytes)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(faces, list) or not faces:
        return None
    face_id = faces[0].get("faceId")
    return str(face_id) if face_id else None


def detect_faces_in_image(image_bytes: bytes) -> int | None:
    """Return face count, or None when Azure Face is not configured."""
    cfg = _azure_config()
    if not cfg:
        return None
    endpoint, key = cfg
    try:
        faces = _face_request(
            endpoint,
            key,
            "/detect?returnFaceId=false&recognitionModel=recognition_04",
            image_bytes,
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(faces, list):
        return None
    return len(faces)


def verify_worker_snapshot(worker_photo_data: str, snapshot_b64: str) -> bool | None:
    """
    Compare worker reference photo with camera snapshot via Azure Face verify.
    Returns None if Azure is not configured or images are invalid.
    """
    cfg = _azure_config()
    if not cfg:
        return None
    endpoint, key = cfg
    ref_bytes = _decode_image_b64(worker_photo_data)
    snap_bytes = _decode_image_b64(snapshot_b64)
    if not ref_bytes or not snap_bytes:
        return None
    face1 = _detect_face_id(endpoint, key, ref_bytes)
    face2 = _detect_face_id(endpoint, key, snap_bytes)
    if not face1 or not face2:
        return False
    try:
        url = f"{endpoint}/face/v1.0/verify"
        payload = json.dumps({"faceId1": face1, "faceId2": face2}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Ocp-Apim-Subscription-Key": key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(result, dict):
        return None
    if result.get("isIdentical") is True:
        conf = float(result.get("confidence") or 0)
        threshold = float(os.getenv("BAUPASS_AZURE_FACE_MIN_CONFIDENCE") or "0.5")
        return conf >= threshold
    return False
