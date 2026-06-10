"""Migration registry invariants — versions must stay unique for SQLite schema_migrations."""
from __future__ import annotations

from collections import Counter

from backend.app.migrations import ALL_MIGRATIONS


def test_migration_versions_are_unique():
    versions = [m.version for m in ALL_MIGRATIONS]
    duplicates = [v for v, count in Counter(versions).items() if count > 1]
    assert not duplicates, f"duplicate migration versions: {duplicates}"


def test_site_cameras_migration_registered():
    by_name = {m.name: m.version for m in ALL_MIGRATIONS}
    assert by_name.get("site_cameras_registry") == "025"


def test_ai_chat_sessions_migration_registered():
    by_name = {m.name: m.version for m in ALL_MIGRATIONS}
    assert by_name.get("ai_chat_sessions") == "024"


def test_migrations_sorted_for_deterministic_apply_order():
    ordered = sorted(ALL_MIGRATIONS, key=lambda m: (int(m.version), m.name))
    assert ALL_MIGRATIONS == ordered, "ALL_MIGRATIONS must be sorted by (int(version), name)"
