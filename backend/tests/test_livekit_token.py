"""LiveKit JWT smoke tests."""
from backend.app.platform.conferences.livekit_token import create_livekit_token


def test_livekit_token_shape():
    token = create_livekit_token(
        api_key="APIkey",
        api_secret="secret-value-for-tests-only",
        identity="worker:1",
        name="Ali",
        room="room-1",
        ttl_seconds=120,
    )
    parts = token.split(".")
    assert len(parts) == 3
    assert all(parts)


def test_livekit_room_list_token_without_room():
    token = create_livekit_token(
        api_key="APIkey",
        api_secret="secret-value-for-tests-only",
        identity="diag",
        room_join=False,
        room_list=True,
        ttl_seconds=60,
    )
    assert token.count(".") == 2
