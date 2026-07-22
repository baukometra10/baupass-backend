"""Workers domain — business logic."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .repository import WorkersRepository


class WorkersService:
    def __init__(self) -> None:
        self.repo = WorkersRepository()

    @staticmethod
    def check_worker_access(user: dict[str, Any], worker: dict[str, Any]) -> dict[str, Any] | None:
        if user.get("role") != "superadmin" and worker.get("company_id") != user.get("company_id"):
            return {"error": {"error": "forbidden_worker"}, "status": 403}
        return None

    @staticmethod
    def check_lock_role(user: dict[str, Any]) -> dict[str, Any] | None:
        if user.get("role") not in ("superadmin", "company-admin", "turnstile"):
            return {"error": {"error": "forbidden"}, "status": 403}
        return None

    def _get_worker_or_error(
        self, db, user: dict[str, Any], worker_id: str, *, allow_deleted: bool = False
    ) -> dict[str, Any]:
        worker = self.repo.get_by_id_global(db, worker_id)
        if not worker:
            return {"error": {"error": "worker_not_found"}, "status": 404}
        denied = self.check_worker_access(user, worker)
        if denied:
            return denied
        if not allow_deleted and worker.get("deleted_at"):
            return {"error": {"error": "worker_deleted"}, "status": 400}
        return {"worker": worker}

    @staticmethod
    def _build_worker_where(
        user: dict[str, Any], *, include_deleted: bool
    ) -> tuple[str, list[Any]]:
        from backend.server import visible_worker_clause

        clause, params = visible_worker_clause(user)
        if include_deleted:
            return clause, list(params)
        if clause:
            return f"{clause} AND deleted_at IS NULL", list(params)
        return " WHERE deleted_at IS NULL", []

    def list_workers(
        self, db, user: dict[str, Any], *, include_deleted: bool
    ) -> dict[str, Any]:
        from backend.server import (
            get_worker_lock_metadata,
            lock_workers_with_expired_documents,
            serialize_worker_record,
        )

        try:
            try:
                lock_workers_with_expired_documents(db)
            except Exception:
                pass
            where_sql, params = self._build_worker_where(user, include_deleted=include_deleted)
            rows = self.repo.list_filtered(db, where_sql, params)
            serialized = []
            for row in rows:
                item = serialize_worker_record(row)
                item.update(get_worker_lock_metadata(db, row))
                serialized.append(item)
            return {"body": serialized}
        except Exception as exc:
            return {
                "error": {
                    "error": "Fehler beim Laden von Mitarbeitern",
                    "details": str(exc),
                },
                "status": 400,
            }

    def get_current_visitors(self, db, user: dict[str, Any]) -> dict[str, Any]:
        company_id = None if user.get("role") == "superadmin" else user.get("company_id")
        now_str = datetime.utcnow().isoformat()
        rows = self.repo.list_current_visitors(db, now_str=now_str, company_id=company_id)
        result = []
        for row in rows:
            expires_at = row.get("visit_end_at") or ""
            minutes_left = None
            if expires_at:
                try:
                    delta = datetime.fromisoformat(expires_at) - datetime.utcnow()
                    minutes_left = int(delta.total_seconds() / 60)
                except Exception:
                    pass
            result.append(
                {
                    "id": row["id"],
                    "name": f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip(),
                    "badge_id": row.get("badge_id"),
                    "visitor_company": row.get("visitor_company"),
                    "visit_purpose": row.get("visit_purpose"),
                    "host_name": row.get("host_name"),
                    "visit_end_at": expires_at,
                    "minutes_left": minutes_left,
                }
            )
        return {"body": result}

    def delete_worker(self, db, user: dict[str, Any], worker_id: str) -> dict[str, Any]:
        from backend.server import now_iso

        worker = self.repo.get_by_id_global(db, worker_id)
        if not worker:
            return {"error": {"error": "worker_not_found"}, "status": 404}
        denied = self.check_worker_access(user, worker)
        if denied:
            return denied
        self.repo.soft_delete(db, worker_id, deleted_at=now_iso())
        db.commit()
        return {
            "body": {"ok": True},
            "audit": {"worker_id": worker_id, "company_id": worker.get("company_id")},
        }

    def restore_worker(self, db, user: dict[str, Any], worker_id: str) -> dict[str, Any]:
        worker = self.repo.get_by_id_global(db, worker_id)
        if not worker:
            return {"error": {"error": "worker_not_found"}, "status": 404}
        denied = self.check_worker_access(user, worker)
        if denied:
            return denied
        self.repo.restore(db, worker_id)
        db.commit()
        return {
            "body": {"ok": True},
            "audit": {"worker_id": worker_id, "company_id": worker.get("company_id")},
        }

    def worker_stats(self, db, user: dict[str, Any]) -> dict[str, Any]:
        company_id = None if user.get("role") == "superadmin" else user.get("company_id")
        return {"body": self.repo.worker_stats(db, company_id)}

    def list_workers_v2(self, db, company_id: str) -> list[dict]:
        return self.repo.list_active(db, company_id)

    def assign_physical_card(
        self, db, company_id: str, worker_id: str, physical_card_id: str | None
    ) -> bool:
        return self.repo.update_physical_card_id(db, company_id, worker_id, physical_card_id)

    def workforce_tracking(self, db, company_id: str, today_prefix: str) -> dict:
        on_site = self.repo.count_on_site_today(db, company_id, today_prefix)
        workers = self.repo.list_active(db, company_id, limit=1000)
        return {
            "on_site": on_site,
            "total_active": len(workers),
            "workers": workers[:50],
        }

    @staticmethod
    def _ensure_worker_doc_dir(worker_id: str) -> dict[str, Any] | None:
        from backend.server import DOCS_UPLOAD_DIR

        try:
            base_upload_root = DOCS_UPLOAD_DIR.resolve()
            worker_doc_dir = (DOCS_UPLOAD_DIR / worker_id).resolve()
            if worker_doc_dir != base_upload_root and base_upload_root not in worker_doc_dir.parents:
                raise ValueError("invalid_worker_doc_path")
            worker_doc_dir.mkdir(parents=True, exist_ok=True)
            return None
        except Exception as exc:
            return {
                "error": {
                    "error": "worker_doc_folder_create_failed",
                    "detail": str(exc),
                },
                "status": 500,
            }

    def create_worker(self, db, user: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        import secrets

        from werkzeug.security import generate_password_hash

        from backend.server import (
            clean_id_input,
            clean_text_input,
            ensure_unique_physical_card_id_or_raise,
            normalize_badge_id,
            normalize_physical_card_id,
            normalize_worker_type,
            parse_datetime_local_to_utc_iso,
            resolve_subcompany_id,
            sanitize_photo_data,
            serialize_worker_record,
            validate_badge_pin_or_raise,
            _persist_worker_compliance_fields,
        )

        try:
            company_id = clean_id_input(payload.get("companyId") or user.get("company_id"))
        except ValueError as error:
            return {"error": {"error": str(error)}, "status": 400}

        if user.get("role") != "superadmin" and company_id != user.get("company_id"):
            return {"error": {"error": "forbidden_company"}, "status": 403}

        company = self.repo.get_company_row(db, company_id)
        if not company or company.get("deleted_at"):
            return {"error": {"error": "company_not_available"}, "status": 400}

        try:
            subcompany_id = resolve_subcompany_id(db, company_id, payload.get("subcompanyId"))
        except ValueError as error:
            return {"error": {"error": str(error)}, "status": 400}

        try:
            photo_data = sanitize_photo_data(payload.get("photoData"), required=True)
        except ValueError as error:
            return {"error": {"error": str(error)}, "status": 400}

        worker_type = normalize_worker_type(payload.get("workerType"))
        visitor_company = clean_text_input(payload.get("visitorCompany") or "", max_len=120)
        visit_purpose = clean_text_input(payload.get("visitPurpose") or "", max_len=200)
        host_name = clean_text_input(payload.get("hostName") or "", max_len=120)
        visit_end_at = parse_datetime_local_to_utc_iso(payload.get("visitEndAt")) or ""

        visitor_err = self._validate_visitor_fields(
            worker_type, visitor_company, visit_purpose, host_name, visit_end_at
        )
        if visitor_err:
            return visitor_err

        if worker_type != "visitor":
            from backend.server import sanitize_compliance_signature_data

            sig_raw = payload.get("complianceSignatureData")
            if sig_raw not in (None, "") and str(sig_raw).strip():
                try:
                    sanitize_compliance_signature_data(sig_raw, required=True)
                except ValueError as error:
                    code = str(error)
                    message = (
                        "Ungültige Unterschrift."
                        if code != "signature_required"
                        else "Ungültige Unterschrift."
                    )
                    return {
                        "error": {
                            "error": code,
                            "message": message,
                        },
                        "status": 400,
                    }

        badge_pin_hash = ""
        if worker_type != "visitor":
            try:
                badge_pin = validate_badge_pin_or_raise(payload.get("badgePin"))
            except ValueError as error:
                return {
                    "error": {
                        "error": str(error),
                        "message": "Badge-PIN muss aus 4 bis 8 Ziffern bestehen.",
                    },
                    "status": 400,
                }
            badge_pin_hash = generate_password_hash(badge_pin)

        physical_card_id = normalize_physical_card_id(payload.get("physicalCardId"))
        try:
            ensure_unique_physical_card_id_or_raise(db, physical_card_id)
        except ValueError as error:
            return {
                "error": {
                    "error": str(error),
                    "message": "Diese Karten-ID ist bereits einem anderen Mitarbeiter zugeordnet.",
                },
                "status": 409,
            }

        first_name = clean_text_input(payload.get("firstName", ""), max_len=80)
        last_name = clean_text_input(payload.get("lastName", ""), max_len=80)
        insurance_number = clean_text_input(payload.get("insuranceNumber", ""), max_len=64)
        role_value = clean_text_input(payload.get("role", ""), max_len=120)
        site_value = clean_text_input(payload.get("site", ""), max_len=120)
        valid_until_value = clean_text_input(payload.get("validUntil", ""), max_len=32)
        status_value = clean_text_input(payload.get("status", "aktiv"), max_len=32) or "aktiv"
        badge_id_value = normalize_badge_id(
            clean_text_input(
                payload.get(
                    "badgeId",
                    f"{'VS' if worker_type == 'visitor' else 'BP'}-{secrets.token_hex(3).upper()}",
                ),
                max_len=64,
            )
        )

        worker_id = f"wrk-{secrets.token_hex(6)}"
        dir_err = self._ensure_worker_doc_dir(worker_id)
        if dir_err:
            return dir_err

        self.repo.insert_worker(
            db,
            worker_id=worker_id,
            company_id=company_id,
            subcompany_id=subcompany_id,
            first_name=first_name,
            last_name=last_name,
            insurance_number=insurance_number if worker_type != "visitor" else "",
            worker_type=worker_type,
            role=role_value if worker_type != "visitor" else (role_value or "Besucher"),
            site=site_value,
            valid_until=valid_until_value,
            visitor_company=visitor_company,
            visit_purpose=visit_purpose,
            host_name=host_name,
            visit_end_at=visit_end_at,
            status=status_value,
            photo_data=photo_data,
            badge_id=badge_id_value,
            badge_id_lookup=normalize_badge_id(badge_id_value),
            badge_pin_hash=badge_pin_hash,
            physical_card_id=physical_card_id,
        )
        from backend.server import apply_worker_site_coordinates_from_payload

        try:
            apply_worker_site_coordinates_from_payload(db, worker_id, payload)
        except ValueError as error:
            return {"error": {"error": str(error)}, "status": 400}
        try:
            _persist_worker_compliance_fields(db, worker_id, payload, user, is_new=True)
        except ValueError as error:
            return {"error": {"error": str(error)}, "status": 400}
        self._apply_worker_personal_fields(db, worker_id, payload, self.repo.get_by_id_global(db, worker_id) or {})
        if worker_type != "visitor":
            from backend.server import lock_worker_for_required_documents

            lock_worker_for_required_documents(db, self.repo.get_by_id_global(db, worker_id))
        db.commit()
        row = self.repo.get_by_id_global(db, worker_id)
        return {
            "status": 201,
            "body": serialize_worker_record(row),
            "audit": {
                "worker_id": worker_id,
                "company_id": company_id,
                "name": f"{first_name} {last_name}",
            },
        }

    def update_worker(
        self, db, user: dict[str, Any], worker_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        from werkzeug.security import generate_password_hash

        from backend.server import (
            clean_id_input,
            clean_text_input,
            create_operation_approval,
            ensure_unique_physical_card_id_or_raise,
            normalize_badge_id,
            normalize_badge_pin,
            normalize_physical_card_id,
            normalize_worker_type,
            parse_datetime_local_to_utc_iso,
            resolve_subcompany_id,
            sanitize_photo_data,
            validate_badge_pin_or_raise,
            _persist_worker_compliance_fields,
        )

        worker = self.repo.get_by_id_global(db, worker_id)
        if not worker:
            return {"error": {"error": "worker_not_found"}, "status": 404}
        denied = self.check_worker_access(user, worker)
        if denied:
            return denied
        if worker.get("deleted_at"):
            return {"error": {"error": "worker_deleted"}, "status": 400}

        photo_override_requested = bool(payload.get("photoMatchOverride"))
        photo_similarity_raw = payload.get("photoMatchSimilarity")
        photo_override_reason = clean_text_input(
            payload.get("photoMatchOverrideReason") or "", max_len=240
        )
        photo_similarity = self._parse_photo_similarity(photo_similarity_raw)
        if isinstance(photo_similarity, dict):
            return photo_similarity

        if photo_override_requested and user.get("role") != "superadmin":
            return {"error": {"error": "photo_override_forbidden"}, "status": 403}
        if photo_override_requested and len(photo_override_reason) < 8:
            return {"error": {"error": "photo_override_reason_required"}, "status": 400}

        photo_override_needs_approval = photo_override_requested

        try:
            next_company_id = clean_id_input(payload.get("companyId", worker.get("company_id")))
        except ValueError as error:
            return {"error": {"error": str(error)}, "status": 400}
        if user.get("role") != "superadmin" and next_company_id != user.get("company_id"):
            return {"error": {"error": "forbidden_company"}, "status": 403}

        company = self.repo.get_company_row(db, next_company_id)
        if not company or company.get("deleted_at"):
            return {"error": {"error": "company_not_available"}, "status": 400}

        try:
            subcompany_id = resolve_subcompany_id(
                db, next_company_id, payload.get("subcompanyId", worker.get("subcompany_id"))
            )
        except ValueError as error:
            return {"error": {"error": str(error)}, "status": 400}

        try:
            updated_photo_data = sanitize_photo_data(
                payload.get("photoData", worker.get("photo_data")), required=True
            )
        except ValueError as error:
            return {"error": {"error": str(error)}, "status": 400}

        worker_type = normalize_worker_type(payload.get("workerType", worker.get("worker_type")))
        visitor_company = clean_text_input(
            payload.get("visitorCompany", worker.get("visitor_company")) or "", max_len=120
        )
        visit_purpose = clean_text_input(
            payload.get("visitPurpose", worker.get("visit_purpose")) or "", max_len=200
        )
        host_name = clean_text_input(
            payload.get("hostName", worker.get("host_name")) or "", max_len=120
        )
        visit_end_raw = payload.get("visitEndAt", worker.get("visit_end_at"))
        visit_end_at = (
            parse_datetime_local_to_utc_iso(visit_end_raw) if visit_end_raw else ""
        )

        visitor_err = self._validate_visitor_fields(
            worker_type, visitor_company, visit_purpose, host_name, visit_end_at
        )
        if visitor_err:
            return visitor_err

        next_badge_pin_hash = worker.get("badge_pin_hash") or ""
        raw_badge_pin = payload.get("badgePin")
        if worker_type != "visitor" and raw_badge_pin is not None:
            normalized_candidate_pin = normalize_badge_pin(raw_badge_pin)
            if normalized_candidate_pin:
                try:
                    validated_pin = validate_badge_pin_or_raise(normalized_candidate_pin)
                except ValueError as error:
                    return {
                        "error": {
                            "error": str(error),
                            "message": "Badge-PIN muss aus 4 bis 8 Ziffern bestehen.",
                        },
                        "status": 400,
                    }
                next_badge_pin_hash = generate_password_hash(validated_pin)
            elif not next_badge_pin_hash:
                return {
                    "error": {
                        "error": "badge_pin_required",
                        "message": "Bitte eine Badge-PIN fuer diesen Mitarbeiter setzen.",
                    },
                    "status": 400,
                }
        if worker_type != "visitor" and not next_badge_pin_hash:
            return {
                "error": {
                    "error": "badge_pin_required",
                    "message": "Bitte eine Badge-PIN fuer diesen Mitarbeiter setzen.",
                },
                "status": 400,
            }

        next_physical_card_id = normalize_physical_card_id(
            payload.get("physicalCardId", worker.get("physical_card_id"))
        )
        try:
            ensure_unique_physical_card_id_or_raise(
                db, next_physical_card_id, worker_id_to_exclude=worker_id
            )
        except ValueError as error:
            return {
                "error": {
                    "error": str(error),
                    "message": "Diese Karten-ID ist bereits einem anderen Mitarbeiter zugeordnet.",
                },
                "status": 409,
            }

        next_first_name = clean_text_input(payload.get("firstName", worker.get("first_name")), max_len=80)
        next_last_name = clean_text_input(payload.get("lastName", worker.get("last_name")), max_len=80)
        next_insurance_number = clean_text_input(
            payload.get("insuranceNumber", worker.get("insurance_number")), max_len=64
        )
        next_role = clean_text_input(payload.get("role", worker.get("role")), max_len=120)
        next_site = clean_text_input(payload.get("site", worker.get("site")), max_len=120)
        next_valid_until = clean_text_input(
            payload.get("validUntil", worker.get("valid_until")), max_len=32
        )
        next_status = clean_text_input(payload.get("status", worker.get("status")), max_len=32) or worker.get(
            "status"
        )

        if photo_override_needs_approval and updated_photo_data != (worker.get("photo_data") or ""):
            approval_payload = {
                "workerId": worker_id,
                "companyId": next_company_id,
                "subcompanyId": subcompany_id,
                "firstName": next_first_name,
                "lastName": next_last_name,
                "insuranceNumber": next_insurance_number if worker_type != "visitor" else "",
                "workerType": worker_type,
                "role": next_role
                if worker_type != "visitor"
                else (next_role or visitor_company or "Besucher"),
                "site": next_site,
                "validUntil": next_valid_until,
                "visitorCompany": visitor_company,
                "visitPurpose": visit_purpose,
                "hostName": host_name,
                "visitEndAt": visit_end_at,
                "status": next_status,
                "photoData": updated_photo_data,
                "badgePinHash": next_badge_pin_hash if worker_type != "visitor" else "",
                "physicalCardId": next_physical_card_id,
                "photoMatchOverrideReason": photo_override_reason,
                "photoMatchSimilarity": photo_similarity,
            }
            approval_id = create_operation_approval(
                db,
                action_type="worker.photo_override",
                payload=approval_payload,
                actor=user,
                target_type="worker",
                target_id=worker_id,
                company_id=next_company_id,
            )
            return {
                "status": 202,
                "body": {
                    "ok": True,
                    "approvalRequested": True,
                    "approvalId": approval_id,
                    "message": "Foto-Override erfordert eine zweite Superadmin-Freigabe.",
                },
            }

        try:
            _persist_worker_compliance_fields(db, worker_id, payload, user, is_new=False)
        except ValueError as error:
            code = str(error)
            return {"error": {"error": code}, "status": 400}

        from backend.server import apply_worker_site_coordinates_from_payload

        try:
            apply_worker_site_coordinates_from_payload(db, worker_id, payload, dict(worker))
        except ValueError as error:
            return {"error": {"error": str(error)}, "status": 400}

        self.repo.update_worker(
            db,
            worker_id,
            company_id=next_company_id,
            subcompany_id=subcompany_id,
            first_name=next_first_name,
            last_name=next_last_name,
            insurance_number=next_insurance_number if worker_type != "visitor" else "",
            worker_type=worker_type,
            role=next_role
            if worker_type != "visitor"
            else (next_role or visitor_company or "Besucher"),
            site=next_site,
            valid_until=next_valid_until,
            visitor_company=visitor_company,
            visit_purpose=visit_purpose,
            host_name=host_name,
            visit_end_at=visit_end_at,
            status=next_status,
            photo_data=updated_photo_data,
            badge_pin_hash=next_badge_pin_hash if worker_type != "visitor" else "",
            physical_card_id=next_physical_card_id,
            contact_email=clean_text_input(
                payload.get("contactEmail", worker.get("contact_email") or "") or "",
                max_len=200,
            ),
            leave_balance=max(
                0,
                int(
                    payload.get(
                        "leaveBalance",
                        worker.get("leave_balance")
                        if worker.get("leave_balance") is not None
                        else 30,
                    )
                ),
            ),
        )
        self._apply_worker_personal_fields(db, worker_id, payload, worker)
        db.commit()

        photo_override_audit = None
        if photo_override_requested and updated_photo_data != (worker.get("photo_data") or ""):
            similarity_label = (
                f"{photo_similarity * 100:.1f}%"
                if isinstance(photo_similarity, float)
                else "n/a"
            )
            photo_override_audit = {
                "worker_id": worker_id,
                "company_id": worker.get("company_id"),
                "message": (
                    f"Foto-Override fuer Mitarbeiter {worker_id} bestaetigt "
                    f"(Aehnlichkeit: {similarity_label}, Grund: {photo_override_reason})"
                ),
            }

        return {
            "body": {"ok": True},
            "audit": {"worker_id": worker_id, "company_id": worker.get("company_id")},
            "photo_override_audit": photo_override_audit,
        }

    @staticmethod
    def _validate_visitor_fields(
        worker_type: str,
        visitor_company: str,
        visit_purpose: str,
        host_name: str,
        visit_end_at: str,
    ) -> dict[str, Any] | None:
        if worker_type != "visitor":
            return None
        if not visit_purpose:
            return {"error": {"error": "visit_purpose_required"}, "status": 400}
        if not visitor_company:
            return {"error": {"error": "visitor_company_required"}, "status": 400}
        if not host_name:
            return {"error": {"error": "host_name_required"}, "status": 400}
        if not visit_end_at:
            return {"error": {"error": "visit_end_required"}, "status": 400}
        return None

    @staticmethod
    def _parse_photo_similarity(raw) -> float | None | dict[str, Any]:
        if raw is None or str(raw).strip() == "":
            return None
        try:
            photo_similarity = float(raw)
        except (TypeError, ValueError):
            return {"error": {"error": "invalid_photo_match_similarity"}, "status": 400}
        if photo_similarity < 0 or photo_similarity > 1:
            return {"error": {"error": "invalid_photo_match_similarity"}, "status": 400}
        return photo_similarity

    def set_worker_lock(
        self, db, user: dict[str, Any], worker_id: str, *, status: str
    ) -> dict[str, Any]:
        denied = self.check_lock_role(user)
        if denied:
            return denied
        status = str(status or "").strip().lower()
        if status not in ("gesperrt", "aktiv"):
            return {"error": {"error": "invalid_status"}, "status": 400}

        loaded = self._get_worker_or_error(db, user, worker_id)
        if "error" in loaded:
            return loaded
        worker = loaded["worker"]

        if user.get("role") != "superadmin" and worker.get("company_id") != user.get(
            "company_id"
        ):
            return {"error": {"error": "forbidden_worker"}, "status": 403}

        self.repo.set_status(db, worker_id, status)
        db.commit()
        action = "worker.locked" if status == "gesperrt" else "worker.unlocked"
        return {
            "body": {"ok": True, "status": status},
            "audit": {
                "action": action,
                "worker_id": worker_id,
                "company_id": worker.get("company_id"),
                "status": status,
            },
        }

    def reset_worker_pin(
        self, db, user: dict[str, Any], worker_id: str, *, new_pin: str
    ) -> dict[str, Any]:
        from werkzeug.security import generate_password_hash

        from backend.server import (
            company_has_feature,
            feature_not_available_response,
            get_company_plan,
            normalize_badge_pin,
            validate_badge_pin_or_raise,
        )

        loaded = self._get_worker_or_error(db, user, worker_id)
        if "error" in loaded:
            return loaded
        worker = loaded["worker"]

        if user.get("role") != "superadmin":
            plan_value = get_company_plan(db, worker.get("company_id"))
            if not company_has_feature(plan_value, "nfc_badges"):
                resp, status = feature_not_available_response("nfc_badges", plan_value)
                return {"error": resp.get_json(), "status": status}

        badge_id = str(worker.get("badge_id") or "")
        if badge_id.upper().startswith("VS"):
            return {
                "error": {
                    "error": "visitor_no_pin",
                    "message": "Besucher haben keine Badge-PIN.",
                },
                "status": 400,
            }

        raw_pin = normalize_badge_pin(new_pin)
        if not raw_pin:
            return {
                "error": {
                    "error": "missing_pin",
                    "message": "Bitte eine neue PIN angeben.",
                },
                "status": 400,
            }
        try:
            validated_pin = validate_badge_pin_or_raise(raw_pin)
        except ValueError as error:
            return {
                "error": {"error": "invalid_pin", "message": str(error)},
                "status": 400,
            }

        self.repo.set_badge_pin_hash(
            db, worker_id, generate_password_hash(validated_pin)
        )
        db.commit()
        return {
            "body": {"ok": True},
            "audit": {
                "worker_id": worker_id,
                "company_id": worker.get("company_id"),
                "message": (
                    f"Badge-PIN fuer {worker.get('first_name')} {worker.get('last_name')} "
                    f"(Badge {badge_id}) wurde zurueckgesetzt"
                ),
            },
        }

    @staticmethod
    def _normalize_bulk_ids(ids: Any) -> list[str]:
        if not isinstance(ids, list) or not ids:
            return []
        return [str(item) for item in ids if isinstance(item, str) and item.strip()][:200]

    def get_compliance_signature(
        self, db, user: dict[str, Any], worker_id: str
    ) -> dict[str, Any]:
        worker = self.repo.get_by_id_global(db, worker_id)
        if not worker:
            return {"error": {"error": "worker_not_found"}, "status": 404}
        denied = self.check_worker_access(user, worker)
        if denied:
            return denied
        return {
            "body": {
                "workerId": worker_id,
                "signatureData": worker.get("compliance_signature_data") or "",
                "signatureAt": worker.get("compliance_signature_at") or "",
                "capturedByUserId": worker.get("compliance_signature_captured_by") or "",
                "idHandoverAt": worker.get("id_handover_at") or "",
            }
        }

    def put_compliance_signature(
        self, db, user: dict[str, Any], worker_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        from backend.server import (
            _persist_worker_compliance_fields,
            _worker_compliance_signature_meta,
        )

        loaded = self._get_worker_or_error(db, user, worker_id)
        if "error" in loaded:
            return loaded
        try:
            _persist_worker_compliance_fields(
                db, worker_id, payload, user, is_new=False
            )
        except ValueError as error:
            return {"error": {"error": str(error)}, "status": 400}
        db.commit()
        row = self.repo.get_by_id_global(db, worker_id)
        meta = _worker_compliance_signature_meta(row)
        return {
            "body": {
                "ok": True,
                **meta,
                "signatureData": (row or {}).get("compliance_signature_data") or "",
            }
        }

    def bulk_update_status(
        self, db, user: dict[str, Any], *, ids: Any, status: str
    ) -> dict[str, Any]:
        worker_ids = self._normalize_bulk_ids(ids)
        if not worker_ids:
            return {"error": {"error": "missing_ids"}, "status": 400}
        if status not in ("aktiv", "inaktiv", "gesperrt"):
            return {"error": {"error": "invalid_status"}, "status": 400}

        updated = 0
        for worker_id in worker_ids:
            worker = self.repo.get_worker_brief(db, worker_id)
            if not worker or worker.get("deleted_at"):
                continue
            if user.get("role") != "superadmin" and worker.get("company_id") != user.get(
                "company_id"
            ):
                continue
            self.repo.set_status(db, worker_id, status)
            updated += 1
        db.commit()
        return {
            "body": {"ok": True, "updated": updated},
            "audit": {"updated": updated, "status": status},
        }

    def _require_document_upload_feature(
        self, db, company_id: str
    ) -> dict[str, Any] | None:
        from backend.server import (
            company_has_feature,
            feature_not_available_response,
            get_company_plan,
        )

        plan_value = get_company_plan(db, company_id)
        if not company_has_feature(plan_value, "document_upload"):
            resp, status = feature_not_available_response("document_upload", plan_value)
            return {"error": resp.get_json(), "status": status}
        return None

    def _load_worker_for_documents(
        self, db, user: dict[str, Any], worker_id: str
    ) -> dict[str, Any]:
        worker = self.repo.get_by_id_global(db, worker_id)
        if not worker:
            return {"error": {"error": "worker_not_found"}, "status": 404}
        denied = self.check_worker_access(user, worker)
        if denied:
            return denied
        feature_err = self._require_document_upload_feature(db, worker["company_id"])
        if feature_err:
            return feature_err
        return {"worker": worker}

    def list_worker_documents(
        self, db, user: dict[str, Any], worker_id: str
    ) -> dict[str, Any]:
        loaded = self._load_worker_for_documents(db, user, worker_id)
        if "error" in loaded:
            return loaded
        docs = self.repo.list_worker_documents(db, worker_id)
        return {"body": docs}

    def upload_worker_document(
        self,
        db,
        user: dict[str, Any],
        worker_id: str,
        *,
        doc_type_raw: str,
        notes_raw: str,
        expiry_date_raw: str,
        filename: str | None,
        mimetype: str,
        file_data: bytes,
        e2e_meta: str | None = None,
        encrypted: bool = False,
    ) -> dict[str, Any]:
        import secrets

        from backend.app.platform.security.e2e_envelope import assert_e2e_attachment, assert_e2e_sensitive_field
        from backend.app.platform.security.e2e_policy import is_e2e_attachment_required, is_e2e_sensitive_required
        from backend.app.platform.worker_documents import (
            ALLOWED_WORKER_DOC_TYPES as ALLOWED_DOC_TYPES,
            normalize_doc_type,
        )
        from backend.app.platform.documents.verify import verify_worker_document_upload
        from backend.server import (
            ALLOWED_UPLOAD_MIMETYPES,
            DOCS_UPLOAD_DIR,
            MAX_IMAP_ATTACHMENT_BYTES,
            _sanitize_attachment_filename,
            _stored_file_path,
            clean_text_input,
            normalize_upload_mimetype,
            now_iso,
            unlock_worker_if_documents_valid,
            utc_now,
            validate_document_expiry_date,
        )

        doc_type = normalize_doc_type(clean_text_input(doc_type_raw, max_len=64))
        notes = clean_text_input(notes_raw, max_len=500)
        expiry_date, expiry_error, expiry_message = validate_document_expiry_date(
            doc_type, expiry_date_raw
        )

        if doc_type not in ALLOWED_DOC_TYPES:
            return {
                "error": {
                    "error": "invalid_doc_type",
                    "allowed": sorted(ALLOWED_DOC_TYPES),
                },
                "status": 400,
            }
        if expiry_error:
            return {
                "error": {"error": expiry_error, "message": expiry_message},
                "status": 400,
            }
        if not filename:
            return {"error": {"error": "missing_file"}, "status": 400}

        mime = normalize_upload_mimetype(mimetype, filename)
        e2e_cipher_mimes = {
            "application/vnd.suppix.e2e+binary",
            "application/octet-stream",
            "binary/octet-stream",
        }
        if encrypted:
            if mime not in ALLOWED_UPLOAD_MIMETYPES and mime not in e2e_cipher_mimes:
                return {"error": {"error": "invalid_file_type"}, "status": 400}
        elif mime not in ALLOWED_UPLOAD_MIMETYPES:
            return {"error": {"error": "invalid_file_type"}, "status": 400}
        if not file_data:
            return {
                "error": {
                    "error": "empty_file",
                    "message": "Die Datei ist leer.",
                },
                "status": 400,
            }
        if len(file_data) > MAX_IMAP_ATTACHMENT_BYTES:
            return {
                "error": {
                    "error": "file_too_large",
                    "maxBytes": MAX_IMAP_ATTACHMENT_BYTES,
                },
                "status": 400,
            }

        loaded = self._load_worker_for_documents(db, user, worker_id)
        if "error" in loaded:
            return loaded
        worker = loaded["worker"]
        company_id = str(worker.get("company_id") or "")
        if is_e2e_attachment_required(db, company_id):
            try:
                assert_e2e_attachment(
                    e2e_meta=str(e2e_meta or ""),
                    content_type=str(mimetype or ""),
                    encrypted=bool(encrypted),
                )
            except ValueError as exc:
                return {"error": {"error": str(exc)}, "status": 400}
        if notes and is_e2e_sensitive_required(db, company_id):
            try:
                assert_e2e_sensitive_field(notes, field_name="notes")
            except ValueError as exc:
                return {"error": {"error": str(exc)}, "status": 400}

        verification = verify_worker_document_upload(
            doc_type=doc_type,
            filename=str(filename or ""),
            claimed_mime=mime,
            file_data=file_data,
            encrypted=bool(encrypted),
        )
        if not verification.get("ok"):
            return {
                "error": {
                    "error": verification.get("error") or "document_verification_failed",
                    "message": verification.get("message")
                    or "Dokumentprüfung fehlgeschlagen.",
                    "verification": {
                        "status": verification.get("status"),
                        "score": verification.get("score"),
                        "reasons": verification.get("reasons") or [],
                    },
                },
                "status": 400,
            }
        trusted_mime = verification.get("mime") or mime

        base_upload_root = DOCS_UPLOAD_DIR.resolve()
        worker_doc_dir = (DOCS_UPLOAD_DIR / worker_id).resolve()
        if worker_doc_dir != base_upload_root and base_upload_root not in worker_doc_dir.parents:
            return {"error": {"error": "invalid_storage_path"}, "status": 400}
        try:
            worker_doc_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            return {"error": {"error": "storage_error", "detail": str(exc)}, "status": 500}

        safe_name = _sanitize_attachment_filename(filename)
        ts = utc_now().strftime("%Y%m%d_%H%M%S")
        file_path = (worker_doc_dir / f"{doc_type}_{ts}_{safe_name}").resolve()
        if worker_doc_dir not in file_path.parents:
            return {"error": {"error": "invalid_target_path"}, "status": 400}

        try:
            file_path.write_bytes(file_data)
        except Exception as exc:
            return {"error": {"error": "write_error", "detail": str(exc)}, "status": 500}

        import json as _json

        stored_path = _stored_file_path(file_path)
        doc_id = f"doc-{secrets.token_hex(8)}"
        checked_at = now_iso()
        try:
            verification_payload = _json.dumps(
                {
                    "status": verification.get("status"),
                    "score": verification.get("score"),
                    "reasons": verification.get("reasons") or [],
                    "details": verification.get("details") or {},
                },
                ensure_ascii=False,
            )
        except Exception:
            verification_payload = "{}"
        self.repo.insert_worker_document(
            db,
            doc_id=doc_id,
            worker_id=worker_id,
            company_id=worker["company_id"],
            doc_type=doc_type,
            filename=safe_name,
            file_path=stored_path,
            file_size=len(file_data),
            uploaded_by_user_id=user["id"],
            created_at=checked_at,
            notes=notes,
            expiry_date=expiry_date,
            e2e_meta=str(e2e_meta or "").strip() or None,
            verification_status=str(verification.get("status") or "accepted"),
            verification_score=float(verification.get("score") or 0),
            verification_json=verification_payload,
            verification_checked_at=checked_at,
        )
        unlock_worker_if_documents_valid(db, worker, actor=user)
        try:
            from backend.app.domains.chat.service import ChatService
            from backend.app.platform.notifications.worker_mitteilung import document_type_label
            from backend.server import BASE_DIR

            ChatService(db).share_file_in_worker_thread(
                company_id=str(worker["company_id"]),
                worker_id=worker_id,
                filename=safe_name,
                content_type=trusted_mime,
                blob=file_data,
                body=f"{document_type_label(doc_type)}: {safe_name}",
                sender_type="admin",
                sender_user_id=str(user.get("id") or ""),
            )
        except Exception:
            pass
        try:
            from backend.app.platform.notifications.worker_mitteilung import (
                notify_worker_new_document,
            )

            notify_worker_new_document(db, worker_id, doc_type=doc_type, filename=safe_name)
        except Exception:
            pass
        db.commit()
        return {
            "body": {
                "ok": True,
                "documentId": doc_id,
                "verification": {
                    "status": verification.get("status"),
                    "score": verification.get("score"),
                    "message": verification.get("message") or "",
                },
            },
            "audit": {
                "worker_id": worker_id,
                "company_id": worker["company_id"],
                "badge_id": worker.get("badge_id"),
                "doc_type": doc_type,
                "filename": safe_name,
                "verification_status": verification.get("status"),
                "verification_score": verification.get("score"),
            },
        }

    def download_worker_document(
        self, db, user: dict[str, Any], worker_id: str, doc_id: str
    ) -> dict[str, Any]:
        from backend.server import BASE_DIR

        loaded = self._load_worker_for_documents(db, user, worker_id)
        if "error" in loaded:
            return loaded

        doc = self.repo.get_worker_document(db, worker_id, doc_id)
        if not doc:
            return {"error": {"error": "document_not_found"}, "status": 404}

        file_path = BASE_DIR / doc["file_path"]
        if not file_path.exists():
            return {"error": {"error": "file_not_found"}, "status": 404}

        return {
            "send_file": {
                "path": str(file_path),
                "download_name": doc["filename"],
            }
        }

    def delete_worker_document(
        self, db, user: dict[str, Any], worker_id: str, doc_id: str
    ) -> dict[str, Any]:
        from pathlib import Path

        from backend.server import BASE_DIR

        worker = self.repo.get_by_id_global(db, worker_id)
        if not worker:
            return {"error": {"error": "worker_not_found"}, "status": 404}
        denied = self.check_worker_access(user, worker)
        if denied:
            return denied
        feature_err = self._require_document_upload_feature(db, worker["company_id"])
        if feature_err:
            return feature_err

        doc = self.repo.get_worker_document(db, worker_id, doc_id)
        if not doc:
            return {"error": {"error": "document_not_found"}, "status": 404}

        file_path = BASE_DIR / doc["file_path"]
        try:
            if file_path.exists():
                file_path.unlink()
        except Exception:
            pass

        self.repo.delete_worker_document(db, doc_id)
        db.commit()
        return {"body": {"ok": True}}

    @staticmethod
    def _export_where_clause(
        user: dict[str, Any], *, include_deleted: bool, prefix: str = "workers."
    ) -> tuple[str, list[Any]]:
        from backend.server import visible_worker_clause

        where_clause, params = visible_worker_clause(user, prefix=prefix)
        if not include_deleted:
            where_clause = (
                f"{where_clause}{' AND' if where_clause else ' WHERE'} "
                f"{prefix}deleted_at IS NULL"
            )
        return where_clause, list(params)

    @staticmethod
    def _csv_column(row: dict[str, str], *candidates: str) -> str:
        for key in row:
            norm = (
                key.strip()
                .lower()
                .replace(" ", "_")
                .replace("-", "_")
                .replace("ä", "ae")
                .replace("ö", "oe")
                .replace("ü", "ue")
                .replace("ß", "ss")
            )
            if norm in candidates:
                return str(row[key] or "").strip()
        return ""

    def import_workers_csv(
        self, db, user: dict[str, Any], raw_bytes: bytes
    ) -> dict[str, Any]:
        import csv
        import io
        import secrets
        from datetime import datetime as dt

        from backend.server import normalize_badge_id

        if not raw_bytes:
            return {"error": {"error": "no_file"}, "status": 400}

        try:
            raw_text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            raw_text = raw_bytes.decode("latin-1", errors="replace")

        try:
            sample = raw_text[:2048]
            dialect = csv.Sniffer().sniff(sample, delimiters=",;|\t")
            reader = csv.DictReader(io.StringIO(raw_text), dialect=dialect)
        except csv.Error:
            reader = csv.DictReader(io.StringIO(raw_text))

        created: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        all_companies = self.repo.company_name_to_id_map(db)

        for row_num, row in enumerate(reader, start=2):
            try:
                first_name = self._csv_column(row, "vorname", "first_name", "firstname")
                last_name = self._csv_column(
                    row, "nachname", "last_name", "lastname", "name"
                )
                if not first_name or not last_name:
                    skipped.append({"row": row_num, "reason": "Vor- oder Nachname fehlt"})
                    continue

                company_name_raw = self._csv_column(
                    row, "firma", "company", "unternehmen", "company_name"
                )
                company_id = all_companies.get(company_name_raw.lower(), "")
                if not company_id:
                    for cn, cid in all_companies.items():
                        if (
                            company_name_raw.lower() in cn
                            or cn in company_name_raw.lower()
                        ):
                            company_id = cid
                            break
                if not company_id:
                    if user.get("role") == "company-admin":
                        company_id = user.get("company_id", "")
                    else:
                        skipped.append(
                            {
                                "row": row_num,
                                "reason": f"Firma '{company_name_raw}' nicht gefunden",
                            }
                        )
                        continue

                if user.get("role") == "company-admin" and company_id != user.get(
                    "company_id"
                ):
                    skipped.append({"row": row_num, "reason": "Firma nicht erlaubt"})
                    continue

                insurance_number = self._csv_column(
                    row,
                    "versicherungsnr",
                    "insurance_number",
                    "sozialversicherungsnr",
                    "svnr",
                )
                worker_type_raw = self._csv_column(row, "typ", "type", "worker_type").lower()
                worker_type = (
                    "worker" if worker_type_raw not in ("visitor", "besucher") else "visitor"
                )
                role_value = self._csv_column(row, "rolle", "role", "position") or "Mitarbeiter"
                site_value = self._csv_column(row, "baustelle", "site", "standort") or ""
                valid_until_raw = self._csv_column(
                    row,
                    "gueltig_bis",
                    "gueltigbis",
                    "valid_until",
                    "validuntil",
                    "ablaufdatum",
                )
                valid_until_value = None
                if valid_until_raw:
                    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
                        try:
                            parsed = dt.strptime(valid_until_raw, fmt)
                            valid_until_value = parsed.strftime("%Y-%m-%dT23:59:00")
                            break
                        except ValueError:
                            continue

                worker_id = f"wrk-{secrets.token_hex(6)}"
                badge_id_value = str(row_num).zfill(6)
                if self.repo.badge_id_exists(db, badge_id_value):
                    badge_id_value = secrets.token_hex(4)

                self.repo.insert_csv_import_worker(
                    db,
                    worker_id=worker_id,
                    company_id=company_id,
                    first_name=first_name,
                    last_name=last_name,
                    insurance_number=insurance_number,
                    worker_type=worker_type,
                    role_value=role_value,
                    site_value=site_value,
                    valid_until_value=valid_until_value,
                    badge_id_value=badge_id_value,
                    badge_id_lookup=normalize_badge_id(badge_id_value),
                )
                created.append(
                    {
                        "row": row_num,
                        "name": f"{first_name} {last_name}",
                        "id": worker_id,
                    }
                )
            except Exception as exc:
                errors.append({"row": row_num, "reason": str(exc)[:200]})

        if created:
            db.commit()

        return {
            "body": {
                "created": len(created),
                "skipped": len(skipped),
                "errors": len(errors),
                "details": {
                    "created": created[:50],
                    "skipped": skipped[:50],
                    "errors": errors[:50],
                },
            },
            "audit": {"created_count": len(created)} if created else None,
        }

    def export_workers_csv(
        self, db, user: dict[str, Any], *, include_deleted: bool
    ) -> dict[str, Any]:
        from .exports import build_workers_csv_bytes

        where_clause, params = self._export_where_clause(
            user, include_deleted=include_deleted
        )
        rows = self.repo.fetch_workers_csv_rows(db, where_clause, params)
        data = build_workers_csv_bytes(rows)
        return {
            "response": {
                "data": data,
                "mimetype": "application/octet-stream",
                "headers": {
                    "Content-Disposition": 'attachment; filename="mitarbeiterliste.csv"'
                },
            }
        }

    def export_workers_pdf(
        self,
        db,
        user: dict[str, Any],
        *,
        include_deleted: bool,
        include_photos: bool,
        period: str,
        date_param: str,
    ) -> dict[str, Any]:
        from datetime import datetime

        from .exports import build_workers_pdf_bytes

        try:
            period_date = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            period_date = datetime.now().date()

        where_clause, params = self._export_where_clause(
            user, include_deleted=include_deleted
        )
        period_label = ""
        if period == "day":
            day_str = period_date.isoformat()
            where_clause = (
                f"{where_clause}{' AND' if where_clause else ' WHERE'} "
                f"workers.id IN (SELECT DISTINCT worker_id FROM access_logs WHERE date(timestamp) = ?)"
            )
            params = list(params) + [day_str]
            period_label = f" | Tag: {day_str}"
        elif period == "week":
            week_start = (
                period_date - timedelta(days=period_date.weekday())
            ).isoformat()
            week_end = (
                period_date
                - timedelta(days=period_date.weekday())
                + timedelta(days=6)
            ).isoformat()
            where_clause = (
                f"{where_clause}{' AND' if where_clause else ' WHERE'} "
                "workers.id IN (SELECT DISTINCT worker_id FROM access_logs "
                "WHERE date(timestamp) >= ? AND date(timestamp) <= ?)"
            )
            params = list(params) + [week_start, week_end]
            period_label = f" | Woche: {week_start} – {week_end}"

        rows = self.repo.fetch_workers_pdf_rows(db, where_clause, params)
        pdf_result = build_workers_pdf_bytes(
            rows, include_photos=include_photos, period_label=period_label
        )
        if isinstance(pdf_result, dict) and "error" in pdf_result:
            return pdf_result

        filename = f"mitarbeiterliste-{datetime.now().strftime('%Y-%m-%d')}.pdf"
        return {
            "response": {
                "data": pdf_result,
                "mimetype": "application/pdf",
                "headers": {"Content-Disposition": f'attachment; filename="{filename}"'},
            }
        }

    def export_workers_signatures_zip(
        self, db, user: dict[str, Any], *, include_deleted: bool
    ) -> dict[str, Any]:
        import base64
        import io
        import re
        import zipfile
        from datetime import datetime

        where_clause, params = self._export_where_clause(
            user, include_deleted=include_deleted
        )
        where_clause = (
            f"{where_clause}{' AND' if where_clause else ' WHERE'} "
            "COALESCE(workers.compliance_signature_data, '') != '' "
            "AND COALESCE(workers.worker_type, 'worker') != 'visitor'"
        )
        rows = db.execute(
            f"""
            SELECT workers.id, workers.first_name, workers.last_name, workers.badge_id,
                   workers.compliance_signature_data
            FROM workers
            {where_clause}
            ORDER BY workers.last_name, workers.first_name
            """,
            params,
        ).fetchall()

        buf = io.BytesIO()
        generated = 0
        used_names: set[str] = set()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
            for row in rows:
                sig = str(row["compliance_signature_data"] or "").strip()
                if not sig.startswith("data:image"):
                    continue
                try:
                    _, encoded = sig.split(",", 1)
                    raw = base64.b64decode(encoded)
                except Exception:
                    continue
                safe_base = re.sub(
                    r"[^A-Za-z0-9_-]+",
                    "_",
                    f"{row['last_name']}_{row['first_name']}_{row['badge_id'] or row['id']}",
                )[:60]
                filename = f"{safe_base}.png"
                suffix = 2
                while filename in used_names:
                    filename = f"{safe_base}_{suffix}.png"
                    suffix += 1
                used_names.add(filename)
                archive.writestr(filename, raw)
                generated += 1

        if generated == 0:
            return {"error": {"error": "no_signatures"}, "status": 404}

        buf.seek(0)
        today = datetime.now().strftime("%Y-%m-%d")
        return {
            "response": {
                "data": buf.getvalue(),
                "mimetype": "application/zip",
                "headers": {
                    "Content-Disposition": f'attachment; filename="unterschriften-{today}.zip"'
                },
            }
        }

    def export_attendance_pdf(
        self, db, user: dict[str, Any], *, date_param: str
    ) -> dict[str, Any]:
        from datetime import datetime, timezone

        from backend.server import build_open_entries_from_rows, visible_worker_clause

        from .exports import build_attendance_pdf_bytes

        try:
            datetime.strptime(date_param, "%Y-%m-%d")
        except ValueError:
            date_param = datetime.now().strftime("%Y-%m-%d")

        settings = self.repo.get_settings_row(db)
        platform_label = (
            str(settings["platform_name"] or "WorkPass").strip() if settings else "WorkPass"
        )
        primary_color = (
            str(settings["invoice_primary_color"] or "#06b6d4").strip()
            if settings
            else "#06b6d4"
        )

        clause, params = visible_worker_clause(user, prefix="w.")
        rows = self.repo.fetch_attendance_source_rows(db, clause, params, date_param)
        now_dt = datetime.now(timezone.utc)
        open_entries = build_open_entries_from_rows(rows, now_dt)
        worker_id_to_company = {row["worker_id"]: row["company_name"] for row in rows}

        pdf_result = build_attendance_pdf_bytes(
            date_param=date_param,
            open_entries=open_entries,
            worker_id_to_company=worker_id_to_company,
            platform_label=platform_label,
            primary_color=primary_color,
        )
        if isinstance(pdf_result, dict) and "error" in pdf_result:
            return pdf_result

        filename = f"anwesenheitsliste-{date_param}.pdf"
        return {
            "response": {
                "data": pdf_result,
                "mimetype": "application/pdf",
                "headers": {"Content-Disposition": f'attachment; filename="{filename}"'},
            }
        }

    def _require_worker_app_feature(self, db, company_id: str | None) -> dict[str, Any] | None:
        if not company_id:
            return None
        from backend.server import (
            company_has_feature,
            feature_not_available_response,
            get_company_plan,
        )

        plan_value = get_company_plan(db, company_id)
        if not company_has_feature(plan_value, "worker_app"):
            resp, status = feature_not_available_response("worker_app", plan_value)
            return {"error_response": (resp, status)}
        return None

    def _load_worker_admin_scope(
        self, db, user: dict[str, Any], worker_id: str, *, require_active: bool = False
    ) -> dict[str, Any]:
        worker = self.repo.get_by_id_global(db, worker_id)
        if not worker:
            return {"error": {"error": "worker_not_found"}, "status": 404}
        if user.get("role") != "superadmin" and worker.get("company_id") != user.get(
            "company_id"
        ):
            return {"error": {"error": "forbidden_worker"}, "status": 403}
        if require_active and worker.get("deleted_at"):
            return {"error": {"error": "worker_not_found"}, "status": 404}
        return {"worker": worker}

    def _load_worker_identity_scope(
        self, db, user: dict[str, Any], worker_id: str
    ) -> dict[str, Any]:
        worker = self.repo.get_by_id_global(db, worker_id)
        if not worker or worker.get("deleted_at"):
            return {"error": {"error": "worker_not_found"}, "status": 404}
        if user.get("role") != "superadmin" and user.get("company_id") != worker.get(
            "company_id"
        ):
            return {"error": {"error": "forbidden_company_scope"}, "status": 403}
        return {"worker": worker}

    def list_hce_devices(
        self, db, user: dict[str, Any], worker_id: str
    ) -> dict[str, Any]:
        loaded = self._load_worker_admin_scope(db, user, worker_id)
        if "error" in loaded:
            return loaded
        devices = []
        for row in self.repo.list_hce_devices(db, worker_id):
            devices.append(
                {
                    "id": row["id"],
                    "deviceId": row["device_id"],
                    "platform": row["platform"],
                    "appVersion": row["app_version"],
                    "status": row["status"],
                    "trustVersion": int(row["trust_version"] or 1),
                    "signatureAlgo": row["signature_algo"] or "",
                    "hasPublicKey": bool(row["device_public_key"]),
                    "createdAt": row["created_at"],
                    "lastSeenAt": row["last_seen_at"],
                }
            )
        return {"body": {"workerId": worker_id, "devices": devices}}

    def revoke_hce_device(
        self, db, user: dict[str, Any], worker_id: str, device_id: str
    ) -> dict[str, Any]:
        from backend.server import clean_id_input

        loaded = self._load_worker_admin_scope(db, user, worker_id)
        if "error" in loaded:
            return loaded
        worker = loaded["worker"]
        try:
            normalized_device_id = clean_id_input(device_id, max_len=80)
        except ValueError as error:
            return {"error": {"error": str(error)}, "status": 400}

        row = self.repo.get_hce_device(db, worker_id, normalized_device_id)
        if not row:
            return {"error": {"error": "hce_device_not_found"}, "status": 404}

        self.repo.revoke_hce_device(db, row["id"], normalized_device_id)
        db.commit()
        return {
            "body": {
                "ok": True,
                "status": "revoked",
                "deviceId": normalized_device_id,
            },
            "audit": {
                "action": "hce.device_revoked",
                "message": (
                    f"HCE-Geraet {normalized_device_id} fuer Worker {worker_id} gesperrt"
                ),
                "worker_id": worker_id,
                "company_id": worker.get("company_id"),
            },
        }

    def activate_hce_device(
        self, db, user: dict[str, Any], worker_id: str, device_id: str
    ) -> dict[str, Any]:
        from backend.server import clean_id_input, now_iso

        loaded = self._load_worker_admin_scope(db, user, worker_id)
        if "error" in loaded:
            return loaded
        worker = loaded["worker"]
        try:
            normalized_device_id = clean_id_input(device_id, max_len=80)
        except ValueError as error:
            return {"error": {"error": str(error)}, "status": 400}

        row = self.repo.get_hce_device(db, worker_id, normalized_device_id)
        if not row:
            return {"error": {"error": "hce_device_not_found"}, "status": 404}

        self.repo.activate_hce_device(db, row["id"], now_iso())
        db.commit()
        return {
            "body": {
                "ok": True,
                "status": "active",
                "deviceId": normalized_device_id,
            },
            "audit": {
                "action": "hce.device_activated",
                "message": (
                    f"HCE-Geraet {normalized_device_id} fuer Worker {worker_id} reaktiviert"
                ),
                "worker_id": worker_id,
                "company_id": worker.get("company_id"),
            },
        }

    def get_worker_app_access(
        self, db, user: dict[str, Any], worker_id: str
    ) -> dict[str, Any]:
        from backend.server import build_worker_app_access_payload

        company_id = self.repo.get_worker_company_id(db, worker_id)
        feature_err = self._require_worker_app_feature(db, company_id)
        if feature_err:
            return feature_err

        payload, error_response = build_worker_app_access_payload(
            db, worker_id, user, issue_new_token=False
        )
        if error_response:
            return {"error_response": error_response}
        return {"body": payload}

    def create_worker_app_access(
        self, db, user: dict[str, Any], worker_id: str
    ) -> dict[str, Any]:
        from backend.server import build_worker_app_access_payload

        company_id = self.repo.get_worker_company_id(db, worker_id)
        feature_err = self._require_worker_app_feature(db, company_id)
        if feature_err:
            return feature_err

        payload, error_response = build_worker_app_access_payload(
            db, worker_id, user, issue_new_token=True
        )
        if error_response:
            return {"error_response": error_response}

        worker = self.repo.get_by_id_global(db, worker_id)
        return {
            "body": payload,
            "audit": {
                "worker_id": worker_id,
                "company_id": (worker or {}).get("company_id"),
            },
        }

    def get_worker_identity_token(
        self, db, user: dict[str, Any], worker_id: str
    ) -> dict[str, Any]:
        loaded = self._load_worker_identity_scope(db, user, worker_id)
        if "error" in loaded:
            return loaded

        row = self.repo.get_identity_token_row(db, worker_id)
        if not row:
            return {"body": {"workerId": worker_id, "configured": False}}

        return {
            "body": {
                "workerId": worker_id,
                "configured": True,
                "status": str(row.get("status") or ""),
                "tokenHint": str(row.get("token_hint") or ""),
                "issuedAt": str(row.get("issued_at") or ""),
                "expiresAt": str(row.get("expires_at") or ""),
                "lastUsedAt": str(row.get("last_used_at") or ""),
                "lastDeviceId": str(row.get("last_device_id") or ""),
                "lastSource": str(row.get("last_source") or ""),
            }
        }

    def create_or_rotate_worker_identity_token(
        self, db, user: dict[str, Any], worker_id: str, *, rotate: bool
    ) -> dict[str, Any]:
        from backend.server import IDENTITY_TOKEN_TTL_DAYS, issue_worker_identity_token

        loaded = self._load_worker_identity_scope(db, user, worker_id)
        if "error" in loaded:
            return loaded
        worker = loaded["worker"]

        result = issue_worker_identity_token(db, worker, rotate=rotate)
        db.commit()
        return {
            "body": {
                "workerId": worker_id,
                "created": bool(result["created"]),
                "rotated": bool(result["rotated"]),
                "status": result["status"],
                "token": result["token"],
                "tokenHint": result["tokenHint"],
                "issuedAt": result["issuedAt"],
                "expiresAt": result["expiresAt"],
                "lastUsedAt": result["lastUsedAt"],
                "ttlDays": IDENTITY_TOKEN_TTL_DAYS,
            },
            "audit": {
                "action": (
                    "worker.identity_token_rotated"
                    if result["rotated"]
                    else "worker.identity_token_created"
                ),
                "message": (
                    f"Unified identity token fuer Worker {worker_id} "
                    f"{'rotiert' if result['rotated'] else 'erstellt'}"
                ),
                "worker_id": worker_id,
                "company_id": worker.get("company_id"),
            },
        }

    def set_worker_identity_token_status(
        self, db, user: dict[str, Any], worker_id: str, *, status: str
    ) -> dict[str, Any]:
        loaded = self._load_worker_identity_scope(db, user, worker_id)
        if "error" in loaded:
            return loaded
        worker = loaded["worker"]

        token_row = self.repo.get_identity_token_row(db, worker_id)
        if not token_row:
            return {"error": {"error": "identity_token_not_configured"}, "status": 404}

        status_value = str(status or "").strip().lower()
        if status_value not in ("active", "revoked"):
            return {
                "error": {"error": "invalid_status", "allowed": ["active", "revoked"]},
                "status": 400,
            }

        self.repo.set_identity_token_status(db, token_row["id"], status_value)
        db.commit()

        refreshed = self.repo.get_identity_token_row(db, worker_id) or {}
        return {
            "body": {
                "workerId": worker_id,
                "status": str(refreshed.get("status") or ""),
                "tokenHint": str(refreshed.get("token_hint") or ""),
                "issuedAt": str(refreshed.get("issued_at") or ""),
                "expiresAt": str(refreshed.get("expires_at") or ""),
                "lastUsedAt": str(refreshed.get("last_used_at") or ""),
                "lastDeviceId": str(refreshed.get("last_device_id") or ""),
                "lastSource": str(refreshed.get("last_source") or ""),
            },
            "audit": {
                "action": "worker.identity_token_status_changed",
                "message": (
                    f"Unified identity token fuer Worker {worker_id} "
                    f"auf {status_value} gesetzt"
                ),
                "worker_id": worker_id,
                "company_id": worker.get("company_id"),
            },
        }

    def export_leave_request_pdf(
        self, db, user: dict[str, Any], req_id: str
    ) -> dict[str, Any]:
        from backend.server import row_to_dict

        from .exports import build_leave_request_pdf_bytes

        if user.get("role") not in ("superadmin", "company-admin", "turnstile"):
            return {"error": {"error": "forbidden"}, "status": 403}

        row = self.repo.get_leave_request_export_row(db, req_id)
        if not row:
            return {"error": {"error": "not_found"}, "status": 404}

        if user.get("role") != "superadmin" and row["company_id"] != user.get(
            "company_id"
        ):
            return {"error": {"error": "forbidden"}, "status": 403}

        data = row_to_dict(row)
        from backend.app.platform.workforce.deployment_branding import resolve_company_pdf_branding

        branding = resolve_company_pdf_branding(db, str(row.get("company_id") or ""))
        data["companyName"] = branding.get("companyName") or data.get("portal_display_name") or data.get("company_name")
        data["logoData"] = branding.get("logoData") or data.get("branding_logo_data") or ""
        data["accent"] = branding.get("accent") or data.get("branding_accent_color") or ""
        if not str(data.get("worker_signature_name") or "").strip():
            data["worker_signature_name"] = data.get("worker_name") or ""
        pdf_result = build_leave_request_pdf_bytes(data)
        if isinstance(pdf_result, dict) and "error" in pdf_result:
            return pdf_result

        filename = f"urlaubsantrag-{str(req_id)[:24]}.pdf"
        return {
            "response": {
                "data": pdf_result,
                "mimetype": "application/pdf",
                "headers": {"Content-Disposition": f'attachment; filename="{filename}"'},
            }
        }

    def bulk_delete_workers(self, db, user: dict[str, Any], *, ids: Any) -> dict[str, Any]:
        from backend.server import now_iso

        worker_ids = self._normalize_bulk_ids(ids)
        if not worker_ids:
            return {"error": {"error": "missing_ids"}, "status": 400}

        deleted_at = now_iso()
        deleted = 0
        for worker_id in worker_ids:
            worker = self.repo.get_worker_brief(db, worker_id)
            if not worker or worker.get("deleted_at"):
                continue
            if user.get("role") != "superadmin" and worker.get("company_id") != user.get(
                "company_id"
            ):
                continue
            self.repo.soft_delete(db, worker_id, deleted_at=deleted_at)
            deleted += 1
        db.commit()
        return {
            "body": {"ok": True, "deleted": deleted},
            "audit": {"deleted": deleted},
        }

    @staticmethod
    def _apply_worker_personal_fields(db, worker_id: str, payload: dict[str, Any], worker: dict[str, Any]) -> None:
        from backend.app.domains.contracts.contract_locales import normalize_employee_gender
        from backend.server import clean_text_input

        from .repository import WorkersRepository

        repo = WorkersRepository()
        fields: dict[str, str] = {}
        if "homeAddress" in payload or "home_address" in payload:
            fields["home_address"] = clean_text_input(
                payload.get("homeAddress", payload.get("home_address", worker.get("home_address") or "")) or "",
                max_len=500,
            )
        if "birthDate" in payload or "birth_date" in payload:
            fields["birth_date"] = clean_text_input(
                payload.get("birthDate", payload.get("birth_date", worker.get("birth_date") or "")) or "",
                max_len=32,
            )
        if "gender" in payload or "employee_gender" in payload:
            raw = payload.get("gender", payload.get("employee_gender", worker.get("gender") or ""))
            fields["gender"] = normalize_employee_gender(raw) or clean_text_input(str(raw or ""), max_len=16)
        if "contactPhone" in payload or "contact_phone" in payload:
            fields["contact_phone"] = clean_text_input(
                payload.get("contactPhone", payload.get("contact_phone", worker.get("contact_phone") or "")) or "",
                max_len=40,
            )
        if fields:
            repo.update_worker_personal(
                db,
                worker_id,
                home_address=fields.get("home_address"),
                birth_date=fields.get("birth_date"),
                gender=fields.get("gender"),
                contact_phone=fields.get("contact_phone"),
            )
