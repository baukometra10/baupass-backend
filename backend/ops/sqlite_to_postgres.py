#!/usr/bin/env python3
"""
Copy BauPass schema + data from SQLite to PostgreSQL.

Usage:
  set DATABASE_URL=postgresql://...
  python backend/ops/sqlite_to_postgres.py --sqlite backend/baupass.db
  python backend/ops/sqlite_to_postgres.py --sqlite /data/baupass.db --truncate

Then enable runtime:
  BAUPASS_PG_RUNTIME=1
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.database import init_postgres_pool, is_postgres_configured, postgres_connection

SQLITE_TYPE_MAP = {
    "INTEGER": "BIGINT",
    "INT": "BIGINT",
    "REAL": "DOUBLE PRECISION",
    "TEXT": "TEXT",
    "BLOB": "BYTEA",
    "NUMERIC": "NUMERIC",
    "BOOLEAN": "BOOLEAN",
}


def _pg_type(sqlite_decl: str, col_name: str, pk: bool) -> str:
    decl = (sqlite_decl or "TEXT").upper()
    if pk and "INT" in decl:
        return "BIGSERIAL PRIMARY KEY"
    for key, pg in SQLITE_TYPE_MAP.items():
        if key in decl:
            return pg
    return "TEXT"


def list_sqlite_tables(sqlite_conn: sqlite3.Connection) -> list[str]:
    rows = sqlite_conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [r[0] for r in rows]


def create_pg_table(sqlite_conn: sqlite3.Connection, pg_conn, table: str, truncate: bool) -> None:
    info = sqlite_conn.execute(f"PRAGMA table_info({table})").fetchall()
    if not info:
        return
    cols = []
    for col in info:
        cid, name, decl, notnull, default, pk = col
        pg_t = _pg_type(decl or "", name, bool(pk))
        null_sql = " NOT NULL" if notnull and "PRIMARY KEY" not in pg_t else ""
        default_sql = ""
        if default is not None and default != "" and "PRIMARY KEY" not in pg_t:
            default_sql = f" DEFAULT {default}"
        cols.append(f'"{name}" {pg_t}{null_sql}{default_sql}')
    ddl = f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(cols)})'
    with pg_conn.cursor() as cur:
        if truncate:
            cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        cur.execute(ddl)
    pg_conn.commit()


def copy_table_data(sqlite_conn: sqlite3.Connection, pg_conn, table: str, batch: int) -> int:
    info = sqlite_conn.execute(f"PRAGMA table_info({table})").fetchall()
    sqlite_cols = [c[1] for c in info]
    pg_cols = [f'"{c}"' for c in sqlite_cols]
    if not sqlite_cols:
        return 0
    placeholders = ", ".join(["%s"] * len(pg_cols))
    insert_sql = f'INSERT INTO "{table}" ({", ".join(pg_cols)}) VALUES ({placeholders})'
    total = 0
    offset = 0
    while True:
        rows = sqlite_conn.execute(
            f'SELECT {", ".join(sqlite_cols)} FROM "{table}" LIMIT ? OFFSET ?',
            (batch, offset),
        ).fetchall()
        if not rows:
            break
        with pg_conn.cursor() as cur:
            cur.executemany(insert_sql, rows)
        pg_conn.commit()
        total += len(rows)
        offset += batch
    return total


def reset_sequences(pg_conn) -> None:
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'S' AND n.nspname = 'public'
            """
        )
        for (seq_name,) in cur.fetchall():
            table_guess = seq_name.replace("_id_seq", "")
            try:
                cur.execute(
                    f"""
                    SELECT setval('{seq_name}',
                        COALESCE((SELECT MAX(id) FROM "{table_guess}"), 1),
                        true)
                    """
                )
            except Exception:
                pg_conn.rollback()
                continue
    pg_conn.commit()


def migrate_sqlite_to_postgres(
    sqlite_path: Path,
    *,
    batch: int = 500,
    truncate: bool = False,
    schema_only: bool = False,
) -> dict[str, int | bool]:
    """Migrate schema/data from SQLite file into configured PostgreSQL DB."""
    if not is_postgres_configured():
        raise RuntimeError("DATABASE_URL must be a postgresql:// URL")
    if not init_postgres_pool():
        raise RuntimeError("Could not initialize PostgreSQL pool")
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite file not found: {sqlite_path}")

    sqlite_conn = sqlite3.connect(str(sqlite_path))
    try:
        tables = list_sqlite_tables(sqlite_conn)
        rows_copied = 0
        with postgres_connection() as pg_conn:
            for table in tables:
                create_pg_table(sqlite_conn, pg_conn, table, truncate=truncate)
            if not schema_only:
                for table in tables:
                    rows_copied += copy_table_data(sqlite_conn, pg_conn, table, batch)
                reset_sequences(pg_conn)
        return {"tables": len(tables), "rows": rows_copied, "schema_only": schema_only}
    finally:
        sqlite_conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate BauPass SQLite → PostgreSQL")
    parser.add_argument("--sqlite", required=True, help="Path to baupass.db")
    parser.add_argument("--batch", type=int, default=500)
    parser.add_argument("--truncate", action="store_true", help="Drop PG tables before create")
    parser.add_argument("--schema-only", action="store_true")
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite).expanduser()
    try:
        result = migrate_sqlite_to_postgres(
            sqlite_path,
            batch=args.batch,
            truncate=args.truncate,
            schema_only=args.schema_only,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"Migration complete (tables={result['tables']}, rows={result['rows']}). "
        "Set BAUPASS_PG_RUNTIME=1 and redeploy."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
