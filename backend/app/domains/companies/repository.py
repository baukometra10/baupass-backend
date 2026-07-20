"""Companies domain — SQL data access."""
from __future__ import annotations

from typing import Any


def _rows_to_dicts(rows) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


class CompaniesRepository:
    def list_filtered(self, db, where_sql: str, params: list[Any]) -> list[dict[str, Any]]:
        rows = db.execute(f"SELECT * FROM companies{where_sql} ORDER BY name", params).fetchall()
        return _rows_to_dicts(rows)

    def get_by_id(self, db, company_id: str) -> dict[str, Any] | None:
        row = db.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
        return dict(row) if row else None

    def conflict_by_customer_number(self, db, customer_number: str) -> dict[str, Any] | None:
        row = db.execute(
            "SELECT id, name FROM companies WHERE COALESCE(customer_number, '') = ? LIMIT 1",
            (customer_number,),
        ).fetchone()
        return dict(row) if row else None

    def conflict_by_document_email(self, db, document_email: str) -> dict[str, Any] | None:
        row = db.execute(
            """
            SELECT id, name FROM companies
            WHERE deleted_at IS NULL AND lower(document_email) = ? LIMIT 1
            """,
            (document_email,),
        ).fetchone()
        return dict(row) if row else None

    def conflict_by_customer_number_excluding(
        self, db, company_id: str, customer_number: str
    ) -> dict[str, Any] | None:
        row = db.execute(
            "SELECT id, name FROM companies WHERE id != ? AND COALESCE(customer_number, '') = ? LIMIT 1",
            (company_id, customer_number),
        ).fetchone()
        return dict(row) if row else None

    def conflict_by_document_email_excluding(
        self, db, company_id: str, document_email: str
    ) -> dict[str, Any] | None:
        row = db.execute(
            """
            SELECT id, name FROM companies
            WHERE deleted_at IS NULL AND id != ? AND lower(document_email) = ? LIMIT 1
            """,
            (company_id, document_email),
        ).fetchone()
        return dict(row) if row else None

    def get_mail_access_row(self, db, company_id: str) -> dict[str, Any] | None:
        row = db.execute(
            "SELECT id, name, deleted_at FROM companies WHERE id = ?",
            (company_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_active_id(self, db, company_id: str) -> str | None:
        row = db.execute(
            "SELECT id FROM companies WHERE id = ? AND deleted_at IS NULL",
            (company_id,),
        ).fetchone()
        return str(row["id"]) if row else None

    def update_work_times(
        self,
        db,
        company_id: str,
        *,
        work_start_time: str,
        work_end_time: str,
        access_mode: str,
        site_geofence_radius_meters: int,
        site_auto_checkin: int,
        site_auto_logout_on_leave: int,
        site_auto_proximity_login: int,
    ) -> None:
        db.execute(
            """
            UPDATE companies
            SET work_start_time = ?, work_end_time = ?, access_mode = ?,
                site_geofence_radius_meters = ?, site_auto_checkin = ?, site_auto_logout_on_leave = ?,
                site_auto_proximity_login = ?
            WHERE id = ?
            """,
            (
                work_start_time,
                work_end_time,
                access_mode,
                site_geofence_radius_meters,
                site_auto_checkin,
                site_auto_logout_on_leave,
                site_auto_proximity_login,
                company_id,
            ),
        )

    def update_company(
        self,
        db,
        company_id: str,
        *,
        name: str,
        customer_number: str,
        contact: str,
        billing_email: str,
        billing_street: str,
        billing_zip_city: str,
        document_email: str,
        access_host: str,
        branding_preset: str,
        plan: str,
        status: str,
        trial_ends_at: str,
        invoice_email_lang: str,
        portal_display_name: str,
        branding_accent_color: str,
        branding_logo_data: str,
        report_timezone: str,
        operating_sector: str,
    ) -> None:
        db.execute(
            """
            UPDATE companies
            SET name = ?, customer_number = ?, contact = ?, billing_email = ?, billing_street = ?,
                billing_zip_city = ?, document_email = ?, access_host = ?, branding_preset = ?,
                plan = ?, status = ?, trial_ends_at = ?, invoice_email_lang = ?,
                portal_display_name = ?, branding_accent_color = ?, branding_logo_data = ?,
                report_timezone = ?, operating_sector = ?
            WHERE id = ?
            """,
            (
                name,
                customer_number,
                contact,
                billing_email,
                billing_street,
                billing_zip_city,
                document_email,
                access_host,
                branding_preset,
                plan,
                status,
                trial_ends_at,
                invoice_email_lang,
                portal_display_name,
                branding_accent_color,
                branding_logo_data,
                report_timezone,
                operating_sector,
                company_id,
            ),
        )

    def set_turnstile_endpoint(self, db, endpoint: str) -> None:
        db.execute("UPDATE settings SET turnstile_endpoint = ? WHERE id = 1", (endpoint,))

    def insert_company(
        self,
        db,
        *,
        company_id: str,
        name: str,
        customer_number: str,
        contact: str,
        billing_email: str,
        document_email: str,
        access_host: str,
        branding_preset: str,
        plan: str,
        status: str,
        trial_ends_at: str,
        invoice_email_lang: str,
        report_timezone: str,
        operating_sector: str,
    ) -> None:
        db.execute(
            """
            INSERT INTO companies (
                id, name, customer_number, contact, billing_email, document_email, access_host,
                branding_preset, plan, status, trial_ends_at, invoice_email_lang, report_timezone,
                operating_sector
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                name,
                customer_number,
                contact,
                billing_email,
                document_email,
                access_host,
                branding_preset,
                plan,
                status,
                trial_ends_at,
                invoice_email_lang,
                report_timezone,
                operating_sector,
            ),
        )

    def count_active_workers(self, db, company_id: str) -> int:
        row = db.execute(
            "SELECT COUNT(*) AS c FROM workers WHERE company_id = ? AND deleted_at IS NULL",
            (company_id,),
        ).fetchone()
        return int(row["c"]) if row else 0

    def soft_delete(self, db, company_id: str, *, deleted_at: str) -> None:
        db.execute(
            "UPDATE companies SET deleted_at = ?, status = ? WHERE id = ?",
            (deleted_at, "pausiert", company_id),
        )

    def restore(self, db, company_id: str) -> None:
        db.execute(
            "UPDATE companies SET deleted_at = NULL, status = ? WHERE id = ?",
            ("aktiv", company_id),
        )

    def get_review_row(self, db, company_id: str) -> dict[str, Any] | None:
        row = db.execute(
            "SELECT id, name, review_enabled FROM companies WHERE id = ?",
            (company_id,),
        ).fetchone()
        return dict(row) if row else None

    def set_review_access(
        self, db, company_id: str, *, review_enabled: int, review_token: str
    ) -> None:
        db.execute(
            "UPDATE companies SET review_enabled = ?, review_token = ? WHERE id = ?",
            (review_enabled, review_token, company_id),
        )

    def get_survey_prompt_row(self, db, company_id: str) -> dict[str, Any] | None:
        row = db.execute(
            "SELECT id, name, survey_prompt_enabled FROM companies WHERE id = ?",
            (company_id,),
        ).fetchone()
        return dict(row) if row else None

    def set_survey_prompt_enabled(self, db, company_id: str, *, enabled: int) -> None:
        db.execute(
            "UPDATE companies SET survey_prompt_enabled = ? WHERE id = ?",
            (enabled, company_id),
        )

    def get_plan(self, db, company_id: str) -> str | None:
        row = db.execute(
            "SELECT plan FROM companies WHERE id = ? AND deleted_at IS NULL",
            (company_id,),
        ).fetchone()
        return str(row["plan"] or "starter").strip().lower() if row else None

    def list_document_email_export_rows(self, db) -> list[dict[str, Any]]:
        rows = db.execute(
            """
            SELECT
                c.id,
                c.name,
                c.contact,
                c.billing_email,
                c.document_email,
                c.status,
                c.deleted_at,
                MAX(e.received_at) AS last_inbox_activity_at,
                SUM(CASE WHEN e.dismissed = 0 THEN 1 ELSE 0 END) AS open_inbox_count,
                SUM(CASE WHEN e.dismissed = 0 AND e.matched_company_id IS NULL
                    AND lower(e.to_addr) = lower(c.document_email) THEN 1 ELSE 0 END) AS unresolved_inbox_count
            FROM companies c
            LEFT JOIN email_inbox e ON (
                e.matched_company_id = c.id OR lower(e.to_addr) = lower(c.document_email)
            )
            GROUP BY c.id, c.name, c.contact, c.billing_email, c.document_email, c.status, c.deleted_at
            ORDER BY name
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def list_worker_ids(self, db, company_id: str) -> list[str]:
        rows = db.execute(
            "SELECT id FROM workers WHERE company_id = ?", (company_id,)
        ).fetchall()
        return [str(row["id"]) for row in rows]

    def delete_expired_worker_app_tokens(self, db, worker_id: str, now: str) -> int:
        result = db.execute(
            "DELETE FROM worker_app_tokens WHERE worker_id = ? AND expires_at < ?",
            (worker_id, now),
        )
        return int(result.rowcount)

    def delete_expired_worker_app_sessions(self, db, worker_id: str, now: str) -> int:
        result = db.execute(
            "DELETE FROM worker_app_sessions WHERE worker_id = ? AND expires_at < ?",
            (worker_id, now),
        )
        return int(result.rowcount)

    def workers_missing_badge(self, db, company_id: str) -> list[str]:
        rows = db.execute(
            """
            SELECT id FROM workers
            WHERE company_id = ? AND (badge_id IS NULL OR badge_id = '') AND deleted_at IS NULL
            """,
            (company_id,),
        ).fetchall()
        return [str(row["id"]) for row in rows]

    def set_worker_badge(
        self, db, worker_id: str, *, badge_id: str, badge_id_lookup: str
    ) -> None:
        db.execute(
            "UPDATE workers SET badge_id = ?, badge_id_lookup = ? WHERE id = ?",
            (badge_id, badge_id_lookup, worker_id),
        )

    def workers_invalid_status(self, db, company_id: str) -> list[str]:
        rows = db.execute(
            """
            SELECT id FROM workers
            WHERE company_id = ? AND status NOT IN ('aktiv','gesperrt','abgelaufen')
              AND deleted_at IS NULL
            """,
            (company_id,),
        ).fetchall()
        return [str(row["id"]) for row in rows]

    def fix_worker_status_active(self, db, worker_id: str) -> None:
        db.execute("UPDATE workers SET status = 'aktiv' WHERE id = ?", (worker_id,))

    def access_logs_month_for_company(
        self, db, company_id: str, month_prefix: str
    ) -> list[dict[str, Any]]:
        rows = db.execute(
            """
            SELECT al.worker_id, al.direction, al.timestamp,
                   w.first_name, w.last_name, w.badge_id, w.role AS worker_role
            FROM access_logs al
            JOIN workers w ON w.id = al.worker_id
            WHERE w.company_id = ?
              AND w.deleted_at IS NULL
              AND w.worker_type = 'worker'
              AND al.timestamp LIKE ?
            ORDER BY al.worker_id, al.timestamp
            """,
            (company_id, f"{month_prefix}%"),
        ).fetchall()
        return [dict(row) for row in rows]

    def access_logs_day_for_company(
        self, db, company_id: str, day_iso: str
    ) -> list[dict[str, Any]]:
        """Same columns as month query, filtered to a single calendar day (YYYY-MM-DD)."""
        day = str(day_iso or "").strip()[:10]
        if not day:
            return []
        rows = db.execute(
            """
            SELECT al.worker_id, al.direction, al.timestamp,
                   w.first_name, w.last_name, w.badge_id, w.role AS worker_role
            FROM access_logs al
            JOIN workers w ON w.id = al.worker_id
            WHERE w.company_id = ?
              AND w.deleted_at IS NULL
              AND w.worker_type = 'worker'
              AND al.timestamp LIKE ?
            ORDER BY al.worker_id, al.timestamp
            """,
            (company_id, f"{day}%"),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_worker_brief(
        self, db, worker_id: str, company_id: str
    ) -> dict[str, Any] | None:
        row = db.execute(
            """
            SELECT id, first_name, last_name, badge_id FROM workers
            WHERE id = ? AND company_id = ? AND deleted_at IS NULL
            """,
            (worker_id, company_id),
        ).fetchone()
        return dict(row) if row else None

    def access_logs_month_for_worker(
        self, db, worker_id: str, month_prefix: str
    ) -> list[dict[str, Any]]:
        rows = db.execute(
            """
            SELECT direction, gate, note, timestamp
            FROM access_logs
            WHERE worker_id = ? AND timestamp LIKE ?
            ORDER BY timestamp ASC
            """,
            (worker_id, f"{month_prefix}%"),
        ).fetchall()
        return [dict(row) for row in rows]

    def force_soft_delete(self, db, company_id: str, *, deleted_at: str) -> None:
        worker_rows = db.execute(
            "SELECT id FROM workers WHERE company_id = ?", (company_id,)
        ).fetchall()
        worker_ids = [row["id"] for row in worker_rows]

        db.execute(
            "UPDATE workers SET deleted_at = ?, status = 'gesperrt' WHERE company_id = ?",
            (deleted_at, company_id),
        )
        db.execute(
            "UPDATE subcompanies SET deleted_at = ?, status = 'pausiert' WHERE company_id = ?",
            (deleted_at, company_id),
        )
        db.execute(
            "UPDATE companies SET deleted_at = ?, status = ? WHERE id = ?",
            (deleted_at, "pausiert", company_id),
        )
        db.execute(
            "DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE company_id = ?)",
            (company_id,),
        )
        if worker_ids:
            placeholders = ",".join(["?"] * len(worker_ids))
            db.execute(
                f"DELETE FROM worker_app_tokens WHERE worker_id IN ({placeholders})",
                worker_ids,
            )
            db.execute(
                f"DELETE FROM worker_app_sessions WHERE worker_id IN ({placeholders})",
                worker_ids,
            )


class CompanyMailSettingsRepository:
    def get_row(self, db, company_id: str) -> dict[str, Any] | None:
        row = db.execute(
            "SELECT * FROM company_mail_settings WHERE company_id = ?",
            (company_id,),
        ).fetchone()
        return dict(row) if row else None

    def insert(self, db, values: dict[str, Any], *, now_value: str) -> None:
        db.execute(
            """
            INSERT INTO company_mail_settings (
                company_id, mail_provider,
                imap_host, imap_port, imap_username, imap_password, imap_use_tls,
                smtp_host, smtp_port, smtp_username, smtp_password, smtp_use_tls,
                brevo_api_key, sender_email, sender_name,
                last_test_inbound, last_test_outbound, test_inbound_status, test_outbound_status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["company_id"],
                values["mail_provider"],
                values["imap_host"],
                values["imap_port"],
                values["imap_username"],
                values["imap_password"],
                values["imap_use_tls"],
                values["smtp_host"],
                values["smtp_port"],
                values["smtp_username"],
                values["smtp_password"],
                values["smtp_use_tls"],
                values["brevo_api_key"],
                values["sender_email"],
                values["sender_name"],
                values["last_test_inbound"],
                values["last_test_outbound"],
                values["test_inbound_status"],
                values["test_outbound_status"],
                now_value,
                now_value,
            ),
        )

    def update(self, db, values: dict[str, Any], *, now_value: str, company_id: str) -> None:
        db.execute(
            """
            UPDATE company_mail_settings
            SET mail_provider = ?,
                imap_host = ?, imap_port = ?, imap_username = ?, imap_password = ?, imap_use_tls = ?,
                smtp_host = ?, smtp_port = ?, smtp_username = ?, smtp_password = ?, smtp_use_tls = ?,
                brevo_api_key = ?, sender_email = ?, sender_name = ?,
                updated_at = ?
            WHERE company_id = ?
            """,
            (
                values["mail_provider"],
                values["imap_host"],
                values["imap_port"],
                values["imap_username"],
                values["imap_password"],
                values["imap_use_tls"],
                values["smtp_host"],
                values["smtp_port"],
                values["smtp_username"],
                values["smtp_password"],
                values["smtp_use_tls"],
                values["brevo_api_key"],
                values["sender_email"],
                values["sender_name"],
                now_value,
                company_id,
            ),
        )

    def record_inbound_test(self, db, company_id: str, *, status: str, tested_at: str) -> None:
        db.execute(
            """
            UPDATE company_mail_settings
            SET test_inbound_status = ?, last_test_inbound = ?, updated_at = ?
            WHERE company_id = ?
            """,
            (status, tested_at, tested_at, company_id),
        )

    def record_outbound_test(self, db, company_id: str, *, status: str, tested_at: str) -> None:
        db.execute(
            """
            UPDATE company_mail_settings
            SET test_outbound_status = ?, last_test_outbound = ?, updated_at = ?
            WHERE company_id = ?
            """,
            (status, tested_at, tested_at, company_id),
        )


class UsersRepository:
    def username_taken(self, db, username: str) -> bool:
        return bool(db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone())

    def insert_user(
        self,
        db,
        *,
        user_id: str,
        username: str,
        password_hash: str,
        name: str,
        role: str,
        company_id: str,
        api_key_hash: str | None = None,
    ) -> None:
        if api_key_hash is not None:
            db.execute(
                """
                INSERT INTO users (id, username, password_hash, name, role, company_id, api_key_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, password_hash, name, role, company_id, api_key_hash),
            )
        else:
            db.execute(
                """
                INSERT INTO users (id, username, password_hash, name, role, company_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, password_hash, name, role, company_id),
            )

    def allocate_username(self, db, base: str) -> str:
        username = base
        suffix = 1
        while self.username_taken(db, username):
            username = f"{base}{suffix}"
            suffix += 1
        return username

    def count_turnstiles(self, db, company_id: str) -> int:
        row = db.execute(
            "SELECT COUNT(*) AS c FROM users WHERE company_id = ? AND role = 'turnstile'",
            (company_id,),
        ).fetchone()
        return int(row["c"]) if row else 0

    def list_turnstiles(self, db, company_id: str) -> list[dict[str, Any]]:
        rows = db.execute(
            """
            SELECT u.id, u.username, u.name, u.is_active,
                   CASE WHEN COALESCE(u.api_key_hash, '') != '' THEN 1 ELSE 0 END AS has_api_key,
                   MAX(s.last_seen) AS last_seen
            FROM users u
            LEFT JOIN sessions s ON s.user_id = u.id
            WHERE u.company_id = ? AND u.role = 'turnstile'
            GROUP BY u.id ORDER BY u.name
            """,
            (company_id,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "username": r["username"],
                "name": r["name"],
                "isActive": int(r["is_active"] or 1) == 1,
                "lastSeen": r["last_seen"],
                "hasApiKey": int(r["has_api_key"] or 0) == 1,
            }
            for r in rows
        ]

    def get_turnstile(self, db, company_id: str, user_id: str) -> dict[str, Any] | None:
        row = db.execute(
            "SELECT * FROM users WHERE id = ? AND company_id = ? AND role = 'turnstile'",
            (user_id, company_id),
        ).fetchone()
        return dict(row) if row else None

    def update_password_hash(self, db, user_id: str, password_hash: str) -> None:
        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (password_hash, user_id),
        )

    def update_api_key_hash(self, db, user_id: str, api_key_hash: str) -> None:
        db.execute(
            "UPDATE users SET api_key_hash = ? WHERE id = ?",
            (api_key_hash, user_id),
        )

    def set_active(self, db, user_id: str, is_active: int) -> None:
        db.execute("UPDATE users SET is_active = ? WHERE id = ?", (is_active, user_id))

    def delete_sessions(self, db, user_id: str) -> None:
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

    def get_company_admin(self, db, company_id: str) -> dict[str, Any] | None:
        row = db.execute(
            """
            SELECT id, username, email, twofa_enabled
            FROM users WHERE company_id = ? AND role = 'company-admin' LIMIT 1
            """,
            (company_id,),
        ).fetchone()
        return dict(row) if row else None

    def update_company_admin_security(
        self, db, user_id: str, *, email: str, twofa_enabled: int
    ) -> None:
        db.execute(
            "UPDATE users SET email = ?, twofa_enabled = ? WHERE id = ?",
            (email, twofa_enabled, user_id),
        )

    def delete_otp_codes(self, db, user_id: str) -> None:
        db.execute("DELETE FROM otp_codes WHERE user_id = ?", (user_id,))


class SubcompaniesRepository:
    def list_filtered(self, db, where_sql: str, params: list[Any]) -> list[dict[str, Any]]:
        rows = db.execute(f"SELECT * FROM subcompanies{where_sql} ORDER BY name", params).fetchall()
        return _rows_to_dicts(rows)

    def find_active_by_name(self, db, company_id: str, name: str) -> dict[str, Any] | None:
        row = db.execute(
            """
            SELECT * FROM subcompanies
            WHERE company_id = ? AND lower(name) = lower(?) AND deleted_at IS NULL
            """,
            (company_id, name),
        ).fetchone()
        return dict(row) if row else None

    def insert(
        self,
        db,
        *,
        subcompany_id: str,
        company_id: str,
        name: str,
        contact: str,
    ) -> None:
        db.execute(
            """
            INSERT INTO subcompanies (id, company_id, name, contact, status, deleted_at)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (subcompany_id, company_id, name, contact, "aktiv"),
        )

    def get_by_id(self, db, subcompany_id: str) -> dict[str, Any] | None:
        row = db.execute("SELECT * FROM subcompanies WHERE id = ?", (subcompany_id,)).fetchone()
        return dict(row) if row else None
