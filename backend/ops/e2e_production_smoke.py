#!/usr/bin/env python3
"""
Production E2E smoke — fast, read-mostly checks after deploy (no secrets printed).

Usage:
  python backend/ops/e2e_production_smoke.py --base-url https://baupass-production.up.railway.app
  BAUPASS_SMOKE_TOKEN=<jwt> python backend/ops/e2e_production_smoke.py --base-url ...
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any
from urllib import error, request

TIMEOUT = 20


def _get(url: str, headers: dict | None = None) -> tuple[int, dict, float]:
    h = {"Accept": "application/json", **(headers or {})}
    req = request.Request(url, headers=h, method="GET")
    t0 = time.perf_counter()
    try:
        with request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode() or "{}"
            ms = (time.perf_counter() - t0) * 1000
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = {"_raw": body[:200]}
            return resp.status, data, ms
    except error.HTTPError as exc:
        ms = (time.perf_counter() - t0) * 1000
        try:
            data = json.loads(exc.read().decode() or "{}")
        except Exception:
            data = {"error": str(exc)}
        return exc.code, data, ms


def _get_html(url: str) -> tuple[int, float]:
    req = request.Request(url, method="GET")
    t0 = time.perf_counter()
    with request.urlopen(req, timeout=TIMEOUT) as resp:
        resp.read(4096)
        return resp.status, (time.perf_counter() - t0) * 1000


def run_smoke(base: str, token: str | None) -> dict[str, Any]:
    base = base.rstrip("/")
    checks: list[dict[str, Any]] = []
    ok = True
    max_ms = 0

    def add(
        name: str,
        passed: bool,
        *,
        ms: float = 0,
        detail: str = "",
        severity: str = "critical",
    ) -> None:
        nonlocal ok, max_ms
        if not passed and severity == "critical":
            ok = False
        max_ms = max(max_ms, ms)
        checks.append({"name": name, "ok": passed, "ms": round(ms, 1), "detail": detail, "severity": severity})

    status, health, health_ms = _get(f"{base}/api/health")
    ent = health.get("enterprise") or {}
    db = health.get("db") or health.get("checks", {}).get("database") or {}
    add("health", status == 200 and health.get("status") in {"ok", "degraded"}, ms=health_ms)
    add(
        "demo_disabled",
        ent.get("demoAllowed") is not True,
        detail=f"demoAllowed={ent.get('demoAllowed')}",
    )
    add(
        "db_persistent",
        bool(db.get("persistent")),
        severity="recommended",
        detail=str(db.get("path") or ""),
    )

    status, ready, ms = _get(f"{base}/api/health/ready")
    add("ready", status == 200 and ready.get("status") == "ready", ms=ms, detail=ready.get("status", ""))

    status, setup, ms = _get(f"{base}/api/platform/setup-status")
    pct = (setup.get("readyScore") or {}).get("percent", 0)
    add("setup_status", status == 200 and pct >= 80, ms=ms, detail=f"{pct}%")

    status, prev, ms = _get(f"{base}/api/platform/enterprise-catalog/preview")
    add(
        "enterprise_catalog",
        status == 200 and (prev.get("layerCount") or 0) >= 16,
        ms=ms,
        detail=f"layers={prev.get('layerCount')}",
    )

    for path in (
        "/admin-v2/index.html",
        "/foreman.html",
        "/join.html",
        "/enterprise-hub.html",
    ):
        try:
            code, html_ms = _get_html(f"{base}{path}")
            add(f"page{path}", code == 200, ms=html_ms)
        except Exception as exc:
            add(f"page{path}", False, detail=str(exc))

    if token:
        auth = {"Authorization": f"Bearer {token}"}
        status, caps, ms = _get(f"{base}/api/platform/capabilities", auth)
        add("capabilities_auth", status == 200, ms=ms, severity="recommended")
        status, inbox, ms = _get(f"{base}/api/inbox/counts", auth)
        add("inbox_counts_auth", status == 200, ms=ms, severity="recommended")
    else:
        add("auth_skipped", True, detail="set BAUPASS_SMOKE_TOKEN for inbox/capabilities", severity="info")

    add("health_latency", health_ms <= 3000, ms=health_ms, detail=f"{round(health_ms)}ms", severity="recommended")

    return {
        "ok": ok,
        "baseUrl": base,
        "maxLatencyMs": round(max_ms, 1),
        "checks": checks,
        "passed": sum(1 for c in checks if c["ok"]),
        "total": len(checks),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="BauPass production E2E smoke")
    parser.add_argument("--base-url", default=os.getenv("PUBLIC_BASE_URL", "").strip())
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    if not args.base_url:
        print("ERROR: --base-url or PUBLIC_BASE_URL required", file=sys.stderr)
        return 2

    token = (os.getenv("BAUPASS_SMOKE_TOKEN") or "").strip() or None
    report = run_smoke(args.base_url, token)

    if args.json_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"E2E smoke: {report['passed']}/{report['total']} — max {report['maxLatencyMs']}ms")
        for c in report["checks"]:
            mark = "OK" if c["ok"] else "FAIL"
            print(f"  [{mark}] {c['name']} {c.get('detail', '')}")
        print(f"Overall: {'PASS' if report['ok'] else 'FAIL'}")

    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
