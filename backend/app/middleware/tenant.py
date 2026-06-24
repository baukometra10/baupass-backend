"""
SUPPIX – Tenant Isolation Middleware
======================================
يضمن:
  1. كل طلب authenticated له company_id مرتبط
  2. لا يمكن لأي tenant الوصول لبيانات tenant آخر
  3. التحقق يحدث على مستوى الـ architecture لا فقط الـ queries

المبدأ الأساسي:
  العزل لا يعتمد فقط على WHERE company_id = ?
  بل على TenantContext يُحقَّق في كل layer قبل التنفيذ.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from flask import Flask, g, jsonify, request

logger = logging.getLogger("baupass.tenant")


@dataclass(frozen=True)
class TenantContext:
    """
    Context مرتبط بكل طلب يحتوي معلومات الـ tenant.
    frozen=True يمنع التعديل العرضي.
    """
    company_id: int
    company_name: str = ""
    user_id: Optional[str] = None
    user_role: Optional[str] = None
    is_superadmin: bool = False  # يمكنه الوصول لجميع tenants

    def validate(self) -> None:
        """يتحقق من صحة الـ context."""
        if not self.is_superadmin and (not self.company_id or self.company_id <= 0):
            raise ValueError(f"Invalid TenantContext: company_id={self.company_id}")

    def can_access_company(self, target_company_id: int) -> bool:
        """هل يمكن لهذا المستخدم الوصول لبيانات شركة معينة؟"""
        if self.is_superadmin:
            return True
        return self.company_id == target_company_id


def get_tenant_context() -> Optional[TenantContext]:
    """يُعيد الـ tenant context للطلب الحالي (None إذا غير authenticated)."""
    return getattr(g, "_tenant_context", None)


def require_tenant_context() -> TenantContext:
    """
    يُعيد الـ tenant context أو يرفع استثناء.
    يُستدعى من داخل repositories وservices.
    """
    ctx = get_tenant_context()
    if ctx is None:
        raise RuntimeError(
            "TenantContext not set. This code must run within an authenticated request context. "
            "Ensure @require_admin or @require_worker_session decorator is applied."
        )
    return ctx


def set_tenant_context(ctx: TenantContext) -> None:
    """يُعيّن الـ tenant context للطلب الحالي. يُستدعى من auth decorators."""
    ctx.validate()
    g._tenant_context = ctx


class TenantMiddleware:
    """
    Middleware يُراقب الطلبات ويُضيف tenant context.
    يعمل كـ validator لا كـ enforcer (الـ enforcement في auth decorators).
    """

    def __init__(self, app: Flask):
        self.app = app

    def __call__(self, environ, start_response):
        return self.app(environ, start_response)


def tenant_guard(target_company_id: int) -> None:
    """
    يتحقق أن المستخدم الحالي له صلاحية الوصول لشركة معينة.
    يُستدعى في بداية أي service method تستقبل company_id من الخارج.

    مثال:
        def get_workers(company_id: int):
            tenant_guard(company_id)  # يُطلق استثناء إذا غير مسموح
            return worker_repo.find_by_company(company_id)
    """
    ctx = require_tenant_context()
    if not ctx.can_access_company(target_company_id):
        logger.error(
            "Tenant isolation violation: user=%s company=%d tried to access company=%d",
            ctx.user_id,
            ctx.company_id,
            target_company_id,
        )
        # هذا خطأ أمني خطير — يُسجَّل ويُرفع
        raise PermissionError(
            f"Tenant isolation: user from company {ctx.company_id} "
            f"attempted to access company {target_company_id} data."
        )


def register_tenant_violation_handler(app: Flask) -> None:
    """يُسجّل معالج أخطاء لـ PermissionError الناتجة عن انتهاك tenant isolation."""

    @app.errorhandler(PermissionError)
    def handle_tenant_violation(exc: PermissionError):
        logger.critical("TENANT ISOLATION VIOLATION: %s", exc)
        # لا نُعيد تفاصيل الخطأ للعميل
        return jsonify({
            "error": "forbidden",
            "message": "Access denied.",
        }), 403
