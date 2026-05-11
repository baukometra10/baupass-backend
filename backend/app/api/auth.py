"""
BauPass – Auth Routes (نموذج على blueprint مع Service/Repository pattern)
"""
from __future__ import annotations

from flask import g, jsonify, request

from . import auth_bp
# TODO: استيراد auth_service عند إنشائه
# from backend.app.services.auth_service import AuthService


@auth_bp.post("/auth/logout")
def logout():
    """
    مثال: logout مع session revocation.
    المنطق الكامل سيُنقل من server.py تدريجياً.
    """
    # TODO: نقل منطق server.py/logout هنا
    return jsonify({"ok": True}), 200
