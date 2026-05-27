#!/usr/bin/env python3
"""
PostgreSQL DR snapshot metadata (table counts + optional pg_dump).

Usage:
  DATABASE_URL=postgresql://... python backend/ops/postgres_dr_snapshot.py
  DATABASE_URL=postgresql://... python backend/ops/postgres_dr_snapshot.py --dump
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CORE_TABLES = (
    "companies",
    "workers",
    "users",
    "sessions",
    "invoices",
    "system_alerts",
    "access_logs",
    "platform_events",
)


def table_counts() -> dict:
    from backend.app.database import init_postgres_pool, postgres_connection

    if not init_postgres_pool():
        raise RuntimeError("PostgreSQL pool init failed")
    out = {}
    with postgres_connection() as conn:
        with conn.cursor() as cur:
            for table in CORE_TABLES:
                try:
                    cur.execute(f'SELECT COUNT(*) AS c FROM "{table}"')
                    row = cur.fetchone()
                    if isinstance(row, dict):
                        out[table] = int(row.get("c") or 0)
                    else:
                        out[table] = int(row[0])
                except Exception as exc:
                    out[table] = f"error:{exc}"
    return out


def _pg_dump(output_dir: Path) -> dict:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is required for --dump")
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_file = output_dir / f"pg-dump-{stamp}.sql"
    cmd = ["pg_dump", url, "-f", str(out_file), "--no-owner", "--no-acl"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr.strip() or proc.stdout.strip(), "command": " ".join(cmd[:2])}
    return {"ok": True, "path": str(out_file), "sizeBytes": out_file.stat().st_size if out_file.exists() else 0}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="PostgreSQL DR snapshot helper")
    parser.add_argument("--dump", action="store_true", help="Run pg_dump when available")
    parser.add_argument("--output-dir", default=str(ROOT / "backend" / "backups" / "postgres"))
    args = parser.parse_args()

    try:
        counts = table_counts()
        payload = {
            "ok": True,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "tableCounts": counts,
        }
        if args.dump:
            payload["dump"] = _pg_dump(Path(args.output_dir))
            if not payload["dump"].get("ok"):
                payload["ok"] = False
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") else 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
