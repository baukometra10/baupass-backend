"""In-memory ring buffer of recent Platform Guardian checks."""
from __future__ import annotations

from typing import Any

_MAX_ENTRIES = 20
_history: list[dict[str, Any]] = []


def append_history(snapshot: dict[str, Any]) -> None:
    remediation = snapshot.get("remediation") or {}
    security = snapshot.get("security") or {}
    entry = {
        "timestamp": snapshot.get("timestamp"),
        "status": snapshot.get("status"),
        "durationMs": snapshot.get("durationMs"),
        "failedProbes": list(snapshot.get("failedProbes") or []),
        "appliedCount": remediation.get("appliedCount", 0),
        "securityElevated": bool(security.get("elevated")),
        "securitySeverity": security.get("severity"),
        "deadLetterTotal": snapshot.get("deadLetterTotal", 0),
    }
    _history.insert(0, entry)
    del _history[_MAX_ENTRIES:]


def get_history(limit: int = 20) -> list[dict[str, Any]]:
    limit = min(_MAX_ENTRIES, max(1, limit))
    return list(_history[:limit])


def reset_history_for_tests() -> None:
    _history.clear()
