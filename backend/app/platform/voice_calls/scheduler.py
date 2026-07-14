"""Background expiry for ringing voice calls (missed-call lifecycle)."""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)
_started = False


def expire_voice_calls_once() -> int:
    try:
        from backend.app.database import get_db
        from backend.app.platform.voice_calls.service import VoiceCallService

        db = get_db()
        count = VoiceCallService(db).expire_stale_calls()
        if count:
            db.commit()
        return count
    except Exception as exc:
        logger.warning("voice_call expire tick failed: %s", exc)
        return 0


def voice_call_scheduler_loop(interval_seconds: float = 15.0) -> None:
    while True:
        expire_voice_calls_once()
        time.sleep(max(5.0, float(interval_seconds or 15.0)))


def bootstrap_voice_call_scheduler(*, interval_seconds: float = 15.0) -> None:
    global _started
    if _started:
        return
    _started = True
    threading.Thread(
        target=voice_call_scheduler_loop,
        kwargs={"interval_seconds": interval_seconds},
        name="baupass-voice-call-expiry",
        daemon=True,
    ).start()
