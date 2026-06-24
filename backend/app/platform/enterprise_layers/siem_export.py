"""SIEM export formats (Phase C)."""
from __future__ import annotations

import json
from typing import Any


def _cef_escape(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace("|", "\\|")


def audit_row_to_cef(row: dict[str, Any], *, vendor: str = "SUPPIX") -> str:
    severity = 3
    if str(row.get("event_type") or "").endswith(".failed"):
        severity = 7
    extensions = [
        f"rt={_cef_escape(row.get('created_at') or '')}",
        f"suser={_cef_escape(row.get('actor_user_id') or '')}",
        f"cs1={_cef_escape(row.get('company_id') or '')}",
        f"msg={_cef_escape(row.get('message') or '')}",
    ]
    ext = " ".join(extensions)
    return (
        f"CEF:0|{vendor}|ControlPass|1.0|{_cef_escape(row.get('event_type') or 'audit')}|"
        f"Audit|{severity}|{ext}"
    )


def export_siem_payload(
    db,
    *,
    company_id: str | None = None,
    limit: int = 200,
    source: str = "both",
    fmt: str = "json",
) -> dict[str, Any]:
    limit = min(2000, max(1, limit))
    events: list[dict[str, Any]] = []
    cef_lines: list[str] = []

    if source in {"audit", "both"}:
        params: list[Any] = []
        scope = ""
        if company_id:
            scope = " AND company_id = ?"
            params.append(company_id)
        rows = db.execute(
            f"""
            SELECT id, event_type, actor_user_id, actor_role, company_id, target_type, target_id, message, created_at
            FROM audit_logs
            WHERE 1=1 {scope}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        for r in rows:
            item = dict(r)
            item["_source"] = "audit_logs"
            events.append(item)
            if fmt == "cef":
                cef_lines.append(audit_row_to_cef(item))

    if source in {"immutable", "both"}:
        try:
            imm_params: list[Any] = []
            imm_scope = ""
            if company_id:
                imm_scope = " AND company_id = ?"
                imm_params.append(int(company_id) if str(company_id).isdigit() else company_id)
            imm_rows = db.execute(
                f"""
                SELECT event_id, event_type, company_id, actor_id, payload_json, occurred_at, event_hash
                FROM immutable_audit_events
                WHERE 1=1 {imm_scope}
                ORDER BY seq DESC
                LIMIT ?
                """,
                (*imm_params, limit),
            ).fetchall()
            for r in imm_rows:
                item = {
                    "id": r["event_id"],
                    "event_type": r["event_type"],
                    "company_id": r["company_id"],
                    "actor_user_id": r["actor_id"],
                    "message": r["payload_json"],
                    "created_at": r["occurred_at"],
                    "_source": "immutable_audit_events",
                    "event_hash": r["event_hash"],
                }
                events.append(item)
                if fmt == "cef":
                    cef_lines.append(audit_row_to_cef(item))
        except Exception:
            pass

    if fmt == "cef":
        return {
            "format": "cef",
            "count": len(cef_lines),
            "lines": cef_lines,
        }
    return {
        "format": "baupass_siem_v2",
        "count": len(events),
        "events": events,
    }
