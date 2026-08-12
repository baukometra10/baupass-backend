"""One-time WorkPass Lohn platform link + auto-provision on company create."""
from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from backend.app.core.platform_env import platform_env

from . import repository as repo
from .auth import sign_payload
from .company_sync import company_upsert_payload
from .schema import ensure_accounting_schema


def _workpass_raw_env(var_name: str) -> str:
    """Read WORKPASS_* from Railway env plus SUPPIX_/BAUPASS_ mirrors."""
    for key in (var_name, f"SUPPIX_{var_name}", f"BAUPASS_{var_name}"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def resolve_master_api_keys(link: dict[str, Any] | None = None) -> list[str]:
    """
    All secrets accepted for inbound Lohn webhooks and outbound Lohn API calls.
    DB master key plus WORKPASS_LOHN_MASTER_KEY / WORKPASS_PLATFORM_WEBHOOK_KEY env.
    """
    link = link or {}
    keys: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        candidate = str(raw or "").strip()
        if candidate and candidate not in seen:
            seen.add(candidate)
            keys.append(candidate)

    add(str(link.get("master_api_key") or ""))
    add(platform_env("WORKPASS_LOHN_MASTER_KEY", ""))
    add(_workpass_raw_env("WORKPASS_LOHN_MASTER_KEY"))
    add(_workpass_raw_env("WORKPASS_PLATFORM_WEBHOOK_KEY"))
    return keys


def primary_master_api_key(link: dict[str, Any] | None = None) -> str:
    keys = resolve_master_api_keys(link)
    return keys[0] if keys else ""


def _ensure_platform_link_table(db) -> None:
    ensure_accounting_schema(db)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS workpass_lohn_platform_link (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            enabled INTEGER NOT NULL DEFAULT 0,
            base_url TEXT NOT NULL DEFAULT '',
            master_api_key TEXT NOT NULL DEFAULT '',
            company_upsert_path TEXT NOT NULL DEFAULT '/v1/company/upsert',
            hours_webhook_path TEXT NOT NULL DEFAULT '/hooks/suppix-hours',
            platform_public_url TEXT NOT NULL DEFAULT '',
            auto_provision INTEGER NOT NULL DEFAULT 1,
            default_run_day INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    row = db.execute("SELECT id FROM workpass_lohn_platform_link WHERE id = 1").fetchone()
    if not row:
        db.execute(
            """
            INSERT INTO workpass_lohn_platform_link
            (id, enabled, base_url, master_api_key, company_upsert_path, hours_webhook_path,
             platform_public_url, auto_provision, default_run_day, updated_at)
            VALUES (1, 0, '', '', '/v1/company/upsert', '/hooks/suppix-hours', '', 1, 1, '')
            """
        )
        try:
            db.commit()
        except Exception:
            pass
    # Optional browser UI host (API base often requires X-WorkPass-Key and is not openable in a tab)
    try:
        cols = {str(r[1]) for r in db.execute("PRAGMA table_info(workpass_lohn_platform_link)").fetchall()}
    except Exception:
        cols = set()
    if cols and "ui_base_url" not in cols:
        try:
            db.execute(
                "ALTER TABLE workpass_lohn_platform_link ADD COLUMN ui_base_url TEXT NOT NULL DEFAULT ''"
            )
            db.commit()
        except Exception:
            try:
                db.execute(
                    "ALTER TABLE workpass_lohn_platform_link ADD COLUMN IF NOT EXISTS ui_base_url TEXT NOT NULL DEFAULT ''"
                )
                db.commit()
            except Exception:
                pass

def get_platform_link(db) -> dict[str, Any]:
    _ensure_platform_link_table(db)
    row = db.execute("SELECT * FROM workpass_lohn_platform_link WHERE id = 1").fetchone()
    data = dict(row) if row else {}
    # Env wins as bootstrap / override when DB empty
    env_base = platform_env("WORKPASS_LOHN_BASE_URL", "")
    env_ui = platform_env("WORKPASS_LOHN_UI_URL", "")
    env_enabled = platform_env("WORKPASS_LOHN_ENABLED", "")
    env_public = platform_env("PUBLIC_BASE_URL", "") or platform_env("PLATFORM_PUBLIC_URL", "")
    if env_base and not str(data.get("base_url") or "").strip():
        data["base_url"] = env_base
    if env_ui and not str(data.get("ui_base_url") or "").strip():
        data["ui_base_url"] = env_ui
    if not str(data.get("master_api_key") or "").strip():
        boot_key = primary_master_api_key(data)
        if boot_key:
            data["master_api_key"] = boot_key
    if env_public and not str(data.get("platform_public_url") or "").strip():
        data["platform_public_url"] = env_public
    if env_enabled:
        data["enabled"] = 0 if env_enabled.strip().lower() in {"0", "false", "no", "off"} else 1
    data["configured"] = bool(str(data.get("base_url") or "").strip() and int(data.get("enabled") or 0))
    # Never leak full master key in API responses — mask unless caller asks raw via separate path
    key = str(data.get("master_api_key") or "")
    data["masterApiKeySet"] = bool(key)
    data["masterApiKeyPreview"] = (key[:6] + "…" + key[-4:]) if len(key) > 12 else ("***" if key else "")
    # camelCase aliases for admin UIs
    data["baseUrl"] = str(data.get("base_url") or "")
    data["uiBaseUrl"] = str(data.get("ui_base_url") or "")
    data["companyUpsertPath"] = str(data.get("company_upsert_path") or "/v1/company/upsert")
    data["hoursWebhookPath"] = str(data.get("hours_webhook_path") or "/hooks/suppix-hours")
    data["platformPublicUrl"] = str(data.get("platform_public_url") or "")
    data["autoProvision"] = bool(int(data.get("auto_provision") or 0))
    data["runDay"] = int(data.get("default_run_day") or 1)
    data["enabled"] = bool(int(data.get("enabled") or 0)) if not isinstance(data.get("enabled"), bool) else data.get("enabled")
    return data


def test_platform_link_connectivity(db) -> dict[str, Any]:
    """Ping WorkPass Lohn base URL (health-ish) using stored link settings."""
    link = get_platform_link(db)
    base = str(link.get("base_url") or "").rstrip("/")
    if not base:
        return {
            "ok": False,
            "error": "lohn_base_url_missing",
            "message": "WorkPass Lohn Basis-URL fehlt. Bitte Lohn-Host speichern (nicht die Plattform-URL).",
        }
    if not link.get("enabled"):
        return {
            "ok": False,
            "error": "platform_link_disabled",
            "baseUrl": base,
            "message": "Verbindung ist deaktiviert. Bitte «Verbindung aktiv = Ja» speichern.",
        }
    platform_public = str(link.get("platform_public_url") or "").rstrip("/").lower()
    if base.lower() in {"https://suppix-ai-workpass.com", "http://suppix-ai-workpass.com"} or (
        platform_public and base.lower() == platform_public
    ):
        return {
            "ok": False,
            "error": "lohn_base_url_is_platform",
            "baseUrl": base,
            "message": "Basis-URL zeigt auf die Plattform. Hier muss die URL der WorkPass-Lohn-App stehen.",
        }
    # Prefer /health then root
    candidates = [f"{base}/health", f"{base}/api/health", base]
    last_error = ""
    for url in candidates:
        req = urlrequest.Request(
            url,
            headers={
                "User-Agent": "SUPPIX-WorkPass-Lohn-Bridge/1.0",
                "Accept": "application/json,text/plain,*/*",
            },
            method="GET",
        )
        master = primary_master_api_key(link)
        if master:
            # WorkPass Lohn expects X-WorkPass-Key (Bearer/Master aliases kept for compatibility).
            req.add_header("X-WorkPass-Key", master)
            req.add_header("Authorization", f"Bearer {master}")
            req.add_header("X-WorkPass-Master-Key", master)
        try:
            with urlrequest.urlopen(req, timeout=12) as resp:
                body = resp.read()[:400].decode("utf-8", errors="replace")
                return {
                    "ok": True,
                    "status": int(resp.status),
                    "url": url,
                    "baseUrl": base,
                    "bodyPreview": body,
                    "message": "Lohn-Host erreichbar.",
                }
        except urlerror.HTTPError as exc:
            # 401/404 still proves host is reachable
            if int(exc.code) in {401, 403, 404, 405}:
                return {
                    "ok": True,
                    "reachable": True,
                    "status": int(exc.code),
                    "url": url,
                    "baseUrl": base,
                    "note": "host_reachable_auth_or_path",
                    "message": f"Lohn-Host erreichbar (HTTP {exc.code}).",
                }
            last_error = f"HTTP {exc.code}"
        except Exception as exc:
            last_error = str(exc)[:200]
    return {
        "ok": False,
        "error": last_error or "unreachable",
        "baseUrl": base,
        "message": (
            f"Lohn-Host nicht erreichbar ({last_error or 'unreachable'}). "
            "Prüfe Basis-URL und ob der Server von der Plattform aus erreichbar ist."
        ),
    }


def save_platform_link(
    db,
    *,
    enabled: bool | None = None,
    base_url: str | None = None,
    ui_base_url: str | None = None,
    master_api_key: str | None = None,
    company_upsert_path: str | None = None,
    hours_webhook_path: str | None = None,
    platform_public_url: str | None = None,
    auto_provision: bool | None = None,
    default_run_day: int | None = None,
) -> dict[str, Any]:
    _ensure_platform_link_table(db)
    current = get_platform_link(db)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    enabled_v = int(current.get("enabled") or 0) if enabled is None else (1 if enabled else 0)
    base_v = str(current.get("base_url") or "") if base_url is None else base_url.strip().rstrip("/")
    ui_v = str(current.get("ui_base_url") or "") if ui_base_url is None else ui_base_url.strip().rstrip("/")
    key_v = str(current.get("master_api_key") or "")
    if master_api_key is not None and master_api_key.strip():
        key_v = master_api_key.strip()
    upsert_v = (
        str(current.get("company_upsert_path") or "/v1/company/upsert")
        if company_upsert_path is None
        else (company_upsert_path.strip() or "/v1/company/upsert")
    )
    if not upsert_v.startswith("/"):
        upsert_v = "/" + upsert_v
    hook_v = (
        str(current.get("hours_webhook_path") or "/hooks/suppix-hours")
        if hours_webhook_path is None
        else (hours_webhook_path.strip() or "/hooks/suppix-hours")
    )
    if not hook_v.startswith("/"):
        hook_v = "/" + hook_v
    public_v = (
        str(current.get("platform_public_url") or "")
        if platform_public_url is None
        else platform_public_url.strip().rstrip("/")
    )
    auto_v = int(current.get("auto_provision") or 1) if auto_provision is None else (1 if auto_provision else 0)
    run_v = int(current.get("default_run_day") or 1) if default_run_day is None else max(1, min(28, int(default_run_day)))
    db.execute(
        """
        UPDATE workpass_lohn_platform_link
        SET enabled = ?, base_url = ?, ui_base_url = ?, master_api_key = ?, company_upsert_path = ?,
            hours_webhook_path = ?, platform_public_url = ?, auto_provision = ?,
            default_run_day = ?, updated_at = ?
        WHERE id = 1
        """,
        (enabled_v, base_v, ui_v, key_v, upsert_v, hook_v, public_v, auto_v, run_v, now),
    )
    db.commit()
    link = get_platform_link(db)
    try:
        sync_lohn_cors_origins(db, link)
    except Exception:
        pass
    return link


def _origin_from_host(host: str) -> list[str]:
    h = (host or "").strip().lower().rstrip("/")
    if not h:
        return []
    if h.startswith("http://") or h.startswith("https://"):
        try:
            from urllib.parse import urlparse

            parsed = urlparse(h)
            origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
            return [origin] if origin.startswith("http") else []
        except Exception:
            return []
    # bare hostname
    out = [f"https://{h}"]
    if not h.startswith("www."):
        out.append(f"https://www.{h}")
    return out


def collect_platform_cors_origins(db, link: dict[str, Any] | None = None) -> list[str]:
    """Origins SUPPIX uses (public URL + per-company access_host) for Lohn CORS."""
    link = link or get_platform_link(db)
    origins: list[str] = []
    seen: set[str] = set()

    def _add(items: list[str]) -> None:
        for o in items:
            n = (o or "").strip().rstrip("/")
            if not n or n in seen:
                continue
            seen.add(n)
            origins.append(n)

    public = str(link.get("platform_public_url") or "").strip().rstrip("/")
    if public:
        _add(_origin_from_host(public))
    try:
        env_public = (platform_env("PUBLIC_BASE_URL", "") or "").strip().rstrip("/")
        if env_public:
            _add(_origin_from_host(env_public))
    except Exception:
        pass
    _add(
        [
            "https://suppix-ai-workpass.com",
            "https://www.suppix-ai-workpass.com",
            "https://app.suppix-ai-workpass.com",
            "http://127.0.0.1:8080",
            "http://localhost:8080",
        ]
    )
    try:
        rows = db.execute(
            "SELECT COALESCE(access_host, '') AS h FROM companies "
            "WHERE deleted_at IS NULL AND TRIM(COALESCE(access_host, '')) != ''"
        ).fetchall()
        for row in rows:
            _add(_origin_from_host(str(row["h"] if hasattr(row, "keys") else row[0])))
    except Exception:
        pass
    return origins


def sync_lohn_cors_origins(db, link: dict[str, Any] | None = None) -> dict[str, Any]:
    """Push SUPPIX + tenant origins to WorkPass Lohn CORS allow-list."""
    link = link or get_platform_link(db)
    if not int(link.get("enabled") or 0):
        return {"ok": False, "skipped": "platform_link_disabled"}
    origins = collect_platform_cors_origins(db, link)
    if not origins:
        return {"ok": False, "skipped": "no_origins"}
    return _post_lohn_json(
        link,
        path="/v1/platform/cors-origins",
        body={"origins": origins},
        event="platform.cors-origins",
        timeout=15,
    )


def _company_webhook_url(link: dict[str, Any]) -> str:
    base = str(link.get("base_url") or "").rstrip("/")
    path = str(link.get("hours_webhook_path") or "/hooks/suppix-hours")
    if not base:
        return ""
    return f"{base}{path}"


def _post_lohn_json(
    link: dict[str, Any],
    *,
    path: str,
    body: dict[str, Any],
    event: str,
    timeout: float = 20,
) -> dict[str, Any]:
    base = str(link.get("base_url") or "").rstrip("/")
    if not base:
        return {"ok": False, "error": "lohn_base_url_missing"}
    if not path.startswith("/"):
        path = "/" + path
    url = f"{base}{path}"
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    ts = str(int(time.time()))
    master = primary_master_api_key(link)
    company_id = str(
        body.get("companyId")
        or body.get("company_id")
        or (body.get("login") or {}).get("companyId")
        or body.get("id")
        or ""
    )
    if not master:
        return {
            "ok": False,
            "error": "master_api_key_missing",
            "message": "Master-API-Key fehlt im Plattform-Link.",
            "url": url,
        }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SUPPIX-WorkPass-Lohn-Bridge/1.0",
        "X-WorkPass-Company-Id": company_id,
        "X-Suppix-Timestamp": ts,
        "X-Suppix-Event": event,
        "X-Suppix-Product": "WorkPass Lohn",
        "X-WorkPass-Key": master,
        "Authorization": f"Bearer {master}",
        "X-WorkPass-Master-Key": master,
        "X-Suppix-Signature": sign_payload(master, timestamp=ts, body=raw),
    }
    req = urlrequest.Request(url, data=raw, headers=headers, method="POST")
    def _decode_body(raw: bytes, limit: int = 8000) -> tuple[str, dict[str, Any] | None]:
        text = (raw or b"")[:limit].decode("utf-8", errors="replace")
        parsed: dict[str, Any] | None = None
        if text.strip().startswith("{"):
            try:
                obj = json.loads(text)
                if isinstance(obj, dict):
                    parsed = obj
            except Exception:
                parsed = None
        return text, parsed

    try:
        with urlrequest.urlopen(req, timeout=max(2.0, float(timeout or 20))) as resp:
            text, parsed = _decode_body(resp.read())
            out = {
                "ok": True,
                "status": int(resp.status),
                "url": url,
                "body": text[:800],
            }
            if parsed is not None:
                out["json"] = parsed
            return out
    except urlerror.HTTPError as exc:
        detail = ""
        parsed = None
        try:
            detail, parsed = _decode_body(exc.read(), limit=4000)
        except Exception:
            detail = str(exc)
        out = {"ok": False, "status": int(exc.code), "url": url, "error": (detail or str(exc))[:200], "body": detail[:800] if detail else ""}
        if parsed is not None:
            out["json"] = parsed
        return out
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200], "url": url}


