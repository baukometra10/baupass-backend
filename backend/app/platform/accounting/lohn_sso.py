"""WorkPass Lohn SSO handoff — one-time ticket + remote magic-link + form bridge."""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode

from . import repository as repo
from .platform_link import _post_lohn_json, get_platform_link

SSO_API_PATHS = (
    "/v1/auth/platform-sso",
    "/v1/company/sso",
    "/api/v1/auth/platform-sso",
)
TICKET_TTL_SEC = 90


def _ensure_sso_tickets(db) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS workpass_lohn_sso_tickets (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            actor_user_id TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            consumed_at REAL
        )
        """
    )
    try:
        db.commit()
    except Exception:
        pass


def _lohn_email(company_id: str) -> str:
    return f"{company_id}@firma.de"


def _parse_lohn_json(result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result.get("json"), dict):
        return result["json"]
    raw = result.get("body") or ""
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _extract_sso_url(payload: dict[str, Any]) -> str:
    for key in ("url", "ssoUrl", "redirectUrl", "loginUrl", "magicLink"):
        val = str(payload.get(key) or "").strip()
        if val.startswith("http://") or val.startswith("https://"):
            return val
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for key in ("url", "ssoUrl", "redirectUrl"):
        val = str(data.get(key) or "").strip()
        if val.startswith("http://") or val.startswith("https://"):
            return val
    return ""


def mint_sso_ticket(db, *, company_id: str, actor_user_id: str = "") -> str:
    _ensure_sso_tickets(db)
    ticket_id = secrets.token_urlsafe(24)
    now = time.time()
    db.execute(
        """
        INSERT INTO workpass_lohn_sso_tickets
        (id, company_id, actor_user_id, created_at, expires_at, consumed_at)
        VALUES (?, ?, ?, ?, ?, NULL)
        """,
        (ticket_id, company_id, str(actor_user_id or ""), now, now + TICKET_TTL_SEC),
    )
    db.commit()
    return ticket_id


def consume_sso_ticket(db, ticket_id: str) -> dict[str, Any] | None:
    _ensure_sso_tickets(db)
    ticket_id = (ticket_id or "").strip()
    if not ticket_id:
        return None
    row = db.execute(
        "SELECT * FROM workpass_lohn_sso_tickets WHERE id = ?",
        (ticket_id,),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    now = time.time()
    if data.get("consumed_at") is not None:
        return None
    if float(data.get("expires_at") or 0) < now:
        return None
    db.execute(
        "UPDATE workpass_lohn_sso_tickets SET consumed_at = ? WHERE id = ?",
        (now, ticket_id),
    )
    db.commit()
    return data


def build_signed_handoff_url(
    link: dict[str, Any],
    *,
    company_id: str,
    email: str,
    actor_user_id: str = "",
) -> str:
    """HMAC handoff Lohn can verify with the shared master key (no password in browser)."""
    base = str(link.get("base_url") or "").rstrip("/")
    master = str(link.get("master_api_key") or "").strip()
    if not base or not master:
        return ""
    exp = int(time.time()) + TICKET_TTL_SEC
    nonce = secrets.token_hex(12)
    msg = f"{company_id}.{email}.{exp}.{nonce}".encode("utf-8")
    sig = hmac.new(master.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    query = urlencode(
        {
            "companyId": company_id,
            "email": email,
            "exp": str(exp),
            "nonce": nonce,
            "sig": sig,
            "source": "suppix",
            "actorUserId": actor_user_id or "",
        }
    )
    return f"{base}/sso?{query}"


def request_lohn_sso_url(
    link: dict[str, Any],
    *,
    company_id: str,
    login: dict[str, Any],
    actor_user_id: str = "",
) -> dict[str, Any]:
    """Ask WorkPass Lohn for a one-time login URL (server-to-server, master key)."""
    email = _lohn_email(company_id)
    username = str(login.get("username") or "").strip()
    password = str(login.get("password") or "")
    body = {
        "companyId": company_id,
        "firmaId": company_id,
        "id": company_id,
        "email": email,
        "username": username,
        "password": password,
        "login": {"email": email, "username": username, "password": password},
        "actorUserId": actor_user_id or "",
        "source": "suppix",
        "product": "WorkPass Lohn",
        "exp": int(time.time()) + TICKET_TTL_SEC,
        "nonce": secrets.token_hex(12),
    }
    last: dict[str, Any] = {"ok": False, "error": "sso_unsupported"}
    for path in SSO_API_PATHS:
        result = _post_lohn_json(link, path=path, body=body, event="auth.platform-sso", timeout=12)
        parsed = _parse_lohn_json(result)
        # Attach parsed for callers that inspect body only
        if parsed and "json" not in result:
            result = {**result, "json": parsed}
        url = _extract_sso_url(parsed) if result.get("ok") else ""
        if url:
            return {"ok": True, "url": url, "path": path, "status": result.get("status")}
        last = {**result, "path": path, "parsed": parsed}
        # 404/405 → try next path; other auth errors → stop
        status = int(result.get("status") or 0)
        if status and status not in {404, 405, 501} and not result.get("ok"):
            break
    return {"ok": False, "error": last.get("error") or "sso_unsupported", "detail": last}


def _login_form_path(link: dict[str, Any]) -> str:
    path = str(link.get("sso_login_path") or link.get("ssoLoginPath") or "/login").strip() or "/login"
    if not path.startswith("/"):
        path = "/" + path
    return path


def render_auto_login_html(
    *,
    action_url: str,
    email: str,
    username: str,
    password: str,
    company_id: str,
) -> str:
    """Browser navigates to Lohn origin via POST so cookies can be set on Lohn domain."""
    e_email = html.escape(email, quote=True)
    e_user = html.escape(username, quote=True)
    e_pass = html.escape(password, quote=True)
    e_cid = html.escape(company_id, quote=True)
    e_action = html.escape(action_url, quote=True)
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>WorkPass Lohn — Anmeldung</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0;
           display: grid; place-items: center; min-height: 100vh; margin: 0; }}
    .box {{ text-align: center; padding: 1.5rem; }}
    .spin {{ width: 28px; height: 28px; border: 3px solid #334155; border-top-color: #38bdf8;
             border-radius: 50%; margin: 0 auto 1rem; animation: s 0.7s linear infinite; }}
    @keyframes s {{ to {{ transform: rotate(360deg); }} }}
    noscript p {{ color: #fbbf24; }}
  </style>
</head>
<body>
  <div class="box">
    <div class="spin" aria-hidden="true"></div>
    <p>Anmeldung bei WorkPass Lohn…</p>
    <noscript><p>JavaScript deaktiviert — Formular unten absenden.</p></noscript>
  </div>
  <form id="sso" method="post" action="{e_action}" style="display:none">
    <input type="hidden" name="email" value="{e_email}"/>
    <input type="hidden" name="username" value="{e_user}"/>
    <input type="hidden" name="password" value="{e_pass}"/>
    <input type="hidden" name="companyId" value="{e_cid}"/>
    <input type="hidden" name="firmaId" value="{e_cid}"/>
    <input type="hidden" name="source" value="suppix"/>
    <button type="submit">Anmelden</button>
  </form>
  <script>document.getElementById("sso").submit();</script>
</body>
</html>"""


