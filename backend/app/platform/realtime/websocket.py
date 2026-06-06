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
_socketio_state: dict[str, Any] = {"enabled": False, "supported": False, "reason": "not_initialized"}


def _serve_engine() -> str:
    return os.getenv("BAUPASS_SERVE_ENGINE", "waitress").strip().lower()


def websocket_transport_supported() -> bool:
    """True when the active WSGI server can handle WebSocket upgrades."""
    return _serve_engine() not in {"waitress", "wsgiref"}


def _websocket_env_enabled() -> bool:
    raw = os.getenv("BAUPASS_WEBSOCKET_ENABLED", "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return websocket_transport_supported()


def init_socketio(flask_app) -> Any:
    global socketio
    if not _websocket_env_enabled():
        reason = "disabled_by_env" if os.getenv("BAUPASS_WEBSOCKET_ENABLED", "").strip() else "waitress_no_websocket"
        _socketio_state.update({"enabled": False, "supported": False, "reason": reason})
        return None
    if not websocket_transport_supported():
        _socketio_state.update({"enabled": False, "supported": False, "reason": "server_no_websocket"})
        return None
    try:
        from flask import request as flask_request
        from flask_socketio import SocketIO, emit, join_room

        cors = os.getenv("BAUPASS_WEBSOCKET_CORS", "*").strip() or "*"
        ping_interval = int(os.getenv("BAUPASS_WEBSOCKET_PING_INTERVAL", "25"))
        ping_timeout = int(os.getenv("BAUPASS_WEBSOCKET_PING_TIMEOUT", "20"))
        max_buffer = int(os.getenv("BAUPASS_WEBSOCKET_MAX_HTTP_BUFFER", "1000000"))
        debug_logs = os.getenv("BAUPASS_WEBSOCKET_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
        socketio = SocketIO(
            flask_app,
            cors_allowed_origins=cors,
            async_mode="threading",
            logger=debug_logs,
            engineio_logger=debug_logs,
            ping_interval=max(10, ping_interval),
            ping_timeout=max(10, ping_timeout),
            max_http_buffer_size=max(100000, max_buffer),
            http_compression=False,
            manage_ack=True,
        )

        @socketio.on("connect")
        def on_connect():
            try:
                logger.debug("WebSocket client connected: %s", flask_request.remote_addr)
                emit("connected", {"ok": True})
            except Exception as exc:
                logger.error("Connect handler error: %s", exc)

        def _session_company_id(data) -> tuple[str | None, str | None]:
            """Return (company_id, error) after optional session validation."""
            require_session = os.getenv("BAUPASS_WEBSOCKET_REQUIRE_SESSION", "1").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            token = str((data or {}).get("session_token", "")).strip()
            if not token:
                token = (flask_request.cookies.get("baupass_session") or "").strip()
            if not token:
                auth = (flask_request.headers.get("Authorization") or "").strip()
                if auth.lower().startswith("bearer "):
                    token = auth[7:].strip()
            if require_session and not token:
                return None, "session_required"
            if not token:
                return str((data or {}).get("company_id", "")).strip() or None, None
            try:
                from backend.server import get_db, now_iso

                row = get_db().execute(
                    """
                    SELECT u.company_id
                    FROM sessions s
                    JOIN users u ON u.id = s.user_id
                    WHERE s.token = ? AND s.expires_at >= ?
                    LIMIT 1
                    """,
                    (token, now_iso()),
                ).fetchone()
                if not row:
                    return None, "invalid_session"
                return str(row["company_id"] or ""), None
            except Exception:
                return None, "session_check_failed"

        @socketio.on("subscribe")
        def on_subscribe(data):
            try:
                company_id, session_error = _session_company_id(data)
                if session_error:
                    logger.warning("Subscribe session error: %s", session_error)
                    emit("subscribed", {"ok": False, "error": session_error})
                    return
                if not company_id:
                    company_id = str((data or {}).get("company_id", "")).strip()
                require_key = os.getenv("BAUPASS_WEBSOCKET_REQUIRE_SUBSCRIBE_KEY", "0").strip().lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
                provided_key = str((data or {}).get("subscribe_key", "")).strip()
                expected_key = os.getenv("BAUPASS_WEBSOCKET_SUBSCRIBE_KEY", "").strip()
                if require_key and (not expected_key or provided_key != expected_key):
                    logger.warning("Subscribe key validation failed")
                    emit("subscribed", {"ok": False, "error": "forbidden"})
                    return
                cid = str(company_id or "").strip()
                if cid and (len(cid) > 64 or not cid.replace("-", "").replace("_", "").isalnum()):
                    logger.warning("Invalid company_id format: %s", cid)
                    emit("subscribed", {"ok": False, "error": "invalid_company_id"})
                    return
                if cid:
                    join_room(f"company:{cid}")
                    logger.debug("Client subscribed to company:%s", cid)
                emit("subscribed", {"ok": True, "company_id": company_id})
            except Exception as exc:
                logger.error("Subscribe handler error: %s", exc)
                emit("subscribed", {"ok": False, "error": "internal_error"})

        @socketio.on("ping")
        def on_ping():
            try:
                emit("pong", {})
            except Exception as exc:
                logger.error("Ping handler error: %s", exc)

        flask_app.extensions["socketio"] = socketio
        _socketio_state.update(
            {
                "enabled": True,
                "supported": True,
                "reason": "ok",
                "cors": cors,
                "ping_interval": ping_interval,
                "ping_timeout": ping_timeout,
            }
        )
        logger.info("WebSocket (SocketIO) enabled")
        return socketio
    except ImportError:
        _socketio_state.update({"enabled": False, "supported": False, "reason": "flask_socketio_not_installed"})
        logger.warning("flask-socketio not installed — WebSocket disabled")
        return None
    except Exception as exc:
        _socketio_state.update({"enabled": False, "supported": False, "reason": f"initialization_error: {exc}"})
        logger.error("WebSocket initialization failed: %s", exc)
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
    status = dict(_socketio_state)
    status["supported"] = bool(status.get("supported"))
    status["transport"] = _serve_engine()
    return status
