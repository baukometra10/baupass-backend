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
                "employee_address",
                "job_title",
                "start_date",
                "work_location",
                "hourly_rate",
                "monthly_cap",
            ]
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
    ) -> str:
        contract_id = f"ctr-{uuid.uuid4().hex[:16]}"
        now = utc_now_iso()
        self.db.execute(
            """
            INSERT INTO employment_contracts
            (id, company_id, worker_id, template_id, contract_type, title, language, status, input_json,
             ai_prompt, draft_text, final_text, pdf_file_path, created_by_user_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, '', ?, ?, ?)
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
            "DELETE FROM employment_contract_events WHERE contract_id = ? AND company_id = ?",
            (contract_id, company_id),
        )
        self.db.execute(
            "DELETE FROM employment_contracts WHERE id = ? AND company_id = ?",
            (contract_id, company_id),
        )
        self.db.commit()
