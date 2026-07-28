"""Accounting bridge routes — WorkPass Lohn API + admin approval."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

accounting_bp = Blueprint("platform_accounting", __name__)


def _company_scope_for_user(user: dict) -> str | None:
    role = str(user.get("role") or "")
    if role == "superadmin":
        return (request.args.get("company_id") or (request.get_json(silent=True) or {}).get("companyId") or "").strip() or None
    return (user.get("company_id") or "").strip() or None


def register_accounting_blueprint(flask_app) -> None:
    from backend.server import get_db, require_auth, require_roles

    from . import repository as repo
    from .auth import authenticate_accounting_request
    from .company_sync import company_upsert_payload
    from .hours_service import normalize_period
    from .monthly_job import run_monthly_accounting_exports
    from .platform_link import (
        get_platform_link,
        provision_all_active_companies,
        provision_company_for_lohn,
        save_platform_link,
        test_platform_link_connectivity,
    )
    from .company_opt_in import is_workpass_lohn_enabled, set_workpass_lohn_enabled
    from .schema import ensure_accounting_schema
    from .service import (
        approve_batch,
        ingest_statements,
        notify_hours_ready,
        prepare_hour_export,
        reject_batch,
    )

    def _auth_accounting():
        """Returns (integration, None) or (None, (payload, http_status))."""
        db = get_db()
        ensure_accounting_schema(db)
        company_id = (
            request.headers.get("X-WorkPass-Company-Id")
            or request.headers.get("X-Company-Id")
            or request.args.get("company_id")
            or ""
        ).strip()
        if not company_id:
            return None, ({"error": "company_id_required", "hint": "Send X-WorkPass-Company-Id"}, 400)
        api_key = (
            request.headers.get("X-Accounting-Key")
            or request.headers.get("X-WorkPass-Accounting-Key")
            or request.headers.get("X-Api-Key")
            or ""
        ).strip()
        if api_key.lower().startswith("bearer "):
            api_key = api_key[7:].strip()
        auth = request.headers.get("Authorization") or ""
        if not api_key and auth.lower().startswith("bearer "):
            api_key = auth[7:].strip()
        timestamp = (request.headers.get("X-Suppix-Timestamp") or "").strip()
        signature = (request.headers.get("X-Suppix-Signature") or "").strip()
        body = request.get_data(cache=True) or b""
        integ = authenticate_accounting_request(
            db,
            company_id=company_id,
            api_key=api_key,
            timestamp=timestamp,
            signature=signature,
            body=body,
            require_signature=bool(signature),
        )
        if not integ:
            return None, ({"error": "unauthorized"}, 401)
        if str(integ.get("company_id") or "") != company_id:
            return None, ({"error": "company_scope_mismatch"}, 403)
        return integ, None

    @accounting_bp.get("/v2/accounting/hours")
    def accounting_pull_hours():
        integ, err = _auth_accounting()
        if err:
            return jsonify(err[0]), err[1]
        from .company_opt_in import require_lohn_enabled_or_error

        blocked = require_lohn_enabled_or_error(get_db(), integ["company_id"])
        if blocked:
            return jsonify(blocked), 403
        period = (request.args.get("period") or "").strip()
        if not period:
            from .monthly_job import previous_period

            period = previous_period()
        try:
            payload = prepare_hour_export(
                get_db(),
                company_id=integ["company_id"],
                period=period,
                mark_sent=True,
            )
        except ValueError as exc:
            code = "company_id_required" if "company" in str(exc) else "invalid_period"
            return jsonify({"error": code}), 400
        return jsonify(payload), 200

    @accounting_bp.post("/v2/accounting/hours/ack")
    def accounting_ack_hours():
        integ, err = _auth_accounting()
        if err:
            return jsonify(err[0]), err[1]
        from .company_opt_in import require_lohn_enabled_or_error

        blocked = require_lohn_enabled_or_error(get_db(), integ["company_id"])
        if blocked:
            return jsonify(blocked), 403
        data = request.get_json(silent=True) or {}
        period = str(data.get("period") or "").strip()
        fingerprint = str(data.get("fingerprint") or "").strip()
        body_company = str(data.get("companyId") or data.get("company_id") or "").strip()
        if body_company and body_company != integ["company_id"]:
            return jsonify({"error": "company_id_mismatch"}), 403
        if not period:
            return jsonify({"error": "period_required"}), 400
        try:
            normalize_period(period)
        except ValueError:
            return jsonify({"error": "invalid_period"}), 400
        result = repo.ack_hour_export(
            get_db(),
            company_id=integ["company_id"],
            period=period,
            fingerprint=fingerprint,
        )
        return jsonify(result), (200 if result.get("ok") else 404)

    @accounting_bp.post("/v2/accounting/statements")
    def accounting_push_statements():
        integ, err = _auth_accounting()
        if err:
            return jsonify(err[0]), err[1]
        from .company_opt_in import require_lohn_enabled_or_error

        blocked = require_lohn_enabled_or_error(get_db(), integ["company_id"])
        if blocked:
            return jsonify(blocked), 403
        data = request.get_json(silent=True) or {}
        period = str(data.get("period") or "").strip()
        body_company = str(
            data.get("companyId") or data.get("company_id") or (data.get("company") or {}).get("id") or ""
        ).strip()
        if not body_company:
            return jsonify({"error": "company_id_required"}), 400
        if body_company != integ["company_id"]:
            return jsonify({"error": "company_id_mismatch"}), 403
        statements = data.get("statements") or data.get("items") or []
        if not isinstance(statements, list):
            return jsonify({"error": "statements_must_be_array"}), 400
        try:
            normalize_period(period)
        except ValueError:
            return jsonify({"error": "invalid_period"}), 400
        result = ingest_statements(
            get_db(),
            company_id=integ["company_id"],
            period=period,
            statements=statements,
            external_ref=str(data.get("externalRef") or ""),
            notes=str(data.get("notes") or ""),
        )
        return jsonify(result), (200 if result.get("ok") else 400)

    @accounting_bp.get("/v2/accounting/company")
    def accounting_get_company():
        integ, err = _auth_accounting()
        if err:
            return jsonify(err[0]), err[1]
        from .company_opt_in import require_lohn_enabled_or_error

        blocked = require_lohn_enabled_or_error(get_db(), integ["company_id"])
        if blocked:
            return jsonify(blocked), 403
        try:
            payload = company_upsert_payload(get_db(), integ["company_id"])
        except LookupError:
            return jsonify({"error": "company_not_found"}), 404
        except ValueError:
            return jsonify({"error": "company_id_required"}), 400
        return jsonify(payload), 200

    @accounting_bp.post("/v2/accounting/company/upsert")
    def accounting_company_upsert_mirror():
        """Platform mirror of WorkPass Lohn POST /v1/company/upsert (Firma-ID scoped)."""
        integ, err = _auth_accounting()
        if err:
            return jsonify(err[0]), err[1]
        from .company_opt_in import require_lohn_enabled_or_error

        blocked = require_lohn_enabled_or_error(get_db(), integ["company_id"])
        if blocked:
            return jsonify(blocked), 403
        data = request.get_json(silent=True) or {}
        body_id = str(
            data.get("id") or data.get("companyId") or (data.get("company") or {}).get("id") or ""
        ).strip()
        if not body_id:
            return jsonify({"error": "company_id_required"}), 400
        if body_id != integ["company_id"]:
            return jsonify({"error": "company_id_mismatch"}), 403
        try:
            payload = company_upsert_payload(get_db(), integ["company_id"])
        except LookupError:
            return jsonify({"error": "company_not_found"}), 404
        payload["upserted"] = True
        payload["source"] = "platform_mirror"
        return jsonify(payload), 200

    # ── Admin (session auth) ───────────────────────────────────────────

    @accounting_bp.get("/payroll/accounting/platform-link")
    @require_auth
    @require_roles("superadmin")
    def admin_get_platform_link():
        link = get_platform_link(get_db())
        # Strip raw master key from HTTP response
        safe = {k: v for k, v in link.items() if k != "master_api_key"}
        return jsonify({"ok": True, "link": safe}), 200

    @accounting_bp.post("/payroll/accounting/platform-link")
    @require_auth
    @require_roles("superadmin")
    def admin_save_platform_link():
        data = request.get_json(silent=True) or {}
        link = save_platform_link(
            get_db(),
            enabled=data.get("enabled") if "enabled" in data else None,
            base_url=data.get("baseUrl") if "baseUrl" in data else None,
            master_api_key=data.get("masterApiKey") if "masterApiKey" in data else None,
            company_upsert_path=data.get("companyUpsertPath") if "companyUpsertPath" in data else None,
            hours_webhook_path=data.get("hoursWebhookPath") if "hoursWebhookPath" in data else None,
            platform_public_url=data.get("platformPublicUrl") if "platformPublicUrl" in data else None,
            auto_provision=data.get("autoProvision") if "autoProvision" in data else None,
            default_run_day=data.get("runDay") if "runDay" in data else None,
        )
        safe = {k: v for k, v in link.items() if k != "master_api_key"}
        return jsonify({"ok": True, "link": safe}), 200

    @accounting_bp.post("/payroll/accounting/platform-link/test")
    @require_auth
    @require_roles("superadmin")
    def admin_test_platform_link():
        result = test_platform_link_connectivity(get_db())
        code = 200 if result.get("ok") else 400
        return jsonify(result), code

    @accounting_bp.post("/payroll/accounting/provision/<company_id>")
    @require_auth
    @require_roles("superadmin")
    def admin_provision_company(company_id: str):
        data = request.get_json(silent=True) or {}
        if bool(data.get("enable") or data.get("force")):
            result = set_workpass_lohn_enabled(
                get_db(), company_id, enabled=True, provision_if_enabled=True
            )
        else:
            result = provision_company_for_lohn(
                get_db(),
                company_id,
                force=bool(data.get("force", False)),
            )
        code = 200 if result.get("ok") or result.get("skipped") else 400
        return jsonify(result), code

    @accounting_bp.get("/payroll/accounting/company-settings")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_get_company_lohn_settings():
        user = g.current_user
        company_id = user.get("company_id") if user["role"] != "superadmin" else (
            request.args.get("company_id") or user.get("company_id")
        )
        if not company_id:
            return jsonify({"error": "company_id_required"}), 400
        if user["role"] != "superadmin" and company_id != user.get("company_id"):
            return jsonify({"error": "forbidden"}), 403
        enabled = is_workpass_lohn_enabled(get_db(), company_id)
        integ = repo.get_integration(get_db(), company_id)
        return jsonify(
            {
                "ok": True,
                "companyId": company_id,
                "workpassLohnEnabled": enabled,
                "integrationEnabled": bool(integ and int(integ.get("enabled") or 0)),
                "optional": True,
            }
        ), 200

    @accounting_bp.put("/payroll/accounting/company-settings")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_put_company_lohn_settings():
        user = g.current_user
        data = request.get_json(silent=True) or {}
        company_id = user.get("company_id") if user["role"] != "superadmin" else (
            data.get("companyId") or request.args.get("company_id") or user.get("company_id")
        )
        if not company_id:
            return jsonify({"error": "company_id_required"}), 400
        if user["role"] != "superadmin" and company_id != user.get("company_id"):
            return jsonify({"error": "forbidden"}), 403
        if "workpassLohnEnabled" not in data and "enabled" not in data:
            return jsonify({"error": "workpassLohnEnabled_required"}), 400
        enabled = data.get("workpassLohnEnabled") if "workpassLohnEnabled" in data else data.get("enabled")
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() in {"1", "true", "yes", "on"}
        result = set_workpass_lohn_enabled(
            get_db(),
            str(company_id),
            enabled=bool(enabled),
            provision_if_enabled=True,
        )
        code = 200 if result.get("ok") else 400
        return jsonify(result), code

    @accounting_bp.post("/payroll/accounting/provision-all")
    @require_auth
    @require_roles("superadmin")
    def admin_provision_all():
        data = request.get_json(silent=True) or {}
        result = provision_all_active_companies(get_db(), force=bool(data.get("force", False)))
        return jsonify(result), 200

    @accounting_bp.get("/payroll/accounting/integration")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_get_integration():
        user = g.current_user
        company_id = _company_scope_for_user(user)
        if user["role"] != "superadmin":
            company_id = user.get("company_id")
        if not company_id:
            return jsonify({"error": "company_id_required"}), 400
        row = repo.get_integration(get_db(), company_id)
        return jsonify({"ok": True, "integration": row, "firmaIdHeader": "X-WorkPass-Company-Id"}), 200

    @accounting_bp.post("/payroll/accounting/integration")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_upsert_integration():
        user = g.current_user
        data = request.get_json(silent=True) or {}
        company_id = user.get("company_id") if user["role"] != "superadmin" else (
            data.get("companyId") or user.get("company_id")
        )
        if not company_id:
            return jsonify({"error": "company_id_required"}), 400
        out = repo.upsert_integration(
            get_db(),
            company_id=str(company_id),
            webhook_url=str(data.get("webhookUrl") or ""),
            enabled=bool(data.get("enabled", True)),
            run_day=int(data.get("runDay") or 1),
            rotate_key=bool(data.get("rotateKey") or data.get("createKey")),
        )
        return jsonify({"ok": True, "integration": out}), 200

    @accounting_bp.get("/payroll/statements/pending")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_pending_batches():
        user = g.current_user
        company_id = None if user["role"] == "superadmin" else user.get("company_id")
        if user["role"] == "superadmin" and request.args.get("company_id"):
            company_id = request.args.get("company_id")
        batches = repo.list_pending_batches(get_db(), company_id=company_id)
        return jsonify({"ok": True, "batches": batches}), 200

    @accounting_bp.get("/payroll/statements/<batch_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_batch_detail(batch_id: str):
        user = g.current_user
        db = get_db()
        batch = repo.get_batch(db, batch_id)
        if not batch:
            return jsonify({"error": "not_found"}), 404
        if user["role"] != "superadmin" and batch["company_id"] != user.get("company_id"):
            return jsonify({"error": "forbidden"}), 403
        statements = repo.list_batch_statements(db, batch_id)
        return jsonify({"ok": True, "batch": batch, "statements": statements}), 200

    @accounting_bp.post("/payroll/statements/<batch_id>/approve")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_approve_batch(batch_id: str):
        user = g.current_user
        company_scope = None if user["role"] == "superadmin" else user.get("company_id")
        result = approve_batch(
            get_db(),
            batch_id=batch_id,
            actor_user_id=str(user.get("id") or ""),
            company_id=company_scope,
        )
        code = 200 if result.get("ok") else (403 if result.get("error") == "forbidden_company" else 400)
        return jsonify(result), code

    @accounting_bp.post("/payroll/statements/<batch_id>/reject")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_reject_batch(batch_id: str):
        user = g.current_user
        data = request.get_json(silent=True) or {}
        company_scope = None if user["role"] == "superadmin" else user.get("company_id")
        result = reject_batch(
            get_db(),
            batch_id=batch_id,
            actor_user_id=str(user.get("id") or ""),
            company_id=company_scope,
            reason=str(data.get("reason") or ""),
        )
        code = 200 if result.get("ok") else (403 if result.get("error") == "forbidden_company" else 400)
        return jsonify(result), code

    @accounting_bp.post("/payroll/accounting/export-now")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_export_now():
        user = g.current_user
        data = request.get_json(silent=True) or {}
        company_id = user.get("company_id") if user["role"] != "superadmin" else (
            data.get("companyId") or request.args.get("company_id") or user.get("company_id")
        )
        if not company_id:
            return jsonify({"error": "company_id_required"}), 400
        period = str(data.get("period") or "").strip()
        notify = bool(data.get("notify", True))
        try:
            if notify:
                from .monthly_job import previous_period

                result = notify_hours_ready(
                    get_db(),
                    company_id=str(company_id),
                    period=period or previous_period(),
                )
            else:
                if not period:
                    from .monthly_job import previous_period

                    period = previous_period()
                payload = prepare_hour_export(get_db(), company_id=str(company_id), period=period, mark_sent=False)
                result = {"ok": True, "payload": payload}
        except ValueError:
            return jsonify({"error": "invalid_period"}), 400
        return jsonify(result), 200

    @accounting_bp.post("/payroll/accounting/run-monthly")
    @require_auth
    @require_roles("superadmin")
    def admin_run_monthly():
        data = request.get_json(silent=True) or {}
        result = run_monthly_accounting_exports(
            get_db(),
            force=bool(data.get("force", True)),
            period=str(data.get("period") or "").strip() or None,
        )
        return jsonify(result), 200

    flask_app.register_blueprint(accounting_bp, url_prefix="/api")
