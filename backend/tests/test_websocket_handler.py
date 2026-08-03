"""
Tests for WebSocket implementation — connection, messaging, broadcasting, and metrics.
"""

import time
import pytest
from unittest.mock import Mock, patch, MagicMock

from backend.app.platform.realtime.websocket_handler import (
    WebSocketUser,
    WebSocketMetrics,
    WebSocketManager,
    WebSocketHandler,
)


class TestWebSocketUser:
    """Test WebSocketUser session tracking."""

    def test_user_creation(self):
        """Test creating a WebSocket user."""
        user = WebSocketUser(
            user_id="user1",
            session_id="sess1",
            company_id="comp1",
            role="supervisor",
        )
        assert user.user_id == "user1"
        assert user.session_id == "sess1"
        assert user.company_id == "comp1"
        assert user.role == "supervisor"
        assert user.is_active

    def test_user_activity_timeout(self):
        """Test user becomes inactive after timeout."""
        user = WebSocketUser(
            user_id="user1",
            session_id="sess1",
            company_id="comp1",
            role="supervisor",
        )
        # Move timestamp back 3 minutes
        user.last_activity = user.last_activity.replace(year=user.last_activity.year - 1)
        assert not user.is_active

    def test_touch_updates_activity(self):
        """Test touch() updates last activity timestamp."""
        user = WebSocketUser(
            user_id="user1",
            session_id="sess1",
            company_id="comp1",
            role="supervisor",
        )
        old_time = user.last_activity
        time.sleep(0.01)
        user.touch()
        assert user.last_activity > old_time


class TestWebSocketMetrics:
    """Test metrics collection."""

    def test_message_tracking(self):
        """Test message metrics are recorded."""
        metrics = WebSocketMetrics()
        metrics.message_sent("location_update", 500)
        metrics.message_received("chat_message", 200)

        assert metrics.total_messages == 2
        assert metrics.total_bytes_sent == 500
        assert metrics.total_bytes_received == 200
        assert metrics.messages_by_type["location_update"] == 1
        assert metrics.messages_by_type["chat_message"] == 1

    def test_metrics_summary(self):
        """Test getting metrics summary."""
        metrics = WebSocketMetrics()
        metrics.total_connections = 10
        metrics.active_connections = 5
        metrics.message_sent("test", 100)

        summary = metrics.get_summary()
        assert summary["active_connections"] == 5
        assert summary["total_connections"] == 10
        assert summary["total_messages"] == 1


class TestWebSocketManager:
    """Test session management."""

    def test_add_session(self):
        """Test adding a session."""
        manager = WebSocketManager()
        user = manager.add_session(
            session_id="sess1",
            user_id="user1",
            company_id="comp1",
            role="supervisor",
        )

        assert user.user_id == "user1"
        assert manager.get_session("sess1") == user

    def test_session_indices(self):
        """Test sessions are indexed by user, company, and role."""
        manager = WebSocketManager()
        manager.add_session("sess1", "user1", "comp1", "supervisor")
        manager.add_session("sess2", "user2", "comp1", "supervisor")
        manager.add_session("sess3", "user3", "comp1", "worker")

        # User sessions
        user1_sessions = manager.get_user_sessions("user1")
        assert len(user1_sessions) == 1
        assert user1_sessions[0].session_id == "sess1"

        # Company sessions
        comp1_sessions = manager.get_company_sessions("comp1")
        assert len(comp1_sessions) == 3

        # Role sessions
        supervisor_sessions = manager.get_role_sessions("supervisor")
        assert len(supervisor_sessions) == 2

    def test_remove_session(self):
        """Test removing a session."""
        manager = WebSocketManager()
        manager.add_session("sess1", "user1", "comp1", "supervisor")

        user = manager.remove_session("sess1")
        assert user.user_id == "user1"
        assert manager.get_session("sess1") is None
        assert len(manager.get_user_sessions("user1")) == 0

    def test_get_active_sessions(self):
        """Test getting only active sessions."""
        manager = WebSocketManager()
        user1 = manager.add_session("sess1", "user1", "comp1", "supervisor")
        user2 = manager.add_session("sess2", "user2", "comp1", "supervisor")

        # Make user2 inactive
        user2.last_activity = user2.last_activity.replace(year=2000)

        active = manager.get_active_sessions_for_company("comp1")
        assert len(active) == 1
        assert active[0].user_id == "user1"

    def test_max_sessions_limit(self):
        """Test max sessions limit is enforced."""
        manager = WebSocketManager(max_sessions=2)
        manager.add_session("sess1", "user1", "comp1", "supervisor")
        manager.add_session("sess2", "user2", "comp1", "supervisor")

        with pytest.raises(RuntimeError):
            manager.add_session("sess3", "user3", "comp1", "supervisor")

    def test_metrics_update_on_add_remove(self):
        """Test metrics are updated when sessions are added/removed."""
        manager = WebSocketManager()
        assert manager.metrics.active_connections == 0

        manager.add_session("sess1", "user1", "comp1", "supervisor")
        assert manager.metrics.active_connections == 1
        assert manager.metrics.total_connections == 1

        manager.add_session("sess2", "user2", "comp1", "supervisor")
        assert manager.metrics.active_connections == 2

        manager.remove_session("sess1")
        assert manager.metrics.active_connections == 1


