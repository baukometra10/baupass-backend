"""Per-company WorkPass Lohn opt-in (optional — not mandatory)."""
from __future__ import annotations

from typing import Any

from . import repository as repo
from .schema import ensure_accounting_schema


def ensure_company_lohn_column(db) -> None:
    ensure_accounting_schema(db)
    try:
        cols = {str(r[1]) for r in db.execute("PRAGMA table_info(companies)").fetchall()}
    except Exception:
        try:
            # Postgres-ish fallback: attempt add and ignore
            db.execute(
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS workpass_lohn_enabled INTEGER NOT NULL DEFAULT 0"
            )
            db.commit()
        except Exception:
            pass
        return
    if "workpass_lohn_enabled" not in cols:
        try:
            db.execute(
                "ALTER TABLE companies ADD COLUMN workpass_lohn_enabled INTEGER NOT NULL DEFAULT 0"
            )
            db.commit()
        except Exception:
            pass


def is_workpass_lohn_enabled(db, company_id: str) -> bool:
    ensure_company_lohn_column(db)
    company_id = (company_id or "").strip()
    if not company_id:
        return False
    try:
        row = db.execute(
            "SELECT workpass_lohn_enabled FROM companies WHERE id = ? AND deleted_at IS NULL",
            (company_id,),
        ).fetchone()
    except Exception:
        return False
    if not row:
        return False
    try:
        return int(row["workpass_lohn_enabled"] or 0) == 1
    except (KeyError, TypeError, ValueError):
        return False


