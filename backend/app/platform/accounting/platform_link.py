"""One-time WorkPass Lohn platform link + auto-provision on company create."""
from __future__ import annotations

import json
import time
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from backend.app.core.platform_env import platform_env

from . import repository as repo
from .auth import sign_payload
from .company_sync import company_upsert_payload
from .schema import ensure_accounting_schema


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


def get_platform_link(db) -> dict[str, Any]:
    _ensure_platform_link_table(db)
    row = db.execute("SELECT * FROM workpass_lohn_platform_link WHERE id = 1").fetchone()
    data = dict(row) if row else {}
    # Env wins as bootstrap / override when DB empty
    env_base = platform_env("WORKPASS_LOHN_BASE_URL", "")
    env_key = platform_env("WORKPASS_LOHN_MASTER_KEY", "")
    env_enabled = platform_env("WORKPASS_LOHN_ENABLED", "")
    env_public = platform_env("PUBLIC_BASE_URL", "") or platform_env("PLATFORM_PUBLIC_URL", "")
    if env_base and not str(data.get("base_url") or "").strip():
        data["base_url"] = env_base
    if env_key and not str(data.get("master_api_key") or "").strip():
        data["master_api_key"] = env_key
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
        master = str(link.get("master_api_key") or "")
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
        SET enabled = ?, base_url = ?, master_api_key = ?, company_upsert_path = ?,
            hours_webhook_path = ?, platform_public_url = ?, auto_provision = ?,
            default_run_day = ?, updated_at = ?
        WHERE id = 1
        """,
        (enabled_v, base_v, key_v, upsert_v, hook_v, public_v, auto_v, run_v, now),
    )
    db.commit()
    return get_platform_link(db)


def _company_webhook_url(link: dict[str, Any]) -> str:
    base = str(link.get("base_url") or "").rstrip("/")
    path = str(link.get("hours_webhook_path") or "/hooks/suppix-hours")
    if not base:
        return ""
    return f"{base}{path}"


def _post_lohn_upsert(link: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    base = str(link.get("base_url") or "").rstrip("/")
    path = str(link.get("company_upsert_path") or "/v1/company/upsert")
    if not base:
        return {"ok": False, "error": "lohn_base_url_missing"}
    url = f"{base}{path}"
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    ts = str(int(time.time()))
    master = str(link.get("master_api_key") or "")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SUPPIX-WorkPass-Lohn-Bridge/1.0",
        "X-WorkPass-Company-Id": str(body.get("id") or body.get("companyId") or ""),
        "X-Suppix-Timestamp": ts,
        "X-Suppix-Event": "company.upsert",
        "X-Suppix-Product": "WorkPass Lohn",
    }
    if master:
        headers["X-WorkPass-Key"] = master
        headers["Authorization"] = f"Bearer {master}"
        headers["X-WorkPass-Master-Key"] = master
        headers["X-Suppix-Signature"] = sign_payload(master, timestamp=ts, body=raw)
    req = urlrequest.Request(url, data=raw, headers=headers, method="POST")
    try:
        with urlrequest.urlopen(req, timeout=20) as resp:
            return {
                "ok": True,
                "status": int(resp.status),
                "body": resp.read()[:800].decode("utf-8", errors="replace"),
            }
    except urlerror.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read()[:400].decode("utf-8", errors="replace")
        except Exception:
            detail = str(exc)
        return {"ok": False, "status": int(exc.code), "error": detail or str(exc)[:200]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


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
) -> dict[str, Any]:
    """
    Create local accounting bridge credentials for the company and register it in WorkPass Lohn.
    Requires per-company opt-in (`companies.workpass_lohn_enabled = 1`).
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

    platform_url = str(link.get("platform_public_url") or "").rstrip("/")
    bridge = {
        "baseUrl": platform_url,
        "hoursUrl": f"{platform_url}/api/v2/accounting/hours" if platform_url else "/api/v2/accounting/hours",
        "statementsUrl": f"{platform_url}/api/v2/accounting/statements" if platform_url else "/api/v2/accounting/statements",
        "companyUpsertUrl": f"{platform_url}/api/v2/accounting/company/upsert" if platform_url else "/api/v2/accounting/company/upsert",
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
    remote = _post_lohn_upsert(link, body)
    return {
        "ok": bool(remote.get("ok")),
        "companyId": company_id,
        "localIntegration": {
            "enabled": True,
            "webhookUrl": webhook,
            "apiKeyPrefix": local.get("api_key_prefix") or local.get("apiKey", "")[:16],
            "keyRotated": bool(local.get("apiKey")),
        },
        "remote": remote,
        "autoProvision": True,
    }


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
