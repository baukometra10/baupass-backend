"""
WebSocket Server and Handlers — Real-time communication with namespaces, authentication, and metrics.

Provides bidirectional communication for:
- Live worker location updates
- Real-time chat/messaging
- Notifications and alerts
- Status changes and events
- Command distribution to mobile apps
"""

from __future__ import annotations

import json
import time
import threading
import logging
from typing import Any, Callable, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps

try:
    from flask import request
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

try:
    import socketio
    HAS_SOCKETIO = True
except ImportError:
    HAS_SOCKETIO = False


@dataclass
class WebSocketUser:
    """Authenticated user session in WebSocket connection."""

    user_id: str
    session_id: str
    company_id: str
    role: str  # supervisor, manager, admin, worker, etc.
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        """Check if connection is still active."""
        return (datetime.utcnow() - self.last_activity).total_seconds() < 120

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.utcnow()


@dataclass
class WebSocketMetrics:
    """Metrics for WebSocket connections and messages."""

    total_connections: int = 0
    active_connections: int = 0
    total_messages: int = 0
    messages_by_type: dict[str, int] = field(default_factory=dict)
    total_bytes_sent: int = 0
    total_bytes_received: int = 0
    errors: int = 0
    connection_timeouts: int = 0
    last_reset: datetime = field(default_factory=datetime.utcnow)

    def message_sent(self, msg_type: str, size: int) -> None:
        """Record outgoing message."""
        self.total_messages += 1
        self.total_bytes_sent += size
        self.messages_by_type[msg_type] = self.messages_by_type.get(msg_type, 0) + 1

    def message_received(self, msg_type: str, size: int) -> None:
        """Record incoming message."""
        self.total_messages += 1
        self.total_bytes_received += size
        self.messages_by_type[msg_type] = self.messages_by_type.get(msg_type, 0) + 1

    def get_summary(self) -> dict[str, Any]:
        """Get metrics summary."""
        uptime_seconds = (datetime.utcnow() - self.last_reset).total_seconds()
        return {
            "active_connections": self.active_connections,
            "total_connections": self.total_connections,
            "total_messages": self.total_messages,
            "avg_messages_per_second": self.total_messages / max(1, uptime_seconds),
            "total_mb_sent": round(self.total_bytes_sent / 1_000_000, 2),
            "total_mb_received": round(self.total_bytes_received / 1_000_000, 2),
            "errors": self.errors,
            "connection_timeouts": self.connection_timeouts,
            "uptime_seconds": int(uptime_seconds),
        }


