#!/usr/bin/env python3
"""Verify Railway HA posture via public health/capability endpoints.

Usage:
  python backend/ops/railway_ha_verify.py --base-url https://your-app.up.railway.app
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def _get(url: str, timeout: float = 25.0) -> tuple[int, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            try:
                return int(resp.status), json.loads(raw)
            except Exception:
                return int(resp.status), {"raw": raw[:500]}
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")[:500]
        except Exception:
            pass
        return int(exc.code), {"error": str(exc), "body": body}
    except Exception as exc:
        return 0, {"error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Railway HA cutover verifier")
    parser.add_argument("--base-url", required=True, help="Public app base URL")
    parser.add_argument("--min-ha-score", type=int, default=95)
    args = parser.parse_args()
    base = str(args.base_url).rstrip("/")

    checks = [
        ("ready", f"{base}/api/health/ready"),
        ("queues", f"{base}/api/health/queues"),
        ("dr", f"{base}/api/health/dr"),
        ("capabilities", f"{base}/api/platform/capabilities"),
    ]
    results: dict[str, Any] = {}
    failed = False
    for name, url in checks:
        status, payload = _get(url)
        ok = 200 <= status < 300
        results[name] = {"http": status, "ok": ok, "payload": payload}
        mark = "OK" if ok else "FAIL"
        print(f"[{mark}] {name} HTTP {status}")
        if not ok:
            failed = True

    caps = results.get("capabilities", {}).get("payload") or {}
    ha = caps.get("ha") if isinstance(caps, dict) else None
    if not isinstance(ha, dict):
        # Some builds nest under capabilities.platform
        platform = caps.get("platform") if isinstance(caps, dict) else None
        ha = (platform or {}).get("ha") if isinstance(platform, dict) else {}
    score = int((ha or {}).get("score") or 0)
    level = str((ha or {}).get("level") or "")
    print(f"[INFO] ha.score={score} level={level}")
    if score < int(args.min_ha_score):
        print(f"[FAIL] ha.score < {args.min_ha_score} — complete Postgres/Redis/worker/replicas/S3 cutover")
        failed = True
    else:
        print(f"[OK] ha.score >= {args.min_ha_score}")

    # Soft hints for DR / queues
    queues = results.get("queues", {}).get("payload") or {}
    if isinstance(queues, dict) and queues.get("ok") is False:
        print("[WARN] queues report not ok — ensure dedicated RQ worker")
    dr = results.get("dr", {}).get("payload") or {}
    if isinstance(dr, dict) and dr.get("ok") is False:
        print("[WARN] DR posture not ok")

    print(json.dumps({"failed": failed, "haScore": score, "haLevel": level}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
