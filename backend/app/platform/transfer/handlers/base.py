"""Shared contracts for transfer domain handlers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class MergeMode(str, Enum):
    """How to treat rows that already exist with different content."""

    SKIP = "skip"  # keep existing, report conflict
    REPLACE = "replace"  # overwrite existing
    FAIL = "fail"  # abort apply on first content conflict


ProgressCb = Callable[[str, int, str], None]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def g(row: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return default


def row_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    if hasattr(row, "keys"):
        return {k: row[k] for k in row.keys()}
    return {}


def docs_root() -> Path:
    try:
        from backend.server import DOCS_UPLOAD_DIR

        return Path(DOCS_UPLOAD_DIR)
    except Exception:
        return Path("uploads") / "documents"


def contracts_root() -> Path:
    try:
        from backend.server import BASE_DIR

        root = Path(BASE_DIR) / "uploads" / "contracts"
    except Exception:
        root = Path("uploads") / "contracts"
    root.mkdir(parents=True, exist_ok=True)
    return root


def photos_look_like_data_url(value: str) -> bool:
    return bool(value) and str(value).strip().lower().startswith("data:")


@dataclass
class ApplyContext:
    db: Any
    company_id: str
    actor_user_id: str = ""
    dry_run: bool = False
    merge_mode: MergeMode = MergeMode.SKIP
    package_files: dict[str, bytes] = field(default_factory=dict)
    written_files: dict[str, str] = field(default_factory=dict)
    progress: ProgressCb | None = None

    def report(self, domain: str, percent: int, message: str = "") -> None:
        if self.progress:
            self.progress(domain, percent, message)


@dataclass
class DomainResult:
    domain: str
    accepted: int = 0
    unchanged: int = 0
    conflicts: int = 0
    skipped_invalid: int = 0
    conflict_ids: list[str] = field(default_factory=list)
    error: str | None = None

    def as_summary(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "unchanged": self.unchanged,
            "conflicts": self.conflicts,
            "skippedInvalid": self.skipped_invalid,
            "conflictIds": self.conflict_ids[:50],
            "error": self.error,
        }


def decide_row_action(
    *,
    exists: bool,
    same: bool,
    merge_mode: MergeMode,
) -> str:
    """Return insert | skip | replace | unchanged | fail."""
    if not exists:
        return "insert"
    if same:
        return "unchanged"
    if merge_mode == MergeMode.FAIL:
        return "fail"
    if merge_mode == MergeMode.REPLACE:
        return "replace"
    return "skip"


def fetch_by_id(db, table: str, row_id: str) -> dict[str, Any] | None:
    try:
        row = db.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    except Exception:
        return None
    return row_dict(row) if row else None


def values_equal(a: Any, b: Any) -> bool:
    if a is None and (b is None or b == ""):
        return True
    if b is None and (a is None or a == ""):
        return True
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a or 0) - float(b or 0)) < 1e-6
        except Exception:
            return str(a) == str(b)
    return str(a if a is not None else "") == str(b if b is not None else "")


def fingerprint_match(existing: dict[str, Any], incoming: dict[str, Any], fields: list[tuple[str, ...]]) -> bool:
    """fields: list of key tuples — first existing key vs first matching incoming key via g()."""
    for keys in fields:
        ex_key = keys[0]
        if not values_equal(existing.get(ex_key), g(incoming, *keys, default=None)):
            return False
    return True
