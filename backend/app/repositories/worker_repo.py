"""
WorkPass – Worker Repository
============================
مثال على repository حقيقي يرث من BaseRepository.
"""
from __future__ import annotations

from typing import Optional

from .base import BaseRepository


class WorkerRepository(BaseRepository):
    TABLE = "workers"
    SOFT_DELETE_COLUMN = "deleted_at"  # soft delete بدل الحذف الفعلي

    def find_by_badge(self, badge_id: str) -> Optional[dict]:
        """البحث بـ badge_id (فريد داخل الشركة)."""
        return self.find_one("badge_id = ?", (badge_id,))

    def find_by_email(self, email: str) -> Optional[dict]:
        """البحث بالإيميل."""
        return self.find_one("LOWER(email) = LOWER(?)", (email.strip(),))

    def find_active(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """جميع العمال النشطين."""
        return self.find_many(
            "status = ?", ("active",),
            order_by="last_name ASC, first_name ASC",
            limit=limit, offset=offset,
        )

    def find_expiring_documents(self, days_ahead: int = 30) -> list[dict]:
        """
        عمال لديهم وثائق تنتهي خلال X يوم.
        يُستدعى من background task.
        """
        from backend.app.database import get_connection
        sql = """
            SELECT DISTINCT w.*
            FROM workers w
            JOIN documents d ON d.worker_id = w.id
            WHERE w.company_id = ?
              AND w.status = 'active'
              AND d.expiry_date IS NOT NULL
              AND d.expiry_date BETWEEN date('now') AND date('now', ? || ' days')
              AND d.status = 'approved'
              AND w.deleted_at IS NULL
        """
        rows = get_connection().execute(sql, (self.company_id, str(days_ahead))).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """بحث نصي في الاسم والـ badge_id."""
        pattern = f"%{query.strip()}%"
        return self.find_many(
            "(first_name LIKE ? OR last_name LIKE ? OR badge_id LIKE ? OR email LIKE ?)",
            (pattern, pattern, pattern, pattern),
            order_by="last_name ASC",
            limit=limit,
        )

    def count_by_status(self) -> dict:
        """إحصاء العمال حسب الحالة."""
        from backend.app.database import get_connection
        rows = get_connection().execute(
            "SELECT status, COUNT(*) as cnt FROM workers "
            "WHERE company_id = ? AND deleted_at IS NULL "
            "GROUP BY status",
            (self.company_id,),
        ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}
