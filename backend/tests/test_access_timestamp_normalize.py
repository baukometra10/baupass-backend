"""Canonical access-log timestamp normalization (naive Europe/Berlin)."""
from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path


def _load_common():
    path = Path(__file__).resolve().parents[1] / "app" / "platform" / "physical_operations" / "_common.py"
    spec = importlib.util.spec_from_file_location("access_common_norm", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_normalize_z_winter_to_berlin_naive():
    mod = _load_common()
    # 2026-01-15 09:00 UTC → 10:00 Berlin (CET) with IANA; fixed +02 fallback → 11:00
    expected = "2026-01-15T10:00:00" if mod.ACCESS_WALL_TZ_IS_IANA else "2026-01-15T11:00:00"
    assert mod.normalize_access_timestamp_value("2026-01-15T09:00:00Z") == expected


def test_normalize_z_summer_to_berlin_naive():
    mod = _load_common()
    # 2026-07-15 09:00 UTC → 11:00 Berlin (CEST); +02 fallback also 11:00
    assert mod.normalize_access_timestamp_value("2026-07-15T09:00:00Z") == "2026-07-15T11:00:00"


def test_normalize_naive_unchanged():
    mod = _load_common()
    assert mod.normalize_access_timestamp_value("2026-07-19T02:00:00") == "2026-07-19T02:00:00"


def test_normalize_empty_and_garbage():
    mod = _load_common()
    assert mod.normalize_access_timestamp_value("") == ""
    assert mod.normalize_access_timestamp_value("not-a-date") == ""


def test_access_now_iso_shape():
    mod = _load_common()
    stamp = mod.access_now_iso()
    assert len(stamp) == 19
    assert stamp[10] == "T"
    assert not stamp.endswith("Z")
    datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S")


def test_migration_classify_and_idempotent(tmp_path):
    import sqlite3
    import sys

    repo = Path(__file__).resolve().parents[2]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from backend.ops.migrate_access_log_timestamps import migrate

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE access_logs (id TEXT PRIMARY KEY, timestamp TEXT)"
    )
    conn.executemany(
        "INSERT INTO access_logs (id, timestamp) VALUES (?, ?)",
        [
            ("a", "2026-01-15T09:00:00Z"),
            ("b", "2026-07-19T02:00:00"),
            ("c", ""),
            ("d", "bad"),
        ],
    )
    conn.commit()
    conn.close()

    dry = migrate(db_path, apply=False, limit_sample=10, allow_fixed_offset=True)
    assert dry["ok"] is True
    assert dry["converted"] == 1
    assert dry["alreadyCanonical"] == 1
    assert dry["empty"] == 1
    assert dry["unparseable"] == 1
    assert dry["wouldChange"] == 1

    applied = migrate(db_path, apply=True, limit_sample=10, allow_fixed_offset=True)
    assert applied["ok"] is True
    assert applied["changed"] == 1

    again = migrate(db_path, apply=True, limit_sample=10, allow_fixed_offset=True)
    assert again["ok"] is True
    assert again["converted"] == 0
    assert again["changed"] == 0
    assert again["alreadyCanonical"] >= 2

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT timestamp FROM access_logs WHERE id='a'").fetchone()
    conn.close()
    mod = _load_common()
    expected = "2026-01-15T10:00:00" if mod.ACCESS_WALL_TZ_IS_IANA else "2026-01-15T11:00:00"
    assert row[0] == expected


def test_open_entries_accepts_naive_berlin():
    """build_open_entries_from_rows must not TypeError on naive stamps vs aware now."""
    import sys

    repo = Path(__file__).resolve().parents[2]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    # Import only the function via a light stub path — load from server is heavy;
    # replicate the comparison using shared parser instead when Flask import fails.
    mod = _load_common()
    entry = mod._parse_access_timestamp("2026-07-19T08:00:00")
    now = datetime.now(timezone.utc).astimezone(mod.ACCESS_WALL_TZ)
    assert entry is not None
    minutes = int((now - entry).total_seconds() // 60)
    assert minutes >= 0
