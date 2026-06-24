#!/usr/bin/env python3
"""
Production cutover validation (PostgreSQL + Redis + DR posture).

Usage:
  python backend/ops/production_cutover_check.py --base-url https://your-app.up.railway.app
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib import request as urlrequest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fetch_json(url: str, timeout: int = 20) -> tuple[int, dict]:
    req = urlrequest.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode()
    return resp.status, json.loads(body or "{}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate SUPPIX production cutover readiness")
    parser.add_argument("--base-url", default=os.getenv("PUBLIC_BASE_URL", "").strip())
    args = parser.parse_args()
    base = (args.base_url or "").rstrip("/")
    if not base:
        print("ERROR: set --base-url or PUBLIC_BASE_URL", file=sys.stderr)
        return 1

    checks: dict[str, object] = {}
    ok = True

    endpoints = {
        "health": f"{base}/api/health",
        "ready": f"{base}/api/health/ready",
        "queues": f"{base}/api/health/queues",
        "dr": f"{base}/api/health/dr",
    }
    for name, url in endpoints.items():
        try:
            status, payload = _fetch_json(url)
            checks[name] = {"httpStatus": status, "payload": payload}
            if name == "ready" and (status != 200 or payload.get("status") != "ready"):
                ok = False
            if name == "health" and status != 200:
                ok = False
            if name == "dr" and not payload.get("ok", False):
                ok = False
        except Exception as exc:
            checks[name] = {"error": str(exc)}
            ok = False

    try:
        from backend.app.database import postgres_preflight
        from backend.app.db.runtime import postgres_runtime_enabled

        if postgres_runtime_enabled():
            pf = postgres_preflight()
            checks["postgres_preflight"] = pf
            if pf.get("status") != "ok":
                ok = False
        else:
            checks["postgres_preflight"] = {"status": "skipped", "reason": "BAUPASS_PG_RUNTIME not enabled"}
    except Exception as exc:
        checks["postgres_preflight"] = {"error": str(exc)}
        ok = False

    try:
        from backend.ops.validate_enterprise_env import _check_env, _check_http

        env_report = _check_env()
        checks["enterprise_env"] = env_report
        if env_report.get("criticalFailures"):
            ok = False
        live_ent = _check_http(base)
        checks["enterprise_live"] = live_ent
        if not live_ent.get("ok"):
            ok = False
    except Exception as exc:
        checks["enterprise_validation"] = {"error": str(exc)}
        ok = False

    result = {"ok": ok, "baseUrl": base, "checks": checks}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
