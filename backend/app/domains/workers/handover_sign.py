"""Remote compliance signature (ID handover) via token link."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.server import (
    get_public_base_url,
    log_audit,
    now_iso,
    sanitize_compliance_signature_data,
)


def _parse_expires(expires_at: str) -> datetime | None:
    raw = str(expires_at or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _session_expired(session: dict[str, Any]) -> bool:
    expires = _parse_expires(str(session.get("expires_at") or ""))
    if not expires:
        return True
    return datetime.now(timezone.utc) >= expires


class WorkerHandoverSignService:
    def __init__(self, db):
        self.db = db

    def expire_pending_sessions(self, worker_id: str, company_id: str) -> None:
        self.db.execute(
            """
            UPDATE worker_handover_sign_sessions
            SET status = 'expired'
            WHERE worker_id = ? AND company_id = ? AND status = 'pending'
            """,
            (worker_id, company_id),
        )

    def create_sign_invite(
        self,
        worker_id: str,
        company_id: str,
        *,
        actor_user_id: str,
        expires_days: int = 7,
        renew: bool = False,
    ) -> dict[str, Any]:
        worker = self.db.execute(
            "SELECT * FROM workers WHERE id = ? AND company_id = ? AND deleted_at IS NULL",
            (worker_id, company_id),
        ).fetchone()
        if not worker:
            raise ValueError("worker_not_found")
        if str(worker["worker_type"] or "worker").strip().lower() != "worker":
            raise ValueError("visitor_not_supported")
        if str(worker["compliance_signature_data"] or "").strip():
            raise ValueError("signature_already_present")

        if renew:
            self.expire_pending_sessions(worker_id, company_id)

        token = secrets.token_urlsafe(32)
        session_id = str(uuid.uuid4())
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=max(1, min(expires_days, 30)))
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        created_at = now_iso()
        self.db.execute(
            """
            INSERT INTO worker_handover_sign_sessions (
                id, worker_id, company_id, token, status, expires_at, created_by_user_id, created_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (session_id, worker_id, company_id, token, expires_at, actor_user_id, created_at),
        )
        log_audit(
            "worker.handover_sign_link.created",
            f"Handover-Signatur-Link fuer Mitarbeiter {worker_id} erstellt",
            target_type="worker",
            target_id=worker_id,
            company_id=company_id,
            actor={"id": actor_user_id} if actor_user_id else None,
        )
        sign_url = f"/handover-sign.html?token={token}"
        base = get_public_base_url().rstrip("/")
        return {
            "token": token,
            "signUrl": sign_url,
            "absoluteUrl": f"{base}{sign_url}" if base else sign_url,
            "expiresAt": expires_at,
            "workerId": worker_id,
        }

    def get_session_by_token(self, token: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM worker_handover_sign_sessions WHERE token = ? LIMIT 1",
            (token,),
        ).fetchone()
        return dict(row) if row else None

    def get_public_view(self, token: str) -> dict[str, Any] | None:
        session = self.get_session_by_token(token)
        if not session:
            return None
        if str(session.get("status") or "") == "expired":
            return {"error": "sign_link_expired"}
        if str(session.get("status") or "") == "pending" and _session_expired(session):
            self.db.execute(
                "UPDATE worker_handover_sign_sessions SET status = 'expired' WHERE id = ?",
                (session["id"],),
            )
            return {"error": "sign_link_expired"}
        if str(session.get("status") or "") == "signed":
            return {"error": "already_signed", "signedAt": session.get("signed_at")}

        worker = self.db.execute(
            "SELECT first_name, last_name, compliance_signature_data FROM workers WHERE id = ?",
            (session["worker_id"],),
        ).fetchone()
        if not worker:
            return None
        if str(worker["compliance_signature_data"] or "").strip():
            return {"error": "already_signed"}

        company = self.db.execute(
            "SELECT name FROM companies WHERE id = ?",
            (session["company_id"],),
        ).fetchone()
        setting = self.db.execute("SELECT platform_name FROM settings WHERE id = 1").fetchone()
        worker_name = f"{worker['first_name'] or ''} {worker['last_name'] or ''}".strip()
        return {
            "token": token,
            "status": session.get("status"),
            "expiresAt": session.get("expires_at"),
            "workerName": worker_name,
            "companyName": (company["name"] if company else "") or (
                setting["platform_name"] if setting else "WorkPass"
            ),
        }

    def submit_signature(
        self,
        token: str,
        *,
        signature_data: str,
        consent_accepted: bool = False,
    ) -> dict[str, Any]:
        session = self.get_session_by_token(token)
        if not session:
            raise ValueError("sign_session_not_found")
        if str(session.get("status") or "") == "signed":
            raise ValueError("already_signed")
        if str(session.get("status") or "") == "expired":
            raise ValueError("sign_link_expired")
        if _session_expired(session):
            self.db.execute(
                "UPDATE worker_handover_sign_sessions SET status = 'expired' WHERE id = ?",
                (session["id"],),
            )
            raise ValueError("sign_link_expired")
        if not consent_accepted:
            raise ValueError("consent_required")

        worker_id = str(session["worker_id"])
        worker = self.db.execute(
            "SELECT compliance_signature_data FROM workers WHERE id = ?",
            (worker_id,),
        ).fetchone()
        if not worker:
            raise ValueError("worker_not_found")
        if str(worker["compliance_signature_data"] or "").strip():
            raise ValueError("already_signed")

        sanitized = sanitize_compliance_signature_data(signature_data, required=True)
        signed_at = now_iso()
        self.db.execute(
            """
            UPDATE workers
            SET compliance_signature_data = ?, compliance_signature_at = ?, compliance_signature_captured_by = ?
            WHERE id = ?
            """,
            (sanitized, signed_at, f"remote:{session['id']}", worker_id),
        )
        self.db.execute(
            """
            UPDATE worker_handover_sign_sessions
            SET status = 'signed', signature_data = ?, signed_at = ?
            WHERE id = ?
            """,
            (sanitized, signed_at, session["id"]),
        )
        log_audit(
            "worker.compliance_signature_saved",
            f"Remote-Handover-Unterschrift fuer Mitarbeiter {worker_id} gespeichert",
            target_type="worker",
            target_id=worker_id,
            company_id=session["company_id"],
        )
        return {"ok": True, "signedAt": signed_at, "workerId": worker_id}
