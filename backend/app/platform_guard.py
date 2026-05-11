from __future__ import annotations

from typing import Any


def enforce_platform_guards(config: dict[str, Any]) -> None:
    """Hard fails on unsafe production runtime settings."""
    errors: list[str] = []

    database_url = str(config.get("DATABASE_URL", "")).strip()
    allow_sqlite = bool(config.get("BAUPASS_ALLOW_SQLITE_PRODUCTION", False))
    if not database_url and not allow_sqlite:
        errors.append("Production must run with PostgreSQL DATABASE_URL")

    if not bool(config.get("SESSION_COOKIE_SECURE", False)):
        errors.append("SESSION_COOKIE_SECURE must be enabled")

    if not bool(config.get("SESSION_COOKIE_HTTPONLY", False)):
        errors.append("SESSION_COOKIE_HTTPONLY must be enabled")

    if str(config.get("SESSION_COOKIE_SAMESITE", "")).lower() not in {"lax", "strict"}:
        errors.append("SESSION_COOKIE_SAMESITE must be Lax or Strict")

    if not bool(config.get("ENFORCE_HTTPS", False)):
        errors.append("HTTPS enforcement must be enabled")

    if errors:
        msg = "\n".join(f"  - {e}" for e in errors)
        raise RuntimeError(f"[BauPass] Production platform guard failed:\n{msg}")
