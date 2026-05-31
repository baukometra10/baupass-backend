"""
BauPass bounded contexts (Clean Architecture domains).

Each package exposes ``register_*_blueprint(app)``.
Registration order is defined in ``registry.py`` (HTTP/static last).
"""
from __future__ import annotations

import logging

from flask import Flask

from .registry import DOMAIN_REGISTRARS

logger = logging.getLogger("baupass.domains")


def register_domain_blueprints(flask_app: Flask) -> None:
    """Register all domain blueprints in canonical order."""
    results: list[tuple[str, str]] = []
    for entry in DOMAIN_REGISTRARS:
        try:
            mod = __import__(entry.module, fromlist=[entry.registrar])
            getattr(mod, entry.registrar)(flask_app)
            results.append((entry.name, "ok"))
        except Exception as exc:
            logger.exception("Domain blueprint failed: %s", entry.name)
            print(f"[baupass] WARNING: domain/{entry.name} skipped: {exc}", flush=True)
            results.append((entry.name, f"error: {exc}"))

    failed = [name for name, status in results if status != "ok"]
    if failed:
        print(
            f"[baupass] Domains: {len(results) - len(failed)}/{len(results)} registered; failed: {failed}",
            flush=True,
        )
    else:
        print(f"[baupass] Domains: all {len(results)} blueprints registered", flush=True)

    flask_app.extensions["domain_blueprints"] = results