def set_workpass_lohn_enabled(
    db,
    company_id: str,
    *,
    enabled: bool,
    provision_if_enabled: bool = True,
    admin_username: str | None = None,
    admin_password: str | None = None,
) -> dict[str, Any]:
    """
    Toggle WorkPass Lohn for one company.
    When disabled: local bridge off + no outbound hours/webhooks.
    When enabled: flag on + optional provision to WorkPass Lohn.
    Optional admin_username/password are pushed to Lohn on provision.
    """
    ensure_company_lohn_column(db)
    company_id = (company_id or "").strip()
    if not company_id:
        return {"ok": False, "error": "company_id_required"}
    exists = db.execute(
        "SELECT id FROM companies WHERE id = ? AND deleted_at IS NULL",
        (company_id,),
    ).fetchone()
    if not exists:
        return {"ok": False, "error": "company_not_found"}

    flag = 1 if enabled else 0
    db.execute(
        "UPDATE companies SET workpass_lohn_enabled = ? WHERE id = ?",
        (flag, company_id),
    )

    if not enabled:
        # Stop all bridge traffic for this company
        existing = repo.get_integration(db, company_id)
        if existing:
            repo.upsert_integration(
                db,
                company_id=company_id,
                webhook_url=str(existing.get("webhook_url") or ""),
                enabled=False,
                run_day=int(existing.get("run_day") or 1),
                rotate_key=False,
            )
        else:
            db.commit()
        deactivate = {"skipped": "no_remote"}
        try:
            from .platform_link import notify_company_lohn_status

            deactivate = notify_company_lohn_status(db, company_id, enabled=False)
        except Exception as exc:
            deactivate = {"ok": False, "error": str(exc)[:160]}
        return {
            "ok": True,
            "companyId": company_id,
            "workpassLohnEnabled": False,
            "outboundStopped": True,
            "remote": deactivate,
        }

    db.commit()
    provision: dict[str, Any] = {"skipped": "not_requested"}
    if provision_if_enabled:
        try:
            from .platform_link import provision_company_for_lohn

            provision = provision_company_for_lohn(
                db,
                company_id,
                force=True,
                admin_username=admin_username,
                admin_password=admin_password,
            )
        except Exception as exc:
            provision = {"ok": False, "error": str(exc)[:200]}

    # Enabling without a successful Lohn push is not useful for the accounting app.
    if provision_if_enabled and not provision.get("ok"):
        skip = str(provision.get("skipped") or "")
        err = str(provision.get("error") or skip or "provision_failed")
        login_sync = provision.get("loginSync") or {}
        remote = provision.get("remote") or {}
        messages = {
            "platform_link_disabled": (
                "WorkPass Lohn Plattform-Link fehlt oder ist deaktiviert. "
                "Als Superadmin: Admin → WorkPass Lohn → Basis-URL + Master-Key speichern."
            ),
            "lohn_base_url_missing": (
                "WorkPass Lohn Basis-URL fehlt. Bitte Plattform-Link speichern "
                "(https://workpass-lohn.up.railway.app)."
            ),
            "master_api_key_missing": (
                "Master-API-Key fehlt. Bitte im Plattform-Link den gleichen Key wie in "
                "WorkPass Lohn (WORKPASS_API_KEY) speichern."
            ),
            "company_opted_out": "WorkPass Lohn ist für diese Firma nicht freigeschaltet.",
        }
        detail = ""
        for blob in (login_sync, remote, provision):
            if not blob.get("ok") and blob.get("error"):
                detail = str(blob.get("error"))[:220]
                err = f"{blob.get('error') and 'sync_failed'}:{detail}"[:240]
                break
            if blob.get("status") and not blob.get("ok"):
                detail = f"HTTP {blob.get('status')} {blob.get('error') or ''}".strip()
                err = detail[:240]
                break
        if not login_sync.get("ok") and login_sync.get("error"):
            err = f"login_sync_failed:{str(login_sync.get('error'))[:180]}"
        base_msg = (
            messages.get(skip)
            or messages.get(str(provision.get("error") or ""))
            or messages.get("master_api_key_missing" if "master_api_key_missing" in err else "")
        )
        if not base_msg:
            if "401" in err or "Unauthorized" in err or "X-WorkPass-Key" in err:
                base_msg = (
                    "WorkPass Lohn lehnt den Master-Key ab (401). "
                    "Im Plattform-Link denselben WORKPASS_API_KEY speichern und erneut senden."
                )
            elif "urlopen" in err or "getaddrinfo" in err or "timed out" in err.lower():
                base_msg = (
                    "WorkPass Lohn Host nicht erreichbar. Basis-URL prüfen: "
                    "https://workpass-lohn.up.railway.app"
                )
            else:
                base_msg = (
                    "Login konnte nicht an WorkPass Lohn gesendet werden. "
                    "Admin → WorkPass Lohn Plattform-Link (Basis-URL + Master-Key) prüfen."
                )
        if detail and detail not in base_msg:
            base_msg = f"{base_msg} Details: {detail}"
        return {
            "ok": False,
            "companyId": company_id,
            "workpassLohnEnabled": True,
            "error": err,
            "message": base_msg,
            "provision": provision,
        }

    return {
        "ok": True,
        "companyId": company_id,
        "workpassLohnEnabled": True,
        "provision": provision,
        "temporaryAdminPassword": provision.get("temporaryAdminPassword")
        or provision.get("exportedPassword"),
        "loginUsername": provision.get("loginUsername")
        or ((provision.get("localIntegration") or {}).get("loginUsername") or ""),
        "lohnLoginEmail": provision.get("lohnLoginEmail")
        or ((provision.get("localIntegration") or {}).get("lohnLoginEmail") or ""),
        "warning": provision.get("warning"),
    }


def require_lohn_enabled_or_error(db, company_id: str) -> dict[str, Any] | None:
    """Return error payload if company opted out; else None."""
    if is_workpass_lohn_enabled(db, company_id):
        # also require integration enabled
        integ = repo.get_integration(db, company_id)
        if integ and int(integ.get("enabled") or 0) == 1:
            return None
        return {"error": "workpass_lohn_disabled", "message": "WorkPass Lohn is disabled for this company"}
    return {"error": "workpass_lohn_disabled", "message": "WorkPass Lohn is disabled for this company"}
