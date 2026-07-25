"""WorkPass integrated document editor — HTTP routes."""
from __future__ import annotations

from flask import Blueprint, Flask, Response, g, jsonify, request

from .._routes import register_blueprint_once
from ..shared import company_id_from_user, forbidden_company
from .service import EditorDocsService

docs_v2_bp = Blueprint("docs_domain_v2", __name__)
_service = EditorDocsService()


def _actor_id() -> str:
    return str(g.current_user.get("id") or g.current_user.get("username") or "")


def _actor_name() -> str:
    return str(g.current_user.get("name") or g.current_user.get("username") or "").strip()


def _actor_role() -> str:
    return str(g.current_user.get("role") or "").strip().lower()


def _resolve_company_id(data: dict | None = None, *, required: bool = True) -> str | None:
    data = data or {}
    role = str(g.current_user.get("role") or "")
    if role == "superadmin":
        cid = str(
            data.get("company_id")
            or data.get("companyId")
            or request.args.get("company_id")
            or request.args.get("companyId")
            or ""
        ).strip()
        if required and not cid:
            return None
        return cid or None
    return company_id_from_user(allow_query=True)



def _payload_is_contract(data: dict | None) -> bool:
    data = data or {}
    mode = str(data.get("mode") or "").strip().lower()
    contract_id = str(data.get("contractId") or data.get("contract_id") or "").strip()
    return mode == "contract" or bool(contract_id)


def _doc_is_contract(doc: dict | None) -> bool:
    if not doc:
        return False
    if str(doc.get("contract_id") or "").strip():
        return True
    return str(doc.get("mode") or "").strip().lower() == "contract"


def _redact_doc_body(doc: dict | None) -> dict | None:
    """Hide document body when owner step-up is locked (list metadata stays)."""
    if not doc:
        return doc
    out = dict(doc)
    out["bodyRedacted"] = True
    out["contentHtml"] = ""
    out["content_html"] = ""
    out["contentText"] = ""
    out["content_text"] = ""
    return out


def _docs_body_unlocked(db, company_id: str, *, doc: dict | None = None) -> bool:
    """General docs are always readable; contract-linked docs need owner unlock."""
    if not _doc_is_contract(doc):
        return True
    from backend.app.platform.security.contracts_lock import (
        contracts_lock_required,
        is_contracts_unlocked,
        owner_setup_required,
    )

    if owner_setup_required(db, company_id):
        return False
    if not contracts_lock_required(db, company_id):
        return True
    return is_contracts_unlocked(db, getattr(g, "token", ""), company_id)


def _contract_docs_gate(
    db,
    company_id: str,
    *,
    doc: dict | None = None,
    data: dict | None = None,
    action: str = "contract_doc",
):
    """Owner/OTP lock + turnstile deny only for Arbeitsvertrag / contract docs."""
    if not (_doc_is_contract(doc) or _payload_is_contract(data)):
        return None
    from backend.app.platform.security.contracts_lock import (
        contracts_lock_required,
        deny_turnstile_sensitive_response,
        is_contracts_unlocked,
        is_sensitive_role_blocked,
        owner_setup_required,
    )

    user = getattr(g, "current_user", None) or {}
    if is_sensitive_role_blocked(user):
        return deny_turnstile_sensitive_response(
            db, company_id, surface="docs", action=action
        )
    if owner_setup_required(db, company_id):
        return (
            jsonify(
                {
                    "error": "owner_setup_required",
                    "stepUpRequired": True,
                    "ownerSetupRequired": True,
                    "message": (
                        "Owner-Handynummer muss eingerichtet werden, "
                        "bevor Arbeitsverträge nutzbar sind."
                    ),
                }
            ),
            403,
        )
    if contracts_lock_required(db, company_id) and not is_contracts_unlocked(
        db, getattr(g, "token", ""), company_id
    ):
        return (
            jsonify(
                {
                    "error": "contracts_locked",
                    "stepUpRequired": True,
                    "message": (
                        "Owner-Freischaltung nötig für Arbeitsverträge. "
                        "Bitte Code per SMS/E-Mail bestätigen."
                    ),
                }
            ),
            403,
        )
    return None


