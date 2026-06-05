#!/usr/bin/env python3
"""Probe critical API routes before deploy (exit 1 if any required route is missing)."""
from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("BAUPASS_ENV", "testing")
os.environ["BAUPASS_ENABLE_BACKGROUND_JOBS"] = "0"
os.environ["BAUPASS_SKIP_IMAP_POLL"] = "1"

from backend.app.health.route_probe import CRITICAL_API_ROUTES, build_api_route_probe
from backend.server import _route_methods_for, app


def main() -> int:
    probe = build_api_route_probe(_route_methods_for)
    print(json.dumps(probe, indent=2, ensure_ascii=False))
    if probe.get("ok"):
        print(f"[probe_api] all {len(CRITICAL_API_ROUTES)} critical routes registered")
        return 0
    missing = probe.get("missing") or []
    print(f"[probe_api] FAIL: {len(missing)} route(s) missing", file=sys.stderr)
    for item in missing:
        print(
            f"  - {item.get('path')} requires {item.get('required')} got {item.get('available')}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
