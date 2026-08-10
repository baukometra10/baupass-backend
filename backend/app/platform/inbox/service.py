"""Unified operations inbox — system, security, documents, leave."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

_log = logging.getLogger(__name__)


def _inbox_soft_fail(where: str, exc: Exception) -> None:
    _log.warning("inbox builder soft-fail at %s: %s", where, exc)

def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_local() -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:
        return datetime.now()


def _parse_hhmm(value: str) -> tuple[int, int] | None:
    raw = str(value or "").strip()
    if len(raw) >= 16 and "T" in raw:
        raw = raw[11:16]
    raw = raw.strip()
    # Accept "7:00", "07:00", "7:00:00"
    if ":" not in raw:
        return None
    parts = raw.split(":")
    try:
        hh, mm = int(parts[0]), int(parts[1] if len(parts) > 1 else 0)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except Exception:
        return None
    return None


def _missing_past_grace(worker: dict[str, Any], now_local: datetime) -> bool:
    """Grace after day/shift start — company-flexible, no hard-coded industry shifts.

    Priority: Einsatzplan shiftStart → Firmen-Arbeitsbeginn → only scheduled days
    without any configured hours (soft noon). Pure Mo–Fr fallback without company
    hours does not create inbox noise (firm runs flexible times).
    """
    w = worker or {}
    for key in ("shiftStart", "companyStart"):
        parsed = _parse_hhmm(str(w.get(key) or ""))
        if parsed:
            hh, mm = parsed
            grace = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0) + timedelta(minutes=20)
            return now_local >= grace
    reason = str(w.get("reason") or "")
    if reason == "scheduled":
        # Planned day but no times set by the company → gentle afternoon nudge.
        return (now_local.hour, now_local.minute) >= (12, 0)
    # Flexible company (no work_start_time): skip time-based missing inbox.
    return False


def _missing_inbox_eligible(worker: dict[str, Any], now_local: datetime) -> bool:
    """Whether a missing worker should appear in the employer inbox.

    Always show planned/expected absences that the Lage KPI counts — otherwise
    "Fehlt heute: 2" opens an empty Posteingang. Grace only affects severity.
    Flexible Mo–Fr fallback without company hours still stays out (no noise).
    """
    w = worker or {}
    if _parse_hhmm(str(w.get("shiftStart") or "")) or _parse_hhmm(str(w.get("companyStart") or "")):
        return True
    reason = str(w.get("reason") or "")
    if reason == "scheduled":
        return True
    # workday fallback without company hours: only after soft noon (same as grace)
    return _missing_past_grace(w, now_local)


def _acked_missing_worker_ids(db, company_id: str, work_date: str) -> set[str]:
    """Workers already acknowledged missing for this work day."""
    out: set[str] = set()
    try:
        rows = db.execute(
            """
            SELECT details FROM system_alerts
            WHERE code = 'missing_checkin_noted'
              AND (details LIKE ? OR details LIKE ?)
            ORDER BY created_at DESC
            LIMIT 200
            """,
            (f'%"{company_id}"%', f"%company_id={company_id}%"),
        ).fetchall()
        for r in rows:
            raw = r["details"] or ""
            try:
                details = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                details = {}
            if not isinstance(details, dict):
                continue
            if str(details.get("workDate") or details.get("work_date") or "")[:10] != str(work_date)[:10]:
                continue
            wid = str(details.get("workerId") or details.get("worker_id") or "").strip()
            if wid:
                out.add(wid)
    except Exception:
        return set()
    return out


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
            alert_type = str(r["alert_type"] or "").strip()
            title = str(r["title"] or "Security alert").strip() or "Security alert"
            details_obj: dict[str, Any] = {}
            try:
                import json as _json

                raw_details = r["details_json"]
                if isinstance(raw_details, dict):
                    details_obj = dict(raw_details)
                elif raw_details:
                    parsed = _json.loads(str(raw_details))
                    if isinstance(parsed, dict):
                        details_obj = parsed
            except Exception:
                details_obj = {}
            reason = str(
                details_obj.get("reasonSummary")
                or details_obj.get("reason")
                or details_obj.get("summary")
                or details_obj.get("message")
                or ""
            ).strip()
            worker_name = str(
                details_obj.get("workerName") or details_obj.get("worker_name") or ""
            ).strip()
            msg_bits = [title]
            if worker_name:
                msg_bits.append(worker_name)
            if reason and reason.lower() not in title.lower():
                msg_bits.append(reason)
            message = " · ".join(msg_bits)[:500]
            nav_action = (
                {
                    "type": "navigate",
                    "url": "/admin-v2/index.html?tab=audit",
                    "label": "Audit öffnen",
                    "tab": "audit",
                }
                if alert_type == "sensitive_attempt"
                else {"type": "navigate", "url": "/index.html", "label": "Admin Legacy"}
            )
            items.append(
                {
                    "id": f"sec:{r['id']}",
                    "source": "security",
                    "severity": r["severity"] or "medium",
                    "code": alert_type or "security_alert",
                    "title": title,
                    "message": message,
                    "companyId": row_cid,
                    "workerId": r["worker_id"],
                    "createdAt": _coerce_iso_timestamp(r["created_at"]),
                    "status": "open",
                    "details": {
                        **details_obj,
                        "workerName": worker_name or details_obj.get("workerName"),
                        "reasonSummary": reason,
                    },
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
                                        "body": (title or "Security-Hinweis")[:200],
                                    },
                                    "label": "Push an MA",
                                }
                            ]
                            if r["worker_id"]
                            else []
                        ),
                        {
                            "type": "prompt",
                            "prompt": (
                                f"Analysiere Security-Alert „{title or alert_type or 'Security'}“ "
                                f"für Mitarbeiter {r['worker_id'] or '—'}. Priorität {r['severity'] or 'medium'}. "
                                "Kurz: Risiko, nächste Schritte, Eskalation ja/nein."
                            ),
                            "label": "KI analysieren",
                            "agent": "decision",
                        },
                        nav_action,
                    ],
                }
            )
    except Exception as exc:
        _inbox_soft_fail("security_alerts", exc)

    # Open camera-watch escalations (same Security-Inbox filter)
    if cid:
        try:
            from backend.app.platform.physical_operations.camera_escalation import list_escalations

            open_esc = list(list_escalations(db, cid, limit=15, status="open") or [])
            try:
                pending = list(list_escalations(db, cid, limit=10, status="pending_second_ack") or [])
                open_esc.extend(pending)
            except Exception:
                pass
            seen_esc: set[str] = set()
            for e in open_esc:
                eid = str(e.get("id") or "").strip()
                if not eid or eid in seen_esc:
                    continue
                seen_esc.add(eid)
                cam = str(e.get("cameraName") or e.get("cameraId") or "Kamera").strip()
                status = str(e.get("status") or "open")
                href = f"/admin-v2/camera-watch.html?company_id={cid}&escalation={eid}"
                items.append(
                    {
                        "id": f"camesc:{eid}",
                        "source": "security",
                        "severity": e.get("severity") or "critical",
                        "code": "camera_escalation",
                        "title": f"Kamera-Eskalation · {cam}",
                        "message": (
                            f"Status {status}"
                            + (f" · {e.get('slaLabel')}" if e.get("slaLabel") else "")
                            + " · kein Auto-Polizei-Anruf"
                        ),
                        "companyId": cid,
                        "workerId": None,
                        "createdAt": _coerce_iso_timestamp(e.get("createdAt") or e.get("created_at")),
                        "status": "open",
                        "actions": [
                            {
                                "type": "resolve",
                                "action": "ack_camera_escalation",
                                "params": {"escalation_id": eid},
                                "label": "Ack / Security informiert",
                            },
                            {
                                "type": "navigate",
                                "url": href,
                                "label": "Kamera-Wächter öffnen",
                            },
                            {
                                "type": "prompt",
                                "prompt": (
                                    f"Analysiere Kamera-Eskalation {cam} (Status {status}). "
                                    "Assistierte Polizei nur — kein Auto-Dial. Nächste Schritte für Security?"
                                ),
                                "label": "KI analysieren",
                                "agent": "decision",
                            },
                        ],
                    }
                )
        except Exception as exc:
            _inbox_soft_fail("camera_escalations", exc)

    # System alerts — only when they belong to the selected company (or global view without company)
    try:
        cond = "" if include_resolved else "AND resolved_at IS NULL"
        params: list[Any] = []
        company_sql = ""
        if cid:
            # Prefer tenant rows so busy shared DBs don't bury company alerts under LIMIT.
            company_sql = """
              AND (
                details LIKE ?
                OR details LIKE ?
                OR details LIKE ?
              )
            """
            params.extend([f'%"{cid}"%', f"%company_id={cid}%", f"%companyId={cid}%"])
        rows = db.execute(
            f"""
            SELECT id, code, severity, message, details, created_at, resolved_at
            FROM system_alerts
            WHERE 1=1 {cond} {company_sql}
            ORDER BY created_at DESC
            LIMIT 80
            """,
            tuple(params),
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
                "outside_hours_checkin_attempt": "Anmeldung außerhalb der Arbeitszeit",
                "shift_swap_accepted": "Schichttausch",
                "repeated_late_checkin": "Wiederholte Verspätung",
                "tomorrow_attendance_forecast": "Prognose für morgen",
                "docs.review": "Dokument zur Prüfung",
                "docs.review.stale": "Dokument-Prüfung überfällig",
                "docs.published": "Dokument an Mitarbeiter",
                "autopilot.leave_queue": "Urlaub offen (Hinweis)",
                "autopilot.docs_review": "Docs in Prüfung (Hinweis)",
                "autopilot.missing_expected": "Fehlende MA (Hinweis)",
                "autopilot.security_open": "Security offen (Hinweis)",
                "autopilot.ops_digest": "Tages-Digest (Hinweis)",
                "map.zone_crowd": "Karten-Alarm: Zonen-Ansammlung",
                "map.off_site_dwell": "Karten-Alarm: Länger außerhalb",
                "map.stale_presence": "Karten-Hinweis: Kein frisches GPS",
                "map.wrong_zone_dwell": "Karten-Alarm: Ungewöhnliche Zone",
            }
            if code.startswith("sensitive_attempt"):
                title_map[code] = "Sensibler Zugriff blockiert"
            details_obj = {}
            raw_details = r["details"] or ""
            if isinstance(raw_details, str) and raw_details.strip():
                try:
                    parsed = json.loads(raw_details)
                    if isinstance(parsed, dict):
                        details_obj = parsed
                except Exception:
                    details_obj = {}
            # Live-enrich late evidence if missing (older alerts).
            if code == "repeated_late_checkin" and details_obj.get("workerId"):
                if not details_obj.get("lateEvents"):
                    try:
                        from backend.app.platform.workforce.late_streak import (
                            list_late_checkin_evidence,
                            summarize_late_evidence,
                        )

                        ev = list_late_checkin_evidence(db, str(details_obj["workerId"]), limit=8)
                        details_obj["lateEvents"] = ev
                        details_obj["reasonSummary"] = summarize_late_evidence(ev)
                    except Exception as exc:
                        _inbox_soft_fail("late_evidence_enrich", exc)
            worker_id = str(details_obj.get("workerId") or "").strip()
            ai_prompt = ""
            if code == "repeated_late_checkin" and worker_id:
                ai_prompt = (
                    f"Analysiere die wiederholte Verspätung von {details_obj.get('workerName') or worker_id} "
                    f"(Streak {details_obj.get('streak') or '?'}). Gründe/Zeiten: "
                    f"{details_obj.get('reasonSummary') or details_obj.get('lateEvents')}. "
                    "Gib eine kurze Empfehlung für den Arbeitgeber (Gespräch, Schichtanpassung, Eskalation)."
                )
            elif code == "outside_hours_checkin_attempt" and worker_id:
                ai_prompt = (
                    f"Analysiere Anmeldung außerhalb der Arbeitszeit von {details_obj.get('workerName') or worker_id}. "
                    f"Kanal={details_obj.get('channel')}, Tor={details_obj.get('gate')}, "
                    f"Fenster={details_obj.get('shiftStart')}-{details_obj.get('shiftEnd')}. Empfehlung?"
                )
            docs_nav = []
            if code in {"docs.review", "docs.review.stale", "docs.published", "autopilot.docs_review"}:
                doc_id = str(details_obj.get("documentId") or details_obj.get("editorDocumentId") or "").strip()
                company_for_docs = str(details_obj.get("companyId") or cid or "").strip()
                if doc_id:
                    q = f"id={doc_id}"
                    if company_for_docs:
                        q += f"&company_id={company_for_docs}"
                    docs_nav = [
                        {
                            "type": "navigate",
                            "url": f"/admin-v2/docs.html?{q}",
                            "label": "Dokument prüfen" if "review" in code else "Im Editor öffnen",
                        }
                    ]
                elif code == "autopilot.docs_review" and company_for_docs:
                    docs_nav = [
                        {
                            "type": "navigate",
                            "url": f"/admin-v2/docs.html?company_id={company_for_docs}&status=in_review",
                            "label": "Docs in Prüfung",
                        },
                        {
                            "type": "navigate",
                            "url": f"/admin-v2/index.html?company_id={company_for_docs}&tab=inbox&source=document",
                            "label": "Dokument-Inbox",
                        },
                    ]
            leave_nav = []
            if code == "autopilot.leave_queue":
                company_for_leave = str(details_obj.get("companyId") or cid or "").strip()
                leave_nav = [
                    {
                        "type": "navigate",
                        "url": f"/admin-v2/index.html?company_id={company_for_leave}&tab=inbox&source=leave",
                        "label": "Urlaub-Inbox",
                    }
                ]
            missing_nav = []
            if code == "autopilot.missing_expected":
                company_for_miss = str(details_obj.get("companyId") or cid or "").strip()
                missing_nav = [
                    {
                        "type": "navigate",
                        "url": f"/admin-v2/index.html?company_id={company_for_miss}&tab=inbox&source=attendance",
                        "label": "Anwesenheit-Inbox",
                    },
                    {
                        "type": "navigate",
                        "url": f"/ops-live-map.html?company_id={company_for_miss}",
                        "label": "Live-Karte",
                    },
                ]
            security_hint_nav = []
            if code == "autopilot.security_open":
                company_for_sec = str(details_obj.get("companyId") or cid or "").strip()
                security_hint_nav = [
                    {
                        "type": "navigate",
                        "url": f"/admin-v2/index.html?company_id={company_for_sec}&tab=inbox&source=security",
                        "label": "Security-Inbox",
                    },
                    {
                        "type": "navigate",
                        "url": f"/admin-v2/camera-watch.html?company_id={company_for_sec}",
                        "label": "Kamera-Wächter",
                    },
                ]
            actions = [
                {"type": "ack", "action": "ack_system_alert", "params": {"alert_id": r["id"]}},
                *docs_nav,
                *leave_nav,
                *missing_nav,
                *security_hint_nav,
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
                *(
                    [
                        {
                            "type": "navigate",
                            "url": "/admin-v2/index.html?tab=audit",
                            "label": "Audit öffnen",
                            "tab": "audit",
                        }
                    ]
                    if code.startswith("sensitive_attempt")
                    else []
                ),
            ]
            if ai_prompt:
                actions.append(
                    {
                        "type": "prompt",
                        "prompt": ai_prompt,
                        "label": "KI analysieren",
                        "agent": "decision",
                    }
                )
            actions.append({"type": "open", "label": "Öffnen"})
            items.append(
                {
                    "id": f"sys:{r['id']}",
                    "source": "system",
                    "severity": r["severity"] or "info",
                    "code": code,
                    "title": title_map.get(code, code or "system"),
                    "message": r["message"] or "",
                    "details": details_obj,
                    "companyId": cid or details_obj.get("companyId") or None,
                    "workerId": worker_id or None,
                    "createdAt": _coerce_iso_timestamp(r["created_at"]),
                    "status": "resolved" if r["resolved_at"] else "open",
                    "autoAckOnOpen": bool(
                        details_obj.get("autoAckOnOpen")
                        or code in {"repeated_late_checkin", "outside_hours_checkin_attempt", "tomorrow_attendance_forecast"}
                    ),
                    "actions": actions,
                }
            )
    except Exception as exc:
        _inbox_soft_fail("system_alerts", exc)

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
                    worker_name = str(dec.get("workerName") or "Mitarbeiter").strip() or "Mitarbeiter"
                    work_date = str(dec.get("workDate") or "").strip()
                    msg = f"{worker_name} · {work_date} · {loc}"
                    if reason:
                        msg += f" · Grund: {reason}"
                    items.append(
                        {
                            "id": f"depdecl:{key}",
                            "source": "deployment",
                            "severity": "high",
                            "code": "deployment_worker_declined",
                            "title": "Einsatz abgelehnt",
                            "message": msg[:500],
                            "companyId": cid,
                            "workerId": dec.get("workerId"),
                            "createdAt": _coerce_iso_timestamp(dec.get("respondedAt")) or _now_iso(),
                            "status": "open",
                            "details": {
                                "workerName": worker_name,
                                "workDate": work_date,
                                "location": loc if loc != "—" else "",
                                "reason": reason,
                                "reasonSummary": reason,
                            },
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
        except Exception as exc:
            _inbox_soft_fail("deployment_declines", exc)

    # Documents expiring in 14 days (company scoped)
    if cid:
        try:
            from backend.app.platform.physical_operations._common import calendar_day_offset, today_prefix

            horizon = calendar_day_offset(14)
            today = today_prefix()
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
        except Exception as exc:
            _inbox_soft_fail("document_expiry", exc)

        # Editor documents waiting for review (live status, not only system alerts)
        try:
            try:
                from backend.app.domains.docs.repository import EditorDocsRepository

                EditorDocsRepository().ensure_schema(db)
            except Exception:
                pass
            rows = db.execute(
                """
                SELECT id, title, mode, worker_id, updated_at, created_at
                FROM editor_documents
                WHERE company_id = ?
                  AND status = 'in_review'
                ORDER BY datetime(COALESCE(updated_at, created_at)) ASC
                LIMIT 30
                """,
                (cid,),
            ).fetchall()
            for r in rows:
                did = str(r["id"] or "").strip()
                if not did:
                    continue
                title = str(r["title"] or "Dokument").strip() or "Dokument"
                mode = str(r["mode"] or "general")
                items.append(
                    {
                        "id": f"edoc:{did}",
                        "source": "document",
                        "severity": "medium",
                        "code": "docs_in_review",
                        "title": f"Prüfung · {title}",
                        "message": (
                            f"Editor-Dokument wartet auf Freigabe (Modus: {mode}). "
                            "Im Docs-Editor prüfen — kein Auto-Approve."
                        ),
                        "companyId": cid,
                        "workerId": str(r["worker_id"] or "").strip() or None,
                        "createdAt": _coerce_iso_timestamp(r["updated_at"])
                        or _coerce_iso_timestamp(r["created_at"])
                        or _now_iso(),
                        "status": "open",
                        "actions": [
                            {
                                "type": "navigate",
                                "url": f"/admin-v2/docs.html?company_id={cid}&id={did}&status=in_review",
                                "label": "Dokument prüfen",
                            },
                            {
                                "type": "navigate",
                                "url": f"/admin-v2/docs.html?company_id={cid}&status=in_review",
                                "label": "Alle in Prüfung",
                            },
                        ],
                    }
                )
        except Exception as exc:
            _inbox_soft_fail("editor_docs_review", exc)

        # Pending leave requests
        try:
            rows = db.execute(
                """
                SELECT lr.id, lr.worker_id, lr.type, lr.start_date, lr.end_date, lr.status,
                       lr.note, lr.created_at, w.first_name, w.last_name
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
                note = str(r["note"] or "").strip()
                msg = f"{name}: {r['type']} {r['start_date']} – {r['end_date']}"
                if note:
                    msg += f" · Grund: {note}"
                items.append(
                    {
                        "id": f"leave:{r['id']}",
                        "source": "leave",
                        "severity": "medium",
                        "code": "leave_request_pending",
                        "title": "Urlaubsantrag offen",
                        "message": msg[:500],
                        "companyId": cid,
                        "workerId": r["worker_id"],
                        "createdAt": _coerce_iso_timestamp(r["created_at"]) or _now_iso(),
                        "status": "open",
                        "details": {
                            "workerName": name,
                            "leaveType": str(r["type"] or "").strip(),
                            "startDate": str(r["start_date"] or "").strip(),
                            "endDate": str(r["end_date"] or "").strip(),
                            "note": note,
                            "reasonSummary": note,
                        },
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
                            {
                                "type": "prompt",
                                "prompt": (
                                    f"Prüfe Urlaubsantrag von {name}: {r['type']} "
                                    f"{r['start_date']}–{r['end_date']}. Empfehlung genehmigen/ablehnen?"
                                ),
                                "label": "KI prüfen",
                                "agent": "decision",
                            },
                        ],
                    }
                )
        except Exception as exc:
            _inbox_soft_fail("leave_requests", exc)

        # Missing expected check-ins (after morning / shift grace) — Absenz-Welle
        try:
            from backend.app.platform.physical_operations.daily_brief import build_attendance_brief

            att = build_attendance_brief(db, cid) or {}
            today = str(att.get("date") or "")
            missing = list(att.get("missingWorkers") or [])
            if today and missing:
                acked = _acked_missing_worker_ids(db, cid, today)
                now_local = _now_local()
                for w in missing[:40]:
                    wid = str(w.get("workerId") or "").strip()
                    if not wid or wid in acked:
                        continue
                    if not _missing_inbox_eligible(w, now_local):
                        continue
                    past_grace = _missing_past_grace(w, now_local)
                    name = str(w.get("name") or wid).strip()
                    loc = str(w.get("location") or "").strip()
                    shift_s = str(w.get("shiftStart") or w.get("companyStart") or "").strip()
                    shift_e = str(w.get("shiftEnd") or w.get("companyEnd") or "").strip()
                    reason = str(w.get("reason") or "workday")
                    shift_bit = f" · Schicht {shift_s}–{shift_e}" if shift_s and shift_e else ""
                    loc_bit = f" · {loc}" if loc else ""
                    if past_grace:
                        sev = "high" if reason == "scheduled" and shift_s else "medium"
                        msg = (
                            f"Erwartet, noch kein Check-in{loc_bit}{shift_bit}. "
                            "Bitte prüfen oder im Chat nachfragen."
                        )
                    else:
                        sev = "info"
                        msg = (
                            f"Noch nicht eingecheckt{loc_bit}{shift_bit}. "
                            "Noch im Toleranzfenster — erscheint bereits im Posteingang."
                        )
                    items.append(
                        {
                            "id": f"miss:{today}:{wid}",
                            "source": "attendance",
                            "severity": sev,
                            "code": "missing_checkin",
                            "title": f"Fehlt heute · {name}",
                            "message": msg,
                            "companyId": cid,
                            "workerId": wid,
                            "createdAt": f"{today}T08:00:00Z",
                            "status": "open",
                            "details": {
                                "workerName": name,
                                "location": loc,
                                "shiftStart": shift_s,
                                "shiftEnd": shift_e,
                                "workDate": today,
                                "pastGrace": past_grace,
                            },
                            "actions": [
                                {
                                    "type": "resolve",
                                    "action": "ack_missing_checkin",
                                    "params": {"worker_id": wid, "work_date": today},
                                    "label": "Kenntnis genommen",
                                },
                                {
                                    "type": "navigate",
                                    "url": f"/admin-v2/chat.html?company_id={cid}&worker_id={wid}",
                                    "label": "Chat öffnen",
                                },
                                {
                                    "type": "navigate",
                                    "url": f"/admin-v2/index.html?company_id={cid}&tab=access",
                                    "label": "Anwesenheit",
                                    "tab": "access",
                                },
                                {
                                    "type": "execute",
                                    "action": "notify_worker",
                                    "params": {
                                        "worker_id": wid,
                                        "title": "SUPPIX Anwesenheit",
                                        "body": "Bitte einchecken bzw. Abwesenheit melden.",
                                        "tag": "missing-checkin",
                                    },
                                    "label": "Push an MA",
                                },
                            ],
                        }
                    )
        except Exception as exc:
            _inbox_soft_fail("missing_checkins", exc)

        # Chat / voice: missed inbound + callback requests
        try:
            from backend.app.platform.physical_operations.daily_brief import build_chat_brief

            chat = build_chat_brief(db, cid) or {}
            for it in list(chat.get("items") or [])[:25]:
                call_id = str(it.get("id") or "").strip()
                wid = str(it.get("workerId") or "").strip()
                if not call_id:
                    continue
                kind = str(it.get("kind") or "missed_call")
                is_cb = kind == "callback_requested"
                item_id = f"vcallcb:{call_id}" if is_cb else f"vcall:{call_id}"
                name = str(it.get("workerName") or wid or "Mitarbeiter").strip()
                status = str(it.get("status") or "")
                if is_cb:
                    title = f"Rückruf · {name}"
                    message = "Mitarbeiter hat einen Rückruf angefordert — bitte im Chat zurückrufen."
                    sev = "high"
                    code = "voice_callback_requested"
                else:
                    title = f"Verpasster Anruf · {name}" if status != "declined" else f"Anruf abgelehnt · {name}"
                    message = (
                        "Eingehender Anruf nicht angenommen. Kenntnisnahme in der Inbox — Rückruf über Chat."
                    )
                    sev = "high" if status == "missed" else "medium"
                    code = "voice_missed_call"
                items.append(
                    {
                        "id": item_id,
                        "source": "chat",
                        "severity": sev,
                        "code": code,
                        "title": title,
                        "message": message,
                        "companyId": cid,
                        "workerId": wid,
                        "createdAt": str(it.get("createdAt") or _now_iso()),
                        "status": "open",
                        "actions": [
                            {
                                "type": "resolve",
                                "action": "ack_voice_call",
                                "params": {"call_id": call_id},
                                "label": "Kenntnis genommen",
                            },
                            {
                                "type": "navigate",
                                "url": f"/admin-v2/chat.html?company_id={cid}&worker_id={wid}",
                                "label": "Chat / Zurückrufen",
                            },
                        ],
                    }
                )
        except Exception as exc:
            _inbox_soft_fail("voice_calls", exc)

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

    # Sector vocabulary (e.g. security: Einsatzkräfte / Objekt / Kontrollpunkt)
    if cid:
        try:
            from backend.app.platform.ai.sector_copy import apply_sector_to_inbox_items

            items = apply_sector_to_inbox_items(db, cid, items, lang="de")
        except Exception as exc:
            _inbox_soft_fail("sector_copy", exc)

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

    if item_id.startswith("camesc:"):
        escalation_id = item_id[7:]
        if not company_id or not escalation_id:
            return {"ok": False, "error": "company_required"}
        try:
            from backend.app.platform.physical_operations.camera_escalation import acknowledge_escalation

            result = acknowledge_escalation(
                db,
                str(company_id),
                escalation_id,
                actor_user_id=str(user_id or ""),
                mark_security_notified=True,
            )
        except ValueError as exc:
            return {"ok": False, "error": str(exc) or "ack_failed"}
        except Exception as exc:
            return {"ok": False, "error": "ack_failed", "hint": str(exc)}
        if not result:
            return {"ok": False, "error": "not_found"}
        from .events import notify_inbox_changed

        notify_inbox_changed(company_id, source="camera_escalation_ack")
        return {
            "ok": True,
            "id": item_id,
            "status": str(result.get("status") or "acknowledged"),
            "autoDial": False,
            "escalation": result,
        }

    if item_id.startswith("sys:"):
        alert_id = item_id[4:]
        row = db.execute(
            "SELECT id, details, resolved_at FROM system_alerts WHERE id = ?",
            (alert_id,),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "not_found"}
        details_obj: dict[str, Any] = {}
        raw_details = row["details"] or ""
        if isinstance(raw_details, str) and raw_details.strip():
            try:
                parsed = json.loads(raw_details)
                if isinstance(parsed, dict):
                    details_obj = parsed
            except Exception:
                details_obj = {}
        if company_id:
            cid = str(company_id)
            owned = (
                cid in raw_details
                or str(details_obj.get("companyId") or "") == cid
                or str(details_obj.get("company_id") or "") == cid
            )
            if not owned:
                return {"ok": False, "error": "forbidden"}
        if row["resolved_at"]:
            return {"ok": True, "id": item_id, "status": "acknowledged", "alreadyResolved": True}
        details_obj["acknowledgedAt"] = _now_iso()
        details_obj["acknowledgedBy"] = str(user_id or "")
        details_obj["autoAckOnOpen"] = True
        db.execute(
            "UPDATE system_alerts SET resolved_at = ?, details = ? WHERE id = ? AND resolved_at IS NULL",
            (_now_iso(), json.dumps(details_obj, ensure_ascii=False), alert_id),
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

    if item_id.startswith("miss:"):
        # miss:{YYYY-MM-DD}:{workerId}
        parts = item_id.split(":", 2)
        if len(parts) != 3 or not company_id:
            return {"ok": False, "error": "invalid_missing_id"}
        work_date = parts[1].strip()
        worker_id = parts[2].strip()
        if not work_date or not worker_id:
            return {"ok": False, "error": "invalid_missing_id"}
        # Tenant check
        row = db.execute(
            "SELECT id FROM workers WHERE id = ? AND company_id = ? AND COALESCE(deleted_at, '') = ''",
            (worker_id, company_id),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "not_found"}
        if worker_id in _acked_missing_worker_ids(db, str(company_id), work_date):
            return {"ok": True, "id": item_id, "status": "acknowledged", "alreadyResolved": True}
        alert_id = f"missnote-{work_date}-{worker_id}"[:80]
        details = {
            "companyId": str(company_id),
            "workerId": worker_id,
            "workDate": work_date,
            "acknowledgedAt": _now_iso(),
            "acknowledgedBy": str(user_id or ""),
            "note": "missing_checkin_noted",
        }
        try:
            db.execute(
                """
                INSERT INTO system_alerts (id, code, severity, message, details, created_at, resolved_at)
                VALUES (?, 'missing_checkin_noted', 'info', ?, ?, ?, ?)
                """,
                (
                    alert_id,
                    f"Fehlende Anwesenheit zur Kenntnis genommen ({worker_id})",
                    json.dumps(details, ensure_ascii=False),
                    _now_iso(),
                    _now_iso(),
                ),
            )
        except Exception:
            # id collision / schema variance — update if exists
            try:
                db.execute(
                    """
                    UPDATE system_alerts
                    SET resolved_at = ?, details = ?, message = ?
                    WHERE id = ? OR (code = 'missing_checkin_noted' AND details LIKE ? AND details LIKE ?)
                    """,
                    (
                        _now_iso(),
                        json.dumps(details, ensure_ascii=False),
                        f"Fehlende Anwesenheit zur Kenntnis genommen ({worker_id})",
                        alert_id,
                        f'%"{worker_id}"%',
                        f'%"{work_date}"%',
                    ),
                )
            except Exception as exc:
                return {"ok": False, "error": "ack_failed", "hint": str(exc)}
        db.commit()
        from .events import notify_inbox_changed

        notify_inbox_changed(company_id, source="missing_checkin_ack")
        return {"ok": True, "id": item_id, "status": "acknowledged", "autoDial": False}

    if item_id.startswith("vcall:") or item_id.startswith("vcallcb:"):
        # vcall:{callId} | vcallcb:{callId}
        prefix = "vcallcb:" if item_id.startswith("vcallcb:") else "vcall:"
        call_id = item_id[len(prefix) :].strip()
        if not company_id or not call_id:
            return {"ok": False, "error": "invalid_voice_call_id"}
        row = db.execute(
            """
            SELECT id, company_id, worker_id FROM chat_voice_calls
            WHERE id = ? AND company_id = ?
            """,
            (call_id, company_id),
        ).fetchone()
        # Callback may reference a call that still exists; if not found, allow ack by id only
        worker_id = str(row["worker_id"] if row else "") if row else ""
        if row is None:
            # Still permit ack when only chat log exists (callback without call row)
            try:
                msg = db.execute(
                    """
                    SELECT worker_id FROM chat_messages
                    WHERE company_id = ? AND body LIKE ?
                    ORDER BY datetime(created_at) DESC LIMIT 1
                    """,
                    (company_id, f"%callId={call_id}%"),
                ).fetchone()
                if msg:
                    worker_id = str(msg["worker_id"] or "")
            except Exception:
                pass
            if not worker_id:
                return {"ok": False, "error": "not_found"}
        from backend.app.platform.physical_operations.daily_brief import _acked_voice_call_ids

        if call_id in _acked_voice_call_ids(db, str(company_id)):
            return {"ok": True, "id": item_id, "status": "acknowledged", "alreadyResolved": True}
        alert_id = f"vcallnote-{call_id}"[:80]
        details = {
            "companyId": str(company_id),
            "workerId": worker_id,
            "callId": call_id,
            "acknowledgedAt": _now_iso(),
            "acknowledgedBy": str(user_id or ""),
            "note": "voice_call_noted",
            "kind": "callback" if prefix == "vcallcb:" else "missed",
        }
        try:
            db.execute(
                """
                INSERT INTO system_alerts (id, code, severity, message, details, created_at, resolved_at)
                VALUES (?, 'voice_call_noted', 'info', ?, ?, ?, ?)
                """,
                (
                    alert_id,
                    f"Anruf zur Kenntnis genommen ({call_id})",
                    json.dumps(details, ensure_ascii=False),
                    _now_iso(),
                    _now_iso(),
                ),
            )
        except Exception:
            try:
                db.execute(
                    """
                    UPDATE system_alerts
                    SET resolved_at = ?, details = ?, message = ?
                    WHERE id = ? OR (code = 'voice_call_noted' AND details LIKE ?)
                    """,
                    (
                        _now_iso(),
                        json.dumps(details, ensure_ascii=False),
                        f"Anruf zur Kenntnis genommen ({call_id})",
                        alert_id,
                        f'%"{call_id}"%',
                    ),
                )
            except Exception as exc:
                return {"ok": False, "error": "ack_failed", "hint": str(exc)}
        db.commit()
        from .events import notify_inbox_changed

        notify_inbox_changed(company_id, source="voice_call_ack")
        return {"ok": True, "id": item_id, "status": "acknowledged", "autoDial": False}

    return {"ok": False, "error": "action_not_supported", "hint": "Use linked admin screens for documents and leave."}
