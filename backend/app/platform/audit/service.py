"""Company and platform event/audit browsing helpers."""
from __future__ import annotations

import json
from typing import Any


def serialize_audit_row(row) -> dict[str, Any]:
    item = dict(row) if hasattr(row, "keys") else dict(row or {})
    details_raw = item.pop("details_json", None)
    if details_raw in (None, ""):
        item["details"] = {}
    else:
        try:
            parsed = json.loads(details_raw) if isinstance(details_raw, str) else details_raw
            item["details"] = parsed if isinstance(parsed, dict) else {"value": parsed}
        except Exception:
            item["details"] = {"raw": str(details_raw)[:500]}
    item["reason"] = str(item.get("reason") or "")
    item["actorName"] = str(item.get("actor_name") or "")
    item["ipAddress"] = str(item.get("ip_address") or "")
    # camelCase aliases for admin-v2
    item["eventType"] = item.get("event_type")
    item["actorUserId"] = item.get("actor_user_id")
    item["actorRole"] = item.get("actor_role")
    item["companyId"] = item.get("company_id")
    item["targetType"] = item.get("target_type")
    item["targetId"] = item.get("target_id")
    item["createdAt"] = item.get("created_at")
    return item


def build_audit_query(
    *,
    role: str,
    user_company_id: str | None,
    company_id: str | None = None,
    event_type: str = "",
    actor_role: str = "",
    actor_user_id: str = "",
    target_type: str = "",
    target_id: str = "",
    query_text: str = "",
    from_date: str = "",
    to_date: str = "",
    strict_company: bool = True,
) -> tuple[str, list[Any]]:
    """Build WHERE clause for audit browsing.

    Company admins always get a strict per-company log (no cross-company leakage).
    Superadmins can filter by company_id or see everything.
    """
    conditions: list[str] = []
    params: list[Any] = []
    role_l = str(role or "").strip()
    own = str(user_company_id or "").strip()
    requested = str(company_id or "").strip()

    if role_l == "superadmin":
        if requested:
            conditions.append("company_id = ?")
            params.append(requested)
    else:
        # Non-superadmin: always own company only (ignore client-supplied companyId).
        scope = own
        if not scope:
            conditions.append("1 = 0")
        elif strict_company:
            conditions.append("company_id = ?")
            params.append(scope)
        else:
            conditions.append(
                "(company_id = ? OR actor_user_id IN (SELECT id FROM users WHERE company_id = ?))"
            )
            params.extend([scope, scope])

    if event_type:
        conditions.append("event_type LIKE ?")
        params.append(f"{event_type}%")
    if actor_role:
        conditions.append("actor_role = ?")
        params.append(actor_role)
    if actor_user_id:
        conditions.append("actor_user_id = ?")
        params.append(actor_user_id)
    if target_type:
        conditions.append("target_type = ?")
        params.append(target_type)
    if target_id:
        conditions.append("target_id = ?")
        params.append(target_id)
    if query_text:
        pattern = f"%{query_text}%"
        conditions.append(
            "(message LIKE ? OR event_type LIKE ? OR IFNULL(target_id, '') LIKE ? OR IFNULL(reason, '') LIKE ? OR IFNULL(actor_name, '') LIKE ?)"
        )
        params.extend([pattern, pattern, pattern, pattern, pattern])
    if from_date:
        conditions.append("created_at >= ?")
        params.append(f"{from_date}T00:00:00Z" if "T" not in from_date else from_date)
    if to_date:
        conditions.append("created_at <= ?")
        params.append(f"{to_date}T23:59:59Z" if "T" not in to_date else to_date)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return where_clause, params


def list_audit_events(
    db,
    *,
    role: str,
    user_company_id: str | None,
    company_id: str | None = None,
    event_type: str = "",
    actor_role: str = "",
    actor_user_id: str = "",
    target_type: str = "",
    target_id: str = "",
    query_text: str = "",
    from_date: str = "",
    to_date: str = "",
    limit: int = 100,
    offset: int = 0,
    strict_company: bool = True,
) -> dict[str, Any]:
    where_clause, params = build_audit_query(
        role=role,
        user_company_id=user_company_id,
        company_id=company_id,
        event_type=event_type,
        actor_role=actor_role,
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        query_text=query_text,
        from_date=from_date,
        to_date=to_date,
        strict_company=strict_company,
    )
    limit = min(max(int(limit or 100), 1), 1000)
    offset = max(int(offset or 0), 0)
    rows = db.execute(
        f"SELECT * FROM audit_logs {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    total = db.execute(f"SELECT COUNT(*) AS c FROM audit_logs {where_clause}", params).fetchone()["c"]
    return {
        "events": [serialize_audit_row(row) for row in rows],
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
    }


def audit_summary(
    db,
    *,
    role: str,
    user_company_id: str | None,
    company_id: str | None = None,
    days: int = 7,
) -> dict[str, Any]:
    days = max(1, min(90, int(days or 7)))
    where_clause, params = build_audit_query(
        role=role,
        user_company_id=user_company_id,
        company_id=company_id,
        strict_company=True,
    )
    # Append time window
    from datetime import datetime, timedelta, timezone

    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if where_clause:
        where_clause = f"{where_clause} AND created_at >= ?"
    else:
        where_clause = "WHERE created_at >= ?"
    params = [*params, since]

    by_type = db.execute(
        f"""
        SELECT event_type, COUNT(*) AS c
        FROM audit_logs
        {where_clause}
        GROUP BY event_type
        ORDER BY c DESC
        LIMIT 20
        """,
        params,
    ).fetchall()
    by_actor = db.execute(
        f"""
        SELECT COALESCE(NULLIF(actor_name, ''), actor_user_id, actor_role, 'system') AS actor_label,
               COUNT(*) AS c
        FROM audit_logs
        {where_clause}
        GROUP BY actor_label
        ORDER BY c DESC
        LIMIT 15
        """,
        params,
    ).fetchall()
    total = db.execute(f"SELECT COUNT(*) AS c FROM audit_logs {where_clause}", params).fetchone()["c"]

    companies = []
    if str(role or "") == "superadmin" and not company_id:
        name_map: dict[str, str] = {}
        try:
            for crow in db.execute("SELECT id, name FROM companies").fetchall():
                name_map[str(crow["id"])] = str(crow["name"] or crow["id"])
        except Exception:
            name_map = {}
        companies = []
        for r in db.execute(
            f"""
            SELECT company_id, COUNT(*) AS c
            FROM audit_logs
            {where_clause}
            GROUP BY company_id
            ORDER BY c DESC
            LIMIT 25
            """,
            params,
        ).fetchall():
            cid = r["company_id"]
            companies.append(
                {
                    "companyId": cid,
                    "companyName": name_map.get(str(cid or ""), str(cid or "—") or "—"),
                    "count": int(r["c"] or 0),
                }
            )

    return {
        "days": days,
        "total": int(total or 0),
        "byEventType": [{"eventType": r["event_type"], "count": int(r["c"] or 0)} for r in by_type],
        "byActor": [{"actor": r["actor_label"], "count": int(r["c"] or 0)} for r in by_actor],
        "byCompany": companies,
    }
