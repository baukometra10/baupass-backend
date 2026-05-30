"""Default automation rules so events trigger actions without manual setup."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def ensure_company_automation_rules(db, company_id: str) -> int:
    """Insert starter rules if company has none. Returns count created."""
    try:
        existing = db.execute(
            "SELECT COUNT(*) AS c FROM automation_rules WHERE company_id = ?",
            (str(company_id),),
        ).fetchone()
        if int(existing["c"] if existing else 0) > 0:
            return 0
    except Exception:
        return 0

    templates = [
        {
            "name": "Autopilot: täglicher Security-Scan",
            "trigger_event": "autopilot.daily",
            "conditions": [],
            "actions": [{"type": "run_security_scan"}],
        },
        {
            "name": "Autopilot: kritischer Alert → Systemhinweis",
            "trigger_event": "security.alert.critical",
            "conditions": [{"field": "severity", "op": "eq", "value": "critical"}],
            "actions": [
                {
                    "type": "create_system_alert",
                    "code": "autopilot_security_escalation",
                    "severity": "high",
                    "message": "Kritischer Security-Alert — bitte prüfen (Autopilot).",
                }
            ],
        },
    ]
    created = 0
    for tpl in templates:
        rule_id = f"rule-{uuid.uuid4().hex[:12]}"
        db.execute(
            """
            INSERT INTO automation_rules
                (id, company_id, name, trigger_event, conditions_json, actions_json, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                rule_id,
                str(company_id),
                tpl["name"],
                tpl["trigger_event"],
                json.dumps(tpl["conditions"]),
                json.dumps(tpl["actions"]),
                _now_iso(),
            ),
        )
        created += 1
    if created:
        db.commit()
    return created
