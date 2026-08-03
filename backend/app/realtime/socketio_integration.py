"""
Flask Socket.IO Integration for SUPPIX WebSocket Architecture
==============================================================

Integriert Socket.IO mit der bestehenden Flask App für bidirektionale
Echtzeit-Kommunikation zwischen Server, Web-Dashboard und Mobile-Clients.
"""

from flask import Flask, request, g
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect
import logging
from typing import Optional, Callable, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class SupplixWebSocketServer:
    """Wrapper for Socket.IO integration with SUPPIX platform."""

    def __init__(self, app: Optional[Flask] = None):
        self.app = app
        self.socketio = None
        self.event_handlers: Dict[str, list] = {}

    def init_app(self, app: Flask, message_queue: Optional[str] = None) -> None:
        """Initialize Socket.IO with Flask app."""
        self.app = app

        # Configure Socket.IO
        self.socketio = SocketIO(
            app,
            cors_allowed_origins="*" if app.config.get("DEBUG") else [
                app.config.get("PUBLIC_BASE_URL", "")
            ],
            message_queue=message_queue,  # Redis URL for scaling
            async_mode="threading",
            ping_timeout=10,
            ping_interval=5,
            logger=True if app.config.get("DEBUG") else False
        )

        self._register_handlers()
        logger.info("Socket.IO initialized for SUPPIX WebSocket")

    def _register_handlers(self) -> None:
        """Register Socket.IO event handlers."""
        if not self.socketio:
            return

        @self.socketio.on("connect")
        def handle_connect():
            """Handle client connection."""
            try:
                client_id = request.sid
                user_id = g.get("user_id")
                company_id = g.get("company_id")

                logger.info(f"Client connected: {client_id} (user={user_id})")

                # Join company room for broadcasting
                if company_id:
                    join_room(f"company_{company_id}")
                    emit("connection_status", {
                        "status": "connected",
                        "message": "Successfully connected to SUPPIX platform",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })

            except Exception as e:
                logger.error(f"Connection error: {e}")
                disconnect()

        @self.socketio.on("disconnect")
        def handle_disconnect():
            """Handle client disconnection."""
            client_id = request.sid
            logger.info(f"Client disconnected: {client_id}")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Point #1: Geospatial Real-time Updates
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        @self.socketio.on("location_update")
        def handle_location_update(data):
            """Handle real-time location update from worker."""
            try:
                worker_id = data.get("worker_id")
                latitude = float(data.get("latitude"))
                longitude = float(data.get("longitude"))
                company_id = g.get("company_id")

                logger.debug(f"Location update: {worker_id} @ ({latitude}, {longitude})")

                # Broadcast to company supervisors
                self.broadcast_to_company(
                    company_id,
                    "worker_location_update",
                    {
                        "worker_id": worker_id,
                        "latitude": latitude,
                        "longitude": longitude,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )

                # Send ACK
                emit("location_update_ack", {"worker_id": worker_id, "status": "received"})

            except Exception as e:
                logger.error(f"Location update error: {e}")
                emit("error", {"message": str(e)})

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Point #2: Battery & Motion Status
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        @self.socketio.on("battery_status")
        def handle_battery_status(data):
            """Handle battery status updates."""
            try:
                worker_id = data.get("worker_id")
                battery_level = float(data.get("battery_level"))
                motion_state = data.get("motion_state")
                company_id = g.get("company_id")

                logger.debug(f"Battery: {worker_id} @ {battery_level}% ({motion_state})")

                self.broadcast_to_company(
                    company_id,
                    "worker_battery_update",
                    {
                        "worker_id": worker_id,
                        "battery_level": battery_level,
                        "motion_state": motion_state,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
            except Exception as e:
                logger.error(f"Battery status error: {e}")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Point #5: Edge AI Events
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        @self.socketio.on("edge_ai_event")
        def handle_edge_ai_event(data):
            """Handle edge AI detection events."""
            try:
                gate_id = data.get("gate_id")
                event_type = data.get("event_type")
                confidence = float(data.get("confidence", 0.0))
                company_id = g.get("company_id")

                logger.info(f"Edge AI: {gate_id} - {event_type} ({confidence:.2%})")

                self.broadcast_to_company(
                    company_id,
                    "edge_ai_detection",
                    {
                        "gate_id": gate_id,
                        "event_type": event_type,
                        "confidence": confidence,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
            except Exception as e:
                logger.error(f"Edge AI event error: {e}")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Offline Sync Status
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

        @self.socketio.on("sync_status")
        def handle_sync_status(data):
            """Handle offline sync status updates."""
            try:
                device_id = data.get("device_id")
                pending = int(data.get("pending", 0))
                synced = int(data.get("synced", 0))
                company_id = g.get("company_id")

                logger.debug(f"Sync: {device_id} - {pending} pending, {synced} synced")

                self.broadcast_to_company(
                    company_id,
                    "device_sync_status",
                    {
                        "device_id": device_id,
                        "pending": pending,
                        "synced": synced,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
            except Exception as e:
                logger.error(f"Sync status error: {e}")

    def broadcast_to_company(self, company_id: str, event: str, data: Dict[str, Any]) -> None:
        """Broadcast event to all users in company."""
        if not self.socketio:
            return

        try:
            room = f"company_{company_id}"
            self.socketio.emit(event, data, room=room)
        except Exception as e:
            logger.error(f"Broadcast error: {e}")

    def broadcast_to_user(self, user_id: str, event: str, data: Dict[str, Any]) -> None:
        """Broadcast event to specific user."""
        if not self.socketio:
            return

        try:
            room = f"user_{user_id}"
            self.socketio.emit(event, data, room=room)
        except Exception as e:
            logger.error(f"User broadcast error: {e}")


# Global instance
supplix_ws = SupplixWebSocketServer()


def init_websocket(app: Flask, redis_url: Optional[str] = None) -> SupplixWebSocketServer:
    """Initialize WebSocket for Flask app."""
    supplix_ws.init_app(app, message_queue=redis_url)
    return supplix_ws
