"""Security monitoring and safe countermeasures for Platform Guardian."""
from __future__ import annotations

import os
import re
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

_last_security_alert_at: float = 0.0


def security_guard_enabled() -> bool:
    return os.getenv("BAUPASS_GUARDIAN_SECURITY", "1").strip().lower() not in {"0", "false", "no"}


def security_remediation_enabled() -> bool:
    return os.getenv("BAUPASS_GUARDIAN_SECURITY_REMEDIATION", "1").strip().lower() not in {"0", "false", "no"}


def login_spike_threshold_15m() -> int:
    return max(5, int(os.getenv("BAUPASS_GUARDIAN_LOGIN_SPIKE_THRESHOLD", "15")))


def login_spike_threshold_24h() -> int:
    return max(10, int(os.getenv("BAUPASS_GUARDIAN_LOGIN_DAILY_THRESHOLD", "50")))


def security_alert_cooldown_seconds() -> int:
    return max(60, int(os.getenv("BAUPASS_GUARDIAN_SECURITY_ALERT_COOLDOWN_SECONDS", "600")))


def ip_ban_threshold() -> int:
    return max(3, int(os.getenv("BAUPASS_GUARDIAN_IP_BAN_THRESHOLD", "8")))


def ip_ban_hours() -> int:
    return max(1, int(os.getenv("BAUPASS_GUARDIAN_IP_BAN_HOURS", "2")))


def _failed_login_ips(db, *, minutes: int = 15) -> dict[str, int]:
    try:
        rows = db.execute(
            """
            SELECT message FROM audit_logs
            WHERE event_type = 'login.failed'
              AND created_at >= datetime('now', ?)
            """,
            (f"-{max(1, minutes)} minutes",),
        ).fetchall()
    except Exception:
        return {}
    counts: Counter[str] = Counter()
    pattern = re.compile(r"ip:([^\s\)]+)", re.I)
    for row in rows:
        match = pattern.search(str(row["message"] or ""))
        if not match:
            continue
        ip = match.group(1).strip()
        if ip and ip not in {"local", "unknown"}:
            counts[ip] += 1
    return dict(counts)


