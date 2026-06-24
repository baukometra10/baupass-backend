"""Serve Signotec library, installer, and one-click Windows setup helpers."""
from __future__ import annotations

import base64
import os
from pathlib import Path

from flask import Blueprint, Response, jsonify, redirect, request, send_file

BASE_DIR = Path(__file__).resolve().parents[4]

SIGNOTEC_INSTALLER_FILENAME = "signotec_signoPAD-API_Web_3.5.0.exe"
SIGNOTEC_INSTALLER_DEFAULT_URL = (
    "https://backend.signotec.com/wp-content/uploads/2025/11/"
    "signotec_signoPAD-API_Web_3.5.0.exe"
)

bp = Blueprint("signotec", __name__)


def _signotec_lib_bytes() -> bytes | None:
    target = BASE_DIR / "vendor" / "signotec" / "STPadServerLib.js"
    if target.exists() and target.is_file():
        try:
            return target.read_bytes()
        except OSError:
            pass
    b64 = str(os.getenv("BAUPASS_SIGNOTEC_LIB_BASE64", "") or "").strip()
    if b64:
        try:
            return base64.b64decode(b64)
        except Exception:
            pass
    return None


def _signotec_installer_path() -> Path | None:
    target = BASE_DIR / "vendor" / "signotec" / SIGNOTEC_INSTALLER_FILENAME
    if target.exists() and target.is_file():
        return target
    return None


def _signotec_setup_ps1_content(base: str) -> str:
    script_path = BASE_DIR / "scripts" / "baupass-signotec-bridge-setup.ps1"
    if script_path.exists() and script_path.is_file():
        return script_path.read_text(encoding="utf-8").replace("{{BASE_URL}}", base)
    return (
        f"# SUPPIX Signotec Bridge fallback\n"
        f"$ErrorActionPreference = 'Stop'\n"
        f"Write-Host 'Setup script missing on server. Download installer from {base}/api/signotec/installer'\n"
        f"pause\n"
    )


def _setup_bat_response(base: str) -> Response:
    bat = f"""@echo off
title SUPPIX Signotec Bridge
echo WorkPass: Signotec bridge setup (once per PC, needs admin once)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Join-Path $env:TEMP 'baupass-signotec-setup.ps1'; Invoke-WebRequest -Uri '{base}/api/signotec/setup-helper.ps1' -OutFile $p -UseBasicParsing; & $p"
echo.
pause
"""
    response = Response(bat, mimetype="application/octet-stream")
    response.headers["Content-Disposition"] = 'attachment; filename="baupass-signotec-setup.bat"'
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/api/signotec/lib.js")
def signotec_lib_script():
    data = _signotec_lib_bytes()
    if not data:
        return jsonify({"error": "signotec_lib_missing"}), 404
    response = Response(data, mimetype="application/javascript")
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


@bp.get("/api/signotec/status")
def signotec_lib_status():
    data = _signotec_lib_bytes()
    installer_local = _signotec_installer_path()
    return jsonify({
        "available": bool(data),
        "bytes": len(data) if data else 0,
        "url": "/vendor/signotec/STPadServerLib.js",
        "version": "3.5.0",
        "bridge": {
            "required": True,
            "port": 49494,
            "platform": "windows",
            "installerUrl": "/api/signotec/installer",
            "installerBundled": bool(installer_local),
            "setupUrl": "/api/signotec/setup.bat",
            "setupHelperUrl": "/api/signotec/setup-helper.bat",
            "setupHelperPs1Url": "/api/signotec/setup-helper.ps1",
            "setupPageUrl": "/signotec-setup.html",
            "trustUrl": "https://localhost:49494/",
            "note": "Library is on SUPPIX server; signoPAD-API/Web runs once per PC with USB pad.",
        },
    })


@bp.get("/api/signotec/installer")
def signotec_installer_download():
    local = _signotec_installer_path()
    if local:
        return send_file(
            local,
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=SIGNOTEC_INSTALLER_FILENAME,
        )
    remote = str(os.getenv("BAUPASS_SIGNOTEC_INSTALLER_URL", "") or "").strip()
    if not remote:
        remote = SIGNOTEC_INSTALLER_DEFAULT_URL
    return redirect(remote, code=302)


@bp.get("/api/signotec/setup-helper.ps1")
def signotec_setup_helper():
    base = request.url_root.rstrip("/")
    ps1 = _signotec_setup_ps1_content(base)
    response = Response(ps1, mimetype="application/octet-stream")
    response.headers["Content-Disposition"] = 'attachment; filename="baupass-signotec-setup.ps1"'
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/api/signotec/setup-helper.bat")
def signotec_setup_helper_bat():
    return _setup_bat_response(request.url_root.rstrip("/"))


@bp.get("/api/signotec/setup.bat")
def signotec_setup_bat():
    """Canonical one-file download URL used by signotec-setup.html."""
    return _setup_bat_response(request.url_root.rstrip("/"))


@bp.get("/api/signotec/start-bridge.bat")
def signotec_start_bridge_bat():
    base = request.url_root.rstrip("/")
    bat = f"""@echo off
title SUPPIX Signotec Bridge starten
echo WorkPass: STPadServer starten (Port 49494, Admin)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Join-Path $env:TEMP 'baupass-signotec-setup.ps1'; Invoke-WebRequest -Uri '{base}/api/signotec/setup-helper.ps1' -OutFile $p -UseBasicParsing; & $p -SkipInstall"
echo.
pause
"""
    response = Response(bat, mimetype="application/octet-stream")
    response.headers["Content-Disposition"] = 'attachment; filename="baupass-signotec-start.bat"'
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/api/signotec/check.ps1")
def signotec_check_helper():
    script_path = BASE_DIR / "scripts" / "baupass-signotec-bridge-check.ps1"
    if script_path.exists() and script_path.is_file():
        ps1 = script_path.read_text(encoding="utf-8")
    else:
        ps1 = "Write-Host 'Check script missing'; pause"
    response = Response(ps1, mimetype="application/octet-stream")
    response.headers["Content-Disposition"] = 'attachment; filename="baupass-signotec-check.ps1"'
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.get("/api/signotec/check.bat")
def signotec_check_bat():
    base = request.url_root.rstrip("/")
    bat = f"""@echo off
title SUPPIX Signotec Diagnose
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Join-Path $env:TEMP 'baupass-signotec-check.ps1'; Invoke-WebRequest -Uri '{base}/api/signotec/check.ps1' -OutFile $p -UseBasicParsing; & $p"
"""
    response = Response(bat, mimetype="application/octet-stream")
    response.headers["Content-Disposition"] = 'attachment; filename="baupass-signotec-check.bat"'
    response.headers["Cache-Control"] = "no-store"
    return response


def register_signotec_blueprint(flask_app) -> None:
    if flask_app.extensions.get("signotec_routes_registered"):
        return
    existing = {rule.rule for rule in flask_app.url_map.iter_rules()}
    if "/api/signotec/status" in existing:
        if "/api/signotec/setup.bat" not in existing:
            flask_app.add_url_rule(
                "/api/signotec/setup.bat",
                "signotec_setup_bat_alias",
                signotec_setup_bat,
                methods=["GET"],
            )
        flask_app.extensions["signotec_routes_registered"] = True
        return
    flask_app.register_blueprint(bp)
    flask_app.extensions["signotec_routes_registered"] = True
