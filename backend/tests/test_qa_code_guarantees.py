"""Static guarantees for remaining device-QA items that are code-enforced."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_voice_repo_reserves_recvonly_video():
    src = (ROOT / "mobile" / "lib" / "services" / "voice_call_repository.dart").read_text(
        encoding="utf-8"
    )
    assert "_ensureRecvVideoTransceiver" in src
    assert "TransceiverDirection.RecvOnly" in src
    assert "_syncReceiversIntoRemoteStream" in src or "_ingestRemoteTrack" in src


def test_web_voice_reserves_recvonly_video():
    src = (ROOT / "chat-voice-call.js").read_text(encoding="utf-8")
    assert "recvonly" in src.lower() or "RecvOnly" in src


def test_live_map_single_click_opens_targets():
    html = (ROOT / "ops-live-map.html").read_text(encoding="utf-8")
    assert 'marker.on("click"' in html
    assert "camera-watch.html" in html
    assert "chat.html" in html
    assert "workerSearch" in html
    assert "showWorkerTrail" in html
    assert "autoDial" in (ROOT / "backend" / "app" / "platform" / "physical_operations" / "live_map.py").read_text(
        encoding="utf-8"
    )
    trail = (
        ROOT / "backend" / "app" / "platform" / "physical_operations" / "location_trail.py"
    ).read_text(encoding="utf-8")
    assert "maybe_record_location_sample" in trail
    assert "derive_worker_map_status" in trail


def test_lagebild_embeds_live_map():
    app = (ROOT / "admin-v2" / "app.js").read_text(encoding="utf-8")
    assert "lage-map-embed" in app
    assert "ops-live-map.html" in app and "embed=1" in app


def test_no_autodial_in_camera_escalation_defaults():
    brief = (ROOT / "backend" / "app" / "platform" / "physical_operations" / "daily_brief.py").read_text(
        encoding="utf-8"
    )
    assert '"autoDial": False' in brief or "'autoDial': False" in brief
