"""
Real-time Communication Package — WebSockets and streaming updates.

Provides:
- WebSocket server with namespaces and authentication
- Automatic reconnection and message queuing
- Broadcast and direct messaging
- Connection and session management
- Performance metrics and monitoring
"""

from .websocket_handler import (
    WebSocketHandler,
    WebSocketManager,
    WebSocketUser,
    WebSocketMetrics,
    get_websocket_handler,
)

__all__ = [
    "WebSocketHandler",
    "WebSocketManager",
    "WebSocketUser",
    "WebSocketMetrics",
    "get_websocket_handler",
]
