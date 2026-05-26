"""
Workflow automation rule evaluator.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def list_rules(db, company_id: int) -> list[dict]:
    rows = db.execute(
        """
        SELECT id, company_id, name, trigger_event, conditions_json, actions_json, enabled, created_at
        FROM automation_rules
        WHERE company_id = ?
        ORDER BY created_at DESC
        """,
        (company_id,),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["conditions"] = json.loads(item.pop("conditions_json") or "[]")
        item["actions"] = json.loads(item.pop("actions_json") or "[]")
        out.append(item)
    return out


def create_rule(db, company_id: int, payload: dict[str, Any]) -> dict:
    rule_id = f"rule-{uuid.uuid4().hex[:12]}"
    db.execute(
        """
        INSERT INTO automation_rules
            (id, company_id, name, trigger_event, conditions_json, actions_json, enabled, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rule_id,
            company_id,
            str(payload.get("name", "")).strip(),
            str(payload.get("trigger_event", "*")).strip(),
            json.dumps(payload.get("conditions") or []),
            json.dumps(payload.get("actions") or []),
            1 if payload.get("enabled", True) else 0,
            _now_iso(),
        ),
    )
    db.commit()
    return {"id": rule_id}


def evaluate_event(db, company_id: int, event_type: str, context: dict[str, Any]) -> list[dict]:
    """Run matching automation rules; returns executed action summaries."""
    rows = db.execute(
        """
        SELECT id, name, trigger_event, conditions_json, actions_json
        FROM automation_rules
        WHERE company_id = ? AND enabled = 1
        """,
        (company_id,),
    ).fetchall()
    executed = []
    for row in rows:
        trigger = str(row["trigger_event"] or "*")
        if trigger not in ("*", event_type) and not event_type.startswith(trigger.rstrip("*")):
            continue
        conditions = json.loads(row["conditions_json"] or "[]")
        if not _conditions_match(conditions, context):
            continue
        actions = json.loads(row["actions_json"] or "[]")
        for action in actions:
            executed.append(_execute_action(db, company_id, row["id"], action, context))
    return executed


def _conditions_match(conditions: list, context: dict) -> bool:
    if not conditions:
        return True
    for cond in conditions:
        field = cond.get("field")
        op = cond.get("op", "eq")
        expected = cond.get("value")
        actual = context.get(field)
        if op == "eq" and actual != expected:
            return False
        if op == "gt" and not (actual is not None and actual > expected):
            return False
        if op == "lt" and not (actual is not None and actual < expected):
            return False
    return True


def _execute_action(db, company_id: int, rule_id: str, action: dict, context: dict) -> dict:
    action_type = str(action.get("type", "")).strip()
    result = {"type": action_type, "status": "skipped"}
    if action_type == "emit_event":
        from backend.app.platform.events.bus import publish_event

        publish_event(
            str(action.get("event_type", "automation.fired")),
            company_id,
            {"rule_id": rule_id, "context": context},
        )
        result["status"] = "ok"
    elif action_type == "webhook_retry":
        from backend.app.platform.api_platform.webhooks import process_webhook_delivery_batch

        process_webhook_delivery_batch(company_id=company_id)
        result["status"] = "ok"
    elif action_type == "create_system_alert":
        alert_id = f"alert-{uuid.uuid4().hex[:10]}"
        db.execute(
            """
            INSERT INTO system_alerts (id, code, severity, message, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                alert_id,
                str(action.get("code", "automation")),
                str(action.get("severity", "info")),
                str(action.get("message", action.get("title", "Automation"))),
                json.dumps({"company_id": company_id, "rule_id": rule_id}),
                _now_iso(),
            ),
        )
        db.commit()
        result = {"status": "ok", "alert_id": alert_id}
    return result
