"""Shared helpers for domain blueprints."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from flask import Blueprint


def mount_rules(
    blueprint: Blueprint,
    rules: Sequence[tuple[str, Callable[..., Any], Sequence[str]]],
) -> None:
    """Register multiple URL rules on a blueprint."""
    for path, view_func, methods in rules:
        blueprint.add_url_rule(path, view_func=view_func, methods=list(methods))