def ban_abusive_ips(db, ip_counts: dict[str, int]) -> dict[str, Any]:
    threshold = ip_ban_threshold()
    hours = ip_ban_hours()
    banned: list[str] = []
    skipped = 0
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%fZ")
    banned_at = now.strftime("%Y-%m-%dT%H:%M:%fZ")
    for ip, count in ip_counts.items():
        if count < threshold:
            continue
        try:
            existing = db.execute(
                """
                SELECT id FROM rate_limit_bans
                WHERE ip_address = ? AND lifted_at IS NULL AND expires_at > ?
                LIMIT 1
                """,
                (ip, banned_at),
            ).fetchone()
            if existing:
                skipped += 1
                continue
            db.execute(
                """
                INSERT INTO rate_limit_bans (id, ip_address, reason, banned_at, expires_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"ban-{uuid.uuid4().hex[:12]}",
                    ip,
                    f"guardian_login_spike ({count} failures/{threshold}+)",
                    banned_at,
                    expires,
                    "platform_guardian",
                ),
            )
            banned.append(ip)
        except Exception:
            skipped += 1
    if banned:
        db.commit()
    return {
        "id": "ban_abusive_ips",
        "ok": True,
        "banned": banned,
        "skipped": skipped,
        "threshold": threshold,
    }


def is_ip_banned(db, ip: str) -> bool:
    ip = (ip or "").strip()
    if not ip or ip in {"local", "unknown"}:
        return False
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%fZ")
        row = db.execute(
            """
            SELECT id FROM rate_limit_bans
            WHERE ip_address = ? AND lifted_at IS NULL AND expires_at > ?
            LIMIT 1
            """,
            (ip, now),
        ).fetchone()
        return row is not None
    except Exception:
        return False


def reset_security_state_for_tests() -> None:
    global _last_security_alert_at
    _last_security_alert_at = 0.0


def _count_failed_logins(db, *, minutes: int) -> int:
    try:
        row = db.execute(
            """
            SELECT COUNT(*) AS c FROM audit_logs
            WHERE event_type = 'login.failed'
              AND created_at >= datetime('now', ?)
            """,
            (f"-{max(1, minutes)} minutes",),
        ).fetchone()
        return int((row["c"] if row else 0) or 0)
    except Exception:
        return 0


def _active_login_locks() -> int:
    try:
        from backend.server import failed_login_attempts, utc_now

        now = utc_now()
        active = 0
        for state in list(failed_login_attempts.values()):
            locked_until = state.get("locked_until")
            if locked_until and locked_until > now:
                active += 1
        return active
    except Exception:
        return 0


def clear_expired_login_locks() -> dict[str, Any]:
    try:
        from backend.server import failed_login_attempts, utc_now

        now = utc_now()
        cleared = 0
        for key, state in list(failed_login_attempts.items()):
            locked_until = state.get("locked_until")
            if locked_until and locked_until <= now:
                failed_login_attempts.pop(key, None)
                cleared += 1
        return {"id": "clear_expired_login_locks", "ok": True, "cleared": cleared}
    except Exception as exc:
        return {"id": "clear_expired_login_locks", "ok": False, "error": str(exc)[:200]}


def scan_security(db) -> dict[str, Any]:
    if not security_guard_enabled():
        return {"enabled": False, "elevated": False, "severity": "ok"}

    failed_15m = _count_failed_logins(db, minutes=15)
    failed_24h = _count_failed_logins(db, minutes=24 * 60)
    active_locks = _active_login_locks()
    threshold_15m = login_spike_threshold_15m()
    threshold_24h = login_spike_threshold_24h()

    spike_15m = failed_15m >= threshold_15m
    spike_24h = failed_24h >= threshold_24h
    elevated = spike_15m or spike_24h
    if spike_15m and failed_15m >= threshold_15m * 2:
        severity = "critical"
    elif elevated:
        severity = "warning"
    else:
        severity = "ok"

    fixes: list[dict[str, Any]] = []
    suspicious_ips: dict[str, int] = {}
    if security_remediation_enabled():
        fixes.append(clear_expired_login_locks())
        if elevated:
            suspicious_ips = _failed_login_ips(db, minutes=15)
            fixes.append(ban_abusive_ips(db, suspicious_ips))

    return {
        "enabled": True,
        "failedLogins15m": failed_15m,
        "failedLogins24h": failed_24h,
        "activeLoginLocks": active_locks,
        "threshold15m": threshold_15m,
        "threshold24h": threshold_24h,
        "elevated": elevated,
        "severity": severity,
        "suspiciousIps": suspicious_ips,
        "fixes": fixes,
    }


def maybe_raise_security_alert(db, security: dict[str, Any]) -> dict[str, Any]:
    global _last_security_alert_at
    if not security.get("enabled") or not security.get("elevated"):
        return {"sent": 0, "skipped": "not_elevated"}

    now = time.time()
    if now - _last_security_alert_at < security_alert_cooldown_seconds():
        return {"sent": 0, "skipped": "cooldown"}

    severity = str(security.get("severity") or "warning")
    message = (
        f"Guardian Security: {failed_summary(security)} "
        f"({security.get('activeLoginLocks', 0)} aktive Login-Sperren)"
    )
    try:
        from backend.server import create_system_alert

        create_system_alert(
            db,
            code="guardian_login_spike",
            severity="critical" if severity == "critical" else "warning",
            message=message,
            details=security,
            dedup_minutes=max(5, security_alert_cooldown_seconds() // 60),
        )
    except Exception:
        pass

    notify = maybe_notify_security(security)
    if notify.get("sent"):
        _last_security_alert_at = now
    return notify


def failed_summary(security: dict[str, Any]) -> str:
    return (
        f"{security.get('failedLogins15m', 0)} Fehl-Logins/15min, "
        f"{security.get('failedLogins24h', 0)} Fehl-Logins/24h"
    )


def maybe_notify_security(security: dict[str, Any]) -> dict[str, Any]:
    from .notify import guardian_webhook_urls

    urls = guardian_webhook_urls()
    if not urls:
        return {"sent": 0, "skipped": "no_webhook"}
    if not security.get("elevated"):
        return {"sent": 0, "skipped": "not_elevated"}

    from backend.app.platform.ai.notifications import send_webhook_notification

    severity = str(security.get("severity") or "warning").upper()
    text = (
        f"*Login-Anomalie ({severity})*\n"
        f"Fehl-Logins 15 Min: {security.get('failedLogins15m', 0)} "
        f"(Schwelle {security.get('threshold15m', 0)})\n"
        f"Fehl-Logins 24 h: {security.get('failedLogins24h', 0)} "
        f"(Schwelle {security.get('threshold24h', 0)})\n"
        f"Aktive Login-Sperren: {security.get('activeLoginLocks', 0)}"
    )
    sent = 0
    for url in urls:
        ok, _ = send_webhook_notification(url, text, title="WorkPass Security Guardian")
        if ok:
            sent += 1
    return {"sent": sent, "total": len(urls), "severity": severity}
