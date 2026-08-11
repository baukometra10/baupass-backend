"""WorkPass Lohn SSO — public /v1/auth/login + HTML UI handoff (not API JSON)."""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import secrets
import time
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import quote, urlencode

from . import repository as repo
from .platform_link import _post_lohn_json, get_platform_link

# Master-key SSO (optional). Public company login is handled separately.
SSO_API_PATHS = (
    "/v1/auth/platform-sso",
    "/v1/company/sso",
    "/v1/auth/sso",
    "/api/v1/auth/platform-sso",
    "/api/auth/platform-sso",
)
TICKET_TTL_SEC = 90
_HTML_UI_CACHE: dict[str, tuple[float, bool]] = {}


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


def base_serves_html_ui(base_url: str) -> bool:
    """True when Lohn root returns an HTML shell (SPA), not API JSON Unauthorized."""
    base = (base_url or "").rstrip("/")
    if not base:
        return False
    now = time.time()
    cached = _HTML_UI_CACHE.get(base)
    if cached and cached[0] > now:
        return cached[1]
    ok = False
    req = urlrequest.Request(
        base + "/",
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "Mozilla/5.0 SUPPIX-Lohn-SSO/1.0",
        },
        method="GET",
    )
    try:
        with urlrequest.urlopen(req, timeout=10) as resp:
            ctype = str(resp.headers.get("Content-Type") or "").lower()
            body = resp.read(800).decode("utf-8", errors="replace").lower()
            ok = "text/html" in ctype or "<!doctype html" in body or "<html" in body
    except urlerror.HTTPError as exc:
        try:
            body = exc.read(400).decode("utf-8", errors="replace").lower()
        except Exception:
            body = ""
        ok = "<!doctype html" in body or "<html" in body
    except Exception:
        ok = False
    _HTML_UI_CACHE[base] = (now + 300, ok)
    return ok


def _browser_base(link: dict[str, Any]) -> str:
    ui = str(link.get("ui_base_url") or link.get("uiBaseUrl") or "").strip().rstrip("/")
    if ui:
        return ui
    api = str(link.get("base_url") or "").rstrip("/")
    if api and base_serves_html_ui(api):
        return api
    return api


def _has_browser_ui(link: dict[str, Any]) -> bool:
    if str(link.get("ui_base_url") or link.get("uiBaseUrl") or "").strip():
        return True
    api = str(link.get("base_url") or "").rstrip("/")
    return bool(api and base_serves_html_ui(api))


def _extract_sso_url(payload: dict[str, Any], *, browser_base: str = "") -> str:
    for key in ("url", "ssoUrl", "redirectUrl", "loginUrl", "magicLink", "sessionUrl"):
        val = str(payload.get(key) or "").strip()
        if val.startswith("http://") or val.startswith("https://"):
            return val
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for key in ("url", "ssoUrl", "redirectUrl"):
        val = str(data.get(key) or "").strip()
        if val.startswith("http://") or val.startswith("https://"):
            return val
    token = str(payload.get("session") or payload.get("token") or data.get("token") or "").strip()
    if token and browser_base:
        return build_session_handoff_url(
            browser_base,
            {
                "token": token,
                "expiresAt": payload.get("expiresAt") or data.get("expiresAt"),
                "user": payload.get("user") or data.get("user"),
                "via": payload.get("via") or "suppix",
            },
        )
    return ""


def build_session_handoff_url(browser_base: str, session_payload: dict[str, Any]) -> str:
    """
    Hand off session to Lohn SPA via hash fragment.
    Lohn auth-gate should consume #suppix-sso=… (see docs snippet).
    """
    base = (browser_base or "").rstrip("/")
    if not base or not session_payload.get("token"):
        return base
    blob = quote(json.dumps(session_payload, ensure_ascii=False, separators=(",", ":")), safe="")
    return f"{base}/#suppix-sso={blob}"


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
    return f"{base}/#/sso?{query}"


