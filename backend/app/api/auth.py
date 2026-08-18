"""
WorkPass – Auth Routes (blueprint; delegates to AuthService).
"""
from __future__ import annotations

from flask import jsonify, request

from . import auth_bp
from backend.app.domains.auth.service import AuthService
from backend.server import SESSION_COOKIE_NAME


@auth_bp.post("/auth/logout")
def logout():
    from backend.server import get_auth_token_from_request, get_user_from_session_token, get_db

    token = get_auth_token_from_request()
    cookie_token = (request.cookies.get(SESSION_COOKIE_NAME, "") or "").strip()
    if token:
        try:
            user = get_user_from_session_token(token) or {}
            AuthService().logout(token, user)
        except Exception:
            try:
                db = get_db()
                db.execute("DELETE FROM sessions WHERE token = ?", (token,))
                db.commit()
            except Exception:
                pass
    response = jsonify({"ok": True})
    if not cookie_token or cookie_token == token:
        response.delete_cookie(SESSION_COOKIE_NAME)
    return response, 200
