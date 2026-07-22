import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = BASE_DIR / "backend" / "baupass.db"
DEFAULT_BACKUP_DIR = BASE_DIR / "backend" / "backups" / "sqlite"
DEFAULT_RETENTION_DAYS = int(os.getenv("BAUPASS_DB_BACKUP_RETENTION_DAYS", "30"))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_db_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env_path = (os.getenv("BAUPASS_DB_PATH") or "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    return DEFAULT_DB_PATH.resolve()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_db_stats(db_path: Path) -> Dict[str, Any]:
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        tables = [
            "users",
            "companies",
            "workers",
            "access_logs",
            "device_ingest_events",
            "worker_gate_feedback_events",
            "audit_logs",
        ]
        row_counts: Dict[str, int] = {}
        for table in tables:
            try:
                row = db.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
                row_counts[table] = int(row["c"] if row else 0)
            except sqlite3.Error:
                row_counts[table] = -1

        integrity_row = db.execute("PRAGMA integrity_check").fetchone()
        integrity = str(integrity_row[0] if integrity_row else "unknown")

    return {
        "rowCounts": row_counts,
        "integrityCheck": integrity,
    }


def prune_old_backups(backup_dir: Path, retention_days: int) -> Dict[str, Any]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    cutoff = utc_now() - timedelta(days=max(1, retention_days))
    removed = []
    kept = 0

    for backup in backup_dir.glob("baupass-*.sqlite3"):
        try:
            modified = datetime.fromtimestamp(backup.stat().st_mtime, tz=timezone.utc)
            if modified < cutoff:
                backup.unlink(missing_ok=True)
                meta = backup.with_suffix(".meta.json")
                if meta.exists():
                    meta.unlink(missing_ok=True)
                removed.append(str(backup))
            else:
                kept += 1
        except OSError:
            continue

    return {
        "retentionDays": max(1, retention_days),
        "removed": removed,
        "kept": kept,
    }


def perform_backup(db_path: Path, backup_dir: Path, retention_days: int) -> Dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"baupass-{timestamp}.sqlite3"

    with sqlite3.connect(db_path) as source:
        with sqlite3.connect(backup_path) as dest:
            source.backup(dest)

    stats = collect_db_stats(backup_path)
    digest = sha256_file(backup_path)

    metadata = {
        "createdAt": utc_now().isoformat(),
        "sourceDbPath": str(db_path),
        "backupPath": str(backup_path),
        "sizeBytes": backup_path.stat().st_size,
        "sha256": digest,
        "stats": stats,
    }

    meta_path = backup_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    rotation = prune_old_backups(backup_dir, retention_days)

    return {
        "ok": True,
        "action": "backup",
        "backupPath": str(backup_path),
        "metadataPath": str(meta_path),
        "sha256": digest,
        "sizeBytes": backup_path.stat().st_size,
        "integrityCheck": stats.get("integrityCheck"),
        "rotation": rotation,
    }


def perform_verify_restore(backup_path: Path, work_dir: Path, keep_restored: bool) -> Dict[str, Any]:
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    work_dir.mkdir(parents=True, exist_ok=True)
    restored_path = work_dir / f"restore-check-{utc_now().strftime('%Y%m%d-%H%M%S')}.sqlite3"

    with sqlite3.connect(backup_path) as source:
        with sqlite3.connect(restored_path) as dest:
            source.backup(dest)

    stats = collect_db_stats(restored_path)
    integrity_ok = stats.get("integrityCheck") == "ok"

    required_tables = [
        "users",
        "companies",
        "workers",
        "access_logs",
    ]
    missing_required = [
        table
        for table, count in stats.get("rowCounts", {}).items()
        if table in required_tables and count < 0
    ]

    ok = integrity_ok and not missing_required

    result = {
        "ok": ok,
        "action": "verify-restore",
        "backupPath": str(backup_path),
        "restoredPath": str(restored_path),
        "sha256": sha256_file(backup_path),
        "integrityCheck": stats.get("integrityCheck"),
        "missingRequiredTables": missing_required,
        "rowCounts": stats.get("rowCounts", {}),
    }

    if not keep_restored:
        try:
            restored_path.unlink(missing_ok=True)
            result["restoredPath"] = "deleted"
        except OSError:
            pass

    return result


def latest_backup(backup_dir: Path) -> Path | None:
    files = sorted(backup_dir.glob("baupass-*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def upload_backup_offsite(backup_path: Path) -> Dict[str, Any]:
    """Best-effort upload of backup (+ meta) via object store. Never raises."""
    result: Dict[str, Any] = {"uploaded": False, "key": None, "error": None}
    try:
        backend = (os.getenv("UPLOAD_BACKEND") or "local").strip().lower()
        # Only treat real remote backends as offsite success for operators.
        if backend != "s3" or not (os.getenv("S3_BUCKET") or "").strip():
            result["error"] = "offsite_not_configured"
            return result
        from backend.app.platform.storage.object_store import get_object_store

        store = get_object_store()
        key = f"backups/sqlite/{backup_path.name}"
        store.put(key, backup_path.read_bytes(), content_type="application/x-sqlite3")
        meta_path = backup_path.with_suffix(".meta.json")
        if meta_path.exists():
            store.put(
                f"backups/sqlite/{meta_path.name}",
                meta_path.read_bytes(),
                content_type="application/json",
            )
        result["uploaded"] = True
        result["key"] = key
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)[:300]
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and verify SQLite backups for SUPPIX.")
    parser.add_argument("command", choices=["backup", "verify-restore"], help="Operation mode")
    parser.add_argument("--db-path", dest="db_path", default="", help="Path to source SQLite DB")
    parser.add_argument("--backup-dir", dest="backup_dir", default=str(DEFAULT_BACKUP_DIR), help="Backup directory")
    parser.add_argument("--backup-path", dest="backup_path", default="", help="Specific backup file for verify-restore")
    parser.add_argument("--retention-days", dest="retention_days", type=int, default=DEFAULT_RETENTION_DAYS)
    parser.add_argument("--keep-restored", dest="keep_restored", action="store_true")
    parser.add_argument("--upload", dest="upload", action="store_true", help="Upload backup to object store (S3/R2)")

    args = parser.parse_args()
    backup_dir = Path(args.backup_dir).expanduser().resolve()

    try:
        if args.command == "backup":
            db_path = resolve_db_path(args.db_path)
            ensure_parent(db_path)
            result = perform_backup(db_path, backup_dir, max(1, args.retention_days))
            if args.upload:
                offsite = upload_backup_offsite(Path(result["backupPath"]))
                result["offsite"] = offsite
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "verify-restore":
            if args.backup_path:
                backup_path = Path(args.backup_path).expanduser().resolve()
            else:
                latest = latest_backup(backup_dir)
                if not latest:
                    raise FileNotFoundError("No backup file found in backup directory.")
                backup_path = latest

            verify_dir = backup_dir / "restore-check"
            result = perform_verify_restore(backup_path, verify_dir, args.keep_restored)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("ok") else 2

        return 1

    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc), "command": args.command}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
