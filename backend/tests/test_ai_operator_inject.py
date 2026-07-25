"""AI Operator FAB HTML injection middleware."""
from __future__ import annotations


def test_inject_skips_when_present():
    from backend.app.middleware.ai_operator_inject import _inject_into_html

    html = b"<html><body><script src=\"/ai-operator-fab.js\"></script></body></html>"
    assert _inject_into_html(html) is None


def test_inject_before_body_close():
    from backend.app.middleware.ai_operator_inject import _SCRIPT_MARKER, _inject_into_html

    html = b"<html><body><h1>Hi</h1></body></html>"
    out = _inject_into_html(html)
    assert out is not None
    assert _SCRIPT_MARKER.encode() in out
    assert out.index(_SCRIPT_MARKER.encode()) < out.lower().index(b"</body>")
    # Voice stack is preloaded with FAB when BAUPASS_AI_OPERATOR_VOICE is on (default).
    assert b"ai-voice-ui.js" in out
    assert b"ai-operator-fab.css" in out
    # Welcome TTS is on by default (once per company/day for admins).
    assert b"BAUPASS_AI_OPERATOR_WELCOME=true" in out


def test_inject_does_not_duplicate_existing_voice_ui():
    from backend.app.middleware.ai_operator_inject import _inject_into_html

    html = b'<html><body><script src="/ai-voice-ui.js?v=page"></script></body></html>'
    out = _inject_into_html(html)
    assert out is not None
    assert out.count(b"ai-voice-ui.js") == 1
    assert b"ai-operator-fab.js" in out


def test_path_skip_api_and_assets():
    from backend.app.middleware.ai_operator_inject import _path_should_skip

    assert _path_should_skip("/api/v2/auth/session") is True
    assert _path_should_skip("/ai-operator-fab.js") is True
    assert _path_should_skip("/admin-v2/index.html") is False
    assert _path_should_skip("/index.html") is False
    assert _path_should_skip("/foreman.html") is False
    assert _path_should_skip("/desktop/splash.html") is True
