"""
Workflow automation rule evaluator.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("baupass.automation")
MAX_ACTIONS_PER_RULE = 20


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


def evaluate_event(db, company_id: str, event_type: str, context: dict[str, Any]) -> list[dict]:
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
        for action in actions[:MAX_ACTIONS_PER_RULE]:
            try:
                executed.append(_execute_action(db, company_id, row["id"], action, context))
            except Exception as exc:
                logger.warning("automation action failed rule=%s event=%s err=%s", row["id"], event_type, exc)
                try:
                    from backend.app.tasks import enqueue

                    enqueue(
                        "dead_letter",
                        _record_dead_letter,
                        company_id=company_id,
                        rule_id=row["id"],
                        event_type=event_type,
                        action=action,
                        error=str(exc),
                    )
                except Exception:
                    pass
                executed.append({"type": str(action.get("type", "")), "status": "error", "error": str(exc)})
    return executed


def _conditions_match(conditions: list, context: dict) -> bool:
    if not conditions:
        return True
    for cond in conditions:
        field = cond.get("field")
        op = cond.get("op", "eq")
        expected = cond.get("value")
        actual = context.get(field)
        if field is None:
            return False
        if op == "eq" and actual != expected:
            return False
        if op == "neq" and actual == expected:
            return False
        if op == "gt" and not (actual is not None and actual > expected):
            return False
        if op == "lt" and not (actual is not None and actual < expected):
            return False
        if op == "contains" and not (isinstance(actual, (str, list, tuple, dict)) and expected in actual):
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
    elif action_type == "lock_worker":
        wid = str(action.get("worker_id") or context.get("worker_id") or "").strip()
        if wid:
            db.execute(
                "UPDATE workers SET status = 'gesperrt' WHERE id = ? AND company_id = ?",
                (wid, str(company_id)),
            )
            db.commit()
            result = {"status": "ok", "worker_id": wid, "new_status": "gesperrt"}
    elif action_type == "unlock_worker":
        wid = str(action.get("worker_id") or context.get("worker_id") or "").strip()
        if wid:
            db.execute(
                "UPDATE workers SET status = 'aktiv' WHERE id = ? AND company_id = ?",
                (wid, str(company_id)),
            )
            db.commit()
            result = {"status": "ok", "worker_id": wid, "new_status": "aktiv"}
    elif action_type == "run_security_scan":
        from backend.app.platform.physical_operations.security_engine import analyze_security

        report = analyze_security(db, company_id, persist=True)
        result = {"status": "ok", "newFindings": report.get("newFindings", 0)}
    elif action_type == "generate_ops_report":
        from backend.app.platform.physical_operations.copilot import build_copilot_context

        snapshot = build_copilot_context(db, company_id)
        publish_event = None
        try:
            from backend.app.platform.events.bus import publish_event as _pe

            _pe("automation.ops_report", company_id, {"snapshot": snapshot})
            publish_event = True
        except Exception:
            pass
        result = {"status": "ok", "reportGenerated": True, "published": bool(publish_event)}
    elif action_type == "email_ops_report_pdf":
        from backend.app.platform.reports.email_delivery import send_pdf_report_email
        from backend.app.platform.reports.guidance import build_operational_guidance
        from backend.app.platform.reports.pdf_reports import build_operations_report_pdf
        from backend.server import _operations_snapshot_for_user

        recipient = str(action.get("email") or context.get("admin_email") or "").strip()
        if not recipient:
            admin = db.execute(
                """
                SELECT email FROM users
                WHERE company_id = ? AND role = 'company-admin' AND COALESCE(email, '') != ''
                ORDER BY username LIMIT 1
                """,
                (str(company_id),),
            ).fetchone()
            recipient = str(admin["email"] if admin else "").strip()
        if not recipient:
            result = {"status": "skipped", "reason": "no_recipient_email"}
        else:
            snapshot = _operations_snapshot_for_user(
                db,
                {"role": "company-admin", "company_id": str(company_id), "email": recipient},
            )
            guidance = build_operational_guidance(snapshot)
            company = db.execute("SELECT name FROM companies WHERE id = ?", (str(company_id),)).fetchone()
            pdf_bytes = build_operations_report_pdf(
                title="BauPass Operations Report",
                company_name=company["name"] if company else "BauPass",
                snapshot=snapshot,
                guidance=guidance,
            )
            ok, err = send_pdf_report_email(
                to=recipient,
                subject=str(action.get("subject") or "BauPass Automationsbericht"),
                body_text=str(action.get("body") or "Automatischer Betriebsbericht (PDF im Anhang)."),
                pdf_bytes=pdf_bytes,
            )
            result = {"status": "ok" if ok else "error", "recipient": recipient, "error": err}
    return result


def _record_dead_letter(
    *,
    company_id: int,
    rule_id: str,
    event_type: str,
    action: dict[str, Any],
    error: str,
) -> dict[str, Any]:
    """Persist automation failures in system alerts for operator visibility."""
    from backend.server import get_db

    db = get_db()
    alert_id = f"alert-{uuid.uuid4().hex[:10]}"
    db.execute(
        """
        INSERT INTO system_alerts (id, code, severity, message, details, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            alert_id,
            "automation.dead_letter",
            "warning",
            "Automation action failed",
            json.dumps(
                {
                    "company_id": company_id,
                    "rule_id": rule_id,
                    "event_type": event_type,
                    "action": action,
                    "error": error,
                }
            ),
            _now_iso(),
        ),
    )
    db.commit()
    return {"alert_id": alert_id}
