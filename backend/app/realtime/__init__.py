"""
SUPPIX Realtime Communication Module
====================================

WebSocket (Socket.IO) integration für Echtzeit-Kommunikation zwischen
Server, Dashboard und Mobile Clients.
"""

from .socketio_integration import init_websocket, supplix_ws

__all__ = ["init_websocket", "supplix_ws"]
