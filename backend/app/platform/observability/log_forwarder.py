"""
Centralized logging — forward structured JSON lines to HTTP endpoint (Loki/ELK).
Set BAUPASS_LOG_FORWARD_URL=https://...
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from urllib import request as urlrequest

logger = logging.getLogger("baupass.log_forward")


class HttpForwardHandler(logging.Handler):
    _queue: "queue.Queue[bytes]" = queue.Queue(maxsize=2000)
    _worker_started = False
    _worker_lock = threading.Lock()

    @classmethod
    def _start_worker(cls) -> None:
        with cls._worker_lock:
            if cls._worker_started:
                return
            t = threading.Thread(target=cls._worker_loop, daemon=True, name="baupass-log-forwarder")
            t.start()
            cls._worker_started = True

    @classmethod
    def _worker_loop(cls) -> None:
        while True:
            payload = cls._queue.get()
            try:
                cls._post_payload(payload)
            except Exception:
                pass

    @staticmethod
    def _post_payload(payload: bytes) -> None:
        url = os.getenv("BAUPASS_LOG_FORWARD_URL", "").strip()
        if not url:
            return
        token = os.getenv("BAUPASS_LOG_FORWARD_TOKEN", "").strip()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urlrequest.Request(url, data=payload, headers=headers, method="POST")
        # Light retry for transient network failures
        for attempt in range(2):
            try:
                urlrequest.urlopen(req, timeout=2)
                return
            except Exception:
                if attempt == 0:
                    time.sleep(0.2)
                else:
                    raise

    def emit(self, record: logging.LogRecord) -> None:
        url = os.getenv("BAUPASS_LOG_FORWARD_URL", "").strip()
        if not url:
            return
        try:
            payload = json.dumps(
                {
                    "level": record.levelname,
                    "message": record.getMessage(),
                    "logger": record.name,
                }
            ).encode()
            self._start_worker()
            self._queue.put_nowait(payload)
        except queue.Full:
            # Drop when buffer is saturated to avoid blocking app threads.
            pass
        except Exception:
            pass


def attach_log_forwarder() -> None:
    if os.getenv("BAUPASS_LOG_FORWARD_URL", "").strip():
        logging.getLogger().addHandler(HttpForwardHandler())
