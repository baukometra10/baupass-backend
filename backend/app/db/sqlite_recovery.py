"""SQLite integrity checks and auto-restore from backups when the live DB is unusable."""
from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def sqlite_core_tables_ok(db_path: Path, *, timeout: float = 3.0, attempts: int = 3) -> bool:
    """Return True when users (and settings) are readable — minimum for admin login."""
    if not db_path.is_file() or db_path.stat().st_size < 4096:
        return False
    for attempt in range(max(1, attempts)):
        try:
            with sqlite3.connect(str(db_path), timeout=timeout) as conn:
                conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
                conn.execute("SELECT 1 FROM settings LIMIT 1").fetchone()
            return True
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() and attempt + 1 < attempts:
                import time

                time.sleep(0.15 * (attempt + 1))
                continue
            return False
        except sqlite3.DatabaseError:
            return False
        except Exception:
            return False
    return False


def _is_sqlite_locked(exc: BaseException) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower()


def _backup_search_dirs(db_path: Path | None = None) -> list[Path]:
    dirs: list[Path] = []
    seen: set[str] = set()

    def add(directory: Path) -> None:
        try:
            if not directory.is_dir():
                return
            key = str(directory.resolve())
        except OSError:
            key = str(directory)
        if key in seen:
            return
        seen.add(key)
        dirs.append(directory)

    add(Path("/data/backups"))
    if db_path is not None:
        add(db_path.parent / "backups")
    backend_root = Path(__file__).resolve().parents[2]
    add(backend_root / "backups")
    return dirs


def _backup_candidates(exclude: Path | None = None, db_path: Path | None = None) -> list[Path]:
    exclude_resolved = exclude.resolve() if exclude else None
    found: list[Path] = []
    for directory in _backup_search_dirs(db_path):
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


def _quarantine_unusable_db(db_path: Path) -> None:
    """Move a corrupt or login-unready DB aside so init_db can create a fresh file."""
    if not db_path.is_file():
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    quarantine = db_path.with_name(f"{db_path.name}.unusable-{stamp}")
    try:
        db_path.rename(quarantine)
        print(
            f"[baupass] Quarantined unusable SQLite DB {db_path} → {quarantine}",
            flush=True,
        )
    except OSError as exc:
        print(f"[baupass] WARNING: Could not quarantine {db_path}: {exc}", flush=True)
        return
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{db_path}{suffix}")
        if sidecar.is_file():
            try:
                sidecar.rename(Path(f"{quarantine}{suffix}"))
            except OSError:
                pass


def ensure_usable_sqlite_path(db_path: Path) -> Path:
    """
    Return db_path when login-ready; otherwise restore the newest valid backup.
    When no backups exist, quarantine a corrupt file and allow init_db to bootstrap fresh.
    Raises RuntimeError only when backups exist but none could be restored.
    """
    if sqlite_core_tables_ok(db_path):
        return db_path

    auto = str(os.getenv("BAUPASS_SQLITE_AUTO_RESTORE", "1")).strip().lower()
    if auto in {"0", "false", "no", "off"}:
        raise RuntimeError(f"SQLite database at {db_path} is not login-ready (auto-restore disabled)")

    # Busy DB during concurrent requests is not corruption — never quarantine for that.
    try:
        with sqlite3.connect(str(db_path), timeout=3.0) as conn:
            conn.execute("SELECT 1").fetchone()
        print(
            f"[baupass] WARNING: SQLite at {db_path} passed open check but core tables probe failed — "
            "continuing without quarantine.",
            flush=True,
        )
        return db_path
    except sqlite3.OperationalError as exc:
        if _is_sqlite_locked(exc):
            print(f"[baupass] WARNING: SQLite at {db_path} is temporarily locked — continuing.", flush=True)
            return db_path
    except Exception:
        pass

    candidates = _backup_candidates(exclude=db_path, db_path=db_path)
    for backup in candidates:
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

    if not candidates:
        _quarantine_unusable_db(db_path)
        print(
            f"[baupass] WARNING: SQLite at {db_path} is not login-ready and no backups were found — "
            "bootstrapping a fresh database.",
            flush=True,
        )
        return db_path

    raise RuntimeError(
        f"SQLite database at {db_path} is not login-ready and no valid backup could be restored "
        f"({len(candidates)} candidate(s) checked)"
    )
