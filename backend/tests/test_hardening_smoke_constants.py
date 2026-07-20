"""Automated smoke checks for recent hardening (GPS / chat / invoice / Berlin day)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_gps_leave_requires_three_off_site_polls():
    from backend import server

    assert server.SITE_LEAVE_OFF_SITE_POLLS_REQUIRED == 3
    worker_js = (ROOT / "worker-app.js").read_text(encoding="utf-8")
    assert "SITE_OFF_SITE_STRIKES_REQUIRED = 3" in worker_js


def test_chat_mark_read_routes_registered():
    from backend.app.domains.chat import routes as chat_routes

    source = Path(chat_routes.__file__).read_text(encoding="utf-8")
    assert '/chat/threads/<thread_id>/mark-read' in source
    assert '/worker-app/chat/threads/<thread_id>/mark-read' in source


def test_invoice_preview_iframes_are_sandboxed():
    index_html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert 'id="invoicePreviewFrame"' in index_html
    assert 'id="invoicePdfFrame"' in index_html
    assert index_html.count('sandbox="allow-same-origin"') >= 2
    # No script execution in preview sandbox
    assert "allow-scripts" not in index_html.split('id="invoicePreviewFrame"')[1][:200]


def test_stripe_return_url_allowlist():
    from backend.app.domains.billing.stripe_service import allowlisted_return_url

    safe = allowlisted_return_url(
        "https://evil.example/steal",
        fallback="https://suppix-workpass-ai.up.railway.app/billing",
    )
    assert "evil.example" not in safe
    assert "railway.app" in safe or safe.startswith("https://")


def test_document_horizon_uses_berlin_calendar():
    from datetime import datetime, timezone

    from backend.app.platform.physical_operations._common import calendar_day_offset, today_prefix
    from backend.server import access_calendar_day_offset, access_today_prefix

    ref = datetime(2026, 1, 15, 23, 30, tzinfo=timezone.utc)
    assert today_prefix(reference=ref) == "2026-01-16"
    assert access_today_prefix(ref) == "2026-01-16"
    assert calendar_day_offset(30, reference=ref) == "2026-02-15"
    assert access_calendar_day_offset(30, ref) == "2026-02-15"
