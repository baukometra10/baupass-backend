"""HTTP routes for company system transfer import/export (Enterprise + superadmin)."""
from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request

transfer_bp = Blueprint("platform_transfer", __name__)


def register_transfer_blueprint(flask_app) -> None:
    from backend.server import (
        company_has_feature,
        feature_not_available_response,
        get_company_plan,
        get_db,
        require_auth,
        require_roles,
    )

    from .export_builder import export_company_package
    from .service import job_status, run_import, start_import_job, validate_package_bytes

    def _read_upload():
        uploaded = request.files.get("file") or request.files.get("package")
        dry_run = False
        company_override = None
        merge_mode = "skip"
        if uploaded is not None:
            blob = uploaded.read()
            filename = uploaded.filename or "package.zip"
            dry_run = str(request.form.get("dryRun") or request.form.get("dry_run") or "0").strip().lower() in {
                "1",
                "true",
                "yes",
            }
            company_override = (request.form.get("companyId") or request.form.get("company_id") or "").strip() or None
            merge_mode = (request.form.get("mergeMode") or request.form.get("merge_mode") or "skip").strip()
            return blob, filename, dry_run, company_override, merge_mode
        if request.is_json:
            import json

            payload = request.get_json(silent=True) or {}
            dry_run = bool(payload.get("dryRun") or payload.get("dry_run"))
            company_override = str(payload.get("companyId") or payload.get("company_id") or "").strip() or None
            merge_mode = str(payload.get("mergeMode") or payload.get("merge_mode") or "skip").strip()
            if isinstance(payload.get("package"), (dict, list)):
                blob = json.dumps(payload["package"]).encode("utf-8")
            elif isinstance(payload.get("data"), dict):
                blob = json.dumps(payload["data"]).encode("utf-8")
            else:
                blob = json.dumps(payload).encode("utf-8")
            filename = str(payload.get("filename") or "package.json")
            return blob, filename, dry_run, company_override, merge_mode
        blob = request.get_data(cache=False, as_text=False) or b""
        filename = request.headers.get("X-Filename") or "package.bin"
        dry_run = str(request.args.get("dryRun") or "0").lower() in {"1", "true", "yes"}
        company_override = (request.args.get("companyId") or "").strip() or None
        merge_mode = (request.args.get("mergeMode") or "skip").strip()
        return blob, filename, dry_run, company_override, merge_mode

    def _authorize_transfer(db):
        """
        superadmin: full access.
        company-admin with Enterprise system_transfer: own company only (forced remap).
        office: never.
        """
        user = g.current_user or {}
        role = str(user.get("role") or "")
        if role == "office":
            return None, (jsonify({"error": "forbidden"}), 403)
        if role == "superadmin":
            return {
                "role": role,
                "company_id": None,
                "remap_to_company_id": None,
                "force_own_company": False,
            }, None
        if role == "company-admin":
            cid = str(user.get("company_id") or "").strip()
            if not cid:
                return None, (jsonify({"error": "missing_company"}), 400)
            plan = get_company_plan(db, cid)
            if not company_has_feature(plan, "system_transfer"):
                return None, feature_not_available_response("system_transfer", plan)
            return {
                "role": role,
                "company_id": cid,
                "remap_to_company_id": cid,
                "force_own_company": True,
            }, None
        return None, (jsonify({"error": "forbidden"}), 403)

    @transfer_bp.post("/api/transfer/import/validate")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def transfer_import_validate():
        db = get_db()
        access, err = _authorize_transfer(db)
        if err:
            return err
        blob, filename, *_rest = _read_upload()
        if not blob:
            return jsonify({"error": "missing_package"}), 400
        try:
            result = validate_package_bytes(blob, filename=filename)
            if access.get("force_own_company"):
                result["willRemapToCompanyId"] = access["company_id"]
                result["tenantScoped"] = True
            return jsonify(result)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @transfer_bp.post("/api/transfer/import/start")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def transfer_import_start():
        db = get_db()
        access, err = _authorize_transfer(db)
        if err:
            return err
        blob, filename, dry_run, company_override, merge_mode = _read_upload()
        if not blob:
            return jsonify({"error": "missing_package"}), 400

        actor = g.current_user or {}
        remap_to = access.get("remap_to_company_id")
        if access.get("force_own_company"):
            company_override = access["company_id"]
            remap_to = access["company_id"]
        elif company_override and access["role"] != "superadmin":
            return jsonify({"error": "forbidden_company"}), 403

        sync = str(request.args.get("sync") or request.form.get("sync") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if request.is_json:
            sync = sync or bool((request.get_json(silent=True) or {}).get("sync"))

        if sync:
            try:
                result = run_import(
                    db,
                    blob,
                    filename=filename,
                    dry_run=dry_run,
                    company_id_override=company_override,
                    actor_user_id=str(actor.get("id") or ""),
                    merge_mode=merge_mode,
                    remap_to_company_id=remap_to,
                )
                return jsonify(result)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

        job_id = start_import_job(
            get_db,
            blob,
            filename=filename,
            dry_run=dry_run,
            company_id_override=company_override,
            actor_user_id=str(actor.get("id") or ""),
            actor_name=str(actor.get("username") or actor.get("name") or ""),
            merge_mode=merge_mode,
            remap_to_company_id=remap_to,
            company_scope=access.get("company_id") or company_override or "",
            flask_app=flask_app,
        )
        return jsonify({"ok": True, "jobId": job_id})

    @transfer_bp.get("/api/transfer/import/<job_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def transfer_import_status(job_id: str):
        db = get_db()
        access, err = _authorize_transfer(db)
        if err:
            return err
        job = job_status(job_id)
        if not job:
            return jsonify({"error": "job_not_found"}), 404
        if access.get("force_own_company"):
            job_cid = str(job.get("companyId") or "").strip()
            if job_cid and job_cid != access["company_id"]:
                return jsonify({"error": "forbidden"}), 403
        return jsonify(job)

    @transfer_bp.get("/api/transfer/export")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def transfer_export():
        db = get_db()
        access, err = _authorize_transfer(db)
        if err:
            return err
        company_id = (request.args.get("companyId") or request.args.get("company_id") or "").strip()
        if access.get("force_own_company"):
            company_id = access["company_id"]
        if not company_id:
            return jsonify({"error": "missing_company_id"}), 400
        if access["role"] != "superadmin" and company_id != access.get("company_id"):
            return jsonify({"error": "forbidden_company"}), 403
        try:
            blob, meta = export_company_package(db, company_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404 if str(exc) == "company_not_found" else 400
        filename = f"workpass-transfer-{company_id}.zip"
        return Response(
            blob,
            mimetype="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Transfer-File-Count": str(meta.get("fileCount") or 0),
                "X-Transfer-Company-Id": company_id,
            },
        )

    flask_app.register_blueprint(transfer_bp)
