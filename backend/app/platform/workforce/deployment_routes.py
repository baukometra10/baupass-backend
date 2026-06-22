"""Einsatzplan API — daily sites per worker, premium PDF, bulk (plan-gated)."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, Response, g, jsonify, request

workforce_bp = Blueprint("platform_workforce", __name__)


def register_workforce_blueprint(flask_app) -> None:
    if getattr(register_workforce_blueprint, "_routes_defined", False):
        if "platform_workforce" not in flask_app.blueprints:
            flask_app.register_blueprint(workforce_bp, url_prefix="/api")
        return
    from backend.server import get_company_plan, get_db, require_auth, require_roles
    from backend.app.platform.plan_entitlements import min_plan_for_capability, plan_includes
    from backend.app.platform.plan_guard import require_plan_capability

    def _company_id() -> str:
        user = g.current_user
        payload = request.get_json(silent=True) or {}
        if user.get("role") == "superadmin":
            return str(
                request.args.get("company_id")
                or payload.get("company_id")
                or payload.get("companyId")
                or ""
            ).strip()
        return str(user.get("company_id") or "").strip()

    def _plan_allows(cap: str) -> bool:
        if g.current_user.get("role") == "superadmin":
            return True
        db = get_db()
        plan = get_company_plan(db, _company_id())
        return plan_includes(plan, min_plan_for_capability(cap))

    @workforce_bp.get("/workforce/deployment-plan")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def get_deployment_plan():
        from .deployment_store import build_month_calendar

        cid = _company_id()
        worker_id = str(request.args.get("worker_id") or request.args.get("workerId") or "").strip()
        try:
            year = int(request.args.get("year") or datetime.utcnow().year)
            month = int(request.args.get("month") or datetime.utcnow().month)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_year_month"}), 400
        lang = str(request.args.get("lang") or "de")[:2]
        if not cid or not worker_id:
            return jsonify({"error": "company_id_and_worker_id_required"}), 400
        db = get_db()
        w = db.execute(
            "SELECT id, first_name, last_name, badge_id FROM workers WHERE id = ? AND company_id = ?",
            (worker_id, cid),
        ).fetchone()
        if not w:
            return jsonify({"error": "worker_not_found"}), 404
        from .deployment_responses import attach_responses_to_days, count_declined_days, list_responses_for_month

        days = build_month_calendar(db, company_id=cid, worker_id=worker_id, year=year, month=month, lang=lang)
        responses = list_responses_for_month(db, company_id=cid, worker_id=worker_id, year=year, month=month)
        days = attach_responses_to_days(days, responses)
        declined_count = count_declined_days(days)
        plan = get_company_plan(db, cid) if g.current_user.get("role") != "superadmin" else "enterprise"
        from .deployment_month import get_month_batch

        month_batch = get_month_batch(db, cid, year, month)
        return jsonify(
            {
                "companyId": cid,
                "workerId": worker_id,
                "workerName": f"{w['first_name']} {w['last_name']}".strip(),
                "badgeId": w["badge_id"],
                "year": year,
                "month": month,
                "days": days,
                "declinedDayCount": declined_count,
                "monthBatch": month_batch,
                "capabilities": {
                    "pdf": plan_includes(plan, min_plan_for_capability("deployment_plan")),
                    "bulk": plan_includes(plan, min_plan_for_capability("deployment_plan_bulk")),
                },
            }
        )

    @workforce_bp.put("/workforce/deployment-plan")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("scheduling")
    def put_deployment_plan():
        from .deployment_store import upsert_deployment_days

        cid = _company_id()
        body = request.get_json(silent=True) or {}
        worker_id = str(body.get("workerId") or body.get("worker_id") or "").strip()
        try:
            year = int(body.get("year") or datetime.utcnow().year)
            month = int(body.get("month") or datetime.utcnow().month)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_year_month"}), 400
        days = body.get("days") or []
        if not cid or not worker_id:
            return jsonify({"error": "company_id_and_worker_id_required"}), 400
        db = get_db()
        result = upsert_deployment_days(db, company_id=cid, worker_id=worker_id, days=days, source="manual")
        result["year"] = year
        result["month"] = month
        return jsonify(result)

    @workforce_bp.post("/workforce/deployment-plan/from-shifts")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("scheduling")
    def deployment_from_shifts():
        from .deployment_store import sync_from_shift_assignments

        cid = _company_id()
        body = request.get_json(silent=True) or {}
        worker_id = str(body.get("workerId") or body.get("worker_id") or "").strip()
        year = int(body.get("year") or datetime.utcnow().year)
        month = int(body.get("month") or datetime.utcnow().month)
        if not cid or not worker_id:
            return jsonify({"error": "company_id_and_worker_id_required"}), 400
        return jsonify(sync_from_shift_assignments(db=get_db(), company_id=cid, worker_id=worker_id, year=year, month=month))

    @workforce_bp.post("/workforce/deployment-plan/rotation")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("scheduling")
    def deployment_rotation():
        from .deployment_store import fill_rotation_template

        cid = _company_id()
        body = request.get_json(silent=True) or {}
        worker_id = str(body.get("workerId") or body.get("worker_id") or "").strip()
        year = int(body.get("year") or datetime.utcnow().year)
        month = int(body.get("month") or datetime.utcnow().month)
        locations = body.get("locations") or []
        skip_weekends = bool(body.get("skipWeekends"))
        if not cid or not worker_id:
            return jsonify({"error": "company_id_and_worker_id_required"}), 400
        return jsonify(
            fill_rotation_template(
                get_db(),
                company_id=cid,
                worker_id=worker_id,
                year=year,
                month=month,
                locations=locations,
                skip_weekends=skip_weekends,
            )
        )

    @workforce_bp.post("/workforce/deployment-plan/pdf")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("deployment_plan")
    def deployment_pdf():
        from .deployment_pdf import build_deployment_plan_pdf
        from .deployment_store import build_month_calendar

        cid = _company_id()
        body = request.get_json(silent=True) or {}
        worker_id = str(body.get("workerId") or body.get("worker_id") or request.args.get("worker_id") or "").strip()
        year = int(body.get("year") or request.args.get("year") or datetime.utcnow().year)
        month = int(body.get("month") or request.args.get("month") or datetime.utcnow().month)
        lang = str(body.get("lang") or request.args.get("lang") or "de")[:2]
        if not cid or not worker_id:
            return jsonify({"error": "company_id_and_worker_id_required"}), 400
        db = get_db()
        w = db.execute(
            "SELECT id, first_name, last_name, badge_id FROM workers WHERE id = ? AND company_id = ?",
            (worker_id, cid),
        ).fetchone()
        if not w:
            return jsonify({"error": "worker_not_found"}), 404
        from .deployment_branding import resolve_company_pdf_branding

        branding = resolve_company_pdf_branding(db, cid)
        days = build_month_calendar(db, company_id=cid, worker_id=worker_id, year=year, month=month, lang=lang)
        plan = get_company_plan(db, cid)
        tier = "enterprise" if plan_includes(plan, "enterprise") else "professional"
        pdf_bytes = build_deployment_plan_pdf(
            company_name=branding.get("companyName") or "WorkPass",
            worker_name=f"{w['first_name']} {w['last_name']}".strip(),
            badge_id=w["badge_id"],
            year=year,
            month=month,
            days=days,
            lang=lang,
            plan_tier=tier,
            branding=branding,
        )
        fname = f"einsatzplan-{worker_id}-{year}-{month:02d}.pdf"
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )

    @workforce_bp.post("/workforce/deployment-plan/pdf/branding-preview")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def deployment_branding_preview_pdf():
        from .deployment_branding import resolve_company_pdf_branding
        from .deployment_pdf import branding_preview_sample_days, build_deployment_plan_pdf

        cid = _company_id()
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        body = request.get_json(silent=True) or {}
        try:
            year = int(body.get("year") or request.args.get("year") or datetime.utcnow().year)
            month = int(body.get("month") or request.args.get("month") or datetime.utcnow().month)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_year_month"}), 400
        lang = str(body.get("lang") or request.args.get("lang") or "de")[:2]
        db = get_db()
        branding = resolve_company_pdf_branding(db, cid)
        if isinstance(body.get("branding"), dict):
            from .deployment_branding import merge_pdf_branding_override

            branding = merge_pdf_branding_override(branding, body.get("branding"))
        plan = get_company_plan(db, cid)
        tier = "enterprise" if plan_includes(plan, "enterprise") else "professional"
        days = branding_preview_sample_days(year, month, lang)
        worker_label = {
            "de": "Muster · Einsatzplan-Vorschau",
            "en": "Sample · plan preview",
            "ar": "معاينة · خطة توزيع",
        }.get(lang[:2], "Muster · Einsatzplan-Vorschau")
        pdf_bytes = build_deployment_plan_pdf(
            company_name=branding.get("companyName") or "WorkPass",
            worker_name=worker_label,
            badge_id="VORSCHAU",
            year=year,
            month=month,
            days=days,
            lang=lang,
            plan_tier=tier,
            branding=branding,
        )
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": 'inline; filename="einsatzplan-branding-preview.pdf"'},
        )

    @workforce_bp.post("/workforce/deployment-plan/bulk-pdf")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("deployment_plan_bulk")
    def deployment_bulk_pdf():
        import io
        import zipfile

        from .deployment_pdf import build_deployment_plan_pdf
        from .deployment_store import build_month_calendar

        cid = _company_id()
        body = request.get_json(silent=True) or {}
        year = int(body.get("year") or datetime.utcnow().year)
        month = int(body.get("month") or datetime.utcnow().month)
        lang = str(body.get("lang") or "de")[:2]
        worker_ids = body.get("workerIds") or body.get("worker_ids")
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        db = get_db()
        from .deployment_branding import resolve_company_pdf_branding

        branding = resolve_company_pdf_branding(db, cid)
        if worker_ids:
            ids = [str(x).strip() for x in worker_ids if str(x).strip()]
        else:
            rows = db.execute(
                """
                SELECT id FROM workers
                WHERE company_id = ? AND deleted_at IS NULL
                  AND COALESCE(status, 'aktiv') NOT IN ('gesperrt', 'inactive', 'deleted')
                ORDER BY last_name, first_name
                LIMIT 200
                """,
                (cid,),
            ).fetchall()
            ids = [str(r["id"]) for r in rows]
        if not ids:
            return jsonify({"error": "no_workers"}), 400

        buf = io.BytesIO()
        generated = 0
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for wid in ids:
                w = db.execute(
                    "SELECT id, first_name, last_name, badge_id FROM workers WHERE id = ? AND company_id = ?",
                    (wid, cid),
                ).fetchone()
                if not w:
                    continue
                days = build_month_calendar(db, company_id=cid, worker_id=wid, year=year, month=month, lang=lang)
                if not any(str(d.get("location") or "").strip() for d in days):
                    continue
                pdf_bytes = build_deployment_plan_pdf(
                    company_name=branding.get("companyName") or "WorkPass",
                    worker_name=f"{w['first_name']} {w['last_name']}".strip(),
                    badge_id=w["badge_id"],
                    year=year,
                    month=month,
                    days=days,
                    lang=lang,
                    plan_tier="enterprise",
                    branding=branding,
                )
                safe = f"{w['last_name']}_{w['first_name']}_{wid}".replace(" ", "_")[:60]
                zf.writestr(f"einsatzplan-{year}-{month:02d}-{safe}.pdf", pdf_bytes)
                generated += 1
        if generated == 0:
            return jsonify({"error": "no_plans_with_locations"}), 400
        buf.seek(0)
        return Response(
            buf.getvalue(),
            mimetype="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="einsatzplaene-{cid}-{year}-{month:02d}.zip"'
            },
        )

    @workforce_bp.post("/workforce/deployment-plan/distribute")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("deployment_plan")
    def deployment_distribute():
        from .deployment_month import send_worker_plan

        cid = _company_id()
        body = request.get_json(silent=True) or {}
        worker_id = str(body.get("workerId") or "").strip()
        year = int(body.get("year") or datetime.utcnow().year)
        month = int(body.get("month") or datetime.utcnow().month)
        lang = str(body.get("lang") or "de")[:2]
        if not cid or not worker_id:
            return jsonify({"error": "company_id_and_worker_id_required"}), 400
        return jsonify(
            send_worker_plan(
                get_db(),
                company_id=cid,
                worker_id=worker_id,
                year=year,
                month=month,
                lang=lang,
            )
        )

    @workforce_bp.get("/workforce/deployment-month")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def get_deployment_month():
        from .deployment_month import get_month_batch, worker_month_summary

        cid = _company_id()
        year = int(request.args.get("year") or datetime.utcnow().year)
        month = int(request.args.get("month") or datetime.utcnow().month)
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        db = get_db()
        batch = get_month_batch(db, cid, year, month)
        workers = worker_month_summary(db, cid, year, month)
        ready_count = sum(1 for w in workers if w.get("ready"))
        declined_day_count = sum(int(w.get("declinedDayCount") or 0) for w in workers)
        from .deployment_responses import list_company_declines_for_month

        recent_declines = list_company_declines_for_month(
            db, company_id=cid, year=year, month=month, limit=30
        )
        return jsonify(
            {
                "companyId": cid,
                "year": year,
                "month": month,
                "batch": batch,
                "workers": workers,
                "readyCount": ready_count,
                "totalWorkers": len(workers),
                "declinedDayCount": declined_day_count,
                "recentDeclines": recent_declines,
            }
        )

    @workforce_bp.post("/workforce/deployment-month/prepare-next")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("scheduling")
    def deployment_prepare_next():
        from .deployment_month import copy_month_weekday_pattern, prepare_next_month_draft

        cid = _company_id()
        body = request.get_json(silent=True) or {}
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        db = get_db()
        if body.get("useAutopilotLogic"):
            return jsonify(prepare_next_month_draft(db, cid))
        ty = int(body.get("targetYear") or body.get("year") or datetime.utcnow().year)
        tm = int(body.get("targetMonth") or body.get("month") or datetime.utcnow().month)
        sy = int(body.get("sourceYear") or (ty if tm > 1 else ty - 1))
        sm = int(body.get("sourceMonth") or (tm - 1 if tm > 1 else 12))
        return jsonify(
            copy_month_weekday_pattern(
                db,
                company_id=cid,
                source_year=sy,
                source_month=sm,
                target_year=ty,
                target_month=tm,
            )
        )

    @workforce_bp.post("/workforce/deployment-month/confirm-send")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("deployment_plan")
    def deployment_confirm_send():
        from .deployment_month import confirm_and_send_month

        cid = _company_id()
        body = request.get_json(silent=True) or {}
        year = int(body.get("year") or datetime.utcnow().year)
        month = int(body.get("month") or datetime.utcnow().month)
        lang = str(body.get("lang") or "de")[:2]
        confirmed = bool(body.get("confirmSend") or body.get("userConfirmed"))
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        user = g.current_user
        result = confirm_and_send_month(
            get_db(),
            company_id=cid,
            year=year,
            month=month,
            user_id=str(user.get("id") or user.get("username") or ""),
            user_confirmed=confirmed,
            lang=lang,
            worker_ids=body.get("workerIds"),
        )
        status = 200 if result.get("ok") else 400
        return jsonify(result), status

    @workforce_bp.post("/workforce/deployment-month/reopen")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("scheduling")
    def deployment_reopen_month():
        from .deployment_month import reopen_month

        cid = _company_id()
        body = request.get_json(silent=True) or {}
        year = int(body.get("year") or datetime.utcnow().year)
        month = int(body.get("month") or datetime.utcnow().month)
        if not cid:
            return jsonify({"error": "company_id_required"}), 400
        return jsonify(reopen_month(get_db(), cid, year, month))

    flask_app.register_blueprint(workforce_bp, url_prefix="/api")
    register_workforce_blueprint._routes_defined = True