def login_lohn_company_session(
    link: dict[str, Any],
    *,
    company_id: str,
    login: dict[str, Any],
) -> dict[str, Any]:
    """
    Public company login used by Lohn SPA (no X-WorkPass-Key).
    POST {base}/v1/auth/login  { email, password }
    """
    base = str(link.get("base_url") or "").rstrip("/")
    if not base:
        return {"ok": False, "error": "lohn_base_url_missing"}
    email = _lohn_email(company_id)
    password = str(login.get("password") or "")
    if len(password) < 4:
        return {"ok": False, "error": "lohn_password_missing"}
    body = json.dumps({"email": email, "password": password, "companyId": company_id}, ensure_ascii=False).encode(
        "utf-8"
    )
    url = f"{base}/v1/auth/login"
    req = urlrequest.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "SUPPIX-Lohn-SSO/1.0",
            "X-WorkPass-Company-Id": company_id,
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            raw = resp.read()[:8000].decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw.strip().startswith("{") else {}
            if not isinstance(parsed, dict):
                parsed = {}
            token = str(parsed.get("session") or parsed.get("token") or "").strip()
            if resp.status < 400 and parsed.get("ok") is not False and token:
                return {
                    "ok": True,
                    "token": token,
                    "expiresAt": parsed.get("expiresAt"),
                    "user": parsed.get("user") or {"companyId": company_id, "email": email},
                    "via": parsed.get("via") or "suppix-login",
                    "status": int(resp.status),
                }
            return {
                "ok": False,
                "error": parsed.get("error") or "login_failed",
                "status": int(resp.status),
                "body": raw[:300],
            }
    except urlerror.HTTPError as exc:
        detail = ""
        parsed: dict[str, Any] = {}
        try:
            detail = exc.read()[:800].decode("utf-8", errors="replace")
            if detail.strip().startswith("{"):
                parsed = json.loads(detail)
        except Exception:
            detail = str(exc)
        return {
            "ok": False,
            "status": int(exc.code),
            "error": (parsed.get("error") if isinstance(parsed, dict) else None) or detail[:200],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def request_lohn_sso_url(
    link: dict[str, Any],
    *,
    company_id: str,
    login: dict[str, Any],
    actor_user_id: str = "",
) -> dict[str, Any]:
    """Ask WorkPass Lohn for a one-time browser URL (master-key SSO), else public login session."""
    # 1) Public SPA login (preferred — matches auth-gate.js)
    public = login_lohn_company_session(link, company_id=company_id, login=login)
    if public.get("ok") and public.get("token"):
        ui = _browser_base(link)
        url = build_session_handoff_url(
            ui,
            {
                "token": public["token"],
                "expiresAt": public.get("expiresAt"),
                "user": public.get("user"),
                "via": public.get("via") or "suppix",
            },
        )
        return {"ok": True, "url": url, "path": "/v1/auth/login", "mode": "session_handoff"}

    # 2) Master-key platform SSO (optional)
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
    last: dict[str, Any] = {"ok": False, "error": public.get("error") or "sso_unsupported"}
    if str(link.get("master_api_key") or "").strip():
        for path in SSO_API_PATHS:
            result = _post_lohn_json(link, path=path, body=body, event="auth.platform-sso", timeout=12)
            parsed = _parse_lohn_json(result)
            url = _extract_sso_url(parsed, browser_base=browser_base)
            if url and (result.get("ok") or parsed.get("ok") is True or parsed.get("session") or parsed.get("url")):
                return {"ok": True, "url": url, "path": path, "status": result.get("status")}
            last = {**result, "path": path, "parsed": parsed, "publicLogin": public}
            status = int(result.get("status") or 0)
            if status and status not in {404, 405, 501} and status >= 500:
                break
    return {"ok": False, "error": last.get("error") or "sso_unsupported", "detail": last, "publicLogin": public}


def build_ui_login_url(link: dict[str, Any], *, company_id: str, email: str) -> str:
    base = _browser_base(link)
    if not base or not _has_browser_ui(link):
        return ""
    q = urlencode({"email": email, "companyId": company_id, "source": "suppix"})
    return f"{base}/?{q}"


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
    link = get_platform_link(db)
    api_base = str(link.get("base_url") or "").rstrip("/")
    if not api_base or not link.get("enabled"):
        return {
            "ok": False,
            "error": "lohn_base_url_missing",
            "message": "Buchhaltungs-Domain fehlt. Superadmin muss die Lohn-URL unter Plattform speichern.",
        }

    # Always open via SUPPIX sso-enter (autologin shell). Do NOT send the browser to
    # Lohn #suppix-sso=… — live Lohn auth-gate does not consume that hash yet.
    login = repo.get_lohn_login(db, company_id)
    if login:
        remote = request_lohn_sso_url(
            link,
            company_id=company_id,
            login=login,
            actor_user_id=actor_user_id,
        )
        remote_url = str(remote.get("url") or "")
        remote_mode = str(remote.get("mode") or "")
        # Accept only a real magic-link from Lohn master-key SSO (not our hash handoff).
        if (
            remote.get("ok")
            and remote_url.startswith("http")
            and remote_mode not in ("session_handoff", "ui_login", "")
            and "suppix-sso=" not in remote_url
        ):
            return {
                "ok": True,
                "url": remote_url,
                "baseUrl": api_base,
                "companyId": company_id,
                "mode": remote_mode or "lohn_sso",
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
    email = _lohn_email(company_id)
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
        "needsUiUrl": not _has_browser_ui(link),
    }


def _normalize_expires_at(value: Any) -> str:
    """Lohn auth-gate uses Date.parse(expiresAt); always return an ISO string."""
    if value is None or value == "":
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 8 * 3600))
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:  # ms
            ts = ts / 1000.0
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
    text = str(value).strip()
    if text.isdigit():
        return _normalize_expires_at(int(text))
    # Already ISO / parseable
    return text


