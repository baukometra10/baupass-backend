"""Workers domain — data access."""
from __future__ import annotations

from typing import Any


class WorkersRepository:
    def list_active(self, db, company_id: str, limit: int = 500) -> list[dict[str, Any]]:
        rows = db.execute(
            """
            SELECT id, badge_id, first_name, last_name, status, worker_type, site, physical_card_id
            FROM workers
            WHERE company_id = ? AND deleted_at IS NULL
            ORDER BY last_name, first_name
            LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_id(self, db, company_id: str, worker_id: str) -> dict[str, Any] | None:
        row = db.execute(
            """
            SELECT * FROM workers
            WHERE id = ? AND company_id = ? AND deleted_at IS NULL
            """,
            (worker_id, company_id),
        ).fetchone()
        return dict(row) if row else None

    def count_on_site_today(self, db, company_id: str, today_prefix: str) -> int:
        row = db.execute(
            """
            SELECT COUNT(*) AS c
            FROM (
                SELECT al.worker_id, al.direction
                FROM access_logs al
                JOIN workers w ON w.id = al.worker_id
                WHERE w.company_id = ? AND w.deleted_at IS NULL AND al.timestamp LIKE ?
                  AND al.timestamp = (
                      SELECT MAX(al2.timestamp) FROM access_logs al2
                      WHERE al2.worker_id = al.worker_id AND al2.timestamp LIKE ?
                  )
            ) latest
            WHERE latest.direction IN ('check-in', 'app-login')
            """,
            (company_id, f"{today_prefix}%", f"{today_prefix}%"),
        ).fetchone()
        return int((row["c"] if row else 0) or 0)

    def update_physical_card_id(
        self, db, company_id: str, worker_id: str, physical_card_id: str | None
    ) -> bool:
        cur = db.execute(
            """
            UPDATE workers
            SET physical_card_id = ?
            WHERE id = ? AND company_id = ? AND deleted_at IS NULL
            """,
            (physical_card_id, worker_id, company_id),
        )
        return int(cur.rowcount or 0) > 0

    def list_filtered(self, db, where_sql: str, params: list[Any]) -> list[dict[str, Any]]:
        rows = db.execute(
            f"SELECT * FROM workers{where_sql} ORDER BY last_name, first_name",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def get_by_id_global(self, db, worker_id: str) -> dict[str, Any] | None:
        row = db.execute("SELECT * FROM workers WHERE id = ?", (worker_id,)).fetchone()
        return dict(row) if row else None

    def get_company_row(self, db, company_id: str) -> dict[str, Any] | None:
        row = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        return dict(row) if row else None

    def insert_worker(
        self,
        db,
        *,
        worker_id: str,
        company_id: str,
        subcompany_id: str | None,
        first_name: str,
        last_name: str,
        insurance_number: str,
        worker_type: str,
        role: str,
        site: str,
        valid_until: str,
        visitor_company: str,
        visit_purpose: str,
        host_name: str,
        visit_end_at: str,
        status: str,
        photo_data: str,
        badge_id: str,
        badge_id_lookup: str,
        badge_pin_hash: str,
        physical_card_id: str | None,
    ) -> None:
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, subcompany_id, first_name, last_name, insurance_number,
                worker_type, role, site, valid_until, visitor_company, visit_purpose,
                host_name, visit_end_at, status, photo_data, badge_id, badge_id_lookup,
                badge_pin_hash, physical_card_id, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                worker_id,
                company_id,
                subcompany_id,
                first_name,
                last_name,
                insurance_number,
                worker_type,
                role,
                site,
                valid_until,
                visitor_company,
                visit_purpose,
                host_name,
                visit_end_at,
                status,
                photo_data,
                badge_id,
                badge_id_lookup,
                badge_pin_hash,
                physical_card_id,
                None,
            ),
        )

    def update_worker(
        self,
        db,
        worker_id: str,
        *,
        company_id: str,
        subcompany_id: str | None,
        first_name: str,
        last_name: str,
        insurance_number: str,
        worker_type: str,
        role: str,
        site: str,
        valid_until: str,
        visitor_company: str,
        visit_purpose: str,
        host_name: str,
        visit_end_at: str,
        status: str,
        photo_data: str,
        badge_pin_hash: str,
        physical_card_id: str | None,
        contact_email: str,
        leave_balance: int,
    ) -> None:
        db.execute(
            """
            UPDATE workers
            SET company_id = ?, subcompany_id = ?, first_name = ?, last_name = ?,
                insurance_number = ?, worker_type = ?, role = ?, site = ?, valid_until = ?,
                visitor_company = ?, visit_purpose = ?, host_name = ?, visit_end_at = ?,
                status = ?, photo_data = ?, badge_pin_hash = ?, physical_card_id = ?,
                contact_email = ?, leave_balance = ?
            WHERE id = ?
            """,
            (
                company_id,
                subcompany_id,
                first_name,
                last_name,
                insurance_number,
                worker_type,
                role,
                site,
                valid_until,
                visitor_company,
                visit_purpose,
                host_name,
                visit_end_at,
                status,
                photo_data,
                badge_pin_hash,
                physical_card_id,
                contact_email,
                leave_balance,
                worker_id,
            ),
        )

    def update_worker_personal(
        self,
        db,
        worker_id: str,
        *,
        home_address: str | None = None,
        birth_date: str | None = None,
        gender: str | None = None,
        contact_phone: str | None = None,
    ) -> None:
        sets: list[str] = []
        params: list[Any] = []
        if home_address is not None:
            sets.append("home_address = ?")
            params.append(home_address)
        if birth_date is not None:
            sets.append("birth_date = ?")
            params.append(birth_date)
        if gender is not None:
            sets.append("gender = ?")
            params.append(gender)
        if contact_phone is not None:
            sets.append("contact_phone = ?")
            params.append(contact_phone)
        if not sets:
            return
        params.append(worker_id)
        db.execute(
            f"UPDATE workers SET {', '.join(sets)} WHERE id = ?",
            tuple(params),
        )

    def soft_delete(self, db, worker_id: str, *, deleted_at: str) -> None:
        db.execute("UPDATE workers SET deleted_at = ? WHERE id = ?", (deleted_at, worker_id))

    def restore(self, db, worker_id: str) -> None:
        db.execute("UPDATE workers SET deleted_at = NULL WHERE id = ?", (worker_id,))

    def list_current_visitors(
        self, db, *, now_str: str, company_id: str | None
    ) -> list[dict[str, Any]]:
        if company_id:
            rows = db.execute(
                """
                SELECT w.id, w.first_name, w.last_name, w.badge_id, w.visitor_company,
                       w.visit_purpose, w.host_name, w.visit_end_at, w.status
                FROM workers w
                WHERE w.worker_type = 'visitor'
                  AND w.deleted_at IS NULL
                  AND (w.visit_end_at = '' OR w.visit_end_at > ?)
                  AND w.status != 'gesperrt'
                  AND w.company_id = ?
                ORDER BY w.visit_end_at ASC
                """,
                (now_str, company_id),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT w.id, w.first_name, w.last_name, w.badge_id, w.visitor_company,
                       w.visit_purpose, w.host_name, w.visit_end_at, w.status
                FROM workers w
                WHERE w.worker_type = 'visitor'
                  AND w.deleted_at IS NULL
                  AND (w.visit_end_at = '' OR w.visit_end_at > ?)
                  AND w.status != 'gesperrt'
                ORDER BY w.visit_end_at ASC
                """,
                (now_str,),
            ).fetchall()
        return [dict(row) for row in rows]

    def worker_stats(self, db, company_id: str | None) -> dict[str, Any]:
        company_filter = "AND w.company_id = ?" if company_id else ""
        params: list[Any] = [company_id] if company_id else []
        access_params = list(params)

        status_rows = db.execute(
            f"""
            SELECT COALESCE(status,'unbekannt') AS status, COUNT(*) AS cnt
            FROM workers w WHERE w.deleted_at IS NULL {company_filter}
            GROUP BY status ORDER BY cnt DESC
            """,
            params,
        ).fetchall()
        site_rows = db.execute(
            f"""
            SELECT site, COUNT(*) AS cnt FROM workers w
            WHERE w.deleted_at IS NULL AND TRIM(COALESCE(site,'')) != '' {company_filter}
            GROUP BY site ORDER BY cnt DESC LIMIT 10
            """,
            params,
        ).fetchall()
        type_rows = db.execute(
            f"""
            SELECT COALESCE(worker_type,'worker') AS worker_type, COUNT(*) AS cnt
            FROM workers w WHERE w.deleted_at IS NULL {company_filter}
            GROUP BY worker_type
            """,
            params,
        ).fetchall()
        total_row = db.execute(
            f"SELECT COUNT(*) AS cnt FROM workers w WHERE w.deleted_at IS NULL {company_filter}",
            params,
        ).fetchone()
        access_filter = "AND w.company_id = ?" if company_id else ""
        gate_rows = db.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(al.gate),''), 'Unbekannt') AS gate, COUNT(*) AS cnt
            FROM access_logs al JOIN workers w ON w.id = al.worker_id
            WHERE DATE(al.timestamp) >= DATE('now', '-30 day') {access_filter}
            GROUP BY gate ORDER BY cnt DESC LIMIT 10
            """,
            access_params,
        ).fetchall()
        hour_rows = db.execute(
            f"""
            SELECT CAST(strftime('%H', al.timestamp) AS INTEGER) AS hour, COUNT(*) AS cnt
            FROM access_logs al JOIN workers w ON w.id = al.worker_id
            WHERE al.direction = 'check-in'
              AND DATE(al.timestamp) >= DATE('now', '-30 day') {access_filter}
            GROUP BY hour ORDER BY hour ASC
            """,
            access_params,
        ).fetchall()
        return {
            "totalWorkers": int(total_row["cnt"]) if total_row else 0,
            "byStatus": [{"status": r["status"], "count": r["cnt"]} for r in status_rows],
            "bySite": [{"site": r["site"] or "Keine Baustelle", "count": r["cnt"]} for r in site_rows],
            "byGate": [{"gate": r["gate"], "count": r["cnt"]} for r in gate_rows],
            "checkInsByHour": [{"hour": r["hour"], "count": r["cnt"]} for r in hour_rows],
            "byType": [{"type": r["worker_type"], "count": r["cnt"]} for r in type_rows],
        }

    def set_status(self, db, worker_id: str, status: str) -> None:
        db.execute("UPDATE workers SET status = ? WHERE id = ?", (status, worker_id))

    def set_badge_pin_hash(self, db, worker_id: str, pin_hash: str) -> None:
        db.execute(
            "UPDATE workers SET badge_pin_hash = ? WHERE id = ?",
            (pin_hash, worker_id),
        )

    def get_worker_brief(self, db, worker_id: str) -> dict[str, Any] | None:
        row = db.execute(
            "SELECT id, company_id, deleted_at FROM workers WHERE id = ?",
            (worker_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_worker_documents(self, db, worker_id: str) -> list[dict[str, Any]]:
        rows = db.execute(
            """
            SELECT id, doc_type, filename, file_size, source_email_from, created_at, notes, expiry_date
            FROM worker_documents
            WHERE worker_id = ?
            ORDER BY created_at DESC
            """,
            (worker_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_worker_document(
        self, db, worker_id: str, doc_id: str
    ) -> dict[str, Any] | None:
        row = db.execute(
            "SELECT * FROM worker_documents WHERE id = ? AND worker_id = ?",
            (doc_id, worker_id),
        ).fetchone()
        return dict(row) if row else None

    def insert_worker_document(
        self,
        db,
        *,
        doc_id: str,
        worker_id: str,
        company_id: str,
        doc_type: str,
        filename: str,
        file_path: str,
        file_size: int,
        uploaded_by_user_id: str,
        created_at: str,
        notes: str,
        expiry_date: str | None,
    ) -> None:
        db.execute(
            """
            INSERT INTO worker_documents
               (id, worker_id, company_id, doc_type, filename, file_path, file_size,
                source_email_from, source_inbox_id, uploaded_by_user_id, created_at, notes, expiry_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                doc_id,
                worker_id,
                company_id,
                doc_type,
                filename,
                file_path,
                file_size,
                "",
                None,
                uploaded_by_user_id,
                created_at,
                notes,
                expiry_date,
            ),
        )

    def delete_worker_document(self, db, doc_id: str) -> None:
        db.execute("DELETE FROM worker_documents WHERE id = ?", (doc_id,))

    def company_name_to_id_map(self, db) -> dict[str, str]:
        rows = db.execute(
            "SELECT id, name FROM companies WHERE deleted_at IS NULL"
        ).fetchall()
        return {str(r["name"]).strip().lower(): str(r["id"]) for r in rows}

    def badge_id_exists(self, db, badge_id: str) -> bool:
        row = db.execute(
            "SELECT id FROM workers WHERE badge_id = ?", (badge_id,)
        ).fetchone()
        return row is not None

    def insert_csv_import_worker(
        self,
        db,
        *,
        worker_id: str,
        company_id: str,
        first_name: str,
        last_name: str,
        insurance_number: str,
        worker_type: str,
        role_value: str,
        site_value: str,
        valid_until_value: str | None,
        badge_id_value: str,
        badge_id_lookup: str,
    ) -> None:
        db.execute(
            """
            INSERT INTO workers (
                id, company_id, subcompany_id, first_name, last_name, insurance_number,
                worker_type, role, site, valid_until, visitor_company, visit_purpose,
                host_name, visit_end_at, status, photo_data, badge_id, badge_id_lookup, badge_pin_hash,
                physical_card_id, deleted_at
            ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, '', '', '', NULL, 'active', '', ?, ?, '', '', NULL)
            """,
            (
                worker_id,
                company_id,
                first_name,
                last_name,
                insurance_number,
                worker_type,
                role_value,
                site_value,
                valid_until_value,
                badge_id_value,
                badge_id_lookup,
            ),
        )

    def fetch_workers_csv_rows(
        self, db, where_clause: str, params: list[Any]
    ) -> list[dict[str, Any]]:
        rows = db.execute(
            f"""
            SELECT workers.*, companies.name AS company_name, subcompanies.name AS subcompany_name
            FROM workers
            JOIN companies ON companies.id = workers.company_id
            LEFT JOIN subcompanies ON subcompanies.id = workers.subcompany_id
            {where_clause}
            ORDER BY workers.last_name, workers.first_name
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def fetch_workers_pdf_rows(
        self, db, where_clause: str, params: list[Any]
    ) -> list[dict[str, Any]]:
        rows = db.execute(
            f"""
            SELECT workers.id, workers.first_name, workers.last_name, workers.status,
                   workers.photo_data, workers.badge_id, workers.site,
                   companies.name AS company_name, subcompanies.name AS subcompany_name
            FROM workers
            JOIN companies ON companies.id = workers.company_id
            LEFT JOIN subcompanies ON subcompanies.id = workers.subcompany_id
            {where_clause}
            ORDER BY workers.last_name, workers.first_name
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def fetch_attendance_source_rows(
        self, db, clause: str, params: list[Any], date_param: str
    ) -> list[dict[str, Any]]:
        rows = db.execute(
            f"""
            SELECT w.id AS worker_id, w.first_name, w.last_name, w.badge_id,
                   al.direction, al.gate, al.timestamp,
                   c.name AS company_name
            FROM workers w
            JOIN (
                SELECT worker_id, MAX(timestamp) AS latest_ts
                FROM access_logs
                WHERE DATE(timestamp) = ?
                GROUP BY worker_id
            ) latest ON latest.worker_id = w.id
            JOIN access_logs al ON al.worker_id = w.id AND al.timestamp = latest.latest_ts
            JOIN companies c ON c.id = w.company_id
            {clause}
            WHERE w.deleted_at IS NULL
            ORDER BY al.timestamp DESC
            """,
            [date_param] + list(params),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_settings_row(self, db) -> dict[str, Any] | None:
        row = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        return dict(row) if row else None

    def get_worker_company_id(self, db, worker_id: str) -> str | None:
        row = db.execute(
            "SELECT company_id FROM workers WHERE id = ?", (worker_id,)
        ).fetchone()
        return str(row["company_id"]) if row else None

    def list_hce_devices(self, db, worker_id: str) -> list[dict[str, Any]]:
        rows = db.execute(
            """
            SELECT id, device_id, platform, app_version, status, trust_version, signature_algo,
                   created_at, last_seen_at, device_public_key
            FROM hce_device_trust
            WHERE worker_id = ?
            ORDER BY created_at DESC
            """,
            (worker_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_hce_device(
        self, db, worker_id: str, device_id: str
    ) -> dict[str, Any] | None:
        row = db.execute(
            "SELECT * FROM hce_device_trust WHERE worker_id = ? AND device_id = ? LIMIT 1",
            (worker_id, device_id),
        ).fetchone()
        return dict(row) if row else None

    def revoke_hce_device(self, db, row_id: str, device_id: str) -> None:
        db.execute(
            "UPDATE hce_device_trust SET status = 'revoked' WHERE id = ?", (row_id,)
        )
        db.execute("DELETE FROM hce_device_nonces WHERE device_id = ?", (device_id,))

    def activate_hce_device(self, db, row_id: str, last_seen_at: str) -> None:
        db.execute(
            "UPDATE hce_device_trust SET status = 'active', last_seen_at = ? WHERE id = ?",
            (last_seen_at, row_id),
        )

    def get_identity_token_row(self, db, worker_id: str) -> dict[str, Any] | None:
        row = db.execute(
            """
            SELECT * FROM worker_identity_tokens WHERE worker_id = ? LIMIT 1
            """,
            (worker_id,),
        ).fetchone()
        return dict(row) if row else None

    def set_identity_token_status(self, db, token_id: str, status: str) -> None:
        db.execute(
            "UPDATE worker_identity_tokens SET status = ? WHERE id = ?",
            (status, token_id),
        )

    def get_leave_request_export_row(self, db, req_id: str) -> dict[str, Any] | None:
        row = db.execute(
            """
            SELECT lr.*, w.first_name, w.last_name, w.badge_id,
                   reviewer.username AS reviewer_username
            FROM leave_requests lr
            JOIN workers w ON w.id = lr.worker_id
            LEFT JOIN users reviewer ON reviewer.id = lr.reviewed_by_user_id
            WHERE lr.id = ?
            """,
            (req_id,),
        ).fetchone()
        return dict(row) if row else None
