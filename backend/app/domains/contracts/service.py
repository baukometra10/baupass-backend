from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.platform.ai.assistant import natural_language_query
from backend.app.platform.reports.contracts_pdf import build_employment_contract_pdf
from backend.app.platform.workforce.deployment_branding import resolve_company_pdf_branding

from .repository import ContractsRepository


class ContractsService:
    def __init__(self, db):
        self.db = db
        self.repo = ContractsRepository(db)

    def bootstrap_templates(self, company_id: str, actor_user_id: str | None = None) -> list[dict[str, Any]]:
        self.repo.ensure_default_templates(None, actor_user_id=actor_user_id)
        self.repo.ensure_default_templates(company_id, actor_user_id=actor_user_id)
        return self.repo.list_templates(company_id)

    def build_contract_draft(
        self,
        *,
        company_id: str,
        template_id: str,
        worker_id: str | None,
        actor_user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        template = self.repo.get_template(template_id, company_id)
        if not template:
            raise ValueError("template_not_found")
        worker = self._load_worker(worker_id, company_id) if worker_id else None
        company = self._load_company(company_id)
        input_data = {
            "company": company,
            "worker": worker,
            "form": payload.get("form") or {},
            "notes": str(payload.get("notes") or "").strip(),
        }
        prompt = self._build_contract_prompt(template, input_data)
        result = natural_language_query(company_id, prompt, input_data, mode="chat", lang=str(payload.get("language") or template.get("language") or "de")[:2])
        draft_text = str(result.get("answer") or "").strip()
        if not draft_text:
            draft_text = self._fallback_contract_text(template, input_data, str(payload.get("language") or template.get("language") or "de")[:2])
        contract_title = str(payload.get("title") or template.get("name") or "Arbeitsvertrag").strip()
        contract_id = self.repo.create_contract(
            company_id=company_id,
            worker_id=worker_id,
            template_id=template_id,
            contract_type=str(template.get("contract_type") or "employment"),
            title=contract_title,
            language=str(payload.get("language") or template.get("language") or "de")[:2],
            input_data=input_data,
            ai_prompt=prompt,
            draft_text=draft_text,
            actor_user_id=actor_user_id,
        )
        contract = self.repo.get_contract(contract_id, company_id)
        return {
            "contract": contract,
            "ai": {
                "configured": bool(result.get("configured")),
                "model": result.get("model"),
                "hint": result.get("hint"),
            },
        }

    def list_contracts(self, company_id: str) -> list[dict[str, Any]]:
        return self.repo.list_contracts(company_id)

    def get_contract(self, contract_id: str, company_id: str) -> dict[str, Any] | None:
        return self.repo.get_contract(contract_id, company_id)

    def update_contract(self, contract_id: str, company_id: str, final_text: str) -> dict[str, Any] | None:
        self.repo.update_contract_text(contract_id, company_id=company_id, final_text=final_text, status="final")
        return self.repo.get_contract(contract_id, company_id)

    def generate_contract_pdf(self, contract_id: str, company_id: str, storage_root: Path) -> tuple[dict[str, Any], bytes, Path]:
        contract = self.repo.get_contract(contract_id, company_id)
        if not contract:
            raise ValueError("contract_not_found")
        branding = resolve_company_pdf_branding(self.db, company_id)
        pdf_bytes = build_employment_contract_pdf(
            contract={
                **contract,
                "companyName": branding.get("companyName"),
                "final_text": contract.get("final_text") or contract.get("draft_text") or "",
            },
            branding=branding,
        )
        target_dir = storage_root / "contracts" / company_id
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{contract_id}.pdf"
        file_path = target_dir / safe_name
        file_path.write_bytes(pdf_bytes)
        stored_path = str(file_path)
        self.repo.update_contract_text(
            contract_id,
            company_id=company_id,
            final_text=str(contract.get("final_text") or contract.get("draft_text") or ""),
            status="final",
            pdf_file_path=stored_path,
        )
        updated = self.repo.get_contract(contract_id, company_id)
        return updated, pdf_bytes, file_path

    def _build_contract_prompt(self, template: dict[str, Any], input_data: dict[str, Any]) -> str:
        return json.dumps(
            {
                "task": "employment_contract_draft",
                "template": {
                    "name": template.get("name"),
                    "type": template.get("contract_type"),
                    "guidance": template.get("guidance_text"),
                    "required_fields": json.loads(template.get("required_fields_json") or "[]"),
                },
                "input": input_data,
                "instructions": [
                    "Generate a legally structured employment contract draft in the requested language.",
                    "Use section headings and complete sentences.",
                    "Do not invent company/employee facts that are not present; if missing, phrase neutrally.",
                    "Return only the final contract text without markdown fences.",
                ],
            },
            ensure_ascii=False,
        )

    def _fallback_contract_text(self, template: dict[str, Any], input_data: dict[str, Any], lang: str) -> str:
        company = input_data.get("company") or {}
        worker = input_data.get("worker") or {}
        form = input_data.get("form") or {}
        notes = str(input_data.get("notes") or "").strip()
        company_name = str(company.get("portal_display_name") or company.get("name") or "Unternehmen").strip()
        employee_name = (
            str(form.get("employee_name") or "").strip()
            or f"{str(worker.get('first_name') or '').strip()} {str(worker.get('last_name') or '').strip()}".strip()
            or "Mitarbeiter"
        )
        job_title = str(form.get("job_title") or worker.get("role") or "Position").strip()
        work_location = str(form.get("work_location") or worker.get("site") or "Arbeitsort").strip()
        start_date = str(form.get("start_date") or "").strip() or "nach Vereinbarung"
        weekly_hours = str(form.get("weekly_hours") or "").strip() or "nach Vereinbarung"
        salary = str(form.get("salary_gross_monthly") or form.get("hourly_rate") or "").strip() or "nach Vereinbarung"
        title = str(template.get("name") or "Arbeitsvertrag").strip()

        if lang == "ar":
            return (
                f"{title}\n\n"
                f"بين شركة {company_name} والموظف {employee_name} لوظيفة {job_title}.\n\n"
                f"1. بداية العمل: {start_date}\n"
                f"2. مكان العمل: {work_location}\n"
                f"3. ساعات العمل الأسبوعية: {weekly_hours}\n"
                f"4. الأجر: {salary}\n"
                f"5. ملاحظات إضافية: {notes or 'لا توجد ملاحظات إضافية.'}\n\n"
                "يجب مراجعة هذا النص قانونيًا قبل الاستخدام النهائي."
            )
        if lang == "en":
            return (
                f"{title}\n\n"
                f"Between {company_name} and employee {employee_name} for the role of {job_title}.\n\n"
                f"1. Start date: {start_date}\n"
                f"2. Work location: {work_location}\n"
                f"3. Weekly working hours: {weekly_hours}\n"
                f"4. Compensation: {salary}\n"
                f"5. Additional notes: {notes or 'No additional notes.'}\n\n"
                "This draft should be legally reviewed before final use."
            )
        return (
            f"{title}\n\n"
            f"Zwischen der Firma {company_name} und dem Arbeitnehmer {employee_name} für die Position {job_title}.\n\n"
            f"1. Arbeitsbeginn: {start_date}\n"
            f"2. Arbeitsort: {work_location}\n"
            f"3. Wöchentliche Arbeitszeit: {weekly_hours}\n"
            f"4. Vergütung: {salary}\n"
            f"5. Zusätzliche Hinweise: {notes or 'Keine weiteren Hinweise.'}\n\n"
            "Dieser Vertragsentwurf sollte vor der finalen Verwendung rechtlich geprüft werden."
        )

    def _load_company(self, company_id: str) -> dict[str, Any]:
        row = self.db.execute(
            """
            SELECT id, name, portal_display_name, contact, status, billing_email, document_email
            FROM companies WHERE id = ?
            """,
            (company_id,),
        ).fetchone()
        return dict(row) if row else {"id": company_id}

    def _load_worker(self, worker_id: str, company_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            """
            SELECT id, company_id, first_name, last_name, role, site, contact_email, status
            FROM workers WHERE id = ? AND company_id = ?
            """,
            (worker_id, company_id),
        ).fetchone()
        return dict(row) if row else None
