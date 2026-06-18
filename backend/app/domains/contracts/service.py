from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.platform.ai.assistant import natural_language_query
from backend.app.platform.reports.contracts_pdf import build_employment_contract_pdf
from backend.app.platform.workforce.deployment_branding import resolve_company_pdf_branding

from .contract_locales import (
    build_ai_instructions,
    build_fallback_contract_body,
    default_currency_for_jurisdiction,
    document_title,
    normalize_jurisdiction,
    normalize_lang,
)
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
        form = dict(payload.get("form") or {})
        jurisdiction = normalize_jurisdiction(form.get("jurisdiction") or form.get("jurisdiction_country"))
        if not form.get("currency"):
            form["currency"] = default_currency_for_jurisdiction(jurisdiction)
        lang = normalize_lang(payload.get("language") or template.get("language"))
        input_data = {
            "company": company,
            "worker": worker,
            "form": form,
            "notes": str(payload.get("notes") or "").strip(),
        }
        prompt = self._build_contract_prompt(template, input_data, lang=lang, jurisdiction=jurisdiction)
        result = natural_language_query(company_id, prompt, input_data, mode="chat", lang=lang)
        draft_text = str(result.get("answer") or "").strip()
        if not draft_text:
            draft_text = self._fallback_contract_text(input_data, lang=lang, jurisdiction=jurisdiction)
        contract_title = str(
            payload.get("title")
            or document_title(lang, jurisdiction, template.get("name"))
        ).strip()
        contract_id = self.repo.create_contract(
            company_id=company_id,
            worker_id=worker_id,
            template_id=template_id,
            contract_type=str(template.get("contract_type") or "employment"),
            title=contract_title,
            language=lang,
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

    def delete_contract(self, contract_id: str, company_id: str, storage_root: Path | None = None) -> bool:
        contract = self.repo.get_contract(contract_id, company_id)
        if not contract:
            return False
        pdf_path = Path(str(contract.get("pdf_file_path") or ""))
        if storage_root and pdf_path.is_file():
            try:
                pdf_path.unlink()
            except OSError:
                pass
        elif pdf_path.is_file():
            try:
                pdf_path.unlink()
            except OSError:
                pass
        self.repo.delete_contract(contract_id, company_id)
        return True

    def update_contract(self, contract_id: str, company_id: str, final_text: str) -> dict[str, Any] | None:
        self.repo.update_contract_text(contract_id, company_id=company_id, final_text=final_text, status="final")
        return self.repo.get_contract(contract_id, company_id)

    def generate_contract_pdf(self, contract_id: str, company_id: str, storage_root: Path) -> tuple[dict[str, Any], bytes, Path]:
        contract = self.repo.get_contract(contract_id, company_id)
        if not contract:
            raise ValueError("contract_not_found")
        branding = resolve_company_pdf_branding(self.db, company_id)
        input_data: dict[str, Any] = {}
        raw_input = contract.get("input_json")
        if isinstance(raw_input, str) and raw_input.strip():
            try:
                input_data = json.loads(raw_input)
            except json.JSONDecodeError:
                input_data = {}
        elif isinstance(raw_input, dict):
            input_data = raw_input
        pdf_bytes = build_employment_contract_pdf(
            contract={
                **contract,
                "companyName": branding.get("companyName"),
                "final_text": contract.get("final_text") or contract.get("draft_text") or "",
                "input_data": input_data,
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

    def _build_contract_prompt(
        self,
        template: dict[str, Any],
        input_data: dict[str, Any],
        *,
        lang: str,
        jurisdiction: str,
    ) -> str:
        return json.dumps(
            {
                "task": "employment_contract_draft",
                "language": lang,
                "jurisdiction": jurisdiction,
                "template": {
                    "name": template.get("name"),
                    "type": template.get("contract_type"),
                    "guidance": template.get("guidance_text"),
                    "required_fields": json.loads(template.get("required_fields_json") or "[]"),
                },
                "input": input_data,
                "instructions": build_ai_instructions(lang, jurisdiction),
            },
            ensure_ascii=False,
        )

    def _fallback_contract_text(self, input_data: dict[str, Any], *, lang: str, jurisdiction: str) -> str:
        form = input_data.get("form") or {}
        notes = str(input_data.get("notes") or "").strip()
        return build_fallback_contract_body(
            lang=lang,
            jurisdiction=jurisdiction,
            form=form,
            notes=notes,
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
