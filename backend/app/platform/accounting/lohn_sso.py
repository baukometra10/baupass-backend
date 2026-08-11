"""WorkPass Lohn SSO handoff — magic-link via master key; never open bare API in browser."""
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

# Paths Lohn may expose for one-time browser session (called server-side with X-WorkPass-Key).
SSO_API_PATHS = (
    "/v1/auth/platform-sso",
    "/v1/company/sso",
    "/v1/auth/sso",
    "/v1/auth/login",
    "/v1/company/login",
    "/v1/login",
    "/api/v1/auth/platform-sso",
    "/api/auth/platform-sso",
    "/api/auth/login",
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


def _browser_base(link: dict[str, Any]) -> str:
    """UI host for the browser — never confuse with API-only base when ui_base_url is set."""
    ui = str(link.get("ui_base_url") or link.get("uiBaseUrl") or "").strip().rstrip("/")
    if ui:
        return ui
    return str(link.get("base_url") or "").rstrip("/")


def _extract_sso_url(payload: dict[str, Any], *, browser_base: str = "") -> str:
    for key in ("url", "ssoUrl", "redirectUrl", "loginUrl", "magicLink", "sessionUrl"):
        val = str(payload.get(key) or "").strip()
        if val.startswith("http://") or val.startswith("https://"):
            return val
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for key in ("url", "ssoUrl", "redirectUrl", "token"):
        val = str(data.get(key) or "").strip()
        if val.startswith("http://") or val.startswith("https://"):
            return val
    token = str(
        payload.get("token")
        or payload.get("accessToken")
        or payload.get("sessionToken")
        or data.get("token")
        or ""
    ).strip()
    if token and browser_base:
        q = urlencode({"token": token, "source": "suppix"})
        return f"{browser_base}/#/sso?{q}"
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
    """HMAC handoff for Lohn UI host (not API-only root)."""
    base = _browser_base(link)
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
    # Prefer hash route (SPA) then /sso
    return f"{base}/#/sso?{query}"


def request_lohn_sso_url(
    link: dict[str, Any],
    *,
    company_id: str,
    login: dict[str, Any],
    actor_user_id: str = "",
) -> dict[str, Any]:
    """Ask WorkPass Lohn for a one-time browser URL (server-to-server, master key)."""
    email = _lohn_email(company_id)
    username = str(login.get("username") or "").strip()
    password = str(login.get("password") or "")
    browser_base = _browser_base(link)
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
        if parsed and "json" not in result:
            result = {**result, "json": parsed}
        # Accept URL even when HTTP ok=false but body still contains a session link
        url = _extract_sso_url(parsed, browser_base=browser_base)
        if url and (result.get("ok") or parsed.get("ok") is True or parsed.get("token") or parsed.get("url")):
            return {"ok": True, "url": url, "path": path, "status": result.get("status")}
        if result.get("ok") and url:
            return {"ok": True, "url": url, "path": path, "status": result.get("status")}
        last = {**result, "path": path, "parsed": parsed}
        status = int(result.get("status") or 0)
        # Keep trying on missing routes; stop early only on hard auth failure to master key
        err = str(result.get("error") or parsed.get("error") or "")
        if status in {401, 403} and "X-WorkPass-Key" in err and not str(link.get("master_api_key") or "").strip():
            break
        if status and status not in {404, 405, 501} and status >= 500:
            break
    return {"ok": False, "error": last.get("error") or "sso_unsupported", "detail": last}


def build_ui_login_url(link: dict[str, Any], *, company_id: str, email: str) -> str:
    """GET URL for dedicated Lohn UI host (not API-only root)."""
    if not _has_dedicated_ui(link):
        return ""
    base = _browser_base(link)
    if not base:
        return ""
    q = urlencode(
        {
            "email": email,
            "companyId": company_id,
            "firmaId": company_id,
            "source": "suppix",
        }
    )
    ui_path = str(link.get("sso_login_path") or link.get("ssoLoginPath") or "").strip()
    if ui_path:
        if not ui_path.startswith("/") and not ui_path.startswith("#"):
            ui_path = "/" + ui_path
        if ui_path.startswith("#"):
            return f"{base}/{ui_path}?{q}" if "?" not in ui_path else f"{base}/{ui_path}&{q}"
        return f"{base}{ui_path}{'&' if '?' in ui_path else '?'}{q}"
    return f"{base}/#/login?{q}"


def _has_dedicated_ui(link: dict[str, Any]) -> bool:
    return bool(str(link.get("ui_base_url") or link.get("uiBaseUrl") or "").strip())


def render_sso_help_html(
    *,
    ui_url: str,
    email: str,
    message: str,
) -> str:
    e_url = html.escape(ui_url, quote=True) if ui_url else ""
    e_email = html.escape(email)
    e_msg = html.escape(message)
    link_html = (
        f'<p><a href="{e_url}">WorkPass Lohn öffnen</a></p>'
        f"<script>location.replace({json.dumps(ui_url)});</script>"
        if ui_url
        else ""
    )
    refresh = f'<meta http-equiv="refresh" content="0;url={e_url}"/>' if ui_url else ""
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  {refresh}
  <title>WorkPass Lohn</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0;
           display: grid; place-items: center; min-height: 100vh; margin: 0; padding: 1.5rem; }}
    .box {{ max-width: 32rem; text-align: center; line-height: 1.45; }}
    a {{ color: #38bdf8; }}
    .muted {{ color: #94a3b8; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <div class="box">
    <p>{e_msg}</p>
    <p class="muted">Login-E-Mail: <strong>{e_email}</strong></p>
    {link_html}
  </div>
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
    Prefer remote Lohn magic-link (server + master key).
    Fallback: platform ticket → dedicated UI host. Never open API-only root in the browser.
    """
    link = get_platform_link(db)
    api_base = str(link.get("base_url") or "").rstrip("/")
    if not api_base or not link.get("enabled"):
        return {
            "ok": False,
            "error": "lohn_base_url_missing",
            "message": "Buchhaltungs-Domain fehlt. Superadmin muss die Lohn-URL unter Plattform speichern.",
        }

    login = repo.get_lohn_login(db, company_id)
    email = _lohn_email(company_id)

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
                "baseUrl": api_base,
                "companyId": company_id,
                "mode": "lohn_sso",
                "sso": True,
                "message": "SSO-Link von WorkPass Lohn.",
            }

    ticket = mint_sso_ticket(db, company_id=company_id, actor_user_id=actor_user_id)
    pub = (public_base or str(link.get("platform_public_url") or "")).rstrip("/")
    bridge_url = (
        f"{pub}/api/payroll/accounting/sso-enter?ticket={ticket}"
        if pub
        else f"/api/payroll/accounting/sso-enter?ticket={ticket}"
    )
    ui_url = build_ui_login_url(link, company_id=company_id, email=email)

    return {
        "ok": True,
        "url": bridge_url,
        "baseUrl": api_base,
        "uiUrl": ui_url or None,
        "companyId": company_id,
        "mode": "sso_bridge",
        "sso": True,
        "fallbackUrl": ui_url or None,
        "message": "SSO-Übergabe (einmaliges Ticket).",
        "needsUiUrl": not _has_dedicated_ui(link),
    }


def resolve_sso_enter(db, ticket_id: str) -> dict[str, Any]:
    """
    Consume ticket → magic-link or dedicated UI host.
    Never navigates the browser to an API-only Lohn base (JSON X-WorkPass-Key).
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
    login = repo.get_lohn_login(db, company_id)
    email = _lohn_email(company_id)

    if login:
        remote = request_lohn_sso_url(link, company_id=company_id, login=login, actor_user_id=actor)
        if remote.get("ok") and remote.get("url"):
            return {"ok": True, "redirect": remote["url"], "mode": "lohn_sso"}

    if _has_dedicated_ui(link):
        handoff = build_signed_handoff_url(
            link, company_id=company_id, email=email, actor_user_id=actor
        )
        target = handoff or build_ui_login_url(link, company_id=company_id, email=email)
        return {
            "ok": True,
            "redirect": target,
            "html": render_sso_help_html(
                ui_url=target,
                email=email,
                message="Weiterleitung zu WorkPass Lohn…",
            ),
            "mode": "ui_login",
        }

    msg = (
        "WorkPass Lohn API verlangt den Header X-WorkPass-Key — die API-URL kann nicht im Browser geöffnet werden. "
        "Bitte unter Plattform → WorkPass Lohn die «UI-URL» (Browser-App) speichern, "
        "oder in Lohn den Endpoint POST /v1/auth/platform-sso freischalten."
    )
    return {
        "ok": True,
        "html": render_sso_help_html(ui_url="", email=email, message=msg),
        "mode": "needs_ui_url",
    }