def register_docs_blueprint(flask_app: Flask) -> None:
    if getattr(register_docs_blueprint, "_routes_defined", False):
        register_blueprint_once(flask_app, docs_v2_bp, url_prefix="/api/v2")
        return

    from backend.app.platform.security.contracts_lock import (
        deny_turnstile_sensitive,
        require_owner_step_up,
    )
    from backend.server import get_db, require_auth, require_roles

    @docs_v2_bp.get("/docs")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def list_docs():
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        mode = str(request.args.get("mode") or "").strip()
        limit = int(request.args.get("limit") or 50)
        return jsonify(_service.list_docs(get_db(), company_id=cid, mode=mode, limit=limit))

    @docs_v2_bp.post("/docs")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def create_doc():
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        gate = _contract_docs_gate(get_db(), cid, data=data, action="create")
        if gate:
            return gate
        doc = _service.create_doc(
            get_db(),
            company_id=cid,
            actor_user_id=_actor_id(),
            data=data,
        )
        return jsonify({"ok": True, "document": doc}), 201

    @docs_v2_bp.get("/docs/merge-context")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def merge_context():
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        worker_id = str(request.args.get("worker_id") or request.args.get("workerId") or "").strip() or None
        ctx = _service.build_merge_context(
            get_db(), company_id=cid, worker_id=worker_id, actor_name=_actor_name()
        )
        workers = _service.list_workers_brief(get_db(), cid)
        return jsonify({**ctx, "workers": workers})

    @docs_v2_bp.post("/docs/fill-merge")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def fill_merge():
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        worker_id = str(data.get("workerId") or data.get("worker_id") or "").strip() or None
        html = str(data.get("contentHtml") or data.get("content_html") or "")
        header_html = str(data.get("headerHtml") or data.get("header_html") or "")
        footer_html = str(data.get("footerHtml") or data.get("footer_html") or "")
        result = _service.fill_merge_fields(
            get_db(),
            company_id=cid,
            content_html=html,
            header_html=header_html,
            footer_html=footer_html,
            worker_id=worker_id,
            actor_name=_actor_name(),
        )
        return jsonify({"ok": True, **result})

    @docs_v2_bp.get("/docs/shared")
    def get_shared_doc():
        """Public read-only snapshot via share token (no Bearer)."""
        from datetime import datetime, timezone

        from werkzeug.security import check_password_hash

        from . import onlyoffice as oo

        token = str(request.args.get("t") or request.args.get("token") or "").strip()
        password = str(request.args.get("password") or request.args.get("p") or "").strip()
        if not token:
            return jsonify({"error": "invalid_or_expired"}), 403

        db = get_db()
        share = _service.repo.get_share_by_token(db, token)
        doc = None
        require_approved = False
        has_password = False
        if share:
            if share.get("revoked_at"):
                return jsonify({"error": "revoked"}), 403
            exp = str(share.get("expires_at") or "")
            try:
                exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if exp_dt < datetime.now(timezone.utc):
                    return jsonify({"error": "invalid_or_expired"}), 403
            except Exception:
                return jsonify({"error": "invalid_or_expired"}), 403
            pwd_hash = str(share.get("password_hash") or "")
            has_password = bool(pwd_hash)
            if has_password:
                if not password or not check_password_hash(pwd_hash, password):
                    return jsonify(
                        {
                            "ok": False,
                            "needsPassword": True,
                            "title": "Geschütztes Dokument",
                            "error": "password_required",
                        }
                    ), 401
            require_approved = bool(int(share.get("require_approved") or 0))
            doc = _service.get_doc(db, str(share.get("document_id") or ""), company_id=str(share.get("company_id") or "") or None)
        else:
            # Legacy JWT shares
            payload = oo.verify_share_token(token)
            if not payload:
                return jsonify({"error": "invalid_or_expired"}), 403
            doc = _service.get_doc(
                db,
                str(payload.get("doc_id") or ""),
                company_id=str(payload.get("company_id") or "") or None,
            )

        if not doc:
            return jsonify({"error": "not_found"}), 404
        if require_approved and str(doc.get("status") or "") not in {"approved", "archived"}:
            return jsonify({"error": "not_approved"}), 403
        return jsonify(
            {
                "ok": True,
                "title": doc.get("title") or "Dokument",
                "contentHtml": doc.get("content_html") or "<p><br></p>",
                "status": doc.get("status") or "draft",
                "updatedAt": doc.get("updated_at"),
                "readOnly": True,
                "hasPassword": has_password,
            }
        )

    @docs_v2_bp.post("/docs/shared/unlock")
    def unlock_shared_doc():
        from datetime import datetime, timezone

        from werkzeug.security import check_password_hash

        data = request.get_json(silent=True) or {}
        token = str(data.get("t") or data.get("token") or "").strip()
        password = str(data.get("password") or "").strip()
        if not token:
            return jsonify({"error": "invalid_or_expired"}), 403
        db = get_db()
        share = _service.repo.get_share_by_token(db, token)
        if not share or share.get("revoked_at"):
            return jsonify({"error": "invalid_or_expired"}), 403
        exp = str(share.get("expires_at") or "")
        try:
            exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt < datetime.now(timezone.utc):
                return jsonify({"error": "invalid_or_expired"}), 403
        except Exception:
            return jsonify({"error": "invalid_or_expired"}), 403
        pwd_hash = str(share.get("password_hash") or "")
        if pwd_hash and (not password or not check_password_hash(pwd_hash, password)):
            return jsonify({"error": "bad_password", "needsPassword": True}), 401
        doc = _service.get_doc(
            db,
            str(share.get("document_id") or ""),
            company_id=str(share.get("company_id") or "") or None,
        )
        if not doc:
            return jsonify({"error": "not_found"}), 404
        if bool(int(share.get("require_approved") or 0)) and str(doc.get("status") or "") not in {
            "approved",
            "archived",
        }:
            return jsonify({"error": "not_approved"}), 403
        return jsonify(
            {
                "ok": True,
                "title": doc.get("title") or "Dokument",
                "contentHtml": doc.get("content_html") or "<p><br></p>",
                "status": doc.get("status") or "draft",
                "updatedAt": doc.get("updated_at"),
                "readOnly": True,
            }
        )

    @docs_v2_bp.post("/docs/import-docx")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def import_docx():
        from . import onlyoffice as oo

        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        upload = request.files.get("file") or request.files.get("docx")
        if not upload:
            return jsonify({"error": "file_required"}), 400
        raw = upload.read() or b""
        if len(raw) > 12 * 1024 * 1024:
            return jsonify({"error": "file_too_large"}), 413
        html = oo.docx_bytes_to_html(raw)
        name = str(upload.filename or "Import.docx").rsplit(".", 1)[0].strip() or "Import"
        create = str(request.form.get("create") or request.args.get("create") or "0").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not create:
            return jsonify({"ok": True, "title": name, "contentHtml": html})
        doc = _service.create_doc(
            get_db(),
            company_id=cid,
            actor_user_id=_actor_id(),
            data={
                "title": name,
                "mode": "general",
                "contentHtml": html,
            },
        )
        return jsonify({"ok": True, "document": doc, "title": name, "contentHtml": html}), 201

    @docs_v2_bp.get("/docs/templates")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def list_editor_templates():
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        actor = _actor_id()
        is_sa = _actor_role() == "superadmin"
        raw = _service.repo.list_templates(get_db(), cid)
        items = []
        for it in raw:
            row = dict(it)
            owner = str(row.get("created_by_user_id") or "")
            row["isMine"] = bool(owner and owner == actor)
            row["canDelete"] = bool(is_sa or not owner or owner == actor)
            items.append(row)
        return jsonify({"ok": True, "items": items})

    @docs_v2_bp.post("/docs/templates")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def create_editor_template():
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        layout = data.get("layout") if isinstance(data.get("layout"), dict) else {}
        from .repository import dumps_json

        tpl = _service.repo.create_template(
            get_db(),
            company_id=cid,
            title=str(data.get("title") or "Vorlage"),
            blurb=str(data.get("blurb") or ""),
            content_html=str(data.get("contentHtml") or data.get("content_html") or ""),
            layout_json=dumps_json(layout),
            actor_user_id=_actor_id(),
        )
        return jsonify({"ok": True, "template": tpl}), 201

    @docs_v2_bp.get("/docs/templates/<template_id>")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def get_editor_template(template_id: str):
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        db = get_db()
        tpl = _service.repo.get_template(db, template_id, cid)
        if not tpl:
            return jsonify({"error": "not_found"}), 404
        unlocked = _docs_body_unlocked(db, cid, doc=None)
        if not unlocked:
            tpl = dict(tpl)
            tpl["bodyRedacted"] = True
            tpl["contentHtml"] = ""
            tpl["content_html"] = ""
        return jsonify({"ok": True, "template": tpl, "stepUpRequired": not unlocked})

    @docs_v2_bp.delete("/docs/templates/<template_id>")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def delete_editor_template(template_id: str):
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        ok, err = _service.repo.delete_template_as(
            get_db(),
            template_id,
            cid,
            actor_user_id=_actor_id(),
            allow_any=_actor_role() == "superadmin",
        )
        if err == "forbidden":
            return jsonify({"error": "forbidden", "message": "Nur eigene Team-Vorlagen löschen"}), 403
        if not ok:
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True})

    @docs_v2_bp.post("/docs/suggest")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def suggest_docs():
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        result = _service.suggest(
            get_db(),
            company_id=cid,
            content_html=str(data.get("contentHtml") or data.get("content_html") or ""),
            action=str(data.get("action") or "improve"),
            lang=str(data.get("lang") or "de"),
        )
        return jsonify(result)

    @docs_v2_bp.get("/docs/<doc_id>")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def get_doc(doc_id: str):
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        db = get_db()
        doc = _service.get_doc(db, doc_id, company_id=cid)
        if not doc:
            return jsonify({"error": "not_found"}), 404
        gate = _contract_docs_gate(db, cid, doc=doc, action="get")
        if gate:
            return gate
        unlocked = _docs_body_unlocked(db, cid, doc=doc)
        if not unlocked:
            doc = _redact_doc_body(doc)
        return jsonify({"document": doc, "stepUpRequired": not unlocked})

    @docs_v2_bp.put("/docs/<doc_id>")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def update_doc(doc_id: str):
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        existing = _service.get_doc(get_db(), doc_id, company_id=cid)
        gate = _contract_docs_gate(get_db(), cid, doc=existing, data=data, action="update")
        if gate:
            return gate
        save_version = str(data.get("saveVersion", data.get("save_version", "1"))).lower() not in {
            "0",
            "false",
            "no",
        }
        doc = _service.update_doc(
            get_db(),
            doc_id,
            company_id=cid,
            actor_user_id=_actor_id(),
            data=data,
            save_version=save_version,
        )
        if not doc:
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True, "document": doc})

    @docs_v2_bp.delete("/docs/<doc_id>")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def delete_doc(doc_id: str):
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        existing = _service.get_doc(get_db(), doc_id, company_id=cid)
        gate = _contract_docs_gate(get_db(), cid, doc=existing, action="delete")
        if gate:
            return gate
        ok = _service.delete_doc(get_db(), doc_id, company_id=cid)
        if not ok:
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True})

    @docs_v2_bp.get("/docs/<doc_id>/versions")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def list_versions(doc_id: str):
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        result = _service.list_versions(get_db(), doc_id, company_id=cid)
        if result.get("error") == "not_found":
            return jsonify({"error": "not_found"}), 404
        return jsonify(result)

    @docs_v2_bp.get("/docs/<doc_id>/versions/<version_id>")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def get_version(doc_id: str, version_id: str):
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        db = get_db()
        version = _service.get_version(db, doc_id, version_id, company_id=cid)
        if not version:
            return jsonify({"error": "not_found"}), 404
        unlocked = True  # version bodies follow parent doc gate via list/get
        existing = _service.get_doc(db, doc_id, company_id=cid)
        gate = _contract_docs_gate(db, cid, doc=existing, action="version")
        if gate:
            return gate
        unlocked = _docs_body_unlocked(db, cid, doc=existing)
        if not unlocked:
            version = dict(version)
            version["bodyRedacted"] = True
            version["contentHtml"] = ""
            version["content_html"] = ""
            version["contentText"] = ""
            version["content_text"] = ""
        return jsonify({"ok": True, "version": version, "stepUpRequired": not unlocked})

    @docs_v2_bp.post("/docs/<doc_id>/versions/<version_id>/restore")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def restore_version(doc_id: str, version_id: str):
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        existing = _service.get_doc(get_db(), doc_id, company_id=cid)
        gate = _contract_docs_gate(get_db(), cid, doc=existing, data=data, action="restore")
        if gate:
            return gate
        doc = _service.restore_version(
            get_db(),
            doc_id,
            version_id,
            company_id=cid,
            actor_user_id=_actor_id(),
        )
        if not doc:
            return jsonify({"error": "not_found"}), 404
        return jsonify({"ok": True, "document": doc})

    @docs_v2_bp.get("/docs/<doc_id>/export")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def export_doc(doc_id: str):
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        existing = _service.get_doc(get_db(), doc_id, company_id=cid)
        gate = _contract_docs_gate(get_db(), cid, doc=existing, data=(request.get_json(silent=True) or {}), action="export")
        if gate:
            return gate
        doc = _service.get_doc(get_db(), doc_id, company_id=cid)
        if not doc:
            return jsonify({"error": "not_found"}), 404
        fmt = str(request.args.get("format") or "html")
        branding = None
        try:
            ctx = _service.build_merge_context(get_db(), company_id=cid)
            branding = ctx.get("branding")
        except Exception:
            branding = None
        payload = _service.export_payload(doc, fmt=fmt, branding=branding)
        return Response(
            payload["content"],
            mimetype=payload["mimetype"],
            headers={"Content-Disposition": f'attachment; filename="{payload["filename"]}"'},
        )

    @docs_v2_bp.post("/docs/<doc_id>/email")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def email_doc(doc_id: str):
        """Send the document as a PDF attachment via configured SMTP/API mail."""
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        existing = _service.get_doc(get_db(), doc_id, company_id=cid)
        gate = _contract_docs_gate(get_db(), cid, doc=existing, data=(request.get_json(silent=True) or {}), action="email")
        if gate:
            return gate
        to = str(data.get("to") or data.get("email") or "").strip()
        if not to or "@" not in to:
            return jsonify({"error": "email_required"}), 400
        doc = _service.get_doc(get_db(), doc_id, company_id=cid)
        if not doc:
            return jsonify({"error": "not_found"}), 404
        branding = None
        try:
            ctx = _service.build_merge_context(get_db(), company_id=cid)
            branding = ctx.get("branding")
        except Exception:
            branding = None
        payload = _service.export_payload(doc, fmt="pdf", branding=branding)
        title = str(doc.get("title") or "Dokument").strip() or "Dokument"
        company_name = ""
        if isinstance(branding, dict):
            company_name = str(branding.get("companyName") or branding.get("company_name") or "").strip()
        subject = str(data.get("subject") or "").strip() or (
            f"{title} ({company_name})" if company_name else title
        )
        body = str(data.get("message") or data.get("body") or "").strip()
        if not body:
            parts = []
            if company_name:
                parts.append(company_name)
                parts.append("")
            parts.append(f"Anbei das Dokument «{title}» als PDF.")
            parts.append("")
            parts.append("— SUPPIX Docs")
            body = "\n".join(parts)
        from backend.app.platform.reports.email_delivery import send_pdf_report_email

        ok, err = send_pdf_report_email(
            to=to,
            subject=subject,
            body_text=body,
            pdf_bytes=payload["content"],
            filename=str(payload.get("filename") or f"{title}.pdf"),
            report_meta={"kind": "editor_doc", "document_id": doc_id, "company_id": cid},
        )
        if not ok:
            hint = (
                "SMTP/API-Mail ist nicht konfiguriert oder fehlgeschlagen. "
                "Einstellungen → E-Mail (SMTP_HOST / Resend / Brevo) prüfen."
            )
            return jsonify(
                {
                    "ok": False,
                    "error": "send_failed",
                    "message": err or "send_failed",
                    "hint": hint,
                }
            ), 502
        return jsonify({"ok": True, "to": to, "filename": payload.get("filename")})

    @docs_v2_bp.get("/docs/onlyoffice/status")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def onlyoffice_status():
        from . import onlyoffice as oo

        return jsonify(
            {
                "ok": True,
                "enabled": oo.onlyoffice_enabled(),
                "documentServerUrl": oo.onlyoffice_browser_url() if oo.onlyoffice_enabled() else "",
                "hint": None
                if oo.onlyoffice_enabled()
                else "ONLYOFFICE_URL setzen und Document Server starten (deploy/start-onlyoffice.ps1).",
            }
        )

    @docs_v2_bp.get("/docs/<doc_id>/onlyoffice/config")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def onlyoffice_config(doc_id: str):
        from . import onlyoffice as oo

        if not oo.onlyoffice_enabled():
            return jsonify({"ok": False, "error": "onlyoffice_disabled"}), 503
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        existing = _service.get_doc(get_db(), doc_id, company_id=cid)
        gate = _contract_docs_gate(get_db(), cid, doc=existing, data=(request.get_json(silent=True) or {}), action="onlyoffice")
        if gate:
            return gate
        doc = _service.get_doc(get_db(), doc_id, company_id=cid)
        if not doc:
            return jsonify({"error": "not_found"}), 404
        # Refresh DOCX from current HTML so Quill edits open in Word Pro
        oo.ensure_docx_file(doc, force=True)
        mode = str(request.args.get("mode") or "edit")
        cfg = oo.build_editor_config(
            doc=doc,
            company_id=cid,
            user_id=_actor_id(),
            user_name=_actor_name() or "Editor",
            mode=mode,
        )
        return jsonify(cfg)

    @docs_v2_bp.get("/docs/<doc_id>/onlyoffice/file")
    def onlyoffice_file(doc_id: str):
        """Downloaded by OnlyOffice Document Server (token query, no Bearer)."""
        from . import onlyoffice as oo

        token = str(request.args.get("oo_token") or "").strip()
        payload = oo.verify_jwt(token) if token else None
        if not payload or payload.get("purpose") != "oo_file" or str(payload.get("doc_id")) != str(doc_id):
            return jsonify({"error": "invalid_token"}), 403
        cid = str(payload.get("company_id") or request.args.get("company_id") or "").strip()
        doc = _service.get_doc(get_db(), doc_id, company_id=cid or None)
        if not doc:
            return jsonify({"error": "not_found"}), 404
        path = oo.ensure_docx_file(doc, force=False)
        data = path.read_bytes()
        return Response(
            data,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="{path.name}"',
                "Cache-Control": "no-store",
            },
        )

    @docs_v2_bp.post("/docs/<doc_id>/onlyoffice/callback")
    def onlyoffice_callback(doc_id: str):
        """OnlyOffice save callback — no user Bearer token."""
        from . import onlyoffice as oo

        body = request.get_json(silent=True) or {}
        # Optional JWT verification when Document Server sends token
        token = str(request.args.get("token") or body.get("token") or "").strip()
        if token:
            payload = oo.verify_jwt(token)
            if payload is None:
                return jsonify({"error": 1}), 403

        status = int(body.get("status") or 0)
        # 2 = ready for saving, 6 = force save
        if status in {2, 6} and body.get("url"):
            try:
                content = oo.download_bytes(str(body["url"]))
                path = oo.docx_path_for(doc_id)
                oo.apply_saved_docx(path, content)
                plain = oo.docx_to_plain_preview(path)
                cid = str(request.args.get("company_id") or "").strip() or None
                db = get_db()
                _service.update_doc(
                    db,
                    doc_id,
                    company_id=cid,
                    actor_user_id="onlyoffice",
                    data={
                        "contentText": plain,
                        "contentHtml": "".join(
                            f"<p>{line}</p>" if line.strip() else "<p><br></p>"
                            for line in plain.splitlines()
                        )
                        or "<p><br></p>",
                        "versionNote": "onlyoffice-save",
                    },
                    save_version=True,
                )
            except Exception as exc:
                print(f"[baupass] onlyoffice callback save failed: {exc}", flush=True)
                return jsonify({"error": 1}), 500
        return jsonify({"error": 0})

    @docs_v2_bp.post("/docs/<doc_id>/share")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def create_doc_share(doc_id: str):
        from datetime import datetime, timedelta, timezone

        from werkzeug.security import generate_password_hash

        from . import onlyoffice as oo

        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        existing = _service.get_doc(get_db(), doc_id, company_id=cid)
        gate = _contract_docs_gate(get_db(), cid, doc=existing, data=(request.get_json(silent=True) or {}), action="share")
        if gate:
            return gate
        doc = _service.get_doc(get_db(), doc_id, company_id=cid)
        if not doc:
            return jsonify({"error": "not_found"}), 404
        try:
            hours = int(data.get("ttlHours") or data.get("ttl_hours") or 72)
        except (TypeError, ValueError):
            hours = 72
        hours = max(1, min(hours, 24 * 30))
        password = str(data.get("password") or "").strip()
        require_approved = str(data.get("requireApproved") or data.get("require_approved") or "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        token = oo.new_share_token()
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        pwd_hash = generate_password_hash(password) if password else None
        _service.repo.create_share(
            get_db(),
            document_id=doc_id,
            company_id=cid,
            token=token,
            password_hash=pwd_hash,
            expires_at=expires_at,
            require_approved=require_approved,
            actor_user_id=_actor_id(),
        )
        return jsonify(
            {
                "ok": True,
                "token": token,
                "url": oo.public_share_url(token),
                "ttlHours": hours,
                "expiresAt": expires_at,
                "hasPassword": bool(password),
                "requireApproved": require_approved,
                "title": doc.get("title") or "Dokument",
            }
        )

    @docs_v2_bp.post("/docs/<doc_id>/share/revoke")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def revoke_doc_share(doc_id: str):
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        existing = _service.get_doc(get_db(), doc_id, company_id=cid)
        gate = _contract_docs_gate(get_db(), cid, doc=existing, data=(request.get_json(silent=True) or {}), action="share_revoke")
        if gate:
            return gate
        token = str(data.get("token") or "").strip() or None
        n = _service.repo.revoke_share(get_db(), document_id=doc_id, company_id=cid, token=token)
        return jsonify({"ok": True, "revoked": n})

    @docs_v2_bp.get("/docs/<doc_id>/shares")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def list_doc_shares(doc_id: str):
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        items = _service.repo.list_shares(get_db(), doc_id, cid)
        return jsonify({"ok": True, "items": items})

    @docs_v2_bp.post("/docs/<doc_id>/presence")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def upsert_doc_presence(doc_id: str):
        import hashlib

        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        doc = _service.get_doc(get_db(), doc_id, company_id=cid)
        if not doc:
            return jsonify({"error": "not_found"}), 404
        live_rev_raw = data.get("liveRev")
        live_rev = None
        if live_rev_raw is not None and str(live_rev_raw).strip() != "":
            try:
                live_rev = int(live_rev_raw)
            except (TypeError, ValueError):
                live_rev = 0
        peers = _service.repo.upsert_presence(
            get_db(),
            document_id=doc_id,
            company_id=cid,
            user_id=_actor_id() or "anon",
            display_name=_actor_name() or _actor_id() or "User",
            live_html=str(data.get("liveHtml") or data.get("live_html") or "") if live_rev is not None else None,
            live_title=str(data.get("liveTitle") or data.get("live_title") or "") if live_rev is not None else None,
            live_rev=live_rev,
        )
        body = str(doc.get("content_html") or "")
        content_hash = hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest()[:24]
        try:
            from backend.app.platform.realtime.websocket import socketio as _sio

            if _sio is not None and live_rev is not None:
                _sio.emit(
                    "docs_live",
                    {
                        "documentId": doc_id,
                        "companyId": cid,
                        "userId": _actor_id() or "anon",
                        "displayName": _actor_name() or _actor_id() or "User",
                        "liveRev": live_rev,
                        "liveTitle": str(data.get("liveTitle") or "")[:200],
                        "liveHtml": str(data.get("liveHtml") or "")[:250_000],
                    },
                    room=f"company:{cid}",
                )
        except Exception:
            pass
        return jsonify(
            {
                "ok": True,
                "peers": peers,
                "updatedAt": doc.get("updated_at"),
                "contentHash": content_hash,
                "title": doc.get("title") or "",
                "status": doc.get("status") or "draft",
            }
        )

    @docs_v2_bp.get("/docs/<doc_id>/presence")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def list_doc_presence(doc_id: str):
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        peers = _service.repo.list_presence(get_db(), document_id=doc_id, company_id=cid)
        doc = _service.get_doc(get_db(), doc_id, company_id=cid)
        return jsonify({"ok": True, "peers": peers, "updatedAt": (doc or {}).get("updated_at")})

    @docs_v2_bp.post("/docs/<doc_id>/signatures")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def create_doc_signature(doc_id: str):
        import hashlib
        import json as _json

        from werkzeug.security import generate_password_hash

        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        existing = _service.get_doc(get_db(), doc_id, company_id=cid)
        gate = _contract_docs_gate(get_db(), cid, doc=existing, data=(request.get_json(silent=True) or {}), action="signature")
        if gate:
            return gate
        doc = _service.get_doc(get_db(), doc_id, company_id=cid)
        if not doc:
            return jsonify({"error": "not_found"}), 404
        pin = str(data.get("pin") or data.get("confirmPin") or "").strip()
        if len(pin) < 4:
            return jsonify({"error": "pin_required", "message": "PIN mindestens 4 Zeichen"}), 400
        body = str(doc.get("content_html") or "")
        content_hash = hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest()
        signer_name = str(data.get("signerName") or data.get("signer_name") or "").strip()
        stamped = bool(data.get("stamped"))
        level = "aes"  # advanced electronic signature (platform) — not QES/eIDAS TSP
        manifest = {
            "level": level,
            "documentId": doc_id,
            "companyId": cid,
            "title": doc.get("title") or "",
            "signerName": signer_name,
            "actorUserId": _actor_id(),
            "stamped": stamped,
            "contentHashSha256": content_hash,
            "pinHash": generate_password_hash(pin),
            "note": "Advanced electronic signature (AES). Not a qualified electronic signature (QES).",
        }
        payload = str(data.get("signatureData") or data.get("signature_data") or "")[:100000]
        packed = _json.dumps({"manifest": manifest, "imageData": payload}, ensure_ascii=False)
        row = _service.repo.add_signature(
            get_db(),
            document_id=doc_id,
            company_id=cid,
            signer_name=signer_name,
            actor_user_id=_actor_id(),
            stamped=stamped,
            content_hash=content_hash,
            signature_data=packed[:120000],
        )
        lock_raw = data.get("lockAfter")
        lock_after = lock_raw is True or str(lock_raw or "").lower() in {"1", "true", "yes"}
        if lock_after and stamped:
            try:
                _service.set_status(
                    get_db(),
                    doc_id,
                    company_id=cid,
                    actor_user_id=_actor_id(),
                    status="approved",
                )
                doc = _service.get_doc(get_db(), doc_id, company_id=cid) or doc
            except Exception:
                pass
        return jsonify({"ok": True, "signature": row, "level": level, "document": doc})

    def _qes_config() -> dict:
        import os

        provider = (os.getenv("DOCS_QES_PROVIDER") or "").strip()
        api_url = (os.getenv("DOCS_QES_API_URL") or "").strip()
        api_key = (os.getenv("DOCS_QES_API_KEY") or "").strip()
        configured = bool(api_url and api_key)
        return {
            "configured": configured,
            "provider": provider or ("generic" if configured else ""),
            "levelAvailable": "qes" if configured else "aes",
            "hint": (
                "QES via Trust Service Provider konfiguriert."
                if configured
                else "QES nicht konfiguriert. DOCS_QES_API_URL + DOCS_QES_API_KEY (+ optional DOCS_QES_PROVIDER) setzen."
            ),
        }

    @docs_v2_bp.get("/docs/signatures/qes/status")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def qes_status():
        return jsonify({"ok": True, **_qes_config()})

    @docs_v2_bp.post("/docs/<doc_id>/signatures/qes/start")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def qes_start(doc_id: str):
        import hashlib
        import json as _json
        import os
        import urllib.error
        import urllib.request

        cfg = _qes_config()
        if not cfg["configured"]:
            return jsonify({"ok": False, "error": "qes_not_configured", "message": cfg["hint"], **cfg}), 503
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        doc = _service.get_doc(get_db(), doc_id, company_id=cid)
        if not doc:
            return jsonify({"error": "not_found"}), 404
        gate = _contract_docs_gate(get_db(), cid, doc=doc, data=data, action="qes_start")
        if gate:
            return gate
        body = str(doc.get("content_html") or "")
        content_hash = hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest()
        payload = {
            "documentId": doc_id,
            "companyId": cid,
            "title": doc.get("title") or "",
            "contentHashSha256": content_hash,
            "signerName": str(data.get("signerName") or data.get("signer_name") or "").strip(),
            "callbackUrl": str(data.get("callbackUrl") or os.getenv("DOCS_QES_CALLBACK_URL") or "").strip(),
            "level": "qes",
            "provider": cfg["provider"],
        }
        api_url = (os.getenv("DOCS_QES_API_URL") or "").rstrip("/")
        api_key = os.getenv("DOCS_QES_API_KEY") or ""
        req = urllib.request.Request(
            api_url,
            data=_json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "X-Docs-Qes-Provider": cfg["provider"],
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                try:
                    remote = _json.loads(raw) if raw else {}
                except Exception:
                    remote = {"raw": raw}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            return jsonify(
                {
                    "ok": False,
                    "error": "qes_provider_http",
                    "message": f"QES-Provider HTTP {exc.code}",
                    "detail": detail,
                }
            ), 502
        except Exception as exc:
            return jsonify({"ok": False, "error": "qes_provider_unreachable", "message": str(exc)}), 502

        session_url = (
            remote.get("sessionUrl")
            or remote.get("session_url")
            or remote.get("url")
            or remote.get("redirectUrl")
            or ""
        )
        # Audit placeholder row (no PIN / not AES image) marking QES session start
        _service.repo.add_signature(
            get_db(),
            document_id=doc_id,
            company_id=cid,
            signer_name=str(payload["signerName"] or "QES"),
            actor_user_id=_actor_id(),
            stamped=False,
            content_hash=content_hash,
            signature_data=_json.dumps(
                {
                    "manifest": {
                        "level": "qes_pending",
                        "provider": cfg["provider"],
                        "contentHashSha256": content_hash,
                        "remote": {k: remote.get(k) for k in ("id", "sessionId", "status") if k in remote},
                    }
                },
                ensure_ascii=False,
            )[:120000],
        )
        return jsonify(
            {
                "ok": True,
                "level": "qes",
                "provider": cfg["provider"],
                "sessionUrl": session_url,
                "remote": remote,
                "contentHash": content_hash,
            }
        )

    @docs_v2_bp.get("/docs/<doc_id>/signatures")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def list_doc_signatures(doc_id: str):
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        items = _service.repo.list_signatures(get_db(), document_id=doc_id, company_id=cid)
        return jsonify({"ok": True, "items": items})

    @docs_v2_bp.post("/docs/<doc_id>/status")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def set_doc_status(doc_id: str):
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        existing = _service.get_doc(get_db(), doc_id, company_id=cid)
        gate = _contract_docs_gate(get_db(), cid, doc=existing, data=(request.get_json(silent=True) or {}), action="status")
        if gate:
            return gate
        result = _service.set_status(
            get_db(),
            doc_id,
            company_id=cid,
            actor_user_id=_actor_id(),
            status=str(data.get("status") or ""),
        )
        if not result:
            return jsonify({"error": "not_found"}), 404
        if result.get("error") == "invalid_status":
            return jsonify({"error": "invalid_status"}), 400
        return jsonify({"ok": True, "document": result})

    @docs_v2_bp.post("/docs/<doc_id>/publish")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def publish_doc(doc_id: str):
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        existing = _service.get_doc(get_db(), doc_id, company_id=cid)
        gate = _contract_docs_gate(get_db(), cid, doc=existing, data=(request.get_json(silent=True) or {}), action="publish")
        if gate:
            return gate
        result = _service.publish_to_worker(
            get_db(),
            doc_id,
            company_id=cid,
            actor_user_id=_actor_id(),
            worker_id=str(data.get("workerId") or data.get("worker_id") or "").strip() or None,
            notify=str(data.get("notify", "1")).lower() not in {"0", "false", "no"},
            doc_type=str(data.get("docType") or data.get("doc_type") or "sonstiges"),
        )
        if result.get("error"):
            return jsonify({"error": result["error"]}), int(result.get("status") or 400)
        return jsonify(result)

    @docs_v2_bp.post("/docs/from-contract")
    @require_auth
    @deny_turnstile_sensitive(surface="docs", action="from_contract")
    @require_roles("superadmin", "company-admin")
    @require_owner_step_up
    def from_contract():
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        contract_id = str(data.get("contractId") or data.get("contract_id") or "").strip()
        if not contract_id:
            return jsonify({"error": "contract_id_required"}), 400
        title = str(data.get("title") or "Vertrag").strip() or "Vertrag"
        plain = str(data.get("text") or data.get("plainText") or data.get("contentText") or "")
        doc = _service.open_or_create_for_contract(
            get_db(),
            company_id=cid,
            contract_id=contract_id,
            title=title,
            plain_text=plain,
            actor_user_id=_actor_id(),
        )
        return jsonify({"ok": True, "document": doc})

    register_blueprint_once(flask_app, docs_v2_bp, url_prefix="/api/v2")
    register_docs_blueprint._routes_defined = True
    print("[baupass] domain/docs: editor documents /api/v2/docs*", flush=True)
