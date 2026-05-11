"""
BauPass – Base Repository with Tenant Isolation
================================================
جميع repositories ترث من BaseRepository.

الضمانات:
  1. لا query بدون tenant_id (إلا super admin)
  2. كل استعلام يُقيَّد تلقائياً بـ company_id
  3. خطأ صريح إذا حاول repository الوصول لبيانات tenant آخر

نمط الاستخدام:
    class WorkerRepository(BaseRepository):
        TABLE = "workers"

        def find_by_badge(self, badge_id: str) -> Optional[dict]:
            return self.find_one("badge_id = ?", (badge_id,))
            # يُضاف AND company_id = ? تلقائياً

        def find_active(self) -> list[dict]:
            return self.find_many("status = ?", ("active",))
"""
from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from flask import g

from backend.app.database import get_connection
from backend.app.middleware.tenant import require_tenant_context

logger = logging.getLogger("baupass.repository")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class BaseRepository:
    """
    Repository أساسي يُوفّر CRUD آمن مع tenant isolation.

    كل subclass يُعرّف:
        TABLE: str  — اسم الجدول
        TENANT_COLUMN: str  — اسم عمود الـ tenant (افتراضي: 'company_id')

    الأساليب المتاحة:
        find_one(where, params) → Optional[dict]
        find_many(where, params, order_by, limit) → list[dict]
        insert(data) → str (id الجديد)
        update(id, data) → bool
        delete(id) → bool
        count(where, params) → int
        exists(where, params) → bool
    """

    TABLE: str = ""  # يجب تعريفه في الـ subclass
    TENANT_COLUMN: str = "company_id"
    PRIMARY_KEY: str = "id"
    SOFT_DELETE_COLUMN: Optional[str] = None  # 'deleted_at' للـ soft delete

    def __init__(self, company_id: Optional[int] = None):
        """
        Args:
            company_id: تجاوز صريح للـ company_id (للـ super admin)
                        إذا لم يُحدَّد، يُقرأ من TenantContext.
        """
        if not self.TABLE:
            raise NotImplementedError(f"{self.__class__.__name__} must define TABLE")

        if company_id is not None:
            self._company_id = company_id
        else:
            ctx = require_tenant_context()
            self._company_id = ctx.company_id

    @property
    def _db(self) -> sqlite3.Connection:
        return get_connection()

    @property
    def company_id(self) -> int:
        return self._company_id

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _tenant_filter(self) -> tuple[str, tuple]:
        """يُعيد WHERE clause وparams للـ tenant filter."""
        return f"{self.TENANT_COLUMN} = ?", (self._company_id,)

    def _build_where(self, extra_where: str = "", extra_params: tuple = ()) -> tuple[str, tuple]:
        """يبني WHERE clause كامل مع tenant filter."""
        tenant_clause, tenant_params = self._tenant_filter()

        if extra_where:
            where = f"{tenant_clause} AND ({extra_where})"
            params = tenant_params + extra_params
        else:
            where = tenant_clause
            params = tenant_params

        # Soft delete filter
        if self.SOFT_DELETE_COLUMN:
            where += f" AND {self.SOFT_DELETE_COLUMN} IS NULL"

        return where, params

    def _row_to_dict(self, row: Optional[sqlite3.Row]) -> Optional[dict]:
        if row is None:
            return None
        return dict(row)

    # ── Public API ────────────────────────────────────────────────────────────

    def find_one(
        self,
        where: str = "",
        params: tuple = (),
        order_by: str = "",
    ) -> Optional[dict]:
        """يُعيد سجلاً واحداً مطابقاً للـ where clause."""
        full_where, full_params = self._build_where(where, params)

        sql = f"SELECT * FROM {self.TABLE} WHERE {full_where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        sql += " LIMIT 1"

        row = self._db.execute(sql, full_params).fetchone()
        return self._row_to_dict(row)

    def find_by_id(self, record_id: Any) -> Optional[dict]:
        """يُعيد سجلاً بـ primary key مع التحقق من tenant ownership."""
        full_where, full_params = self._build_where(
            f"{self.PRIMARY_KEY} = ?", (record_id,)
        )
        sql = f"SELECT * FROM {self.TABLE} WHERE {full_where} LIMIT 1"
        row = self._db.execute(sql, full_params).fetchone()
        return self._row_to_dict(row)

    def find_many(
        self,
        where: str = "",
        params: tuple = (),
        order_by: str = "",
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[dict]:
        """يُعيد قائمة السجلات المطابقة."""
        full_where, full_params = self._build_where(where, params)

        sql = f"SELECT * FROM {self.TABLE} WHERE {full_where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit is not None:
            sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"

        rows = self._db.execute(sql, full_params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def count(self, where: str = "", params: tuple = ()) -> int:
        """يُعيد عدد السجلات المطابقة."""
        full_where, full_params = self._build_where(where, params)
        sql = f"SELECT COUNT(*) FROM {self.TABLE} WHERE {full_where}"
        row = self._db.execute(sql, full_params).fetchone()
        return row[0] if row else 0

    def exists(self, where: str, params: tuple = ()) -> bool:
        """يتحقق من وجود سجل مطابق."""
        full_where, full_params = self._build_where(where, params)
        sql = f"SELECT 1 FROM {self.TABLE} WHERE {full_where} LIMIT 1"
        return self._db.execute(sql, full_params).fetchone() is not None

    def insert(self, data: dict, return_id: bool = True) -> str:
        """
        يُضيف سجلاً جديداً.
        يُضيف تلقائياً: id, company_id, created_at, updated_at.

        Returns: id السجل الجديد.
        """
        record = dict(data)

        # إضافة الحقول التلقائية
        if self.PRIMARY_KEY not in record:
            record[self.PRIMARY_KEY] = str(uuid.uuid4())
        if self.TENANT_COLUMN not in record:
            record[self.TENANT_COLUMN] = self._company_id
        if "created_at" not in record:
            record["created_at"] = _now_iso()
        if "updated_at" not in record:
            record["updated_at"] = _now_iso()

        # التحقق أن company_id يطابق الـ tenant
        if record.get(self.TENANT_COLUMN) != self._company_id:
            raise PermissionError(
                f"Repository insert: {self.TENANT_COLUMN} mismatch. "
                f"Expected {self._company_id}, got {record.get(self.TENANT_COLUMN)}"
            )

        columns = list(record.keys())
        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)

        self._db.execute(
            f"INSERT INTO {self.TABLE} ({col_names}) VALUES ({placeholders})",
            tuple(record.values()),
        )
        self._db.commit()

        return record[self.PRIMARY_KEY]

    def update(self, record_id: Any, data: dict) -> bool:
        """
        يُحدّث سجلاً بـ id مع التحقق من tenant ownership.
        يُضيف updated_at تلقائياً.
        """
        # التحقق من الملكية أولاً
        existing = self.find_by_id(record_id)
        if not existing:
            return False

        update_data = dict(data)
        update_data.pop(self.PRIMARY_KEY, None)
        update_data.pop(self.TENANT_COLUMN, None)  # لا تسمح بتغيير company_id
        update_data["updated_at"] = _now_iso()

        set_clause = ", ".join([f"{k} = ?" for k in update_data.keys()])
        values = list(update_data.values()) + [record_id, self._company_id]

        cursor = self._db.execute(
            f"UPDATE {self.TABLE} SET {set_clause} "
            f"WHERE {self.PRIMARY_KEY} = ? AND {self.TENANT_COLUMN} = ?",
            values,
        )
        self._db.commit()
        return cursor.rowcount > 0

    def delete(self, record_id: Any) -> bool:
        """
        يحذف سجلاً مع التحقق من tenant ownership.
        إذا كان SOFT_DELETE_COLUMN معرَّفاً، يُنفذ soft delete.
        """
        if self.SOFT_DELETE_COLUMN:
            return self.update(record_id, {self.SOFT_DELETE_COLUMN: _now_iso()})

        cursor = self._db.execute(
            f"DELETE FROM {self.TABLE} "
            f"WHERE {self.PRIMARY_KEY} = ? AND {self.TENANT_COLUMN} = ?",
            (record_id, self._company_id),
        )
        self._db.commit()
        return cursor.rowcount > 0

    def paginate(
        self,
        page: int = 1,
        per_page: int = 50,
        where: str = "",
        params: tuple = (),
        order_by: str = "created_at DESC",
    ) -> dict:
        """
        يُعيد صفحة من النتائج مع معلومات التصفح.

        Returns:
            {
                "items": [...],
                "total": 150,
                "page": 1,
                "per_page": 50,
                "pages": 3,
                "has_next": True,
                "has_prev": False,
            }
        """
        page = max(1, page)
        per_page = min(max(1, per_page), 200)  # حد أقصى 200 سجل
        offset = (page - 1) * per_page

        total = self.count(where, params)
        items = self.find_many(where, params, order_by=order_by, limit=per_page, offset=offset)

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page),
            "has_next": page * per_page < total,
            "has_prev": page > 1,
        }
