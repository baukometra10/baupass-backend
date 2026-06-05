"""Companies domain — business logic."""
from __future__ import annotations

import secrets
from typing import Any

from .repository import (
    CompaniesRepository,
    CompanyMailSettingsRepository,
    SubcompaniesRepository,
    UsersRepository,
)


class CompaniesService:
    def __init__(self) -> None:
        self.companies = CompaniesRepository()
        self.users = UsersRepository()
        self.subcompanies = SubcompaniesRepository()
        self.mail_settings = CompanyMailSettingsRepository()

    @staticmethod
    def check_mail_access(user: dict[str, Any], company: dict[str, Any] | None) -> dict[str, Any] | None:
        if not company or company.get("deleted_at"):
            return {"error": {"error": "company_not_found"}, "status": 404}
        if user.get("role") != "superadmin" and str(user.get("company_id") or "") != str(company.get("id") or ""):
            return {"error": {"error": "forbidden_company"}, "status": 403}
        return None

    @staticmethod
    def check_work_times_access(user: dict[str, Any], company_id: str) -> dict[str, Any] | None:
        user_role = str(user.get("role") or "").strip().lower()
        if user_role != "superadmin" and str(user.get("company_id") or "") != str(company_id):
            return {"error": {"error": "forbidden_company"}, "status": 403}
        return None

    @staticmethod
    def check_turnstile_list_access(user: dict[str, Any], company_id: str) -> dict[str, Any] | None:
        if user.get("role") == "company-admin" and user.get("company_id") != company_id:
            return {"error": {"error": "forbidden"}, "status": 403}
        return None

    @staticmethod
    def _visible_company_clause(user: dict[str, Any], preview_company_id: str = "") -> tuple[str, list[Any]]:
        if user.get("role") == "superadmin":
            if preview_company_id:
                return " WHERE id = ?", [preview_company_id]
            return "", []
        return " WHERE id = ?", [user.get("company_id")]

    @staticmethod
    def _build_where(base_clause: str, base_params: list[Any], extra_condition: str | None) -> tuple[str, list[Any]]:
        if extra_condition:
            if base_clause:
                return f"{base_clause} AND {extra_condition}", list(base_params)
            return f" WHERE {extra_condition}", list(base_params)
        return base_clause, list(base_params)

    def list_companies(
        self,
        db,
        user: dict[str, Any],
        *,
        include_deleted: bool,
        preview_company_id: str = "",
    ) -> list[dict[str, Any]]:
        clause, params = self._visible_company_clause(user, preview_company_id)
        extra = None if include_deleted else "deleted_at IS NULL"
        where, where_params = self._build_where(clause, params, extra)
        return self.companies.list_filtered(db, where, where_params)

    def list_subcompanies(
        self,
        db,
        user: dict[str, Any],
        *,
        include_deleted: bool,
        requested_company_id: str,
    ) -> dict[str, Any]:
        from backend.server import company_has_feature, feature_not_available_response, get_company_plan

        conditions: list[str] = []
        params: list[Any] = []

        if user.get("role") == "superadmin":
            if requested_company_id:
                plan_value = get_company_plan(db, requested_company_id)
                if not company_has_feature(plan_value, "subcompanies"):
                    resp, status = feature_not_available_response("subcompanies", plan_value)
                    return {"error": resp.get_json(), "status": status}
                conditions.append("company_id = ?")
                params.append(requested_company_id)
        else:
            plan_value = get_company_plan(db, user.get("company_id"))
            if not company_has_feature(plan_value, "subcompanies"):
                resp, status = feature_not_available_response("subcompanies", plan_value)
                return {"error": resp.get_json(), "status": status}
            conditions.append("company_id = ?")
            params.append(user.get("company_id"))

        if not include_deleted:
            conditions.append("deleted_at IS NULL")

        where_sql = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        items = self.subcompanies.list_filtered(db, where_sql, params)
        return {"items": items}

    def create_subcompany(
        self,
        db,
        user: dict[str, Any],
        *,
        company_id: str,
        name: str,
        contact: str,
    ) -> dict[str, Any]:
        from backend.server import (
            company_has_feature,
            feature_not_available_response,
            normalize_company_plan,
        )

        if not company_id:
            return {"error": {"error": "missing_company"}, "status": 400}
        if user.get("role") != "superadmin" and company_id != user.get("company_id"):
            return {"error": {"error": "forbidden_company"}, "status": 403}
        if not name:
            return {"error": {"error": "missing_name"}, "status": 400}

        company = self.companies.get_by_id(db, company_id)
        if not company or company.get("deleted_at"):
            return {"error": {"error": "company_not_available"}, "status": 400}

        plan_value = normalize_company_plan(company.get("plan"))
        if not company_has_feature(plan_value, "subcompanies"):
            resp, status = feature_not_available_response("subcompanies", plan_value)
            return {"error": resp.get_json(), "status": status}

        if self.subcompanies.find_active_by_name(db, company_id, name):
            return {"error": {"error": "subcompany_exists"}, "status": 400}

        subcompany_id = f"sub-{secrets.token_hex(6)}"
        self.subcompanies.insert(
            db,
            subcompany_id=subcompany_id,
            company_id=company_id,
            name=name,
            contact=contact,
        )
        db.commit()
        row = self.subcompanies.get_by_id(db, subcompany_id)
        return {"item": row, "status": 201, "audit": {"subcompany_id": subcompany_id, "name": name, "company_id": company_id}}

    def create_company(self, db, payload: dict[str, Any]) -> dict[str, Any]:
        from zoneinfo import ZoneInfo

        from werkzeug.security import generate_password_hash

        from backend.server import (
            clean_text_input,
            create_turnstile_api_key,
            default_company_trial_end_iso,
            get_next_customer_number,
            hash_turnstile_api_key,
            normalize_company_plan,
            normalize_company_trial_end,
            normalize_email_address,
            normalize_operating_sector,
            sanitize_customer_number,
            suggest_company_document_email,
            normalize_branding_preset,
        )

        company_id = f"cmp-{secrets.token_hex(6)}"
        turnstile_endpoint = clean_text_input(payload.get("turnstileEndpoint", ""), max_len=320)
        company_name = clean_text_input(payload.get("name", "Neue Firma"), max_len=120) or "Neue Firma"
        company_contact = clean_text_input(payload.get("contact", ""), max_len=180)
        company_customer_number = sanitize_customer_number(payload.get("customerNumber", ""), max_len=12)
        billing_email = clean_text_input(payload.get("billingEmail", ""), max_len=160)
        document_email = clean_text_input(payload.get("documentEmail", ""), max_len=160)
        if not document_email:
            document_email = suggest_company_document_email(company_name)
        document_email = normalize_email_address(document_email)
        access_host = clean_text_input(
            (payload.get("accessHost") or payload.get("access_host") or "").strip().lower(),
            max_len=180,
        )
        branding_preset = normalize_branding_preset(
            payload.get("brandingPreset") or payload.get("branding_preset")
        )
        company_status = clean_text_input(payload.get("status", "aktiv"), max_len=32) or "aktiv"
        trial_ends_at = normalize_company_trial_end(
            payload.get("trialEndsAt") or payload.get("trial_ends_at")
        )
        if company_status == "test" and not trial_ends_at:
            trial_ends_at = default_company_trial_end_iso()
        if company_status != "test":
            trial_ends_at = ""
        admin_password = (payload.get("adminPassword") or "").strip() or "1234"
        turnstile_password = (payload.get("turnstilePassword") or "").strip() or admin_password

        try:
            turnstile_count = int(payload.get("turnstileCount", 1) or 1)
        except (TypeError, ValueError):
            return {
                "error": {
                    "error": "invalid_turnstile_count",
                    "message": "Anzahl Drehkreuze muss eine Zahl sein.",
                },
                "status": 400,
            }

        if turnstile_count < 1 or turnstile_count > 20:
            return {
                "error": {
                    "error": "invalid_turnstile_count",
                    "message": "Anzahl Drehkreuze muss zwischen 1 und 20 liegen.",
                },
                "status": 400,
            }
        if len(admin_password) < 4:
            return {
                "error": {
                    "error": "password_too_short",
                    "message": "Passwort muss mindestens 4 Zeichen haben.",
                },
                "status": 400,
            }
        if len(turnstile_password) < 4:
            return {
                "error": {
                    "error": "turnstile_password_too_short",
                    "message": "Drehkreuz-Passwort muss mindestens 4 Zeichen haben.",
                },
                "status": 400,
            }

        if not company_customer_number:
            company_customer_number = get_next_customer_number(db)

        dup_cn = self.companies.conflict_by_customer_number(db, company_customer_number)
        if dup_cn:
            return {
                "error": {
                    "error": "duplicate_customer_number",
                    "message": "Diese Kundennummer ist bereits vergeben.",
                    "conflictCompanyId": dup_cn["id"],
                    "conflictCompanyName": dup_cn["name"],
                },
                "status": 409,
            }

        if document_email:
            dup_email = self.companies.conflict_by_document_email(db, document_email)
            if dup_email:
                return {
                    "error": {
                        "error": "duplicate_document_email",
                        "message": "Diese Dokument-E-Mail ist bereits einer anderen Firma zugeordnet.",
                        "conflictCompanyId": dup_email["id"],
                        "conflictCompanyName": dup_email["name"],
                    },
                    "status": 409,
                }

        if turnstile_endpoint:
            self.companies.set_turnstile_endpoint(db, turnstile_endpoint)

        invoice_email_lang = clean_text_input(payload.get("invoiceEmailLang", "de") or "de", max_len=8)
        if invoice_email_lang not in ("de", "en", "fr"):
            invoice_email_lang = "de"
        report_timezone = clean_text_input(
            payload.get("reportTimezone", payload.get("report_timezone", "")),
            max_len=64,
        )
        if report_timezone:
            try:
                ZoneInfo(report_timezone)
            except Exception:
                return {
                    "error": {
                        "error": "invalid_timezone",
                        "message": "Ungültige Zeitzone (IANA).",
                    },
                    "status": 400,
                }
        operating_sector = normalize_operating_sector(
            payload.get("operatingSector", payload.get("operating_sector", "construction"))
        )

        self.companies.insert_company(
            db,
            company_id=company_id,
            name=company_name,
            customer_number=company_customer_number,
            contact=company_contact,
            billing_email=billing_email,
            document_email=document_email,
            access_host=access_host,
            branding_preset=branding_preset,
            plan=normalize_company_plan(payload.get("plan", "starter")),
            status=company_status,
            trial_ends_at=trial_ends_at,
            invoice_email_lang=invoice_email_lang,
            report_timezone=report_timezone,
            operating_sector=operating_sector,
        )

        username_base = "".join(c for c in company_name.lower() if c.isalnum())[:12] or "firma"
        username = self.users.allocate_username(db, username_base)
        self.users.insert_user(
            db,
            user_id=f"usr-{secrets.token_hex(6)}",
            username=username,
            password_hash=generate_password_hash(admin_password),
            name=f"{company_name} Admin",
            role="company-admin",
            company_id=company_id,
        )

        turnstile_credentials: list[dict[str, str]] = []
        for index in range(turnstile_count):
            if turnstile_count == 1:
                turnstile_username_base = f"{username_base}gate"
                turnstile_display_name = f"{company_name} Drehkreuz"
            else:
                turnstile_username_base = f"{username_base}gate{index + 1}"
                turnstile_display_name = f"{company_name} Drehkreuz {index + 1}"

            turnstile_username = self.users.allocate_username(db, turnstile_username_base)
            turnstile_api_key = create_turnstile_api_key()
            self.users.insert_user(
                db,
                user_id=f"usr-{secrets.token_hex(6)}",
                username=turnstile_username,
                password_hash=generate_password_hash(turnstile_password),
                name=turnstile_display_name,
                role="turnstile",
                company_id=company_id,
                api_key_hash=hash_turnstile_api_key(turnstile_api_key),
            )
            turnstile_credentials.append(
                {
                    "username": turnstile_username,
                    "password": turnstile_password,
                    "apiKey": turnstile_api_key,
                }
            )

        db.commit()
        row = self.companies.get_by_id(db, company_id)
        return {
            "status": 201,
            "body": {
                "company": row,
                "adminCredentials": {"username": username, "password": admin_password},
                "turnstileCredentials": {
                    "username": turnstile_credentials[0]["username"],
                    "password": turnstile_credentials[0]["password"],
                    "apiKey": turnstile_credentials[0]["apiKey"],
                },
                "turnstileCredentialsList": turnstile_credentials,
            },
            "audit": {"company_id": company_id, "company_name": company_name},
        }

    def update_company(self, db, company_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        from zoneinfo import ZoneInfo

        from backend.server import (
            clean_text_input,
            default_company_trial_end_iso,
            get_next_customer_number,
            normalize_branding_accent,
            normalize_branding_preset,
            normalize_company_trial_end,
            normalize_email_address,
            normalize_operating_sector,
            normalize_portal_display_name,
            rematch_inbox_company_links,
            sanitize_customer_number,
            suggest_company_document_email,
            validate_branding_logo_data,
        )

        company = self.companies.get_by_id(db, company_id)
        if not company:
            return {"error": {"error": "company_not_found"}, "status": 404}

        company_name = clean_text_input(payload.get("name", company["name"]), max_len=120)
        company_customer_number = sanitize_customer_number(
            payload.get("customerNumber", company.get("customer_number") or ""),
            max_len=12,
        )
        if not company_customer_number:
            company_customer_number = sanitize_customer_number(company.get("customer_number") or "", max_len=12)
        if not company_customer_number:
            company_customer_number = get_next_customer_number(db)
        company_contact = clean_text_input(payload.get("contact", company.get("contact") or ""), max_len=180)
        company_billing_email = clean_text_input(
            payload.get("billingEmail", company.get("billing_email") or ""), max_len=160
        )
        company_billing_street = clean_text_input(
            payload.get("billingStreet", company.get("billing_street") or ""), max_len=200
        )
        company_billing_zip_city = clean_text_input(
            payload.get("billingZipCity", company.get("billing_zip_city") or ""), max_len=120
        )
        company_document_email = clean_text_input(
            payload.get("documentEmail", company.get("document_email") or ""), max_len=160
        )
        if not company_document_email:
            company_document_email = suggest_company_document_email(company_name)
        company_document_email = normalize_email_address(company_document_email)
        company_access_host = clean_text_input(
            (payload.get("accessHost") or payload.get("access_host") or company.get("access_host") or ""),
            max_len=180,
        )
        company_branding_preset = normalize_branding_preset(
            payload.get("brandingPreset") or payload.get("branding_preset") or company.get("branding_preset")
        )
        company_status = clean_text_input(payload.get("status", company.get("status") or ""), max_len=32) or company.get(
            "status"
        )
        company_trial_ends_at = normalize_company_trial_end(
            payload.get("trialEndsAt", payload.get("trial_ends_at", company.get("trial_ends_at") or ""))
        )
        if company_status == "test" and not company_trial_ends_at:
            company_trial_ends_at = (
                normalize_company_trial_end(company.get("trial_ends_at") or "") or default_company_trial_end_iso()
            )
        if company_status != "test":
            company_trial_ends_at = ""
        company_invoice_email_lang = clean_text_input(
            payload.get("invoiceEmailLang", company.get("invoice_email_lang") or "de") or "de",
            max_len=8,
        )
        if company_invoice_email_lang not in ("de", "en", "fr", "tr", "ar", "es", "it", "pl"):
            company_invoice_email_lang = "de"

        if "portalDisplayName" in payload or "portal_display_name" in payload:
            portal_display_name = normalize_portal_display_name(
                payload.get("portalDisplayName", payload.get("portal_display_name", ""))
            )
        else:
            portal_display_name = normalize_portal_display_name(company.get("portal_display_name") or "")
        if "brandingAccentColor" in payload or "branding_accent_color" in payload:
            branding_accent_color = normalize_branding_accent(
                payload.get("brandingAccentColor", payload.get("branding_accent_color", ""))
            )
        else:
            branding_accent_color = normalize_branding_accent(company.get("branding_accent_color") or "")
        if "brandingLogoData" in payload or "branding_logo_data" in payload:
            branding_logo_data, logo_error = validate_branding_logo_data(
                payload.get("brandingLogoData", payload.get("branding_logo_data", ""))
            )
            if logo_error:
                messages = {
                    "logo_too_large": "Logo zu groß (max. ca. 130 KB als PNG/JPG).",
                    "logo_invalid_format": "Logo muss ein Bild (PNG/JPG/WebP) oder eine gültige URL sein.",
                }
                return {
                    "error": {
                        "error": logo_error,
                        "message": messages.get(logo_error, "Ungültiges Logo."),
                    },
                    "status": 400,
                }
        else:
            branding_logo_data, _logo_error = validate_branding_logo_data(company.get("branding_logo_data") or "")
        if "reportTimezone" in payload or "report_timezone" in payload:
            report_timezone = clean_text_input(
                payload.get("reportTimezone", payload.get("report_timezone", "")),
                max_len=64,
            )
            if report_timezone:
                try:
                    ZoneInfo(report_timezone)
                except Exception:
                    return {
                        "error": {
                            "error": "invalid_timezone",
                            "message": "Ungültige Zeitzone (IANA).",
                        },
                        "status": 400,
                    }
        else:
            report_timezone = str(company.get("report_timezone") or "")

        if "operatingSector" in payload or "operating_sector" in payload:
            operating_sector = normalize_operating_sector(
                payload.get("operatingSector", payload.get("operating_sector", ""))
            )
        else:
            operating_sector = normalize_operating_sector(company.get("operating_sector") or "construction")

        current_document_email = normalize_email_address(company.get("document_email") or "")
        dup_cn = self.companies.conflict_by_customer_number_excluding(
            db, company_id, company_customer_number
        )
        if dup_cn:
            return {
                "error": {
                    "error": "duplicate_customer_number",
                    "message": "Diese Kundennummer ist bereits vergeben.",
                    "conflictCompanyId": dup_cn["id"],
                    "conflictCompanyName": dup_cn["name"],
                },
                "status": 409,
            }

        if company_document_email and company_document_email != current_document_email:
            dup_email = self.companies.conflict_by_document_email_excluding(
                db, company_id, company_document_email
            )
            if dup_email:
                return {
                    "error": {
                        "error": "duplicate_document_email",
                        "message": "Diese Dokument-E-Mail ist bereits einer anderen Firma zugeordnet.",
                        "conflictCompanyId": dup_email["id"],
                        "conflictCompanyName": dup_email["name"],
                    },
                    "status": 409,
                }

        self.companies.update_company(
            db,
            company_id,
            name=company_name,
            customer_number=company_customer_number,
            contact=company_contact,
            billing_email=company_billing_email,
            billing_street=company_billing_street,
            billing_zip_city=company_billing_zip_city,
            document_email=company_document_email,
            access_host=company_access_host,
            branding_preset=company_branding_preset,
            plan=payload.get("plan", company.get("plan")),
            status=company_status,
            trial_ends_at=company_trial_ends_at,
            invoice_email_lang=company_invoice_email_lang,
            portal_display_name=portal_display_name,
            branding_accent_color=branding_accent_color,
            branding_logo_data=branding_logo_data,
            report_timezone=report_timezone,
            operating_sector=operating_sector,
        )
        rematch_inbox_company_links(db, company_id=company_id)
        db.commit()
        return {"body": {"ok": True}, "audit": {"company_id": company_id}}

    def _mail_access(self, db, user: dict[str, Any], company_id: str) -> dict[str, Any] | None:
        company = self.companies.get_mail_access_row(db, company_id)
        return self.check_mail_access(user, company)

    @staticmethod
    def _decrypt_mail_row_values(row: dict[str, Any] | None, company_id: str) -> dict[str, Any]:
        from backend.server import decrypt_mail_credential

        if not row:
            return {}
        values = dict(row)
        if values.get("imap_password"):
            values["imap_password"] = decrypt_mail_credential(values["imap_password"], company_id)
        if values.get("smtp_password"):
            values["smtp_password"] = decrypt_mail_credential(values["smtp_password"], company_id)
        if values.get("brevo_api_key"):
            values["brevo_api_key"] = decrypt_mail_credential(values["brevo_api_key"], company_id)
        return values

    def get_mail_settings(self, db, user: dict[str, Any], company_id: str) -> dict[str, Any]:
        from backend.server import _sanitize_company_mail_settings_for_response, get_company_mail_settings

        denied = self._mail_access(db, user, company_id)
        if denied:
            return denied
        settings = get_company_mail_settings(db, company_id)
        return {"body": _sanitize_company_mail_settings_for_response(settings)}

    def create_mail_settings(
        self, db, user: dict[str, Any], company_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        from backend.server import (
            _company_mail_payload_to_db_values,
            _sanitize_company_mail_settings_for_response,
            get_company_mail_settings,
            now_iso,
        )

        denied = self._mail_access(db, user, company_id)
        if denied:
            return denied
        if self.mail_settings.get_row(db, company_id):
            return {"error": {"error": "mail_settings_already_exists"}, "status": 409}

        values = _company_mail_payload_to_db_values(payload, company_id)
        now_value = now_iso()
        self.mail_settings.insert(db, values, now_value=now_value)
        db.commit()
        created = get_company_mail_settings(db, company_id)
        return {
            "body": _sanitize_company_mail_settings_for_response(created),
            "status": 201,
            "audit": {"company_id": company_id, "action": "created"},
        }

    def update_mail_settings(
        self, db, user: dict[str, Any], company_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        from backend.server import (
            _company_mail_payload_to_db_values,
            _get_default_mail_settings,
            _sanitize_company_mail_settings_for_response,
            get_company_mail_settings,
            now_iso,
        )

        denied = self._mail_access(db, user, company_id)
        if denied:
            return denied

        existing = self.mail_settings.get_row(db, company_id)
        existing_values = self._decrypt_mail_row_values(existing, company_id)
        if not existing_values:
            existing_values = _get_default_mail_settings(company_id)

        values = _company_mail_payload_to_db_values(payload, company_id, current=existing_values)
        now_value = now_iso()
        if existing:
            self.mail_settings.update(db, values, now_value=now_value, company_id=company_id)
        else:
            self.mail_settings.insert(db, values, now_value=now_value)
        db.commit()
        updated = get_company_mail_settings(db, company_id)
        return {
            "body": _sanitize_company_mail_settings_for_response(updated),
            "audit": {"company_id": company_id, "action": "updated"},
        }

    def delete_company(self, db, company_id: str, *, force: bool) -> dict[str, Any]:
        from backend.server import now_iso

        if company_id == "cmp-default":
            return {"error": {"error": "default_company_protected"}, "status": 400}

        company = self.companies.get_by_id(db, company_id)
        if not company:
            return {"error": {"error": "company_not_found"}, "status": 404}

        if self.companies.count_active_workers(db, company_id) > 0 and not force:
            return {"error": {"error": "company_has_workers"}, "status": 400}

        deleted_at = now_iso()
        if force:
            self.companies.force_soft_delete(db, company_id, deleted_at=deleted_at)
        else:
            self.companies.soft_delete(db, company_id, deleted_at=deleted_at)
        db.commit()
        return {
            "body": {"ok": True, "force": force},
            "audit": {"company_id": company_id, "force": force},
        }

    def test_mail_inbound(self, db, user: dict[str, Any], company_id: str) -> dict[str, Any]:
        import imaplib
        import socket

        from backend.server import (
            _imap_auth_hint,
            _imap_login_with_fallback,
            get_company_mail_settings,
            now_iso,
        )

        denied = self._mail_access(db, user, company_id)
        if denied:
            return denied

        settings = get_company_mail_settings(db, company_id)
        host = str(settings.get("imap_host") or "").strip()
        port = int(settings.get("imap_port") or 993)
        username = str(settings.get("imap_username") or "").strip()
        password = str(settings.get("imap_password") or "")
        use_tls = int(settings.get("imap_use_tls") or 0) == 1

        missing = []
        if not host:
            missing.append("imapHost")
        if not username:
            missing.append("imapUsername")
        if not password:
            missing.append("imapPassword")
        if missing:
            return {
                "body": {"ok": False, "error": "imap_not_configured", "missingFields": missing},
                "status": 400,
            }

        attempts = [(use_tls, port)]
        if use_tls and port == 993:
            attempts.append((False, 143))
        elif not use_tls and port == 143:
            attempts.append((True, 993))

        tried: list[str] = []
        conn = None
        last_exc: Exception | None = None
        tested_at = now_iso()
        for attempt_tls, attempt_port in attempts:
            tried.append(f"{'SSL' if attempt_tls else 'STARTTLS'}/{attempt_port}")
            try:
                if attempt_tls:
                    conn = imaplib.IMAP4_SSL(host, attempt_port, timeout=15)
                else:
                    conn = imaplib.IMAP4(host, attempt_port, timeout=15)
                    conn.starttls()
                auth_method = _imap_login_with_fallback(conn, username, password)
                conn.logout()
                self.mail_settings.record_inbound_test(
                    db, company_id, status="ok", tested_at=tested_at
                )
                db.commit()
                return {
                    "body": {
                        "ok": True,
                        "message": (
                            f"IMAP Verbindung erfolgreich "
                            f"({'SSL' if attempt_tls else 'STARTTLS'}:{attempt_port}, Auth: {auth_method})"
                        ),
                        "tried": tried,
                    },
                    "status": 200,
                }
            except (socket.timeout, TimeoutError, ConnectionRefusedError, OSError) as exc:
                last_exc = exc
                try:
                    if conn is not None:
                        conn.logout()
                except Exception:
                    pass
                conn = None
            except Exception as exc:
                last_exc = exc
                try:
                    if conn is not None:
                        conn.logout()
                except Exception:
                    pass
                conn = None
                break

        error_text = str(last_exc or "IMAP test failed")
        hint = _imap_auth_hint(host, error_text)
        self.mail_settings.record_inbound_test(
            db, company_id, status="failed", tested_at=tested_at
        )
        db.commit()
        return {
            "body": {"ok": False, "error": f"{error_text}{hint}", "tried": tried},
            "status": 200,
        }

    def test_mail_outbound(
        self,
        db,
        user: dict[str, Any],
        company_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        from backend.server import (
            _is_valid_brevo_api_key,
            _normalize_api_token,
            _run_smtp_diagnostics,
            _send_via_brevo,
            get_company_mail_settings,
            now_iso,
        )

        denied = self._mail_access(db, user, company_id)
        if denied:
            return denied

        settings = get_company_mail_settings(db, company_id)
        smtp_sender_email = str(settings.get("sender_email") or "").strip()
        smtp_sender_name = str(settings.get("sender_name") or "BauPass").strip() or "BauPass"
        smtp_host = str(settings.get("smtp_host") or "").strip()
        smtp_port = int(settings.get("smtp_port") or 587)
        smtp_use_tls = int(settings.get("smtp_use_tls") or 0)
        smtp_username = str(settings.get("smtp_username") or "").strip()
        smtp_password = str(settings.get("smtp_password") or "")
        brevo_api_key = _normalize_api_token(settings.get("brevo_api_key") or "")
        tested_at = now_iso()

        if brevo_api_key:
            recipient = (
                str(payload.get("recipient") or "").strip()
                or str(user.get("email") or "").strip()
                or smtp_sender_email
            )
            if not recipient:
                return {
                    "body": {"ok": False, "error": "missing_recipient"},
                    "status": 400,
                }
            if not _is_valid_brevo_api_key(brevo_api_key):
                self.mail_settings.record_outbound_test(
                    db, company_id, status="failed", tested_at=tested_at
                )
                db.commit()
                return {
                    "body": {"ok": False, "error": "brevo_invalid_api_key_format"},
                    "status": 200,
                }

            ok, err = _send_via_brevo(
                subject="BauPass Company Mail Test",
                sender_email=smtp_sender_email,
                sender_name=smtp_sender_name,
                recipient=recipient,
                text_body="Company outbound mail test via Brevo successful.",
                html_body="<p>Company outbound mail test via <strong>Brevo</strong> successful.</p>",
                api_key=brevo_api_key,
            )
            self.mail_settings.record_outbound_test(
                db, company_id, status="ok" if ok else "failed", tested_at=tested_at
            )
            db.commit()
            if ok:
                return {
                    "body": {"ok": True, "delivery": "brevo", "recipient": recipient},
                    "status": 200,
                }
            return {
                "body": {
                    "ok": False,
                    "error": str(err or "brevo_send_failed"),
                    "delivery": "brevo",
                },
                "status": 200,
            }

        smtp_settings = {
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "smtp_use_tls": smtp_use_tls,
            "smtp_username": smtp_username,
            "smtp_password": smtp_password,
            "smtp_sender_email": smtp_sender_email,
        }
        missing = []
        if not smtp_host:
            missing.append("smtpHost")
        if not smtp_sender_email:
            missing.append("senderEmail")
        if missing:
            return {
                "body": {"ok": False, "error": "smtp_not_configured", "missingFields": missing},
                "status": 400,
            }

        diag_result = _run_smtp_diagnostics(smtp_settings)
        self.mail_settings.record_outbound_test(
            db,
            company_id,
            status="ok" if diag_result.get("ok") else "failed",
            tested_at=tested_at,
        )
        db.commit()
        if diag_result.get("ok"):
            return {
                "body": {"ok": True, "delivery": "smtp", "diagnostics": diag_result},
                "status": 200,
            }
        return {
            "body": {
                "ok": False,
                "error": "smtp_diagnostic_failed",
                "diagnostics": diag_result,
            },
            "status": 200,
        }

    def get_work_times(self, db, user: dict[str, Any], company_id: str) -> dict[str, Any]:
        from backend.server import get_company_site_access_config

        denied = self.check_work_times_access(user, company_id)
        if denied:
            return denied
        if not self.companies.get_active_id(db, company_id):
            return {"error": {"error": "company_not_found"}, "status": 404}

        cfg = get_company_site_access_config(db, company_id)
        return {"body": {"ok": True, "companyId": company_id, **cfg}}

    def update_work_times(
        self, db, user: dict[str, Any], company_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        from backend.server import (
            normalize_company_access_mode,
            normalize_site_geofence_radius_meters,
            normalize_work_time_value,
        )

        denied = self.check_work_times_access(user, company_id)
        if denied:
            return denied
        if not self.companies.get_by_id(db, company_id):
            return {"error": {"error": "company_not_found"}, "status": 404}

        try:
            work_start_time = normalize_work_time_value(payload.get("workStartTime"))
            work_end_time = normalize_work_time_value(payload.get("workEndTime"))
        except ValueError:
            return {"error": {"error": "invalid_work_time"}, "status": 400}

        access_mode = normalize_company_access_mode(payload.get("accessMode"))
        site_radius = normalize_site_geofence_radius_meters(
            payload.get("siteGeofenceRadiusMeters"),
            access_mode,
        )
        site_auto_checkin = (
            1 if payload.get("siteAutoCheckin", True) in (True, 1, "1", "true", "yes") else 0
        )
        site_auto_logout = (
            1
            if payload.get("siteAutoLogoutOnLeave", True) in (True, 1, "1", "true", "yes")
            else 0
        )

        self.companies.update_work_times(
            db,
            company_id,
            work_start_time=work_start_time,
            work_end_time=work_end_time,
            access_mode=access_mode,
            site_geofence_radius_meters=site_radius,
            site_auto_checkin=site_auto_checkin,
            site_auto_logout_on_leave=site_auto_logout,
        )
        db.commit()
        return {
            "body": {
                "ok": True,
                "companyId": company_id,
                "workStartTime": work_start_time,
                "workEndTime": work_end_time,
                "accessMode": access_mode,
                "siteGeofenceRadiusMeters": site_radius,
                "siteAutoCheckin": bool(site_auto_checkin),
                "siteAutoLogoutOnLeave": bool(site_auto_logout),
            },
            "audit": {"company_id": company_id},
        }

    def list_turnstiles(self, db, user: dict[str, Any], company_id: str) -> dict[str, Any]:
        denied = self.check_turnstile_list_access(user, company_id)
        if denied:
            return denied
        if not self.companies.get_active_id(db, company_id):
            return {"error": {"error": "company_not_found"}, "status": 404}
        items = self.users.list_turnstiles(db, company_id)
        return {"body": items}

    def add_turnstile(
        self, db, company_id: str, *, password: str
    ) -> dict[str, Any]:
        import secrets

        from werkzeug.security import generate_password_hash

        from backend.server import create_turnstile_api_key, hash_turnstile_api_key

        company = self.companies.get_by_id(db, company_id)
        if not company or company.get("deleted_at"):
            return {"error": {"error": "company_not_found"}, "status": 404}
        if len(password) < 4:
            return {
                "error": {
                    "error": "password_too_short",
                    "message": "Passwort muss mindestens 4 Zeichen haben.",
                },
                "status": 400,
            }

        existing_count = self.users.count_turnstiles(db, company_id)
        username_base_raw = "".join(c for c in str(company.get("name") or "").lower() if c.isalnum())[:12] or "gate"
        username = self.users.allocate_username(db, f"{username_base_raw}gate{existing_count + 1}")
        display_name = f"{company['name']} Drehkreuz {existing_count + 1}"
        user_id = f"usr-{secrets.token_hex(6)}"
        api_key = create_turnstile_api_key()
        self.users.insert_user(
            db,
            user_id=user_id,
            username=username,
            password_hash=generate_password_hash(password),
            name=display_name,
            role="turnstile",
            company_id=company_id,
            api_key_hash=hash_turnstile_api_key(api_key),
        )
        db.commit()
        return {
            "status": 201,
            "body": {"ok": True, "username": username, "password": password, "apiKey": api_key},
            "audit": {
                "company_id": company_id,
                "company_name": company["name"],
                "username": username,
            },
        }

    def reset_turnstile_password(
        self,
        db,
        user: dict[str, Any],
        company_id: str,
        turnstile_user_id: str,
        *,
        password: str,
    ) -> dict[str, Any]:
        from werkzeug.security import generate_password_hash

        denied = self.check_turnstile_list_access(user, company_id)
        if denied:
            return denied
        if len(password) < 4:
            return {"error": {"error": "password_too_short"}, "status": 400}

        turnstile = self.users.get_turnstile(db, company_id, turnstile_user_id)
        if not turnstile:
            return {"error": {"error": "user_not_found"}, "status": 404}

        self.users.update_password_hash(
            db, turnstile_user_id, generate_password_hash(password)
        )
        db.commit()
        return {
            "body": {"ok": True},
            "audit": {
                "company_id": company_id,
                "user_id": turnstile_user_id,
                "username": turnstile["username"],
            },
        }

    def rotate_turnstile_api_key(
        self, db, company_id: str, turnstile_user_id: str
    ) -> dict[str, Any]:
        from backend.server import create_turnstile_api_key, hash_turnstile_api_key

        turnstile = self.users.get_turnstile(db, company_id, turnstile_user_id)
        if not turnstile:
            return {"error": {"error": "user_not_found"}, "status": 404}

        api_key = create_turnstile_api_key()
        self.users.update_api_key_hash(
            db, turnstile_user_id, hash_turnstile_api_key(api_key)
        )
        db.commit()
        return {
            "body": {"ok": True, "apiKey": api_key},
            "audit": {
                "company_id": company_id,
                "user_id": turnstile_user_id,
                "username": turnstile["username"],
            },
        }

    def toggle_turnstile_active(
        self, db, company_id: str, turnstile_user_id: str
    ) -> dict[str, Any]:
        turnstile = self.users.get_turnstile(db, company_id, turnstile_user_id)
        if not turnstile:
            return {"error": {"error": "user_not_found"}, "status": 404}

        new_active = 0 if int(turnstile.get("is_active") or 1) == 1 else 1
        self.users.set_active(db, turnstile_user_id, new_active)
        if new_active == 0:
            self.users.delete_sessions(db, turnstile_user_id)
        db.commit()
        return {
            "body": {"ok": True, "isActive": new_active == 1},
            "audit": {
                "company_id": company_id,
                "user_id": turnstile_user_id,
                "username": turnstile["username"],
                "is_active": new_active == 1,
            },
        }

    def get_admin_security(self, db, company_id: str) -> dict[str, Any]:
        admin_user = self.users.get_company_admin(db, company_id)
        if not admin_user:
            return {"error": {"error": "admin_not_found"}, "status": 404}
        return {
            "body": {
                "username": admin_user["username"],
                "email": admin_user.get("email") or "",
                "twofa_enabled": bool(int(admin_user.get("twofa_enabled") or 0)),
            }
        }

    def set_admin_security(
        self, db, company_id: str, *, email: str, enable_2fa: bool
    ) -> dict[str, Any]:
        import re

        normalized_email = (email or "").strip().lower()
        if normalized_email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", normalized_email):
            return {"error": {"error": "invalid_email"}, "status": 400}

        admin_user = self.users.get_company_admin(db, company_id)
        if not admin_user:
            return {"error": {"error": "admin_not_found"}, "status": 404}

        self.users.update_company_admin_security(
            db,
            admin_user["id"],
            email=normalized_email,
            twofa_enabled=1 if enable_2fa else 0,
        )
        if not enable_2fa:
            self.users.delete_otp_codes(db, admin_user["id"])
        db.commit()
        return {
            "body": {
                "ok": True,
                "username": admin_user["username"],
                "email": normalized_email,
                "twofa_enabled": enable_2fa,
            },
            "audit": {
                "company_id": company_id,
                "user_id": admin_user["id"],
                "username": admin_user["username"],
            },
        }

    def set_admin_password(self, db, company_id: str, *, new_password: str) -> dict[str, Any]:
        from werkzeug.security import generate_password_hash

        if len(new_password) < 8:
            return {
                "body": {"ok": False, "error": "password_too_short"},
                "status": 400,
            }

        admin_user = self.users.get_company_admin(db, company_id)
        if not admin_user:
            return {
                "body": {"ok": False, "error": "admin_not_found"},
                "status": 404,
            }

        self.users.update_password_hash(
            db, admin_user["id"], generate_password_hash(new_password)
        )
        self.users.delete_sessions(db, admin_user["id"])
        db.commit()
        return {
            "body": {"ok": True, "username": admin_user["username"]},
            "audit": {
                "company_id": company_id,
                "user_id": admin_user["id"],
                "username": admin_user["username"],
            },
        }

    def _deny_feature(self, db, company_id: str, feature: str) -> dict[str, Any] | None:
        from backend.server import company_has_feature, feature_not_available_response, get_company_plan

        plan_value = get_company_plan(db, company_id)
        if not company_has_feature(plan_value, feature):
            resp, status = feature_not_available_response(feature, plan_value)
            return {"error": resp.get_json(), "status": status}
        return None

    @staticmethod
    def _month_prefix(month_param: str) -> str:
        from datetime import datetime as dt

        month_param = (month_param or "").strip()
        if month_param and len(month_param) == 7 and "-" in month_param:
            return month_param
        return dt.now().strftime("%Y-%m")

    def repair_company(self, db, user: dict[str, Any], company_id: str) -> dict[str, Any]:
        from backend.server import normalize_badge_id, now_iso

        denied = self.check_turnstile_list_access(user, company_id)
        if denied:
            return denied

        now = now_iso()
        fixed: list[str] = []
        expired_tokens = 0
        expired_sessions = 0
        for worker_id in self.companies.list_worker_ids(db, company_id):
            expired_tokens += self.companies.delete_expired_worker_app_tokens(db, worker_id, now)
            expired_sessions += self.companies.delete_expired_worker_app_sessions(db, worker_id, now)

        if expired_tokens:
            fixed.append(f"{expired_tokens} abgelaufene App-Tokens entfernt")
        if expired_sessions:
            fixed.append(f"{expired_sessions} abgelaufene App-Sitzungen entfernt")

        no_badge = self.companies.workers_missing_badge(db, company_id)
        for worker_id in no_badge:
            generated_badge_id = f"BP-{worker_id[-6:].upper()}"
            self.companies.set_worker_badge(
                db,
                worker_id,
                badge_id=generated_badge_id,
                badge_id_lookup=normalize_badge_id(generated_badge_id),
            )
        if no_badge:
            fixed.append(f"{len(no_badge)} fehlende Ausweisnummern ergaenzt")

        bad_status = self.companies.workers_invalid_status(db, company_id)
        for worker_id in bad_status:
            self.companies.fix_worker_status_active(db, worker_id)
        if bad_status:
            fixed.append(f"{len(bad_status)} ungueltige Mitarbeiter-Status korrigiert")

        if not fixed:
            fixed.append("Keine Probleme gefunden - System ist in Ordnung")

        db.commit()
        return {
            "body": {"ok": True, "fixed": fixed},
            "audit": {"company_id": company_id, "message": "; ".join(fixed)},
        }

    def restore_company(self, db, company_id: str) -> dict[str, Any]:
        if not self.companies.get_by_id(db, company_id):
            return {"error": {"error": "company_not_found"}, "status": 404}
        self.companies.restore(db, company_id)
        db.commit()
        return {"body": {"ok": True}, "audit": {"company_id": company_id}}

    def toggle_review_access(self, db, company_id: str) -> dict[str, Any]:
        import uuid as uuid_mod

        company = self.companies.get_review_row(db, company_id)
        if not company:
            return {"error": "Firma nicht gefunden", "status": 404}
        new_state = 0 if int(company.get("review_enabled") or 0) else 1
        token = str(uuid_mod.uuid4()).replace("-", "") if new_state else ""
        self.companies.set_review_access(
            db, company_id, review_enabled=new_state, review_token=token
        )
        db.commit()
        return {
            "body": {
                "review_enabled": new_state,
                "review_token": token if new_state else "",
            }
        }

    def get_plan_features(self, db, user: dict[str, Any], company_id: str) -> dict[str, Any]:
        from backend.server import PLAN_RANK, get_plan_features

        denied = self.check_turnstile_list_access(user, company_id)
        if denied:
            return denied
        plan = self.companies.get_plan(db, company_id)
        if plan is None:
            return {"error": {"error": "company_not_found"}, "status": 404}
        return {
            "body": {
                "plan": plan,
                "features": get_plan_features(plan),
                "planRank": PLAN_RANK.get(plan, 1),
                "availablePlans": [
                    {"key": "tageskarte", "labelDe": "Tageskarte", "priceEur": 19.0, "rank": 0},
                    {
                        "key": "starter",
                        "labelDe": "Start",
                        "priceEur": 49.0,
                        "workerPriceEur": 1.50,
                        "rank": 1,
                    },
                    {
                        "key": "professional",
                        "labelDe": "Professional",
                        "priceEur": 99.0,
                        "workerPriceEur": 2.50,
                        "rank": 2,
                    },
                    {
                        "key": "enterprise",
                        "labelDe": "Enterprise",
                        "priceEur": 199.0,
                        "workerPriceEur": 0.0,
                        "rank": 3,
                    },
                ],
            }
        }

    def build_document_emails_pdf(self, db) -> dict[str, Any]:
        import io
        from datetime import datetime

        rows = self.companies.list_document_email_export_rows(db)
        try:
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.pdfgen import canvas as rl_canvas
        except Exception:
            return {
                "error": {
                    "error": "pdf_dependency_missing",
                    "message": "Bitte reportlab installieren.",
                },
                "status": 503,
            }

        buffer = io.BytesIO()
        page_w, page_h = landscape(A4)
        pdf = rl_canvas.Canvas(buffer, pagesize=landscape(A4))
        col_x = [36, 186, 326, 402, 512, 640, 688, 736]
        headers = [
            "Firma",
            "Dokument-Email",
            "Status",
            "Rechnungs-Email",
            "Letzter Eingang",
            "Offen",
            "Ungelöst",
            "Gelöscht",
        ]

        def draw_header(y_pos: float) -> float:
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(36, y_pos, "BauPass - Firmen Dokument-E-Mails")
            y_pos -= 14
            pdf.setFont("Helvetica", 8)
            pdf.drawString(36, y_pos, f"Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
            y_pos -= 16
            pdf.setFont("Helvetica-Bold", 7)
            for idx, header in enumerate(headers):
                pdf.drawString(col_x[idx], y_pos, header)
            y_pos -= 8
            pdf.line(36, y_pos, page_w - 36, y_pos)
            y_pos -= 10
            return y_pos

        y = page_h - 36
        y = draw_header(y)
        pdf.setFont("Helvetica", 7)
        for row in rows:
            if y < 48:
                pdf.showPage()
                y = page_h - 36
                y = draw_header(y)
                pdf.setFont("Helvetica", 7)
            pdf.drawString(col_x[0], y, str(row.get("name") or "")[:24])
            pdf.drawString(col_x[1], y, str(row.get("document_email") or "")[:24])
            pdf.drawString(col_x[2], y, str(row.get("status") or "")[:12])
            pdf.drawString(col_x[3], y, str(row.get("billing_email") or "")[:24])
            pdf.drawString(col_x[4], y, str(row.get("last_inbox_activity_at") or "")[:18])
            pdf.drawString(col_x[5], y, str(int(row.get("open_inbox_count") or 0)))
            pdf.drawString(col_x[6], y, str(int(row.get("unresolved_inbox_count") or 0)))
            pdf.drawString(col_x[7], y, "Ja" if row.get("deleted_at") else "Nein")
            y -= 11
        if not rows:
            pdf.drawString(36, y, "Keine Firmen gefunden.")
        pdf.save()
        buffer.seek(0)
        filename = f"firmen-dokument-emails-{datetime.now().strftime('%Y-%m-%d')}.pdf"
        return {"pdf_bytes": buffer.getvalue(), "filename": filename}

    def worker_hours_summary(
        self, db, user: dict[str, Any], company_id: str, *, month_param: str
    ) -> dict[str, Any]:
        from collections import defaultdict
        from datetime import datetime as dt

        denied = self.check_turnstile_list_access(user, company_id)
        if denied:
            return denied
        if not self.companies.get_active_id(db, company_id):
            return {"error": {"error": "company_not_found"}, "status": 404}
        feature_denied = self._deny_feature(db, company_id, "worker_hours_report")
        if feature_denied:
            return feature_denied

        month_prefix = self._month_prefix(month_param)
        rows = self.companies.access_logs_month_for_company(db, company_id, month_prefix)
        worker_data: dict[str, dict] = defaultdict(
            lambda: {
                "firstName": "",
                "lastName": "",
                "badgeId": "",
                "role": "",
                "totalMinutes": 0,
                "daysWorked": set(),
            }
        )
        by_worker: dict[str, list] = defaultdict(list)
        for row in rows:
            worker_id = row["worker_id"]
            by_worker[worker_id].append(row)
            entry = worker_data[worker_id]
            entry["firstName"] = row.get("first_name") or ""
            entry["lastName"] = row.get("last_name") or ""
            entry["badgeId"] = row.get("badge_id") or ""
            entry["role"] = row.get("worker_role") or ""

        for worker_id, events in by_worker.items():
            pending_checkin = None
            for ev in events:
                if ev["direction"] == "check-in":
                    pending_checkin = ev["timestamp"]
                elif ev["direction"] == "check-out" and pending_checkin:
                    try:
                        t_in = dt.fromisoformat(pending_checkin[:19])
                        t_out = dt.fromisoformat(ev["timestamp"][:19])
                        diff = int((t_out - t_in).total_seconds() / 60)
                        if 0 < diff < 1440:
                            worker_data[worker_id]["totalMinutes"] += diff
                            worker_data[worker_id]["daysWorked"].add(pending_checkin[:10])
                    except Exception:
                        pass
                    pending_checkin = None

        result = []
        for worker_id, data in worker_data.items():
            result.append(
                {
                    "workerId": worker_id,
                    "firstName": data["firstName"],
                    "lastName": data["lastName"],
                    "badgeId": data["badgeId"],
                    "role": data["role"],
                    "totalHours": round(data["totalMinutes"] / 60, 1),
                    "daysWorked": len(data["daysWorked"]),
                }
            )
        result.sort(key=lambda item: (item["lastName"] or "").lower())
        return {"body": {"month": month_prefix, "workers": result}}

    def worker_timeline(
        self,
        db,
        user: dict[str, Any],
        company_id: str,
        worker_id: str,
        *,
        month_param: str,
    ) -> dict[str, Any]:
        from collections import OrderedDict
        from datetime import datetime as dt

        denied = self.check_turnstile_list_access(user, company_id)
        if denied:
            return denied
        feature_denied = self._deny_feature(db, company_id, "worker_hours_report")
        if feature_denied:
            return feature_denied

        worker = self.companies.get_worker_brief(db, worker_id, company_id)
        if not worker:
            return {"error": {"error": "worker_not_found"}, "status": 404}

        month_prefix = self._month_prefix(month_param)
        rows = self.companies.access_logs_month_for_worker(db, worker_id, month_prefix)
        by_day: OrderedDict[str, list] = OrderedDict()
        for row in rows:
            day = row["timestamp"][:10]
            by_day.setdefault(day, []).append(
                {
                    "direction": row["direction"],
                    "gate": row.get("gate") or "",
                    "note": row.get("note") or "",
                    "timestamp": row["timestamp"],
                }
            )

        days = []
        for day, events in by_day.items():
            sessions = []
            pending_in = None
            day_minutes = 0
            for ev in events:
                if ev["direction"] == "check-in":
                    pending_in = ev
                elif ev["direction"] == "check-out":
                    duration = None
                    if pending_in:
                        try:
                            t_in = dt.fromisoformat(pending_in["timestamp"][:19])
                            t_out = dt.fromisoformat(ev["timestamp"][:19])
                            diff = int((t_out - t_in).total_seconds() / 60)
                            if 0 < diff < 1440:
                                duration = diff
                                day_minutes += diff
                        except Exception:
                            pass
                    sessions.append(
                        {
                            "checkIn": pending_in["timestamp"] if pending_in else None,
                            "checkOut": ev["timestamp"],
                            "gateIn": pending_in["gate"] if pending_in else "",
                            "gateOut": ev["gate"],
                            "durationMinutes": duration,
                        }
                    )
                    pending_in = None
            if pending_in:
                sessions.append(
                    {
                        "checkIn": pending_in["timestamp"],
                        "checkOut": None,
                        "gateIn": pending_in["gate"],
                        "gateOut": "",
                        "durationMinutes": None,
                    }
                )
            days.append({"date": day, "sessions": sessions, "dayMinutes": day_minutes})

        return {
            "body": {
                "month": month_prefix,
                "workerId": worker_id,
                "firstName": worker.get("first_name") or "",
                "lastName": worker.get("last_name") or "",
                "badgeId": worker.get("badge_id") or "",
                "days": days,
            }
        }
