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

    @chat_core_bp.get("/chat/threads/<thread_id>/search")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_search(thread_id: str):
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        query = str(request.args.get("q") or request.args.get("query") or "").strip()
        if not query:
            return jsonify({"results": []})
        service = ChatService(get_db())
        results = service.search_messages(thread_id, cid, query)
        return jsonify({"results": results, "query": query})

    @chat_core_bp.post("/chat/threads/<thread_id>/typing")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_typing(thread_id: str):
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        data = request.get_json(silent=True) or {}
        worker_id = str(data.get("worker_id") or "").strip()
        if not worker_id:
            return jsonify({"error": "worker_required"}), 400
        from .typing import set_typing

        user = getattr(g, "current_user", None) or {}
        actor_label = str(user.get("name") or user.get("email") or "Arbeitgeber").strip()
        set_typing(
            thread_id=thread_id,
            company_id=cid,
            worker_id=worker_id,
            actor_type="admin",
            actor_id=str(user.get("id") or ""),
            actor_label=actor_label,
        )
        return jsonify({"ok": True})

    @chat_core_bp.get("/chat/threads/<thread_id>/typing")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_typing_status(thread_id: str):
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        from .typing import list_typing

        user = getattr(g, "current_user", None) or {}
        actors = list_typing(
            thread_id,
            exclude_actor_type="admin",
            exclude_actor_id=str(user.get("id") or ""),
        )
        return jsonify({"actors": actors})

    @chat_core_bp.post("/chat/push-subscribe")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def admin_chat_push_subscribe():
        import secrets

        from backend.server import now_iso

        user = getattr(g, "current_user", None) or {}
        data = request.get_json(silent=True) or {}
        endpoint = str(data.get("endpoint") or "").strip()
        p256dh = str(data.get("p256dh") or "").strip()
        auth_key = str(data.get("auth") or "").strip()
        cid = str(data.get("company_id") or user.get("company_id") or company_id_from_user() or "").strip()
        if not endpoint or not p256dh or not auth_key or not cid:
            return jsonify({"error": "missing_fields"}), 400
        if user.get("role") == "company-admin" and str(user.get("company_id") or "") != cid:
            return jsonify({"error": "forbidden"}), 403
        db = get_db()
        user_id = str(user.get("id") or "")
        existing = db.execute("SELECT id FROM admin_push_subscriptions WHERE endpoint = ?", (endpoint,)).fetchone()
        now = now_iso()
        if existing:
            db.execute(
                """
                UPDATE admin_push_subscriptions
                SET user_id = ?, company_id = ?, p256dh = ?, auth = ?, updated_at = ?
                WHERE endpoint = ?
                """,
                (user_id, cid, p256dh, auth_key, now, endpoint),
            )
        else:
            db.execute(
                """
                INSERT INTO admin_push_subscriptions
                (id, user_id, company_id, endpoint, p256dh, auth, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"apsub-{secrets.token_hex(8)}", user_id, cid, endpoint, p256dh, auth_key, now, now),
            )
        db.commit()
        return jsonify({"ok": True})

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
        e2e_client_unavailable = str(request.headers.get("X-E2E-Client-Unavailable") or "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
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
                allow_plaintext_e2e_fallback=e2e_client_unavailable,
                reply_to_message_id=str(data.get("reply_to_message_id") or data.get("replyToMessageId") or "").strip() or None,
            )
            return jsonify({"ok": True, "message": message})
        except ValueError as exc:
            code = str(exc)
            messages = {
                "message_required": "Nachricht fehlt.",
                "e2e_required": "Verschlüsselte Nachricht erforderlich — E2E-Schlüssel prüfen.",
            }
            return jsonify({"error": code, "message": messages.get(code, code)}), 400

    @chat_core_bp.get("/worker-app/chat/events/recent")
    @require_worker_session
    def worker_chat_events_recent():
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing", "message": "Worker-Sitzung ungueltig."}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        from backend.app.platform.events.bus import list_recent_events

        since_id = str(request.args.get("since_id") or "").strip() or None
        limit = min(50, max(1, int(request.args.get("limit", "25"))))
        raw_events = list_recent_events(company_id, limit=200, since_id=since_id)
        events = []
        for evt in reversed(raw_events):
            evt_type = str(evt.get("type") or "")
            if evt_type not in {"chat.message_created", "chat.typing"}:
                continue
            payload = evt.get("payload") or {}
            if evt_type == "chat.message_created" and str(payload.get("workerId") or "") != worker_id:
                continue
            if evt_type == "chat.typing" and str(payload.get("workerId") or "") != worker_id:
                continue
            events.append(evt)
            if len(events) >= limit:
                break
        return jsonify({"events": events})

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

    @chat_core_bp.get("/worker-app/chat/threads/<thread_id>/search")
    @require_worker_session
    def worker_chat_search(thread_id: str):
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing"}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        query = str(request.args.get("q") or request.args.get("query") or "").strip()
        if not query:
            return jsonify({"results": []})
        service = ChatService(get_db())
        results = service.search_messages(thread_id, company_id, query)
        return jsonify({"results": results, "query": query})

    @chat_core_bp.post("/worker-app/chat/threads/<thread_id>/typing")
    @require_worker_session
    def worker_chat_typing(thread_id: str):
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing"}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        from .typing import set_typing

        worker = getattr(g, "worker", None) or {}
        actor_label = f"{worker.get('first_name') or ''} {worker.get('last_name') or ''}".strip() or worker_id
        set_typing(
            thread_id=thread_id,
            company_id=company_id,
            worker_id=worker_id,
            actor_type="worker",
            actor_id=worker_id,
            actor_label=actor_label,
        )
        return jsonify({"ok": True})

    @chat_core_bp.get("/worker-app/chat/threads/<thread_id>/typing")
    @require_worker_session
    def worker_chat_typing_status(thread_id: str):
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing"}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        from .typing import list_typing

        actors = list_typing(
            thread_id,
            exclude_actor_type="worker",
            exclude_actor_id=worker_id,
        )
        return jsonify({"actors": actors})

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
                reply_to_message_id=str(data.get("reply_to_message_id") or data.get("replyToMessageId") or "").strip() or None,
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
        filename = str(request.form.get("original_filename") or upload.filename or "upload.bin").strip() or "upload.bin"
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

    @chat_core_bp.post("/chat/broadcast")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_broadcast():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        data = request.get_json(silent=True) or {}
        title = str(data.get("title") or "Mitteilung").strip()[:200] or "Mitteilung"
        message = str(data.get("message") or "").strip()
        if not message:
            return jsonify({"error": "message_required", "message": "Nachricht fehlt."}), 400
        message = message[:1000]
        send_email = str(data.get("send_email") or "false").strip().lower() in ("1", "true", "yes")
        raw_excluded = data.get("excludeWorkerIds") or data.get("exclude_worker_ids") or []
        if raw_excluded is None:
            raw_excluded = []
        if not isinstance(raw_excluded, list):
            return jsonify({"error": "invalid_exclusions", "message": "excludeWorkerIds muss eine Liste sein."}), 400
        excluded_ids = []
        for item in raw_excluded[:400]:
            wid = str(item or "").strip()
            if not wid:
                continue
            excluded_ids.append(wid[:64])
        excluded_ids = sorted(set(excluded_ids))
        db = get_db()
        params = [cid]
        exclusion_sql = ""
        if excluded_ids:
            exclusion_sql = " AND id NOT IN ({})".format(",".join(["?"] * len(excluded_ids)))
            params.extend(excluded_ids)
        workers = db.execute(
            f"""
            SELECT id FROM workers
            WHERE company_id = ?
              AND deleted_at IS NULL
              AND worker_type = 'worker'
              {exclusion_sql}
            """,
            tuple(params),
        ).fetchall()
        if len(workers) > 20000:
            return jsonify({"error": "broadcast_too_large", "message": "Zu viele Mitarbeiter für Broadcast."}), 413
        from flask import g

        worker_ids = [str(row["id"] or "").strip() for row in workers if str(row["id"] or "").strip()]
        chat = ChatService(db)
        messages_sent = chat.broadcast_to_workers(
            company_id=cid,
            worker_ids=worker_ids,
            title=title,
            message=message,
            sender_user_id=str(g.current_user.get("id") or ""),
        )
        if send_email and messages_sent:
            from backend.app.platform.notifications.worker_mitteilung import notify_worker_mitteilung

            for wid in worker_ids:
                try:
                    notify_worker_mitteilung(
                        db,
                        wid,
                        notif_type="company_broadcast",
                        title=title,
                        message=message,
                        action_url="chat",
                        push_tag="company-broadcast",
                        send_email=True,
                        skip_push=True,
                    )
                except Exception:
                    logging.getLogger(__name__).exception("broadcast email failed worker %s", wid)
        try:
            from backend.server import log_audit

            log_audit(
                "chat.broadcast",
                f"Broadcast an {messages_sent} Mitarbeiter (excluded={len(excluded_ids)}, send_email={1 if send_email else 0})",
                target_type="company",
                target_id=str(cid),
                company_id=str(cid),
                actor=getattr(g, "current_user", None),
            )
        except Exception:
            pass

        try:
            db.commit()
        except Exception:
            pass
        return jsonify(
            {
                "ok": True,
                "notified": messages_sent,
                "messagesSent": messages_sent,
                "total": len(worker_ids),
                "excluded": len(excluded_ids),
            }
        )

    def _voice_call_error(exc: ValueError):
        code = str(exc)
        status_map = {
            "worker_not_found": 404,
            "call_not_found": 404,
            "worker_busy": 409,
            "call_not_ringing": 409,
            "call_not_active": 409,
            "forbidden": 403,
            "invalid_signal_type": 400,
            "invalid_sender_role": 400,
        }
        messages = {
            "worker_not_found": "Mitarbeiter nicht gefunden.",
            "call_not_found": "Anruf nicht gefunden.",
            "worker_busy": "Mitarbeiter ist bereits in einem Anruf.",
            "call_not_ringing": "Anruf klingelt nicht mehr.",
            "call_not_active": "Anruf ist nicht mehr aktiv.",
            "forbidden": "Keine Berechtigung.",
            "invalid_signal_type": "Ungueltiger Signaltyp.",
            "invalid_sender_role": "Ungueltige Rolle.",
        }
        return jsonify({"error": code, "message": messages.get(code, code)}), status_map.get(code, 400)

    def _assert_admin_call_access(call: dict, company_id: str) -> bool:
        return str(call.get("companyId") or "") == str(company_id or "")

    def _assert_worker_call_access(call: dict, worker_id: str) -> bool:
        return str(call.get("workerId") or "") == str(worker_id or "")

    @chat_core_bp.get("/chat/calls/ice-config")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_call_ice_config():
        from backend.app.platform.voice_calls.service import ice_servers_diagnostics

        return jsonify({"ok": True, "ice": ice_servers_diagnostics()})

    @chat_core_bp.post("/chat/calls")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_call_start():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        data = request.get_json(silent=True) or {}
        worker_id = str(data.get("worker_id") or data.get("workerId") or "").strip()
        if not worker_id:
            return jsonify({"error": "worker_required"}), 400
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        try:
            call = service.start_call(
                company_id=cid,
                worker_id=worker_id,
                caller_user_id=str(g.current_user.get("id") or ""),
            )
            get_db().commit()
            return jsonify({"ok": True, "call": call})
        except ValueError as exc:
            return _voice_call_error(exc)

    @chat_core_bp.get("/chat/calls/incoming")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_call_incoming():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        call = service.get_incoming_for_admin(cid)
        return jsonify({"call": call})

    @chat_core_bp.post("/chat/calls/<call_id>/accept")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_call_accept(call_id: str):
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        try:
            call = service.get_call(call_id)
            if not _assert_admin_call_access(call, cid):
                return jsonify({"error": "forbidden"}), 403
            updated = service.accept_call(call_id, role="admin")
            get_db().commit()
            return jsonify({"ok": True, "call": updated})
        except ValueError as exc:
            return _voice_call_error(exc)

    @chat_core_bp.post("/chat/calls/<call_id>/decline")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_call_decline(call_id: str):
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        try:
            call = service.get_call(call_id)
            if not _assert_admin_call_access(call, cid):
                return jsonify({"error": "forbidden"}), 403
            updated = service.decline_call(call_id, role="admin")
            get_db().commit()
            return jsonify({"ok": True, "call": updated})
        except ValueError as exc:
            return _voice_call_error(exc)

    @chat_core_bp.get("/chat/calls/<call_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_call_get(call_id: str):
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        try:
            call = service.get_call(call_id)
            if not _assert_admin_call_access(call, cid):
                return jsonify({"error": "forbidden"}), 403
            return jsonify({"call": call})
        except ValueError as exc:
            return _voice_call_error(exc)

    @chat_core_bp.post("/chat/calls/<call_id>/signal")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_call_signal(call_id: str):
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        data = request.get_json(silent=True) or {}
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        try:
            call = service.get_call(call_id)
            if not _assert_admin_call_access(call, cid):
                return jsonify({"error": "forbidden"}), 403
            signal = service.add_signal(
                call_id,
                sender_role="admin",
                signal_type=str(data.get("type") or data.get("signalType") or ""),
                payload=data.get("payload") or data.get("sdp") or data.get("candidate"),
            )
            get_db().commit()
            return jsonify({"ok": True, "signal": signal})
        except ValueError as exc:
            return _voice_call_error(exc)

    @chat_core_bp.get("/chat/calls/<call_id>/signals")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_call_signals(call_id: str):
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        since_id = str(request.args.get("since_id") or request.args.get("sinceId") or "").strip()
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        try:
            call = service.get_call(call_id)
            if not _assert_admin_call_access(call, cid):
                return jsonify({"error": "forbidden"}), 403
            signals = service.list_signals(call_id, for_role="admin", since_id=since_id)
            return jsonify({"signals": signals, "call": call})
        except ValueError as exc:
            return _voice_call_error(exc)

    @chat_core_bp.post("/chat/calls/<call_id>/end")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_call_end(call_id: str):
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        data = request.get_json(silent=True) or {}
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        try:
            call = service.get_call(call_id)
            if not _assert_admin_call_access(call, cid):
                return jsonify({"error": "forbidden"}), 403
            updated = service.end_call(call_id, role="admin", reason=str(data.get("reason") or "hangup"))
            get_db().commit()
            return jsonify({"ok": True, "call": updated})
        except ValueError as exc:
            return _voice_call_error(exc)

    @chat_core_bp.post("/worker-app/chat/calls")
    @require_worker_session
    def worker_chat_call_start():
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing"}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        try:
            call = service.start_worker_call(company_id=company_id, worker_id=worker_id)
            get_db().commit()
            return jsonify({"ok": True, "call": call})
        except ValueError as exc:
            return _voice_call_error(exc)

    @chat_core_bp.get("/worker-app/chat/calls/<call_id>")
    @require_worker_session
    def worker_chat_call_get(call_id: str):
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing"}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        try:
            call = service.get_call(call_id)
            if not _assert_worker_call_access(call, worker_id):
                return jsonify({"error": "forbidden"}), 403
            return jsonify({"call": call})
        except ValueError as exc:
            return _voice_call_error(exc)

    @chat_core_bp.get("/worker-app/chat/calls/incoming")
    @require_worker_session
    def worker_chat_call_incoming():
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing"}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        call = service.get_incoming_for_worker(worker_id)
        return jsonify({"call": call})

    @chat_core_bp.post("/worker-app/chat/calls/<call_id>/accept")
    @require_worker_session
    def worker_chat_call_accept(call_id: str):
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing"}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        try:
            call = service.get_call(call_id)
            if not _assert_worker_call_access(call, worker_id):
                return jsonify({"error": "forbidden"}), 403
            updated = service.accept_call(call_id, role="worker")
            get_db().commit()
            return jsonify({"ok": True, "call": updated})
        except ValueError as exc:
            return _voice_call_error(exc)

    @chat_core_bp.post("/worker-app/chat/calls/<call_id>/decline")
    @require_worker_session
    def worker_chat_call_decline(call_id: str):
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing"}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        try:
            call = service.get_call(call_id)
            if not _assert_worker_call_access(call, worker_id):
                return jsonify({"error": "forbidden"}), 403
            updated = service.decline_call(call_id, role="worker")
            get_db().commit()
            return jsonify({"ok": True, "call": updated})
        except ValueError as exc:
            return _voice_call_error(exc)

    @chat_core_bp.post("/worker-app/chat/calls/<call_id>/signal")
    @require_worker_session
    def worker_chat_call_signal(call_id: str):
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing"}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        data = request.get_json(silent=True) or {}
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        try:
            call = service.get_call(call_id)
            if not _assert_worker_call_access(call, worker_id):
                return jsonify({"error": "forbidden"}), 403
            signal = service.add_signal(
                call_id,
                sender_role="worker",
                signal_type=str(data.get("type") or data.get("signalType") or ""),
                payload=data.get("payload") or data.get("sdp") or data.get("candidate"),
            )
            get_db().commit()
            return jsonify({"ok": True, "signal": signal})
        except ValueError as exc:
            return _voice_call_error(exc)

    @chat_core_bp.get("/worker-app/chat/calls/<call_id>/signals")
    @require_worker_session
    def worker_chat_call_signals(call_id: str):
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing"}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        since_id = str(request.args.get("since_id") or request.args.get("sinceId") or "").strip()
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        try:
            call = service.get_call(call_id)
            if not _assert_worker_call_access(call, worker_id):
                return jsonify({"error": "forbidden"}), 403
            signals = service.list_signals(call_id, for_role="worker", since_id=since_id)
            return jsonify({"signals": signals, "call": call})
        except ValueError as exc:
            return _voice_call_error(exc)

    @chat_core_bp.post("/worker-app/chat/calls/<call_id>/end")
    @require_worker_session
    def worker_chat_call_end(call_id: str):
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing"}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        data = request.get_json(silent=True) or {}
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        try:
            call = service.get_call(call_id)
            if not _assert_worker_call_access(call, worker_id):
                return jsonify({"error": "forbidden"}), 403
            updated = service.end_call(call_id, role="worker", reason=str(data.get("reason") or "hangup"))
            get_db().commit()
            return jsonify({"ok": True, "call": updated})
        except ValueError as exc:
            return _voice_call_error(exc)

    @chat_core_bp.get("/chat/calls/history")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("worker_chat")
    def admin_chat_call_history():
        cid = company_id_from_user()
        if not cid:
            return forbidden_company()
        worker_id = str(request.args.get("worker_id") or request.args.get("workerId") or "").strip() or None
        limit = int(request.args.get("limit") or 50)
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        calls = service.list_calls(company_id=cid, worker_id=worker_id, limit=limit)
        missed = service.count_missed_calls(company_id=cid, worker_id=worker_id)
        return jsonify({"calls": calls, "missedCount": missed})

    @chat_core_bp.get("/worker-app/chat/calls/history")
    @require_worker_session
    def worker_chat_call_history():
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing"}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        limit = int(request.args.get("limit") or 50)
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        calls = service.list_calls(company_id=company_id, worker_id=worker_id, limit=limit)
        missed = service.count_missed_calls(company_id=company_id, worker_id=worker_id)
        return jsonify({"calls": calls, "missedCount": missed})

    @chat_core_bp.post("/worker-app/chat/calls/callback-request")
    @require_worker_session
    def worker_chat_call_callback_request():
        worker_id, company_id = _worker_session_identity()
        if not worker_id or not company_id:
            return jsonify({"error": "worker_context_missing"}), 401
        blocked = _worker_chat_allowed(company_id)
        if blocked:
            return blocked
        data = request.get_json(silent=True) or {}
        call_id = str(data.get("call_id") or data.get("callId") or "").strip() or None
        from backend.app.platform.voice_calls.service import VoiceCallService

        service = VoiceCallService(get_db())
        try:
            result = service.request_worker_callback(
                company_id=company_id,
                worker_id=worker_id,
                call_id=call_id,
            )
            get_db().commit()
            return jsonify(result)
        except ValueError as exc:
            return _voice_call_error(exc)

    register_blueprint_once(flask_app, chat_core_bp, url_prefix="/api")
    print("[baupass] domain/chat: worker-company chat routes registered", flush=True)
