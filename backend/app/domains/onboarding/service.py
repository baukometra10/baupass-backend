"""
Employee onboarding workflow service.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any


STEPS = ("invite", "profile", "documents", "approval", "badge")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class OnboardingService:
    def start(self, db, company_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        worker_id = (payload.get("worker_id") or "").strip()
        email = (payload.get("email") or "").strip().lower()
        if not worker_id and not email:
            return {"ok": False, "error": "worker_id_or_email_required"}
        wf_id = f"onb-{uuid.uuid4().hex[:12]}"
        state = {
            "current_step": "invite",
            "steps": {s: "pending" for s in STEPS},
            "worker_id": worker_id,
            "email": email,
        }
        db.execute(
            """
            INSERT INTO onboarding_workflows (id, company_id, worker_id, status, state_json, created_at, updated_at)
            VALUES (?, ?, ?, 'active', ?, ?, ?)
            """,
            (wf_id, company_id, worker_id or None, json.dumps(state), _now_iso(), _now_iso()),
        )
        db.commit()
        return {"ok": True, "id": wf_id, "state": state}

    def advance(self, db, company_id: int, workflow_id: str, step: str) -> dict[str, Any]:
        row = db.execute(
            "SELECT * FROM onboarding_workflows WHERE id = ? AND company_id = ?",
            (workflow_id, company_id),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "not_found"}
        state = json.loads(row["state_json"] or "{}")
        steps = state.setdefault("steps", {})
        if step not in STEPS:
            return {"ok": False, "error": "invalid_step"}
        steps[step] = "done"
        idx = STEPS.index(step)
        next_step = STEPS[idx + 1] if idx + 1 < len(STEPS) else "completed"
        state["current_step"] = next_step
        status = "completed" if next_step == "completed" else "active"
        db.execute(
            "UPDATE onboarding_workflows SET state_json = ?, status = ?, updated_at = ? WHERE id = ?",
            (json.dumps(state), status, _now_iso(), workflow_id),
        )
        db.commit()
        return {"ok": True, "id": workflow_id, "state": state, "status": status}

    def list_active(self, db, company_id: int, limit: int = 50) -> list[dict[str, Any]]:
        rows = db.execute(
            """
            SELECT id, worker_id, status, state_json, created_at, updated_at
            FROM onboarding_workflows
            WHERE company_id = ? AND status = 'active'
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["state"] = json.loads(item.pop("state_json") or "{}")
            out.append(item)
        return out
