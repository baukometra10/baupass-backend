from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
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
        signatures = self._signatures_for_pdf(contract_id, company_id)
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
            signatures=signatures,
        )
        target_dir = storage_root / "contracts" / company_id
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{contract_id}.pdf"
        file_path = target_dir / safe_name
        file_path.write_bytes(pdf_bytes)
        stored_path = str(file_path)
        status = "signed" if len(signatures) >= 2 else "final"
        self.repo.update_contract_text(
            contract_id,
            company_id=company_id,
            final_text=str(contract.get("final_text") or contract.get("draft_text") or ""),
            status=status,
            pdf_file_path=stored_path,
        )
        updated = self.repo.get_contract(contract_id, company_id)
        return updated, pdf_bytes, file_path

    def create_sign_invite(
        self,
        contract_id: str,
        company_id: str,
        *,
        role: str,
        actor_user_id: str,
        expires_days: int = 14,
    ) -> dict[str, Any]:
        role_code = str(role or "").strip().lower()
        if role_code not in {"employer", "employee"}:
            raise ValueError("invalid_sign_role")
        contract = self.repo.get_contract(contract_id, company_id)
        if not contract:
            raise ValueError("contract_not_found")
        final_text = str(contract.get("final_text") or contract.get("draft_text") or "").strip()
        if not final_text:
            raise ValueError("contract_text_required")
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(days=max(1, min(expires_days, 90)))).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        session = self.repo.create_sign_session(
            contract_id=contract_id,
            company_id=company_id,
            role=role_code,
            token=token,
            expires_at=expires_at,
            created_by_user_id=actor_user_id,
        )
        return {
            "session": session,
            "token": token,
            "signUrl": f"/contract-sign.html?token={token}",
        }

    def get_public_sign_view(self, token: str) -> dict[str, Any] | None:
        session = self.repo.get_sign_session_by_token(token)
        if not session:
            return None
        if str(session.get("status") or "") == "pending" and self._session_expired(session):
            return {"error": "sign_link_expired"}

        contract = self.repo.get_contract(str(session["contract_id"]), str(session["company_id"]))
        if not contract:
            return None
        branding = resolve_company_pdf_branding(self.db, str(session["company_id"]))
        input_data = self._parse_contract_input(contract)
        form = input_data.get("form") or {}
        lang = normalize_lang(contract.get("language"))
        return {
            "token": token,
            "role": session.get("role"),
            "status": session.get("status"),
            "signerName": session.get("signer_name") or "",
            "signedAt": session.get("signed_at"),
            "expiresAt": session.get("expires_at"),
            "companyName": branding.get("companyName"),
            "logoData": branding.get("logoData"),
            "title": contract.get("title") or document_title(lang, normalize_jurisdiction(form.get("jurisdiction"))),
            "language": lang,
            "contractText": str(contract.get("final_text") or contract.get("draft_text") or ""),
            "employeeName": str(form.get("employee_name") or "").strip(),
            "downloadReady": str(session.get("status") or "") == "signed",
        }

    def submit_public_signature(
        self,
        token: str,
        *,
        signer_name: str,
        signature_data: str,
        sign_place: str,
        storage_root: Path,
    ) -> dict[str, Any]:
        session = self.repo.get_sign_session_by_token(token)
        if not session:
            raise ValueError("sign_session_not_found")
        if str(session.get("status") or "") == "signed":
            raise ValueError("already_signed")
        if self._session_expired(session):
            raise ValueError("sign_link_expired")
        name = str(signer_name or "").strip()
        sig = str(signature_data or "").strip()
        if not name:
            raise ValueError("signer_name_required")
        updated = self.repo.submit_sign_session(
            token,
            signer_name=name,
            signature_data=sig,
            sign_place=str(sign_place or "").strip(),
        )
        if not updated:
            raise ValueError("sign_failed")
        contract_id = str(session["contract_id"])
        company_id = str(session["company_id"])
        self.generate_contract_pdf(contract_id, company_id, storage_root)
        contract = self.repo.get_contract(contract_id, company_id)
        return {
            "ok": True,
            "session": updated,
            "contract": contract,
            "download": f"/api/public/contracts/sign/{token}/download.pdf",
        }

    def list_sign_sessions(self, contract_id: str, company_id: str) -> list[dict[str, Any]]:
        return self.repo.list_sign_sessions(contract_id, company_id)

    def _signatures_for_pdf(self, contract_id: str, company_id: str) -> dict[str, Any]:
        signed = self.repo.get_signed_sessions(contract_id, company_id)
        out: dict[str, Any] = {}
        for row in signed:
            role = str(row.get("role") or "").strip().lower()
            if role not in {"employer", "employee"}:
                continue
            out[role] = {
                "signer_name": row.get("signer_name") or "",
                "signature_data": row.get("signature_data") or "",
                "sign_place": row.get("sign_place") or "",
                "signed_at": row.get("signed_at") or "",
            }
        return out

    @staticmethod
    def _session_expired(session: dict[str, Any]) -> bool:
        raw = str(session.get("expires_at") or "").strip()
        if not raw:
            return False
        try:
            expires = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return False
        return datetime.now(timezone.utc) > expires

    @staticmethod
    def _parse_contract_input(contract: dict[str, Any]) -> dict[str, Any]:
        raw = contract.get("input_json")
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip():
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}
        return {}

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
