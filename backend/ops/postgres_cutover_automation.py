#!/usr/bin/env python3
"""
PostgreSQL cutover automation — preflight, migration hint, runtime checklist.

Usage:
  python backend/ops/postgres_cutover_automation.py
  python backend/ops/postgres_cutover_automation.py --sqlite /data/baupass.db --migrate
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="BauPass PostgreSQL cutover automation")
    parser.add_argument("--sqlite", default=os.getenv("BAUPASS_DB_PATH", "backend/baupass.db"))
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Run sqlite_to_postgres after preflight (requires DATABASE_URL)",
    )
    parser.add_argument("--truncate", action="store_true", help="Pass --truncate to migration")
    args = parser.parse_args()

    report: dict[str, object] = {"steps": []}
    ok = True

    db_url = (os.getenv("DATABASE_URL") or "").strip()
    pg_runtime = os.getenv("BAUPASS_PG_RUNTIME", "").strip().lower() in {"1", "true", "yes"}
    report["env"] = {
        "DATABASE_URL": bool(db_url),
        "BAUPASS_PG_RUNTIME": pg_runtime,
        "BAUPASS_ALLOW_SQLITE_PRODUCTION": os.getenv("BAUPASS_ALLOW_SQLITE_PRODUCTION", ""),
    }

    if not db_url:
        report["steps"].append({"id": "database_url", "ok": False, "hint": "Set DATABASE_URL on Railway PostgreSQL service"})
        ok = False
    else:
        report["steps"].append({"id": "database_url", "ok": True})

    try:
        from backend.app.database import postgres_preflight

        pf = postgres_preflight()
        report["preflight"] = pf
        report["steps"].append({"id": "preflight", "ok": pf.get("status") == "ok", "detail": pf.get("status")})
        if pf.get("status") != "ok":
            ok = False
    except Exception as exc:
        report["steps"].append({"id": "preflight", "ok": False, "error": str(exc)})
        ok = False

    sqlite_path = Path(args.sqlite)
    report["sqlite"] = {"path": str(sqlite_path), "exists": sqlite_path.is_file()}
    if not sqlite_path.is_file():
        report["steps"].append({"id": "sqlite_file", "ok": False})
        ok = False
    else:
        report["steps"].append({"id": "sqlite_file", "ok": True})

    if args.migrate and ok:
        import subprocess

        cmd = [sys.executable, str(ROOT / "backend" / "ops" / "sqlite_to_postgres.py"), "--sqlite", str(sqlite_path)]
        if args.truncate:
            cmd.append("--truncate")
        try:
            subprocess.run(cmd, check=True, cwd=str(ROOT))
            report["steps"].append({"id": "migrate", "ok": True})
        except subprocess.CalledProcessError as exc:
            report["steps"].append({"id": "migrate", "ok": False, "error": str(exc)})
            ok = False

    report["ok"] = ok
    report["next"] = [
        "Set BAUPASS_PG_RUNTIME=1 on API service",
        "Keep BAUPASS_ALLOW_SQLITE_PRODUCTION=1 for one week rollback",
        "Run: python backend/ops/validate_enterprise_env.py --base-url $PUBLIC_BASE_URL --strict",
        "Verify /api/health → db backend postgres",
    ]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
