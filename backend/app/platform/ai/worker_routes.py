"""Worker app AI — voice (Whisper) + site assistant for employees."""
from __future__ import annotations

import base64
import logging

from flask import Blueprint, g, jsonify, request

logger = logging.getLogger("baupass.ai.worker")

worker_ai_bp = Blueprint("worker_ai", __name__)


def register_worker_ai_blueprint(flask_app) -> None:
    from backend.server import require_worker_session, get_db, company_has_feature

    @worker_ai_bp.get("/ai/status")
    @require_worker_session
    def worker_ai_status():
        from .assistant import is_ai_configured

        worker = g.worker or {}
        company_id = str(worker.get("company_id") or "")
        plan_row = get_db().execute("SELECT plan FROM companies WHERE id = ?", (company_id,)).fetchone()
        plan = (plan_row["plan"] if plan_row else "starter") or "starter"
        enabled = company_has_feature(plan, "worker_app") and is_ai_configured()
        return jsonify({
            "configured": enabled,
            "plan": plan,
            "hints": [
                "Wie viele Kollegen sind auf der Baustelle?",
                "Wann war mein letzter Check-in?",
                "Welche Dokumente laufen bald ab?",
            ],
        })

    @worker_ai_bp.post("/ai/ask")
    @require_worker_session
    def worker_ai_ask():
        from .agent_runner import run_agent_query

        worker = g.worker or {}
        company_id = str(worker.get("company_id") or "")
        plan_row = get_db().execute("SELECT plan FROM companies WHERE id = ?", (company_id,)).fetchone()
        plan = (plan_row["plan"] if plan_row else "starter") or "starter"
        if not company_has_feature(plan, "worker_app"):
            return jsonify({"error": "feature_not_available", "requiredPlan": "starter"}), 403

        data = request.get_json(silent=True) or {}
        question = str(data.get("question") or data.get("text") or "").strip()
        if not question:
            return jsonify({"error": "question_required"}), 400

        lang = str(data.get("lang") or "de")[:2]
        ctx_worker = {
            "workerId": worker.get("id"),
            "name": f"{worker.get('first_name', '')} {worker.get('last_name', '')}".strip(),
            "site": worker.get("site"),
            "status": worker.get("status"),
        }
        result = run_agent_query(
            get_db(),
            company_id,
            question,
            agent_id="hr",
            lang=lang,
            role="worker",
        )
        result["worker"] = ctx_worker
        return jsonify(result)

    @worker_ai_bp.post("/ai/voice")
    @require_worker_session
    def worker_ai_voice():
        """Transcribe audio (base64) and run HR agent query."""
        from .agent_runner import run_agent_query
        from .whisper import transcribe_audio_bytes

        worker = g.worker or {}
        company_id = str(worker.get("company_id") or "")
        data = request.get_json(silent=True) or {}
        audio_b64 = str(data.get("audio") or data.get("audio_b64") or "").strip()
        if not audio_b64:
            return jsonify({"error": "audio_required"}), 400
        try:
            audio_bytes = base64.b64decode(audio_b64, validate=True)
        except Exception:
            return jsonify({"error": "invalid_audio_base64"}), 400

        mime = str(data.get("mime") or "audio/webm")
        ext = "webm" if "webm" in mime else "m4a" if "m4a" in mime else "wav"
        tr = transcribe_audio_bytes(audio_bytes, filename=f"voice.{ext}", mime=mime, language=data.get("lang"))
        if not tr.get("text"):
            return jsonify({"error": tr.get("error", "transcription_failed"), "hint": tr.get("hint")}), 400

        question = tr["text"]
        lang = str(data.get("lang") or "de")[:2]
        result = run_agent_query(get_db(), company_id, question, agent_id="hr", lang=lang, role="worker")
        result["transcript"] = question
        return jsonify(result)

    if "worker_ai" not in flask_app.blueprints:
        flask_app.register_blueprint(worker_ai_bp, url_prefix="/api/worker-app")
