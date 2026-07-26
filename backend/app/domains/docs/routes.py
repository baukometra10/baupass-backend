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


def _docs_capabilities() -> dict:
    """Fine-grained Docs permissions (Turnstile vs Admin)."""
    role = _actor_role()
    is_admin = role in {"superadmin", "company-admin"}
    is_editor = role in {"superadmin", "company-admin", "turnstile"}
    return {
        "role": role,
        "canEdit": is_editor,
        "canShare": is_admin,
        "canDelete": is_admin,
        "canSign": is_admin,
        "canPublish": is_admin,
        "canPublishTeamTemplate": is_admin,
        "canManageLogo": is_admin,
        "canTestEmail": is_admin,
        "canUseWordPro": is_editor,
        "canEmail": is_editor,
        "canReview": is_editor,
        "canResolveSuggestions": is_admin,
    }


def _deny_cap(cap: str):
    caps = _docs_capabilities()
    if caps.get(cap):
        return None
    return (
        jsonify(
            {
                "ok": False,
                "error": "forbidden",
                "message": "Keine Berechtigung für diese Aktion (Turnstile vs Admin).",
                "capability": cap,
                "capabilities": caps,
            }
        ),
        403,
    )


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

    @docs_v2_bp.put("/docs/company-logo")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def set_company_logo():
        """Upload/clear tenant logo for docs letterhead (turnstile: read-only)."""
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        logo = data.get("logoData", data.get("logo_data", data.get("brandingLogoData")))
        # Explicit null/empty clears; missing key is invalid.
        if "logoData" not in data and "logo_data" not in data and "brandingLogoData" not in data:
            return jsonify({"ok": False, "error": "logo_required", "message": "logoData fehlt."}), 400
        result = _service.set_company_logo(get_db(), company_id=cid, logo_data=logo)
        if not result.get("ok"):
            status = 404 if result.get("error") == "company_not_found" else 400
            return jsonify(result), status
        return jsonify(result)

    @docs_v2_bp.get("/docs/capabilities")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def docs_capabilities():
        return jsonify({"ok": True, "capabilities": _docs_capabilities()})

    @docs_v2_bp.get("/docs/email/status")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def docs_email_status():
        from backend.app.platform.reports.email_delivery import mail_delivery_status

        return jsonify({"ok": True, **mail_delivery_status()})

    @docs_v2_bp.post("/docs/email/test")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def docs_email_test():
        """Send a tiny test mail (admin only) to verify SMTP/API config."""
        denied = _deny_cap("canTestEmail")
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        to = str(data.get("to") or data.get("email") or "").strip()
        if not to or "@" not in to:
            return jsonify({"ok": False, "error": "email_required", "message": "Empfänger-E-Mail fehlt."}), 400
        from backend.app.platform.reports.email_delivery import mail_delivery_status, send_attachments_email

        status = mail_delivery_status()
        if not status.get("configured"):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "mail_not_configured",
                        "message": status.get("hint") or "Mail nicht konfiguriert",
                        **status,
                    }
                ),
                503,
            )
        ok, err = send_attachments_email(
            to=to,
            subject=str(data.get("subject") or "SUPPIX Docs — Testsendung").strip()[:200],
            body_text=(
                str(data.get("message") or "").strip()
                or "Dies ist eine Testsendung aus SUPPIX Docs. SMTP/API funktioniert."
            ),
            attachments=[
                {
                    "filename": "suppix-docs-test.txt",
                    "data": b"SUPPIX Docs mail test\n",
                    "maintype": "text",
                    "subtype": "plain",
                }
            ],
            report_meta={"kind": "docs_mail_test", "company_id": _resolve_company_id(data, required=False) or ""},
            branded=False,
        )
        if not ok:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "send_failed",
                        "message": err or "send_failed",
                        "hint": status.get("hint"),
                        **status,
                    }
                ),
                502,
            )
        return jsonify({"ok": True, "to": to, **status})

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
        denied = _deny_cap("canPublishTeamTemplate")
        if denied:
            return denied
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
            category=str(data.get("category") or data.get("topic") or "sonstiges"),
        )
        return jsonify({"ok": True, "template": tpl}), 201

    @docs_v2_bp.post("/docs/templates/starter-kit")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def apply_template_starter_kit():
        """Seed a small set of company team templates (idempotent by title prefix)."""
        denied = _deny_cap("canPublishTeamTemplate")
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        from .repository import dumps_json

        kits = [
            {
                "title": "Kit: Firmenbrief",
                "category": "correspondence",
                "blurb": "Starter-Kit Brief",
                "html": (
                    "<p>{{company.name}}</p><p>{{company.address}}</p>"
                    "<p>{{worker.name}}</p><p>{{date.today}}</p>"
                    "<p><strong>Betreff:</strong> …</p>"
                    "<p>Sehr geehrte Damen und Herren,</p><p>…</p>"
                    "<p>Mit freundlichen Grüßen<br>{{manager.name}}</p>"
                ),
            },
            {
                "title": "Kit: Abmahnung",
                "category": "hr",
                "blurb": "Starter-Kit HR",
                "html": (
                    "<h1>Abmahnung</h1><p>{{worker.name}} · {{date.today}}</p>"
                    "<p>Hiermit sprechen wir Ihnen eine Abmahnung aus wegen:</p><p>…</p>"
                    "<p>{{company.name}}</p>"
                ),
            },
            {
                "title": "Kit: Arbeitsbescheinigung",
                "category": "hr",
                "blurb": "Starter-Kit HR",
                "html": (
                    "<h1>Bescheinigung</h1>"
                    "<p>Hiermit bestätigen wir, dass {{worker.name}} bei {{company.name}} beschäftigt ist.</p>"
                    "<p>Datum: {{date.today}}</p>"
                ),
            },
            {
                "title": "Kit: Sicherheitsunterweisung",
                "category": "safety",
                "blurb": "Starter-Kit Sicherheit",
                "html": (
                    "<h1>Sicherheitsunterweisung</h1>"
                    "<p>Teilnehmer: {{worker.name}}</p><p>Datum: {{date.today}}</p>"
                    "<ul><li>PSA</li><li>Notfallwege</li><li>Meldepflicht</li></ul>"
                    "<p>Unterschrift: ________________</p>"
                ),
            },
            {
                "title": "Kit: Betriebsanweisung",
                "category": "safety",
                "blurb": "Starter-Kit Sicherheit",
                "html": (
                    "<h1>Betriebsanweisung</h1><p>{{company.name}} · {{date.today}}</p>"
                    "<h2>Geltungsbereich</h2><p>…</p><h2>Maßnahmen</h2><p>…</p>"
                ),
            },
            {
                "title": "Kit: Protokoll",
                "category": "meetings",
                "blurb": "Starter-Kit Meeting",
                "html": (
                    "<h1>Protokoll</h1><p>Datum: {{date.today}}</p>"
                    "<p>Teilnehmer: …</p><h2>Beschlüsse</h2><ol><li>…</li></ol>"
                ),
            },
        ]
        existing = {str(t.get("title") or "") for t in _service.repo.list_templates(get_db(), cid, limit=200)}
        created = []
        for kit in kits:
            if kit["title"] in existing:
                continue
            tpl = _service.repo.create_template(
                get_db(),
                company_id=cid,
                title=kit["title"],
                blurb=kit["blurb"],
                content_html=kit["html"],
                layout_json=dumps_json({"showHeader": True, "showFooter": True}),
                actor_user_id=_actor_id(),
                category=kit["category"],
            )
            created.append(tpl)
        return jsonify({"ok": True, "created": len(created), "items": created})

    @docs_v2_bp.post("/docs/templates/policy-pack")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def apply_policy_pack():
        """Seed DE+TR/AR/PL linked policy templates (idempotent by title)."""
        denied = _deny_cap("canPublishTeamTemplate")
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        from .repository import dumps_json

        packs = [
            {
                "packId": "safety-toolbox",
                "category": "safety",
                "required": ["worker.name", "date.today", "site.name"],
                "locales": {
                    "de": (
                        "Pack: Toolbox-Talk (DE)",
                        "<h1>Toolbox-Talk / Kurzunterweisung</h1>"
                        "<p>Teilnehmer: {{worker.name}} · Badge {{worker.badge}}</p>"
                        "<p>Baustelle: {{site.name}} · {{date.today}}</p>"
                        "<p>Schicht: {{shift.slot}}</p>"
                        "<ul><li>PSA prüfen</li><li>Notfallwege</li><li>Meldepflicht bei Gefahr</li></ul>"
                        "<p>Leitung: {{manager.name}}</p><p>Unterschrift: ____________</p>",
                    ),
                    "tr": (
                        "Pack: Toolbox-Talk (TR)",
                        "<h1>Toolbox / Kısa İş Güvenliği</h1>"
                        "<p>Katılımcı: {{worker.name}} · Kart {{worker.badge}}</p>"
                        "<p>Şantiye: {{site.name}} · {{date.today}}</p>"
                        "<p>Vardiya: {{shift.slot}}</p>"
                        "<ul><li>KKD kontrol</li><li>Acil çıkışlar</li><li>Tehlike bildirimi</li></ul>"
                        "<p>Sorumlu: {{manager.name}}</p><p>İmza: ____________</p>",
                    ),
                    "ar": (
                        "Pack: Toolbox-Talk (AR)",
                        "<h1>إحاطة سلامة قصيرة</h1>"
                        "<p>المشارك: {{worker.name}} · البطاقة {{worker.badge}}</p>"
                        "<p>الموقع: {{site.name}} · {{date.today}}</p>"
                        "<p>الوردية: {{shift.slot}}</p>"
                        "<ul><li>فحص معدات الوقاية</li><li>مخارج الطوارئ</li><li>الإبلاغ عن الخطر</li></ul>"
                        "<p>المسؤول: {{manager.name}}</p><p>التوقيع: ____________</p>",
                    ),
                    "pl": (
                        "Pack: Toolbox-Talk (PL)",
                        "<h1>Toolbox / krótkie szkolenie BHP</h1>"
                        "<p>Uczestnik: {{worker.name}} · Identyfikator {{worker.badge}}</p>"
                        "<p>Budowa: {{site.name}} · {{date.today}}</p>"
                        "<p>Zmiana: {{shift.slot}}</p>"
                        "<ul><li>Kontrola ŚOI</li><li>Drogi ewakuacyjne</li><li>Obowiązek zgłoszenia zagrożenia</li></ul>"
                        "<p>Kierownik: {{manager.name}}</p><p>Podpis: ____________</p>",
                    ),
                },
            },
            {
                "packId": "site-rules",
                "category": "safety",
                "required": ["company.name", "site.name", "date.today"],
                "locales": {
                    "de": (
                        "Pack: Baustellenordnung (DE)",
                        "<h1>Baustellenordnung</h1>"
                        "<p>{{company.name}} · {{site.name}}</p>"
                        "<p>Gültig ab {{date.today}}</p>"
                        "<ol><li>Zutritt nur mit Ausweis</li><li>PSA Pflicht</li><li>Alkoholverbot</li></ol>"
                        "<p>Ansprechpartner: {{manager.name}}</p>",
                    ),
                    "tr": (
                        "Pack: Baustellenordnung (TR)",
                        "<h1>Şantiye Kuralları</h1>"
                        "<p>{{company.name}} · {{site.name}}</p>"
                        "<p>Geçerlilik: {{date.today}}</p>"
                        "<ol><li>Kimliksiz giriş yok</li><li>KKD zorunlu</li><li>Alkol yasağı</li></ol>"
                        "<p>İrtibat: {{manager.name}}</p>",
                    ),
                    "ar": (
                        "Pack: Baustellenordnung (AR)",
                        "<h1>نظام الموقع</h1>"
                        "<p>{{company.name}} · {{site.name}}</p>"
                        "<p>اعتباراً من {{date.today}}</p>"
                        "<ol><li>الدخول بالبطاقة فقط</li><li>معدات الوقاية إلزامية</li><li>ممنوع الكحول</li></ol>"
                        "<p>جهة الاتصال: {{manager.name}}</p>",
                    ),
                    "pl": (
                        "Pack: Baustellenordnung (PL)",
                        "<h1>Regulamin budowy</h1>"
                        "<p>{{company.name}} · {{site.name}}</p>"
                        "<p>Obowiązuje od {{date.today}}</p>"
                        "<ol><li>Wejście tylko z identyfikatorem</li><li>Obowiązek ŚOI</li><li>Zakaz alkoholu</li></ol>"
                        "<p>Kontakt: {{manager.name}}</p>",
                    ),
                },
            },
            {
                "packId": "hr-warning",
                "category": "hr",
                "required": ["worker.name", "company.name", "date.today"],
                "locales": {
                    "de": (
                        "Pack: Abmahnung (DE)",
                        "<h1>Abmahnung</h1>"
                        "<p>{{company.name}}</p>"
                        "<p>An: {{worker.name}} ({{worker.role}})</p>"
                        "<p>Datum: {{date.today}}</p>"
                        "<p>Sachverhalt: …</p>"
                        "<p>{{manager.name}}</p>",
                    ),
                    "tr": (
                        "Pack: Abmahnung (TR)",
                        "<h1>Uyarı yazısı</h1>"
                        "<p>{{company.name}}</p>"
                        "<p>Sayın: {{worker.name}} ({{worker.role}})</p>"
                        "<p>Tarih: {{date.today}}</p>"
                        "<p>Konu: …</p>"
                        "<p>{{manager.name}}</p>",
                    ),
                    "ar": (
                        "Pack: Abmahnung (AR)",
                        "<h1>إنذار كتابي</h1>"
                        "<p>{{company.name}}</p>"
                        "<p>إلى: {{worker.name}} ({{worker.role}})</p>"
                        "<p>التاريخ: {{date.today}}</p>"
                        "<p>السبب: …</p>"
                        "<p>{{manager.name}}</p>",
                    ),
                    "pl": (
                        "Pack: Abmahnung (PL)",
                        "<h1>Upomnienie</h1>"
                        "<p>{{company.name}}</p>"
                        "<p>Do: {{worker.name}} ({{worker.role}})</p>"
                        "<p>Data: {{date.today}}</p>"
                        "<p>Zdarzenie: …</p>"
                        "<p>{{manager.name}}</p>",
                    ),
                },
            },
        ]
        existing = {str(t.get("title") or "") for t in _service.repo.list_templates(get_db(), cid, limit=300)}
        created = []
        for pack in packs:
            for loc, (title, html) in pack["locales"].items():
                if title in existing:
                    continue
                layout = {
                    "showHeader": True,
                    "showFooter": True,
                    "packId": pack["packId"],
                    "locale": loc,
                    "required_placeholders": pack["required"],
                    "packMaster": loc == "de",
                }
                tpl = _service.repo.create_template(
                    get_db(),
                    company_id=cid,
                    title=title,
                    blurb=f"Policy-Pack {pack['packId']} · {loc.upper()}",
                    content_html=html,
                    layout_json=dumps_json(layout),
                    actor_user_id=_actor_id(),
                    category=pack["category"],
                )
                created.append(tpl)
        return jsonify({"ok": True, "created": len(created), "items": created, "packs": len(packs)})

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
        worker_id = str(data.get("workerId") or data.get("worker_id") or "").strip() or None
        result = _service.suggest(
            get_db(),
            company_id=cid,
            content_html=str(data.get("contentHtml") or data.get("content_html") or ""),
            action=str(data.get("action") or "improve"),
            lang=str(data.get("lang") or "de"),
            worker_id=worker_id,
            actor_user_id=_actor_id(),
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
        if isinstance(doc, dict) and doc.get("error"):
            return jsonify({"error": doc["error"]}), int(doc.get("status") or 400)
        return jsonify({"ok": True, "document": doc})

    @docs_v2_bp.delete("/docs/<doc_id>")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def delete_doc(doc_id: str):
        denied = _deny_cap("canDelete")
        if denied:
            return denied
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
            from backend.app.platform.reports.email_delivery import mail_delivery_status

            status = mail_delivery_status()
            hint = status.get("hint") or (
                "SMTP/API-Mail ist nicht konfiguriert oder fehlgeschlagen. "
                "Einstellungen → E-Mail (SMTP_HOST / Resend / Brevo) prüfen."
            )
            return jsonify(
                {
                    "ok": False,
                    "error": "send_failed",
                    "message": err or "send_failed",
                    "hint": hint,
                    "mail": status,
                }
            ), 502
        return jsonify({"ok": True, "to": to, "filename": payload.get("filename")})

    @docs_v2_bp.get("/docs/onlyoffice/status")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def onlyoffice_status():
        from . import onlyoffice as oo

        enabled = oo.onlyoffice_enabled()
        probe = oo.probe_document_server() if enabled else {
            "reachable": False,
            "hint": "ONLYOFFICE_URL setzen und Document Server starten (deploy/start-onlyoffice.ps1).",
        }
        ready = bool(enabled and probe.get("reachable"))
        hint = None
        if not enabled:
            hint = probe.get("hint") or "ONLYOFFICE_URL setzen und Document Server starten (deploy/start-onlyoffice.ps1)."
        elif not probe.get("reachable"):
            hint = probe.get("hint") or "Document Server nicht erreichbar."
        return jsonify(
            {
                "ok": True,
                "enabled": enabled,
                "reachable": bool(probe.get("reachable")),
                "ready": ready,
                "documentServerUrl": oo.onlyoffice_browser_url() if enabled else "",
                "checkedUrl": probe.get("checkedUrl") or "",
                "hint": hint,
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
                html = oo.docx_bytes_to_html(content)
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
                        "contentHtml": html or "<p><br></p>",
                        "versionNote": "onlyoffice-save",
                    },
                    save_version=True,
                )
            except Exception as exc:
                print(f"[baupass] onlyoffice callback save failed: {exc}", flush=True)
                return jsonify({"error": 1}), 500
        return jsonify({"error": 0})

    @docs_v2_bp.post("/docs/<doc_id>/onlyoffice/sync")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def onlyoffice_sync(doc_id: str):
        """Re-import the last Word Pro DOCX into the Quill document (roundtrip safety)."""
        from . import onlyoffice as oo

        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        doc = _service.get_doc(get_db(), doc_id, company_id=cid)
        if not doc:
            return jsonify({"error": "not_found"}), 404
        gate = _contract_docs_gate(get_db(), cid, doc=doc, action="onlyoffice_sync")
        if gate:
            return gate
        path = oo.docx_path_for(doc_id)
        if not path.exists():
            return jsonify({"ok": False, "error": "no_docx", "message": "Noch keine Word-Pro-Datei vorhanden."}), 404
        try:
            content = path.read_bytes()
            html = oo.docx_bytes_to_html(content)
            plain = oo.docx_to_plain_preview(path)
            updated = _service.update_doc(
                get_db(),
                doc_id,
                company_id=cid,
                actor_user_id=_actor_id(),
                data={
                    "contentText": plain,
                    "contentHtml": html or "<p><br></p>",
                    "versionNote": "onlyoffice-sync",
                },
                save_version=True,
            )
            return jsonify({"ok": True, "document": updated})
        except Exception as exc:
            return jsonify({"ok": False, "error": "sync_failed", "message": str(exc)[:220]}), 500

    @docs_v2_bp.post("/docs/<doc_id>/share")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def create_doc_share(doc_id: str):
        denied = _deny_cap("canShare")
        if denied:
            return denied
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
        denied = _deny_cap("canShare")
        if denied:
            return denied
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
        cursor_index = None
        cursor_length = 0
        if "cursorIndex" in data or "cursor_index" in data:
            try:
                cursor_index = int(data.get("cursorIndex", data.get("cursor_index")))
            except (TypeError, ValueError):
                cursor_index = -1
            try:
                cursor_length = int(data.get("cursorLength", data.get("cursor_length") or 0))
            except (TypeError, ValueError):
                cursor_length = 0
        peers = _service.repo.upsert_presence(
            get_db(),
            document_id=doc_id,
            company_id=cid,
            user_id=_actor_id() or "anon",
            display_name=_actor_name() or _actor_id() or "User",
            live_html=str(data.get("liveHtml") or data.get("live_html") or "") if live_rev is not None else None,
            live_title=str(data.get("liveTitle") or data.get("live_title") or "") if live_rev is not None else None,
            live_rev=live_rev,
            cursor_index=cursor_index,
            cursor_length=cursor_length,
        )
        body = str(doc.get("content_html") or "")
        content_hash = hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest()[:24]
        try:
            from backend.app.platform.realtime.websocket import socketio as _sio

            if _sio is not None:
                payload = {
                    "documentId": doc_id,
                    "companyId": cid,
                    "userId": _actor_id() or "anon",
                    "displayName": _actor_name() or _actor_id() or "User",
                    "cursorIndex": cursor_index if cursor_index is not None else -1,
                    "cursorLength": cursor_length,
                }
                if live_rev is not None:
                    payload.update(
                        {
                            "liveRev": live_rev,
                            "liveTitle": str(data.get("liveTitle") or "")[:200],
                            "liveHtml": str(data.get("liveHtml") or "")[:250_000],
                        }
                    )
                _sio.emit("docs_live", payload, room=f"company:{cid}")
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

        denied = _deny_cap("canSign")
        if denied:
            return denied
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
        demo = str(os.getenv("DOCS_QES_DEMO") or "").strip().lower() in {"1", "true", "yes", "on"}
        live = bool(api_url and api_key)
        configured = live or demo
        if live:
            hint = "QES via Trust Service Provider konfiguriert."
            mode = "live"
        elif demo:
            hint = "QES-Demo aktiv (DOCS_QES_DEMO=1) — kein echter eIDAS-TSP."
            mode = "demo"
            provider = provider or "demo"
        else:
            hint = (
                "QES nicht konfiguriert. DOCS_QES_API_URL + DOCS_QES_API_KEY "
                "(+ optional DOCS_QES_PROVIDER) setzen — oder DOCS_QES_DEMO=1 für Test."
            )
            mode = "off"
        return {
            "configured": configured,
            "demo": demo and not live,
            "mode": mode,
            "provider": provider or ("generic" if live else ""),
            "levelAvailable": "qes" if configured else "aes",
            "env": {
                "DOCS_QES_API_URL": bool(api_url),
                "DOCS_QES_API_KEY": bool(api_key),
                "DOCS_QES_PROVIDER": bool(provider),
                "DOCS_QES_CALLBACK_URL": bool((os.getenv("DOCS_QES_CALLBACK_URL") or "").strip()),
                "DOCS_QES_DEMO": demo,
            },
            "hint": hint,
        }

    @docs_v2_bp.get("/docs/signatures/qes/status")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def qes_status():
        return jsonify({"ok": True, **_qes_config()})

    @docs_v2_bp.post("/docs/signatures/qes/callback")
    def qes_callback():
        """TSP completion webhook (Bearer DOCS_QES_CALLBACK_SECRET or API key)."""
        import hashlib
        import json as _json
        import os

        secret = (os.getenv("DOCS_QES_CALLBACK_SECRET") or os.getenv("DOCS_QES_API_KEY") or "").strip()
        auth = str(request.headers.get("Authorization") or "")
        token = ""
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        token = token or str(request.args.get("token") or "").strip()
        if secret and token != secret:
            return jsonify({"ok": False, "error": "forbidden"}), 403
        data = request.get_json(silent=True) or {}
        doc_id = str(data.get("documentId") or data.get("document_id") or "").strip()
        cid = str(data.get("companyId") or data.get("company_id") or "").strip()
        if not doc_id or not cid:
            return jsonify({"ok": False, "error": "document_required"}), 400
        doc = _service.get_doc(get_db(), doc_id, company_id=cid)
        if not doc:
            return jsonify({"error": "not_found"}), 404
        body = str(doc.get("content_html") or "")
        content_hash = hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest()
        status = str(data.get("status") or "completed").strip().lower()
        level = "qes" if status in {"completed", "signed", "success", "ok"} else f"qes_{status}"
        row = _service.repo.add_signature(
            get_db(),
            document_id=doc_id,
            company_id=cid,
            signer_name=str(data.get("signerName") or data.get("signer_name") or "QES").strip() or "QES",
            actor_user_id=str(data.get("actorUserId") or "qes-tsp"),
            stamped=status in {"completed", "signed", "success", "ok"},
            content_hash=content_hash,
            signature_data=_json.dumps(
                {
                    "manifest": {
                        "level": level,
                        "provider": str(data.get("provider") or _qes_config().get("provider") or ""),
                        "contentHashSha256": content_hash,
                        "remote": data,
                    }
                },
                ensure_ascii=False,
            )[:120000],
        )
        return jsonify({"ok": True, "signature": row, "level": level})

    @docs_v2_bp.post("/docs/<doc_id>/signatures/qes/start")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def qes_start(doc_id: str):
        import hashlib
        import json as _json
        import os
        import urllib.error
        import urllib.request

        denied = _deny_cap("canSign")
        if denied:
            return denied
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
        signer_name = str(data.get("signerName") or data.get("signer_name") or "").strip()
        callback_url = str(data.get("callbackUrl") or os.getenv("DOCS_QES_CALLBACK_URL") or "").strip()
        if not callback_url:
            # Default webhook endpoint on this API for TSPs that need a callback.
            base = (os.getenv("PUBLIC_BASE_URL") or request.host_url or "").rstrip("/")
            callback_url = f"{base}/api/v2/docs/signatures/qes/callback"
        payload = {
            "documentId": doc_id,
            "companyId": cid,
            "title": doc.get("title") or "",
            "contentHashSha256": content_hash,
            "signerName": signer_name,
            "callbackUrl": callback_url,
            "level": "qes",
            "provider": cfg["provider"],
        }

        # Demo path: no external TSP — seal a demo QES audit row immediately.
        if cfg.get("demo"):
            remote = {"id": f"demo-{content_hash[:12]}", "status": "completed", "mode": "demo"}
            _service.repo.add_signature(
                get_db(),
                document_id=doc_id,
                company_id=cid,
                signer_name=signer_name or "QES Demo",
                actor_user_id=_actor_id(),
                stamped=True,
                content_hash=content_hash,
                signature_data=_json.dumps(
                    {
                        "manifest": {
                            "level": "qes_demo",
                            "provider": "demo",
                            "contentHashSha256": content_hash,
                            "remote": remote,
                            "note": "Demo only — not a qualified eIDAS signature.",
                        }
                    },
                    ensure_ascii=False,
                )[:120000],
            )
            return jsonify(
                {
                    "ok": True,
                    "level": "qes_demo",
                    "provider": "demo",
                    "demo": True,
                    "sessionUrl": "",
                    "remote": remote,
                    "contentHash": content_hash,
                    "message": cfg["hint"],
                }
            )

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
                        "callbackUrl": callback_url,
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
                "callbackUrl": callback_url,
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

    @docs_v2_bp.get("/docs/<doc_id>/suggestions")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def list_doc_suggestions(doc_id: str):
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        result = _service.list_suggestions(
            get_db(),
            document_id=doc_id,
            company_id=cid,
            status=str(request.args.get("status") or ""),
        )
        if result.get("error"):
            return jsonify({"error": result["error"]}), int(result.get("status") or 400)
        return jsonify(result)

    @docs_v2_bp.post("/docs/<doc_id>/suggestions")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def create_doc_suggestion(doc_id: str):
        denied = _deny_cap("canReview")
        if denied:
            return denied
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        result = _service.create_suggestion(
            get_db(),
            document_id=doc_id,
            company_id=cid,
            actor_user_id=_actor_id(),
            actor_name=_actor_name(),
            original_text=str(data.get("originalText") or data.get("original_text") or ""),
            proposed_text=str(data.get("proposedText") or data.get("proposed_text") or ""),
            note=str(data.get("note") or ""),
            anchor_index=int(data.get("anchorIndex") or data.get("anchor_index") or 0),
            anchor_length=int(data.get("anchorLength") or data.get("anchor_length") or 0),
        )
        if result.get("error"):
            return jsonify({"error": result["error"]}), int(result.get("status") or 400)
        return jsonify(result)

    @docs_v2_bp.post("/docs/<doc_id>/suggestions/<suggestion_id>/<action>")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def resolve_doc_suggestion(doc_id: str, suggestion_id: str, action: str):
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        result = _service.resolve_suggestion(
            get_db(),
            document_id=doc_id,
            company_id=cid,
            suggestion_id=suggestion_id,
            action=action,
            actor_user_id=_actor_id(),
            actor_role=_actor_role(),
        )
        if result.get("error"):
            return jsonify({"error": result["error"]}), int(result.get("status") or 400)
        return jsonify(result)

    @docs_v2_bp.get("/docs/<doc_id>/review-comments")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def list_review_comments(doc_id: str):
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        result = _service.list_review_comments(get_db(), document_id=doc_id, company_id=cid)
        if result.get("error"):
            return jsonify({"error": result["error"]}), int(result.get("status") or 400)
        return jsonify(result)

    @docs_v2_bp.post("/docs/<doc_id>/review-comments")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def create_review_comment(doc_id: str):
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        result = _service.create_review_comment(
            get_db(),
            document_id=doc_id,
            company_id=cid,
            body=str(data.get("body") or data.get("text") or ""),
            actor_user_id=_actor_id(),
            actor_name=_actor_name(),
            excerpt=str(data.get("excerpt") or ""),
            assignee=str(data.get("assignee") or ""),
            parent_id=str(data.get("parentId") or data.get("parent_id") or "").strip() or None,
            anchor_index=int(data.get("anchorIndex") or data.get("anchor_index") or 0),
            anchor_length=int(data.get("anchorLength") or data.get("anchor_length") or 0),
        )
        if result.get("error"):
            return jsonify({"error": result["error"]}), int(result.get("status") or 400)
        return jsonify(result)

    @docs_v2_bp.patch("/docs/<doc_id>/review-comments/<comment_id>")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def patch_review_comment(doc_id: str, comment_id: str):
        data = request.get_json(silent=True) or {}
        cid = _resolve_company_id(data, required=True)
        if not cid:
            return forbidden_company()
        result = _service.update_review_comment(
            get_db(),
            document_id=doc_id,
            company_id=cid,
            comment_id=comment_id,
            body=None if "body" not in data and "text" not in data else str(data.get("body") or data.get("text") or ""),
            assignee=None if "assignee" not in data else str(data.get("assignee") or ""),
            status=None if "status" not in data else str(data.get("status") or ""),
        )
        if result.get("error"):
            return jsonify({"error": result["error"]}), int(result.get("status") or 400)
        return jsonify(result)

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
        denied = _deny_cap("canPublish")
        if denied:
            return denied
        result = _service.publish_to_worker(
            get_db(),
            doc_id,
            company_id=cid,
            actor_user_id=_actor_id(),
            worker_id=str(data.get("workerId") or data.get("worker_id") or "").strip() or None,
            notify=str(data.get("notify", "1")).lower() not in {"0", "false", "no"},
            doc_type=str(data.get("docType") or data.get("doc_type") or "sonstiges"),
            expiry_date=str(data.get("expiryDate") or data.get("expiry_date") or "").strip() or None,
            compliance_required=str(
                data.get("complianceRequired") if data.get("complianceRequired") is not None else data.get("compliance_required") or ""
            ).lower()
            in {"1", "true", "yes", "on"},
            locale=str(data.get("locale") or data.get("lang") or "").strip()[:2] or None,
        )
        if result.get("error"):
            return jsonify({"error": result["error"]}), int(result.get("status") or 400)
        return jsonify(result)

    @docs_v2_bp.get("/docs/expiring-worker-docs")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def expiring_worker_docs():
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        try:
            days = int(request.args.get("days") or 14)
        except (TypeError, ValueError):
            days = 14
        items = _service.list_expiring_worker_docs(get_db(), company_id=cid, horizon_days=days)
        return jsonify({"ok": True, "items": items, "days": days})

    @docs_v2_bp.get("/docs/unread-worker-docs")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def unread_worker_docs():
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        items = _service.list_unread_editor_docs(get_db(), company_id=cid)
        return jsonify({"ok": True, "items": items, "count": len(items)})

    @docs_v2_bp.get("/docs/<doc_id>/publish-receipts")
    @require_auth
    @require_roles("superadmin", "company-admin", "turnstile")
    def publish_receipts(doc_id: str):
        cid = _resolve_company_id(required=True)
        if not cid:
            return forbidden_company()
        items = _service.list_archives_for_editor_doc(
            get_db(), company_id=cid, editor_document_id=doc_id
        )
        unread = sum(1 for it in items if not it.get("acknowledged"))
        return jsonify({"ok": True, "items": items, "unread": unread, "total": len(items)})

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
