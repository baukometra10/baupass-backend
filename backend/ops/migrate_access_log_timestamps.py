"""Normalize access_logs.timestamp to naive Europe/Berlin wall-clock ISO.

Canonical form: YYYY-MM-DDTHH:MM:SS (no Z, second precision).

Usage:
  python -m backend.ops.migrate_access_log_timestamps --dry-run
  python -m backend.ops.migrate_access_log_timestamps --apply
  python -m backend.ops.migrate_access_log_timestamps --apply --db-path /data/baupass.db
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = BASE_DIR / "backend" / "baupass.db"

# Ensure repo root imports work when run as a module.
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.platform.physical_operations._common import (  # noqa: E402
    ACCESS_WALL_TZ_IS_IANA,
    normalize_access_timestamp_value,
)


def resolve_db_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env_path = (os.getenv("BAUPASS_DB_PATH") or "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    return DEFAULT_DB_PATH.resolve()


def classify_row(raw: str) -> tuple[str, str]:
    """Return (status, canonical) where status is converted|already|unparseable|empty."""
    text = str(raw or "").strip()
    if not text:
        return "empty", ""
    canonical = normalize_access_timestamp_value(text)
    if not canonical:
        return "unparseable", ""
    if canonical == text:
        return "already", canonical
    # Naive with microseconds / space separator still counts as converted.
    return "converted", canonical


def migrate(db_path: Path, *, apply: bool, limit_sample: int, allow_fixed_offset: bool) -> dict[str, Any]:
    if not ACCESS_WALL_TZ_IS_IANA and not allow_fixed_offset:
        return {
            "ok": False,
            "error": "access_wall_tz_not_iana",
            "detail": (
                "Europe/Berlin ZoneInfo unavailable (fixed +02:00 fallback). "
                "Run on Linux/prod with tzdata, or pass --allow-fixed-offset for dry-run only."
            ),
            "dryRun": not apply,
        }
    if not db_path.exists():
        return {"ok": False, "error": "db_not_found", "dbPath": str(db_path), "dryRun": not apply}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT id, timestamp FROM access_logs").fetchall()
    except sqlite3.Error as exc:
        conn.close()
        return {"ok": False, "error": "query_failed", "detail": str(exc), "dbPath": str(db_path)}

    total = len(rows)
    converted = 0
    already = 0
    unparseable = 0
    empty = 0
    changes: list[tuple[str, str, str]] = []
    sample: list[dict[str, str]] = []

    for row in rows:
        row_id = str(row["id"])
        before = str(row["timestamp"] or "")
        status, after = classify_row(before)
        if status == "converted":
            converted += 1
            changes.append((row_id, before, after))
            if len(sample) < limit_sample:
                sample.append({"id": row_id, "before": before, "after": after})
        elif status == "already":
            already += 1
        elif status == "empty":
            empty += 1
        else:
            unparseable += 1
            if len(sample) < limit_sample:
                sample.append({"id": row_id, "before": before, "after": "", "status": "unparseable"})

    changed = 0
    if apply and changes:
        try:
            conn.execute("BEGIN")
            conn.executemany(
                "UPDATE access_logs SET timestamp = ? WHERE id = ?",
                [(after, row_id) for row_id, _before, after in changes],
            )
            conn.commit()
            changed = len(changes)
        except sqlite3.Error as exc:
            conn.rollback()
            conn.close()
            return {
                "ok": False,
                "error": "update_failed",
                "detail": str(exc),
                "dbPath": str(db_path),
                "wouldChange": len(changes),
            }

    conn.close()
    return {
        "ok": True,
        "action": "apply" if apply else "dry-run",
        "dryRun": not apply,
        "dbPath": str(db_path),
        "tzIana": ACCESS_WALL_TZ_IS_IANA,
        "total": total,
        "converted": converted,
        "alreadyCanonical": already,
        "unparseable": unparseable,
        "empty": empty,
        "changed": changed if apply else 0,
        "wouldChange": converted,
        "sample": sample,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize access_logs timestamps to naive Berlin ISO")
    parser.add_argument("--db-path", default="", help="SQLite path (default BAUPASS_DB_PATH or backend/baupass.db)")
    parser.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Explicit dry-run (default)")
    parser.add_argument("--limit-sample", type=int, default=20, help="Sample before/after rows in output")
    parser.add_argument(
        "--allow-fixed-offset",
        action="store_true",
        help="Allow run when ZoneInfo Europe/Berlin is unavailable (not for production apply)",
    )
    args = parser.parse_args(argv)

    apply = bool(args.apply) and not bool(args.dry_run)
    if apply and not ACCESS_WALL_TZ_IS_IANA and not args.allow_fixed_offset:
        payload = {
            "ok": False,
            "error": "refuse_apply_without_iana",
            "detail": "Refusing --apply without IANA Europe/Berlin. Use Linux/prod or --allow-fixed-offset.",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    if apply:
        print(
            json.dumps(
                {
                    "reminder": "Take a DB backup first: python -m backend.ops.db_backup backup",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )

    result = migrate(
        resolve_db_path(args.db_path or None),
        apply=apply,
        limit_sample=max(0, int(args.limit_sample or 0)),
        allow_fixed_offset=bool(args.allow_fixed_offset) or not apply,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
