"""SQLite integrity checks and auto-restore from /data/backups when the live DB is unusable."""
from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path


def sqlite_core_tables_ok(db_path: Path, *, timeout: float = 3.0) -> bool:
    """Return True when users (and settings) are readable — minimum for admin login."""
    try:
        if not db_path.is_file() or db_path.stat().st_size < 4096:
            return False
        with sqlite3.connect(str(db_path), timeout=timeout) as conn:
            conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
            conn.execute("SELECT 1 FROM settings LIMIT 1").fetchone()
        return True
    except sqlite3.DatabaseError:
        return False
    except Exception:
        return False


def _backup_candidates(exclude: Path | None = None) -> list[Path]:
    exclude_resolved = exclude.resolve() if exclude else None
    found: list[Path] = []
    dirs: list[Path] = []
    backup_dir = Path("/data/backups")
    if backup_dir.is_dir():
        dirs.append(backup_dir)
    for directory in dirs:
        for pattern in ("db-backup-*.db", "baupass-*.sqlite3"):
            found.extend(directory.glob(pattern))
    unique: dict[str, Path] = {}
    for path in found:
        try:
            if not path.is_file() or path.stat().st_size < 4096:
                continue
            resolved = path.resolve()
            if exclude_resolved and resolved == exclude_resolved:
                continue
            unique[str(resolved)] = path
        except OSError:
            continue
    return sorted(unique.values(), key=lambda item: item.stat().st_mtime, reverse=True)


def restore_sqlite_from_backup(backup_path: Path, dest_path: Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        sidecar = Path(f"{dest_path}{suffix}")
        if sidecar.exists():
            try:
                sidecar.unlink()
            except OSError:
                pass
    shutil.copy2(backup_path, dest_path)
    for suffix in ("-wal", "-shm"):
        src_sidecar = Path(f"{backup_path}{suffix}")
        if src_sidecar.is_file():
            try:
                shutil.copy2(src_sidecar, Path(f"{dest_path}{suffix}"))
            except OSError:
                pass


def ensure_usable_sqlite_path(db_path: Path) -> Path:
    """
    Return db_path when login-ready; otherwise restore the newest valid backup
    and return db_path. Raises RuntimeError when no usable database exists.
    """
    if sqlite_core_tables_ok(db_path):
        return db_path

    auto = str(os.getenv("BAUPASS_SQLITE_AUTO_RESTORE", "1")).strip().lower()
    if auto in {"0", "false", "no", "off"}:
        raise RuntimeError(f"SQLite database at {db_path} is not login-ready (auto-restore disabled)")

    for backup in _backup_candidates(exclude=db_path):
        if not sqlite_core_tables_ok(backup):
            continue
        try:
            restore_sqlite_from_backup(backup, db_path)
            print(
                f"[baupass] Restored SQLite DB from backup {backup} → {db_path}",
                flush=True,
            )
        except Exception as exc:
            print(f"[baupass] WARNING: SQLite restore from {backup} failed: {exc}", flush=True)
            continue
        if sqlite_core_tables_ok(db_path):
            return db_path

    raise RuntimeError(
        f"SQLite database at {db_path} is not login-ready and no valid backup was found under /data/backups"
    )