class TestWebSocketHandler:
    """Test WebSocket event handling and broadcasting."""

    def test_handler_creation(self):
        """Test creating WebSocket handler."""
        # Mock socketio since it requires specific async setup
        mock_sio = MagicMock()
        handler = WebSocketHandler(sio=mock_sio)

        assert handler.manager is not None
        assert handler.sio == mock_sio

    def test_emit_to_user(self):
        """Test emitting to specific user."""
        mock_sio = MagicMock()
        handler = WebSocketHandler(sio=mock_sio)

        # Add sessions
        handler.manager.add_session("sess1", "user1", "comp1", "supervisor")
        handler.manager.add_session("sess2", "user1", "comp1", "supervisor")

        # Emit to user
        count = handler.emit_to_user("user1", "test_event", {"data": "test"})

        assert count == 2
        assert mock_sio.emit.call_count == 2

    def test_emit_to_company(self):
        """Test broadcasting to company."""
        mock_sio = MagicMock()
        handler = WebSocketHandler(sio=mock_sio)

        # Add sessions from different companies
        handler.manager.add_session("sess1", "user1", "comp1", "supervisor")
        handler.manager.add_session("sess2", "user2", "comp1", "supervisor")
        handler.manager.add_session("sess3", "user3", "comp2", "supervisor")

        # Emit to company
        count = handler.emit_to_company("comp1", "test_event", {"data": "test"})

        assert count == 2
        assert mock_sio.emit.call_count == 2

    def test_emit_to_role(self):
        """Test broadcasting by role."""
        mock_sio = MagicMock()
        handler = WebSocketHandler(sio=mock_sio)

        # Add sessions with different roles
        handler.manager.add_session("sess1", "user1", "comp1", "supervisor")
        handler.manager.add_session("sess2", "user2", "comp1", "worker")
        handler.manager.add_session("sess3", "user3", "comp1", "supervisor")

        # Emit to role
        count = handler.emit_to_role("supervisor", "test_event", {"data": "test"})

        assert count == 2
        assert mock_sio.emit.call_count == 2

    def test_emit_to_company_role(self):
        """Test broadcasting to role within company."""
        mock_sio = MagicMock()
        handler = WebSocketHandler(sio=mock_sio)

        # Add sessions
        handler.manager.add_session("sess1", "user1", "comp1", "supervisor")
        handler.manager.add_session("sess2", "user2", "comp1", "worker")
        handler.manager.add_session("sess3", "user3", "comp2", "supervisor")

        # Emit to company + role
        count = handler.emit_to_company_role("comp1", "supervisor", "test_event", {"data": "test"})

        assert count == 1  # Only user1
        assert mock_sio.emit.call_count == 1

    def test_message_handler_registration(self):
        """Test registering message handlers."""
        mock_sio = MagicMock()
        handler = WebSocketHandler(sio=mock_sio)

        callback = MagicMock()
        handler.register_message_handler("test_type", callback)

        assert "test_type" in handler.message_handlers
        assert callback in handler.message_handlers["test_type"]

    def test_get_metrics(self):
        """Test getting handler metrics."""
        mock_sio = MagicMock()
        handler = WebSocketHandler(sio=mock_sio)

        handler.manager.add_session("sess1", "user1", "comp1", "supervisor")

        metrics = handler.get_metrics()
        assert metrics["active_connections"] == 1


class TestGlobalHandler:
    """Test global handler singleton."""

    def test_singleton_pattern(self):
        """Test get_websocket_handler returns same instance."""
        from backend.app.platform.realtime.websocket_handler import get_websocket_handler

        handler1 = get_websocket_handler()
        handler2 = get_websocket_handler()

        assert handler1 is handler2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
