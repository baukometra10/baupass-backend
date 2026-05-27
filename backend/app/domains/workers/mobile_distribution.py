"""
Worker mobile app distribution — loaded from admin/system (PWA + APK + Flutter).
Not a public app-store SKU; Hybrid app (PWA + Flutter) NFC/RFID/HCE modes use /api/worker-app/*.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


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
        "hybridModes": [
            {
                "id": "app_qr_badge",
                "label": "Hybrid app: QR / Badge + PIN",
                "api": "/api/worker-app/login",
                "flutter": True,
                "pwa": True,
            },
            {
                "id": "gate_reader_nfc_rfid",
                "label": "Physical NFC/RFID card on gate reader",
                "api": "/api/scan",
                "note": "Reader connected to cloud; phone offline OK",
            },
            {
                "id": "hce_phone_card",
                "label": "Android HCE (phone emulates card)",
                "api": "/api/worker-app/hce",
                "companion": "android-hce-companion/",
            },
        ],
        "pwaInstall": {
            "label": "PWA install from browser (same backend)",
            "entry": f"{base}{entry}?worker=1",
            "launcher": f"{base}{launcher}?v={build_tag}",
        },
        "install": {
            "pwaLauncher": f"{base}{launcher}?v={build_tag}",
            "pwaEntry": f"{base}{entry}?worker=1&v={build_tag}",
            "joinPage": f"{base}/join.html",
            "apkUrl": (os.getenv("BAUPASS_WORKER_APK_URL") or "").strip(),
            "testFlightUrl": (os.getenv("BAUPASS_TESTFLIGHT_URL") or "").strip(),
            "playStoreUrl": (os.getenv("BAUPASS_PLAY_STORE_URL") or "").strip(),
            "appStoreUrl": (os.getenv("BAUPASS_APP_STORE_URL") or "").strip(),
            "flutterProject": "mobile/",
            "hceCompanion": "android-hce-companion/",
        },
        "build": build_info,
        "workerAppApiPrefix": "/api/worker-app",
    }
