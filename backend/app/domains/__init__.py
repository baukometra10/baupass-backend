"""
SUPPIX bounded contexts (Clean Architecture domains).

Each package exposes ``register_*_blueprint(app)``.
Registration order is defined in ``registry.py`` (HTTP/static last).
"""
from __future__ import annotations

import logging

from flask import Flask

from .registry import DOMAIN_REGISTRARS

logger = logging.getLogger("baupass.domains")


def _is_blueprint_setup_error(exc: Exception) -> bool:
    text = str(exc)
    return "The setup method" in text and "can no longer be called on the blueprint" in text


def register_domain_blueprints(flask_app: Flask) -> None:
    """Register all domain blueprints in canonical order."""
    results: list[dict[str, str]] = []
    for entry in DOMAIN_REGISTRARS:
        try:
            mod = __import__(entry.module, fromlist=[entry.registrar])
            getattr(mod, entry.registrar)(flask_app)
            results.append({"name": entry.name, "status": "ok", "category": entry.category})
        except Exception as exc:
            if _is_blueprint_setup_error(exc):
                logger.warning("Domain blueprint already mounted: %s", entry.name)
                print(f"[baupass] domain/{entry.name} already mounted; skipped", flush=True)
            else:
                logger.exception("Domain blueprint failed: %s", entry.name)
                print(f"[baupass] WARNING: domain/{entry.name} skipped: {exc}", flush=True)
            results.append(
                {
                    "name": entry.name,
                    "status": "error",
                    "category": entry.category,
                    "error": str(exc),
                }
            )

    failed = [item["name"] for item in results if item.get("status") != "ok"]
    if failed:
        print(
            f"[baupass] Domains: {len(results) - len(failed)}/{len(results)} registered; failed: {failed}",
            flush=True,
        )
    else:
        print(f"[baupass] Domains: all {len(results)} blueprints registered", flush=True)

    flask_app.extensions["domain_blueprints"] = results
