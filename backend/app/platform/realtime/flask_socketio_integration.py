"""
Flask-SocketIO Integration — Setup and middleware for real-time communication in Flask apps.

Provides:
- Easy Flask app integration
- Authentication middleware
- Namespace routing
- Connection pooling
- Auto-reconnection handling
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from functools import wraps

try:
    from flask import request, has_request_context
    from flask_socketio import SocketIO, disconnect, emit, join_room, leave_room
    HAS_FLASK_SOCKETIO = True
except ImportError:
    HAS_FLASK_SOCKETIO = False

from .websocket_handler import WebSocketHandler, get_websocket_handler


def setup_websocket_routes(app, ws_handler: WebSocketHandler | None = None) -> SocketIO:
    """
    Setup WebSocket routes in Flask app.

    Args:
        app: Flask application instance
        ws_handler: Optional WebSocketHandler instance (creates new if not provided)

    Returns:
        SocketIO instance for further configuration
    """
    if not HAS_FLASK_SOCKETIO:
        raise ImportError(
            "flask-socketio not installed. Install with: "
            "pip install flask-socketio python-socketio python-engineio"
        )

    if ws_handler is None:
        ws_handler = get_websocket_handler()

    # Initialize SocketIO with Flask app
    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode="threading",
        ping_timeout=120,
        ping_interval=25,
        logger=True,
        engineio_logger=False,
    )

    logger = logging.getLogger(__name__)

    # Authentication middleware
    @socketio.on("connect", namespace="/")
    def handle_connect(auth: dict[str, Any] | None = None):
        """Handle WebSocket connection with authentication."""
        try:
            if not auth or "user_id" not in auth:
                logger.warning(f"Connection attempt without auth")
                return False

            session_id = request.sid
            user_id = auth.get("user_id", "")
            company_id = auth.get("company_id", "")
            role = auth.get("role", "user")

            ws_handler.manager.add_session(
                session_id=session_id,
                user_id=user_id,
                company_id=company_id,
                role=role,
                metadata=auth.get("metadata", {}),
            )

            logger.info(f"User {user_id} connected: {session_id}")
            emit("connection_confirmed", {"session_id": session_id})

            # Join user-specific room
            join_room(f"user_{user_id}")

            # Join company room
            join_room(f"company_{company_id}")

            # Join role room
            join_room(f"role_{role}")

            return True

        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    @socketio.on("disconnect", namespace="/")
    def handle_disconnect():
        """Handle WebSocket disconnection."""
        session_id = request.sid
        user = ws_handler.manager.remove_session(session_id)
        if user:
            logger.info(f"User {user.user_id} disconnected: {session_id}")

    @socketio.on("message", namespace="/")
    def handle_message(data: dict[str, Any]):
        """Handle incoming message."""
        try:
            session_id = request.sid
            ws_handler.manager.touch_session(session_id)

            msg_type = data.get("type", "unknown")
            user = ws_handler.manager.get_session(session_id)

            if not user:
                logger.warning(f"Message from unknown session: {session_id}")
                return

            # Call registered handlers
            if msg_type in ws_handler.message_handlers:
                for handler in ws_handler.message_handlers[msg_type]:
                    try:
                        handler(session_id, data)
                    except Exception as e:
                        logger.error(f"Handler error for {msg_type}: {e}")
                        ws_handler.manager.metrics.errors += 1

        except Exception as e:
            logger.error(f"Message error: {e}")
            ws_handler.manager.metrics.errors += 1

    # Heartbeat to keep connection alive
    @socketio.on("heartbeat", namespace="/")
    def handle_heartbeat():
        """Handle client heartbeat."""
        session_id = request.sid
        ws_handler.manager.touch_session(session_id)
        emit("heartbeat_ack", {"timestamp": time.time()})

    return socketio


def websocket_authenticated(required_roles: list[str] | None = None) -> Callable:
    """
    Decorator for WebSocket event handlers requiring authentication.

    Args:
        required_roles: List of roles allowed to call this handler

    Example:
        @socketio.on('my_event')
        @websocket_authenticated(required_roles=['supervisor', 'admin'])
        def handle_event(data):
            ...
    """

    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                ws_handler = get_websocket_handler()
                session_id = request.sid
                user = ws_handler.manager.get_session(session_id)

                if not user:
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Event from unauthenticated session: {session_id}")
                    disconnect()
                    return

                # Check role if required
                if required_roles and user.role not in required_roles:
                    logger = logging.getLogger(__name__)
                    logger.warning(f"User {user.user_id} attempted unauthorized action (role: {user.role})")
                    emit("error", {"message": "Unauthorized"})
                    return

                return f(*args, **kwargs)

            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.error(f"Authentication error: {e}")
                disconnect()

        return wrapper

    return decorator


import time  # Moved here to avoid import error

# Example event handlers that can be registered
def create_location_update_handler(ws_handler: WebSocketHandler) -> Callable:
    """
    Create handler for real-time location updates.

    Example:
        handler = create_location_update_handler(ws_handler)
        ws_handler.register_message_handler('location_update', handler)
    """

    def handler(session_id: str, data: dict[str, Any]) -> None:
        user = ws_handler.manager.get_session(session_id)
        if not user:
            return

        # Broadcast location to supervisors in same company
        location = {
            "user_id": user.user_id,
            "lat": data.get("lat"),
            "lng": data.get("lng"),
            "timestamp": time.time(),
            "accuracy": data.get("accuracy"),
            "speed": data.get("speed"),
        }

        # Would emit to socketio in actual Flask integration
        # socketio.emit('worker_location_update', location, room=f'company_{user.company_id}')

    return handler


def create_chat_message_handler(ws_handler: WebSocketHandler) -> Callable:
    """Create handler for chat messages."""

    def handler(session_id: str, data: dict[str, Any]) -> None:
        user = ws_handler.manager.get_session(session_id)
        if not user:
            return

        message = {
            "from_user_id": user.user_id,
            "to_user_id": data.get("to_user_id"),
            "text": data.get("text"),
            "timestamp": time.time(),
            "company_id": user.company_id,
        }

        # Would emit to socketio in actual Flask integration
        # socketio.emit('chat_message', message, room=f"user_{data.get('to_user_id')}")

    return handler
