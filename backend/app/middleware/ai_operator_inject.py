"""
Inject the ubiquitous AI Operator FAB into every HTML page response.

Idempotent: skips if the script is already present in the document.
Safe: never touches API/binary/streaming responses; best-effort only.

Voice stack (ai-voice-ui) is only injected when the page does NOT already ship it.
That prevents a second BaupassAiUi load from wiping an already-bound mic
(Command Center / Enterprise Hub / contracts).
"""
from __future__ import annotations

import os
import re

from flask import Flask, Response, request

# Bump when shipping FAB stability / voice prep fixes (cache bust for all pages).
FAB_SCRIPT_VERSION = os.getenv("BAUPASS_AI_OPERATOR_FAB_VERSION", "20260725r").strip() or "20260725r"
VOICE_UI_VERSION = os.getenv("BAUPASS_AI_VOICE_UI_VERSION", "20260725voice13").strip() or "20260725voice13"

_SCRIPT_MARKER = "ai-operator-fab.js"
_VOICE_MARKER = "ai-voice-ui.js"


def _voice_inject_enabled() -> bool:
    return os.getenv("BAUPASS_AI_OPERATOR_VOICE", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _welcome_inject_enabled() -> bool:
    """On by default — speak a short greeting once per company/day for admins."""
    return os.getenv("BAUPASS_AI_OPERATOR_WELCOME", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _build_inject_snippet(*, include_voice: bool) -> str:
    parts = ["\n<!-- baupass-ai-operator -->"]
    if include_voice and _voice_inject_enabled():
        parts.append(
            f'<link rel="stylesheet" href="/ai-voice-ui.css?v={VOICE_UI_VERSION}" />'
            f'<script src="/ai-voice-ui.js?v={VOICE_UI_VERSION}" defer></script>'
        )
    # Expose welcome flag before FAB boots (default on; set BAUPASS_AI_OPERATOR_WELCOME=0 to disable).
    welcome_js = "true" if _welcome_inject_enabled() else "false"
    parts.append(f"<script>window.BAUPASS_AI_OPERATOR_WELCOME={welcome_js};</script>")
    parts.append(
        f'<link rel="stylesheet" href="/ai-operator-fab.css?v={FAB_SCRIPT_VERSION}" />'
        f'<script src="/ai-operator-fab.js?v={FAB_SCRIPT_VERSION}" defer></script>\n'
    )
    return "".join(parts)


# Tiny chrome / external signer flows — keep clean (FAB still unused without admin auth).
_SKIP_PATH_SUFFIXES: tuple[str, ...] = (
    "/desktop/splash.html",
    "/desktop/incoming-call.html",
)

_SKIP_PATH_EXACT: frozenset[str] = frozenset(
    {
        "/favicon.ico",
    }
)

_BODY_CLOSE_RE = re.compile(br"</body\s*>", re.IGNORECASE)


def _path_should_skip(path: str) -> bool:
    p = (path or "").split("?", 1)[0].lower()
    if not p:
        return True
    if p in _SKIP_PATH_EXACT:
        return True
    for suffix in _SKIP_PATH_SUFFIXES:
        if p.endswith(suffix):
            return True
    # Never inject into API / static binaries
    if p.startswith("/api/") or p.startswith("/socket.io"):
        return True
    if p.endswith(
        (
            ".js",
            ".css",
            ".map",
            ".json",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".svg",
            ".ico",
            ".woff",
            ".woff2",
            ".ttf",
            ".pdf",
            ".wasm",
            ".mp3",
            ".mp4",
            ".webm",
            ".xml",
            ".txt",
            ".ps1",
            ".bat",
        )
    ):
        return True
    return False


def _is_html_response(response: Response) -> bool:
    ctype = (response.headers.get("Content-Type") or "").lower()
    if "text/html" in ctype:
        return True
    # Some send_from_directory responses omit charset; path heuristic as fallback.
    path = (request.path or "").lower()
    return path.endswith(".html") or path in {"/", "/admin", "/admin/", "/enterprise", "/enterprise/"}


def _inject_into_html(data: bytes) -> bytes | None:
    if not data or _SCRIPT_MARKER.encode("ascii") in data:
        return None
    # If the page already ships the shared voice stack, do NOT inject a second copy.
    # A second load replaces window.BaupassAiUi and orphans already-bound mic buttons.
    include_voice = _VOICE_MARKER.encode("ascii") not in data
    snippet = _build_inject_snippet(include_voice=include_voice).encode("utf-8")
    match = _BODY_CLOSE_RE.search(data)
    if not match:
        # No </body> — append at end for malformed shells.
        if data.rstrip().endswith(b">"):
            return data + snippet
        return None
    start, _end = match.span()
    return data[:start] + snippet + data[start:]


def register_ai_operator_inject(flask_app: Flask) -> None:
    """Register after_request HTML injector (runs on every deployment)."""

    enabled = os.getenv("BAUPASS_AI_OPERATOR_FAB", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    if not enabled:
        return

    @flask_app.after_request
    def _inject_ai_operator_fab(response: Response):
        try:
            if response.status_code < 200 or response.status_code >= 300:
                return response
            if _path_should_skip(request.path or ""):
                return response
            if not _is_html_response(response):
                return response

            # File responses often use direct_passthrough — must materialize to inject.
            try:
                if response.direct_passthrough:
                    response.direct_passthrough = False
                raw = response.get_data(as_text=False)
            except Exception:
                return response
            if not isinstance(raw, (bytes, bytearray)):
                return response
            injected = _inject_into_html(bytes(raw))
            if injected is None:
                return response
            response.set_data(injected)
            response.headers["X-Baupass-AI-Operator"] = "1"
            if _voice_inject_enabled() and _VOICE_MARKER.encode("ascii") not in bytes(raw):
                response.headers["X-Baupass-AI-Operator-Voice"] = "1"
            # Length may change — let Flask recompute.
            response.headers.pop("Content-Length", None)
        except Exception:
            # Never break page delivery because of FAB injection.
            pass
        return response
