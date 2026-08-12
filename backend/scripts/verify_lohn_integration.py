"""One-shot integration probe (run on Railway web service with env vars)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def _get(url: str, headers: dict[str, str], timeout: float = 15) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), json.loads(raw) if raw.strip().startswith("{") else {"raw": raw[:200]}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw.strip().startswith("{") else {"raw": raw[:200]}
        except Exception:
            body = {"raw": raw[:200]}
        return int(exc.code), body


def _post(url: str, headers: dict[str, str], body: dict, timeout: float = 15) -> tuple[int, dict]:
    raw = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=raw, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return int(resp.status), json.loads(text) if text.strip().startswith("{") else {"raw": text[:200]}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw.strip().startswith("{") else {"raw": raw[:200]}
        except Exception:
            parsed = {"raw": raw[:200]}
        return int(exc.code), parsed


def main() -> int:
    lohn = (os.environ.get("WORKPASS_ACCOUNTING_BASE_URL") or "https://workpass-lohn.up.railway.app").rstrip("/")
    platform = (os.environ.get("PUBLIC_BASE_URL") or "https://suppix-ai-workpass.com").rstrip("/")
    api_key = (os.environ.get("WORKPASS_API_KEY") or "").strip()
    webhook_key = (os.environ.get("WORKPASS_PLATFORM_WEBHOOK_KEY") or "").strip()
    company = (os.environ.get("VERIFY_LOHN_COMPANY_ID") or "cmp-cd3c66a0b71a").strip()

    checks: list[dict] = []

    def record(name: str, ok: bool, **extra) -> None:
        checks.append({"name": name, "ok": ok, **extra})

    # Lohn health (no auth)
    st, health = _get(f"{lohn}/health", {"Accept": "application/json"})
    record(
        "lohn_health",
        st == 200 and bool(health.get("ok")),
        status=st,
        webhookConfigured=health.get("webhookConfigured"),
        lastWebhookOk=((health.get("lastWebhook") or {}).get("ok")),
        lastWebhookStatus=((health.get("lastWebhook") or {}).get("status")),
    )

  # Lohn API auth
    if api_key:
        hdr = {
            "X-WorkPass-Key": api_key,
            "X-WorkPass-Company-Id": company,
            "Accept": "application/json",
        }
        st, pending = _get(f"{lohn}/v1/messages/pending?companyId={company}", hdr)
        msgs = pending.get("messages") or pending.get("items") or []
        record("lohn_messages_pending", st == 200 and pending.get("ok", True), status=st, count=len(msgs))
    else:
        record("lohn_messages_pending", False, error="WORKPASS_API_KEY missing")

    # Platform webhook inbound (Lohn → Platform direction)
    if webhook_key:
        wh_url = f"{platform}/api/workpass/webhooks/accounting"
        wh_hdr = {
            "Content-Type": "application/json",
            "X-WorkPass-Webhook-Key": webhook_key,
            "Authorization": f"Bearer {webhook_key}",
            "X-WorkPass-Company-Id": company,
        }
        st, wh = _post(
            wh_url,
            wh_hdr,
            {"event": "platform.ping", "companyId": company},
        )
        record(
            "platform_webhook_ping",
            st == 200 and wh.get("ok"),
            status=st,
            event=wh.get("event"),
            message=wh.get("message"),
        )
    else:
        record("platform_webhook_ping", False, error="WORKPASS_PLATFORM_WEBHOOK_KEY missing")

    # Platform → Lohn via app code (uses DB + env keys)
    try:
        from backend.app.platform.accounting.messages_inbox import pull_pending_messages_from_lohn
        from backend.app.platform.accounting.platform_link import get_platform_link, test_platform_link_connectivity
        from backend.server import get_db

        db = get_db()
        link = get_platform_link(db)
        record(
            "platform_link_configured",
            bool(link.get("enabled")) and bool(str(link.get("base_url") or "").strip()),
            masterSet=bool(str(link.get("master_api_key") or link.get("masterApiKeySet"))),
        )
        conn = test_platform_link_connectivity(db)
        record("platform_to_lohn_connectivity", bool(conn.get("ok")), **{k: conn.get(k) for k in ("status", "error", "message") if k in conn})
        pull = pull_pending_messages_from_lohn(db, company_id=company)
        record(
            "platform_pull_messages",
            bool(pull.get("ok")),
            pulled=pull.get("pulled"),
            pullStatus=((pull.get("pull") or {}).get("status")),
        )
    except Exception as exc:
        record("platform_internal", False, error=str(exc)[:200])

    ok_count = sum(1 for c in checks if c.get("ok"))
    summary = {"ok": ok_count == len(checks), "passed": ok_count, "total": len(checks), "checks": checks}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
