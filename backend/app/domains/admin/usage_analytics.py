"""Platform usage analytics and system satisfaction surveys."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

SATISFACTION_LABELS = {
    1: "excellent",
    2: "good",
    3: "neutral",
    4: "poor",
    5: "very_poor",
}

KNOWN_FEATURES = (
    ("overview", "Übersicht / Overview"),
    ("analytics", "Nutzung & Bewertung"),
    ("inbox", "Posteingang / Inbox"),
    ("workers", "Mitarbeiter / Workers"),
    ("access", "Anwesenheit / Attendance"),
    ("mobile", "Worker-App"),
    ("operations", "Betrieb / Operations"),
    ("tools", "Tools & Geofence"),
    ("platform", "Plattform"),
    ("copilot", "Copilot"),
    ("chat", "Interner Chat"),
    ("contracts", "Verträge / Contracts"),
    ("enterprise", "Enterprise Hub"),
    ("dashboard", "Legacy Dashboard"),
    ("invoices", "Rechnungen / Invoices"),
    ("devices", "Geräte / Devices"),
    ("documents", "Dokumente / Documents"),
    ("settings", "Einstellungen / Settings"),
    ("badge", "Ausweis / Badge"),
    ("deployment-plan", "Einsatzplan"),
    ("admin-v2", "Betrieb (admin-v2)"),
    ("worker-badge", "Worker: Ausweis"),
    ("worker-attendance", "Worker: Check-in"),
    ("worker-tasks", "Worker: Aufgaben"),
    ("worker-profile", "Worker: Profil"),
    ("worker-leave", "Worker: Urlaub"),
    ("worker-timesheets", "Worker: Stunden"),
    ("worker-documents", "Worker: Dokumente"),
    ("worker-deployment", "Worker: Einsatzplan"),
    ("worker-chat", "Worker: Chat"),
    ("worker-notifications", "Worker: Mitteilungen"),
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _since_iso(days: int) -> str:
    return (_utc_now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")


def _period_days(period: str) -> int:
    return 7 if str(period or "").lower() == "week" else 1


def _scalar(db, sql: str, params: tuple) -> int:
    row = db.execute(sql, params).fetchone()
    if not row:
        return 0
    try:
        return int(row[0] or 0)
    except (TypeError, IndexError, KeyError):
        return 0


def _active_users(db, company_id: str, since: str) -> int:
    row = db.execute(
        """
        SELECT COUNT(DISTINCT actor_id) AS c FROM (
            SELECT actor_user_id AS actor_id
            FROM audit_logs
            WHERE company_id = ? AND created_at >= ? AND actor_user_id IS NOT NULL AND actor_user_id != ''
            UNION
            SELECT al.worker_id AS actor_id
            FROM access_logs al
            JOIN workers w ON w.id = al.worker_id
            WHERE w.company_id = ? AND w.deleted_at IS NULL AND al.timestamp >= ?
            UNION
            SELECT s.user_id AS actor_id
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE u.company_id = ? AND s.last_seen IS NOT NULL AND s.last_seen >= ?
            UNION
            SELECT was.worker_id AS actor_id
            FROM worker_app_sessions was
            JOIN workers w ON w.id = was.worker_id
            WHERE w.company_id = ? AND w.deleted_at IS NULL AND was.expires_at >= ?
        )
        """,
        (company_id, since, company_id, since, company_id, since, company_id, since),
    ).fetchone()
    return int((row["c"] if row else 0) or 0)


def build_usage_stats(db, company_id: str, *, period: str = "day") -> dict[str, Any]:
    days = _period_days(period)
    since = _since_iso(days)
    today_prefix = _utc_now().strftime("%Y-%m-%d")

    active_users = _active_users(db, company_id, since)
    logins = _scalar(
        db,
        """
        SELECT COUNT(*) FROM audit_logs
        WHERE company_id = ? AND created_at >= ?
          AND (event_type = 'login.success' OR event_type LIKE 'login.success%')
        """,
        (company_id, since),
    )
    attendance = _scalar(
        db,
        """
        SELECT COUNT(*) FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ? AND w.deleted_at IS NULL
          AND al.direction = 'check-in' AND al.timestamp >= ?
        """,
        (company_id, since),
    )
    contracts_created = _scalar(
        db,
        """
        SELECT COUNT(*) FROM employment_contracts
        WHERE company_id = ? AND created_at >= ?
        """,
        (company_id, since),
    )
    documents_created = _scalar(
        db,
        """
        SELECT COUNT(*) FROM worker_documents
        WHERE company_id = ? AND created_at >= ?
        """,
        (company_id, since),
    )
    messages_sent = _scalar(
        db,
        """
        SELECT COUNT(*) FROM chat_messages
        WHERE company_id = ? AND created_at >= ?
        """,
        (company_id, since),
    )
    on_site_now = _scalar(
        db,
        """
        SELECT COUNT(DISTINCT al.worker_id) FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ? AND w.deleted_at IS NULL
          AND al.timestamp >= ?
          AND al.direction = 'check-in'
          AND NOT EXISTS (
            SELECT 1 FROM access_logs al2
            WHERE al2.worker_id = al.worker_id
              AND al2.direction = 'check-out'
              AND al2.timestamp > al.timestamp
              AND al2.timestamp >= ?
          )
        """,
        (company_id, f"{today_prefix}T00:00:00", f"{today_prefix}T00:00:00"),
    )

    late_checkins = _scalar(
        db,
        """
        SELECT COUNT(*) FROM access_logs al
        JOIN workers w ON w.id = al.worker_id
        WHERE w.company_id = ? AND w.deleted_at IS NULL
          AND al.direction = 'check-in'
          AND al.checked_in_late = 1
          AND al.timestamp >= ?
        """,
        (company_id, since),
    )

    return {
        "period": "week" if days == 7 else "day",
        "days": days,
        "since": since,
        "activeUsers": active_users,
        "logins": logins,
        "attendanceCheckIns": attendance,
        "lateCheckIns": late_checkins,
        "contractsCreated": contracts_created,
        "documentsCreated": documents_created,
        "internalMessagesSent": messages_sent,
        "onSiteNow": on_site_now,
    }


def log_feature_usage(db, company_id: str, user_id: str, feature_id: str, *, source: str = "admin-v2") -> None:
    fid = str(feature_id or "").strip().lower()[:64]
    if not fid or not company_id:
        return
    now = _utc_now().isoformat().replace("+00:00", "Z")
    db.execute(
        """
        INSERT INTO feature_usage_events (id, company_id, user_id, feature_id, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (f"fue-{uuid.uuid4().hex[:12]}", company_id, user_id or "", fid, source[:32], now),
    )
    db.commit()


