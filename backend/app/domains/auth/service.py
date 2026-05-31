"""
Auth domain service.

Business logic migrates here from backend/server.py incrementally.
During transition, methods may delegate to legacy helpers.
"""
from __future__ import annotations

from typing import Any


class AuthService:
    """Authentication and session lifecycle."""

    def login(self):
        """POST /api/login — see login_flow.perform_login."""
        from .login_flow import perform_login

        return perform_login()

    def logout(self, token: str, current_user: dict[str, Any]) -> dict[str, Any]:
        """Revoke session and write audit log (delegates to legacy helpers)."""
        import backend.server as srv

        db = srv.get_db()
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        db.commit()
        srv.log_audit(
            "login.logout",
            f"Benutzer {current_user.get('username', '')} abgemeldet",
            target_type="user",
            target_id=current_user.get("id"),
            actor=current_user,
        )
        return {"ok": True}

    def logout_session(self, token: str | None) -> dict[str, Any]:
        """Revoke token only (probe / API-key flows)."""
        if not token:
            return {"ok": True, "revoked": False}
        import backend.server as srv

        srv.get_db().execute("DELETE FROM sessions WHERE token = ?", (token,))
        srv.get_db().commit()
        return {"ok": True, "revoked": True}
