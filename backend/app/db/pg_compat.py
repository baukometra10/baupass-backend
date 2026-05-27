"""
SQLite → PostgreSQL SQL compatibility helpers for legacy queries in server.py.
"""
from __future__ import annotations

import re


_RE_INSERT_OR_IGNORE = re.compile(
    r"INSERT\s+OR\s+IGNORE\s+INTO",
    re.IGNORECASE,
)
_RE_INSERT_OR_REPLACE = re.compile(
    r"INSERT\s+OR\s+REPLACE\s+INTO",
    re.IGNORECASE,
)
_RE_DATETIME_NOW = re.compile(
    r"datetime\s*\(\s*['\"]now['\"]\s*\)",
    re.IGNORECASE,
)
_RE_STRFTIME_NOW = re.compile(
    r"strftime\s*\(\s*'%Y-%m-%dT%H:%M:%fZ'\s*,\s*'now'\s*\)",
    re.IGNORECASE,
)


def is_pragma(sql: str) -> bool:
    return sql.strip().upper().startswith("PRAGMA")


def adapt_sql(sql: str) -> str:
    """Best-effort SQL dialect tweaks for PostgreSQL."""
    text = sql.strip()
    if is_pragma(text):
        return "SELECT 1"
    out = text
    out = _RE_INSERT_OR_IGNORE.sub("INSERT INTO", out)
    out = _RE_INSERT_OR_REPLACE.sub("INSERT INTO", out)
    out = _RE_DATETIME_NOW.sub("CURRENT_TIMESTAMP", out)
    out = _RE_STRFTIME_NOW.sub("to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US') || 'Z'", out)
    if "?" in out and "%s" not in out:
        out = out.replace("?", "%s")
    return out
