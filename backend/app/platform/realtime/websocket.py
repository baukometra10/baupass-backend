"""
WebSocket real-time layer (Flask-SocketIO).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("baupass.websocket")

socketio = None
_socketio_state: dict[str, Any] = {"enabled": False, "reason": "not_initialized"}


def init_socketio(flask_app) -> Any:
    global socketio
    enabled = os.getenv("BAUPASS_WEBSOCKET_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        _socketio_state.update({"enabled": False, "reason": "disabled_by_env"})
        return None
    try:
        from flask_socketio import SocketIO, emit, join_room

        cors = os.getenv("BAUPASS_WEBSOCKET_CORS", "*").strip() or "*"
        ping_interval = int(os.getenv("BAUPASS_WEBSOCKET_PING_INTERVAL", "25"))
        ping_timeout = int(os.getenv("BAUPASS_WEBSOCKET_PING_TIMEOUT", "20"))
        max_buffer = int(os.getenv("BAUPASS_WEBSOCKET_MAX_HTTP_BUFFER", "1000000"))
        socketio = SocketIO(
            flask_app,
            cors_allowed_origins=cors,
            async_mode="threading",
            logger=False,
            engineio_logger=False,
            ping_interval=max(10, ping_interval),
            ping_timeout=max(10, ping_timeout),
            max_http_buffer_size=max(100000, max_buffer),
        )

        @socketio.on("connect")
        def on_connect():
            emit("connected", {"ok": True})

        @socketio.on("subscribe")
        def on_subscribe(data):
            company_id = str((data or {}).get("company_id", "")).strip()
            if company_id:
                join_room(f"company:{company_id}")
            emit("subscribed", {"company_id": company_id})

        @socketio.on("ping")
        def on_ping():
            emit("pong", {})

        flask_app.extensions["socketio"] = socketio
        _socketio_state.update(
            {
                "enabled": True,
                "reason": "ok",
                "cors": cors,
                "ping_interval": ping_interval,
                "ping_timeout": ping_timeout,
            }
        )
        logger.info("WebSocket (SocketIO) enabled")
        return socketio
    except ImportError:
        _socketio_state.update({"enabled": False, "reason": "flask_socketio_not_installed"})
        logger.warning("flask-socketio not installed — WebSocket disabled")
        return None


def broadcast_event(company_id: int | None, event: dict) -> None:
    if socketio is None:
        return
    try:
        socketio.emit("platform_event", event, room=f"company:{company_id}" if company_id else None)
        socketio.emit("platform_event", event, namespace="/")
    except Exception as exc:
        logger.debug("socketio broadcast failed: %s", exc)


def websocket_status() -> dict[str, Any]:
    return dict(_socketio_state)
