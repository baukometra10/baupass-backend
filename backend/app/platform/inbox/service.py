"""Unified operations inbox — system, security, documents, leave."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _coerce_iso_timestamp(value: Any) -> str:
    """Normalize DB timestamps (TEXT or datetime) for parsing and sorting."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            return dt.replace(microsecond=0).isoformat() + "Z"
        return dt.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat() + "Z"
    return str(value).strip()


def _sla_meta(created_at: Any, severity: str) -> dict[str, Any]:
    sla_hours = {"critical": 4, "high": 24, "medium": 48}.get((severity or "").lower(), 72)
    try:
        raw = _coerce_iso_timestamp(created_at).replace("Z", "+00:00")
        created = datetime.fromisoformat(raw)
        if created.tzinfo is not None:
            created = created.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError, AttributeError):
        created = datetime.utcnow()
    due = created + timedelta(hours=sla_hours)
    now = datetime.utcnow()
    overdue = now > due
    due_soon = not overdue and (due - now).total_seconds() <= 4 * 3600
    return {
        "slaHours": sla_hours,
        "slaDueAt": due.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "slaStatus": "overdue" if overdue else ("due_soon" if due_soon else "ok"),
    }


def _item_with_sla(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("status") != "open":
        return item
    meta = _sla_meta(item.get("createdAt"), str(item.get("severity") or "medium"))
    item.update(meta)
    return item


def _severity_rank(sev: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get((sev or "low").lower(), 5)


def build_operations_inbox(
    db,
    company_id: str | None,
    *,
    role: str = "company-admin",
    limit: int = 80,
    include_resolved: bool = False,
    source_filter: str | None = None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    cid = (company_id or "").strip()

    # Open security alerts (strict company scope when a firm is selected)
    try:
        if cid:
            rows = db.execute(
                """
                SELECT id, company_id, worker_id, alert_type, severity, title, details_json, status, created_at
                FROM security_alerts
                WHERE status = 'open' AND company_id = ?
                ORDER BY created_at DESC
                LIMIT 100
                """,
                (cid,),
            ).fetchall()
        else:
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
            if cid and row_cid != cid:
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
                    "createdAt": _coerce_iso_timestamp(r["created_at"]),
                    "status": "open",
                    "actions": [
                        {"type": "resolve", "action": "resolve_security_alert", "params": {"alert_id": r["id"]}},
                        *(
                            [
                                {
                                    "type": "execute",
                                    "action": "notify_worker",
                                    "params": {
                                        "worker_id": r["worker_id"],
                                        "title": "SUPPIX Sicherheit",
                                        "body": (r["title"] or "Security-Hinweis")[:200],
                                    },
                                    "label": "Push an MA",
                                }
                            ]
                            if r["worker_id"]
                            else []
                        ),
                        {"type": "navigate", "url": "/ai-command-center.html", "label": "KI analysieren"},
                        {"type": "navigate", "url": "/index.html", "label": "Admin Legacy"},
                    ],
                }
            )
    except Exception:
        pass

    # System alerts — only when they belong to the selected company (or global view without company)
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
            details_l = details.lower()
            if cid:
                # When a company is selected, never leak other tenants' / orphan platform noise.
                mentions_company = (
                    cid in details
                    or f'"companyId": "{cid}"' in details
                    or f'"company_id": "{cid}"' in details
                    or f"company_id={cid}" in details_l
                )
                if not mentions_company:
                    continue
            code = str(r["code"] or "")
            title_map = {
                "deployment_worker_declined": "Einsatz abgelehnt",
            }
            items.append(
                {
                    "id": f"sys:{r['id']}",
                    "source": "system",
                    "severity": r["severity"] or "info",
                    "title": title_map.get(code, code or "system"),
                    "message": r["message"] or "",
                    "companyId": cid or None,
                    "createdAt": _coerce_iso_timestamp(r["created_at"]),
                    "status": "resolved" if r["resolved_at"] else "open",
                    "actions": [
                        {"type": "ack", "action": "ack_system_alert", "params": {"alert_id": r["id"]}},
                        *(
                            [
                                {
                                    "type": "navigate",
                                    "url": "/index.html?view=deployment-plan",
                                    "label": "Einsatzplan",
                                }
                            ]
                            if code == "deployment_worker_declined"
                            else []
                        ),
                        {"type": "navigate", "url": "/admin-v2/index.html", "label": "Admin v2"},
                    ],
                }
            )
    except Exception:
        pass

    # Worker declined deployment days (Einsatzplan)
    if cid:
        try:
            from datetime import datetime

            from backend.app.platform.workforce.deployment_responses import list_company_declines_for_month

            now = datetime.utcnow()
            seen_decline: set[str] = set()
            for offset in (0, 1):
                m = now.month + offset
                y = now.year
                if m > 12:
                    m -= 12
                    y += 1
                declines = list_company_declines_for_month(
                    db, company_id=cid, year=y, month=m, limit=25
                )
                for dec in declines:
                    key = f"{dec.get('workerId')}:{dec.get('workDate')}"
                    if key in seen_decline:
                        continue
                    seen_decline.add(key)
                    reason = str(dec.get("reason") or "").strip()
                    loc = str(dec.get("location") or "").strip() or "—"
                    msg = f"{dec.get('workerName') or 'Mitarbeiter'} · {dec.get('workDate')} · {loc}"
                    if reason:
                        msg += f" · Grund: {reason}"
                    items.append(
                        {
                            "id": f"depdecl:{key}",
                            "source": "deployment",
                            "severity": "high",
                            "title": "Einsatz abgelehnt",
                            "message": msg[:500],
                            "companyId": cid,
                            "workerId": dec.get("workerId"),
                            "createdAt": _coerce_iso_timestamp(dec.get("respondedAt")) or _now_iso(),
                            "status": "open",
                            "actions": [
                                {
                                    "type": "navigate",
                                    "url": "/index.html?view=deployment-plan",
                                    "label": "Einsatzplan öffnen",
                                },
                                {
                                    "type": "navigate",
                                    "url": "/enterprise-hub.html",
                                    "label": "Betrieb-Portal",
                                },
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
                SELECT wd.id, wd.worker_id, wd.doc_type, wd.expiry_date, wd.created_at,
                       w.first_name, w.last_name
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
                        "createdAt": _coerce_iso_timestamp(r["created_at"])
                        or _coerce_iso_timestamp(r["expiry_date"])
                        or _now_iso(),
                        "status": "open",
                        "actions": [
                            {
                                "type": "execute",
                                "action": "notify_worker",
                                "params": {
                                    "worker_id": r["worker_id"],
                                    "title": "Dokument läuft ab",
                                    "body": f"{r['doc_type']} bis {r['expiry_date']}",
                                    "tag": "document-expiry",
                                },
                                "label": "Push an MA",
                            },
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
                       lr.created_at, w.first_name, w.last_name
                FROM leave_requests lr
                JOIN workers w ON w.id = lr.worker_id
                WHERE (w.company_id = ? OR lr.company_id = ?) AND lr.status IN ('pending', 'ausstehend')
                ORDER BY lr.created_at DESC
                LIMIT 30
                """,
                (cid, cid),
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
                        "createdAt": _coerce_iso_timestamp(r["created_at"]) or _now_iso(),
                        "status": "open",
                        "actions": [
                            {
                                "type": "navigate",
                                "url": f"/index.html?view=leave&leave_id={r['id']}",
                                "label": "PDF ansehen",
                            },
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

    items = [_item_with_sla(it) for it in items]
    items.sort(
        key=lambda x: (
            _severity_rank(x.get("severity", "low")),
            0 if x.get("slaStatus") == "overdue" else 1 if x.get("slaStatus") == "due_soon" else 2,
            _coerce_iso_timestamp(x.get("createdAt")),
        )
    )

    by_source: dict[str, int] = {}
    for it in items:
        src = str(it.get("source") or "other")
        by_source[src] = by_source.get(src, 0) + 1

    sf = (source_filter or "").strip().lower()
    if sf:
        items = [i for i in items if str(i.get("source") or "").lower() == sf]

    open_count = sum(1 for i in items if i.get("status") == "open")
    critical_count = sum(1 for i in items if i.get("status") == "open" and i.get("severity") == "critical")

    return {
        "companyId": cid or None,
        "role": role,
        "sourceFilter": sf or None,
        "items": items[:limit],
        "counts": {
            "total": len(items[:limit]),
            "open": open_count,
            "critical": critical_count,
            "bySource": by_source,
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
        from .events import notify_inbox_changed

        notify_inbox_changed(company_id, source="security_resolve")
        return {"ok": True, "id": item_id, "status": "resolved"}

    if item_id.startswith("sys:"):
        alert_id = item_id[4:]
        db.execute(
            "UPDATE system_alerts SET resolved_at = ? WHERE id = ? AND resolved_at IS NULL",
            (_now_iso(), alert_id),
        )
        db.commit()
        from .events import notify_inbox_changed

        notify_inbox_changed(company_id, source="system_ack")
        return {"ok": True, "id": item_id, "status": "acknowledged"}

    if item_id.startswith("leave:"):
        leave_id = item_id[6:]
        from backend.app.platform.ai.actions import execute_action

        act = "approve_leave_request" if (decision or "approve") == "approve" else "reject_leave_request"
        result = execute_action(
            db,
            company_id=company_id,
            user_id=user_id,
            action=act,
            params={"leave_id": leave_id},
        )
        if result.get("ok"):
            from .events import notify_inbox_changed

            notify_inbox_changed(company_id, source="leave_resolve")
        return result

    return {"ok": False, "error": "action_not_supported", "hint": "Use linked admin screens for documents and leave."}
