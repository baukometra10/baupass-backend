from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


DEFAULT_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "template_key": "permanent_full_time",
        "contract_type": "employment",
        "name": "Unbefristeter Vollzeitvertrag",
        "language": "de",
        "guidance_text": (
            "Erstelle einen vollständigen Arbeitsvertrag für eine unbefristete Vollzeitstelle in der gewählten Rechtsordnung. "
            "Branche und Tätigkeit sind branchenneutral zu formulieren (Handel, Dienstleistung, Produktion, Verwaltung usw.). "
            "Nutze klare juristische Sprache mit Abschnitten zu Parteien, Tätigkeit, Arbeitsort, Arbeitszeit, "
            "Vergütung (Monatsgehalt oder Stundenlohn gemäß Vorgabe), Probezeit, Urlaub, Verschwiegenheit, Datenschutz, Kündigung und Schlussbestimmungen."
        ),
        "required_fields_json": json.dumps(
            [
                "employee_name",
                "employee_gender",
                "employee_address",
                "job_title",
                "start_date",
                "work_location",
                "weekly_hours",
                "salary_gross_monthly",
                "vacation_days",
                "probation_months",
            ]
        ),
    },
    {
        "template_key": "temporary_fixed_term",
        "contract_type": "fixed_term",
        "name": "Befristeter Arbeitsvertrag",
        "language": "de",
        "guidance_text": (
            "Erstelle einen vollständigen befristeten Arbeitsvertrag in der gewählten Rechtsordnung. "
            "Die Tätigkeit ist branchenneutral zu beschreiben. Berücksichtige Befristung mit Start- und Enddatum, "
            "Arbeitszeit, Vergütung (Monatsgehalt oder Stundenlohn), Urlaub, Probezeit soweit zulässig, sowie Kündigungs- und Schlussklauseln."
        ),
        "required_fields_json": json.dumps(
            [
                "employee_name",
                "employee_gender",
                "employee_address",
                "job_title",
                "start_date",
                "end_date",
                "work_location",
                "weekly_hours",
                "salary_gross_monthly",
            ]
        ),
    },
    {
        "template_key": "mini_job",
        "contract_type": "mini_job",
        "name": "Minijob-Vertrag",
        "language": "de",
        "guidance_text": (
            "Erstelle einen Arbeitsvertrag für eine geringfügige Beschäftigung in der gewählten Rechtsordnung. "
            "Branche und Aufgaben sind neutral zu formulieren. Berücksichtige Vergütungsart (monatlich oder stündlich), "
            "Einsatzzeiten, Urlaub, Dokumentationspflichten und Datenschutz."
        ),
        "required_fields_json": json.dumps(
            [
                "employee_name",
                "employee_gender",
                "employee_address",
                "job_title",
                "start_date",
                "work_location",
                "hourly_rate",
                "monthly_cap",
            ]
        ),
    },
    {
        "template_key": "contract_amendment",
        "contract_type": "amendment",
        "name": "Vertragsänderung / Nachtrag",
        "language": "de",
        "guidance_text": (
            "Erstelle einen Nachtrag zur Änderung eines bestehenden Arbeitsverhältnisses (z. B. Gehalt, Arbeitszeit, "
            "Tätigkeit, Arbeitsort). Verweise auf das ursprüngliche Arbeitsverhältnis, nenne die geänderten Paragraphen "
            "klar und formuliere branchenneutral. Schlussbestimmung: übrige Vertragsbedingungen bleiben unverändert."
        ),
        "required_fields_json": json.dumps(
            [
                "employee_name",
                "employee_gender",
                "job_title",
                "start_date",
                "notes",
            ]
        ),
    },
    {
        "template_key": "retail_sales",
        "contract_type": "employment",
        "name": "Einzelhandel / Verkauf",
        "language": "de",
        "guidance_text": (
            "Arbeitsvertrag für Verkauf/Einzelhandel: Schichten, Kassenführung, Warenpflege, "
            "Kundenkontakt, ArbZG-Pausen, Vergütung, Urlaub, Kündigung — branchentypisch aber neutral formuliert."
        ),
        "required_fields_json": json.dumps(
            ["employee_name", "employee_gender", "employee_address", "job_title", "start_date", "work_location", "weekly_hours", "salary_gross_monthly"]
        ),
    },
    {
        "template_key": "healthcare_care",
        "contract_type": "employment",
        "name": "Gesundheitswesen / Pflege",
        "language": "de",
        "guidance_text": (
            "Arbeitsvertrag für Pflege/Gesundheitswesen: Schichtdienst, Schweigepflicht, Hygiene, "
            "Arbeitszeit, Vergütung nach Tarif/ Vereinbarung, Fortbildung, Kündigung."
        ),
        "required_fields_json": json.dumps(
            ["employee_name", "employee_gender", "employee_address", "job_title", "start_date", "work_location", "weekly_hours", "salary_gross_monthly"]
        ),
    },
    {
        "template_key": "logistics_warehouse",
        "contract_type": "employment",
        "name": "Logistik / Lager / Produktion",
        "language": "de",
        "guidance_text": (
            "Arbeitsvertrag für Lager, Logistik oder Produktion: Arbeitszeiten, Schichtmodelle, "
            "Arbeitsschutz, Vergütung (Stunden/Monat), Urlaub, Verschwiegenheit, Kündigung."
        ),
        "required_fields_json": json.dumps(
            ["employee_name", "employee_gender", "employee_address", "job_title", "start_date", "work_location", "weekly_hours", "salary_gross_monthly"]
        ),
    },
)


