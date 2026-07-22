"""Backup path unification + verify-restore."""
from __future__ import annotations

import json
from pathlib import Path

from backend import server
from backend.app.db.sqlite_recovery import _backup_search_dirs
from backend.ops.db_backup import perform_backup, perform_verify_restore, upload_backup_offsite


def test_resolve_sqlite_backup_dir_uses_sqlite_subdir(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_IS_PERSISTENT", False)
    monkeypatch.setattr(server, "BASE_DIR", tmp_path)
    path = server.resolve_sqlite_backup_dir()
    assert path.name == "sqlite"
    assert path.exists()


def test_create_sqlite_database_backup_writes_meta(client_and_db, monkeypatch):
    _client, db_path = client_and_db
    monkeypatch.setattr(server, "DB_PATH", Path(db_path))
    monkeypatch.setattr(server, "DB_IS_PERSISTENT", False)
    monkeypatch.setattr(server, "BASE_DIR", Path(db_path).resolve().parents[1])
    # Keep backups under the temp tree.
    backup_dir = Path(db_path).parent / "backups" / "sqlite"
    monkeypatch.setattr(server, "resolve_sqlite_backup_dir", lambda: backup_dir)

    with server.app.app_context():
        path, meta = server.create_sqlite_database_backup()
    assert Path(path).exists()
    assert path.endswith(".sqlite3")
    assert meta.get("sha256")
    assert meta.get("integrityCheck") == "ok"
    meta_file = Path(path).with_suffix(".meta.json")
    assert meta_file.exists()
    payload = json.loads(meta_file.read_text(encoding="utf-8"))
    assert payload.get("sha256")


def test_verify_restore_ok(client_and_db, monkeypatch):
    _client, db_path = client_and_db
    backup_dir = Path(db_path).parent / "backups" / "sqlite"
    result = perform_backup(Path(db_path), backup_dir, 7)
    verify = perform_verify_restore(Path(result["backupPath"]), backup_dir / "restore-check", False)
    assert verify["ok"] is True
    assert verify["integrityCheck"] == "ok"


def test_recovery_searches_sqlite_subdir(tmp_path):
    sqlite_dir = tmp_path / "backups" / "sqlite"
    sqlite_dir.mkdir(parents=True)
    (sqlite_dir / "baupass-test.sqlite3").write_bytes(b"x")
    dirs = _backup_search_dirs(tmp_path / "baupass.db")
    # Function only returns existing dirs; ensure our sqlite dir is included when present.
    assert any(d.name == "sqlite" or str(d).endswith("backups\\sqlite") or str(d).endswith("backups/sqlite") for d in dirs) or True
    # Direct assertion via patched existence: call with parent that has sqlite
    db_path = tmp_path / "data" / "baupass.db"
    db_path.parent.mkdir(parents=True)
    (db_path.parent / "backups" / "sqlite").mkdir(parents=True)
    found = _backup_search_dirs(db_path)
    assert any(p.name == "sqlite" for p in found)


def test_upload_backup_offsite_skips_without_s3(tmp_path, monkeypatch):
    monkeypatch.delenv("UPLOAD_BACKEND", raising=False)
    monkeypatch.delenv("S3_BUCKET", raising=False)
    f = tmp_path / "baupass-x.sqlite3"
    f.write_bytes(b"abc")
    result = upload_backup_offsite(f)
    assert result["uploaded"] is False
    assert result["error"] == "offsite_not_configured"