def _post_lohn_upsert(link: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    path = str(link.get("company_upsert_path") or "/v1/company/upsert")
    return _post_lohn_json(link, path=path, body=body, event="company.upsert")


def _post_lohn_login_sync(link: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """WorkPass Lohn expects passwords via POST /v1/company/login-sync."""
    return _post_lohn_json(link, path="/v1/company/login-sync", body=body, event="company.login-sync")


def _resolve_or_mint_lohn_login(
    db,
    company_id: str,
    *,
    admin_username: str | None = None,
    admin_password: str | None = None,
) -> dict[str, Any]:
    """
    Return {username, password, minted?} for Lohn.
    If password missing on re-enable, mint a new company-admin password and store it.
    """
    import secrets

    from werkzeug.security import generate_password_hash

    username = (admin_username or "").strip()
    password = str(admin_password or "")
    if not username:
        try:
            admin_row = db.execute(
                """
                SELECT id, username FROM users
                WHERE company_id = ? AND role = 'company-admin'
                ORDER BY id LIMIT 1
                """,
                (company_id,),
            ).fetchone()
        except Exception:
            admin_row = None
        if admin_row:
            username = str(admin_row["username"] or "").strip()
            admin_id = str(admin_row["id"] or "")
        else:
            admin_id = ""
    else:
        admin_id = ""
        try:
            admin_row = db.execute(
                """
                SELECT id FROM users
                WHERE company_id = ? AND role = 'company-admin' AND username = ?
                LIMIT 1
                """,
                (company_id, username),
            ).fetchone()
            if admin_row:
                admin_id = str(admin_row["id"] or "")
        except Exception:
            pass

    if username and password:
        repo.store_lohn_login(db, company_id, username=username, password=password)
        return {"username": username, "password": password, "minted": False}

    existing = repo.get_lohn_login(db, company_id)
    if existing:
        return {**existing, "minted": False}

    if not username:
        return {}

    # Re-enable / old company: mint password so Lohn login-sync can succeed
    password = secrets.token_urlsafe(14)
    if admin_id:
        try:
            db.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (generate_password_hash(password), admin_id),
            )
            db.execute("DELETE FROM sessions WHERE user_id = ?", (admin_id,))
            db.commit()
        except Exception:
            pass
    repo.store_lohn_login(db, company_id, username=username, password=password)
    return {"username": username, "password": password, "minted": True}


def notify_company_lohn_status(db, company_id: str, *, enabled: bool) -> dict[str, Any]:
    """Tell WorkPass Lohn that a company opted in/out (best-effort)."""
    link = get_platform_link(db)
    if not int(link.get("enabled") or 0) or not str(link.get("base_url") or "").strip():
        return {"ok": False, "skipped": "platform_link_disabled"}
    try:
        company_payload = company_upsert_payload(db, company_id)
    except LookupError:
        return {"ok": False, "error": "company_not_found"}
    body = {
        **company_payload,
        "id": company_id,
        "companyId": company_id,
        "product": "WorkPass Lohn",
        "entitlement": "included_with_platform" if enabled else "disabled",
        "workpassLohnEnabled": bool(enabled),
        "event": "company.lohn.enabled" if enabled else "company.lohn.disabled",
    }
    return _post_lohn_upsert(link, body)


def provision_company_for_lohn(
    db,
    company_id: str,
    *,
    force: bool = False,
    admin_username: str | None = None,
    admin_password: str | None = None,
) -> dict[str, Any]:
    """
    Create local accounting bridge credentials for the company and register it in WorkPass Lohn.
    Requires per-company opt-in (`companies.workpass_lohn_enabled = 1`).
    When admin_username/password are provided (company create / password reset), they are
    stored encrypted and pushed to WorkPass Lohn so both systems can collaborate.
    """
    company_id = (company_id or "").strip()
    if not company_id:
        return {"ok": False, "error": "company_id_required"}

    from .company_opt_in import ensure_company_lohn_column, is_workpass_lohn_enabled

    ensure_company_lohn_column(db)
    if not is_workpass_lohn_enabled(db, company_id):
        return {"ok": False, "skipped": "company_opted_out"}

    link = get_platform_link(db)
    if not int(link.get("enabled") or 0):
        return {"ok": False, "skipped": "platform_link_disabled"}
    if not str(link.get("base_url") or "").strip():
        return {"ok": False, "error": "lohn_base_url_missing"}

    existing = repo.get_integration(db, company_id)
    if existing and not force and int(existing.get("enabled") or 0):
        # Still push upsert so Lohn stays in sync, but do not rotate keys
        rotate = False
    else:
        rotate = True if not existing else force

    webhook = _company_webhook_url(link)
    local = repo.upsert_integration(
        db,
        company_id=company_id,
        webhook_url=webhook,
        enabled=True,
        run_day=int(link.get("default_run_day") or 1),
        rotate_key=rotate,
    )
    try:
        company_payload = company_upsert_payload(db, company_id)
    except LookupError:
        return {"ok": False, "error": "company_not_found"}

    # Resolve / persist company-admin login for Lohn
    login = _resolve_or_mint_lohn_login(
        db,
        company_id,
        admin_username=admin_username,
        admin_password=admin_password,
    )

    platform_url = str(link.get("platform_public_url") or "").rstrip("/")
    bridge = {
        "baseUrl": platform_url,
        "hoursUrl": f"{platform_url}/api/v2/accounting/hours" if platform_url else "/api/v2/accounting/hours",
        "employeesUrl": (
            f"{platform_url}/api/v2/accounting/employees"
            if platform_url
            else "/api/v2/accounting/employees"
        ),
        "employeesCapability": "platform.employees.v1",
        "periodRequestUrl": (
            f"{platform_url}/api/v2/accounting/period-request"
            if platform_url
            else "/api/v2/accounting/period-request"
        ),
        "periodRequestCapability": "platform.period.request.v1",
        "payrollBatchUrl": (
            f"{platform_url}/api/v2/accounting/payroll-batch"
            if platform_url
            else "/api/v2/accounting/payroll-batch"
        ),
        "payrollBatchCapability": "platform.payroll.batch.v1",
        "payrollBatchPushPath": "/v1/payroll/batch",
        "dataAlertsUrl": (
            f"{platform_url}/api/v2/accounting/employee-data-alerts"
            if platform_url
            else "/api/v2/accounting/employee-data-alerts"
        ),
        "platformWebhookUrl": (
            f"{platform_url}/api/workpass/webhooks/accounting"
            if platform_url
            else "/api/workpass/webhooks/accounting"
        ),
        "platformWebhookUrls": [
            f"{platform_url}/api/workpass/webhooks/accounting" if platform_url else "/api/workpass/webhooks/accounting",
            f"{platform_url}/api/v2/accounting/webhook" if platform_url else "/api/v2/accounting/webhook",
        ],
        "platformWebhookEnv": "WORKPASS_PLATFORM_WEBHOOK_URL",
        "messagesPendingPath": "/v1/messages/pending",
        "messagesAckPath": "/v1/messages/ack",
        "employeesImportPath": "/v1/employees/import",
        "statementsUrl": f"{platform_url}/api/v2/accounting/statements" if platform_url else "/api/v2/accounting/statements",
        "statementsStatusCapability": "platform.statements.status.v1",
        "companyUpsertUrl": f"{platform_url}/api/v2/accounting/company/upsert" if platform_url else "/api/v2/accounting/company/upsert",
        "accessUrl": f"{platform_url}/api/v2/accounting/company/access" if platform_url else "/api/v2/accounting/company/access",
        "loginSyncPath": "/v1/company/login-sync",
        "headerCompanyId": "X-WorkPass-Company-Id",
        "headerApiKey": "X-Accounting-Key",
        "companyId": company_id,
        "firmaId": company_id,
    }
    if local.get("apiKey"):
        bridge["accountingKey"] = local["apiKey"]
        bridge["signingSecret"] = local.get("signingSecret") or ""
    elif force:
        # Force re-key if asked
        local = repo.upsert_integration(
            db,
            company_id=company_id,
            webhook_url=webhook,
            enabled=True,
            run_day=int(link.get("default_run_day") or 1),
            rotate_key=True,
        )
        bridge["accountingKey"] = local.get("apiKey")
        bridge["signingSecret"] = local.get("signingSecret") or ""

    body = {
        **company_payload,
        "id": company_id,
        "companyId": company_id,
        "product": "WorkPass Lohn",
        "entitlement": "included_with_platform",
        "platformBridge": bridge,
    }
    login_sync_result: dict[str, Any] = {"skipped": "no_login"}
    lohn_login_email = ""
    if login:
        # WorkPass Lohn authenticates companies as {companyId}@firma.de + login.password
        lohn_login_email = f"{company_id}@firma.de"
        access = {
            "username": login["username"],
            "password": login["password"],
            "email": lohn_login_email,
            "role": "company-admin",
            "firmaId": company_id,
            "companyId": company_id,
        }
        body["access"] = access
        body["login"] = {
            "username": login["username"],
            "password": login["password"],
            "email": lohn_login_email,
        }
        body["username"] = login["username"]
        body["password"] = login["password"]
        body["email"] = lohn_login_email
        body["adminUsername"] = login["username"]
        body["adminPassword"] = login["password"]
        login_sync_body = {
            "id": company_id,
            "companyId": company_id,
            "firmaId": company_id,
            "name": str((company_payload.get("company") or {}).get("name") or company_payload.get("name") or company_id),
            "product": "WorkPass Lohn",
            "email": lohn_login_email,
            "username": login["username"],
            "password": login["password"],
            "login": {
                "email": lohn_login_email,
                "username": login["username"],
                "password": login["password"],
            },
            "login.password": login["password"],
            "login.username": login["username"],
            "login.email": lohn_login_email,
            "access": access,
            "platformBridge": {
                "companyId": company_id,
                "firmaId": company_id,
                "accountingKey": bridge.get("accountingKey") or "",
                "accessUrl": bridge.get("accessUrl") or "",
            },
        }
        # Password sync first — Lohn UI blocks without hasLoginPassword from login-sync.
        login_sync_result = _post_lohn_login_sync(link, login_sync_body)
    remote = _post_lohn_upsert(link, body)
    ok = bool(remote.get("ok"))
    # Prefer login-sync success when Lohn specifically requires it; upsert alone is not enough.
    if login and not login_sync_result.get("ok") and login_sync_result.get("skipped") != "no_login":
        ok = False
    # Detect soft-success without password (Lohn returns ok but hasLoginPassword false)
    if login and login_sync_result.get("ok"):
        ws = {}
        try:
            raw = login_sync_result.get("body") or ""
            parsed = json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("{") else {}
            ws = parsed.get("workspace") or {}
            if ws.get("hasLoginPassword") is False:
                ok = False
                login_sync_result = {
                    **login_sync_result,
                    "ok": False,
                    "error": "lohn_password_not_stored",
                    "message": "WorkPass Lohn accepted sync but hasLoginPassword=false",
                }
        except Exception:
            pass
    out = {
        "ok": ok,
        "companyId": company_id,
        "localIntegration": {
            "enabled": True,
            "webhookUrl": webhook,
            "apiKeyPrefix": local.get("api_key_prefix") or local.get("apiKey", "")[:16],
            "keyRotated": bool(local.get("apiKey")),
            "loginUsername": (login or {}).get("username") or "",
            "lohnLoginEmail": lohn_login_email,
            "loginPushed": bool(login),
            "loginMinted": bool(login.get("minted")) if login else False,
        },
        "remote": remote,
        "loginSync": login_sync_result,
        "autoProvision": True,
    }
    if login and login.get("minted"):
        out["temporaryAdminPassword"] = login["password"]
        out["warning"] = (
            "Admin-Passwort neu erzeugt und an WorkPass Lohn gesendet "
            "(alte Firmen ohne gespeichertes Klartext-Passwort)."
        )
    if login and login_sync_result.get("ok"):
        # One-time reveal in this API response so Superadmin can open Lohn with same login.
        out["loginUsername"] = login["username"]
        out["lohnLoginEmail"] = lohn_login_email
        out["exportedPassword"] = login["password"]
        if not out.get("temporaryAdminPassword"):
            out["temporaryAdminPassword"] = login["password"]
    return out


def sync_lohn_login_credentials(
    db,
    company_id: str,
    *,
    username: str,
    password: str,
) -> dict[str, Any]:
    """Store credentials and push them to WorkPass Lohn when the company is opted in."""
    company_id = (company_id or "").strip()
    username = (username or "").strip()
    password = str(password or "")
    if not company_id or not username or not password:
        return {"ok": False, "error": "credentials_required"}
    from .company_opt_in import is_workpass_lohn_enabled

    if not is_workpass_lohn_enabled(db, company_id):
        return {"ok": False, "skipped": "company_opted_out"}
    # Ensure integration exists, then store + push
    return provision_company_for_lohn(
        db,
        company_id,
        force=False,
        admin_username=username,
        admin_password=password,
    )


def auto_provision_if_enabled(db, company_id: str) -> dict[str, Any]:
    link = get_platform_link(db)
    if not int(link.get("enabled") or 0):
        return {"ok": False, "skipped": "platform_link_disabled"}
    if not int(link.get("auto_provision") or 0):
        return {"ok": False, "skipped": "auto_provision_disabled"}
    return provision_company_for_lohn(db, company_id, force=False)


def provision_all_active_companies(db, *, force: bool = False) -> dict[str, Any]:
    rows = db.execute(
        """
        SELECT id FROM companies
        WHERE deleted_at IS NULL
          AND LOWER(COALESCE(status, '')) NOT IN ('gelöscht', 'geloescht', 'deleted', 'inactive', 'inaktiv')
        ORDER BY name
        """
    ).fetchall()
    results = []
    for row in rows:
        results.append(provision_company_for_lohn(db, str(row["id"]), force=force))
    ok_count = sum(1 for r in results if r.get("ok"))
    return {"ok": True, "total": len(results), "provisionedOk": ok_count, "results": results}
