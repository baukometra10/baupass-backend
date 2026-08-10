"""AI-suggested and executable safe actions."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")


def _audit_ai(
    event_type: str,
    message: str,
    *,
    company_id: str,
    user_id: str = "",
    target_id: str | None = None,
    details: dict | None = None,
) -> None:
    try:
        from backend.server import log_audit

        actor = {"id": user_id, "role": "company-admin"} if user_id else None
        log_audit(
            event_type,
            message,
            target_type="ai_action",
            target_id=target_id,
            company_id=company_id,
            actor=actor,
            details=details or {},
        )
    except Exception:
        pass


ALLOWED_EXECUTE = frozenset(
    {
        "resolve_security_alert",
        "send_briefing_email",
        "send_briefing_webhook",
        "export_briefing_markdown",
        "approve_leave_request",
        "reject_leave_request",
        "notify_worker",
        "ack_system_alert",
        "prepare_deployment_month",
        "confirm_send_deployment_month",
        "remind_expired_documents",
        "remind_late_workers",
        "resolve_open_security_alerts",
        "ack_open_system_alerts",
        "broadcast_worker_message",
        "export_ops_snapshot",
        "resolve_inbox_item",
    }
)


def suggest_actions(
    ctx: dict[str, Any],
    *,
    company_id: str,
    tools_used: list[str] | None = None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    sec = ctx.get("security") or {}
    findings = sec.get("topFindings") or []
    em = ctx.get("emergency") or {}

    if int(sec.get("openFindings") or 0) > 0:
        actions.append(
            {
                "id": "nav_security",
                "type": "navigate",
                "labelDe": "Security-Befunde im Hub öffnen",
                "labelEn": "Open security findings in hub",
                "url": "/enterprise-hub.html",
            }
        )
    if em.get("active"):
        actions.append(
            {
                "id": "nav_emergency",
                "type": "navigate",
                "labelDe": "Notfall-Status prüfen",
                "labelEn": "Check emergency status",
                "url": "/ops-command-center.html",
            }
        )
    if "get_expired_documents" in (tools_used or []) or int(
        (ctx.get("intelligence") or {}).get("risk", {}).get("expired_documents") or 0
    ) > 0:
        actions.append(
            {
                "id": "nav_workers",
                "type": "navigate",
                "labelDe": "Mitarbeiter & Dokumente in Admin",
                "labelEn": "Workers & documents in admin",
                "url": "/admin-v2/index.html",
            }
        )

    for i, f in enumerate(findings[:3]):
        aid = f.get("workerId") or f.get("alert_id")
        if f.get("type") == "high_frequency_taps" and f.get("workerId"):
            actions.append(
                {
                    "id": f"profile_{i}",
                    "type": "navigate",
                    "labelDe": f"Mitarbeiter {f.get('workerId')} prüfen",
                    "url": f"/admin-v2/index.html#workers",
                }
            )

    actions.append(
        {
            "id": "email_briefing",
            "type": "execute",
            "action": "send_briefing_email",
            "labelDe": "Tagesbriefing per E-Mail senden",
            "labelEn": "Email daily briefing",
            "labelAr": "إرسال الملخص بالبريد",
            "paramsSchema": {"to": "email"},
        }
    )
    actions.append(
        {
            "id": "webhook_briefing",
            "type": "execute",
            "action": "send_briefing_webhook",
            "labelDe": "Briefing an Slack/Teams Webhook",
            "labelEn": "Post briefing to Slack/Teams",
            "labelAr": "إرسال إلى Webhook",
        }
    )
    pending_leave = int((ctx.get("pendingLeave") or 0))
    if pending_leave > 0:
        actions.append(
            {
                "id": "nav_inbox",
                "type": "navigate",
                "labelDe": f"{pending_leave} Urlaubsanträge prüfen",
                "labelEn": f"Review {pending_leave} leave requests",
                "url": "/index.html?view=leave",
            }
        )

    actions.append(
        {
            "id": "export_md",
            "type": "execute",
            "action": "export_briefing_markdown",
                "labelDe": "Briefing als Markdown exportieren",
                "labelEn": "Export briefing as markdown",
                "labelAr": "تصدير Markdown",
            "params": {},
        }
    )
    if "get_deployment_month_status" in (tools_used or []):
        actions.append(
            {
                "id": "prep_deployment",
                "type": "execute",
                "action": "prepare_deployment_month",
                "risk": "high",
                "labelDe": "Einsatzplan-Entwurf vorbereiten (Bestätigung)",
                "labelEn": "Prepare deployment draft (needs confirm)",
                "labelAr": "تجهيز مسودة خطة الانتشار (يلزم تأكيد)",
                "params": {},
            }
        )
        actions.append(
            {
                "id": "nav_deployment",
                "type": "navigate",
                "tab": "workers",
                "focus": "deployment",
                "labelDe": "Einsatzplan in Admin öffnen",
                "labelEn": "Open deployment plan in admin",
                "labelAr": "فتح خطة الانتشار",
                "url": "/admin-v2/index.html?tab=workers&einsatzplan=1",
            }
        )
    return actions[:8]


def execute_action(
    db,
    *,
    company_id: str,
    user_id: str,
    action: str,
    params: dict | None = None,
    briefing_text: str | None = None,
) -> dict[str, Any]:
    params = params or {}
    action = (action or "").strip()
    if action not in ALLOWED_EXECUTE:
        return {"ok": False, "error": "action_not_allowed", "action": action}

    if action == "resolve_security_alert":
        alert_id = str(params.get("alert_id") or "").strip()
        if not alert_id:
            return {"ok": False, "error": "alert_id_required"}
        row = db.execute(
            "SELECT id, status FROM security_alerts WHERE id = ? AND company_id = ?",
            (alert_id, company_id),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "alert_not_found"}
        db.execute(
            "UPDATE security_alerts SET status = 'resolved', resolved_at = ? WHERE id = ?",
            (_now(), alert_id),
        )
        db.commit()
        return {"ok": True, "alertId": alert_id, "status": "resolved"}

    if action == "export_briefing_markdown":
        text = (briefing_text or params.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "briefing_text_required"}
        return {"ok": True, "format": "markdown", "content": text}

    if action == "send_briefing_webhook":
        from .notifications import dispatch_briefing_notifications

        text = (briefing_text or params.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "briefing_text_required"}
        dispatch = dispatch_briefing_notifications(text, company_id=company_id)
        return {"ok": dispatch.get("sent", 0) > 0, **dispatch}

    if action == "send_briefing_email":
        from .mailer import send_ai_briefing_email

        to = str(params.get("to") or "").strip()
        subject = str(params.get("subject") or "Suppix AI Tagesbriefing").strip()
        body = (briefing_text or params.get("body") or "").strip()
        if not to or not body:
            return {"ok": False, "error": "to_and_body_required"}
        ok, err = send_ai_briefing_email(to=to, subject=subject, body_text=body)
        return {"ok": ok, "to": to, "error": err or None}

    if action in ("approve_leave_request", "reject_leave_request"):
        leave_id = str(params.get("leave_id") or params.get("request_id") or "").strip()
        if not leave_id:
            return {"ok": False, "error": "leave_id_required"}
        new_status = "genehmigt" if action == "approve_leave_request" else "abgelehnt"
        row = db.execute("SELECT * FROM leave_requests WHERE id = ?", (leave_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "leave_not_found"}
        if str(row["company_id"]) != str(company_id):
            return {"ok": False, "error": "forbidden"}
        review_note = str(params.get("review_note") or "KI/Posteingang")[:500]
        db.execute(
            """
            UPDATE leave_requests
            SET status = ?, reviewed_by_user_id = ?, reviewed_at = ?, review_note = ?
            WHERE id = ?
            """,
            (new_status, user_id or "ai-inbox", _now(), review_note, leave_id),
        )
        db.commit()
        push_delivery = {"delivered": False, "pushSent": 0, "channels": []}
        try:
            from backend.app.platform.push.automation import push_leave_decision

            push_delivery = push_leave_decision(
                db, row, new_status, review_note=review_note
            )
        except Exception:
            pass
        return {
            "ok": True,
            "leaveId": leave_id,
            "status": new_status,
            "pushDelivery": push_delivery,
            "pushSent": push_delivery.get("pushSent", 0),
        }

    if action == "notify_worker":
        worker_id = str(params.get("worker_id") or "").strip()
        title = str(params.get("title") or "WorkPass").strip()[:120]
        body = str(params.get("body") or params.get("message") or "").strip()[:500]
        if not worker_id or not body:
            return {"ok": False, "error": "worker_id_and_body_required"}
        w = db.execute(
            "SELECT id FROM workers WHERE id = ? AND company_id = ?",
            (worker_id, company_id),
        ).fetchone()
        if not w:
            return {"ok": False, "error": "worker_not_found"}
        tag = str(params.get("tag") or "ops-notify").strip()[:40] or "ops-notify"
        action_url = str(params.get("action_url") or "chat").strip()[:80] or "chat"
        delivery: dict[str, Any] = {"pushSent": 0, "delivered": False}
        try:
            from backend.app.platform.notifications.worker_mitteilung import notify_worker_mitteilung

            # In-app Mitteilung + optional push/email — useful even without FCM token.
            result = notify_worker_mitteilung(
                db,
                worker_id,
                notif_type="ops_notify",
                title=title,
                message=body,
                action_url=action_url,
                push_tag=tag,
                send_email=True,
            )
            db.commit()
            push_sent = int(result.get("pushSent") or 0)
            delivery = {
                "delivered": push_sent > 0,
                "pushSent": push_sent,
                "emailSent": bool(result.get("emailSent")),
                "notificationId": result.get("notificationId"),
                "channels": (["push"] if push_sent > 0 else [])
                + (["email"] if result.get("emailSent") else [])
                + (["inbox"] if result.get("notificationId") else []),
                "hint": None
                if push_sent > 0 or result.get("emailSent") or result.get("notificationId")
                else (
                    "Keine Push-Zustellung — Mitarbeiter hat noch kein Gerät / keine Push-Anmeldung. "
                    "Mitteilung wurde trotzdem versucht."
                ),
            }
            if push_sent <= 0 and not result.get("notificationId") and not result.get("emailSent"):
                # Fall back to raw push attempt for clearer channel hints.
                from backend.app.platform.push.automation import push_to_worker

                delivery = push_to_worker(
                    db, worker_id, title, body, tag=tag, company_id=str(company_id)
                )
        except Exception as exc:
            try:
                from backend.app.platform.push.automation import push_to_worker

                delivery = push_to_worker(
                    db, worker_id, title, body, tag=tag, company_id=str(company_id)
                )
            except Exception as exc2:
                return {"ok": False, "error": "push_failed", "hint": str(exc2 or exc)[:200]}
        sent = int(delivery.get("pushSent") or 0)
        has_inbox = bool(delivery.get("notificationId") or "inbox" in (delivery.get("channels") or []))
        has_email = bool(delivery.get("emailSent"))
        # Employer action succeeded if any channel worked (push, email, or in-app).
        ok = sent > 0 or has_inbox or has_email or delivery.get("delivered") is True
        if not ok and not delivery.get("hint"):
            delivery["hint"] = (
                "Kein Push-Gerät beim Mitarbeiter. Bitte Chat nutzen oder Push in der App aktivieren."
            )
        return {
            "ok": True if (sent > 0 or has_inbox or has_email) else False,
            "softFail": sent <= 0,
            "pushSent": sent,
            "pushDelivery": delivery,
            "workerId": worker_id,
            "message": delivery.get("hint") if sent <= 0 else None,
            "error": None if (sent > 0 or has_inbox or has_email) else "push_not_delivered",
        }

    if action == "ack_system_alert":
        alert_id = str(params.get("alert_id") or "").strip()
        if not alert_id:
            return {"ok": False, "error": "alert_id_required"}
        db.execute(
            "UPDATE system_alerts SET resolved_at = ? WHERE id = ? AND resolved_at IS NULL",
            (_now(), alert_id),
        )
        db.commit()
        return {"ok": True, "alertId": alert_id}

    if action == "prepare_deployment_month":
        from backend.app.platform.workforce.deployment_month import (
            copy_month_weekday_pattern,
            prepare_next_month_draft,
        )

        year_raw = params.get("year")
        month_raw = params.get("month")
        if year_raw is not None and month_raw is not None:
            try:
                ty, tm = int(year_raw), int(month_raw)
            except (TypeError, ValueError):
                return {"ok": False, "error": "invalid_year_month"}
            if tm < 1 or tm > 12:
                return {"ok": False, "error": "invalid_month"}
            # Copy weekday pattern from previous month into the requested target.
            if tm <= 1:
                sy, sm = ty - 1, 12
            else:
                sy, sm = ty, tm - 1
            result = copy_month_weekday_pattern(
                db,
                company_id=company_id,
                source_year=sy,
                source_month=sm,
                target_year=ty,
                target_month=tm,
            )
            result["year"] = ty
            result["month"] = tm
            result["awaitingConfirm"] = True
            result["preparedBy"] = user_id
            return result
        result = prepare_next_month_draft(db, company_id)
        result["preparedBy"] = user_id
        return result

    if action == "confirm_send_deployment_month":
        from datetime import datetime, timezone

        from backend.app.platform.workforce.deployment_month import confirm_and_send_month

        # Must come from an approved proposal / explicit UI confirm — never silent.
        if not bool(params.get("user_confirmed")):
            return {"ok": False, "error": "user_confirmation_required"}
        now = datetime.now(timezone.utc).date()
        try:
            year = int(params.get("year") or now.year)
            month = int(params.get("month") or now.month)
        except (TypeError, ValueError):
            return {"ok": False, "error": "invalid_year_month"}
        worker_ids = params.get("worker_ids")
        if worker_ids is not None and not isinstance(worker_ids, list):
            worker_ids = None
        lang = str(params.get("lang") or "de")[:2]
        return confirm_and_send_month(
            db,
            company_id=company_id,
            year=year,
            month=month,
            user_id=user_id,
            user_confirmed=True,
            lang=lang,
            worker_ids=worker_ids,
        )

    if action == "remind_expired_documents":
        from backend.app.platform.ai.tools import tool_expired_documents
        from backend.app.platform.push.automation import push_document_expiry

        limit = max(1, min(40, int(params.get("limit") or 25)))
        data = tool_expired_documents(db, company_id, {"limit": limit})
        rows = data.get("expired") or []
        sent = 0
        failed = 0
        details = []
        for row in rows:
            wid = str(row.get("worker_id") or "").strip()
            if not wid:
                failed += 1
                continue
            try:
                delivery = push_document_expiry(
                    db,
                    worker_id=wid,
                    company_id=company_id,
                    doc_type=str(row.get("doc_type") or "Dokument"),
                    expiry_date=str(row.get("expiry_date") or ""),
                )
                ok = int(delivery.get("pushSent") or 0) > 0
                if ok:
                    sent += 1
                else:
                    failed += 1
                details.append({"workerId": wid, "ok": ok})
            except Exception as exc:
                failed += 1
                details.append({"workerId": wid, "ok": False, "error": str(exc)[:120]})
        return {
            "ok": sent > 0 or (not rows),
            "pushSent": sent,
            "failed": failed,
            "processed": len(rows),
            "details": details[:20],
        }

    if action == "remind_late_workers":
        from backend.app.platform.ai.tools import tool_repeated_late_workers
        from backend.app.platform.push.automation import push_to_worker

        data = tool_repeated_late_workers(db, company_id, {"limit": int(params.get("limit") or 15)})
        workers = data.get("workers") or data.get("items") or data.get("lateWorkers") or []
        if not isinstance(workers, list):
            workers = []
        title = str(params.get("title") or "Hinweis: Pünktlichkeit").strip()[:120]
        body_tmpl = str(
            params.get("body")
            or "Bitte achten Sie auf pünktlichen Arbeitsbeginn. Bei Problemen melden Sie sich bei der Leitung."
        ).strip()[:400]
        sent = 0
        failed = 0
        for w in workers[:20]:
            wid = str(w.get("workerId") or w.get("worker_id") or w.get("id") or "").strip()
            if not wid:
                failed += 1
                continue
            try:
                delivery = push_to_worker(
                    db,
                    wid,
                    title,
                    body_tmpl,
                    tag="ai-late-remind",
                    company_id=str(company_id),
                )
                if int(delivery.get("pushSent") or 0) > 0:
                    sent += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
        return {"ok": sent > 0 or not workers, "pushSent": sent, "failed": failed, "processed": len(workers)}

    if action == "resolve_open_security_alerts":
        limit = max(1, min(30, int(params.get("limit") or 15)))
        rows = db.execute(
            """
            SELECT id FROM security_alerts
            WHERE company_id = ? AND COALESCE(status, '') NOT IN ('resolved', 'closed')
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
        resolved = 0
        for row in rows:
            db.execute(
                "UPDATE security_alerts SET status = 'resolved', resolved_at = ? WHERE id = ?",
                (_now(), row["id"]),
            )
            resolved += 1
        if resolved:
            db.commit()
        return {"ok": True, "resolved": resolved}

    if action == "ack_open_system_alerts":
        limit = max(1, min(40, int(params.get("limit") or 20)))
        # Prefer company-scoped alerts when column exists; fall back to global open alerts.
        try:
            rows = db.execute(
                """
                SELECT id FROM system_alerts
                WHERE resolved_at IS NULL
                  AND (company_id IS NULL OR company_id = '' OR company_id = ?)
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (company_id, limit),
            ).fetchall()
        except Exception:
            rows = db.execute(
                """
                SELECT id FROM system_alerts
                WHERE resolved_at IS NULL
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        acked = 0
        for row in rows:
            db.execute(
                "UPDATE system_alerts SET resolved_at = ? WHERE id = ? AND resolved_at IS NULL",
                (_now(), row["id"]),
            )
            acked += 1
        if acked:
            db.commit()
        return {"ok": True, "acked": acked}

    if action == "broadcast_worker_message":
        from backend.app.platform.push.automation import push_to_worker

        title = str(params.get("title") or "Mitteilung").strip()[:120]
        body = str(params.get("body") or params.get("message") or "").strip()[:500]
        if not body:
            return {"ok": False, "error": "body_required"}
        scope = str(params.get("scope") or "active").strip().lower()
        if scope == "onsite":
            from backend.app.platform.ai.tools import tool_get_on_site_workers

            onsite = tool_get_on_site_workers(db, company_id, {})
            targets = [str(w.get("id")) for w in (onsite.get("workers") or []) if w.get("id")]
        else:
            rows = db.execute(
                """
                SELECT id FROM workers
                WHERE company_id = ? AND deleted_at IS NULL
                  AND COALESCE(status, 'aktiv') NOT IN ('gesperrt', 'inactive', 'deleted')
                LIMIT 300
                """,
                (company_id,),
            ).fetchall()
            targets = [str(r["id"]) for r in rows]
        sent = 0
        failed = 0
        for wid in targets:
            try:
                delivery = push_to_worker(
                    db, wid, title, body, tag="ai-broadcast", company_id=str(company_id)
                )
                if int(delivery.get("pushSent") or 0) > 0:
                    sent += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
        return {
            "ok": sent > 0,
            "pushSent": sent,
            "failed": failed,
            "processed": len(targets),
            "scope": scope,
        }

    if action == "export_ops_snapshot":
        from .context_builder import build_compact_context, deterministic_briefing

        lang = str(params.get("lang") or "de")[:2]
        role = str(params.get("role") or "company-admin")
        ctx = build_compact_context(db, company_id, role)
        content = deterministic_briefing(ctx, lang=lang)
        return {
            "ok": True,
            "format": "markdown",
            "content": content,
            "filename": f"ops-snapshot-{company_id[:12]}.md",
        }

    if action == "resolve_inbox_item":
        from backend.app.platform.inbox.service import resolve_inbox_item

        item_id = str(params.get("item_id") or params.get("id") or "").strip()
        if not item_id:
            return {"ok": False, "error": "item_id_required"}
        decision = str(params.get("decision") or "ack").strip() or "ack"
        result = resolve_inbox_item(
            db,
            item_id=item_id,
            company_id=company_id,
            user_id=user_id,
            decision=decision,
        )
        return result if isinstance(result, dict) else {"ok": bool(result)}

    return {"ok": False, "error": "unknown"}


def _ensure_proposal_tables(db) -> None:
    try:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_action_proposals (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                action TEXT NOT NULL,
                params_json TEXT NOT NULL DEFAULT '{}',
                rationale TEXT,
                risk TEXT DEFAULT 'low',
                status TEXT NOT NULL DEFAULT 'pending',
                created_by TEXT,
                created_at TEXT NOT NULL,
                decided_by TEXT,
                decided_at TEXT,
                result_json TEXT
            )
            """
        )
    except Exception:
        pass


def propose_action(
    db,
    *,
    company_id: str,
    user_id: str,
    action: str,
    params: dict | None = None,
    rationale: str = "",
    risk: str = "low",
) -> dict[str, Any]:
    action = (action or "").strip()
    if action not in ALLOWED_EXECUTE:
        return {"ok": False, "error": "action_not_allowed", "action": action}
    _ensure_proposal_tables(db)
    import secrets

    proposal_id = f"prop-{secrets.token_hex(8)}"
    now = _now()
    db.execute(
        """
        INSERT INTO ai_action_proposals (
            id, company_id, action, params_json, rationale, risk, status, created_by, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        """,
        (
            proposal_id,
            str(company_id),
            action,
            json.dumps(params or {}, ensure_ascii=False),
            str(rationale or "")[:800],
            str(risk or "low")[:20],
            str(user_id or ""),
            now,
        ),
    )
    db.commit()
    _audit_ai(
        "ai.action.proposed",
        f"AI action proposed: {action}",
        company_id=str(company_id),
        user_id=str(user_id or ""),
        target_id=proposal_id,
        details={"action": action, "risk": risk, "rationale": str(rationale or "")[:300]},
    )
    return {
        "ok": True,
        "proposal": {
            "id": proposal_id,
            "action": action,
            "params": params or {},
            "rationale": rationale,
            "risk": risk,
            "status": "pending",
            "createdAt": now,
            "createdBy": user_id,
        },
    }


def list_proposals(db, *, company_id: str, status: str = "pending", limit: int = 40) -> list[dict[str, Any]]:
    _ensure_proposal_tables(db)
    status = (status or "pending").strip() or "pending"
    limit = max(1, min(100, int(limit or 40)))
    rows = db.execute(
        """
        SELECT id, company_id, action, params_json, rationale, risk, status, created_by, created_at,
               decided_by, decided_at, result_json
        FROM ai_action_proposals
        WHERE company_id = ? AND status = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (str(company_id), status, limit),
    ).fetchall()
    out = []
    for row in rows:
        try:
            params = json.loads(row["params_json"] or "{}")
        except Exception:
            params = {}
        out.append(
            {
                "id": row["id"],
                "action": row["action"],
                "params": params,
                "rationale": row["rationale"],
                "risk": row["risk"],
                "status": row["status"],
                "createdAt": row["created_at"],
                "createdBy": row["created_by"],
                "decidedBy": row["decided_by"],
                "decidedAt": row["decided_at"],
            }
        )
    return out


def approve_action(
    db,
    *,
    company_id: str,
    user_id: str,
    proposal_id: str,
    briefing_text: str | None = None,
) -> dict[str, Any]:
    _ensure_proposal_tables(db)
    row = db.execute(
        "SELECT * FROM ai_action_proposals WHERE id = ? AND company_id = ?",
        (str(proposal_id), str(company_id)),
    ).fetchone()
    if not row:
        return {"ok": False, "error": "proposal_not_found"}
    if str(row["status"] or "") != "pending":
        return {"ok": False, "error": "proposal_not_pending", "status": row["status"]}
    action = str(row["action"] or "")
    if action not in ALLOWED_EXECUTE:
        return {"ok": False, "error": "action_not_allowed", "action": action}
    try:
        params = json.loads(row["params_json"] or "{}")
    except Exception:
        params = {}
    if not isinstance(params, dict):
        params = {}
    # Approving a staged proposal is the employer's explicit confirmation.
    if action == "confirm_send_deployment_month":
        params = {**params, "user_confirmed": True}
    execution = execute_action(
        db,
        company_id=company_id,
        user_id=user_id,
        action=action,
        params=params,
        briefing_text=briefing_text,
    )
    new_status = "executed" if execution.get("ok") else "failed"
    db.execute(
        """
        UPDATE ai_action_proposals
        SET status = ?, decided_by = ?, decided_at = ?, result_json = ?
        WHERE id = ?
        """,
        (new_status, str(user_id or ""), _now(), json.dumps(execution, ensure_ascii=False), str(proposal_id)),
    )
    db.commit()
    _audit_ai(
        "ai.action.approved" if execution.get("ok") else "ai.action.failed",
        f"AI action {new_status}: {action}",
        company_id=str(company_id),
        user_id=str(user_id or ""),
        target_id=str(proposal_id),
        details={"action": action, "status": new_status, "ok": bool(execution.get("ok"))},
    )
    return {"ok": bool(execution.get("ok")), "proposalId": proposal_id, "status": new_status, "execution": execution}


def reject_action(
    db,
    *,
    company_id: str,
    user_id: str,
    proposal_id: str,
    note: str = "",
) -> dict[str, Any]:
    _ensure_proposal_tables(db)
    row = db.execute(
        "SELECT id, status FROM ai_action_proposals WHERE id = ? AND company_id = ?",
        (str(proposal_id), str(company_id)),
    ).fetchone()
    if not row:
        return {"ok": False, "error": "proposal_not_found"}
    if str(row["status"] or "") != "pending":
        return {"ok": False, "error": "proposal_not_pending", "status": row["status"]}
    db.execute(
        """
        UPDATE ai_action_proposals
        SET status = 'rejected', decided_by = ?, decided_at = ?, result_json = ?
        WHERE id = ?
        """,
        (
            str(user_id or ""),
            _now(),
            json.dumps({"note": str(note or "")[:400]}, ensure_ascii=False),
            str(proposal_id),
        ),
    )
    db.commit()
    _audit_ai(
        "ai.action.rejected",
        f"AI action rejected: {proposal_id}",
        company_id=str(company_id),
        user_id=str(user_id or ""),
        target_id=str(proposal_id),
        details={"note": str(note or "")[:200]},
    )
    return {"ok": True, "proposalId": proposal_id, "status": "rejected"}
