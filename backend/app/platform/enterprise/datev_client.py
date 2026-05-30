"""
DATEV OAuth / API client (configure via Railway env).

Env:
  DATEV_CLIENT_ID
  DATEV_CLIENT_SECRET
  DATEV_REDIRECT_URI  (e.g. https://baupass-production.up.railway.app/api/integrations/datev/oauth/callback)
  DATEV_SCOPES        (optional, space-separated)
"""
from __future__ import annotations

import json
import os
import secrets
import time
import urllib.parse
from typing import Any
from urllib import parse as urlparse
from urllib import request as urlrequest

DEFAULT_SCOPES = "openid profile accounting:clients:read accounting:payroll:read"
DATEV_AUTHORIZE_URL = "https://login.datev.de/openid/authorize"
DATEV_TOKEN_URL = "https://api.datev.de/token"


def datev_env_configured() -> bool:
    return bool((os.getenv("DATEV_CLIENT_ID") or "").strip() and (os.getenv("DATEV_CLIENT_SECRET") or "").strip())


def build_datev_authorize_url(*, company_id: str, redirect_uri: str | None = None) -> dict[str, Any]:
    client_id = (os.getenv("DATEV_CLIENT_ID") or "").strip()
    if not client_id:
        return {"ok": False, "configured": False, "error": "datev_not_configured"}
    redirect = (redirect_uri or os.getenv("DATEV_REDIRECT_URI") or "").strip()
    if not redirect:
        return {"ok": False, "configured": True, "error": "missing_redirect_uri"}
    scopes = (os.getenv("DATEV_SCOPES") or DEFAULT_SCOPES).strip()
    state = f"{company_id}:{secrets.token_urlsafe(12)}"
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect,
        "scope": scopes,
        "state": state,
    }
    url = f"{DATEV_AUTHORIZE_URL}?{urlparse.urlencode(params)}"
    return {"ok": True, "configured": True, "authorizeUrl": url, "state": state, "redirectUri": redirect}


def exchange_datev_code(code: str, *, redirect_uri: str | None = None) -> dict[str, Any]:
    client_id = (os.getenv("DATEV_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("DATEV_CLIENT_SECRET") or "").strip()
    redirect = (redirect_uri or os.getenv("DATEV_REDIRECT_URI") or "").strip()
    if not client_id or not client_secret or not redirect:
        return {"ok": False, "error": "datev_not_configured"}
    body = urlparse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")
    req = urlrequest.Request(
        DATEV_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8") or "{}")
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    if not payload.get("access_token"):
        return {"ok": False, "error": payload.get("error_description") or payload.get("error") or "token_exchange_failed"}
    payload["obtained_at"] = int(time.time())
    return {"ok": True, "tokens": payload}


def datev_status_from_config(config: dict[str, Any]) -> dict[str, Any]:
    oauth = dict((config or {}).get("oauth") or {})
    connected = bool(oauth.get("access_token") or oauth.get("refresh_token"))
    return {
        "provider": "datev",
        "configured": datev_env_configured(),
        "connected": connected,
        "updatedAt": oauth.get("updated_at"),
    }
