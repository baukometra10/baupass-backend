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
from .validation import extract_form_from_input, normalize_contract_form, validate_contract_form


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
            parent_contract_id=str(payload.get("parent_contract_id") or "").strip() or None,
        )
        self.repo.log_event(
            contract_id=contract_id,
            company_id=company_id,
            event_type="contract.created",
            payload={"template_id": template_id, "worker_id": worker_id},
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

    def rebuild_contract_draft(
        self,
        contract_id: str,
        company_id: str,
        *,
        actor_user_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        contract = self.repo.get_contract(contract_id, company_id)
        if not contract:
            raise ValueError("contract_not_found")
        template_id = str(payload.get("template_id") or contract.get("template_id") or "").strip()
        template = self.repo.get_template(template_id, company_id) if template_id else None
        if not template:
            raise ValueError("template_not_found")
        input_data = self._parse_contract_input(contract)
        form_patch = dict(payload.get("form") or {})
        if form_patch:
            input_data["form"] = normalize_contract_form({**(input_data.get("form") or {}), **form_patch})
        if "notes" in payload:
            input_data["notes"] = str(payload.get("notes") or "").strip()
        existing_text = str(
            payload.get("existing_text")
            or contract.get("final_text")
            or contract.get("draft_text")
            or ""
        ).strip()
        if existing_text:
            input_data["existing_text"] = existing_text
        worker_id = str(payload.get("worker_id") or contract.get("worker_id") or "").strip() or None
        if worker_id:
            worker = self._load_worker(worker_id, company_id)
            if worker:
                input_data["worker"] = worker
        input_data["company"] = self._load_company(company_id)
        form = input_data.get("form") or {}
        jurisdiction = normalize_jurisdiction(form.get("jurisdiction") or form.get("jurisdiction_country"))
        if not form.get("currency"):
            form["currency"] = default_currency_for_jurisdiction(jurisdiction)
            input_data["form"] = form
        lang = normalize_lang(payload.get("language") or contract.get("language") or template.get("language"))
        title = str(payload.get("title") or contract.get("title") or document_title(lang, jurisdiction, template.get("name"))).strip()
        parent_contract_id = str(payload.get("parent_contract_id") or contract.get("parent_contract_id") or "").strip() or None
        prompt = self._build_contract_prompt(template, input_data, lang=lang, jurisdiction=jurisdiction, regenerate=bool(existing_text))
        result = natural_language_query(company_id, prompt, input_data, mode="chat", lang=lang)
        draft_text = str(result.get("answer") or "").strip()
        if not draft_text:
            draft_text = self._fallback_contract_text(input_data, lang=lang, jurisdiction=jurisdiction)
        self.repo.update_contract_full(
            contract_id,
            company_id=company_id,
            draft_text=draft_text,
            final_text=draft_text,
            ai_prompt=prompt,
            input_json=json.dumps(input_data, ensure_ascii=False),
            worker_id=worker_id,
            title=title,
            language=lang,
            status="draft",
            clear_worker=bool(payload.get("worker_id") == ""),
            parent_contract_id=parent_contract_id,
            clear_parent=bool(payload.get("parent_contract_id") == ""),
        )
        self.repo.log_event(
            contract_id=contract_id,
            company_id=company_id,
            event_type="contract.regenerated",
            payload={"template_id": template_id, "worker_id": worker_id},
            actor_user_id=actor_user_id,
        )
        if worker_id and input_data.get("form"):
            self._sync_worker_from_contract_form(worker_id, company_id, input_data["form"])
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
        rows = self.repo.list_contracts(company_id)
        return [self._enrich_contract_summary(row) for row in rows]

    def get_contract(self, contract_id: str, company_id: str) -> dict[str, Any] | None:
        contract = self.repo.get_contract(contract_id, company_id)
        if not contract:
            return None
        enriched = self._enrich_contract_summary(contract)
        enriched["sign_sessions"] = self._serialize_sign_sessions(
            self.repo.list_sign_sessions(contract_id, company_id)
        )
        enriched["events"] = self.repo.list_events(contract_id, company_id, limit=20)
        return enriched

    def list_contracts_for_worker(self, worker_id: str, company_id: str) -> list[dict[str, Any]]:
        rows = self.repo.list_contracts_for_worker(worker_id, company_id)
        return [self._enrich_contract_summary(row) for row in rows]

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

    def update_contract(
        self,
        contract_id: str,
        company_id: str,
        *,
        final_text: str,
        payload: dict[str, Any] | None = None,
        actor_user_id: str | None = None,
    ) -> dict[str, Any] | None:
        contract = self.repo.get_contract(contract_id, company_id)
        if not contract:
            return None
        input_data = self._parse_contract_input(contract)
        worker_id = contract.get("worker_id")
        title = contract.get("title")
        language = contract.get("language")
        parent_contract_id = contract.get("parent_contract_id")
        if payload:
            form_patch = dict((payload.get("form") or {}))
            if form_patch:
                merged_form = normalize_contract_form(
                    {**(input_data.get("form") or {}), **form_patch}
                )
                input_data["form"] = merged_form
            if "notes" in payload:
                input_data["notes"] = str(payload.get("notes") or "").strip()
            if payload.get("worker_id") is not None:
                worker_id = str(payload.get("worker_id") or "").strip() or None
            if payload.get("title"):
                title = str(payload.get("title")).strip()
            if payload.get("language"):
                language = normalize_lang(payload.get("language"))
            if payload.get("parent_contract_id") is not None:
                parent_contract_id = str(payload.get("parent_contract_id") or "").strip() or None
            if payload.get("company_id"):
                input_data["company"] = self._load_company(company_id)
            if worker_id:
                worker = self._load_worker(worker_id, company_id)
                if worker:
                    input_data["worker"] = worker
        self.repo.update_contract_full(
            contract_id,
            company_id=company_id,
            final_text=final_text,
            input_json=json.dumps(input_data, ensure_ascii=False),
            worker_id=worker_id,
            title=str(title or ""),
            language=str(language or "de"),
            status="final",
            clear_worker=bool(payload and payload.get("worker_id") == ""),
            parent_contract_id=parent_contract_id,
            clear_parent=bool(payload and payload.get("parent_contract_id") == ""),
        )
        self.repo.log_event(
            contract_id=contract_id,
            company_id=company_id,
            event_type="contract.updated",
            payload={"fields_updated": list((payload or {}).keys())},
            actor_user_id=actor_user_id,
        )
        if worker_id and input_data.get("form"):
            self._sync_worker_from_contract_form(worker_id, company_id, input_data["form"])
        return self.repo.get_contract(contract_id, company_id)

    def validate_contract_ready(
        self,
        contract_id: str,
        company_id: str,
        *,
        form_override: dict[str, Any] | None = None,
    ) -> list[str]:
        contract = self.repo.get_contract(contract_id, company_id)
        if not contract:
            raise ValueError("contract_not_found")
        input_data = self._parse_contract_input(contract)
        form = extract_form_from_input(input_data)
        if form_override:
            form = normalize_contract_form({**form, **dict(form_override)})
        lang = normalize_lang(contract.get("language"))
        template = None
        if contract.get("template_id"):
            template = self.repo.get_template(str(contract["template_id"]), company_id)
        return validate_contract_form(form, template=template, lang=lang)

    def generate_contract_pdf(
        self,
        contract_id: str,
        company_id: str,
        storage_root: Path,
        *,
        payload: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bytes, Path]:
        self._apply_action_payload(contract_id, company_id, payload)
        form_override = dict((payload or {}).get("form") or {})
        missing = self.validate_contract_ready(contract_id, company_id, form_override=form_override or None)
        if missing:
            raise ValueError(f"missing_fields:{','.join(missing)}")
        contract = self.repo.get_contract(contract_id, company_id)
        if not contract:
            raise ValueError("contract_not_found")
        branding = resolve_company_pdf_branding(self.db, company_id)
        signatures = self._signatures_for_pdf(contract_id, company_id)
        input_data = self._parse_contract_input(contract)
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
        self.repo.update_contract_full(
            contract_id,
            company_id=company_id,
            status=status,
            pdf_file_path=stored_path,
        )
        self.repo.log_event(
            contract_id=contract_id,
            company_id=company_id,
            event_type="contract.pdf_generated",
            payload={"signed_count": len(signatures)},
        )
        updated = self.repo.get_contract(contract_id, company_id)
        return updated, pdf_bytes, file_path

    def build_preview_pdf_bytes(self, contract_id: str, company_id: str) -> bytes:
        contract = self.repo.get_contract(contract_id, company_id)
        if not contract:
            raise ValueError("contract_not_found")
        branding = resolve_company_pdf_branding(self.db, company_id)
        input_data = self._parse_contract_input(contract)
        return build_employment_contract_pdf(
            contract={
                **contract,
                "companyName": branding.get("companyName"),
                "final_text": contract.get("final_text") or contract.get("draft_text") or "",
                "input_data": input_data,
            },
            branding=branding,
            signatures=self._signatures_for_pdf(contract_id, company_id),
        )

    def build_public_preview_pdf_bytes(self, token: str) -> bytes:
        session = self.repo.get_sign_session_by_token(token)
        if not session:
            raise ValueError("sign_session_not_found")
        if str(session.get("status") or "") == "expired":
            raise ValueError("sign_link_expired")
        if str(session.get("status") or "") == "pending" and self._session_expired(session):
            raise ValueError("sign_link_expired")
        return self.build_preview_pdf_bytes(str(session["contract_id"]), str(session["company_id"]))

    def create_sign_invite(
        self,
        contract_id: str,
        company_id: str,
        *,
        role: str,
        actor_user_id: str,
        expires_days: int = 14,
        renew: bool = False,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._apply_action_payload(contract_id, company_id, payload)
        role_code = str(role or "").strip().lower()
        if role_code not in {"employer", "employee"}:
            raise ValueError("invalid_sign_role")
        contract = self.repo.get_contract(contract_id, company_id)
        if not contract:
            raise ValueError("contract_not_found")
        final_text = str(contract.get("final_text") or contract.get("draft_text") or "").strip()
        if not final_text:
            raise ValueError("contract_text_required")
        form_override = dict((payload or {}).get("form") or {})
        missing = self.validate_contract_ready(contract_id, company_id, form_override=form_override or None)
        if missing:
            raise ValueError(f"missing_fields:{','.join(missing)}")
        if renew:
            self.repo.expire_pending_sign_sessions(contract_id, company_id, role_code)
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
        self.repo.log_event(
            contract_id=contract_id,
            company_id=company_id,
            event_type="sign_link.created",
            payload={"role": role_code, "expires_at": expires_at, "renew": renew},
            actor_user_id=actor_user_id,
        )
        result = {
            "session": session,
            "token": token,
            "signUrl": f"/contract-sign.html?token={token}",
        }
        return result

    def send_sign_invite_sms(
        self,
        contract_id: str,
        company_id: str,
        *,
        role: str,
        actor_user_id: str,
        phone: str | None = None,
        renew: bool = False,
        base_url: str = "",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        invite = self.create_sign_invite(
            contract_id,
            company_id,
            role=role,
            actor_user_id=actor_user_id,
            renew=renew,
            payload=payload,
        )
        contract = self.repo.get_contract(contract_id, company_id)
        if not contract:
            raise ValueError("contract_not_found")
        input_data = self._parse_contract_input(contract)
        form = input_data.get("form") or {}
        recipient = str(phone or form.get("employee_phone") or "").strip()
        worker_id = contract.get("worker_id")
        if not recipient and role == "employee" and worker_id:
            worker = self._load_worker(str(worker_id), company_id)
            recipient = str((worker or {}).get("contact_phone") or "").strip()
        if not recipient:
            raise ValueError("recipient_phone_required")
        absolute_url = f"{base_url.rstrip('/')}{invite['signUrl']}"
        lang = normalize_lang(contract.get("language"))
        title = str(contract.get("title") or document_title(lang, normalize_jurisdiction(form.get("jurisdiction"))))
        body = self._sign_invite_sms_body(lang=lang, contract_title=title, sign_url=absolute_url)
        from backend.app.platform.notifications.sms import send_sms

        ok, err = send_sms(to=recipient, body=body)
        if not ok:
            raise ValueError(err or "sms_send_failed")
        self.repo.log_event(
            contract_id=contract_id,
            company_id=company_id,
            event_type="sign_link.sms",
            payload={"role": role, "recipient": recipient},
            actor_user_id=actor_user_id,
        )
        if role == "employee" and worker_id:
            self._push_contract_sign_invite(str(worker_id), contract, absolute_url)
        return {**invite, "absoluteUrl": absolute_url, "smsSent": True, "recipient": recipient}

    def send_sign_invite_email(
        self,
        contract_id: str,
        company_id: str,
        *,
        role: str,
        actor_user_id: str,
        email: str | None = None,
        renew: bool = False,
        base_url: str = "",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        invite = self.create_sign_invite(
            contract_id,
            company_id,
            role=role,
            actor_user_id=actor_user_id,
            renew=renew,
            payload=payload,
        )
        contract = self.repo.get_contract(contract_id, company_id)
        if not contract:
            raise ValueError("contract_not_found")
        input_data = self._parse_contract_input(contract)
        form = input_data.get("form") or {}
        recipient = str(email or form.get("employee_email") or "").strip()
        worker_id = contract.get("worker_id")
        if not recipient and role == "employee" and worker_id:
            worker = self._load_worker(str(worker_id), company_id)
            recipient = str((worker or {}).get("contact_email") or "").strip()
        if role == "employer" and not recipient:
            company = self._load_company(company_id)
            recipient = str(company.get("document_email") or company.get("billing_email") or "").strip()
        if not recipient or "@" not in recipient:
            raise ValueError("recipient_email_required")
        absolute_url = f"{base_url.rstrip('/')}{invite['signUrl']}"
        lang = normalize_lang(contract.get("language"))
        title = str(contract.get("title") or document_title(lang, normalize_jurisdiction(form.get("jurisdiction"))))
        subject, text_body, html_body = self._sign_invite_email_bodies(
            lang=lang,
            role=role,
            company_name=str(self._load_company(company_id).get("name") or "SUPPIX"),
            contract_title=title,
            sign_url=absolute_url,
            expires_at=str((invite.get("session") or {}).get("expires_at") or ""),
        )
        sent = self._send_email(recipient, subject, text_body, html_body)
        if not sent:
            raise ValueError("mail_send_failed")
        self.repo.log_event(
            contract_id=contract_id,
            company_id=company_id,
            event_type="sign_link.emailed",
            payload={"role": role, "recipient": recipient},
            actor_user_id=actor_user_id,
        )
        if role == "employee" and worker_id:
            self._push_contract_sign_invite(str(worker_id), contract, absolute_url)
        return {**invite, "absoluteUrl": absolute_url, "emailSent": True, "recipient": recipient}

    def get_public_sign_view(self, token: str) -> dict[str, Any] | None:
        session = self.repo.get_sign_session_by_token(token)
        if not session:
            return None
        if str(session.get("status") or "") == "expired":
            return {"error": "sign_link_expired"}
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
            "previewPdfUrl": f"/api/public/contracts/sign/{token}/preview.pdf",
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
        consent_accepted: bool = False,
        sign_latitude: float | None = None,
        sign_longitude: float | None = None,
    ) -> dict[str, Any]:
        session = self.repo.get_sign_session_by_token(token)
        if not session:
            raise ValueError("sign_session_not_found")
        if str(session.get("status") or "") == "signed":
            raise ValueError("already_signed")
        if str(session.get("status") or "") == "expired":
            raise ValueError("sign_link_expired")
        if self._session_expired(session):
            raise ValueError("sign_link_expired")
        if not consent_accepted:
            raise ValueError("consent_required")
        name = str(signer_name or "").strip()
        sig = str(signature_data or "").strip()
        if not name:
            raise ValueError("signer_name_required")
        updated = self.repo.submit_sign_session(
            token,
            signer_name=name,
            signature_data=sig,
            sign_place=str(sign_place or "").strip(),
            sign_latitude=sign_latitude,
            sign_longitude=sign_longitude,
            consent_accepted=consent_accepted,
        )
        if not updated:
            raise ValueError("sign_failed")
        contract_id = str(session["contract_id"])
        company_id = str(session["company_id"])
        role = str(session.get("role") or "").strip().lower()
        self.repo.log_event(
            contract_id=contract_id,
            company_id=company_id,
            event_type="contract.signed",
            payload={
                "role": role,
                "signer_name": name,
                "sign_latitude": sign_latitude,
                "sign_longitude": sign_longitude,
                "consent_accepted": consent_accepted,
            },
        )
        self.generate_contract_pdf(contract_id, company_id, storage_root)
        contract = self.repo.get_contract(contract_id, company_id)
        self._notify_counterparty_signed(contract, role=role, company_id=company_id)
        return {
            "ok": True,
            "session": updated,
            "contract": contract,
            "download": f"/api/public/contracts/sign/{token}/download.pdf",
        }

    def list_sign_sessions(self, contract_id: str, company_id: str) -> list[dict[str, Any]]:
        return self._serialize_sign_sessions(self.repo.list_sign_sessions(contract_id, company_id))

    def list_contract_events(self, contract_id: str, company_id: str) -> list[dict[str, Any]]:
        return self.repo.list_events(contract_id, company_id)

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

    def _enrich_contract_summary(self, contract: dict[str, Any]) -> dict[str, Any]:
        contract_id = str(contract.get("id") or "")
        company_id = str(contract.get("company_id") or "")
        sessions = self.repo.list_sign_sessions(contract_id, company_id) if contract_id and company_id else []
        signed_roles = {
            str(row.get("role") or "").lower()
            for row in sessions
            if str(row.get("status") or "") == "signed"
        }
        pending = [
            row for row in sessions
            if str(row.get("status") or "") == "pending" and not self._session_expired(row)
        ]
        expired_pending = [
            row for row in sessions
            if str(row.get("status") or "") == "pending" and self._session_expired(row)
        ]
        sign_status = "draft"
        status = str(contract.get("status") or "draft")
        if status == "signed" or signed_roles >= {"employer", "employee"}:
            sign_status = "fully_signed"
        elif signed_roles:
            sign_status = "partially_signed"
        elif pending:
            sign_status = "awaiting_signature"
        elif status == "final":
            sign_status = "ready"
        return {
            **contract,
            "signStatus": sign_status,
            "signedRoles": sorted(signed_roles),
            "pendingSignCount": len(pending),
            "expiredSignCount": len(expired_pending),
        }

    @staticmethod
    def _serialize_sign_sessions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for row in rows:
            item = dict(row)
            status = str(item.get("status") or "")
            if status == "pending" and ContractsService._session_expired(item):
                item["effectiveStatus"] = "expired"
            else:
                item["effectiveStatus"] = status or "pending"
            item.pop("signature_data", None)
            item.pop("token", None)
            out.append(item)
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

    def _apply_action_payload(
        self,
        contract_id: str,
        company_id: str,
        payload: dict[str, Any] | None,
    ) -> None:
        payload = payload or {}
        form_patch = payload.get("form")
        final_text = payload.get("final_text")
        if not form_patch and final_text is None:
            return
        contract = self.repo.get_contract(contract_id, company_id)
        if not contract:
            raise ValueError("contract_not_found")
        input_data = self._parse_contract_input(contract)
        if form_patch:
            input_data["form"] = normalize_contract_form(
                {**(input_data.get("form") or {}), **dict(form_patch)}
            )
        self.repo.update_contract_full(
            contract_id,
            company_id=company_id,
            final_text=str(final_text).strip() if final_text is not None else None,
            input_json=json.dumps(input_data, ensure_ascii=False),
        )

    def _build_contract_prompt(
        self,
        template: dict[str, Any],
        input_data: dict[str, Any],
        *,
        lang: str,
        jurisdiction: str,
        regenerate: bool = False,
    ) -> str:
        instructions = build_ai_instructions(lang, jurisdiction)
        if regenerate or input_data.get("existing_text"):
            instructions = [
                *instructions,
                "Revise the existing contract text in place using the admin notes and updated form fields.",
                "Do not create a separate or duplicate contract — return the full updated contract body only.",
            ]
        return json.dumps(
            {
                "task": "employment_contract_draft",
                "language": lang,
                "jurisdiction": jurisdiction,
                "regenerate": bool(regenerate or input_data.get("existing_text")),
                "template": {
                    "name": template.get("name"),
                    "type": template.get("contract_type"),
                    "guidance": template.get("guidance_text"),
                    "required_fields": json.loads(template.get("required_fields_json") or "[]"),
                },
                "input": input_data,
                "instructions": instructions,
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
            SELECT id, company_id, first_name, last_name, role, site, contact_email, contact_phone,
                   home_address, birth_date, gender, status
            FROM workers WHERE id = ? AND company_id = ?
            """,
            (worker_id, company_id),
        ).fetchone()
        return dict(row) if row else None

    def _sync_worker_from_contract_form(self, worker_id: str, company_id: str, form: dict[str, Any]) -> None:
        from backend.app.domains.workers.service import WorkersService

        worker = self._load_worker(worker_id, company_id)
        if not worker:
            return
        payload: dict[str, Any] = {}
        if form.get("employee_address"):
            payload["homeAddress"] = form["employee_address"]
        if form.get("employee_birth_date") or form.get("birth_date"):
            payload["birthDate"] = form.get("employee_birth_date") or form.get("birth_date")
        if form.get("employee_gender"):
            payload["gender"] = form["employee_gender"]
        if form.get("employee_email"):
            payload["contactEmail"] = form["employee_email"]
        if form.get("employee_phone"):
            payload["contactPhone"] = form["employee_phone"]
        if payload.get("contactEmail"):
            self.db.execute(
                "UPDATE workers SET contact_email = ? WHERE id = ? AND company_id = ?",
                (str(payload["contactEmail"]).strip(), worker_id, company_id),
            )
        WorkersService._apply_worker_personal_fields(self.db, worker_id, payload, worker)

    def _push_contract_sign_invite(self, worker_id: str, contract: dict[str, Any], sign_url: str) -> None:
        try:
            from backend.app.platform.push.delivery import deliver_worker_push

            lang = normalize_lang(contract.get("language"))
            title = "Arbeitsvertrag unterschreiben" if lang == "de" else "Sign employment contract"
            body = str(contract.get("title") or title)
            deliver_worker_push(
                self.db,
                worker_id,
                title,
                body,
                tag="contract-sign",
                extra={"signUrl": sign_url},
            )
        except Exception:
            pass

    def _send_email(self, recipient: str, subject: str, text_body: str, html_body: str) -> bool:
        try:
            from backend.server import _send_via_any_api

            settings_row = self.db.execute(
                "SELECT smtp_sender_email, smtp_sender_name FROM settings WHERE id = 1"
            ).fetchone()
            sender_email = "noreply@baupass.de"
            sender_name = "SUPPIX"
            if settings_row:
                settings = dict(settings_row)
                sender_email = (settings.get("smtp_sender_email") or "").strip() or sender_email
                sender_name = (settings.get("smtp_sender_name") or "SUPPIX").strip()
            ok, _err, _provider = _send_via_any_api(
                subject, sender_email, sender_name, recipient, text_body, html_body
            )
            return bool(ok)
        except Exception:
            return False

    @staticmethod
    def _sign_invite_email_bodies(
        *,
        lang: str,
        role: str,
        company_name: str,
        contract_title: str,
        sign_url: str,
        expires_at: str,
    ) -> tuple[str, str, str]:
        lang = normalize_lang(lang)
        role_label = {
            "de": ("Mitarbeiter", "Arbeitgeber"),
            "en": ("employee", "employer"),
            "ar": ("الموظف", "صاحب العمل"),
        }
        rl = role_label.get(lang, role_label["en"])
        who = rl[0] if role == "employee" else rl[1]
        if lang == "ar":
            subject = f"توقيع عقد العمل — {contract_title}"
            text = (
                f"مرحباً،\n\n"
                f"يرجى قراءة وتوقيع عقد العمل «{contract_title}» لـ {company_name}.\n"
                f"رابط التوقيع ({who}): {sign_url}\n"
                f"صلاحية الرابط حتى: {expires_at[:10] if expires_at else '—'}\n"
            )
            html = f"<p>{text.replace(chr(10), '<br/>')}</p>"
            return subject, text, html
        if lang == "en":
            subject = f"Sign employment contract — {contract_title}"
            text = (
                f"Hello,\n\n"
                f"Please read and sign the employment contract \"{contract_title}\" for {company_name}.\n"
                f"Sign link ({who}): {sign_url}\n"
                f"Link valid until: {expires_at[:10] if expires_at else '—'}\n"
            )
            html = f"<p>{text.replace(chr(10), '<br/>')}</p>"
            return subject, text, html
        subject = f"Arbeitsvertrag unterschreiben — {contract_title}"
        text = (
            f"Guten Tag,\n\n"
            f"bitte lesen und unterschreiben Sie den Arbeitsvertrag „{contract_title}“ für {company_name}.\n"
            f"Signatur-Link ({who}): {sign_url}\n"
            f"Link gültig bis: {expires_at[:10] if expires_at else '—'}\n"
        )
        html = f"<p>{text.replace(chr(10), '<br/>')}</p>"
        return subject, text, html

    @staticmethod
    def _sign_invite_sms_body(*, lang: str, contract_title: str, sign_url: str) -> str:
        lang = normalize_lang(lang)
        if lang == "en":
            return f"SUPPIX: Please sign \"{contract_title}\": {sign_url}"
        if lang == "ar":
            return f"SUPPIX: يرجى توقيع «{contract_title}»: {sign_url}"
        return f"SUPPIX: Bitte unterschreiben Sie „{contract_title}“: {sign_url}"

    def list_worker_app_contracts(self, worker_id: str, company_id: str, *, base_url: str = "") -> list[dict[str, Any]]:
        rows = self.list_contracts_for_worker(worker_id, company_id)
        out: list[dict[str, Any]] = []
        for row in rows:
            sessions = self.repo.list_sign_sessions(str(row["id"]), company_id)
            pending_employee = next(
                (
                    s for s in sessions
                    if str(s.get("role") or "") == "employee"
                    and str(s.get("status") or "") == "pending"
                    and not self._session_expired(s)
                ),
                None,
            )
            sign_url = ""
            if pending_employee and pending_employee.get("token"):
                sign_url = f"{base_url.rstrip('/')}/contract-sign.html?token={pending_employee['token']}"
            out.append(
                {
                    "id": row.get("id"),
                    "title": row.get("title"),
                    "signStatus": row.get("signStatus"),
                    "status": row.get("status"),
                    "updatedAt": row.get("updated_at"),
                    "signUrl": sign_url,
                    "needsSignature": bool(sign_url),
                }
            )
        return out

    def get_integrations_status(self, company_id: str) -> dict[str, Any]:
        from backend.app.platform.notifications.sms import sms_configured

        settings = self.db.execute(
            "SELECT smtp_sender_email, smtp_host FROM settings WHERE id = 1"
        ).fetchone()
        smtp_ok = bool(settings and (dict(settings).get("smtp_sender_email") or "").strip())
        resend_ok = bool(__import__("os").environ.get("RESEND_API_KEY", "").strip())
        brevo_ok = bool(__import__("os").environ.get("BREVO_API_KEY", "").strip())
        email_ok = smtp_ok or resend_ok or brevo_ok
        return {
            "emailConfigured": email_ok,
            "smsConfigured": sms_configured(),
            "emailHint": "smtp_or_resend" if not email_ok else "",
            "smsHint": "twilio_env" if not sms_configured() else "",
        }

    def send_sign_session_reminder(self, session: dict[str, Any], *, base_url: str = "") -> bool:
        role = str(session.get("role") or "").strip().lower()
        contract_id = str(session.get("contract_id") or "")
        company_id = str(session.get("company_id") or "")
        token = str(session.get("token") or "")
        if not token or not contract_id:
            return False
        contract = self.repo.get_contract(contract_id, company_id)
        if not contract:
            return False
        input_data = self._parse_contract_input(contract)
        form = input_data.get("form") or {}
        lang = normalize_lang(session.get("contract_language") or contract.get("language"))
        title = str(session.get("contract_title") or contract.get("title") or "")
        sign_url = f"{base_url.rstrip('/')}/contract-sign.html?token={token}"
        company = self._load_company(company_id)
        company_name = str(company.get("portal_display_name") or company.get("name") or "SUPPIX")
        recipient = ""
        if role == "employee":
            recipient = str(form.get("employee_email") or "").strip()
            worker_id = contract.get("worker_id")
            if not recipient and worker_id:
                worker = self._load_worker(str(worker_id), company_id)
                recipient = str((worker or {}).get("contact_email") or "").strip()
        else:
            recipient = str(company.get("document_email") or company.get("billing_email") or "").strip()
        if not recipient or "@" not in recipient:
            return False
        subject, text_body, html_body = self._sign_invite_email_bodies(
            lang=lang,
            role=role,
            company_name=company_name,
            contract_title=title,
            sign_url=sign_url,
            expires_at=str(session.get("expires_at") or ""),
        )
        subject = f"[Erinnerung] {subject}" if lang == "de" else f"[Reminder] {subject}"
        if not self._send_email(recipient, subject, text_body, html_body):
            return False
        self.repo.mark_sign_reminder_sent(str(session.get("id") or ""))
        self.repo.log_event(
            contract_id=contract_id,
            company_id=company_id,
            event_type="sign_link.reminder",
            payload={"role": role, "recipient": recipient},
        )
        return True

    def _notify_counterparty_signed(self, contract: dict[str, Any] | None, *, role: str, company_id: str) -> None:
        if not contract:
            return
        input_data = self._parse_contract_input(contract)
        form = input_data.get("form") or {}
        lang = normalize_lang(contract.get("language"))
        title = str(contract.get("title") or "")
        company = self._load_company(company_id)
        company_name = str(company.get("portal_display_name") or company.get("name") or "SUPPIX")
        if role == "employee":
            recipient = str(company.get("document_email") or company.get("billing_email") or "").strip()
            if lang == "en":
                subject = f"Contract signed by employee — {title}"
                text = f"The employee has signed \"{title}\" for {company_name}. Please add the employer signature in SUPPIX admin."
            else:
                subject = f"Vertrag vom Mitarbeiter unterschrieben — {title}"
                text = f"Der Mitarbeiter hat „{title}“ für {company_name} unterschrieben. Bitte Arbeitgeber-Signatur in SUPPIX ergänzen."
        else:
            recipient = str(form.get("employee_email") or "").strip()
            worker_id = contract.get("worker_id")
            if not recipient and worker_id:
                worker = self._load_worker(str(worker_id), company_id)
                recipient = str((worker or {}).get("contact_email") or "").strip()
            if lang == "en":
                subject = f"Contract signed by employer — {title}"
                text = f"The employer has signed \"{title}\". You can download the signed PDF from your SUPPIX app or sign link."
            else:
                subject = f"Vertrag vom Arbeitgeber unterschrieben — {title}"
                text = f"Der Arbeitgeber hat „{title}“ unterschrieben. Das signierte PDF steht in der SUPPIX-App bzw. über den Signatur-Link bereit."
        if recipient and "@" in recipient:
            self._send_email(recipient, subject, text, f"<p>{text.replace(chr(10), '<br/>')}</p>")
            self.repo.log_event(
                contract_id=str(contract.get("id") or ""),
                company_id=company_id,
                event_type="contract.sign_notify",
                payload={"role": role, "recipient": recipient},
            )