def build_launch_payload(
    db,
    *,
    company_id: str,
    actor_user_id: str = "",
    public_base: str = "",
) -> dict[str, Any]:
    """
    Prefer remote Lohn magic-link; else platform SSO bridge (ticket → form / signed /sso).
    Never puts passwords into the JSON response — only into the one-time enter page.
    """
    link = get_platform_link(db)
    base = str(link.get("base_url") or "").rstrip("/")
    if not base or not link.get("enabled"):
        return {
            "ok": False,
            "error": "lohn_base_url_missing",
            "message": "Buchhaltungs-Domain fehlt. Superadmin muss die Lohn-URL unter Plattform speichern.",
        }

    login = repo.get_lohn_login(db, company_id)
    email = _lohn_email(company_id)
    plain_sep = "&" if "?" in base else "?"
    plain_url = f"{base}{plain_sep}company_id={company_id}&source=suppix"

    if login:
        remote = request_lohn_sso_url(
            link,
            company_id=company_id,
            login=login,
            actor_user_id=actor_user_id,
        )
        if remote.get("ok") and remote.get("url"):
            return {
                "ok": True,
                "url": remote["url"],
                "baseUrl": base,
                "companyId": company_id,
                "mode": "lohn_sso",
                "sso": True,
                "message": "SSO-Link von WorkPass Lohn.",
            }

    # Bridge: browser hits platform once, then auto-logs into Lohn (or signed /sso).
    ticket = mint_sso_ticket(db, company_id=company_id, actor_user_id=actor_user_id)
    pub = (public_base or str(link.get("platform_public_url") or "")).rstrip("/")
    if not pub:
        # Relative path still works when admin UI and API share the same origin.
        bridge_url = f"/api/payroll/accounting/sso-enter?ticket={ticket}"
    else:
        bridge_url = f"{pub}/api/payroll/accounting/sso-enter?ticket={ticket}"

    handoff = ""
    if login and str(link.get("master_api_key") or "").strip():
        handoff = build_signed_handoff_url(
            link,
            company_id=company_id,
            email=email,
            actor_user_id=actor_user_id,
        )

    if login:
        return {
            "ok": True,
            "url": bridge_url,
            "baseUrl": base,
            "companyId": company_id,
            "mode": "sso_bridge",
            "sso": True,
            "handoffUrl": handoff or None,
            "fallbackUrl": plain_url,
            "message": "SSO-Übergabe (einmaliges Ticket).",
        }

    return {
        "ok": True,
        "url": plain_url,
        "baseUrl": base,
        "companyId": company_id,
        "mode": "open",
        "sso": False,
        "message": "Kein gespeichertes Lohn-Login — Domain wird geöffnet. Bitte Firma neu provisionieren.",
    }