class ContractsRepository:
    def __init__(self, db):
        self.db = db

    def ensure_default_templates(self, company_id: str | None, actor_user_id: str | None = None) -> None:
        created_at = utc_now_iso()
        for item in DEFAULT_TEMPLATES:
            existing = self.db.execute(
                """
                SELECT id FROM contract_templates
                WHERE company_id IS ? AND template_key = ? AND language = ?
                """,
                (company_id, item["template_key"], item["language"]),
            ).fetchone()
            if existing:
                continue
            self.db.execute(
                """
                INSERT INTO contract_templates
                (id, company_id, template_key, contract_type, name, language, body_template, guidance_text,
                 required_fields_json, active, created_at, updated_at, created_by_user_id)
                VALUES (?, ?, ?, ?, ?, ?, '', ?, ?, 1, ?, ?, ?)
                """,
                (
                    f"ctpl-{uuid.uuid4().hex[:16]}",
                    company_id,
                    item["template_key"],
                    item["contract_type"],
                    item["name"],
                    item["language"],
                    item["guidance_text"],
                    item["required_fields_json"],
                    created_at,
                    created_at,
                    actor_user_id or "",
                ),
            )
        self.db.commit()

    def list_templates(self, company_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT *
            FROM contract_templates
            WHERE active = 1 AND (company_id IS NULL OR company_id = ?)
            ORDER BY company_id DESC, name COLLATE NOCASE
            """,
            (company_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_template(self, template_id: str, company_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            """
            SELECT *
            FROM contract_templates
            WHERE id = ? AND (company_id IS NULL OR company_id = ?)
            """,
            (template_id, company_id),
        ).fetchone()
        return dict(row) if row else None

    def create_contract(
        self,
        *,
        company_id: str,
        worker_id: str | None,
        template_id: str | None,
        contract_type: str,
        title: str,
        language: str,
        input_data: dict[str, Any],
        ai_prompt: str,
        draft_text: str,
        actor_user_id: str,
        parent_contract_id: str | None = None,
    ) -> str:
        contract_id = f"ctr-{uuid.uuid4().hex[:16]}"
        now = utc_now_iso()
        self.db.execute(
            """
            INSERT INTO employment_contracts
            (id, company_id, worker_id, template_id, contract_type, title, language, status, input_json,
             ai_prompt, draft_text, final_text, pdf_file_path, parent_contract_id, created_by_user_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, '', ?, ?, ?, ?)
            """,
            (
                contract_id,
                company_id,
                worker_id,
                template_id,
                contract_type,
                title,
                language,
                json.dumps(input_data, ensure_ascii=False),
                ai_prompt,
                draft_text,
                draft_text,
                parent_contract_id,
                actor_user_id,
                now,
                now,
            ),
        )
        self.db.commit()
        return contract_id

    def update_contract_text(
        self,
        contract_id: str,
        *,
        company_id: str,
        final_text: str,
        status: str = "final",
        pdf_file_path: str | None = None,
    ) -> None:
        now = utc_now_iso()
        self.db.execute(
            """
            UPDATE employment_contracts
            SET final_text = ?, status = ?, pdf_file_path = COALESCE(?, pdf_file_path), updated_at = ?
            WHERE id = ? AND company_id = ?
            """,
            (final_text, status, pdf_file_path, now, contract_id, company_id),
        )
        self.db.commit()

    def update_contract_full(
        self,
        contract_id: str,
        *,
        company_id: str,
        final_text: str | None = None,
        input_json: str | None = None,
        worker_id: str | None = None,
        title: str | None = None,
        language: str | None = None,
        status: str | None = None,
        pdf_file_path: str | None = None,
        clear_worker: bool = False,
        parent_contract_id: str | None = None,
        clear_parent: bool = False,
    ) -> None:
        now = utc_now_iso()
        sets = ["updated_at = ?"]
        params: list[Any] = [now]
        if final_text is not None:
            sets.append("final_text = ?")
            params.append(final_text)
        if input_json is not None:
            sets.append("input_json = ?")
            params.append(input_json)
        if clear_worker:
            sets.append("worker_id = NULL")
        elif worker_id is not None:
            sets.append("worker_id = ?")
            params.append(worker_id)
        if title is not None:
            sets.append("title = ?")
            params.append(title)
        if language is not None:
            sets.append("language = ?")
            params.append(language)
        if status is not None:
            sets.append("status = ?")
            params.append(status)
        if pdf_file_path is not None:
            sets.append("pdf_file_path = ?")
            params.append(pdf_file_path)
        if clear_parent:
            sets.append("parent_contract_id = NULL")
        elif parent_contract_id is not None:
            sets.append("parent_contract_id = ?")
            params.append(parent_contract_id or None)
        params.extend([contract_id, company_id])
        self.db.execute(
            f"""
            UPDATE employment_contracts
            SET {", ".join(sets)}
            WHERE id = ? AND company_id = ?
            """,
            tuple(params),
        )
        self.db.commit()

    def log_event(
        self,
        *,
        contract_id: str,
        company_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        actor_user_id: str | None = None,
    ) -> str:
        event_id = f"cev-{uuid.uuid4().hex[:16]}"
        now = utc_now_iso()
        self.db.execute(
            """
            INSERT INTO employment_contract_events
            (id, contract_id, company_id, actor_user_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                contract_id,
                company_id,
                actor_user_id or "",
                event_type,
                json.dumps(payload or {}, ensure_ascii=False),
                now,
            ),
        )
        self.db.commit()
        return event_id

    def list_events(self, contract_id: str, company_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT * FROM employment_contract_events
            WHERE contract_id = ? AND company_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (contract_id, company_id, max(1, min(limit, 200))),
        ).fetchall()
        return [dict(row) for row in rows]

    def expire_pending_sign_sessions(self, contract_id: str, company_id: str, role: str | None = None) -> int:
        if role:
            cur = self.db.execute(
                """
                UPDATE employment_contract_sign_sessions
                SET status = 'expired'
                WHERE contract_id = ? AND company_id = ? AND role = ? AND status = 'pending'
                """,
                (contract_id, company_id, role),
            )
        else:
            cur = self.db.execute(
                """
                UPDATE employment_contract_sign_sessions
                SET status = 'expired'
                WHERE contract_id = ? AND company_id = ? AND status = 'pending'
                """,
                (contract_id, company_id),
            )
        self.db.commit()
        return int(cur.rowcount or 0)

    def list_contracts(self, company_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT c.*, w.first_name, w.last_name
            FROM employment_contracts c
            LEFT JOIN workers w ON w.id = c.worker_id
            WHERE c.company_id = ?
            ORDER BY c.updated_at DESC
            """,
            (company_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_contracts_for_worker(self, worker_id: str, company_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT c.*, w.first_name, w.last_name
            FROM employment_contracts c
            LEFT JOIN workers w ON w.id = c.worker_id
            WHERE c.worker_id = ? AND c.company_id = ?
            ORDER BY c.updated_at DESC
            """,
            (worker_id, company_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_contract(self, contract_id: str, company_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            """
            SELECT c.*, w.first_name, w.last_name
            FROM employment_contracts c
            LEFT JOIN workers w ON w.id = c.worker_id
            WHERE c.id = ? AND c.company_id = ?
            """,
            (contract_id, company_id),
        ).fetchone()
        return dict(row) if row else None

    def delete_contract(self, contract_id: str, company_id: str) -> None:
        self.db.execute(
            "DELETE FROM employment_contract_sign_sessions WHERE contract_id = ? AND company_id = ?",
            (contract_id, company_id),
        )
        self.db.execute(
            "DELETE FROM employment_contract_events WHERE contract_id = ? AND company_id = ?",
            (contract_id, company_id),
        )
        self.db.execute(
            "DELETE FROM employment_contracts WHERE id = ? AND company_id = ?",
            (contract_id, company_id),
        )
        self.db.commit()

    def create_sign_session(
        self,
        *,
        contract_id: str,
        company_id: str,
        role: str,
        token: str,
        expires_at: str,
        created_by_user_id: str | None,
    ) -> dict[str, Any]:
        session_id = f"csn-{uuid.uuid4().hex[:16]}"
        now = utc_now_iso()
        self.db.execute(
            """
            INSERT INTO employment_contract_sign_sessions
            (id, contract_id, company_id, token, role, status, expires_at, created_by_user_id, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (session_id, contract_id, company_id, token, role, expires_at, created_by_user_id, now),
        )
        self.db.commit()
        return self.get_sign_session_by_token(token) or {}

    def get_sign_session_by_token(self, token: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM employment_contract_sign_sessions WHERE token = ?",
            (token,),
        ).fetchone()
        return dict(row) if row else None

    def list_sign_sessions(self, contract_id: str, company_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT * FROM employment_contract_sign_sessions
            WHERE contract_id = ? AND company_id = ?
            ORDER BY created_at DESC
            """,
            (contract_id, company_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_signed_sessions(self, contract_id: str, company_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT * FROM employment_contract_sign_sessions
            WHERE contract_id = ? AND company_id = ? AND status = 'signed'
            ORDER BY signed_at ASC
            """,
            (contract_id, company_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def submit_sign_session(
        self,
        token: str,
        *,
        signer_name: str,
        signature_data: str,
        sign_place: str,
        sign_latitude: float | None = None,
        sign_longitude: float | None = None,
        consent_accepted: bool = False,
    ) -> dict[str, Any] | None:
        session = self.get_sign_session_by_token(token)
        if not session:
            return None
        now = utc_now_iso()
        self.db.execute(
            """
            UPDATE employment_contract_sign_sessions
            SET status = 'signed', signer_name = ?, signature_data = ?, sign_place = ?, signed_at = ?,
                sign_latitude = ?, sign_longitude = ?, consent_accepted = ?
            WHERE token = ? AND status = 'pending'
            """,
            (
                signer_name,
                signature_data,
                sign_place,
                now,
                sign_latitude,
                sign_longitude,
                1 if consent_accepted else 0,
                token,
            ),
        )
        self.db.commit()
        return self.get_sign_session_by_token(token)

    def list_pending_sign_sessions_for_reminder(self, *, min_age_days: int = 3) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT s.*, c.title AS contract_title, c.language AS contract_language, c.worker_id
            FROM employment_contract_sign_sessions s
            JOIN employment_contracts c ON c.id = s.contract_id AND c.company_id = s.company_id
            WHERE s.status = 'pending'
              AND (s.reminder_sent_at IS NULL OR s.reminder_sent_at = '')
              AND datetime(s.created_at) <= datetime('now', ?)
              AND datetime(s.expires_at) > datetime('now')
            ORDER BY s.created_at ASC
            LIMIT 100
            """,
            (f"-{max(1, min(min_age_days, 30))} days",),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_sign_reminder_sent(self, session_id: str) -> None:
        now = utc_now_iso()
        self.db.execute(
            "UPDATE employment_contract_sign_sessions SET reminder_sent_at = ? WHERE id = ?",
            (now, session_id),
        )
        self.db.commit()
