"""
Migration Runner for SUPPIX Platform
====================================

Lädt und führt alle Migrationen aus.
"""

import os
import logging
from pathlib import Path
import importlib.util
from typing import List

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent


def get_migrations() -> List[tuple]:
    """Get all migrations sorted by version."""
    migrations = []
    for file in sorted(MIGRATIONS_DIR.glob("*.py")):
        if file.name.startswith("__"):
            continue
        version = file.stem
        migrations.append((version, file))
    return migrations


def load_migration_module(migration_file: Path):
    """Dynamically load migration module."""
    spec = importlib.util.spec_from_file_location("migration", migration_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_migrations(db_path: str, direction: str = "up") -> None:
    """Run all migrations."""
    migrations = get_migrations()

    if not migrations:
        logger.warning("No migrations found")
        return

    logger.info(f"Running {direction} migrations for {db_path}")

    if direction == "up":
        migrations = sorted(migrations)
    else:
        migrations = sorted(migrations, reverse=True)

    for version, migration_file in migrations:
        try:
            logger.info(f"Applying migration: {version}")
            module = load_migration_module(migration_file)

            if direction == "up":
                module.migrate_up(db_path)
            else:
                module.migrate_down(db_path)

            logger.info(f"✓ Completed: {version}")
        except Exception as e:
            logger.error(f"✗ Failed: {version} - {e}")
            raise


if __name__ == "__main__":
    import sys
    direction = sys.argv[1] if len(sys.argv) > 1 else "up"
    db_path = sys.argv[2] if len(sys.argv) > 2 else "backend/baupass.db"

    logging.basicConfig(level=logging.INFO)
    run_migrations(db_path, direction)
