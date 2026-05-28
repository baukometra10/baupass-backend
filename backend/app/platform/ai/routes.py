"""
AI routes — assistant + workforce intelligence.
"""
from __future__ import annotations

import logging

from flask import Blueprint, Flask, g, jsonify, request

logger = logging.getLogger("baupass.ai.routes")

ai_bp = Blueprint("platform_ai", __name__)


def _resolve_query_company_id(data: dict) -> str:
    """Company IDs are strings (cmp-…), never integers."""
    role = str(g.current_user.get("role") or "")
    if role == "superadmin":
        return (
            str(data.get("company_id") or "").strip()
            or str(getattr(g, "preview_company_id", "") or "").strip()
            or str(g.current_user.get("preview_company_id") or "").strip()
        )
    return str(g.current_user.get("company_id") or "").strip()


def register_ai_blueprint(flask_app: Flask) -> None:
    from backend.app.platform.plan_guard import require_plan_capability
    from backend.server import require_auth, require_roles, get_db

    @ai_bp.get("/ai/status")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ai_status():
        from .assistant import ai_config_status

        return jsonify(ai_config_status())

    @ai_bp.post("/ai/query")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("ai_assistant")
    def ai_query():
        from .assistant import natural_language_query
        from backend.app.platform.physical_operations.copilot import build_copilot_context

        data = request.get_json(silent=True) or {}
        question = str(data.get("question", "")).strip()
        if not question:
            return jsonify({"error": "question_required", "hint": "Bitte eine Frage eingeben."}), 400

        company_id = _resolve_query_company_id(data)
        if not company_id:
            return jsonify({
                "error": "company_required",
                "hint": "Superadmin: Firma in der Vorschau wählen oder company_id mitsenden.",
            }), 400

        role = str(g.current_user.get("role") or "company-admin")
        try:
            if data.get("context"):
                ctx = data.get("context")
            else:
                ctx = build_copilot_context(get_db(), company_id, role)
            result = natural_language_query(company_id, question, ctx)
            result["companyId"] = company_id
            if not result.get("answer") and not result.get("error"):
                from backend.app.platform.physical_operations.copilot import _deterministic_qa

                fallback = _deterministic_qa(ctx, question)
                if fallback.get("answer"):
                    result["answer"] = fallback["answer"]
                    result["source"] = fallback.get("source", "deterministic")
            return jsonify(result)
        except Exception as exc:
            logger.exception("ai_query failed company_id=%s", company_id)
            return jsonify({
                "error": "ai_query_failed",
                "hint": str(exc),
                "companyId": company_id,
            }), 500

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

        cid = str(request.args.get("company_id") or g.current_user.get("company_id") or "")
        return jsonify(predictive_attendance(get_db(), cid))

    @ai_bp.get("/ai/fraud-detection")
    @require_auth
    @require_roles("superadmin", "company-admin")
    @require_plan_capability("fraud")
    def ai_fraud():
        from .intelligence import fraud_signals

        cid = str(request.args.get("company_id") or g.current_user.get("company_id") or "")
        return jsonify(fraud_signals(get_db(), cid))

    flask_app.register_blueprint(ai_bp, url_prefix="/api")
