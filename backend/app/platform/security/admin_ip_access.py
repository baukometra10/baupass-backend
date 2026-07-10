"""Superadmin IP whitelist policy — opt-in enforcement with env overrides."""
from __future__ import annotations

import ipaddress
import os
from typing import Any

from flask import Request

from backend.app.platform.security.client_ip import resolve_client_ip

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off"}


def _env_truthy(*keys: str) -> bool:
    for key in keys:
        if str(os.getenv(key, "")).strip().lower() in _TRUTHY:
            return True
    return False


def _env_optional_bool(*keys: str) -> bool | None:
    for key in keys:
        raw = str(os.getenv(key, "")).strip().lower()
        if raw in _TRUTHY:
            return True
        if raw in _FALSY:
            return False
    return None


def parse_ip_whitelist(raw: str | None) -> list[str]:
    return [item.strip() for item in (raw or "").replace(";", ",").split(",") if item.strip()]


def ip_allowed(ip_value: str, whitelist: list[str]) -> bool:
    if not whitelist:
        return True
    try:
        ip_obj = ipaddress.ip_address(ip_value)
    except ValueError:
        return False
    for rule in whitelist:
        try:
            if "/" in rule:
                if ip_obj in ipaddress.ip_network(rule, strict=False):
                    return True
            elif ip_obj == ipaddress.ip_address(rule):
                return True
        except ValueError:
            continue
    return False


def is_admin_ip_whitelist_disabled() -> bool:
    return _env_truthy("BAUPASS_ADMIN_IP_WHITELIST_DISABLED", "SUPPIX_ADMIN_IP_WHITELIST_DISABLED")


def get_admin_ip_whitelist_from_env() -> list[str] | None:
    for key in ("BAUPASS_ADMIN_IP_WHITELIST", "SUPPIX_ADMIN_IP_WHITELIST"):
        if key in os.environ:
            return parse_ip_whitelist(os.environ.get(key))
    return None


def _settings_row_keys(settings_row: Any) -> set[str]:
    if settings_row is None:
        return set()
    if hasattr(settings_row, "keys"):
        return set(settings_row.keys())
    return set()


def should_enforce_admin_ip(db, settings_row: Any | None = None) -> bool:
    if is_admin_ip_whitelist_disabled():
        return False

    env_enforce = _env_optional_bool("BAUPASS_ENFORCE_ADMIN_IP_WHITELIST", "SUPPIX_ENFORCE_ADMIN_IP_WHITELIST")
    if env_enforce is not None:
        return env_enforce

    if settings_row is None:
        settings_row = db.execute(
            "SELECT admin_ip_whitelist, enforce_admin_ip_whitelist FROM settings WHERE id = 1"
        ).fetchone()

    keys = _settings_row_keys(settings_row)
    if "enforce_admin_ip_whitelist" not in keys:
        return False
    return int(settings_row["enforce_admin_ip_whitelist"] or 0) == 1


def get_admin_ip_whitelist(db, settings_row: Any | None = None) -> list[str]:
    if is_admin_ip_whitelist_disabled():
        return []

    env_list = get_admin_ip_whitelist_from_env()
    if env_list is not None:
        return env_list

    if settings_row is None:
        settings_row = db.execute("SELECT admin_ip_whitelist FROM settings WHERE id = 1").fetchone()
    return parse_ip_whitelist(settings_row["admin_ip_whitelist"] if settings_row else "")


def check_superadmin_ip_access(db, req: Request | None = None) -> tuple[bool, str, dict[str, Any]]:
    client_ip = resolve_client_ip(req)
    if not should_enforce_admin_ip(db):
        return True, client_ip, {}

    whitelist = get_admin_ip_whitelist(db)
    if not whitelist:
        return True, client_ip, {}

    if ip_allowed(client_ip, whitelist):
        return True, client_ip, {}

    return False, client_ip, {
        "error": "admin_ip_not_allowed",
        "clientIp": client_ip,
        "enforced": True,
        "hint": "Aktuelle IP in Einstellungen übernehmen oder BAUPASS_ENFORCE_ADMIN_IP_WHITELIST=0 setzen.",
    }


def ensure_admin_ip_settings_schema(db) -> None:
    try:
        from backend.app.db.runtime import postgres_runtime_enabled

        if postgres_runtime_enabled():
            db.execute(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS enforce_admin_ip_whitelist INTEGER NOT NULL DEFAULT 0"
            )
            db.commit()
            return
    except Exception:
        pass

    try:
        columns = [row[1] for row in db.execute("PRAGMA table_info(settings)").fetchall()]
    except Exception:
        return
    if "enforce_admin_ip_whitelist" in columns:
        return
    try:
        db.execute(
            "ALTER TABLE settings ADD COLUMN enforce_admin_ip_whitelist INTEGER NOT NULL DEFAULT 0"
        )
        db.commit()
    except Exception:
        pass


def apply_startup_ip_policy(db) -> None:
    ensure_admin_ip_settings_schema(db)
    if not is_admin_ip_whitelist_disabled():
        return
    try:
        db.execute(
            """
            UPDATE settings
            SET admin_ip_whitelist = '', enforce_admin_ip_whitelist = 0
            WHERE id = 1
            """
        )
        db.commit()
    except Exception:
        pass


def clear_admin_ip_policy(db) -> None:
    ensure_admin_ip_settings_schema(db)
    db.execute(
        """
        UPDATE settings
        SET admin_ip_whitelist = '', enforce_admin_ip_whitelist = 0
        WHERE id = 1
        """
    )
    db.commit()
