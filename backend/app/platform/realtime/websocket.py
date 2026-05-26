"""
WebSocket real-time layer (Flask-SocketIO).
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("baupass.websocket")

socketio = None


def init_socketio(flask_app) -> Any:
    global socketio
    try:
        from flask_socketio import SocketIO, emit, join_room

        cors = "*"
        socketio = SocketIO(flask_app, cors_allowed_origins=cors, async_mode="threading", logger=False, engineio_logger=False)

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
        logger.info("WebSocket (SocketIO) enabled")
        return socketio
    except ImportError:
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
