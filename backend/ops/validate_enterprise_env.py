#!/usr/bin/env python3
"""
Enterprise go-live validation — env vars + optional live HTTP checks (no secrets printed).

Usage:
  python backend/ops/validate_enterprise_env.py
  python backend/ops/validate_enterprise_env.py --base-url https://baupass-production.up.railway.app
  python backend/ops/validate_enterprise_env.py --strict
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib import request as urlrequest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.platform_env import mirror_platform_env, platform_env  # noqa: E402

mirror_platform_env()

_WEAK_SECRET_PATTERNS = (
    r"^change-me",
    r"^secret$",
    r"^test$",
    r"^1234",
    r"^password",
)


def _fetch_json(url: str, timeout: int = 25) -> tuple[int, dict]:
    req = urlrequest.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode() or "{}")


def _present(name: str) -> bool:
    suffix = name
    for prefix in ("SUPPIX_", "BAUPASS_"):
        if suffix.startswith(prefix):
            suffix = suffix[len(prefix) :]
            break
    return bool(platform_env(suffix))


def _weak_secret(name: str, min_len: int = 24) -> str | None:
    suffix = name
    for prefix in ("SUPPIX_", "BAUPASS_"):
        if suffix.startswith(prefix):
            suffix = suffix[len(prefix) :]
            break
    raw = platform_env(suffix)
    if not raw:
        return None
    if len(raw) < min_len:
        return "too_short"
    low = raw.lower()
    for pat in _WEAK_SECRET_PATTERNS:
        if re.search(pat, low):
            return "weak_placeholder"
    return None


def _check_env() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    hosted = bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RENDER")
        or (os.getenv("PUBLIC_BASE_URL") or "").strip()
    )

    def add(
        key: str,
        *,
        ok: bool,
        severity: str = "critical",
        hint: str = "",
        value_hint: str = "",
    ) -> None:
        items.append(
            {
                "id": key,
                "ok": ok,
                "severity": severity,
                "hint": hint,
                "configured": value_hint or ("yes" if ok else "no"),
            }
        )

    # ── Security (critical) ─────────────────────────────────────────────
    for var, min_len in (
        ("SUPPIX_SECRET_KEY", 32),
        ("SUPPIX_AUDIT_SIGNING_KEY", 24),
    ):
        weak = _weak_secret(var, min_len)
        add(
            var,
            ok=_present(var) and not weak,
            hint="Generate long random strings; never use change-me in production.",
            value_hint="weak" if weak else ("set" if _present(var) else "missing"),
        )

    add(
        "SUPPIX_DB_PATH",
        ok=_present("SUPPIX_DB_PATH"),
        hint="Mount Railway volume at /data and set SUPPIX_DB_PATH=/data/baupass.db",
    )

    if hosted:
        add(
            "SUPPIX_ALLOW_DEMO",
            ok=not _present("SUPPIX_ALLOW_DEMO")
            or platform_env("ALLOW_DEMO", "").lower() in {"0", "false", "no", "off"},
            severity="critical",
            hint="Demo seed must stay off on production (omit or SUPPIX_ALLOW_DEMO=0).",
            value_hint=platform_env("ALLOW_DEMO", "unset"),
        )

    add(
        "PUBLIC_BASE_URL",
        ok=_present("PUBLIC_BASE_URL"),
        severity="critical" if hosted else "recommended",
        hint="HTTPS URL of the Railway service — used in emails and deep links.",
    )

    # ── Redis / jobs (recommended for enterprise) ─────────────────────────
    redis_ok = _present("REDIS_URL")
    add("REDIS_URL", ok=redis_ok, severity="recommended", hint="Railway Redis + worker service.")
    if redis_ok:
        rq_modes = [
            platform_env("DAILY_JOBS_MODE", "inline"),
            platform_env("DUNNING_MODE", "inline"),
        ]
        add(
            "SUPPIX_*_JOBS_MODE=rq",
            ok=all(m == "rq" for m in rq_modes),
            severity="recommended",
            hint="Set SUPPIX_DAILY_JOBS_MODE=rq and SUPPIX_DUNNING_MODE=rq with a worker process.",
            value_hint=",".join(rq_modes),
        )

    # ── Hybrid push (critical for worker app) ───────────────────────────
    fcm_v1 = _present("FCM_PROJECT_ID") and (
        _present("FCM_SERVICE_ACCOUNT_JSON") or _present("FCM_SERVICE_ACCOUNT_B64")
    )
    fcm_legacy = _present("FCM_SERVER_KEY") or _present("FIREBASE_SERVER_KEY")
    fcm_ok = fcm_v1 or fcm_legacy
    add(
        "FCM (v1 preferred)",
        ok=fcm_ok,
        severity="critical",
        hint="FCM_PROJECT_ID + FCM_SERVICE_ACCOUNT_JSON (or B64); set FCM_V1_ONLY=1 after test.",
        value_hint="v1" if fcm_v1 else ("legacy" if fcm_legacy else "missing"),
    )
    if fcm_v1 and _present("FCM_V1_ONLY"):
        add("FCM_V1_ONLY", ok=True, severity="recommended", value_hint="enabled")

    def _turn_configured() -> bool:
        if _present("ICE_SERVERS_JSON"):
            raw = platform_env("ICE_SERVERS_JSON")
            try:
                parsed = json.loads(raw)
                return isinstance(parsed, list) and len(parsed) > 0
            except Exception:
                return False
        return _present("TURN_URL") and _present("TURN_USERNAME") and _present("TURN_PASSWORD")

    turn_ok = _turn_configured()
    add(
        "WebRTC TURN (voice calls)",
        ok=turn_ok,
        severity="recommended",
        hint="Set SUPPIX_TURN_URL + USERNAME + PASSWORD or SUPPIX_ICE_SERVERS_JSON for reliable voice on mobile networks.",
        value_hint="configured" if turn_ok else "stun-only",
    )

    add(
        "SUPPIX_WORKER_APK_URL",
        ok=_present("SUPPIX_WORKER_APK_URL"),
        severity="recommended",
        hint="Hosted APK for join.html hybrid distribution.",
    )
    add(
        "SUPPIX_TESTFLIGHT_URL",
        ok=_present("SUPPIX_TESTFLIGHT_URL"),
        severity="recommended",
        hint="TestFlight invite link for iPhone worker app (join.html).",
    )
    weak_jwt = _weak_secret("SUPPIX_WORKER_JWT_SECRET", 32)
    add(
        "SUPPIX_WORKER_JWT_SECRET",
        ok=_present("SUPPIX_WORKER_JWT_SECRET") and not weak_jwt,
        severity="critical" if hosted else "recommended",
        hint="Worker session JWT signing — 32+ random chars; do not rely on dev fallback.",
        value_hint="weak" if weak_jwt else ("set" if _present("SUPPIX_WORKER_JWT_SECRET") else "missing"),
    )

    weak_field = _weak_secret("SUPPIX_FIELD_ENCRYPTION_KEY", 32)
    add(
        "SUPPIX_FIELD_ENCRYPTION_KEY",
        ok=_present("SUPPIX_FIELD_ENCRYPTION_KEY") and not weak_field,
        severity="critical" if hosted else "recommended",
        hint="Encrypts chat messages at rest (per-tenant key). Set BAUPASS_FIELD_ENCRYPTION_KEY on Railway.",
        value_hint="weak" if weak_field else ("set" if _present("SUPPIX_FIELD_ENCRYPTION_KEY") else "missing"),
    )

    # ── AI / Copilot ────────────────────────────────────────────────────
    openai_ok = _present("OPENAI_API_KEY")
    add(
        "OPENAI_API_KEY",
        ok=openai_ok,
        severity="recommended",
        hint="Required for KI Command Center, Ops Copilot, and agent tools.",
    )
    if openai_ok:
        weak = _weak_secret("OPENAI_API_KEY", 20)
        if weak:
            items[-1]["ok"] = False
            items[-1]["value_hint"] = "weak"

    # ── Stripe billing ────────────────────────────────────────────────────
    stripe_key = _present("STRIPE_SECRET_KEY")
    add(
        "STRIPE_SECRET_KEY",
        ok=stripe_key,
        severity="recommended",
        hint="Stripe secret key (sk_test_ or sk_live_) for subscription checkout.",
    )
    add(
        "STRIPE_WEBHOOK_SECRET",
        ok=_present("STRIPE_WEBHOOK_SECRET"),
        severity="recommended",
        hint="Webhook signing secret (whsec_) — endpoint /api/billing/stripe/webhook",
    )
    try:
        from backend.app.platform.pricing import resolve_stripe_price_id

        for plan in ("starter", "professional", "enterprise"):
            add(
                f"STRIPE_PRICE_{plan.upper()}",
                ok=bool(resolve_stripe_price_id(plan, annual=False)),
                severity="recommended",
                hint=f"Run: python backend/ops/setup_stripe_products.py",
            )
    except Exception:
        pass
    add(
        "SUPPIX_STRIPE_TRIAL_DAYS",
        ok=_present("SUPPIX_STRIPE_TRIAL_DAYS") or True,
        severity="recommended",
        hint="Checkout trial length in days (default 14). Set 0 to disable.",
        value_hint=platform_env("STRIPE_TRIAL_DAYS", "14 (default)"),
    )

    # ── Email ─────────────────────────────────────────────────────────────
    smtp_ok = _present("SMTP_HOST") and _present("SMTP_PASSWORD")
    add(
        "SMTP",
        ok=smtp_ok,
        severity="recommended",
        hint="Brevo/Gmail SMTP for invoices, leave, and alerts.",
    )

    add(
        "SUPPIX_CONTACT_EMAIL",
        ok=_present("SUPPIX_CONTACT_EMAIL") or _present("VAPID_EMAIL"),
        severity="recommended",
        hint="Used for Web Push (legacy PWA) and operational contact — not admin@example.com.",
    )

    # ── Observability ───────────────────────────────────────────────────
    add("SENTRY_DSN", ok=_present("SENTRY_DSN"), severity="recommended")
    add(
        "SUPPIX_BACKUP_ON_BOOT",
        ok=_present("SUPPIX_BACKUP_ON_BOOT"),
        severity="recommended",
        hint="Automatic DB backup when persistent volume is mounted.",
    )

    # ── Enterprise runtime flags ────────────────────────────────────────
    try:
        from backend.app.core.enterprise_mode import demo_features_allowed, copilot_configured

        add(
            "enterprise.demoAllowed",
            ok=not demo_features_allowed() if hosted else True,
            severity="critical" if hosted else "info",
            hint="Production must not allow demo seed.",
            value_hint=str(demo_features_allowed()),
        )
        add(
            "enterprise.copilotConfigured",
            ok=copilot_configured(),
            severity="recommended",
            value_hint=str(copilot_configured()),
        )
    except Exception as exc:
        add("enterprise.flags", ok=False, hint=str(exc))

    critical = [i for i in items if i["severity"] == "critical"]
    recommended = [i for i in items if i["severity"] == "recommended"]
    crit_fail = [i for i in critical if not i["ok"]]
    rec_fail = [i for i in recommended if not i["ok"]]

    score = int(
        100
        * (
            sum(1 for i in items if i["ok"])
            / max(1, len(items))
        )
    )

    return {
        "hosted": hosted,
        "scorePercent": score,
        "summary": {
            "total": len(items),
            "passed": sum(1 for i in items if i["ok"]),
            "criticalFailed": len(crit_fail),
            "recommendedFailed": len(rec_fail),
        },
        "items": items,
        "criticalFailures": [i["id"] for i in crit_fail],
        "recommendedGaps": [i["id"] for i in rec_fail],
    }


def _check_http(base: str) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    endpoints = {
        "health": "/api/health",
        "ready": "/api/health/ready",
        "setupStatus": "/api/platform/setup-status",
        "workerMobileSetup": "/api/worker-app/mobile-setup",
    }
    ok = True
    for name, path in endpoints.items():
        url = f"{base.rstrip('/')}{path}"
        try:
            status, payload = _fetch_json(url)
            checks[name] = {"httpStatus": status, "ok": status == 200, "payload": payload}
            if status != 200:
                ok = False
            if name == "ready" and payload.get("status") != "ready":
                ok = False
            if name == "health":
                ent = payload.get("enterprise") or {}
                checks[name]["enterprise"] = ent
                if ent.get("demoAllowed") is True:
                    checks[name]["warning"] = "demoAllowed=true on live deployment"
                    ok = False
            if name == "setupStatus":
                rs = (payload.get("readyScore") or {})
                checks[name]["readyPercent"] = rs.get("percent")
                if rs.get("percent", 0) < 80:
                    checks[name]["warning"] = "setup score below 80%"
                    ok = False
                if (payload.get("enterprise") or {}).get("demoAllowed") is True:
                    ok = False
        except Exception as exc:
            checks[name] = {"ok": False, "error": str(exc)}
            ok = False
    return {"ok": ok, "baseUrl": base, "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate SUPPIX enterprise go-live readiness")
    parser.add_argument("--base-url", default=os.getenv("PUBLIC_BASE_URL", "").strip())
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any recommended check fails (not only critical)",
    )
    parser.add_argument(
        "--live-only",
        action="store_true",
        help="Skip local env checks; validate deployed API only (CI post-deploy).",
    )
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    env_report = _check_env() if not args.live_only else None
    result: dict[str, Any] = {"env": env_report, "live": None}

    if args.base_url:
        result["live"] = _check_http(args.base_url)

    env_ok = True if args.live_only else env_report["summary"]["criticalFailed"] == 0
    live_ok = result["live"]["ok"] if result.get("live") else True
    strict_ok = True
    if not args.live_only and args.strict:
        strict_ok = env_report["summary"]["recommendedFailed"] == 0

    result["ok"] = env_ok and live_ok and strict_ok
    result["tier"] = "enterprise_ready" if result["ok"] else "needs_work"

    if args.json_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("SUPPIX Enterprise Go-Live Validation")
        print("=" * 40)
        if env_report:
            print(
                f"Score: {env_report['scorePercent']}% "
                f"({env_report['summary']['passed']}/{env_report['summary']['total']} checks)"
            )
        elif args.live_only:
            print("Env checks skipped (--live-only)")
        if env_report and env_report["criticalFailures"]:
            print("\nCRITICAL (must fix):")
            for fid in env_report["criticalFailures"]:
                print(f"  - {fid}")
        if env_report and env_report["recommendedGaps"]:
            print("\nRECOMMENDED:")
            for fid in env_report["recommendedGaps"][:12]:
                print(f"  - {fid}")
            if len(env_report["recommendedGaps"]) > 12:
                print(f"  ... +{len(env_report['recommendedGaps']) - 12} more")
        if result.get("live"):
            print(f"\nLive HTTP: {'OK' if result['live']['ok'] else 'FAILED'} — {args.base_url}")
        print(f"\nOverall: {result['tier'].upper()} (ok={result['ok']})")
        print("\nFull JSON: re-run with --json-only")

    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
