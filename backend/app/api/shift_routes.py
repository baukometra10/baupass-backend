"""
Shift & swap API — blueprint mounts legacy handlers from server.py.
"""
from __future__ import annotations

import sys

from flask import Blueprint

SHIFT_ROUTES: tuple[tuple[str, str, list[str]], ...] = (
    ("/shift/assignments", "shift_get_assignments", ["GET"]),
    ("/shift/assignments", "shift_create_assignment", ["POST"]),
    ("/shift/coworkers", "shift_coworkers", ["GET"]),
    ("/shift/coworker-assignments", "shift_coworker_assignments", ["GET"]),
    ("/shift/swaps", "shift_get_swaps", ["GET"]),
    ("/shift/propose-swap", "shift_propose_swap", ["POST"]),
    ("/shift/respond-swap/<swap_id>", "shift_respond_swap", ["POST"]),
    ("/foreman/shift-assignments", "foreman_shift_assignments", ["GET"]),
)


def _resolve_legacy_server_module():
    for name in ("backend.server", "__main__", "server"):
        mod = sys.modules.get(name)
        if mod is not None and callable(getattr(mod, "shift_get_assignments", None)):
            return mod
    raise RuntimeError("Legacy server module not loaded (shift_get_assignments missing)")


def register_shift_blueprint(flask_app) -> None:
    if "shift_api" in flask_app.blueprints:
        return
    legacy = _resolve_legacy_server_module()
    bp = Blueprint("shift_api", __name__)
    for path, handler_name, methods in SHIFT_ROUTES:
        view_func = getattr(legacy, handler_name)
        bp.add_url_rule(path, handler_name, view_func, methods=methods)
    flask_app.register_blueprint(bp, url_prefix="/api")
    print(f"[baupass] Shift blueprint registered ({len(SHIFT_ROUTES)} routes)", flush=True)