def _rewrite_relative_attr_urls(page: str, lohn_base: str) -> str:
    import re

    def repl(match: re.Match[str]) -> str:
        attr, quote, url = match.group(1), match.group(2), match.group(3)
        if url.startswith(("http://", "https://", "//", "data:", "mailto:", "javascript:", "#")):
            return match.group(0)
        if url.startswith("/"):
            return f"{attr}={quote}{lohn_base}{url}{quote}"
        return f"{attr}={quote}{lohn_base}/{url}{quote}"

    return re.sub(r"""(src|href)=(["'])([^"']+)\2""", repl, page, flags=re.I)


def build_autologin_shell_html(
    link: dict[str, Any],
    *,
    company_id: str,
    session_payload: dict[str, Any],
) -> str:
    """
    Serve Lohn UI under SUPPIX origin with session already in localStorage.
    Scripts/styles load from Lohn host; API calls go to Lohn via CORS (production)
    or absolute API base stored in workpass.lohn.apiConfig.v1.
    """
    import re

    lohn_base = _browser_base(link) or str(link.get("base_url") or "").rstrip("/")
    if not lohn_base:
        return ""
    try:
        req = urlrequest.Request(
            lohn_base + "/",
            headers={
                "Accept": "text/html",
                "User-Agent": "Mozilla/5.0 SUPPIX-Lohn-SSO/1.0",
            },
            method="GET",
        )
        with urlrequest.urlopen(req, timeout=20) as resp:
            page = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return ""

    # Strip CSP meta that would block cross-origin script/style from Lohn host.
    page = re.sub(
        r'<meta[^>]+http-equiv=["\']Content-Security-Policy["\'][^>]*>',
        "",
        page,
        flags=re.I,
    )
    page = _rewrite_relative_attr_urls(page, lohn_base)

    # Fetch and patch auth-gate so apiOrigin points at Lohn (page origin is SUPPIX).
    auth_js = ""
    try:
        with urlrequest.urlopen(
            urlrequest.Request(
                f"{lohn_base}/auth-gate.js?v=8",
                headers={"User-Agent": "Mozilla/5.0 SUPPIX-Lohn-SSO/1.0"},
            ),
            timeout=20,
        ) as resp:
            auth_js = resp.read().decode("utf-8", errors="replace")
    except Exception:
        auth_js = ""

    if auth_js:
        auth_js = auth_js.replace(
            "function apiOrigin() {",
            "function apiOrigin() {\n    if (window.__LOHN_API_ORIGIN__) return String(window.__LOHN_API_ORIGIN__);",
            1,
        )
        page = re.sub(
            r'<script[^>]+src=["\'][^"\']*auth-gate\.js[^"\']*["\'][^>]*>\s*</script>',
            "<!-- auth-gate inlined by SUPPIX SSO -->",
            page,
            flags=re.I,
        )

    payload = dict(session_payload)
    payload["expiresAt"] = _normalize_expires_at(payload.get("expiresAt"))
    session_json = json.dumps(payload, ensure_ascii=False)
    api_cfg = json.dumps(
        {"base": lohn_base, "companyId": company_id},
        ensure_ascii=False,
    )
    until = int(time.time() * 1000) + 8 * 60 * 60 * 1000
    bootstrap = f"""
<script>
window.__LOHN_API_ORIGIN__ = {json.dumps(lohn_base)};
try {{
  const session = {session_json};
  localStorage.setItem("workpassPlatformSessionV2", JSON.stringify(session));
  localStorage.setItem("workpassLohnSessionV2", JSON.stringify({{
    until: {until},
    touchedAt: new Date().toISOString()
  }}));
  localStorage.setItem("workpass.lohn.apiConfig.v1", {api_cfg});
  document.addEventListener("DOMContentLoaded", function () {{
    try {{ document.body && document.body.classList.remove("auth-locked"); }} catch (e) {{}}
  }});
}} catch (e) {{ console.warn("SUPPIX Lohn SSO bootstrap", e); }}
</script>
"""
    if auth_js:
        safe_js = auth_js.replace("</", "<\\/")
        bootstrap += f"<script>\n{safe_js}\n</script>\n"

    # Do NOT use re.sub replacement with JS (\\d etc. → PatternError / 500).
    head_match = re.search(r"<head[^>]*>", page, flags=re.I)
    if head_match:
        i = head_match.end()
        page = page[:i] + bootstrap + page[i:]
    else:
        page = bootstrap + page
    return page


