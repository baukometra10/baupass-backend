"""
AI routes — assistant + workforce intelligence.
"""
from __future__ import annotations

from flask import Blueprint, Flask, g, jsonify, request

ai_bp = Blueprint("platform_ai", __name__)


def register_ai_blueprint(flask_app: Flask) -> None:
    from backend.server import require_auth, require_roles, get_db

    @ai_bp.get("/ai/status")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ai_status():
        from .assistant import is_ai_configured

        return jsonify({"configured": is_ai_configured()})

    @ai_bp.post("/ai/query")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ai_query():
        from .assistant import natural_language_query

        data = request.get_json(silent=True) or {}
        question = str(data.get("question", "")).strip()
        if not question:
            return jsonify({"error": "question_required"}), 400
        company_id = int(g.current_user.get("company_id") or 0)
        if g.current_user.get("role") == "superadmin" and data.get("company_id"):
            company_id = int(data["company_id"])
        return jsonify(natural_language_query(company_id, question, data.get("context")))

    @ai_bp.get("/ai/intelligence")
    @require_auth
    @require_roles("superadmin", "company-admin")
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
    def ai_predictive_attendance():
        from .intelligence import predictive_attendance

        cid = str(request.args.get("company_id") or g.current_user.get("company_id") or "")
        return jsonify(predictive_attendance(get_db(), cid))

    @ai_bp.get("/ai/fraud-detection")
    @require_auth
    @require_roles("superadmin", "company-admin")
    def ai_fraud():
        from .intelligence import fraud_signals

        cid = str(request.args.get("company_id") or g.current_user.get("company_id") or "")
        return jsonify(fraud_signals(get_db(), cid))

    flask_app.register_blueprint(ai_bp, url_prefix="/api")