def build_feature_usage_insights(db, company_id: str, *, days: int = 14) -> dict[str, Any]:
    days = max(1, min(days, 90))
    since = _since_iso(days)
    rows = db.execute(
        """
        SELECT feature_id, COUNT(*) AS hits,
               COUNT(DISTINCT substr(created_at, 1, 10)) AS active_days,
               MAX(created_at) AS last_used_at
        FROM feature_usage_events
        WHERE company_id = ? AND created_at >= ?
        GROUP BY feature_id
        ORDER BY hits DESC
        """,
        (company_id, since),
    ).fetchall()

    used_ids = {str(r["feature_id"]) for r in rows}
    daily_used = [
        {
            "featureId": r["feature_id"],
            "label": _feature_label(r["feature_id"]),
            "hits": int(r["hits"] or 0),
            "activeDays": int(r["active_days"] or 0),
            "lastUsedAt": r["last_used_at"] or "",
        }
        for r in rows
        if int(r["active_days"] or 0) >= max(1, days // 3)
    ]
    unused = [
        {"featureId": fid, "label": label}
        for fid, label in KNOWN_FEATURES
        if fid not in used_ids
    ]
    low_usage = [
        {
            "featureId": r["feature_id"],
            "label": _feature_label(r["feature_id"]),
            "hits": int(r["hits"] or 0),
            "activeDays": int(r["active_days"] or 0),
        }
        for r in rows
        if int(r["active_days"] or 0) < max(1, days // 7) and int(r["hits"] or 0) <= 2
    ]

    frequent_requests = db.execute(
        """
        SELECT frequent_request, COUNT(*) AS c
        FROM system_satisfaction_surveys
        WHERE company_id = ? AND created_at >= ? AND frequent_request != ''
        GROUP BY frequent_request
        ORDER BY c DESC
        LIMIT 8
        """,
        (company_id, since),
    ).fetchall()

    confusion_notes = db.execute(
        """
        SELECT confusion_note, satisfaction_score, created_at
        FROM system_satisfaction_surveys
        WHERE company_id = ? AND created_at >= ? AND confusion_note != ''
        ORDER BY created_at DESC
        LIMIT 12
        """,
        (company_id, since),
    ).fetchall()

    return {
        "days": days,
        "since": since,
        "dailyUsed": daily_used,
        "unusedModules": unused,
        "lowUsageModules": low_usage,
        "unusedModuleAlerts": build_unused_module_alerts(db, company_id, stale_days=30),
        "frequentRequests": [
            {"text": r["frequent_request"], "count": int(r["c"] or 0)} for r in frequent_requests
        ],
        "confusionReports": [dict(r) for r in confusion_notes],
    }


def _feature_label(feature_id: str) -> str:
    for fid, label in KNOWN_FEATURES:
        if fid == feature_id:
            return label
    return feature_id


def _active_users_between(db, company_id: str, start_iso: str, end_iso: str) -> int:
    row = db.execute(
        """
        SELECT COUNT(DISTINCT actor_id) AS c FROM (
            SELECT actor_user_id AS actor_id
            FROM audit_logs
            WHERE company_id = ? AND created_at >= ? AND created_at <= ?
              AND actor_user_id IS NOT NULL AND actor_user_id != ''
            UNION
            SELECT al.worker_id AS actor_id
            FROM access_logs al
            JOIN workers w ON w.id = al.worker_id
            WHERE w.company_id = ? AND w.deleted_at IS NULL
              AND al.timestamp >= ? AND al.timestamp <= ?
            UNION
            SELECT s.user_id AS actor_id
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE u.company_id = ? AND s.last_seen IS NOT NULL
              AND s.last_seen >= ? AND s.last_seen <= ?
        )
        """,
        (
            company_id, start_iso, end_iso,
            company_id, start_iso, end_iso,
            company_id, start_iso, end_iso,
        ),
    ).fetchone()
    return int((row["c"] if row else 0) or 0)


def build_usage_trends(db, company_id: str, *, days: int = 14) -> dict[str, Any]:
    days = max(7, min(days, 90))
    daily: list[dict[str, Any]] = []
    peak = 0
    for offset in range(days - 1, -1, -1):
        day = (_utc_now() - timedelta(days=offset)).strftime("%Y-%m-%d")
        start = f"{day}T00:00:00"
        end = f"{day}T23:59:59"
        count = _active_users_between(db, company_id, start, end)
        peak = max(peak, count)
        daily.append({"date": day, "activeUsers": count})

    week_rows = db.execute(
        """
        SELECT substr(created_at, 1, 10) AS day,
               AVG(satisfaction_score) AS avg_score,
               COUNT(*) AS responses
        FROM system_satisfaction_surveys
        WHERE company_id = ? AND created_at >= ?
        GROUP BY day
        ORDER BY day ASC
        """,
        (company_id, _since_iso(days)),
    ).fetchall()

    weekly_map: dict[str, dict[str, Any]] = {}
    for r in week_rows:
        day = str(r["day"] or "")
        if len(day) < 10:
            continue
        try:
            dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            week_key = dt.strftime("%G-W%V")
        except ValueError:
            week_key = day[:7]
        bucket = weekly_map.setdefault(week_key, {"week": week_key, "scores": [], "responses": 0})
        bucket["scores"].append(float(r["avg_score"] or 0))
        bucket["responses"] += int(r["responses"] or 0)

    weekly_satisfaction = []
    for week_key in sorted(weekly_map.keys()):
        bucket = weekly_map[week_key]
        scores = bucket["scores"]
        weekly_satisfaction.append(
            {
                "week": week_key,
                "avgSatisfactionScore": round(sum(scores) / max(1, len(scores)), 2) if scores else None,
                "responses": bucket["responses"],
            }
        )

    return {
        "days": days,
        "dailyActiveUsers": daily,
        "peakActiveUsers": peak,
        "weeklySatisfaction": weekly_satisfaction[-8:],
        "scaleNote": "1 = best, 5 = worst",
    }


def build_unused_module_alerts(db, company_id: str, *, stale_days: int = 30) -> list[dict[str, Any]]:
    stale_days = max(7, min(stale_days, 180))
    since = _since_iso(stale_days)
    rows = db.execute(
        """
        SELECT feature_id, MAX(created_at) AS last_used_at, COUNT(*) AS hits
        FROM feature_usage_events
        WHERE company_id = ?
        GROUP BY feature_id
        """,
        (company_id,),
    ).fetchall()
    last_by_id = {str(r["feature_id"]): dict(r) for r in rows}

    alerts: list[dict[str, Any]] = []
    for fid, label in KNOWN_FEATURES:
        row = last_by_id.get(fid)
        if not row:
            alerts.append(
                {
                    "featureId": fid,
                    "label": label,
                    "severity": "warning",
                    "daysSinceUse": stale_days,
                    "message": f"Modul «{label}» wurde in den letzten {stale_days} Tagen nicht genutzt.",
                }
            )
            continue
        last_used = str(row.get("last_used_at") or "")
        if last_used < since:
            try:
                last_dt = datetime.fromisoformat(last_used.replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                days_ago = max(0, (_utc_now() - last_dt.astimezone(timezone.utc)).days)
            except ValueError:
                days_ago = stale_days
            alerts.append(
                {
                    "featureId": fid,
                    "label": label,
                    "severity": "info" if days_ago < stale_days + 7 else "warning",
                    "daysSinceUse": days_ago,
                    "lastUsedAt": last_used,
                    "hits": int(row.get("hits") or 0),
                    "message": f"Modul «{label}» zuletzt vor {days_ago} Tag(en) genutzt.",
                }
            )
    alerts.sort(key=lambda a: int(a.get("daysSinceUse") or 0), reverse=True)
    return alerts[:16]


def survey_pending_for_user(db, user: dict[str, Any], *, cooldown_days: int = 90) -> dict[str, Any]:
    user_id = str(user.get("id") or user.get("user_id") or "").strip()
    company_id = str(user.get("company_id") or "").strip()
    if not user_id:
        return {"pending": False, "reason": "no_user"}

    usage_days = None
    prompt_enabled = False
    invited_recently = False
    usage_required = 30
    try:
        from .survey_dispatch import (
            USAGE_DAYS_BEFORE_INVITE,
            _company_survey_prompt_enabled,
            _recent_survey_invite_for_user,
            _user_usage_age_days,
        )

        usage_required = USAGE_DAYS_BEFORE_INVITE
        usage_days = _user_usage_age_days(db, user_id, company_id)
        prompt_enabled = _company_survey_prompt_enabled(db, company_id)
        invited_recently = _recent_survey_invite_for_user(db, user_id, days=30)
        if not prompt_enabled and not invited_recently and usage_days < USAGE_DAYS_BEFORE_INVITE:
            return {
                "pending": False,
                "reason": "usage_too_short",
                "usageDays": usage_days,
                "usageDaysRequired": USAGE_DAYS_BEFORE_INVITE,
                "surveyPromptEnabled": prompt_enabled,
            }
    except Exception:
        pass

    since = _since_iso(cooldown_days)
    row = db.execute(
        """
        SELECT id, created_at FROM system_satisfaction_surveys
        WHERE user_id = ? AND created_at >= ?
        ORDER BY created_at DESC LIMIT 1
        """,
        (user_id, since),
    ).fetchone()
    if row is not None:
        payload = {
            "pending": False,
            "reason": "recent_submission",
            "lastSubmittedAt": row["created_at"] or "",
            "surveyPromptEnabled": prompt_enabled,
            "invitedRecently": invited_recently,
        }
        if usage_days is not None:
            payload["usageDays"] = usage_days
        return payload

    eligible = bool(prompt_enabled or invited_recently or usage_days is None or usage_days >= usage_required)
    payload = {
        "pending": eligible,
        "lastSubmittedAt": "",
        "surveyPromptEnabled": prompt_enabled,
        "invitedRecently": invited_recently,
    }
    if not eligible:
        payload["reason"] = "usage_too_short"
        payload["usageDaysRequired"] = usage_required
    if usage_days is not None:
        payload["usageDays"] = usage_days
    return payload


def submit_satisfaction_survey(db, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    score = int(payload.get("satisfaction_score") or payload.get("satisfactionScore") or 0)
    if score < 1 or score > 5:
        raise ValueError("invalid_satisfaction_score")

    company_id = str(user.get("company_id") or payload.get("company_id") or "").strip()
    user_id = str(user.get("id") or user.get("user_id") or "").strip()
    would_recommend = 1 if payload.get("would_recommend") in (True, 1, "yes", "ja", "true") else 0
    best_feature = str(payload.get("best_feature") or payload.get("bestFeature") or "").strip()[:500]
    frequent_request = str(payload.get("frequent_request") or payload.get("frequentRequest") or "").strip()[:500]
    confusion_note = str(payload.get("confusion_note") or payload.get("confusionNote") or "").strip()[:1000]
    time_saved = payload.get("time_saved_hours") or payload.get("timeSavedHours")
    cost_saved = payload.get("cost_saved_estimate") or payload.get("costSavedEstimate")

    try:
        time_saved_val = float(time_saved) if time_saved not in (None, "") else None
    except (TypeError, ValueError):
        time_saved_val = None
    try:
        cost_saved_val = float(cost_saved) if cost_saved not in (None, "") else None
    except (TypeError, ValueError):
        cost_saved_val = None

    now = _utc_now().isoformat().replace("+00:00", "Z")
    survey_id = f"ssv-{uuid.uuid4().hex[:12]}"
    db.execute(
        """
        INSERT INTO system_satisfaction_surveys (
            id, company_id, user_id, actor_username, actor_role,
            satisfaction_score, would_recommend, best_feature, frequent_request,
            confusion_note, time_saved_hours, cost_saved_estimate, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            survey_id,
            company_id,
            user_id,
            str(user.get("username") or "")[:120],
            str(user.get("role") or "")[:40],
            score,
            would_recommend,
            best_feature,
            frequent_request,
            confusion_note,
            time_saved_val,
            cost_saved_val,
            now,
        ),
    )
    db.commit()
    return {"ok": True, "id": survey_id}


def list_satisfaction_surveys(db, company_id: str | None = None, *, limit: int = 100) -> dict[str, Any]:
    limit = max(1, min(limit, 500))
    params: list[Any] = []
    where = ""
    if company_id:
        where = " WHERE company_id = ?"
        params.append(company_id)

    rows = db.execute(
        f"""
        SELECT id, company_id, user_id, actor_username, actor_role,
               satisfaction_score, would_recommend, best_feature, frequent_request,
               confusion_note, time_saved_hours, cost_saved_estimate, created_at
        FROM system_satisfaction_surveys
        {where}
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()

    agg_params: list[Any] = list(params)
    agg = db.execute(
        f"""
        SELECT
            COUNT(*) AS total,
            AVG(satisfaction_score) AS avg_score,
            SUM(CASE WHEN would_recommend = 1 THEN 1 ELSE 0 END) AS recommend_yes,
            AVG(time_saved_hours) AS avg_time_saved,
            AVG(cost_saved_estimate) AS avg_cost_saved
        FROM system_satisfaction_surveys
        {where}
        """,
        tuple(agg_params),
    ).fetchone()

    total = int((agg["total"] if agg else 0) or 0)
    recommend_yes = int((agg["recommend_yes"] if agg else 0) or 0)
    avg_score = float((agg["avg_score"] if agg else 0) or 0)
    avg_time = agg["avg_time_saved"] if agg else None
    avg_cost = agg["avg_cost_saved"] if agg else None

    return {
        "summary": {
            "total": total,
            "avgSatisfactionScore": round(avg_score, 2) if total else None,
            "recommendRate": round(recommend_yes / max(1, total), 3) if total else None,
            "avgTimeSavedHours": round(float(avg_time), 1) if avg_time is not None else None,
            "avgCostSavedEstimate": round(float(avg_cost), 2) if avg_cost is not None else None,
            "scaleNote": "1 = best, 5 = worst",
        },
        "surveys": [dict(r) for r in rows],
    }