def resolve_sso_enter(db, ticket_id: str) -> dict[str, Any]:
    """Consume ticket → autologin shell (preferred) or Lohn UI."""
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
    lohn_origin = _browser_base(link) or str(link.get("base_url") or "").rstrip("/")

    # Ensure credentials exist + are pushed to Lohn (mint if missing).
    if not login:
        try:
            from .platform_link import provision_company_for_lohn

            provision_company_for_lohn(db, company_id, force=True)
            login = repo.get_lohn_login(db, company_id)
        except Exception:
            login = repo.get_lohn_login(db, company_id)

    # Re-push password to Lohn so /v1/auth/login matches stored credentials.
    if login:
        try:
            from .platform_link import sync_lohn_login_credentials

            sync_lohn_login_credentials(
                db,
                company_id,
                username=str(login.get("username") or ""),
                password=str(login.get("password") or ""),
            )
            login = repo.get_lohn_login(db, company_id) or login
        except Exception:
            pass

    session_payload: dict[str, Any] | None = None
    login_err = ""
    if login:
        public = login_lohn_company_session(link, company_id=company_id, login=login)
        if public.get("ok") and public.get("token"):
            session_payload = {
                "token": public["token"],
                "expiresAt": _normalize_expires_at(public.get("expiresAt")),
                "user": public.get("user") or {"companyId": company_id, "email": email},
                "via": public.get("via") or "suppix",
            }
        else:
            login_err = str(public.get("error") or "login_failed")
            remote = request_lohn_sso_url(
                link, company_id=company_id, login=login, actor_user_id=actor
            )
            if remote.get("ok") and remote.get("mode") == "session_handoff" and remote.get("url"):
                # Prefer shell if we can re-login; otherwise hash handoff (needs Lohn snippet).
                public2 = login_lohn_company_session(link, company_id=company_id, login=login)
                if public2.get("ok") and public2.get("token"):
                    session_payload = {
                        "token": public2["token"],
                        "expiresAt": _normalize_expires_at(public2.get("expiresAt")),
                        "user": public2.get("user") or {"companyId": company_id, "email": email},
                        "via": public2.get("via") or "suppix",
                    }

    if session_payload and _has_browser_ui(link):
        shell = build_autologin_shell_html(
            link, company_id=company_id, session_payload=session_payload
        )
        if shell:
            return {
                "ok": True,
                "html": shell,
                "mode": "shell_autologin",
                "lohn_origin": lohn_origin,
            }
        handoff = build_session_handoff_url(lohn_origin, session_payload)
        return {
            "ok": True,
            "redirect": handoff,
            "html": render_sso_help_html(
                ui_url=handoff,
                email=email,
                message="Weiterleitung zu WorkPass Lohn (SSO)…",
            ),
            "mode": "session_handoff",
        }

    if _has_browser_ui(link):
        target = build_ui_login_url(link, company_id=company_id, email=email) or lohn_origin
        msg = (
            "WorkPass Lohn wird geöffnet. Automatische Anmeldung nicht möglich — "
            "bitte mit der Firmen-E-Mail anmelden (Passwort ggf. neu synchronisieren)."
        )
        if login_err:
            msg = (
                "WorkPass Lohn wird geöffnet. Automatische Anmeldung fehlgeschlagen "
                f"({login_err}). Bitte mit der Firmen-E-Mail anmelden."
            )
        return {
            "ok": True,
            "redirect": target,
            "html": render_sso_help_html(ui_url=target, email=email, message=msg),
            "mode": "ui_login",
        }

    return {
        "ok": True,
        "html": render_sso_help_html(
            ui_url="",
            email=email,
            message=(
                "WorkPass Lohn API-URL liefert keine Browser-Oberfläche. "
                "Bitte Basis-URL der Web-App speichern (z. B. https://workpass-lohn.up.railway.app)."
            ),
        ),
        "mode": "needs_ui_url",
    }
