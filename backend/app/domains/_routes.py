"""Shared helpers for domain blueprints."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from flask import Blueprint, Flask

_ROUTES_MOUNTED: set[str] = set()


def routes_already_mounted(key: str) -> bool:
    return key in _ROUTES_MOUNTED


def clear_routes_mounted(key: str) -> None:
    _ROUTES_MOUNTED.discard(key)


def mark_routes_mounted(key: str) -> None:
    _ROUTES_MOUNTED.add(key)


def mount_rules(
    blueprint: Blueprint,
    rules: Sequence[tuple[str, Callable[..., Any], Sequence[str]]],
) -> None:
    """Register multiple URL rules on a blueprint."""
    for path, view_func, methods in rules:
        blueprint.add_url_rule(path, view_func=view_func, methods=list(methods))


def mount_rules_once(
    key: str,
    blueprint: Blueprint,
    rules: Sequence[tuple[str, Callable[..., Any], Sequence[str]]],
) -> None:
    if routes_already_mounted(key):
        return
    mount_rules(blueprint, rules)
    mark_routes_mounted(key)


def register_blueprint_once(
    flask_app: Flask,
    blueprint: Blueprint,
    *,
    url_prefix: str | None = None,
) -> bool:
    """Register blueprint on app only once (safe if registrar runs twice)."""
    ext_key = f"bp_registered:{blueprint.name}"
    if ext_key in flask_app.extensions or blueprint.name in flask_app.blueprints:
        flask_app.extensions[ext_key] = True
        return False
    if url_prefix:
        flask_app.register_blueprint(blueprint, url_prefix=url_prefix)
    else:
        flask_app.register_blueprint(blueprint)
    flask_app.extensions[ext_key] = True
    return True
