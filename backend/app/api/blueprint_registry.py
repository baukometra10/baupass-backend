"""
Register modular API blueprints on the legacy Flask app.

Each group is isolated: one failure must not block the rest or crash startup.
"""
from __future__ import annotations

import logging
import traceback
from typing import Any

from flask import Flask

logger = logging.getLogger("baupass.blueprints")


def _register_safe(flask_app: Flask, name: str, registrar) -> dict[str, Any]:
    try:
        registrar(flask_app)
        return {"name": name, "status": "ok"}
    except Exception as exc:
        logger.exception("Blueprint group failed: %s", name)
        traceback.print_exc()
        return {"name": name, "status": "error", "error": str(exc)}


def register_modular_blueprints(flask_app: Flask) -> None:
    results: list[dict[str, Any]] = []

    def _worker_app(app: Flask) -> None:
        from backend.app.api.worker_app_routes import register_worker_app_blueprint

        register_worker_app_blueprint(app)

    def _domains(app: Flask) -> None:
        from backend.app.domains import register_domain_blueprints

        register_domain_blueprints(app)

    def _platform(app: Flask) -> None:
        from backend.app.platform import register_platform_blueprints

        register_platform_blueprints(app)

    def _shift(app: Flask) -> None:
        from backend.app.api.shift_routes import register_shift_blueprint

        register_shift_blueprint(app)

    for name, fn in (
        ("worker_app", _worker_app),
        ("shift", _shift),
        ("domains", _domains),
        ("platform", _platform),
    ):
        results.append(_register_safe(flask_app, name, fn))

    flask_app.extensions["modular_blueprints"] = results
    failed = [r for r in results if r.get("status") != "ok"]
    if failed:
        print(
            f"[baupass] WARNING: {len(failed)} blueprint group(s) failed — core API still runs",
            flush=True,
        )
    else:
        print("[baupass] Modular blueprints: all groups registered", flush=True)
