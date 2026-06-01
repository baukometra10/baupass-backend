#!/usr/bin/env python3
"""
Create BauPass Stripe products/prices and print Railway env vars.

Usage:
  set STRIPE_SECRET_KEY=sk_test_...
  python backend/ops/setup_stripe_products.py
  python backend/ops/setup_stripe_products.py --dry-run

Optional:
  BAUPASS_STRIPE_TRIAL_DAYS=14   (default: 14, set 0 to disable checkout trial)
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
    parser = argparse.ArgumentParser(description="Bootstrap BauPass Stripe catalog")
    parser.add_argument("--dry-run", action="store_true", help="Preview without Stripe API calls")
    args = parser.parse_args()

    key = (os.getenv("STRIPE_SECRET_KEY") or "").strip()
    if not key and not args.dry_run:
        print("ERROR: Set STRIPE_SECRET_KEY (sk_test_... or sk_live_...)", file=sys.stderr)
        print("", file=sys.stderr)
        print("Example:", file=sys.stderr)
        print("  set STRIPE_SECRET_KEY=sk_test_xxx", file=sys.stderr)
        print("  python backend/ops/setup_stripe_products.py", file=sys.stderr)
        return 1

    from backend.app.domains.billing import stripe_service

    try:
        result = stripe_service.bootstrap_stripe_catalog(dry_run=args.dry_run)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("")
    print("# ── Add to Railway Variables ──")
    for name, value in (result.get("env") or {}).items():
        print(f"{name}={value}")
    print("")
    print(f"# Checkout trial: {result.get('trialDays', 14)} days (BAUPASS_STRIPE_TRIAL_DAYS)")
    print("# Webhook: POST /api/billing/stripe/webhook")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
