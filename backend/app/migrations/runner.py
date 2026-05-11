"""
BauPass – Migration CLI Runner
================================
تشغيل:
    python -m backend.app.migrations.runner --migrate
    python -m backend.app.migrations.runner --status
    python -m backend.app.migrations.runner --dry-run
    python -m backend.app.migrations.runner --rollback-last  (بحذر!)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def _get_db_path() -> Path:
    import os
    explicit = os.getenv("BAUPASS_DB_PATH", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    railway = Path("/data/baupass.db")
    if railway.parent.is_dir():
        return railway
    return Path(__file__).resolve().parent.parent.parent.parent / "backend" / "baupass.db"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="BauPass Database Migration Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m backend.app.migrations.runner --migrate
  python -m backend.app.migrations.runner --status
  python -m backend.app.migrations.runner --dry-run
  python -m backend.app.migrations.runner --rollback-last
        """,
    )
    parser.add_argument("--migrate",       action="store_true", help="Apply pending migrations")
    parser.add_argument("--status",        action="store_true", help="Show migration status")
    parser.add_argument("--dry-run",       action="store_true", help="Show what would be applied")
    parser.add_argument("--rollback-last", action="store_true", help="Roll back last migration (DANGEROUS)")
    parser.add_argument("--db-path",       default="", help="Override DB path")

    args = parser.parse_args()

    if not any([args.migrate, args.status, args.dry_run, args.rollback_last]):
        parser.print_help()
        return 1

    from backend.app.database import MigrationRunner
    from backend.app.migrations import ALL_MIGRATIONS

    db_path = Path(args.db_path).expanduser() if args.db_path else _get_db_path()
    print(f"Database: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;
    """)

    runner = MigrationRunner(conn)

    try:
        if args.status:
            applied = runner.status()
            all_versions = {m.version: m.name for m in ALL_MIGRATIONS}
            applied_versions = {r["version"] for r in applied}
            pending = [m for m in ALL_MIGRATIONS if m.version not in applied_versions]

            print(f"\n{'─'*60}")
            print(f"  Migration Status: {db_path.name}")
            print(f"{'─'*60}")
            print(f"  Applied:  {len(applied)}")
            print(f"  Pending:  {len(pending)}")
            print(f"{'─'*60}")

            for rec in applied:
                rolled = " [ROLLED BACK]" if rec["rolled_back"] else ""
                print(f"  ✓ {rec['version']:12s} {rec['name'][:40]:40s} {rec['applied_at'][:19]}{rolled}")

            for m in pending:
                print(f"  ○ {m.version:12s} {m.name[:40]:40s} (pending)")

            print(f"{'─'*60}\n")
            return 0

        if args.dry_run:
            executed = runner.run(ALL_MIGRATIONS, dry_run=True)
            if not executed:
                print("✓ Database is up to date. Nothing to apply.")
            else:
                print(f"\nWould apply {len(executed)} migration(s):")
                for v in executed:
                    print(f"  - {v}")
            return 0

        if args.migrate:
            executed = runner.run(ALL_MIGRATIONS)
            if not executed:
                print("✓ Database is up to date.")
            else:
                print(f"\n✓ Applied {len(executed)} migration(s):")
                for v in executed:
                    print(f"  - {v}")
            return 0

        if args.rollback_last:
            confirm = input(
                "\n⚠️  WARNING: Rolling back migrations can cause data loss.\n"
                "   Type 'yes I understand' to confirm: "
            ).strip()
            if confirm != "yes I understand":
                print("Aborted.")
                return 1
            version = runner.rollback_last()
            if version:
                print(f"Marked migration {version} as rolled back.")
                print("You must manually execute the down_sql from migrations/__init__.py")
            return 0

    except Exception as exc:
        print(f"\n❌ Migration error: {exc}", file=sys.stderr)
        return 2

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