class WebSocketManager:
    """Manages WebSocket connections, authentication, and message routing."""

    def __init__(self, max_sessions: int = 10000):
        self.max_sessions = max_sessions
        self.sessions: dict[str, WebSocketUser] = {}  # session_id → user
        self.user_sessions: dict[str, list[str]] = {}  # user_id → [session_ids]
        self.company_sessions: dict[str, list[str]] = {}  # company_id → [session_ids]
        self.role_sessions: dict[str, list[str]] = {}  # role → [session_ids]
        self.metrics = WebSocketMetrics()
        self._lock = threading.RLock()

    def add_session(
        self,
        session_id: str,
        user_id: str,
        company_id: str,
        role: str,
        metadata: dict[str, Any] | None = None,
    ) -> WebSocketUser:
        """Register new WebSocket connection."""
        with self._lock:
            if len(self.sessions) >= self.max_sessions:
                raise RuntimeError(f"Max sessions ({self.max_sessions}) reached")

            user = WebSocketUser(
                user_id=user_id,
                session_id=session_id,
                company_id=company_id,
                role=role,
                metadata=metadata or {},
            )

            self.sessions[session_id] = user
            self.user_sessions.setdefault(user_id, []).append(session_id)
            self.company_sessions.setdefault(company_id, []).append(session_id)
            self.role_sessions.setdefault(role, []).append(session_id)

            self.metrics.total_connections += 1
            self.metrics.active_connections = len(self.sessions)

            return user

    def remove_session(self, session_id: str) -> Optional[WebSocketUser]:
        """Unregister WebSocket connection."""
        with self._lock:
            if session_id not in self.sessions:
                return None

            user = self.sessions.pop(session_id)

            # Remove from indices
            if user.user_id in self.user_sessions:
                self.user_sessions[user.user_id] = [
                    s for s in self.user_sessions[user.user_id] if s != session_id
                ]
                if not self.user_sessions[user.user_id]:
                    del self.user_sessions[user.user_id]

            if user.company_id in self.company_sessions:
                self.company_sessions[user.company_id] = [
                    s for s in self.company_sessions[user.company_id] if s != session_id
                ]

            if user.role in self.role_sessions:
                self.role_sessions[user.role] = [
                    s for s in self.role_sessions[user.role] if s != session_id
                ]

            self.metrics.active_connections = len(self.sessions)
            return user

    def get_session(self, session_id: str) -> Optional[WebSocketUser]:
        """Get user session."""
        with self._lock:
            return self.sessions.get(session_id)

    def get_user_sessions(self, user_id: str) -> list[WebSocketUser]:
        """Get all sessions for a user."""
        with self._lock:
            session_ids = self.user_sessions.get(user_id, [])
            return [self.sessions[sid] for sid in session_ids if sid in self.sessions]

    def get_company_sessions(self, company_id: str) -> list[WebSocketUser]:
        """Get all sessions for a company."""
        with self._lock:
            session_ids = self.company_sessions.get(company_id, [])
            return [self.sessions[sid] for sid in session_ids if sid in self.sessions]

    def get_role_sessions(self, role: str) -> list[WebSocketUser]:
        """Get all sessions by role."""
        with self._lock:
            session_ids = self.role_sessions.get(role, [])
            return [self.sessions[sid] for sid in session_ids if sid in self.sessions]

    def get_active_sessions_for_company(self, company_id: str) -> list[WebSocketUser]:
        """Get active (recently active) sessions for a company."""
        with self._lock:
            sessions = self.get_company_sessions(company_id)
            return [s for s in sessions if s.is_active]

    def touch_session(self, session_id: str) -> None:
        """Update session activity timestamp."""
        with self._lock:
            if session_id in self.sessions:
                self.sessions[session_id].touch()

    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics."""
        with self._lock:
            return self.metrics.get_summary()

    def reset_metrics(self) -> None:
        """Reset metrics."""
        with self._lock:
            self.metrics = WebSocketMetrics()


class WebSocketHandler:
    """WebSocket event handler with namespace support and authentication."""

    def __init__(self, sio: socketio.Server | None = None, logger: logging.Logger | None = None):
        if HAS_SOCKETIO:
            self.sio = sio or socketio.Server(
                async_mode="threading",
                cors_allowed_origins="*",
                ping_timeout=120,
                ping_interval=25,
            )
        else:
            raise ImportError("python-socketio not installed. Install with: pip install python-socketio")

        self.manager = WebSocketManager()
        self.logger = logger or logging.getLogger(__name__)
        self.message_handlers: dict[str, list[Callable]] = {}
        self._setup_default_events()

    def _setup_default_events(self) -> None:
        """Setup default event handlers."""

        @self.sio.event
        def connect(sid: str, environ: dict, auth: dict | None = None) -> bool:
            """Handle client connection."""
            try:
                if not auth or "user_id" not in auth:
                    self.logger.warning(f"Connection attempt without auth: {sid}")
                    return False

                user_id = auth.get("user_id", "")
                company_id = auth.get("company_id", "")
                role = auth.get("role", "user")

                user = self.manager.add_session(
                    session_id=sid,
                    user_id=user_id,
                    company_id=company_id,
                    role=role,
                    metadata=auth.get("metadata", {}),
                )

                self.logger.info(f"User {user_id} connected: {sid}")
                self.sio.emit("connection_confirmed", {"session_id": sid}, to=sid)
                return True

            except Exception as e:
                self.logger.error(f"Connection error: {e}")
                return False

        @self.sio.event
        def disconnect(sid: str) -> None:
            """Handle client disconnection."""
            user = self.manager.remove_session(sid)
            if user:
                self.logger.info(f"User {user.user_id} disconnected: {sid}")

        @self.sio.event
        def message(sid: str, data: dict[str, Any]) -> None:
            """Handle incoming message."""
            try:
                self.manager.touch_session(sid)
                msg_type = data.get("type", "unknown")

                # Record metrics
                msg_json = json.dumps(data)
                self.manager.metrics.message_received(msg_type, len(msg_json.encode()))

                # Call registered handlers
                if msg_type in self.message_handlers:
                    for handler in self.message_handlers[msg_type]:
                        try:
                            handler(sid, data)
                        except Exception as e:
                            self.logger.error(f"Handler error for {msg_type}: {e}")

            except Exception as e:
                self.logger.error(f"Message error: {e}")
                self.manager.metrics.errors += 1

    def register_message_handler(self, msg_type: str, handler: Callable) -> None:
        """Register handler for message type."""
        if msg_type not in self.message_handlers:
            self.message_handlers[msg_type] = []
        self.message_handlers[msg_type].append(handler)

    def emit_to_user(self, user_id: str, event: str, data: dict[str, Any]) -> int:
        """Emit event to all sessions of a user."""
        sessions = self.manager.get_user_sessions(user_id)
        count = 0
        for session in sessions:
            try:
                self.sio.emit(event, data, to=session.session_id)
                msg_json = json.dumps(data)
                self.manager.metrics.message_sent(event, len(msg_json.encode()))
                count += 1
            except Exception as e:
                self.logger.error(f"Emit error to {session.session_id}: {e}")
        return count

    def emit_to_company(self, company_id: str, event: str, data: dict[str, Any]) -> int:
        """Broadcast event to all users in a company."""
        sessions = self.manager.get_active_sessions_for_company(company_id)
        count = 0
        for session in sessions:
            try:
                self.sio.emit(event, data, to=session.session_id)
                msg_json = json.dumps(data)
                self.manager.metrics.message_sent(event, len(msg_json.encode()))
                count += 1
            except Exception as e:
                self.logger.error(f"Emit error to {session.session_id}: {e}")
        return count

    def emit_to_role(self, role: str, event: str, data: dict[str, Any]) -> int:
        """Broadcast event to all users with a specific role."""
        sessions = self.manager.get_role_sessions(role)
        count = 0
        for session in sessions:
            try:
                self.sio.emit(event, data, to=session.session_id)
                msg_json = json.dumps(data)
                self.manager.metrics.message_sent(event, len(msg_json.encode()))
                count += 1
            except Exception as e:
                self.logger.error(f"Emit error to {session.session_id}: {e}")
        return count

    def emit_to_company_role(
        self, company_id: str, role: str, event: str, data: dict[str, Any]
    ) -> int:
        """Broadcast event to users with specific role in a company."""
        company_sessions = self.manager.get_company_sessions(company_id)
        role_sessions = {s.session_id for s in self.manager.get_role_sessions(role)}

        count = 0
        for session in company_sessions:
            if session.session_id in role_sessions:
                try:
                    self.sio.emit(event, data, to=session.session_id)
                    msg_json = json.dumps(data)
                    self.manager.metrics.message_sent(event, len(msg_json.encode()))
                    count += 1
                except Exception as e:
                    self.logger.error(f"Emit error to {session.session_id}: {e}")
        return count

    def get_metrics(self) -> dict[str, Any]:
        """Get WebSocket metrics."""
        return self.manager.get_metrics()


# Global WebSocket handler instance
_ws_handler: WebSocketHandler | None = None
_ws_lock = threading.Lock()


def get_websocket_handler() -> WebSocketHandler:
    """Get or create global WebSocket handler."""
    global _ws_handler
    if _ws_handler is None:
        with _ws_lock:
            if _ws_handler is None:
                _ws_handler = WebSocketHandler()
    return _ws_handler
