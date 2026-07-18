"""
Worker mobile app distribution — hybrid native app (Flutter) + legacy browser install.
Not a public app-store SKU; NFC/RFID/HCE modes use /api/worker-app/*.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def sanitize_public_download_url(value: str | None) -> str:
    """Normalize env URLs: strip quotes/BOM that Railway/paste often leave behind."""
    text = (value or "").strip().lstrip("\ufeff")
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"', "`"):
        text = text[1:-1].strip()
    # KEY=https://… pasted as the whole value
    for prefix in (
        "BAUPASS_WORKER_APK_URL=",
        "SUPPIX_WORKER_APK_URL=",
        "BAUPASS_ANDROID_APK_URL=",
        "SUPPIX_ANDROID_APK_URL=",
    ):
        if text.upper().startswith(prefix.upper()):
            text = text[len(prefix) :].strip()
            if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"', "`"):
                text = text[1:-1].strip()
            break
    return text


def build_mobile_distribution(public_base: str) -> dict[str, Any]:
    base = (public_base or "").rstrip("/")
    build_path = Path(__file__).resolve().parents[4] / "worker-build.json"
    build_info: dict[str, Any] = {"build": "latest", "entry": "/emp-app.html"}
    try:
        build_info = json.loads(build_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    build_tag = str(build_info.get("build") or "latest")
    entry = str(build_info.get("entry") or "/emp-app.html")
    launcher = str(build_info.get("launcher") or "/worker-install.html")

    return {
        "distributionModel": "in_system",
        "workerAppKind": "hybrid_native",
        "primaryChannel": "flutter_fcm",
        "legacyChannels": ["pwa_vapid"],
        "hybridModes": [
            {
                "id": "app_qr_badge",
                "label": "App: QR-Code, Badge & PIN",
                "api": "/api/worker-app/login",
                "flutter": True,
                "pwa": False,
                "push": "fcm",
            },
            {
                "id": "gate_reader_nfc_rfid",
                "label": "Physische Karte am Drehkreuz (NFC/RFID)",
                "api": "/api/scan",
                "note": "Leser mit Cloud verbunden — Handy kann offline sein",
            },
            {
                "id": "hce_phone_card",
                "label": "Android HCE (Handy als Karte)",
                "api": "/api/worker-app/hce",
                "companion": "android-hce-companion/",
            },
        ],
        "nativeInstall": {
            "label": "SUPPIX Mitarbeiter-App (Android & iOS)",
            "flutterProject": "mobile/",
            "apiPrefix": "/api/worker-app",
            "pushRegister": "/api/worker-app/push/register",
        },
        "pwaInstall": {
            "label": "SUPPIX Browser-Fallback (Notfall)",
            "deprecated": True,
            "fallbackOnly": True,
            "entry": f"{base}{entry}?worker=1",
            "launcher": f"{base}{launcher}?v={build_tag}",
        },
        "install": {
            "primary": "flutter",
            "pwaLauncher": f"{base}{launcher}?v={build_tag}",
            "pwaEntry": f"{base}{entry}?worker=1&v={build_tag}",
            "joinPage": f"{base}/join.html",
            "apkUrl": sanitize_public_download_url(
                os.getenv("BAUPASS_WORKER_APK_URL") or os.getenv("SUPPIX_WORKER_APK_URL")
            ),
            "testFlightUrl": sanitize_public_download_url(os.getenv("BAUPASS_TESTFLIGHT_URL")),
            "playStoreUrl": sanitize_public_download_url(os.getenv("BAUPASS_PLAY_STORE_URL")),
            "appStoreUrl": sanitize_public_download_url(os.getenv("BAUPASS_APP_STORE_URL")),
            "flutterProject": "mobile/",
            "hceCompanion": "android-hce-companion/",
        },
        "build": build_info,
        "workerAppApiPrefix": "/api/worker-app",
    }
