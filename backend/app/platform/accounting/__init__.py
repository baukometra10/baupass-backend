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
    from .hours_service import build_employee_master_list, normalize_period
    from .monthly_job import run_monthly_accounting_exports
    from .platform_link import (
        get_platform_link,
        provision_all_active_companies,
        provision_company_for_lohn,
        save_platform_link,
        test_platform_link_connectivity,
    )
    from .company_opt_in import is_workpass_lohn_enabled, set_workpass_lohn_enabled
    from .messages_inbox import (
        ack_message_to_lohn,
        count_pending_accounting_messages,
        create_test_accounting_message,
        dismiss_all_message_banners,
        dismiss_message_banner,
        handle_inbound_lohn_webhook,
        list_pending_accounting_messages,
        platform_webhook_public_path,
        pull_pending_messages_from_lohn,
        verify_platform_webhook_auth,
    )
    from .schema import ensure_accounting_schema
    from .service import (
        approve_batch,
        confirm_period_handoff,
        ingest_statements,
        notify_hours_ready,
        period_handoff_gate,
        prepare_hour_export,
        prepare_payroll_batch,
        push_payroll_batch_to_lohn,
        reject_batch,
        request_period_handoff,
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

    @accounting_bp.get("/v2/accounting/employees")
    def accounting_pull_employees():
        """platform.employees.v1 — full master; with ?period= only after platform confirmation."""
        integ, err = _auth_accounting()
        if err:
            return jsonify(err[0]), err[1]
        from .company_opt_in import require_lohn_enabled_or_error

        blocked = require_lohn_enabled_or_error(get_db(), integ["company_id"])
        if blocked:
            return jsonify(blocked), 403
        period = (request.args.get("period") or "").strip()
        if period:
            try:
                gate = period_handoff_gate(get_db(), company_id=integ["company_id"], period=period)
            except ValueError:
                return jsonify({"error": "invalid_period"}), 400
            if gate:
                return jsonify(gate), 409
        try:
            payload = build_employee_master_list(get_db(), company_id=integ["company_id"])
        except ValueError:
            return jsonify({"error": "company_id_required"}), 400
        if period:
            payload["period"] = period
            payload["handoffStatus"] = "confirmed"
        return jsonify(payload), 200

    @accounting_bp.post("/v2/accounting/period-request")
    @accounting_bp.get("/v2/accounting/period-request")
    def accounting_period_request():
        """
        Lohn asks for employees + Abrechnung inputs for a company/period.
        Platform holds data until Ops confirms handoff.
        """
        integ, err = _auth_accounting()
        if err:
            return jsonify(err[0]), err[1]
        from .company_opt_in import require_lohn_enabled_or_error

        blocked = require_lohn_enabled_or_error(get_db(), integ["company_id"])
        if blocked:
            return jsonify(blocked), 403
        data = request.get_json(silent=True) or {}
        period = (
            (request.args.get("period") or "").strip()
            or str(data.get("period") or "").strip()
        )
        if not period:
            from .monthly_job import previous_period

            period = previous_period()
        body_company = str(
            data.get("companyId") or data.get("company_id") or (data.get("company") or {}).get("id") or ""
        ).strip()
        if body_company and body_company != integ["company_id"]:
            return jsonify({"error": "company_id_mismatch"}), 403
        if request.method == "GET":
            req = repo.get_period_request(get_db(), company_id=integ["company_id"], period=period)
            if not req:
                return jsonify(
                    {
                        "ok": True,
                        "status": "missing",
                        "period": period,
                        "companyId": integ["company_id"],
                        "message": "No request yet — POST /api/v2/accounting/period-request",
                    }
                ), 200
            return jsonify({"ok": True, "request": req, "status": req.get("status"), "period": period}), 200
        try:
            result = request_period_handoff(
                get_db(),
                company_id=integ["company_id"],
                period=period,
                source="lohn",
                note=str(data.get("note") or data.get("message") or "")[:500],
                external_ref=str(data.get("externalRef") or "")[:120],
            )
        except ValueError as exc:
            code = "company_id_required" if "company" in str(exc) else "invalid_period"
            return jsonify({"error": code}), 400
        status_code = 200 if result.get("ok") else 400
        if result.get("status") == "pending_confirmation":
            status_code = 202
        return jsonify(result), status_code

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
            gate = period_handoff_gate(get_db(), company_id=integ["company_id"], period=period)
        except ValueError:
            return jsonify({"error": "invalid_period"}), 400
        if gate:
            return jsonify(gate), 409
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
        payload["handoffStatus"] = "confirmed"
        return jsonify(payload), 200

    @accounting_bp.get("/v2/accounting/payroll-batch")
    @accounting_bp.post("/v2/accounting/payroll-batch")
    def accounting_payroll_batch():
        """platform.payroll.batch.v1 — only after platform confirmed the period handoff."""
        integ, err = _auth_accounting()
        if err:
            return jsonify(err[0]), err[1]
        from .company_opt_in import require_lohn_enabled_or_error

        blocked = require_lohn_enabled_or_error(get_db(), integ["company_id"])
        if blocked:
            return jsonify(blocked), 403
        data = request.get_json(silent=True) or {}
        period = (
            (request.args.get("period") or "").strip()
            or str(data.get("period") or "").strip()
        )
        body_company = str(
            data.get("companyId") or data.get("company_id") or (data.get("company") or {}).get("id") or ""
        ).strip()
        if body_company and body_company != integ["company_id"]:
            return jsonify({"error": "company_id_mismatch"}), 403
        if not period:
            from .monthly_job import previous_period

            period = previous_period()
        try:
            gate = period_handoff_gate(get_db(), company_id=integ["company_id"], period=period)
        except ValueError:
            return jsonify({"error": "invalid_period"}), 400
        if gate:
            return jsonify(gate), 409
        try:
            payload = prepare_payroll_batch(
                get_db(),
                company_id=integ["company_id"],
                period=period,
                mark_sent=True,
            )
        except ValueError as exc:
            code = "company_id_required" if "company" in str(exc) else "invalid_period"
            return jsonify({"error": code}), 400
        payload["handoffStatus"] = "confirmed"
        return jsonify(payload), 200

    @accounting_bp.get("/v2/accounting/statements")
    def accounting_list_statements():
        """Lohn pulls Abrechnung batch status (pending_approval / approved / rejected)."""
        integ, err = _auth_accounting()
        if err:
            return jsonify(err[0]), err[1]
        from .company_opt_in import require_lohn_enabled_or_error

        blocked = require_lohn_enabled_or_error(get_db(), integ["company_id"])
        if blocked:
            return jsonify(blocked), 403
        period = (request.args.get("period") or "").strip()
        if period:
            try:
                normalize_period(period)
            except ValueError:
                return jsonify({"error": "invalid_period"}), 400
        batches = repo.list_company_statement_batches(
            get_db(),
            company_id=integ["company_id"],
            period=period or None,
            limit=int(request.args.get("limit") or 50),
        )
        out_batches = []
        for b in batches:
            statements = repo.list_batch_statements(get_db(), b["id"])
            out_batches.append(
                {
                    "batchId": b.get("id"),
                    "companyId": b.get("company_id"),
                    "period": b.get("period"),
                    "status": b.get("status"),
                    "createdAt": b.get("created_at"),
                    "approvedAt": b.get("approved_at"),
                    "rejectedAt": b.get("rejected_at"),
                    "externalRef": b.get("external_ref"),
                    "notes": b.get("notes"),
                    "statementCount": len(statements),
                    "statements": [
                        {
                            "id": s.get("id"),
                            "employeeId": s.get("worker_id"),
                            "workerId": s.get("worker_id"),
                            "firstName": s.get("first_name"),
                            "lastName": s.get("last_name"),
                            "badgeId": s.get("badge_id"),
                            "gross": s.get("gross"),
                            "net": s.get("net"),
                            "currency": s.get("currency") or "EUR",
                            "released": bool(s.get("released_at")),
                            "filename": s.get("filename"),
                        }
                        for s in statements
                    ],
                }
            )
        return jsonify(
            {
                "ok": True,
                "format": "platform.statements.status.v1",
                "product": "WorkPass Lohn",
                "companyId": integ["company_id"],
                "period": period or None,
                "batchCount": len(out_batches),
                "batches": out_batches,
                "note": "Push new Abrechnungen via POST /api/v2/accounting/statements; approval stays human on platform",
            }
        ), 200

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

    @accounting_bp.post("/v2/accounting/employee-data-alerts")
    def accounting_push_employee_data_alerts():
        """WorkPass Lohn / Steuer → platform: missing employee fields for a period."""
        integ, err = _auth_accounting()
        if err:
            return jsonify(err[0]), err[1]
        from .company_opt_in import require_lohn_enabled_or_error

        blocked = require_lohn_enabled_or_error(get_db(), integ["company_id"])
        if blocked:
            return jsonify(blocked), 403
        data = request.get_json(silent=True) or {}
        body_company = str(
            data.get("companyId") or data.get("company_id") or (data.get("company") or {}).get("id") or ""
        ).strip()
        if body_company and body_company != integ["company_id"]:
            return jsonify({"error": "company_id_mismatch"}), 403
        issues = data.get("issues") or data.get("alerts") or data.get("items") or []
        if isinstance(data.get("issue"), dict):
            issues = [data["issue"]]
        if not isinstance(issues, list):
            return jsonify({"error": "issues_must_be_array"}), 400
        result = repo.ingest_lohn_data_alerts(
            get_db(),
            company_id=integ["company_id"],
            period=str(data.get("period") or "").strip(),
            issues=issues,
            external_ref=str(data.get("externalRef") or ""),
        )
        return jsonify(result), (200 if result.get("ok") else 400)

    @accounting_bp.post("/v2/accounting/webhook")
    @accounting_bp.post("/v2/accounting/hooks/lohn")
    @accounting_bp.post("/workpass/webhooks/accounting")
    def accounting_platform_webhook():
        """
        Inbound WORKPASS_PLATFORM_WEBHOOK_URL target.
        Canonical (Lohn v2.6+): POST /api/workpass/webhooks/accounting
        Legacy: /api/v2/accounting/webhook
        Handles employees.list.requested, payroll.month.requested, payslip.released,
        and accounting.message (store + pull /v1/messages/pending).
        """
        db = get_db()
        ensure_accounting_schema(db)
        raw = request.get_data(cache=True) or b""
        data = request.get_json(silent=True) or {}
        company_hint = str(
            request.headers.get("X-WorkPass-Company-Id")
            or request.headers.get("X-Company-Id")
            or data.get("companyId")
            or data.get("company_id")
            or ""
        ).strip()
        auth = verify_platform_webhook_auth(
            db,
            headers={k: v for k, v in request.headers.items()},
            body=raw,
            company_id=company_hint,
        )
        if not auth.get("ok"):
            return jsonify({"error": auth.get("error") or "unauthorized", "hint": auth.get("hint")}), 401
        result = handle_inbound_lohn_webhook(
            db,
            data=data if isinstance(data, dict) else {},
            company_id=str(auth.get("companyId") or company_hint or ""),
        )
        # Never return a tuple accidentally from handler
        if isinstance(result, tuple):
            result = result[0] if result else {"ok": False, "error": "handler_error"}
        result["webhookPath"] = platform_webhook_public_path()
        result["webhookPaths"] = [
            "/api/workpass/webhooks/accounting",
            "/api/v2/accounting/webhook",
            "/api/v2/accounting/hooks/lohn",
        ]
        return jsonify(result), 200

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

    @accounting_bp.get("/v2/accounting/company/access")
    def accounting_get_company_access():
        """
        WorkPass Lohn pulls company-admin username/password for collaboration.
        Auth: per-company accounting key + X-WorkPass-Company-Id.
        """
        integ, err = _auth_accounting()
        if err:
            return jsonify(err[0]), err[1]
        from .company_opt_in import require_lohn_enabled_or_error
        from . import repository as repo

        blocked = require_lohn_enabled_or_error(get_db(), integ["company_id"])
        if blocked:
            return jsonify(blocked), 403
        login = repo.get_lohn_login(get_db(), integ["company_id"])
        if not login:
            # Fall back to username-only from users table
            username = ""
            try:
                admin_row = get_db().execute(
                    """
                    SELECT username FROM users
                    WHERE company_id = ? AND role = 'company-admin'
                    ORDER BY id LIMIT 1
                    """,
                    (integ["company_id"],),
                ).fetchone()
                username = str((admin_row["username"] if admin_row else "") or "").strip()
            except Exception:
                username = ""
            return jsonify(
                {
                    "ok": False,
                    "error": "password_not_available",
                    "message": "No stored password for Lohn. Re-provision company or reset admin password to push credentials.",
                    "companyId": integ["company_id"],
                    "username": username,
                    "login": {"username": username, "password": ""} if username else None,
                }
            ), 409
        access = {
            "username": login["username"],
            "password": login["password"],
            "role": "company-admin",
            "firmaId": integ["company_id"],
            "companyId": integ["company_id"],
        }
        return jsonify(
            {
                "ok": True,
                "product": "WorkPass Lohn",
                "companyId": integ["company_id"],
                "access": access,
                "login": access,
                "username": access["username"],
                "password": access["password"],
            }
        ), 200

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
        platform_url = str(link.get("platform_public_url") or "").rstrip("/")
        safe["platformWebhookUrl"] = (
            f"{platform_url}{platform_webhook_public_path()}"
            if platform_url
            else platform_webhook_public_path()
        )
        safe["platformWebhookUrls"] = [
            f"{platform_url}/api/workpass/webhooks/accounting" if platform_url else "/api/workpass/webhooks/accounting",
            f"{platform_url}/api/v2/accounting/webhook" if platform_url else "/api/v2/accounting/webhook",
        ]
        safe["platformWebhookEnv"] = "WORKPASS_PLATFORM_WEBHOOK_URL"
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
        platform_url = str(link.get("platform_public_url") or "").rstrip("/")
        safe["platformWebhookUrl"] = (
            f"{platform_url}{platform_webhook_public_path()}"
            if platform_url
            else platform_webhook_public_path()
        )
        safe["platformWebhookUrls"] = [
            f"{platform_url}/api/workpass/webhooks/accounting" if platform_url else "/api/workpass/webhooks/accounting",
            f"{platform_url}/api/v2/accounting/webhook" if platform_url else "/api/v2/accounting/webhook",
        ]
        safe["platformWebhookEnv"] = "WORKPASS_PLATFORM_WEBHOOK_URL"
        return jsonify({"ok": True, "link": safe}), 200

    @accounting_bp.post("/payroll/accounting/platform-link/test")
    @require_auth
    @require_roles("superadmin")
    def admin_test_platform_link():
        result = test_platform_link_connectivity(get_db())
        if not result.get("ok") and not result.get("message"):
            result["message"] = str(result.get("error") or "test_failed")
        code = 200 if result.get("ok") else 400
        return jsonify(result), code

    @accounting_bp.post("/payroll/accounting/provision/<company_id>")
    @require_auth
    @require_roles("superadmin")
    def admin_provision_company(company_id: str):
        data = request.get_json(silent=True) or {}
        if bool(data.get("enable") or data.get("force")):
            result = set_workpass_lohn_enabled(
                get_db(),
                company_id,
                enabled=True,
                provision_if_enabled=True,
                admin_username=data.get("username") or data.get("adminUsername"),
                admin_password=data.get("password") or data.get("adminPassword"),
            )
        else:
            result = provision_company_for_lohn(
                get_db(),
                company_id,
                force=bool(data.get("force", False)),
                admin_username=data.get("username") or data.get("adminUsername"),
                admin_password=data.get("password") or data.get("adminPassword"),
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
            admin_username=data.get("username") or data.get("adminUsername"),
            admin_password=data.get("password") or data.get("adminPassword"),
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

    @accounting_bp.get("/payroll/accounting/employees")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_list_employees_for_lohn():
        """Session preview: what Lohn receives for employee master / payroll readiness."""
        user = g.current_user
        company_id = user.get("company_id") if user["role"] != "superadmin" else (
            request.args.get("company_id") or user.get("company_id")
        )
        if not company_id:
            return jsonify({"error": "company_id_required"}), 400
        if user["role"] != "superadmin" and company_id != user.get("company_id"):
            return jsonify({"error": "forbidden"}), 403
        try:
            payload = build_employee_master_list(get_db(), company_id=str(company_id))
        except ValueError:
            return jsonify({"error": "company_id_required"}), 400
        period = (request.args.get("period") or "").strip()
        if period:
            try:
                hours = prepare_hour_export(
                    get_db(), company_id=str(company_id), period=period, mark_sent=False
                )
                payload["period"] = hours.get("period")
                payload["totalHours"] = hours.get("totalHours")
                payload["totalGrossEstimate"] = hours.get("totalGrossEstimate")
                payload["incompleteEmployees"] = hours.get("incompleteEmployees") or []
                # Merge period hours onto employees for Ops preview
                by_id = {str(r.get("employeeId")): r for r in (hours.get("rows") or [])}
                for emp in payload.get("employees") or []:
                    row = by_id.get(str(emp.get("employeeId")))
                    if row:
                        emp["hours"] = row.get("hours")
                        emp["grossEstimate"] = row.get("grossEstimate")
                        emp["missingFields"] = row.get("missingFields") or emp.get("missingFields")
                        emp["payrollReady"] = row.get("payrollReady")
            except ValueError:
                return jsonify({"error": "invalid_period"}), 400
        return jsonify(payload), 200

    @accounting_bp.get("/payroll/accounting/data-alerts")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_list_data_alerts():
        user = g.current_user
        company_id = None if user["role"] == "superadmin" else user.get("company_id")
        if user["role"] == "superadmin" and request.args.get("company_id"):
            company_id = request.args.get("company_id")
        alerts = repo.list_open_lohn_data_alerts(get_db(), company_id=company_id)
        return jsonify({"ok": True, "alerts": alerts, "count": len(alerts)}), 200

    @accounting_bp.post("/payroll/accounting/data-alerts/<alert_id>/dismiss")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_dismiss_data_alert(alert_id: str):
        user = g.current_user
        company_scope = None if user["role"] == "superadmin" else user.get("company_id")
        result = repo.dismiss_lohn_data_alert(
            get_db(),
            alert_id=alert_id,
            actor_user_id=str(user.get("id") or ""),
            company_id=company_scope,
        )
        if result.get("error") == "not_found":
            return jsonify(result), 404
        if result.get("error") == "forbidden_company":
            return jsonify(result), 403
        return jsonify(result), 200

    @accounting_bp.get("/payroll/accounting/messages")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_list_accounting_messages():
        user = g.current_user
        company_id = None if user["role"] == "superadmin" else user.get("company_id")
        if user["role"] == "superadmin" and request.args.get("company_id"):
            company_id = request.args.get("company_id")
        sync = str(request.args.get("sync") or "").strip().lower() in {"1", "true", "yes"}
        if sync and company_id:
            pull_pending_messages_from_lohn(get_db(), company_id=str(company_id))
        messages = list_pending_accounting_messages(get_db(), company_id=company_id)
        notifications = [m for m in messages if m.get("bannerVisible")]
        link = get_platform_link(get_db())
        platform_url = str(link.get("platform_public_url") or "").rstrip("/")
        webhook_url = (
            f"{platform_url}{platform_webhook_public_path()}"
            if platform_url
            else platform_webhook_public_path()
        )
        return jsonify(
            {
                "ok": True,
                "messages": messages,
                "notifications": notifications,
                "count": len(messages),
                "notificationCount": len(notifications),
                "webhookUrl": webhook_url,
                "webhookEnv": "WORKPASS_PLATFORM_WEBHOOK_URL",
            }
        ), 200

    @accounting_bp.get("/payroll/accounting/messages/counts")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_count_accounting_messages():
        user = g.current_user
        company_id = None if user["role"] == "superadmin" else user.get("company_id")
        if user["role"] == "superadmin" and request.args.get("company_id"):
            company_id = request.args.get("company_id")
        counts = count_pending_accounting_messages(get_db(), company_id=company_id)
        return jsonify({"ok": True, **counts}), 200

    @accounting_bp.post("/payroll/accounting/messages/dismiss-banners")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_dismiss_all_message_banners():
        user = g.current_user
        company_scope = None if user["role"] == "superadmin" else user.get("company_id")
        if user["role"] == "superadmin":
            data = request.get_json(silent=True) or {}
            company_scope = data.get("companyId") or request.args.get("company_id") or company_scope
        result = dismiss_all_message_banners(
            get_db(),
            actor_user_id=str(user.get("id") or ""),
            company_id=str(company_scope) if company_scope else None,
        )
        return jsonify(result), 200

    @accounting_bp.post("/payroll/accounting/messages/<message_id>/dismiss-banner")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_dismiss_message_banner(message_id: str):
        """Hide dashboard toast only — inbox stays unread; no Lohn ack."""
        user = g.current_user
        company_scope = None if user["role"] == "superadmin" else user.get("company_id")
        result = dismiss_message_banner(
            get_db(),
            message_id=message_id,
            actor_user_id=str(user.get("id") or ""),
            company_id=company_scope,
        )
        if result.get("error") == "not_found":
            return jsonify(result), 404
        if result.get("error") == "forbidden_company":
            return jsonify(result), 403
        if not result.get("ok"):
            return jsonify(result), 400
        return jsonify(result), 200

    @accounting_bp.post("/payroll/accounting/messages/sync")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_sync_accounting_messages():
        user = g.current_user
        data = request.get_json(silent=True) or {}
        company_id = user.get("company_id") if user["role"] != "superadmin" else (
            data.get("companyId") or request.args.get("company_id") or user.get("company_id")
        )
        result = pull_pending_messages_from_lohn(
            get_db(), company_id=str(company_id) if company_id else None
        )
        code = 200 if result.get("ok") or result.get("skipped") else 400
        return jsonify(result), code

    @accounting_bp.post("/payroll/accounting/messages/test")
    @require_auth
    @require_roles("superadmin")
    def admin_test_accounting_message():
        """Inject a simulated Lohn accounting.message for live UI verification."""
        data = request.get_json(silent=True) or {}
        company_id = str(
            data.get("companyId")
            or request.args.get("company_id")
            or ""
        ).strip()
        if not company_id:
            return jsonify({"error": "company_id_required", "hint": "companyId im Body oder ?company_id="}), 400
        result = create_test_accounting_message(
            get_db(),
            company_id=company_id,
            subject=str(data.get("subject") or ""),
            body=str(data.get("body") or ""),
            period=str(data.get("period") or ""),
            worker_id=str(data.get("workerId") or data.get("employeeId") or ""),
            kind=str(data.get("kind") or "missing_data"),
        )
        code = 200 if result.get("ok") else 400
        return jsonify(result), code

    @accounting_bp.post("/payroll/accounting/messages/<message_id>/open")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_open_accounting_message(message_id: str):
        """Open/click: mark read + ack to WorkPass Lohn — message leaves inbox."""
        user = g.current_user
        company_scope = None if user["role"] == "superadmin" else user.get("company_id")
        result = ack_message_to_lohn(
            get_db(),
            message_id=message_id,
            actor_user_id=str(user.get("id") or ""),
            company_id=company_scope,
        )
        if result.get("error") == "not_found":
            return jsonify(result), 404
        if result.get("error") == "forbidden_company":
            return jsonify(result), 403
        return jsonify(result), 200

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

    @accounting_bp.get("/payroll/accounting/period-requests")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_list_period_requests():
        user = g.current_user
        company_id = None if user["role"] == "superadmin" else user.get("company_id")
        if user["role"] == "superadmin" and request.args.get("company_id"):
            company_id = request.args.get("company_id")
        status = (request.args.get("status") or "pending_confirmation").strip()
        if status in {"all", "*"}:
            status = None
        rows = repo.list_period_requests(get_db(), company_id=company_id, status=status)
        return jsonify({"ok": True, "requests": rows, "count": len(rows)}), 200

    @accounting_bp.post("/payroll/accounting/period-requests/<request_id>/confirm")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_confirm_period_request(request_id: str):
        """Bestätigen: Mitarbeiter + Abrechnungsdaten an WorkPass Lohn übergeben."""
        user = g.current_user
        company_scope = None if user["role"] == "superadmin" else user.get("company_id")
        result = confirm_period_handoff(
            get_db(),
            request_id=request_id,
            actor_user_id=str(user.get("id") or ""),
            company_id=company_scope,
        )
        if result.get("error") == "not_found":
            return jsonify(result), 404
        if result.get("error") == "forbidden_company":
            return jsonify(result), 403
        code = 200 if result.get("ok") else 400
        return jsonify(result), code

    @accounting_bp.post("/payroll/accounting/period-requests/<request_id>/reject")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_reject_period_request(request_id: str):
        user = g.current_user
        data = request.get_json(silent=True) or {}
        company_scope = None if user["role"] == "superadmin" else user.get("company_id")
        result = repo.reject_period_request(
            get_db(),
            request_id=request_id,
            actor_user_id=str(user.get("id") or ""),
            company_id=company_scope,
            reason=str(data.get("reason") or ""),
        )
        if result.get("error") == "not_found":
            return jsonify(result), 404
        if result.get("error") == "forbidden_company":
            return jsonify(result), 403
        code = 200 if result.get("ok") else 400
        return jsonify(result), code

    @accounting_bp.post("/payroll/accounting/export-now")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_export_now():
        """Bestätigen & übergeben: Mitarbeiter + Abrechnung an WorkPass Lohn."""
        user = g.current_user
        data = request.get_json(silent=True) or {}
        company_id = user.get("company_id") if user["role"] != "superadmin" else (
            data.get("companyId") or request.args.get("company_id") or user.get("company_id")
        )
        if not company_id:
            return jsonify({"error": "company_id_required"}), 400
        period = str(data.get("period") or "").strip()
        if not period:
            from .monthly_job import previous_period

            period = previous_period()
        # Preview only (no handoff)
        if data.get("previewOnly") is True or data.get("confirm") is False:
            try:
                payload = prepare_payroll_batch(
                    get_db(), company_id=str(company_id), period=period, mark_sent=False
                )
                return jsonify(
                    {"ok": True, "preview": True, "capability": "platform.payroll.batch.v1", "payload": payload}
                ), 200
            except ValueError:
                return jsonify({"error": "invalid_period"}), 400
        try:
            result = confirm_period_handoff(
                get_db(),
                company_id=str(company_id),
                period=period,
                actor_user_id=str(user.get("id") or ""),
            )
        except ValueError:
            return jsonify({"error": "invalid_period"}), 400
        code = 200 if result.get("ok") else 400
        return jsonify(result), code

    @accounting_bp.post("/payroll/accounting/push-payroll-batch")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_push_payroll_batch():
        """Bestätigen (falls nötig) und Batch erneut an Lohn übergeben."""
        user = g.current_user
        data = request.get_json(silent=True) or {}
        company_id = user.get("company_id") if user["role"] != "superadmin" else (
            data.get("companyId") or request.args.get("company_id") or user.get("company_id")
        )
        if not company_id:
            return jsonify({"error": "company_id_required"}), 400
        period = str(data.get("period") or "").strip()
        if not period:
            from .monthly_job import previous_period

            period = previous_period()
        try:
            result = confirm_period_handoff(
                get_db(),
                company_id=str(company_id),
                period=period,
                actor_user_id=str(user.get("id") or ""),
            )
        except ValueError:
            return jsonify({"error": "invalid_period"}), 400
        code = 200 if result.get("ok") else 400
        return jsonify(result), code

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
