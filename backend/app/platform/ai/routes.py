"""
AI routes — assistant + workforce intelligence.
"""
from __future__ import annotations

import logging

from flask import Blueprint, Flask, Response, g, jsonify, request, stream_with_context

logger = logging.getLogger("baupass.ai.routes")

ai_bp = Blueprint("platform_ai", __name__)


def _resolve_company_id_from_request(data: dict | None = None) -> str:
    """Company IDs are strings (cmp-…), never integers."""
    data = data or {}
    role = str(g.current_user.get("role") or "")
    if role == "superadmin":
        return (
            str(data.get("company_id") or request.args.get("company_id") or "").strip()
            or str(getattr(g, "preview_company_id", "") or "").strip()
            or str(g.current_user.get("preview_company_id") or "").strip()
        )
    return str(g.current_user.get("company_id") or "").strip()


def _parse_spoken_flag(data: dict | None) -> bool:
    data = data or {}
    spoken = data.get("spoken", data.get("voice_mode", False))
    if isinstance(spoken, str):
        return spoken.lower() not in {"0", "false", "no"}
    return bool(spoken)


def _parse_bool_flag(value, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no"}


def register_ai_blueprint(flask_app: Flask) -> None:
    from backend.app.platform.plan_guard import require_plan_capability
    from backend.server import require_auth, require_roles, get_db

    @ai_bp.get("/ai/status")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ai_status():
        from .assistant import ai_config_status

        lang = str(request.args.get("lang") or "de")[:2]
        return jsonify(ai_config_status(lang))

    def _operator_plan_allowed(db, company_id: str) -> bool:
        """FAB / voice assistant is an enterprise plan capability (ai_assistant)."""
        try:
            from backend.server import company_has_feature, get_company_plan

            plan = get_company_plan(db, company_id)
            return bool(company_has_feature(plan, "ai_assistant"))
        except Exception:
            # Fail open for superadmin tooling if plan lookup breaks; FAB still respects toggle.
            role = str((g.current_user or {}).get("role") or "")
            return role == "superadmin"

    @ai_bp.get("/ai/operator/pulse")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_operator_pulse():
        """Prioritized daily recommendations for the ubiquitous AI Operator FAB."""
        from .operator_pulse import build_operator_pulse

        company_id = _resolve_company_id_from_request()
        if not company_id:
            return jsonify({"error": "company_required", "urgency": 0, "recommendations": []}), 400
        lang = str(request.args.get("lang") or "de")[:2]
        surface = str(request.args.get("surface") or "").strip()
        tab = str(request.args.get("tab") or "").strip()
        path = str(request.args.get("path") or "").strip()
        role = str(g.current_user.get("role") or "company-admin")
        db = get_db()
        if not _operator_plan_allowed(db, company_id):
            return jsonify(
                {
                    "error": "plan_required",
                    "capability": "ai_assistant",
                    "urgency": 0,
                    "urgent": False,
                    "recommendations": [],
                    "companyId": company_id,
                }
            ), 403
        pulse = build_operator_pulse(
            db,
            company_id,
            role=role,
            lang=lang,
            surface=surface or None,
            tab=tab or None,
            path=path or None,
        )
        return jsonify(pulse)

    @ai_bp.post("/ai/operator/pulse/dispatch")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_operator_pulse_dispatch():
        """Manually send morning-style pulse briefing (Slack/Teams/email) for one company."""
        from .notifications import dispatch_briefing_notifications
        from .scheduler import build_company_morning_dispatch

        data = request.get_json(silent=True) or {}
        company_id = _resolve_company_id_from_request(data)
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        include_llm = _parse_bool_flag(data.get("include_llm"), default=True)
        dry_run = _parse_bool_flag(data.get("dry_run"), default=False)
        db = get_db()
        if not _operator_plan_allowed(db, company_id):
            return jsonify({"error": "plan_required", "capability": "ai_assistant"}), 403

        from .langs import try_normalize_ui_lang
        from .operator_settings import (
            get_settings,
            resolve_briefing_email,
            resolve_briefing_lang,
            resolve_briefing_tz,
            resolve_effective_briefing_hours,
        )

        settings = get_settings(db, company_id)
        lang_raw = str(data.get("lang") or request.args.get("lang") or "").strip()
        if lang_raw and lang_raw.lower() not in {"auto", "automatic", "automatisch", "*"}:
            lang = try_normalize_ui_lang(lang_raw) or resolve_briefing_lang(
                settings, db=db, company_id=company_id
            )
        else:
            lang = resolve_briefing_lang(settings, db=db, company_id=company_id)

        company_name = company_id
        try:
            row = db.execute(
                "SELECT name FROM companies WHERE id = ? AND deleted_at IS NULL",
                (company_id,),
            ).fetchone()
            if row:
                company_name = str(row["name"] or company_id)
        except Exception:
            pass

        payload = build_company_morning_dispatch(
            db,
            company_id,
            company_name=company_name,
            lang=lang,
            include_llm=include_llm,
        )
        body = str(payload.get("body") or "").strip()
        title = f"Suppix AI — {company_name}"
        preview_meta = {
            "email": resolve_briefing_email(settings, db=db, company_id=company_id),
            "lang": resolve_briefing_lang(settings, db=db, company_id=company_id),
            "tz": resolve_briefing_tz(settings, db=db, company_id=company_id),
            "hours": resolve_effective_briefing_hours(settings, db=db, company_id=company_id),
            "sectorTerms": payload.get("sectorTerms") or (payload.get("pulse") or {}).get("sectorTerms") or {},
        }
        if dry_run or not body:
            return jsonify(
                {
                    "ok": True,
                    "dryRun": True,
                    "title": title,
                    "preview": preview_meta,
                    **payload,
                }
            )

        dispatch = dispatch_briefing_notifications(body, company_id=company_id, title=title)
        email_result = None
        briefing_email = resolve_briefing_email(settings, db=db, company_id=company_id)
        if briefing_email:
            from .mailer import send_ai_briefing_email

            ok, err = send_ai_briefing_email(to=briefing_email, subject=title, body_text=body)
            email_result = {"ok": ok, "to": briefing_email, "error": err or None}

        return jsonify(
            {
                "ok": True,
                "dryRun": False,
                "title": title,
                "dispatch": dispatch,
                "email": email_result,
                "urgency": payload.get("urgency"),
                "body": body,
                "companyId": company_id,
            }
        )

    @ai_bp.get("/ai/operator/status")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ai_operator_status():
        """Live readiness: TTS provider + briefing cron + SMTP + resolved briefing meta."""
        import os

        from .operator_settings import (
            enrich_settings_for_api,
            get_settings,
        )
        from .tts import tts_config_status

        company_id = _resolve_company_id_from_request()
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        db = get_db()
        if not _operator_plan_allowed(db, company_id):
            return jsonify({"error": "plan_required", "capability": "ai_assistant"}), 403
        settings = enrich_settings_for_api(db, company_id, get_settings(db, company_id))
        cron_on = str(os.getenv("BAUPASS_AI_BRIEFING_CRON", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        smtp_ok = bool((os.getenv("SMTP_HOST") or "").strip())
        tts = tts_config_status()
        return jsonify(
            {
                "company_id": company_id,
                "tts": {
                    "provider": tts.get("provider"),
                    "configured": bool(tts.get("configured")),
                    "elevenLabsConfigured": bool(tts.get("elevenLabsConfigured")),
                    "openaiConfigured": bool(tts.get("openaiConfigured")),
                    "hint": tts.get("hint"),
                },
                "briefing": {
                    "cronEnabled": cron_on,
                    "smtpConfigured": smtp_ok,
                    "emailResolved": settings.get("briefingEmailResolved") or "",
                    "langResolved": settings.get("briefingLangResolved") or "",
                    "hoursResolved": settings.get("briefingHoursResolved") or [],
                    "tzResolved": settings.get("briefingTzResolved") or "",
                    "enabled": settings.get("briefingEnabled") is not False,
                },
                "ok": bool(tts.get("configured")) and (cron_on and (smtp_ok or bool(settings.get("briefingEmailResolved")))),
            }
        )

    @ai_bp.get("/ai/operator/audit")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ai_operator_audit():
        company_id = _resolve_company_id_from_request()
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        db = get_db()
        if not _operator_plan_allowed(db, company_id):
            return jsonify({"error": "plan_required", "capability": "ai_assistant"}), 403
        limit = 30
        try:
            limit = max(5, min(80, int(request.args.get("limit") or 30)))
        except Exception:
            limit = 30
        rows = []
        try:
            rows = db.execute(
                """
                SELECT id, event_type, message, actor_name, actor_user_id, actor_role,
                       target_id, created_at, details_json, reason
                FROM audit_logs
                WHERE company_id = ?
                  AND event_type LIKE 'ai.action.%'
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (company_id, limit),
            ).fetchall()
        except Exception:
            rows = []
        events = []
        for row in rows or []:
            details = {}
            try:
                import json

                details = json.loads(row["details_json"] or "{}")
            except Exception:
                details = {}
            events.append(
                {
                    "id": row["id"],
                    "eventType": row["event_type"],
                    "message": row["message"],
                    "actor": row["actor_name"] or row["actor_user_id"] or "",
                    "role": row["actor_role"] or "",
                    "targetId": row["target_id"] or "",
                    "createdAt": row["created_at"],
                    "details": details,
                    "reason": row["reason"] or "",
                }
            )
        return jsonify({"company_id": company_id, "events": events})

    @ai_bp.get("/ai/operator/memory")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ai_operator_memory_get():
        from .operator_memory import get_memory

        company_id = _resolve_company_id_from_request()
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        db = get_db()
        if not _operator_plan_allowed(db, company_id):
            return jsonify({"error": "plan_required", "capability": "ai_assistant"}), 403
        return jsonify({"company_id": company_id, "memory": get_memory(db, company_id)})

    @ai_bp.post("/ai/operator/memory")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ai_operator_memory_save():
        from .operator_memory import save_memory

        data = request.get_json(silent=True) or {}
        company_id = _resolve_company_id_from_request(data)
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        db = get_db()
        if not _operator_plan_allowed(db, company_id):
            return jsonify({"error": "plan_required", "capability": "ai_assistant"}), 403
        mem = save_memory(
            db,
            company_id,
            data,
            actor=str(g.current_user.get("id") or g.current_user.get("username") or ""),
        )
        return jsonify({"ok": True, "company_id": company_id, "memory": mem})

    @ai_bp.get("/ai/operator/settings")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ai_operator_settings_get():
        from .operator_settings import enrich_settings_for_api, get_settings

        company_id = _resolve_company_id_from_request()
        if not company_id:
            return jsonify({"error": "company_required", "enabled": False, "planAllowed": False}), 400
        db = get_db()
        settings = enrich_settings_for_api(db, company_id, get_settings(db, company_id))
        plan_allowed = _operator_plan_allowed(db, company_id)
        company_on = bool(settings.get("enabled", True))
        effective = company_on and plan_allowed
        return jsonify(
            {
                "company_id": company_id,
                "settings": settings,
                **settings,
                "enabled": effective,
                "companyEnabled": company_on,
                "planAllowed": plan_allowed,
                "capability": "ai_assistant",
            }
        )

    @ai_bp.patch("/ai/operator/settings")
    @ai_bp.post("/ai/operator/settings")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ai_operator_settings_save():
        from .operator_settings import save_settings

        data = request.get_json(silent=True) or {}
        company_id = _resolve_company_id_from_request(data)
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        db = get_db()
        actor = str(g.current_user.get("id") or g.current_user.get("username") or "")
        settings = save_settings(db, company_id, data, actor=actor)
        plan_allowed = _operator_plan_allowed(db, company_id)
        company_on = bool(settings.get("enabled", True))
        effective = company_on and plan_allowed
        return jsonify(
            {
                "ok": True,
                "company_id": company_id,
                "settings": settings,
                **settings,
                "enabled": effective,
                "companyEnabled": company_on,
                "planAllowed": plan_allowed,
                "capability": "ai_assistant",
            }
        )

    def _user_id() -> str:
        return str(g.current_user.get("id") or g.current_user.get("username") or "unknown")

    @ai_bp.post("/ai/query")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_query():
        import os

        from .agent_runner import run_agent_query
        from .assistant import natural_language_query
        from .context_builder import build_compact_context
        from .sessions import append_message, get_session, list_messages, record_audit, touch_session_title
        from backend.app.platform.physical_operations.copilot import build_copilot_context

        data = request.get_json(silent=True) or {}
        question = str(data.get("question", "")).strip()
        if not question:
            return jsonify({"error": "question_required", "hint": "Bitte eine Frage eingeben."}), 400

        company_id = _resolve_company_id_from_request(data)
        if not company_id:
            return jsonify({
                "error": "company_required",
                "hint": "Superadmin: Firma in der Vorschau wählen oder company_id mitsenden.",
            }), 400

        role = str(g.current_user.get("role") or "company-admin")
        lang = str(data.get("lang") or request.args.get("lang") or "de")[:2]
        agent_id = str(data.get("agent_id") or data.get("agent") or "operations").strip()
        session_id = str(data.get("session_id") or "").strip()
        use_agent = _parse_bool_flag(data.get("use_agent"), default=True)
        tools_env = os.getenv("BAUPASS_AI_TOOLS", "1").strip().lower() not in {"0", "false", "no"}
        use_tools = _parse_bool_flag(data.get("use_tools"), default=False) and tools_env
        spoken = _parse_spoken_flag(data)

        db = get_db()
        history = []
        if session_id:
            sess = get_session(db, session_id, company_id=company_id, user_id=_user_id())
            if not sess:
                return jsonify({"error": "session_not_found"}), 404
            agent_id = sess["agent_id"] or agent_id
            history = [{"role": m["role"], "content": m["content"]} for m in list_messages(db, session_id)]
            if len(history) <= 1:
                touch_session_title(db, session_id, question, lang=lang)

        try:
            from .intents import try_intent_response

            intent_hit = try_intent_response(
                db, company_id, question, role=role, lang=lang
            )
            if intent_hit:
                result = intent_hit
            elif use_agent:
                result = run_agent_query(
                    db,
                    company_id,
                    question,
                    agent_id=agent_id,
                    lang=lang,
                    role=role,
                    history=history,
                    spoken=spoken,
                    use_tools=use_tools,
                )
            else:
                ctx = data.get("context") or build_compact_context(db, company_id, role)
                result = natural_language_query(company_id, question, ctx, lang=lang)
                if not result.get("answer") and not result.get("error"):
                    from backend.app.platform.physical_operations.copilot import _deterministic_qa

                    full_ctx = build_copilot_context(db, company_id, role)
                    fallback = _deterministic_qa(full_ctx, question)
                    if fallback.get("answer"):
                        result["answer"] = fallback["answer"]
                        result["source"] = fallback.get("source", "deterministic")

            result["companyId"] = company_id
            from .brand_guard import sanitize_ai_answer

            if result.get("answer"):
                result["answer"] = sanitize_ai_answer(result["answer"])
            tool_count = len(result.get("toolsUsed") or [])
            record_audit(
                db,
                company_id=company_id,
                user_id=_user_id(),
                question=question,
                agent_id=agent_id,
                mode="agent" if use_agent else "chat",
                session_id=session_id or None,
                tool_calls=tool_count,
            )

            if session_id and result.get("answer"):
                append_message(db, session_id, role="user", content=question)
                append_message(
                    db,
                    session_id,
                    role="assistant",
                    content=result["answer"],
                    meta={"toolsUsed": result.get("toolsUsed"), "sources": result.get("sources")},
                )
                if len(history) <= 1:
                    touch_session_title(db, session_id, question, lang=lang)

            return jsonify(result)
        except Exception as exc:
            logger.exception("ai_query failed company_id=%s", company_id)
            return jsonify({
                "error": "ai_query_failed",
                "hint": str(exc),
                "companyId": company_id,
            }), 500

    @ai_bp.get("/ai/briefing")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_briefing():
        from .assistant import generate_operations_briefing
        from .context_builder import build_compact_context

        company_id = _resolve_company_id_from_request()
        if not company_id:
            company_id = str(request.args.get("company_id") or "").strip()
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        lang = str(request.args.get("lang") or "de")[:2]
        role = str(g.current_user.get("role") or "company-admin")
        ctx = build_compact_context(get_db(), company_id, role)
        result = generate_operations_briefing(company_id, ctx, lang=lang)
        result["companyId"] = company_id
        return jsonify(result)

    @ai_bp.get("/ai/prompts")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_prompts():
        from .context_builder import build_compact_context, suggested_prompts

        company_id = str(request.args.get("company_id") or "").strip()
        if not company_id and g.current_user.get("role") == "superadmin":
            company_id = str(g.current_user.get("preview_company_id") or "").strip()
        if g.current_user.get("role") != "superadmin":
            company_id = str(g.current_user.get("company_id") or "").strip()
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        lang = str(request.args.get("lang") or "de")[:2]
        role = str(g.current_user.get("role") or "company-admin")
        ctx = build_compact_context(get_db(), company_id, role)
        return jsonify({
            "companyId": company_id,
            "prompts": suggested_prompts(ctx, lang),
            "snapshot": {
                "workersOnSite": ctx.get("workersOnSite"),
                "openSecurityFindings": (ctx.get("security") or {}).get("openFindings"),
            },
        })

    @ai_bp.get("/ai/intelligence")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("operational_insights")
    def ai_intelligence():
        from .intelligence import operational_insights

        cid = str(g.current_user.get("company_id") or "")
        if g.current_user.get("role") == "superadmin":
            cid = str(request.args.get("company_id", cid) or cid)
        if not cid:
            return jsonify({"error": "company_required"}), 400
        return jsonify(operational_insights(get_db(), cid))

    @ai_bp.get("/ai/predictive-attendance")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("predictive_att")
    def ai_predictive_attendance():
        from .intelligence import predictive_attendance

        cid = _resolve_company_id_from_request()
        if not cid:
            return jsonify({"error": "company_required"}), 400
        return jsonify(predictive_attendance(get_db(), cid))

    @ai_bp.get("/ai/fraud-detection")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("fraud")
    def ai_fraud():
        from .intelligence import fraud_signals

        cid = _resolve_company_id_from_request()
        if not cid:
            return jsonify({"error": "company_required"}), 400
        return jsonify(fraud_signals(get_db(), cid))

    @ai_bp.get("/ai/agents")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_agents():
        from .agents import list_agents

        lang = str(request.args.get("lang") or "de")[:2]
        return jsonify({"agents": list_agents(lang)})

    @ai_bp.get("/ai/insights")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_insights():
        from .insights import build_insights_dashboard
        from .sessions import audit_stats

        company_id = _resolve_company_id_from_request()
        if not company_id:
            company_id = str(request.args.get("company_id") or "").strip()
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        role = str(g.current_user.get("role") or "company-admin")
        db = get_db()
        dash = build_insights_dashboard(db, company_id, role)
        dash["usage"] = audit_stats(db, company_id)
        from .experience import enrich_insights_dashboard
        from backend.app.platform.sector.catalog import sector_terms_for_company

        lang = str(request.args.get("lang") or "de")[:2]
        terms = sector_terms_for_company(db, company_id, lang=lang)
        enrich_insights_dashboard(dash, company_id=company_id, lang=lang, terms=terms)
        return jsonify(dash)

    @ai_bp.post("/ai/analyze")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_analyze():
        from .agent_runner import run_deep_analysis
        from .sessions import record_audit

        data = request.get_json(silent=True) or {}
        company_id = _resolve_company_id_from_request(data)
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        topic = str(data.get("topic") or "operations").strip()
        lang = str(data.get("lang") or "de")[:2]
        role = str(g.current_user.get("role") or "company-admin")
        result = run_deep_analysis(get_db(), company_id, topic, lang=lang, role=role)
        record_audit(
            get_db(),
            company_id=company_id,
            user_id=_user_id(),
            question=f"[analyze:{topic}]",
            agent_id=result.get("agentId", topic),
            mode="analyze",
            tool_calls=len(result.get("toolsUsed") or []),
        )
        result["companyId"] = company_id
        result["topic"] = topic
        return jsonify(result)

    @ai_bp.get("/ai/sessions")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_sessions_list():
        from .sessions import list_sessions

        company_id = _resolve_company_id_from_request()
        if not company_id:
            company_id = str(request.args.get("company_id") or "").strip()
        if not company_id:
            return jsonify(
                {
                    "sessions": [],
                    "companyId": "",
                    "hint": "company_required",
                }
            )
        sessions = list_sessions(get_db(), company_id=company_id, user_id=_user_id())
        return jsonify({"sessions": sessions, "companyId": company_id})

    @ai_bp.post("/ai/sessions")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_sessions_create():
        from .sessions import create_session

        data = request.get_json(silent=True) or {}
        company_id = _resolve_company_id_from_request(data)
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        agent_id = str(data.get("agent_id") or "operations").strip()
        lang = str(data.get("lang") or "de")[:2]
        title = str(data.get("title") or "").strip()
        sess = create_session(
            get_db(),
            company_id=company_id,
            user_id=_user_id(),
            agent_id=agent_id,
            title=title,
            lang=lang,
        )
        return jsonify(sess), 201

    @ai_bp.get("/ai/sessions/<session_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_session_detail(session_id: str):
        from .sessions import get_session, list_messages

        company_id = _resolve_company_id_from_request()
        if not company_id:
            company_id = str(request.args.get("company_id") or "").strip()
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        sess = get_session(get_db(), session_id, company_id=company_id, user_id=_user_id())
        if not sess:
            return jsonify({"error": "session_not_found"}), 404
        messages = list_messages(get_db(), session_id)
        return jsonify({
            "session": {
                "id": sess["id"],
                "agentId": sess["agent_id"],
                "title": sess["title"],
                "lang": sess["lang"],
            },
            "messages": messages,
        })

    @ai_bp.delete("/ai/sessions/<session_id>")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_session_delete(session_id: str):
        from .sessions import delete_session

        company_id = _resolve_company_id_from_request()
        if not company_id:
            company_id = str(request.args.get("company_id") or "").strip()
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        if not delete_session(
            get_db(),
            session_id,
            company_id=company_id,
            user_id=_user_id(),
        ):
            return jsonify({"error": "session_not_found"}), 404
        return jsonify({"deleted": session_id})

    @ai_bp.delete("/ai/sessions")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_sessions_delete_all():
        from .sessions import delete_all_sessions

        company_id = _resolve_company_id_from_request()
        if not company_id:
            company_id = str(request.args.get("company_id") or "").strip()
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        count = delete_all_sessions(
            get_db(),
            company_id=company_id,
            user_id=_user_id(),
        )
        return jsonify({"deleted": True, "count": count})

    @ai_bp.post("/ai/query/stream")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_query_stream():
        import os

        from .agent_runner import run_agent_query_stream
        from .sessions import append_message, get_session, list_messages, record_audit, touch_session_title
        from .streaming import sse_event

        data = request.get_json(silent=True) or {}
        question = str(data.get("question", "")).strip()
        if not question:
            return jsonify({"error": "question_required"}), 400
        company_id = _resolve_company_id_from_request(data)
        if not company_id:
            return jsonify({"error": "company_required"}), 400

        agent_id = str(data.get("agent_id") or "operations").strip()
        session_id = str(data.get("session_id") or "").strip()
        lang = str(data.get("lang") or "de")[:2]
        role = str(g.current_user.get("role") or "company-admin")
        spoken = _parse_spoken_flag(data)
        tools_env = os.getenv("BAUPASS_AI_TOOLS", "1").strip().lower() not in {"0", "false", "no"}
        use_tools = _parse_bool_flag(data.get("use_tools"), default=False) and tools_env
        db = get_db()
        analysis_topic = str(data.get("analysis_topic") or "").strip().lower()
        extra_context = ""
        if analysis_topic:
            from .context_builder import build_compact_context, format_analysis_data_block

            ctx = build_compact_context(db, company_id, role)
            extra_context = format_analysis_data_block(ctx, analysis_topic, lang=lang)
        history = []
        if session_id:
            sess = get_session(db, session_id, company_id=company_id, user_id=_user_id())
            if not sess:
                return jsonify({"error": "session_not_found"}), 404
            agent_id = sess["agent_id"] or agent_id
            history = [{"role": m["role"], "content": m["content"]} for m in list_messages(db, session_id)]
            if len(history) <= 1:
                touch_session_title(db, session_id, question, lang=lang)

        def generate():
            from .intents import try_intent_response

            final: dict = {}
            intent_hit = try_intent_response(
                db, company_id, question, role=role, lang=lang
            )
            if intent_hit:
                answer = str(intent_hit.get("answer") or "").strip()
                # Stage executable suggestions so FAB shows real confirm cards.
                staged = []
                try:
                    from .actions import ALLOWED_EXECUTE, propose_action

                    for item in (intent_hit.get("suggestedActions") or intent_hit.get("actions") or []):
                        if not isinstance(item, dict):
                            continue
                        if str(item.get("type") or "") != "execute":
                            continue
                        action = str(item.get("action") or "").strip()
                        if action not in ALLOWED_EXECUTE:
                            continue
                        proposal = propose_action(
                            db,
                            company_id=company_id,
                            user_id=_user_id(),
                            action=action,
                            params=item.get("params") if isinstance(item.get("params"), dict) else {},
                            rationale=str(
                                item.get("labelDe")
                                or item.get("labelEn")
                                or item.get("rationale")
                                or action
                            ),
                            risk=str(item.get("risk") or "medium"),
                        )
                        if proposal.get("ok") and proposal.get("proposal"):
                            staged.append(proposal["proposal"])
                except Exception:
                    staged = []
                yield sse_event({"type": "start", "agentId": agent_id, "mode": "intent"})
                yield sse_event({"type": "answer_start"})
                step = max(24, len(answer) // 6) if answer else 0
                for i in range(0, len(answer), step or 1):
                    yield sse_event({"type": "chunk", "text": answer[i : i + step]})
                final = {
                    "type": "done",
                    "ok": True,
                    "answer": answer,
                    "agentId": agent_id,
                    "mode": "intent",
                    "intent": intent_hit.get("intent"),
                    "toolsUsed": intent_hit.get("toolsUsed") or [],
                    "suggestedActions": intent_hit.get("suggestedActions") or intent_hit.get("actions") or [],
                    "actions": intent_hit.get("actions") or intent_hit.get("suggestedActions") or [],
                    "sources": intent_hit.get("sources") or [],
                    "stagedProposals": staged,
                }
                yield sse_event(final)
            else:
                for ev in run_agent_query_stream(
                    db,
                    company_id,
                    question,
                    agent_id=agent_id,
                    lang=lang,
                    role=role,
                    history=history,
                    spoken=spoken,
                    use_tools=use_tools,
                    extra_context=extra_context,
                ):
                    if ev.get("type") == "done":
                        final = ev
                    yield sse_event(ev)

            record_audit(
                db,
                company_id=company_id,
                user_id=_user_id(),
                question=question,
                agent_id=agent_id,
                mode="stream",
                session_id=session_id or None,
                tool_calls=len(final.get("toolsUsed") or []),
            )
            if session_id and final.get("answer"):
                append_message(db, session_id, role="user", content=question)
                append_message(
                    db,
                    session_id,
                    role="assistant",
                    content=final["answer"],
                    meta={"toolsUsed": final.get("toolsUsed"), "stream": True},
                )
                if len(history) <= 1:
                    touch_session_title(db, session_id, question, lang=lang)

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @ai_bp.post("/ai/actions/execute")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_execute_action():
        from .actions import execute_action

        data = request.get_json(silent=True) or {}
        company_id = _resolve_company_id_from_request(data)
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        action = str(data.get("action") or "").strip()
        params = data.get("params") or {}
        briefing_text = str(data.get("briefingText") or data.get("briefing_text") or "").strip()
        result = execute_action(
            get_db(),
            company_id=company_id,
            user_id=_user_id(),
            action=action,
            params=params,
            briefing_text=briefing_text or None,
        )
        status = 200 if result.get("ok") else 400
        return jsonify(result), status

    @ai_bp.post("/ai/decision")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_decision():
        from .agent_runner import run_decision_query
        from .sessions import append_message, create_session, get_session, list_messages, touch_session_title

        data = request.get_json(silent=True) or {}
        company_id = _resolve_company_id_from_request(data)
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        question = str(data.get("question") or data.get("q") or "").strip()
        if not question:
            return jsonify({"error": "question_required"}), 400
        lang = str(data.get("lang") or "de")[:2]
        role = str(g.current_user.get("role") or "company-admin")
        db = get_db()
        session_id = str(data.get("session_id") or data.get("sessionId") or "").strip()
        history = []
        if session_id:
            sess = get_session(db, session_id, company_id=company_id, user_id=_user_id())
            if sess:
                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in list_messages(db, session_id, limit=12)
                ]
                if len(history) <= 1:
                    touch_session_title(db, session_id, question, lang=lang)
        else:
            created = create_session(
                db,
                company_id=company_id,
                user_id=_user_id(),
                agent_id="decision",
                title=question,
                lang=lang,
            )
            session_id = str(created.get("id") or "")
        result = run_decision_query(
            db,
            company_id,
            question,
            lang=lang,
            role=role,
            history=history,
            user_id=_user_id(),
            auto_stage=bool(data.get("autoStage", True)),
        )
        if session_id and result.get("answer"):
            append_message(db, session_id, role="user", content=question)
            append_message(
                db,
                session_id,
                role="assistant",
                content=result.get("answer"),
                meta={"decision": result.get("decision"), "agentId": "decision"},
            )
            touch_session_title(db, session_id, question, lang=lang)
        result["sessionId"] = session_id
        result["companyId"] = company_id
        return jsonify(result)

    @ai_bp.post("/ai/actions/propose")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_propose_action():
        from .actions import propose_action

        data = request.get_json(silent=True) or {}
        company_id = _resolve_company_id_from_request(data)
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        result = propose_action(
            get_db(),
            company_id=company_id,
            user_id=_user_id(),
            action=str(data.get("action") or ""),
            params=data.get("params") or {},
            rationale=str(data.get("rationale") or ""),
            risk=str(data.get("risk") or "low"),
        )
        return jsonify(result), (200 if result.get("ok") else 400)

    @ai_bp.get("/ai/actions/proposals")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_list_proposals():
        from .actions import list_proposals

        company_id = _resolve_company_id_from_request(request.args)
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        status = str(request.args.get("status") or "pending")
        proposals = list_proposals(get_db(), company_id=company_id, status=status)
        return jsonify({"proposals": proposals})

    @ai_bp.post("/ai/actions/approve")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_approve_action():
        from .actions import approve_action

        data = request.get_json(silent=True) or {}
        company_id = _resolve_company_id_from_request(data)
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        proposal_id = str(data.get("proposal_id") or data.get("proposalId") or "").strip()
        if not proposal_id:
            return jsonify({"error": "proposal_id_required"}), 400
        result = approve_action(
            get_db(),
            company_id=company_id,
            user_id=_user_id(),
            proposal_id=proposal_id,
            briefing_text=str(data.get("briefingText") or "") or None,
        )
        return jsonify(result), (200 if result.get("ok") else 400)

    @ai_bp.post("/ai/actions/reject")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_reject_action():
        from .actions import reject_action

        data = request.get_json(silent=True) or {}
        company_id = _resolve_company_id_from_request(data)
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        proposal_id = str(data.get("proposal_id") or data.get("proposalId") or "").strip()
        if not proposal_id:
            return jsonify({"error": "proposal_id_required"}), 400
        result = reject_action(
            get_db(),
            company_id=company_id,
            user_id=_user_id(),
            proposal_id=proposal_id,
            note=str(data.get("note") or ""),
        )
        return jsonify(result), (200 if result.get("ok") else 400)

    @ai_bp.post("/ai/briefing/email")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_briefing_email():
        from .actions import execute_action
        from .assistant import generate_operations_briefing
        from .context_builder import build_compact_context

        data = request.get_json(silent=True) or {}
        company_id = _resolve_company_id_from_request(data)
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        to = str(data.get("to") or g.current_user.get("email") or "").strip()
        if not to:
            return jsonify({"error": "email_required", "hint": "Empfänger-E-Mail angeben."}), 400
        lang = str(data.get("lang") or "de")[:2]
        role = str(g.current_user.get("role") or "company-admin")
        ctx = build_compact_context(get_db(), company_id, role)
        briefing = generate_operations_briefing(company_id, ctx, lang=lang)
        body = briefing.get("answer") or ""
        result = execute_action(
            get_db(),
            company_id=company_id,
            user_id=_user_id(),
            action="send_briefing_email",
            params={"to": to, "subject": data.get("subject") or "Suppix AI Tagesbriefing"},
            briefing_text=body,
        )
        result["briefingPreview"] = body[:500]
        return jsonify(result), (200 if result.get("ok") else 400)

    @ai_bp.post("/ai/briefing/webhook")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_briefing_webhook():
        from .assistant import generate_operations_briefing
        from .context_builder import build_compact_context
        from .notifications import dispatch_briefing_notifications

        data = request.get_json(silent=True) or {}
        company_id = _resolve_company_id_from_request(data)
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        lang = str(data.get("lang") or "de")[:2]
        role = str(g.current_user.get("role") or "company-admin")
        ctx = build_compact_context(get_db(), company_id, role)
        briefing = generate_operations_briefing(company_id, ctx, lang=lang)
        body = briefing.get("answer") or ""
        dispatch = dispatch_briefing_notifications(
            body, company_id=company_id, title=data.get("title") or "Suppix AI Tagesbriefing"
        )
        dispatch["briefingPreview"] = body[:400]
        return jsonify(dispatch), (200 if dispatch.get("sent") else 400)

    @ai_bp.post("/ai/transcribe")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_transcribe():
        import base64

        from .whisper import transcribe_audio_bytes

        data = request.get_json(silent=True) or {}
        audio_b64 = str(data.get("audio") or data.get("audio_b64") or "").strip()
        if not audio_b64:
            return jsonify({"error": "audio_required", "hint": "Keine Audiodaten."}), 400
        try:
            audio_bytes = base64.b64decode(audio_b64, validate=False)
        except Exception:
            return jsonify({"error": "invalid_audio_base64"}), 400
        if not audio_bytes:
            return jsonify({"error": "audio_required", "hint": "Keine Audiodaten."}), 400

        mime = str(data.get("mime") or "audio/webm")
        ext = "webm" if "webm" in mime else "m4a" if "m4a" in mime else "wav"
        multilingual = data.get("multilingual", True)
        if isinstance(multilingual, str):
            multilingual = multilingual.lower() not in {"0", "false", "no"}
        raw_lang = str(data.get("lang") or request.args.get("lang") or "").strip().lower()
        # Never slice "auto" → "au". Multilingual / auto always auto-detects.
        if multilingual or raw_lang in {"", "auto", "mul", "multi", "*", "xx", "detect"}:
            lang_hint = "auto"
        else:
            from .langs import try_normalize_ui_lang

            lang_hint = try_normalize_ui_lang(raw_lang) or "auto"
        tr = transcribe_audio_bytes(
            audio_bytes,
            filename=f"voice.{ext}",
            mime=mime,
            language=lang_hint,
        )
        if not tr.get("text"):
            err = tr.get("error", "transcription_failed")
            logger.warning(
                "ai_transcribe failed error=%s bytes=%s lang=%s provider=%s",
                err,
                len(audio_bytes),
                lang_hint,
                tr.get("provider"),
            )
            hints = {
                "openai_not_configured": "Whisper nicht konfiguriert (OPENAI_API_KEY / Azure). Browser-Spracherkennung als Fallback.",
                "audio_too_short": "Aufnahme zu kurz — bitte länger sprechen oder FAB erneut tippen.",
                "no_speech_detected": "Keine Sprache erkannt — bitte klarer sprechen.",
            }
            return jsonify({
                "error": err,
                "hint": tr.get("hint") or hints.get(err) or "Transkription fehlgeschlagen.",
                "provider": tr.get("provider"),
            }), 400
        payload = {"text": tr["text"], "model": tr.get("model")}
        if tr.get("language"):
            payload["language"] = tr["language"]
            payload["lang"] = tr["language"]
        return jsonify(payload)

    @ai_bp.post("/ai/speak")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_speak():
        from flask import Response

        from .tts import synthesize_speech_bytes, synthesize_speech_stream

        data = request.get_json(silent=True) or {}
        text = str(data.get("text") or "").strip()
        if not text:
            return jsonify({"error": "text_required"}), 400
        lang = str(data.get("lang") or "de")[:2]
        fast = _parse_bool_flag(data.get("fast"), default=True)
        stream = _parse_bool_flag(data.get("stream"), default=False)

        if stream:
            from flask import stream_with_context

            gen = synthesize_speech_stream(text, lang=lang, fast=fast)
            first = next(gen, None)
            if first is None:
                result = synthesize_speech_bytes(text, lang=lang, fast=fast)
                audio = result.get("audio")
                if not audio:
                    return jsonify({
                        "error": result.get("error", "tts_failed"),
                        "hint": result.get("hint"),
                    }), 400
                return Response(audio, mimetype=result.get("mime") or "audio/mpeg")

            def generate():
                yield first
                yield from gen

            return Response(
                stream_with_context(generate()),
                mimetype="audio/wav",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        result = synthesize_speech_bytes(text, lang=lang, fast=fast)
        audio = result.get("audio")
        if not audio:
            return jsonify({
                "error": result.get("error", "tts_failed"),
                "hint": result.get("hint"),
            }), 400
        return Response(audio, mimetype=result.get("mime") or "audio/mpeg")

    @ai_bp.get("/ai/rag/search")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_rag_search():
        from .rag import search_knowledge

        company_id = _resolve_company_id_from_request()
        if not company_id:
            company_id = str(request.args.get("company_id") or "").strip()
        if not company_id:
            return jsonify({"error": "company_required"}), 400
        q = str(request.args.get("q") or "").strip()
        chunks = search_knowledge(get_db(), company_id, q)
        return jsonify({"query": q, "chunks": chunks, "count": len(chunks)})

    flask_app.register_blueprint(ai_bp, url_prefix="/api")

    from .worker_routes import register_worker_ai_blueprint

    register_worker_ai_blueprint(flask_app)
