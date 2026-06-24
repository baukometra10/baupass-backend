"""
SUPPIX – Auth Routes (blueprint; delegates to AuthService).
"""
from __future__ import annotations

from flask import g, jsonify, request

from . import auth_bp
from backend.app.domains.auth.service import AuthService
from backend.server import SESSION_COOKIE_NAME, require_auth


@auth_bp.post("/auth/logout")
@require_auth
def logout():
    token = g.token
    AuthService().logout(token, g.current_user)
    response = jsonify({"ok": True})
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response, 200
