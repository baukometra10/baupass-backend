"""
Server-Sent Events (SSE) for live workforce / access updates.
"""
from __future__ import annotations

import json
import time
from typing import Generator

from flask import Blueprint, Flask, Response, g, jsonify, request, stream_with_context

realtime_bp = Blueprint("platform_realtime", __name__)


def _resolve_company_id() -> str | None:
    user = getattr(g, "current_user", None) or {}
    cid = str(user.get("company_id") or "").strip()
    if cid:
        return cid
    raw = str(request.args.get("company_id", "") or "").strip()
    return raw or None


def register_realtime_blueprint(flask_app: Flask) -> None:
    from backend.server import require_auth, require_roles

    @realtime_bp.get("/v1/stream/events")
    @require_auth
    def stream_events():
        company_id = _resolve_company_id()
        last_id = request.args.get("last_id", "").strip() or None

        @stream_with_context
        def generate() -> Generator[str, None, None]:
            from backend.app.platform.events.bus import list_recent_events

            cursor = last_id
            yield "event: connected\ndata: {}\n\n"
            idle_ticks = 0
            while idle_ticks < 120:
                events = list_recent_events(company_id, limit=25, since_id=cursor)
                for evt in events:
                    cursor = evt["id"]
                    yield f"event: {evt['type']}\ndata: {json.dumps(evt, ensure_ascii=False)}\n\n"
                    idle_ticks = 0
                if not events:
                    idle_ticks += 1
                    yield ": keepalive\n\n"
                time.sleep(2)

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @realtime_bp.get("/v1/events/recent")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def recent_events():
        from backend.app.platform.events.bus import list_recent_events

        company_id = _resolve_company_id()
        if g.current_user.get("role") != "superadmin":
            company_id = str(g.current_user.get("company_id") or "").strip() or None
        limit = min(200, max(1, int(request.args.get("limit", "50"))))
        since_id = request.args.get("since_id", "").strip() or None
        return {"events": list_recent_events(company_id, limit=limit, since_id=since_id)}

    @realtime_bp.get("/v1/realtime/status")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def realtime_status():
        from backend.app.platform.realtime.websocket import websocket_status

        return jsonify({"websocket": websocket_status()})

    flask_app.register_blueprint(realtime_bp, url_prefix="/api")
