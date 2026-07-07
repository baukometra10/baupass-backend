from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, Flask, g, jsonify, request, send_file

from .._routes import register_blueprint_once
from ..shared import company_id_from_user, forbidden_company
from .service import ChatService

chat_core_bp = Blueprint("chat_domain_core", __name__)


def register_chat_blueprint(flask_app: Flask) -> None:
    from backend.app.platform.plan_guard import capability_blocked_response, require_plan_capability
    from backend.server import get_db, require_auth, require_roles, require_worker_session

    def _worker_chat_allowed(company_id: str):
        from backend.server import company_has_feature, get_company_plan

        plan = get_company_plan(get_db(), company_id)
        if company_has_feature(plan, "worker_chat") or company_has_feature(plan, "worker_app"):
            return None
        return capability_blocked_response(get_db(), company_id, "worker_chat")

    def _worker_session_identity():
        worker = getattr(g, "worker", None)
        if not worker:
            return None, None
        return str(worker.get("id") or ""), str(worker.get("company_id") or "")

    def _normalize_thread_row(row) -> dict:
        from backend.app.domains.chat.service import _json_safe_row

        item = _json_safe_row(row)
        thread_id = str(item.get("id") or item.get("thread_id") or item.get("threadId") or "").strip()
        if thread_id:
            item["id"] = thread_id
            item["threadId"] = thread_id
        return item

    def _admin_can_access_company(company_id: str) -> bool:
        user = getattr(g, "current_user", None) or {}
        role = str(user.get("role") or "")
        target = str(company_id or "")
        if not target:
            return False
        if role == "superadmin":
            return True
        if role == "company-admin":
            return str(user.get("company_id") or "") == target
        return False

    @chat_core_bp.get("/chat/threads")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_threads():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        worker_id = str(request.args.get("worker_id") or "").strip() or None
        service = ChatService(get_db())
        if worker_id:
            return jsonify({"threads": service.list_threads(cid, worker_id=worker_id)})
        return jsonify({"threads": service.list_admin_chat_directory(cid)})

    @chat_core_bp.post("/chat/threads")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_create_thread():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        data = request.get_json(silent=True) or {}
        worker_id = str(data.get("worker_id") or "").strip()
        if not worker_id:
            return jsonify({"error": "worker_required"}), 400
        worker = get_db().execute(
            "SELECT id FROM workers WHERE id = ? AND company_id = ? AND deleted_at IS NULL",
            (worker_id, cid),
        ).fetchone()
        if not worker:
            return jsonify({"error": "worker_not_found"}), 404
        subject = str(data.get("subject") or "general").strip() or "general"
        thread_id = ChatService(get_db()).get_or_create_worker_thread(
            company_id=cid,
            worker_id=worker_id,
            subject=subject,
            created_by_user_id=str(g.current_user.get("id") or ""),
        )
        return jsonify({"ok": True, "threadId": thread_id})

    @chat_core_bp.get("/chat/threads/<thread_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_thread(thread_id: str):
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        service = ChatService(get_db())
        messages = service.list_messages(thread_id, cid)
        service.mark_thread_read(thread_id=thread_id, company_id=cid, reader_type="admin")
        return jsonify({"messages": messages})

    @chat_core_bp.post("/chat/threads/<thread_id>/messages")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_reply(thread_id: str):
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        data = request.get_json(silent=True) or {}
        worker_id = str(data.get("worker_id") or "").strip()
        if not worker_id:
            return jsonify({"error": "worker_required"}), 400
        service = ChatService(get_db())
        try:
            message = service.create_message(
                thread_id=thread_id,
                company_id=cid,
                worker_id=worker_id,
                sender_type="admin",
                sender_user_id=str(g.current_user.get("id") or ""),
                sender_worker_id=None,
                body=str(data.get("body") or ""),
            )
            return jsonify({"ok": True, "message": message})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @chat_core_bp.post("/chat/threads/<thread_id>/attachments")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_attachment(thread_id: str):
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        message_id = str(request.form.get("message_id") or "").strip()
        worker_id = str(request.form.get("worker_id") or "").strip()
        upload = request.files.get("file")
        if not message_id or not worker_id or upload is None:
            return jsonify({"error": "attachment_payload_required", "message": "Datei oder Nachricht fehlt."}), 400
        db = get_db()
        thread = db.execute(
            "SELECT id, worker_id FROM chat_threads WHERE id = ? AND company_id = ?",
            (thread_id, cid),
        ).fetchone()
        if not thread or str(thread["worker_id"]) != worker_id:
            return jsonify({"error": "thread_not_found", "message": "Chat nicht gefunden."}), 404
        message = db.execute(
            "SELECT id FROM chat_messages WHERE id = ? AND thread_id = ? AND company_id = ? AND worker_id = ?",
            (message_id, thread_id, cid, worker_id),
        ).fetchone()
        if not message:
            return jsonify({"error": "message_not_found", "message": "Nachricht nicht gefunden."}), 404
        try:
            attachment = ChatService(db).save_attachment(
                message_id=message_id,
                company_id=cid,
                worker_id=worker_id,
                filename=str(upload.filename or "upload.bin"),
                content_type=str(upload.mimetype or "application/octet-stream"),
                blob=upload.read(),
                e2e_meta=str(request.form.get("e2e_meta") or "").strip(),
                encrypted=str(request.form.get("e2e_encrypted") or request.headers.get("X-E2E-Attachment") or "").strip().lower() in ("1", "true", "yes"),
            )
            return jsonify({"ok": True, "attachment": attachment, "threadId": thread_id})
        except Exception:
            logging.getLogger(__name__).exception("admin_chat_attachment failed for thread %s", thread_id)
            return jsonify({"error": "attachment_upload_failed", "message": "Anhang konnte nicht hochgeladen werden."}), 500

    @chat_core_bp.post("/chat/messages/<message_id>/mark-read")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_mark_read(message_id: str):
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        thread_id = str((request.get_json(silent=True) or {}).get("thread_id") or "").strip()
        if not thread_id:
            return jsonify({"error": "thread_required"}), 400
        ChatService(get_db()).mark_thread_read(thread_id=thread_id, company_id=cid, reader_type="admin")
        return jsonify({"ok": True, "messageId": message_id})

    @chat_core_bp.get("/chat/attachments/<attachment_id>/download")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def download_chat_attachment(attachment_id: str):
        row = get_db().execute(
            "SELECT filename, content_type, file_path, company_id, worker_id FROM chat_attachments WHERE id = ?",
            (attachment_id,),
        ).fetchone()
        if not row:
            return jsonify({"error": "attachment_not_found"}), 404
        attachment_company_id = str(row["company_id"] or "")
        if not _admin_can_access_company(attachment_company_id):
            return jsonify({"error": "attachment_not_found"}), 404
        file_path = ChatService(get_db()).resolve_attachment_path(row)
        if not file_path:
            return jsonify({"error": "attachment_missing", "message": "Datei nicht mehr auf dem Server vorhanden."}), 404
        return send_file(file_path, mimetype=str(row["content_type"] or "application/octet-stream"), as_attachment=True, download_name=str(row["filename"] or "attachment.bin"))

    @chat_core_bp.get("/worker-app/chat/threads")
    @require_worker_session
    def worker_chat_threads():
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing", "message": "Worker-Sitzung ungueltig."}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        try:
            rows = ChatService(get_db()).list_threads(company_id, worker_id=worker_id)
            return jsonify({"threads": [_normalize_thread_row(row) for row in rows]})
        except Exception:
            logging.getLogger(__name__).exception("worker_chat_threads failed for worker %s", worker_id)
            return jsonify({"threads": []})

    @chat_core_bp.post("/worker-app/chat/threads")
    @require_worker_session
    def worker_create_thread():
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing", "message": "Worker-Sitzung ungueltig."}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        data = request.get_json(silent=True) or {}
        subject = str(data.get("subject") or "general").strip() or "general"
        try:
            thread_id = ChatService(get_db()).get_or_create_worker_thread(
                company_id=company_id,
                worker_id=worker_id,
                subject=subject,
            )
            return jsonify({"ok": True, "threadId": thread_id})
        except Exception:
            logging.getLogger(__name__).exception("worker_create_thread failed for worker %s", worker_id)
            return jsonify({"error": "chat_thread_failed", "message": "Chat konnte nicht gestartet werden."}), 500

    @chat_core_bp.get("/worker-app/chat/threads/<thread_id>/messages")
    @require_worker_session
    def worker_chat_messages(thread_id: str):
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing", "message": "Worker-Sitzung ungueltig."}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        service = ChatService(get_db())
        try:
            messages = service.list_messages(thread_id, company_id)
            messages = [msg for msg in messages if str(msg.get("workerId")) == worker_id]
            try:
                service.mark_thread_read(thread_id=thread_id, company_id=company_id, reader_type="worker")
            except Exception:
                pass
            return jsonify({"messages": messages})
        except Exception:
            logging.getLogger(__name__).exception("worker_chat_messages failed for thread %s", thread_id)
            return jsonify({"error": "chat_load_failed", "message": "Nachrichten konnten nicht geladen werden.", "messages": []}), 500

    @chat_core_bp.get("/worker-app/chat/attachments/<attachment_id>/download")
    @require_worker_session
    def worker_chat_attachment_download(attachment_id: str):
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing", "message": "Worker-Sitzung ungueltig."}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        row = get_db().execute(
            "SELECT filename, content_type, file_path, worker_id, company_id FROM chat_attachments WHERE id = ?",
            (attachment_id,),
        ).fetchone()
        if not row or str(row["worker_id"]) != worker_id:
            return jsonify({"error": "attachment_not_found"}), 404
        file_path = ChatService(get_db()).resolve_attachment_path(row)
        if not file_path:
            return jsonify({"error": "attachment_missing", "message": "Datei nicht mehr auf dem Server vorhanden."}), 404
        return send_file(file_path, mimetype=str(row["content_type"] or "application/octet-stream"), as_attachment=True, download_name=str(row["filename"] or "attachment.bin"))

    @chat_core_bp.post("/worker-app/chat/threads/<thread_id>/messages")
    @require_worker_session
    def worker_chat_send(thread_id: str):
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing", "message": "Worker-Sitzung ungueltig."}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        data = request.get_json(silent=True) or {}
        service = ChatService(get_db())
        thread = get_db().execute(
            "SELECT id, worker_id FROM chat_threads WHERE id = ? AND company_id = ?",
            (thread_id, company_id),
        ).fetchone()
        if not thread or str(thread["worker_id"]) != worker_id:
            return jsonify({"error": "thread_not_found", "message": "Chat nicht gefunden."}), 404
        e2e_client_unavailable = str(request.headers.get("X-E2E-Client-Unavailable") or "").strip().lower() in {"1", "true", "yes"}
        try:
            message = service.create_message(
                thread_id=thread_id,
                company_id=company_id,
                worker_id=worker_id,
                sender_type="worker",
                sender_user_id=None,
                sender_worker_id=worker_id,
                body=str(data.get("body") or ""),
                allow_plaintext_e2e_fallback=e2e_client_unavailable,
            )
            return jsonify({"ok": True, "message": message})
        except ValueError as exc:
            return jsonify({"error": str(exc), "message": "Nachricht fehlt oder ist ungueltig."}), 400
        except Exception:
            logging.getLogger(__name__).exception("worker_chat_send failed for thread %s", thread_id)
            return jsonify({"error": "chat_send_failed", "message": "Nachricht konnte nicht gesendet werden."}), 500

    @chat_core_bp.delete("/worker-app/chat/messages/<message_id>")
    @require_worker_session
    def worker_chat_delete_message(message_id: str):
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing", "message": "Worker-Sitzung ungueltig."}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        try:
            ChatService(get_db()).delete_message(
                message_id,
                company_id,
                actor_type="worker",
                actor_worker_id=worker_id,
            )
            return jsonify({"ok": True, "messageId": message_id})
        except ValueError as exc:
            code = str(exc)
            status = 403 if code == "forbidden" else 400
            messages = {
                "message_not_found": "Nachricht nicht gefunden.",
                "message_already_read": "Nachricht wurde bereits gelesen und kann nicht geloescht werden.",
                "forbidden": "Keine Berechtigung zum Loeschen.",
            }
            return jsonify({"error": code, "message": messages.get(code, code)}), status

    @chat_core_bp.delete("/worker-app/chat/threads/<thread_id>/messages")
    @require_worker_session
    def worker_chat_clear_messages(thread_id: str):
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing", "message": "Worker-Sitzung ungueltig."}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        scope = str(request.args.get("scope") or "own").strip().lower() or "own"
        try:
            deleted = ChatService(get_db()).clear_thread_messages(
                thread_id,
                company_id,
                actor_type="worker",
                actor_worker_id=worker_id,
                scope=scope,
            )
            return jsonify({"ok": True, "deleted": deleted, "threadId": thread_id})
        except ValueError as exc:
            code = str(exc)
            status = 403 if code == "forbidden" else 400
            return jsonify({"error": code, "message": code}), status

    @chat_core_bp.delete("/chat/messages/<message_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_delete_message(message_id: str):
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        worker_id = str(request.args.get("worker_id") or "").strip()
        if not worker_id:
            worker_id = str((request.get_json(silent=True) or {}).get("worker_id") or "").strip()
        if not worker_id:
            return jsonify({"error": "worker_required"}), 400
        try:
            ChatService(get_db()).delete_message(
                message_id,
                cid,
                actor_type="admin",
                actor_user_id=str(g.current_user.get("id") or ""),
            )
            return jsonify({"ok": True, "messageId": message_id})
        except ValueError as exc:
            code = str(exc)
            status = 403 if code == "forbidden" else 400
            messages = {
                "message_not_found": "Nachricht nicht gefunden.",
                "message_already_read": "Nachricht wurde bereits gelesen und kann nicht geloescht werden.",
                "forbidden": "Keine Berechtigung zum Loeschen.",
            }
            return jsonify({"error": code, "message": messages.get(code, code)}), status

    @chat_core_bp.delete("/chat/threads/<thread_id>/messages")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_clear_messages(thread_id: str):
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        scope = str(request.args.get("scope") or "own").strip().lower() or "own"
        try:
            deleted = ChatService(get_db()).clear_thread_messages(
                thread_id,
                cid,
                actor_type="admin",
                actor_user_id=str(g.current_user.get("id") or ""),
                scope=scope,
            )
            return jsonify({"ok": True, "deleted": deleted, "threadId": thread_id})
        except ValueError as exc:
            code = str(exc)
            status = 403 if code == "forbidden" else 400
            return jsonify({"error": code, "message": code}), status

    @chat_core_bp.post("/worker-app/chat/threads/<thread_id>/attachments")
    @require_worker_session
    def worker_chat_attachment(thread_id: str):
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing", "message": "Worker-Sitzung ungueltig."}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        message_id = str(request.form.get("message_id") or "").strip()
        upload = request.files.get("file")
        if not message_id or upload is None:
            return jsonify({"error": "attachment_payload_required"}), 400
        db = get_db()
        thread = db.execute(
            "SELECT id, worker_id FROM chat_threads WHERE id = ? AND company_id = ?",
            (thread_id, company_id),
        ).fetchone()
        if not thread or str(thread["worker_id"]) != worker_id:
            return jsonify({"error": "thread_not_found", "message": "Chat nicht gefunden."}), 404
        message = db.execute(
            "SELECT id FROM chat_messages WHERE id = ? AND thread_id = ? AND company_id = ? AND worker_id = ?",
            (message_id, thread_id, company_id, worker_id),
        ).fetchone()
        if not message:
            return jsonify({"error": "message_not_found", "message": "Nachricht nicht gefunden."}), 404
        blob = upload.read()
        filename = str(upload.filename or "upload.bin")
        from backend.server import normalize_upload_mimetype
        content_type = normalize_upload_mimetype(str(upload.mimetype or "application/octet-stream"), filename)
        service = ChatService(db)
        try:
            attachment = service.save_attachment(
                message_id=message_id,
                company_id=company_id,
                worker_id=worker_id,
                filename=filename,
                content_type=content_type,
                blob=blob,
                e2e_meta=str(request.form.get("e2e_meta") or "").strip(),
                encrypted=str(request.form.get("e2e_encrypted") or request.headers.get("X-E2E-Attachment") or "").strip().lower() in ("1", "true", "yes"),
            )
            doc_type = str(request.form.get("doc_type") or "sonstiges").strip() or "sonstiges"
            document_id = service.register_worker_chat_submission(
                worker_id=worker_id,
                company_id=company_id,
                filename=filename,
                content_type=content_type,
                blob=blob,
                doc_type_raw=doc_type,
            )
            return jsonify({"ok": True, "attachment": attachment, "threadId": thread_id, "documentId": document_id})
        except Exception:
            logging.getLogger(__name__).exception("worker_chat_attachment failed for thread %s", thread_id)
            return jsonify({"error": "attachment_upload_failed", "message": "Anhang konnte nicht hochgeladen werden."}), 500

    register_blueprint_once(flask_app, chat_core_bp, url_prefix="/api")
    print("[baupass] domain/chat: worker-company chat routes registered", flush=True)
