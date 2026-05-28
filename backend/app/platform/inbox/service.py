"""Unified operations inbox — system, security, documents, leave."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _severity_rank(sev: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get((sev or "low").lower(), 5)


def build_operations_inbox(
    db,
    company_id: str | None,
    *,
    role: str = "company-admin",
    limit: int = 80,
    include_resolved: bool = False,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    cid = (company_id or "").strip()

    # Open security alerts
    try:
        rows = db.execute(
            """
            SELECT id, company_id, worker_id, alert_type, severity, title, details_json, status, created_at
            FROM security_alerts
            WHERE status = 'open'
            ORDER BY created_at DESC
            LIMIT 100
            """
        ).fetchall()
        for r in rows:
            row_cid = str(r["company_id"] or "").strip()
            if cid and row_cid and row_cid != cid:
                continue
            items.append(
                {
                    "id": f"sec:{r['id']}",
                    "source": "security",
                    "severity": r["severity"] or "medium",
                    "title": r["title"] or "Security alert",
                    "message": r["title"] or "",
                    "companyId": row_cid,
                    "workerId": r["worker_id"],
                    "createdAt": r["created_at"],
                    "status": "open",
                    "actions": [
                        {"type": "resolve", "action": "resolve_security_alert", "params": {"alert_id": r["id"]}},
                        {"type": "navigate", "url": "/ai-command-center.html", "label": "KI analysieren"},
                        {"type": "navigate", "url": "/index.html", "label": "Admin Legacy"},
                    ],
                }
            )
    except Exception:
        pass

    # System alerts (platform-wide; show to superadmin always, filter message for company hints)
    try:
        cond = "" if include_resolved else "AND resolved_at IS NULL"
        rows = db.execute(
            f"""
            SELECT id, code, severity, message, details, created_at, resolved_at
            FROM system_alerts
            WHERE 1=1 {cond}
            ORDER BY created_at DESC
            LIMIT 60
            """
        ).fetchall()
        for r in rows:
            details = (r["details"] or "") if r else ""
            if cid and details and cid not in details and f'"companyId": "{cid}"' not in details:
                if role != "superadmin":
                    continue
            items.append(
                {
                    "id": f"sys:{r['id']}",
                    "source": "system",
                    "severity": r["severity"] or "info",
                    "title": r["code"] or "system",
                    "message": r["message"] or "",
                    "companyId": cid or None,
                    "createdAt": r["created_at"],
                    "status": "resolved" if r["resolved_at"] else "open",
                    "actions": [
                        {"type": "ack", "action": "ack_system_alert", "params": {"alert_id": r["id"]}},
                        {"type": "navigate", "url": "/admin-v2/index.html", "label": "Admin v2"},
                    ],
                }
            )
    except Exception:
        pass

    # Documents expiring in 14 days (company scoped)
    if cid:
        try:
            horizon = (datetime.utcnow() + timedelta(days=14)).strftime("%Y-%m-%d")
            today = datetime.utcnow().strftime("%Y-%m-%d")
            rows = db.execute(
                """
                SELECT wd.id, wd.worker_id, wd.doc_type, wd.expiry_date, w.first_name, w.last_name
                FROM worker_documents wd
                JOIN workers w ON w.id = wd.worker_id
                WHERE w.company_id = ?
                  AND wd.expiry_date IS NOT NULL
                  AND wd.expiry_date <= ?
                  AND wd.expiry_date >= ?
                ORDER BY wd.expiry_date ASC
                LIMIT 40
                """,
                (cid, horizon, today),
            ).fetchall()
            for r in rows:
                name = f"{r['first_name']} {r['last_name']}".strip()
                items.append(
                    {
                        "id": f"doc:{r['id']}",
                        "source": "document",
                        "severity": "high",
                        "title": "Dokument läuft ab",
                        "message": f"{name}: {r['doc_type']} bis {r['expiry_date']}",
                        "companyId": cid,
                        "workerId": r["worker_id"],
                        "createdAt": _now_iso(),
                        "status": "open",
                        "actions": [
                            {"type": "navigate", "url": "/index.html#workers", "label": "Mitarbeiter"},
                            {"type": "prompt", "prompt": f"Welche Schritte für ablaufendes Dokument {r['doc_type']} von {name}?"},
                        ],
                    }
                )
        except Exception:
            pass

        # Pending leave requests
        try:
            rows = db.execute(
                """
                SELECT lr.id, lr.worker_id, lr.type, lr.start_date, lr.end_date, lr.status,
                       w.first_name, w.last_name
                FROM leave_requests lr
                JOIN workers w ON w.id = lr.worker_id
                WHERE w.company_id = ? AND lr.status IN ('pending', 'ausstehend')
                ORDER BY lr.created_at DESC
                LIMIT 30
                """,
                (cid,),
            ).fetchall()
            for r in rows:
                name = f"{r['first_name']} {r['last_name']}".strip()
                items.append(
                    {
                        "id": f"leave:{r['id']}",
                        "source": "leave",
                        "severity": "medium",
                        "title": "Urlaubsantrag offen",
                        "message": f"{name}: {r['type']} {r['start_date']} – {r['end_date']}",
                        "companyId": cid,
                        "workerId": r["worker_id"],
                        "createdAt": _now_iso(),
                        "status": "open",
                        "actions": [
                            {
                                "type": "execute",
                                "action": "approve_leave_request",
                                "params": {"leave_id": r["id"]},
                                "label": "Genehmigen",
                            },
                            {
                                "type": "execute",
                                "action": "reject_leave_request",
                                "params": {"leave_id": r["id"]},
                                "label": "Ablehnen",
                            },
                            {"type": "navigate", "url": "/ai-command-center.html", "label": "KI prüfen"},
                        ],
                    }
                )
        except Exception:
            pass

    items.sort(key=lambda x: (_severity_rank(x.get("severity", "low")), x.get("createdAt") or ""))
    open_count = sum(1 for i in items if i.get("status") == "open")
    critical_count = sum(1 for i in items if i.get("status") == "open" and i.get("severity") == "critical")

    return {
        "companyId": cid or None,
        "role": role,
        "items": items[:limit],
        "counts": {
            "total": len(items[:limit]),
            "open": open_count,
            "critical": critical_count,
        },
    }


def resolve_inbox_item(
    db,
    *,
    item_id: str,
    company_id: str,
    user_id: str,
    decision: str | None = None,
) -> dict[str, Any]:
    """Resolve or acknowledge a single inbox item."""
    if item_id.startswith("sec:"):
        alert_id = item_id[4:]
        row = db.execute(
            "SELECT id, company_id FROM security_alerts WHERE id = ? AND status = 'open'",
            (alert_id,),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "not_found"}
        if company_id and str(row["company_id"]) != str(company_id):
            return {"ok": False, "error": "forbidden"}
        db.execute(
            "UPDATE security_alerts SET status = 'resolved', resolved_at = ? WHERE id = ?",
            (_now_iso(), alert_id),
        )
        db.commit()
        return {"ok": True, "id": item_id, "status": "resolved"}

    if item_id.startswith("sys:"):
        alert_id = item_id[4:]
        db.execute(
            "UPDATE system_alerts SET resolved_at = ? WHERE id = ? AND resolved_at IS NULL",
            (_now_iso(), alert_id),
        )
        db.commit()
        return {"ok": True, "id": item_id, "status": "acknowledged"}

    if item_id.startswith("leave:"):
        leave_id = item_id[6:]
        from backend.app.platform.ai.actions import execute_action

        act = "approve_leave_request" if (decision or "approve") == "approve" else "reject_leave_request"
        return execute_action(
            db,
            company_id=company_id,
            user_id=user_id,
            action=act,
            params={"leave_id": leave_id},
        )

    return {"ok": False, "error": "action_not_supported", "hint": "Use linked admin screens for documents and leave."}