def resolve_sso_enter(db, ticket_id: str) -> dict[str, Any]:
    """
    Consume ticket and return either redirect URL or HTML auto-login.
    Keys: ok, redirect, html, error, message
    """
    ticket = consume_sso_ticket(db, ticket_id)
    if not ticket:
        return {
            "ok": False,
            "error": "invalid_or_expired_ticket",
            "message": "SSO-Ticket ungültig oder abgelaufen. Bitte erneut über SUPPIX öffnen.",
        }
    company_id = str(ticket.get("company_id") or "")
    actor = str(ticket.get("actor_user_id") or "")
    link = get_platform_link(db)
    base = str(link.get("base_url") or "").rstrip("/")
    login = repo.get_lohn_login(db, company_id)
    if not login or not base:
        sep = "&" if "?" in base else "?"
        return {
            "ok": True,
            "redirect": f"{base}{sep}company_id={company_id}&source=suppix" if base else "",
            "mode": "open",
        }

    remote = request_lohn_sso_url(link, company_id=company_id, login=login, actor_user_id=actor)
    if remote.get("ok") and remote.get("url"):
        return {"ok": True, "redirect": remote["url"], "mode": "lohn_sso"}

    email = _lohn_email(company_id)
    # Prefer form POST to Lohn login path (sets session cookies on Lohn origin).
    action = f"{base}{_login_form_path(link)}"
    html_page = render_auto_login_html(
        action_url=action,
        email=email,
        username=str(login.get("username") or ""),
        password=str(login.get("password") or ""),
        company_id=company_id,
    )
    return {
        "ok": True,
        "html": html_page,
        "mode": "form_bridge",
        "handoffUrl": build_signed_handoff_url(
            link, company_id=company_id, email=email, actor_user_id=actor
        )
        or None,
    }
