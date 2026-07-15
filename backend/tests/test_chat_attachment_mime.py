from __future__ import annotations

from backend.app.domains.chat.service import ChatService


class _FakeDb:
    """Minimal stub — ChatService methods under test don't need SQL."""

    def execute(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("db should not be touched by classifier helpers")


def test_image_attachment_not_classified_as_audio():
    svc = ChatService(_FakeDb())
    assert svc._is_image_attachment("photo.jpg", "image/jpeg") is True
    assert svc._is_audio_attachment("photo.jpg", "image/jpeg") is False
    assert svc._is_audio_attachment("photo.jpg", "application/octet-stream") is False
    assert svc._is_image_attachment("photo.jpg", "application/octet-stream") is True


def test_e2e_image_filename_not_audio():
    svc = ChatService(_FakeDb())
    assert svc._is_image_attachment("photo.png.e2e", "application/vnd.suppix.e2e+binary") is True
    assert svc._is_audio_attachment("photo.png.e2e", "application/vnd.suppix.e2e+binary") is False


def test_voice_webm_still_audio():
    svc = ChatService(_FakeDb())
    assert svc._is_audio_attachment("voice-123.webm", "audio/webm") is True
    assert svc._is_image_attachment("voice-123.webm", "audio/webm") is False


def test_preview_prefers_photo_over_voice_tokens():
    svc = ChatService(_FakeDb())
    preview = svc._message_preview_text(
        "📎 foto.jpg",
        "company-1",
        attachment_filename="summer.jpg",
        attachment_content_type="image/jpeg",
    )
    assert preview == "photo"


def test_preview_voice_for_audio():
    svc = ChatService(_FakeDb())
    preview = svc._message_preview_text(
        "Sprachnachricht",
        "company-1",
        attachment_filename="voice-1.webm",
        attachment_content_type="audio/webm",
    )
    assert preview == "voice"
