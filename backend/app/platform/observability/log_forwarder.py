"""
Centralized logging — forward structured JSON lines to HTTP endpoint (Loki/ELK).
Set BAUPASS_LOG_FORWARD_URL=https://...
"""
from __future__ import annotations

import json
import logging
import os
from urllib import request as urlrequest

logger = logging.getLogger("baupass.log_forward")


class HttpForwardHandler(logging.Handler):
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
            req = urlrequest.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            urlrequest.urlopen(req, timeout=2)
        except Exception:
            pass


def attach_log_forwarder() -> None:
    if os.getenv("BAUPASS_LOG_FORWARD_URL", "").strip():
        logging.getLogger().addHandler(HttpForwardHandler())
