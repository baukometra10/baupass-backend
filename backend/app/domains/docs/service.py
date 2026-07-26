"""WorkPass integrated document editor — service."""
from __future__ import annotations

import os
import re
from datetime import datetime
from html import escape as html_escape
from typing import Any
from zoneinfo import ZoneInfo

from .repository import EditorDocsRepository, dumps_json

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+\n")
_MERGE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def html_to_text(html: str) -> str:
    text = (html or "").replace("</p>", "\n").replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = _HTML_TAG_RE.sub("", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    text = _WS_RE.sub("\n", text)
    return text.strip()


def _today_de() -> str:
    try:
        now = datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:
        now = datetime.now()
    return now.strftime("%d.%m.%Y")


def apply_merge_map(content: str, mapping: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key in mapping and mapping[key]:
            return mapping[key]
        return match.group(0)

    return _MERGE_RE.sub(repl, content or "")


class EditorDocsService:
    def __init__(self) -> None:
        self.repo = EditorDocsRepository()

    def list_docs(self, db, *, company_id: str | None, mode: str = "", limit: int = 50) -> dict[str, Any]:
        items = self.repo.list_documents(db, company_id=company_id, mode=mode, limit=limit)
        return {"items": items, "count": len(items)}

    def get_doc(self, db, doc_id: str, *, company_id: str | None) -> dict[str, Any] | None:
        return self.repo.get_document(db, doc_id, company_id=company_id)

    def create_doc(self, db, *, company_id: str | None, actor_user_id: str | None, data: dict[str, Any]) -> dict[str, Any]:
        content_html = str(data.get("contentHtml") or data.get("content_html") or "")
        content_text = str(data.get("contentText") or data.get("content_text") or "")
        if not content_text and content_html:
            content_text = html_to_text(content_html)
        content_json = dumps_json(data.get("contentJson") if "contentJson" in data else data.get("content_json"))
        doc = self.repo.create_document(
            db,
            company_id=company_id,
            title=str(data.get("title") or "Unbenannt"),
            mode=str(data.get("mode") or "general"),
            content_json=content_json,
            content_html=content_html,
            content_text=content_text,
            worker_id=str(data.get("workerId") or data.get("worker_id") or "").strip() or None,
            contract_id=str(data.get("contractId") or data.get("contract_id") or "").strip() or None,
            actor_user_id=actor_user_id,
        )
        self.repo.add_version(
            db,
            document_id=str(doc.get("id")),
            company_id=company_id,
            title=str(doc.get("title") or ""),
            content_json=content_json,
            content_html=content_html,
            content_text=content_text,
            note="created",
            actor_user_id=actor_user_id,
        )
        return doc

    def update_doc(
        self,
        db,
        doc_id: str,
        *,
        company_id: str | None,
        actor_user_id: str | None,
        data: dict[str, Any],
        save_version: bool = True,
        version_note: str = "autosave",
    ) -> dict[str, Any] | None:
        content_html = data.get("contentHtml") if "contentHtml" in data else data.get("content_html")
        content_text = data.get("contentText") if "contentText" in data else data.get("content_text")
        if content_html is not None and content_text is None:
            content_text = html_to_text(str(content_html))
        content_json = None
        if "contentJson" in data or "content_json" in data:
            content_json = dumps_json(data.get("contentJson") if "contentJson" in data else data.get("content_json"))
        worker_raw = data.get("workerId") if "workerId" in data else data.get("worker_id", ...)
        contract_raw = data.get("contractId") if "contractId" in data else data.get("contract_id", ...)
        clear_worker = worker_raw is not ... and str(worker_raw or "").strip() == ""
        clear_contract = contract_raw is not ... and str(contract_raw or "").strip() == ""
        before = self.repo.get_document(db, doc_id, company_id=company_id)
        if before and str(before.get("status") or "") == "in_review":
            content_touch = (
                content_html is not None or content_text is not None or content_json is not None
            )
            note = str(data.get("versionNote") or data.get("version_note") or version_note or "")
            if content_touch and not note.startswith("suggestion-accept"):
                return {"error": "review_locked", "status": 409}
        doc = self.repo.update_document(
            db,
            doc_id,
            company_id=company_id,
            title=None if "title" not in data else str(data.get("title") or "Unbenannt"),
            mode=None if "mode" not in data else str(data.get("mode") or "general"),
            status=None if "status" not in data else str(data.get("status") or "draft"),
            content_json=content_json,
            content_html=None if content_html is None else str(content_html),
            content_text=None if content_text is None else str(content_text),
            worker_id=None if worker_raw is ... else (str(worker_raw or "").strip() or None),
            contract_id=None if contract_raw is ... else (str(contract_raw or "").strip() or None),
            clear_worker=clear_worker,
            clear_contract=clear_contract,
            actor_user_id=actor_user_id,
        )
        if not doc:
            return None
        content_changed = before and (
            (content_html is not None and str(before.get("content_html") or "") != str(doc.get("content_html") or ""))
            or (content_text is not None and str(before.get("content_text") or "") != str(doc.get("content_text") or ""))
            or (content_json is not None and str(before.get("content_json") or "") != str(doc.get("content_json") or ""))
        )
        if save_version and content_changed:
            self.repo.add_version(
                db,
                document_id=doc_id,
                company_id=company_id,
                title=str(doc.get("title") or ""),
                content_json=str(doc.get("content_json") or ""),
                content_html=str(doc.get("content_html") or ""),
                content_text=str(doc.get("content_text") or ""),
                note=str(data.get("versionNote") or data.get("version_note") or version_note),
                actor_user_id=actor_user_id,
            )
        return doc

    def delete_doc(self, db, doc_id: str, *, company_id: str | None) -> bool:
        return self.repo.delete_document(db, doc_id, company_id)

    def open_or_create_for_contract(
        self,
        db,
        *,
        company_id: str,
        contract_id: str,
        title: str,
        plain_text: str,
        actor_user_id: str | None,
    ) -> dict[str, Any]:
        existing = self.repo.find_by_contract(db, company_id, contract_id)
        if existing:
            return existing
        html = "".join(f"<p>{line}</p>" if line.strip() else "<p></p>" for line in (plain_text or "").splitlines()) or "<p></p>"
        return self.create_doc(
            db,
            company_id=company_id,
            actor_user_id=actor_user_id,
            data={
                "title": title or "Vertrag",
                "mode": "contract",
                "contractId": contract_id,
                "contentHtml": html,
                "contentText": plain_text or "",
                "contentJson": "",
            },
        )

    def build_merge_context(
        self,
        db,
        *,
        company_id: str,
        worker_id: str | None = None,
        actor_name: str | None = None,
    ) -> dict[str, Any]:
        company = None
        try:
            company = db.execute(
                """
                SELECT id, name, portal_display_name, contact, billing_email, document_email,
                       billing_street, billing_zip_city, branding_logo_data, branding_accent_color,
                       branding_preset
                FROM companies WHERE id = ?
                """,
                (company_id,),
            ).fetchone()
        except Exception:
            company = db.execute(
                "SELECT id, name, contact, billing_email, document_email FROM companies WHERE id = ?",
                (company_id,),
            ).fetchone()

        brand: dict[str, Any] = {}
        try:
            from backend.app.platform.workforce.deployment_branding import resolve_company_pdf_branding

            # Docs paper = tenant identity only (no SUPPIX platform logo fallback).
            brand = resolve_company_pdf_branding(
                db, company_id, allow_platform_logo_fallback=False
            ) or {}
        except Exception:
            brand = {}

        company_name = str(
            brand.get("companyName")
            or (company["portal_display_name"] if company and "portal_display_name" in company.keys() else "")
            or (company["name"] if company else "")
            or ""
        ).strip()
        street = str((company["billing_street"] if company and "billing_street" in company.keys() else "") or "").strip()
        zip_city = str(
            (company["billing_zip_city"] if company and "billing_zip_city" in company.keys() else "") or ""
        ).strip()
        contact = str((company["contact"] if company else "") or "").strip()
        email = str(
            (company["document_email"] if company else "")
            or (company["billing_email"] if company else "")
            or ""
        ).strip()
        address_line = ", ".join(p for p in (street, zip_city) if p)
        logo = str(brand.get("logoData") or "").strip()
        if not logo and company and "branding_logo_data" in company.keys():
            logo = str(company["branding_logo_data"] or "").strip()
        # Guard: never paint platform mark onto customer letterhead.
        if logo and re.search(r"suppix", logo, flags=re.I):
            logo = ""
        accent = str(brand.get("accent") or "#0ea5e9").strip()

        site_name = ""
        site_address = ""
        try:
            site = db.execute(
                """
                SELECT name, address, street, city
                FROM geofences
                WHERE company_id = ? AND COALESCE(active, 1) = 1
                ORDER BY name COLLATE NOCASE
                LIMIT 1
                """,
                (company_id,),
            ).fetchone()
            if site:
                site_name = str(site["name"] or "")
                site_address = str(
                    (site["address"] if "address" in site.keys() else "")
                    or " ".join(
                        p
                        for p in (
                            (site["street"] if "street" in site.keys() else "") or "",
                            (site["city"] if "city" in site.keys() else "") or "",
                        )
                        if p
                    )
                    or ""
                ).strip()
        except Exception:
            try:
                site = db.execute(
                    """
                    SELECT name FROM geofences
                    WHERE company_id = ? AND COALESCE(active, 1) = 1
                    ORDER BY name COLLATE NOCASE
                    LIMIT 1
                    """,
                    (company_id,),
                ).fetchone()
                if site:
                    site_name = str(site["name"] or "")
            except Exception:
                site_name = ""

        worker_name = ""
        worker_badge = ""
        worker_first = ""
        worker_last = ""
        worker_email = ""
        worker_phone = ""
        worker_role = ""
        worker_site = ""
        worker_lang = "de"
        shift_site = ""
        shift_start = ""
        shift_end = ""
        if worker_id:
            worker = None
            try:
                worker = db.execute(
                    """
                    SELECT id, first_name, last_name, badge_id, email, phone, role, site
                    FROM workers
                    WHERE id = ? AND company_id = ? AND deleted_at IS NULL
                    """,
                    (worker_id, company_id),
                ).fetchone()
            except Exception:
                worker = db.execute(
                    """
                    SELECT id, first_name, last_name, badge_id
                    FROM workers
                    WHERE id = ? AND company_id = ? AND deleted_at IS NULL
                    """,
                    (worker_id, company_id),
                ).fetchone()
            if worker:
                worker_first = str(worker["first_name"] or "").strip()
                worker_last = str(worker["last_name"] or "").strip()
                worker_name = f"{worker_first} {worker_last}".strip()
                worker_badge = str(worker["badge_id"] or "")
                try:
                    worker_email = str(worker["email"] or "").strip()
                except Exception:
                    worker_email = ""
                try:
                    worker_phone = str(worker["phone"] or "").strip()
                except Exception:
                    worker_phone = ""
                try:
                    worker_role = str(worker["role"] or "").strip()
                except Exception:
                    worker_role = ""
                try:
                    worker_site = str(worker["site"] or "").strip()
                except Exception:
                    worker_site = ""
                if worker_site and not site_name:
                    site_name = worker_site
                for lang_key in ("preferred_lang", "app_lang", "locale", "lang"):
                    try:
                        if lang_key in worker.keys() and worker[lang_key]:
                            worker_lang = str(worker[lang_key] or "de").strip().lower()[:2] or "de"
                            break
                    except Exception:
                        continue
            # Next/current shift slot (no salary fields).
            try:
                from datetime import timezone as _tz

                now_iso = datetime.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                shift = db.execute(
                    """
                    SELECT site, start_time, end_time
                    FROM shift_assignments
                    WHERE company_id = ? AND worker_id = ?
                      AND status IN ('assigned', 'active', 'confirmed', 'open', '')
                      AND (end_time IS NULL OR end_time = '' OR end_time >= ?)
                    ORDER BY start_time ASC
                    LIMIT 1
                    """,
                    (company_id, worker_id, now_iso),
                ).fetchone()
                if shift:
                    shift_site = str(shift["site"] or "").strip()
                    shift_start = str(shift["start_time"] or "")[:16].replace("T", " ")
                    shift_end = str(shift["end_time"] or "")[:16].replace("T", " ")
                    if shift_site and not site_name:
                        site_name = shift_site
            except Exception:
                pass

        try:
            date_iso = datetime.now(ZoneInfo("Europe/Berlin")).strftime("%Y-%m-%d")
        except Exception:
            date_iso = datetime.now().strftime("%Y-%m-%d")

        sector = str(brand.get("sectorLabel") or "").strip()
        fields = {
            "company.name": company_name or "—",
            "company.contact": contact or "—",
            "company.email": email or "—",
            "company.address": address_line or "—",
            "company.street": street or "—",
            "company.zipCity": zip_city or "—",
            "company.phone": contact or "—",
            "company.sector": sector or "—",
            "worker.name": worker_name or "—",
            "worker.firstName": worker_first or "—",
            "worker.lastName": worker_last or "—",
            "worker.badge": worker_badge or "—",
            "worker.email": worker_email or "—",
            "worker.phone": worker_phone or "—",
            "worker.role": worker_role or "—",
            "worker.site": worker_site or site_name or "—",
            "worker.lang": worker_lang or "de",
            "site.name": site_name or "—",
            "site.address": site_address or "—",
            "shift.site": shift_site or site_name or "—",
            "shift.start": shift_start or "—",
            "shift.end": shift_end or "—",
            "shift.slot": (
                f"{shift_start} – {shift_end}".strip(" –")
                if shift_start or shift_end
                else "—"
            ),
            "date.today": _today_de(),
            "date.iso": date_iso,
            "manager.name": (actor_name or "").strip() or "—",
            "doc.title": "—",
        }

        letterhead = self.build_letterhead_html(
            company_name=company_name,
            logo_data=logo,
            accent=accent,
            sector=str(brand.get("sectorLabel") or ""),
            address=address_line,
            contact=contact,
            email=email,
        )

        return {
            "fields": fields,
            "companyId": company_id,
            "workerId": worker_id or "",
            "workerLang": worker_lang if worker_id else "de",
            "placeholders": [f"{{{{{k}}}}}" for k in fields.keys()],
            "branding": {
                "companyName": company_name,
                "logoData": logo,
                "accent": accent,
                "sectorLabel": str(brand.get("sectorLabel") or ""),
                "address": address_line,
                "street": street,
                "zipCity": zip_city,
                "contact": contact,
                "email": email,
            },
            "letterhead": letterhead,
        }

    def resolve_pack_variant_html(
        self,
        db,
        *,
        company_id: str,
        pack_id: str,
        locale: str,
        fallback_html: str = "",
    ) -> dict[str, Any]:
        """Find team template in the same policy pack for the requested locale."""
        import json as _json

        pack = str(pack_id or "").strip()
        loc = str(locale or "de").strip().lower()[:2] or "de"
        if not pack:
            return {"html": fallback_html, "locale": loc, "matched": False}
        templates = self.repo.list_templates(db, company_id, limit=200)
        best = None
        de_fallback = None
        for tpl in templates:
            lay_raw = tpl.get("layout_json") or ""
            try:
                lay = _json.loads(lay_raw) if isinstance(lay_raw, str) and lay_raw.strip() else {}
            except Exception:
                lay = {}
            if not isinstance(lay, dict):
                continue
            if str(lay.get("packId") or "") != pack:
                continue
            tpl_loc = str(lay.get("locale") or "de").strip().lower()[:2] or "de"
            if tpl_loc == loc:
                best = tpl
                break
            if tpl_loc == "de" and de_fallback is None:
                de_fallback = tpl
        chosen = best or de_fallback
        if not chosen:
            return {"html": fallback_html, "locale": loc, "matched": False}
        chosen_loc = loc
        try:
            clay = _json.loads(str(chosen.get("layout_json") or "") or "{}")
            if isinstance(clay, dict) and clay.get("locale"):
                chosen_loc = str(clay.get("locale")).strip().lower()[:2] or loc
        except Exception:
            chosen_loc = "de" if de_fallback and chosen is de_fallback else loc
        return {
            "html": str(chosen.get("content_html") or chosen.get("contentHtml") or fallback_html),
            "locale": chosen_loc,
            "matched": True,
            "templateId": chosen.get("id"),
            "title": chosen.get("title"),
        }

    def build_letterhead_html(
        self,
        *,
        company_name: str,
        logo_data: str = "",
        accent: str = "#0ea5e9",
        sector: str = "",
        address: str = "",
        contact: str = "",
        email: str = "",
    ) -> dict[str, str]:
        """HTML for paper header (logo + name) and footer (address/contact)."""
        name = html_escape((company_name or "Firma").strip() or "Firma", quote=True)
        sector_safe = html_escape((sector or "").strip() or " ", quote=True)
        accent = accent if re.match(r"^#[0-9a-fA-F]{6}$", accent or "") else "#0ea5e9"
        logo_html = ""
        raw_logo = str(logo_data or "").strip()
        # Tenant data-image logos only (no platform mark / script schemes).
        if (
            raw_logo.lower().startswith("data:image/")
            and "," in raw_logo
            and "javascript:" not in raw_logo.lower()
            and "suppix" not in raw_logo.lower()
            and "<" not in raw_logo.split(",", 1)[0]
        ):
            safe_src = raw_logo.replace('"', "").replace("'", "")
            logo_html = (
                f'<img class="wp-lh-logo" src="{safe_src}" alt="" '
                f'style="max-height:52px;max-width:150px;object-fit:contain;display:block" />'
            )
        contact_lines = [
            html_escape(p, quote=True)
            for p in (address, contact, email)
            if p and str(p).strip() and str(p).strip() != "—"
        ]
        contact_html = "<br>".join(contact_lines) if contact_lines else "&nbsp;"
        # DIN-ähnlicher Briefkopf: Logo + Firma links, Kontaktdaten rechts.
        header = f"""<div class="wp-letterhead" style="border-bottom:2px solid {accent};padding:0 0 10px">
  <div class="wp-lh-row" style="display:flex;justify-content:space-between;align-items:flex-start;gap:18px">
    <div class="wp-lh-brand" style="display:flex;gap:12px;align-items:center;min-width:0">
      {logo_html}
      <div class="wp-lh-nameblock">
        <div class="wp-hf-brand" style="font-weight:700;font-size:1.05rem;line-height:1.25;color:#0f172a;letter-spacing:-0.01em">{name}</div>
        <div class="wp-hf-meta" style="font-size:0.72rem;color:#64748b;margin-top:2px">{sector_safe}</div>
      </div>
    </div>
    <div class="wp-lh-contact" style="text-align:right;font-size:0.72rem;color:#475569;line-height:1.45;max-width:46%">
      {contact_html}
    </div>
  </div>
</div>"""
        foot_bits = contact_lines
        footer = f"""<div class="wp-letterfoot" style="border-top:1px solid {accent};padding-top:8px;font-size:0.7rem;color:#64748b;line-height:1.45">
  <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap">
    <div style="font-weight:650;color:#334155">{name}</div>
    <div>{" · ".join(foot_bits) if foot_bits else "&nbsp;"}</div>
  </div>
</div>"""
        return {"headerHtml": header, "footerHtml": footer}

    def set_company_logo(self, db, *, company_id: str, logo_data: str | None) -> dict[str, Any]:
        """Set or clear tenant company logo used by docs letterhead (no platform mark)."""
        from backend.app.platform.company_branding import BRANDING_LOGO_MAX_LEN

        raw = "" if logo_data is None else str(logo_data).strip()
        if not raw:
            db.execute(
                "UPDATE companies SET branding_logo_data = '' WHERE id = ?",
                (company_id,),
            )
            try:
                db.commit()
            except Exception:
                pass
            ctx = self.build_merge_context(db, company_id=company_id)
            return {
                "ok": True,
                "cleared": True,
                "branding": ctx.get("branding"),
                "letterhead": ctx.get("letterhead"),
            }

        lowered = raw.lower()
        if not lowered.startswith("data:image/") or "," not in raw:
            return {
                "ok": False,
                "error": "logo_invalid_format",
                "message": "Logo muss ein Bild als Data-URL sein (PNG/JPG/WebP/SVG).",
            }
        if "javascript:" in lowered or "<" in raw.split(",", 1)[0]:
            return {
                "ok": False,
                "error": "logo_invalid_format",
                "message": "Ungültiges Logo-Format.",
            }
        if "suppix" in lowered:
            return {
                "ok": False,
                "error": "logo_platform_forbidden",
                "message": "Plattform-Logo (SUPPIX) darf nicht als Firmenlogo gesetzt werden.",
            }
        if len(raw) > BRANDING_LOGO_MAX_LEN:
            return {
                "ok": False,
                "error": "logo_too_large",
                "message": "Logo zu groß (max. ca. 130 KB als PNG/JPG).",
            }

        row = db.execute("SELECT id FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "company_not_found", "message": "Firma nicht gefunden."}

        db.execute(
            "UPDATE companies SET branding_logo_data = ? WHERE id = ?",
            (raw, company_id),
        )
        try:
            db.commit()
        except Exception:
            pass
        ctx = self.build_merge_context(db, company_id=company_id)
        return {
            "ok": True,
            "cleared": False,
            "branding": ctx.get("branding"),
            "letterhead": ctx.get("letterhead"),
        }

    def fill_merge_fields(
        self,
        db,
        *,
        company_id: str,
        content_html: str,
        header_html: str = "",
        footer_html: str = "",
        worker_id: str | None = None,
        actor_name: str | None = None,
    ) -> dict[str, Any]:
        ctx = self.build_merge_context(
            db, company_id=company_id, worker_id=worker_id, actor_name=actor_name
        )
        fields = ctx["fields"]
        filled_html = apply_merge_map(content_html or "", fields)
        filled_header = apply_merge_map(header_html or "", fields)
        filled_footer = apply_merge_map(footer_html or "", fields)
        unresolved = sorted(
            set(
                _MERGE_RE.findall(filled_html or "")
                + _MERGE_RE.findall(filled_header or "")
                + _MERGE_RE.findall(filled_footer or "")
            )
        )
        return {
            "contentHtml": filled_html,
            "headerHtml": filled_header,
            "footerHtml": filled_footer,
            "contentText": html_to_text(filled_html),
            "fields": fields,
            "unresolved": unresolved,
        }

    def list_versions(self, db, doc_id: str, *, company_id: str | None, limit: int = 30) -> dict[str, Any]:
        doc = self.repo.get_document(db, doc_id, company_id=company_id)
        if not doc:
            return {"items": [], "count": 0, "error": "not_found"}
        items = self.repo.list_versions(db, doc_id, company_id, limit=limit)
        return {"items": items, "count": len(items)}

    def get_version(
        self,
        db,
        doc_id: str,
        version_id: str,
        *,
        company_id: str | None,
    ) -> dict[str, Any] | None:
        doc = self.repo.get_document(db, doc_id, company_id=company_id)
        if not doc:
            return None
        version = self.repo.get_version(db, version_id, company_id=company_id)
        if not version or str(version.get("document_id")) != str(doc_id):
            return None
        return {
            "id": version.get("id"),
            "document_id": version.get("document_id"),
            "version_no": version.get("version_no"),
            "title": version.get("title") or "",
            "note": version.get("note") or "",
            "created_at": version.get("created_at"),
            "contentHtml": version.get("content_html") or "",
            "contentText": version.get("content_text") or "",
            "contentJson": version.get("content_json") or "",
        }

    def restore_version(
        self,
        db,
        doc_id: str,
        version_id: str,
        *,
        company_id: str | None,
        actor_user_id: str | None,
    ) -> dict[str, Any] | None:
        version = self.repo.get_version(db, version_id, company_id=company_id)
        if not version or str(version.get("document_id")) != str(doc_id):
            return None
        return self.update_doc(
            db,
            doc_id,
            company_id=company_id,
            actor_user_id=actor_user_id,
            data={
                "title": version.get("title"),
                "contentHtml": version.get("content_html") or "",
                "contentText": version.get("content_text") or "",
                "contentJson": version.get("content_json") or "",
                "versionNote": f"restore v{version.get('version_no')}",
            },
            save_version=True,
        )

    _SALARY_RE = re.compile(
        r"(?i)\b(gehalt|salary|lohn|brutto|netto|stundenlohn|hourly[_ ]?rate|vergütung|entgelt)\b"
    )

    def _scrub_salary_text(self, value: str) -> str:
        text = str(value or "")
        if not text:
            return ""
        return self._SALARY_RE.sub("[redacted]", text)

    def build_docs_grounding(
        self,
        db,
        *,
        company_id: str,
        worker_id: str | None = None,
        query: str = "",
    ) -> dict[str, Any]:
        """Ops context for Docs AI — never includes salary/contract pay fields."""
        grounding: dict[str, Any] = {
            "mode": "docs_editor_grounded",
            "companyId": company_id,
            "workerId": worker_id or "",
            "expiringDocuments": [],
            "unreadEditorDocs": 0,
            "attendance": [],
            "knowledge": [],
            "worker": {},
            "guards": {"salaryExcluded": True},
        }
        try:
            exp = self.list_expiring_worker_docs(db, company_id=company_id, horizon_days=14, limit=8)
            if worker_id:
                exp = [x for x in exp if str(x.get("workerId") or "") == str(worker_id)]
            grounding["expiringDocuments"] = [
                {
                    "workerName": self._scrub_salary_text(x.get("workerName") or ""),
                    "docType": x.get("docType"),
                    "filename": self._scrub_salary_text(x.get("filename") or ""),
                    "expiryDate": x.get("expiryDate"),
                }
                for x in exp
            ]
        except Exception:
            pass
        try:
            unread = self.list_unread_editor_docs(db, company_id=company_id, limit=20)
            if worker_id:
                unread = [x for x in unread if str(x.get("workerId") or "") == str(worker_id)]
            grounding["unreadEditorDocs"] = len(unread)
        except Exception:
            pass
        if worker_id:
            try:
                ctx = self.build_merge_context(db, company_id=company_id, worker_id=worker_id)
                fields = ctx.get("fields") or {}
                # Explicit allow-list — never pass salary-ish keys even if added later.
                allow = {
                    "worker.name",
                    "worker.firstName",
                    "worker.lastName",
                    "worker.badge",
                    "worker.role",
                    "worker.site",
                    "worker.email",
                    "worker.phone",
                    "site.name",
                    "shift.slot",
                    "shift.site",
                    "company.name",
                    "date.today",
                }
                grounding["worker"] = {
                    k: self._scrub_salary_text(fields.get(k) or "")
                    for k in allow
                    if fields.get(k) and fields.get(k) != "—"
                }
            except Exception:
                pass
            try:
                from backend.app.platform.workforce.late_streak import (
                    list_late_checkin_evidence,
                    summarize_late_evidence,
                )

                evidence = list_late_checkin_evidence(db, str(worker_id), limit=6)
                grounding["attendance"] = [
                    {
                        "at": self._scrub_salary_text(str(e.get("at") or "")),
                        "day": e.get("day") or "",
                        "time": e.get("time") or "",
                        "gate": self._scrub_salary_text(str(e.get("gate") or "")),
                        "reason": self._scrub_salary_text(str(e.get("note") or "late_checkin")),
                    }
                    for e in (evidence or [])
                    if isinstance(e, dict)
                ]
                grounding["attendanceSummary"] = self._scrub_salary_text(
                    summarize_late_evidence(evidence or [])
                )
            except Exception:
                grounding["attendance"] = []
        try:
            from backend.app.platform.ai.rag import search_knowledge

            q = (query or "ablauf dokument verspätung unterweisung").strip()
            chunks = search_knowledge(db, company_id, q, limit=6)
            grounding["knowledge"] = [
                {
                    "source": c.get("source"),
                    "text": self._scrub_salary_text(str(c.get("text") or "")[:280]),
                }
                for c in chunks
                if not self._SALARY_RE.search(str(c.get("text") or ""))
            ]
        except Exception:
            pass
        return grounding

    def _local_grounded_draft(
        self,
        db,
        *,
        company_id: str,
        worker_id: str | None,
        action: str,
        grounding: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Deterministic drafts when OpenAI is unavailable."""
        worker = grounding.get("worker") or {}
        name = worker.get("worker.name") or "Mitarbeiter/in"
        company = worker.get("company.name") or "Firma"
        today = worker.get("date.today") or _today_de()
        if action == "from_expiry":
            items = grounding.get("expiringDocuments") or []
            if not items:
                return {
                    "ok": True,
                    "action": action,
                    "provider": "local",
                    "contentHtml": (
                        f"<p>Sehr geehrte/r {html_escape(name)},</p>"
                        f"<p>bitte prüfen Sie Ihre hinterlegten Nachweise. Aktuell sind keine "
                        f"ablaufenden Dokumente in den nächsten 14 Tagen gemeldet.</p>"
                        f"<p>{html_escape(company)} · {html_escape(today)}</p>"
                    ),
                    "contentText": f"Keine ablaufenden Dokumente für {name}.",
                    "grounding": grounding,
                    "hint": "Lokal ohne OpenAI — Hinweis aus Expiry-Liste.",
                }
            lines = "".join(
                f"<li>{html_escape(str(it.get('docType') or 'Dokument'))}: "
                f"{html_escape(str(it.get('filename') or ''))} "
                f"(Ablauf {html_escape(str(it.get('expiryDate') or '—'))})</li>"
                for it in items[:5]
            )
            html = (
                f"<p>Sehr geehrte/r {html_escape(name)},</p>"
                f"<p>folgende Nachweise laufen in Kürze ab bzw. sind abgelaufen:</p>"
                f"<ul>{lines}</ul>"
                f"<p>Bitte reichen Sie rechtzeitig gültige Kopien nach.</p>"
                f"<p>{html_escape(company)} · {html_escape(today)}</p>"
            )
            return {
                "ok": True,
                "action": action,
                "provider": "local",
                "contentHtml": html,
                "contentText": html_to_text(html),
                "grounding": grounding,
                "hint": "Lokal ohne OpenAI — Entwurf aus Ablaufdaten.",
            }
        if action in {"from_attendance", "draft_warning"}:
            summary = grounding.get("attendanceSummary") or ""
            events = grounding.get("attendance") or []
            if not events and not summary:
                html = (
                    f"<p>Sehr geehrte/r {html_escape(name)},</p>"
                    f"<p>wir möchten Sie auf die Einhaltung der Arbeitszeiten hinweisen.</p>"
                    f"<p>Bitte erscheinen Sie pünktlich und melden Sie Verzögerungen frühzeitig.</p>"
                    f"<p>{html_escape(company)} · {html_escape(today)}</p>"
                )
            else:
                bullets = "".join(
                    f"<li>{html_escape(str(e.get('day') or e.get('at') or '—'))}"
                    f"{(' um ' + html_escape(str(e.get('time')))) if e.get('time') else ''}"
                    f"{(' · Tor ' + html_escape(str(e.get('gate')))) if e.get('gate') else ''}"
                    f"{(' — ' + html_escape(str(e.get('reason')))) if e.get('reason') and e.get('reason') != 'late_checkin' else ''}</li>"
                    for e in events[:5]
                )
                html = (
                    f"<p>Sehr geehrte/r {html_escape(name)},</p>"
                    f"<p>hiermit sprechen wir eine schriftliche Ermahnung wegen wiederholter "
                    f"Unpünktlichkeit aus.</p>"
                    f"{('<p>' + html_escape(str(summary)) + '</p>') if summary else ''}"
                    f"{('<ul>' + bullets + '</ul>') if bullets else ''}"
                    f"<p>Wir fordern Sie auf, künftig pünktlich zu erscheinen.</p>"
                    f"<p>{html_escape(company)} · {html_escape(today)}</p>"
                )
            return {
                "ok": True,
                "action": action,
                "provider": "local",
                "contentHtml": html,
                "contentText": html_to_text(html),
                "grounding": grounding,
                "hint": "Lokal ohne OpenAI — Entwurf aus Anwesenheitsdaten.",
            }
        return None

    def suggest(
        self,
        db,
        *,
        company_id: str,
        content_html: str,
        action: str = "improve",
        lang: str = "de",
        worker_id: str | None = None,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        text = html_to_text(content_html or "")
        action = (action or "improve").strip().lower()
        lang = (lang or "de")[:2]
        grounded_actions = {"from_expiry", "from_attendance", "draft_warning", "grounded_improve"}
        grounding = self.build_docs_grounding(
            db,
            company_id=company_id,
            worker_id=worker_id,
            query=text[:200] or action,
        )

        prompts = {
            "improve": "Improve the following text for clarity and style. Keep the meaning. Reply with the improved text only.",
            "shorten": "Shorten the following text clearly while keeping the key points. Reply with the shortened text only.",
            "formal": "Rewrite the following text in a more formal business tone. Reply with the text only.",
            "grounded_improve": (
                "Improve the document using ONLY the provided ops grounding context. "
                "Do not invent salary, wages, or contract pay. Reply with the improved document text only."
            ),
            "from_expiry": (
                "Draft a short German HR letter reminding the worker about expiring compliance documents. "
                "Use ONLY grounding.expiringDocuments and worker fields. No salary. Reply with letter text only."
            ),
            "from_attendance": (
                "Draft a short German reminder about late attendance using grounding.attendance. "
                "No salary. Reply with letter text only."
            ),
            "draft_warning": (
                "Draft a formal German Abmahnung/Ermahnung about punctuality using grounding.attendance. "
                "No salary or legal overclaim. Reply with letter text only."
            ),
            "translate_de": "Übersetze den folgenden Text ins Deutsche. Antworte nur mit der Übersetzung.",
            "translate_en": "Translate the following text to English. Reply with the translation only.",
            "translate_ar": "ترجم النص التالي إلى العربية فقط بدون شرح.",
            "translate_tr": "Aşağıdaki metni Türkçeye çevir. Sadece çeviriyi yaz.",
            "translate_fr": "Traduis le texte suivant en français. Réponds uniquement avec la traduction.",
            "translate_es": "Traduce el siguiente texto al español. Responde solo con la traducción.",
            "translate_it": "Traduci il seguente testo in italiano. Rispondi solo con la traduzione.",
            "translate_pl": "Przetłumacz poniższy tekst na polski. Odpowiedz tylko tłumaczeniem.",
        }
        if action == "translate_ui":
            action = f"translate_{lang}" if f"translate_{lang}" in prompts else "translate_en"
        if action.startswith("translate_") and action not in prompts:
            action = "translate_en"
        instruction = prompts.get(action) or prompts["improve"]
        if action.startswith("translate_"):
            lang = action.split("_", 1)[-1] or lang

        # Grounded drafts can run without an existing editor body.
        if action not in grounded_actions and not text.strip():
            return {"ok": False, "error": "empty_content", "action": action}

        openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        use_grounding = action in grounded_actions or bool(worker_id)
        if openai_key and (text.strip() or action in grounded_actions):
            try:
                from backend.app.platform.ai.assistant import natural_language_query

                question = (
                    f"{instruction}\n\n---DOCUMENT---\n{text[:5000]}\n\n---GROUNDING---\n"
                    f"{str(grounding)[:3500]}"
                    if use_grounding
                    else f"{instruction}\n\n---\n{text[:6000]}"
                )
                result = natural_language_query(
                    company_id,
                    question,
                    {
                        "mode": "docs_editor",
                        "docsGrounding": grounding if use_grounding else {},
                        "salaryExcluded": True,
                    },
                    lang=lang,
                )
                answer = self._scrub_salary_text(str(result.get("answer") or "").strip())
                if answer:
                    html = "".join(
                        f"<p>{html_escape(line)}</p>" if line.strip() else "<p><br></p>"
                        for line in answer.splitlines()
                    )
                    out = {
                        "ok": True,
                        "action": action,
                        "provider": "openai",
                        "contentHtml": html,
                        "contentText": answer,
                        "grounding": grounding if use_grounding else None,
                    }
                    try:
                        from backend.server import log_audit

                        log_audit(
                            "docs.ai_suggest",
                            f"Docs AI suggest: {action}",
                            target_type="company",
                            target_id=company_id,
                            company_id=company_id,
                            actor={"id": actor_user_id} if actor_user_id else None,
                            details={
                                "action": action,
                                "workerId": worker_id or "",
                                "provider": "openai",
                                "grounded": use_grounding,
                            },
                        )
                    except Exception:
                        pass
                    return out
            except Exception as exc:
                # Fall through to local grounded/local rewrite.
                if action not in grounded_actions:
                    return {
                        "ok": False,
                        "action": action,
                        "provider": "openai",
                        "error": str(exc),
                        "fallbackHtml": content_html,
                    }

        if action in grounded_actions:
            local = self._local_grounded_draft(
                db,
                company_id=company_id,
                worker_id=worker_id,
                action=action,
                grounding=grounding,
            )
            if local:
                try:
                    from backend.server import log_audit

                    log_audit(
                        "docs.ai_suggest",
                        f"Docs AI suggest (local): {action}",
                        target_type="company",
                        target_id=company_id,
                        company_id=company_id,
                        actor={"id": actor_user_id} if actor_user_id else None,
                        details={"action": action, "workerId": worker_id or "", "provider": "local"},
                    )
                except Exception:
                    pass
                return local

        # Deterministic offline fallback
        if action == "shorten" and text:
            parts = [p.strip() for p in re.split(r"[.\n]+", text) if p.strip()]
            short = ". ".join(parts[: max(1, len(parts) // 2)])
            if short and not short.endswith("."):
                short += "."
            html = f"<p>{html_escape(short)}</p>"
            return {"ok": True, "action": action, "provider": "local", "contentHtml": html, "contentText": short}
        if action == "formal" and text:
            formal = text.replace("Hallo", "Sehr geehrte Damen und Herren").replace(
                "hiermit teilen wir", "hiermit teilen wir Ihnen förmlich"
            )
            html = "".join(
                f"<p>{html_escape(line)}</p>" if line.strip() else "<p><br></p>" for line in formal.splitlines()
            )
            return {"ok": True, "action": action, "provider": "local", "contentHtml": html, "contentText": formal}

        return {
            "ok": True,
            "action": action,
            "provider": "local",
            "contentHtml": content_html,
            "contentText": text,
            "grounding": grounding if use_grounding else None,
            "hint": "OPENAI_API_KEY nicht gesetzt — lokal nur begrenzte Vorschläge.",
        }

    def export_payload(self, doc: dict[str, Any], fmt: str = "html", branding: dict[str, Any] | None = None) -> dict[str, Any]:
        title = str(doc.get("title") or "Dokument").strip() or "Dokument"
        html_body = str(doc.get("content_html") or "")
        safe_name = re.sub(r"[^a-zA-Z0-9_\-äöüÄÖÜß]+", "_", title)[:80] or "dokument"
        fmt = (fmt or "html").lower()
        if fmt in {"pdf"}:
            header_html = ""
            footer_html = ""
            layout = None
            try:
                import json as _json

                raw = doc.get("content_json") or ""
                parsed = _json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("{") else None
                if isinstance(parsed, dict) and parsed.get("schema") == "workpass-doc-v2":
                    header_html = str(parsed.get("headerHtml") or "")
                    footer_html = str(parsed.get("footerHtml") or "")
                    layout = parsed.get("layout") if isinstance(parsed.get("layout"), dict) else None
            except Exception:
                pass
            # Prefer body-only HTML so letterhead is not rendered twice
            # (envelope header + branding band + body header).
            body_only = html_body
            main_m = re.search(
                r'<main[^>]*class=["\']wp-doc-body["\'][^>]*>([\s\S]*?)</main>',
                html_body,
                flags=re.I,
            )
            if main_m:
                body_only = main_m.group(1)
                if not header_html:
                    hm = re.search(
                        r'<header[^>]*class=["\']wp-doc-header["\'][^>]*>([\s\S]*?)</header>',
                        html_body,
                        flags=re.I,
                    )
                    if hm:
                        header_html = hm.group(1)
                if not footer_html:
                    fm = re.search(
                        r'<footer[^>]*class=["\']wp-doc-footer["\'][^>]*>([\s\S]*?)</footer>',
                        html_body,
                        flags=re.I,
                    )
                    if fm:
                        footer_html = fm.group(1)
            from backend.app.platform.reports.editor_pdf import build_editor_pdf_bytes

            pdf_bytes = build_editor_pdf_bytes(
                title=title,
                content_html=body_only,
                content_text=str(doc.get("content_text") or ""),
                header_html=header_html,
                footer_html=footer_html,
                branding=branding,
                layout=layout,
            )
            return {
                "filename": f"{safe_name}.pdf",
                "mimetype": "application/pdf",
                "content": pdf_bytes,
            }
        if fmt in {"doc", "word", "docx"}:
            layout = None
            try:
                import json as _json

                raw = doc.get("content_json") or ""
                parsed = _json.loads(raw) if isinstance(raw, str) and raw.strip().startswith("{") else None
                if isinstance(parsed, dict) and isinstance(parsed.get("layout"), dict):
                    layout = parsed.get("layout")
            except Exception:
                layout = None
            try:
                from .onlyoffice import build_docx_bytes, ensure_docx_file

                docx = build_docx_bytes(title=title, html=html_body, layout=layout)
                # Keep OnlyOffice file in sync for round-trip editing.
                try:
                    ensure_docx_file({**doc, "content_html": html_body, "content_json": doc.get("content_json")}, force=True)
                except Exception:
                    pass
                return {
                    "filename": f"{safe_name}.docx",
                    "mimetype": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "content": docx,
                }
            except Exception:
                safe_title = html_escape(title, quote=True)
                word_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{safe_title}</title></head>
<body>{html_body}</body></html>"""
                return {
                    "filename": f"{safe_name}.doc",
                    "mimetype": "application/msword",
                    "content": word_html,
                }
        safe_title = html_escape(title, quote=True)
        full = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><title>{safe_title}</title>
<style>body{{font-family:Segoe UI,Calibri,sans-serif;line-height:1.5;max-width:800px;margin:2rem auto;}}</style>
</head><body><h1>{safe_title}</h1>{html_body}</body></html>"""
        return {
            "filename": f"{safe_name}.html",
            "mimetype": "text/html; charset=utf-8",
            "content": full,
        }

    def list_workers_brief(self, db, company_id: str, limit: int = 200) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit or 200), 500))
        rows = db.execute(
            """
            SELECT id, first_name, last_name, badge_id, role, site
            FROM workers
            WHERE company_id = ? AND deleted_at IS NULL AND COALESCE(worker_type, 'worker') != 'visitor'
            ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE
            LIMIT ?
            """,
            (company_id, limit),
        ).fetchall()
        out = []
        for r in rows:
            name = f"{r['first_name'] or ''} {r['last_name'] or ''}".strip()
            out.append(
                {
                    "id": r["id"],
                    "name": name,
                    "badgeId": r["badge_id"] or "",
                    "role": (r["role"] if "role" in r.keys() else "") or "",
                    "site": (r["site"] if "site" in r.keys() else "") or "",
                }
            )
        return out

    _ALLOWED_STATUSES = frozenset({"draft", "in_review", "approved", "archived"})

    def set_status(
        self,
        db,
        doc_id: str,
        *,
        company_id: str | None,
        actor_user_id: str | None,
        status: str,
    ) -> dict[str, Any] | None:
        import json as _json

        status = str(status or "").strip().lower()
        if status not in self._ALLOWED_STATUSES:
            return {"error": "invalid_status"}
        updated = self.update_doc(
            db,
            doc_id,
            company_id=company_id,
            actor_user_id=actor_user_id,
            data={"status": status, "versionNote": f"status:{status}"},
            save_version=False,
        )
        if updated and status == "in_review" and company_id:
            title = str(updated.get("title") or "Dokument").strip() or "Dokument"
            try:
                from backend.server import create_system_alert
                from backend.app.platform.inbox.events import notify_inbox_changed

                create_system_alert(
                    db,
                    "docs.review",
                    "info",
                    f"Dokument zur Prüfung: {title}",
                    details=_json.dumps(
                        {
                            "documentId": doc_id,
                            "companyId": company_id,
                            "actorUserId": actor_user_id or "",
                            "title": title,
                        },
                        ensure_ascii=False,
                    ),
                    dedup_minutes=5,
                )
                notify_inbox_changed(
                    company_id,
                    source="docs_review",
                    alert_title=f"Dokument zur Prüfung: {title}",
                    alert_message="Bitte im Docs-Editor prüfen und freigeben.",
                    severity="info",
                )
            except Exception:
                pass
        return updated

    def publish_to_worker(
        self,
        db,
        doc_id: str,
        *,
        company_id: str,
        actor_user_id: str | None,
        worker_id: str | None = None,
        notify: bool = True,
        doc_type: str = "sonstiges",
        expiry_date: str | None = None,
        compliance_required: bool = False,
        locale: str | None = None,
    ) -> dict[str, Any]:
        """Approve document, archive PDF into worker_documents, notify worker."""
        import json as _json
        import secrets

        from backend.app.platform.worker_documents import normalize_doc_type

        doc = self.repo.get_document(db, doc_id, company_id=company_id)
        if not doc:
            return {"error": "not_found", "status": 404}

        wid = str(worker_id or doc.get("worker_id") or "").strip()
        if not wid:
            return {"error": "worker_required", "status": 400}

        worker = db.execute(
            """
            SELECT id, company_id, first_name, last_name
            FROM workers
            WHERE id = ? AND company_id = ? AND deleted_at IS NULL
            """,
            (wid, company_id),
        ).fetchone()
        if not worker:
            return {"error": "worker_not_found", "status": 404}

        # Mark approved then archived in editor_documents
        updated = self.update_doc(
            db,
            doc_id,
            company_id=company_id,
            actor_user_id=actor_user_id,
            data={
                "status": "archived",
                "workerId": wid,
                "mode": doc.get("mode") or "workforce",
                "versionNote": "publish-to-worker",
            },
            save_version=True,
        )
        if not updated or (isinstance(updated, dict) and updated.get("error")):
            return {"error": (updated or {}).get("error") if isinstance(updated, dict) else "update_failed", "status": 500}

        title = str(doc.get("title") or "Dokument").strip() or "Dokument"
        html_body = str(doc.get("content_html") or "")
        pack_id = ""
        pack_locale_used = "de"
        try:
            envelope = _json.loads(str(doc.get("content_json") or "") or "{}")
            lay = envelope.get("layout") if isinstance(envelope, dict) else {}
            if isinstance(lay, dict):
                pack_id = str(lay.get("packId") or "").strip()
        except Exception:
            pack_id = ""
        merge_ctx = self.build_merge_context(
            db, company_id=company_id, worker_id=wid, actor_name=None
        )
        target_locale = (
            str(locale or "").strip().lower()[:2]
            or str(merge_ctx.get("workerLang") or "de")[:2]
            or "de"
        )
        if pack_id:
            variant = self.resolve_pack_variant_html(
                db,
                company_id=company_id,
                pack_id=pack_id,
                locale=target_locale,
                fallback_html=html_body,
            )
            if variant.get("matched") and variant.get("html"):
                html_body = str(variant["html"])
                pack_locale_used = str(variant.get("locale") or target_locale)
                # Fill merge fields for the worker locale variant before PDF export.
                filled = self.fill_merge_fields(
                    db,
                    company_id=company_id,
                    worker_id=wid,
                    content_html=html_body,
                    header_html="",
                    footer_html="",
                )
                if isinstance(filled, dict) and filled.get("contentHtml"):
                    html_body = str(filled["contentHtml"])
                doc = {**doc, "content_html": html_body}
        plain = re.sub(r"<[^>]+>", " ", html_body)
        plain = re.sub(r"\s+", " ", plain).strip()
        safe_title = re.sub(r"[^a-zA-Z0-9_\-äöüÄÖÜß]+", "_", title)[:60] or "dokument"

        # Prefer PDF archive; fall back to HTML
        file_data: bytes
        filename: str
        try:
            brand = merge_ctx.get("branding")
            payload = self.export_payload(doc, fmt="pdf", branding=brand)
            file_data = payload["content"] if isinstance(payload["content"], (bytes, bytearray)) else bytes(payload["content"])
            filename = str(payload.get("filename") or f"{safe_title}.pdf")
        except Exception:
            full_html = f"""<!DOCTYPE html>
<html lang="{html_escape(pack_locale_used or target_locale, quote=True)}"><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font-family:Segoe UI,Calibri,sans-serif;line-height:1.55;max-width:800px;margin:2rem auto;padding:0 1rem;color:#0f172a}}</style>
</head><body><h1>{title}</h1>{html_body}</body></html>"""
            file_data = full_html.encode("utf-8")
            filename = f"{safe_title}.html"

        from backend.server import DOCS_UPLOAD_DIR, _sanitize_attachment_filename, _stored_file_path, now_iso, utc_now

        worker_doc_dir = (DOCS_UPLOAD_DIR / wid).resolve()
        worker_doc_dir.mkdir(parents=True, exist_ok=True)
        ts = utc_now().strftime("%Y%m%d_%H%M%S")
        safe_name = _sanitize_attachment_filename(filename)
        dtype = normalize_doc_type(doc_type or "sonstiges") or "sonstiges"
        if dtype not in {
            "mindestlohnnachweis",
            "personalausweis",
            "sozialversicherungsnachweis",
            "arbeitserlaubnis",
            "aufenthaltserlaubnis",
            "gesundheitszeugnis",
            "geburtsurkunde",
            "meldebescheinigung",
            "lohnabrechnung",
            "gehaltsabrechnung",
            "sonstiges",
            "einsatzplan",
        }:
            dtype = "sonstiges"
        path = (worker_doc_dir / f"{dtype}_{ts}_{safe_name}").resolve()
        path.write_bytes(file_data)
        stored_path = _stored_file_path(path)

        archive_id = f"doc-{secrets.token_hex(8)}"
        created_at = now_iso()
        exp = str(expiry_date or "").strip()[:10] or None
        if exp and not re.match(r"^\d{4}-\d{2}-\d{2}$", exp):
            exp = None
        # Required-doc types already participate in lock engine; flag stores intent for audits/UI.
        try:
            from backend.server import _required_worker_doc_types

            required_types = set(_required_worker_doc_types() or [])
        except Exception:
            required_types = {"mindestlohnnachweis", "personalausweis"}
        compliance_flag = bool(compliance_required) or dtype in required_types
        meta = {
            "source": "editor",
            "editorDocumentId": doc_id,
            "title": title,
            "acknowledgedAt": None,
            "acknowledgedBy": None,
            "complianceRequired": compliance_flag,
            "packId": pack_id or None,
            "locale": pack_locale_used if pack_id else target_locale,
        }
        notes = f"editor:{doc_id}|Aus Dokumenteneditor freigegeben"
        if compliance_flag:
            notes += "|compliance_required"
        if pack_id:
            notes += f"|pack:{pack_id}|lang:{pack_locale_used}"
        from backend.app.domains.workers.repository import WorkersRepository

        WorkersRepository().insert_worker_document(
            db,
            doc_id=archive_id,
            worker_id=wid,
            company_id=company_id,
            doc_type=dtype,
            filename=safe_name,
            file_path=stored_path,
            file_size=len(file_data),
            uploaded_by_user_id=str(actor_user_id or ""),
            created_at=created_at,
            notes=notes,
            expiry_date=exp,
            e2e_meta=_json.dumps(meta, ensure_ascii=False),
            verification_status="accepted",
            verification_score=1.0,
            verification_json="{}",
            verification_checked_at=created_at,
        )

        notify_result: dict[str, Any] = {}
        if notify:
            try:
                from backend.app.platform.notifications.worker_mitteilung import (
                    notify_worker_mitteilung,
                    notify_worker_new_document,
                )

                notify_worker_new_document(db, wid, doc_type=dtype, filename=safe_name)
                notify_result = notify_worker_mitteilung(
                    db,
                    wid,
                    notif_type="editor_document",
                    title=f"Freigegeben: {title}",
                    message=(plain[:280] + ("…" if len(plain) > 280 else ""))
                    or f"Dokument „{title}“ wurde freigegeben und archiviert.",
                    action_url="documents",
                    push_tag="editor-document",
                )
            except Exception as exc:
                notify_result = {"ok": False, "error": str(exc)}

        try:
            from backend.server import create_system_alert, log_audit

            log_audit(
                "docs.published",
                f"Editor-Dokument freigegeben: {title}",
                target_type="worker_document",
                target_id=archive_id,
                company_id=company_id,
                actor={"id": actor_user_id} if actor_user_id else None,
                details={
                    "editorDocumentId": doc_id,
                    "workerDocumentId": archive_id,
                    "workerId": wid,
                    "docType": dtype,
                    "expiryDate": exp,
                    "complianceRequired": compliance_flag,
                    "filename": safe_name,
                },
            )
            create_system_alert(
                db,
                "docs.published",
                "info",
                f"An Mitarbeiter gesendet: {title}",
                details=_json.dumps(
                    {
                        "documentId": doc_id,
                        "workerDocumentId": archive_id,
                        "companyId": company_id,
                        "workerId": wid,
                        "title": title,
                    },
                    ensure_ascii=False,
                ),
                dedup_minutes=2,
            )
        except Exception:
            pass

        try:
            db.commit()
        except Exception:
            pass

        return {
            "ok": True,
            "document": updated,
            "workerDocumentId": archive_id,
            "filename": safe_name,
            "workerId": wid,
            "docType": dtype,
            "expiryDate": exp,
            "editorDocumentId": doc_id,
            "complianceRequired": compliance_flag,
            "acknowledged": False,
            "acknowledgedAt": None,
            "packId": pack_id or None,
            "locale": pack_locale_used if pack_id else target_locale,
            "notify": notify_result,
        }

    def list_expiring_worker_docs(
        self, db, *, company_id: str, horizon_days: int = 14, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Worker documents with expiry within horizon (for Docs rail)."""
        import json as _json
        from datetime import datetime, timedelta, timezone

        today = datetime.now(timezone.utc).date()
        end = today + timedelta(days=max(1, min(int(horizon_days or 14), 90)))
        lim = max(1, min(int(limit or 20), 50))
        try:
            rows = db.execute(
                """
                SELECT wd.id, wd.worker_id, wd.doc_type, wd.filename, wd.expiry_date, wd.notes, wd.e2e_meta,
                       wd.created_at, w.first_name, w.last_name
                FROM worker_documents wd
                LEFT JOIN workers w ON w.id = wd.worker_id
                WHERE wd.company_id = ?
                  AND wd.expiry_date IS NOT NULL AND wd.expiry_date != ''
                  AND wd.expiry_date <= ?
                ORDER BY wd.expiry_date ASC
                LIMIT ?
                """,
                (company_id, end.isoformat(), lim),
            ).fetchall()
        except Exception:
            return []
        out = []
        for r in rows:
            editor_id = ""
            ack_at = None
            compliance = False
            try:
                meta = _json.loads(str(r["e2e_meta"] or "") or "{}")
                if isinstance(meta, dict):
                    editor_id = str(meta.get("editorDocumentId") or "")
                    ack_at = meta.get("acknowledgedAt")
                    compliance = bool(meta.get("complianceRequired"))
            except Exception:
                meta = {}
            notes = str(r["notes"] or "")
            if not editor_id and notes.startswith("editor:"):
                editor_id = notes.split("|", 1)[0].replace("editor:", "", 1).strip()
            if "compliance_required" in notes:
                compliance = True
            name = f"{r['first_name'] or ''} {r['last_name'] or ''}".strip()
            out.append(
                {
                    "id": r["id"],
                    "workerId": r["worker_id"],
                    "workerName": name,
                    "docType": r["doc_type"],
                    "filename": r["filename"],
                    "expiryDate": r["expiry_date"],
                    "editorDocumentId": editor_id,
                    "source": "editor" if editor_id else "upload",
                    "createdAt": r["created_at"],
                    "acknowledgedAt": ack_at,
                    "acknowledged": bool(ack_at),
                    "complianceRequired": compliance,
                }
            )
        return out

    @staticmethod
    def _parse_editor_meta(row) -> dict[str, Any]:
        import json as _json

        meta: dict[str, Any] = {}
        try:
            raw = row["e2e_meta"] if hasattr(row, "keys") and "e2e_meta" in row.keys() else ""
            parsed = _json.loads(str(raw or "") or "{}")
            if isinstance(parsed, dict):
                meta = parsed
        except Exception:
            meta = {}
        notes = ""
        try:
            notes = str(row["notes"] or "") if hasattr(row, "keys") and "notes" in row.keys() else ""
        except Exception:
            notes = ""
        editor_id = str(meta.get("editorDocumentId") or "").strip()
        if not editor_id and notes.startswith("editor:"):
            editor_id = notes.split("|", 1)[0].replace("editor:", "", 1).strip()
        ack_at = meta.get("acknowledgedAt")
        return {
            "editorDocumentId": editor_id,
            "acknowledgedAt": ack_at,
            "acknowledged": bool(ack_at),
            "acknowledgedBy": meta.get("acknowledgedBy"),
            "complianceRequired": bool(meta.get("complianceRequired")) or ("compliance_required" in notes),
            "source": str(meta.get("source") or ("editor" if editor_id else "upload")),
            "title": str(meta.get("title") or ""),
        }

    def list_unread_editor_docs(
        self, db, *, company_id: str, limit: int = 30
    ) -> list[dict[str, Any]]:
        """Editor-sourced worker_documents not yet acknowledged (Docs rail)."""
        lim = max(1, min(int(limit or 30), 80))
        try:
            rows = db.execute(
                """
                SELECT wd.id, wd.worker_id, wd.doc_type, wd.filename, wd.expiry_date, wd.notes, wd.e2e_meta,
                       wd.created_at, w.first_name, w.last_name
                FROM worker_documents wd
                LEFT JOIN workers w ON w.id = wd.worker_id
                WHERE wd.company_id = ?
                  AND (
                    wd.notes LIKE 'editor:%'
                    OR (wd.e2e_meta IS NOT NULL AND wd.e2e_meta LIKE '%"source": "editor"%')
                    OR (wd.e2e_meta IS NOT NULL AND wd.e2e_meta LIKE '%"source":"editor"%')
                  )
                ORDER BY wd.created_at DESC
                LIMIT ?
                """,
                (company_id, lim * 3),
            ).fetchall()
        except Exception:
            return []
        out = []
        for r in rows:
            parsed = self._parse_editor_meta(r)
            if not parsed.get("editorDocumentId"):
                continue
            if parsed.get("acknowledged"):
                continue
            name = f"{r['first_name'] or ''} {r['last_name'] or ''}".strip()
            out.append(
                {
                    "id": r["id"],
                    "workerId": r["worker_id"],
                    "workerName": name,
                    "docType": r["doc_type"],
                    "filename": r["filename"],
                    "expiryDate": r["expiry_date"],
                    "editorDocumentId": parsed["editorDocumentId"],
                    "createdAt": r["created_at"],
                    "acknowledged": False,
                    "complianceRequired": parsed["complianceRequired"],
                    "title": parsed.get("title") or r["filename"],
                }
            )
            if len(out) >= lim:
                break
        return out

    def list_archives_for_editor_doc(
        self, db, *, company_id: str, editor_document_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Published worker_documents linked to an editor document (ack receipt)."""
        eid = str(editor_document_id or "").strip()
        if not eid:
            return []
        lim = max(1, min(int(limit or 10), 30))
        try:
            rows = db.execute(
                """
                SELECT wd.id, wd.worker_id, wd.doc_type, wd.filename, wd.expiry_date, wd.notes, wd.e2e_meta,
                       wd.created_at, w.first_name, w.last_name
                FROM worker_documents wd
                LEFT JOIN workers w ON w.id = wd.worker_id
                WHERE wd.company_id = ?
                  AND (
                    wd.notes LIKE ?
                    OR (wd.e2e_meta IS NOT NULL AND wd.e2e_meta LIKE ?)
                  )
                ORDER BY wd.created_at DESC
                LIMIT ?
                """,
                (company_id, f"editor:{eid}%", f"%{eid}%", lim),
            ).fetchall()
        except Exception:
            return []
        out = []
        for r in rows:
            parsed = self._parse_editor_meta(r)
            if parsed.get("editorDocumentId") != eid:
                continue
            name = f"{r['first_name'] or ''} {r['last_name'] or ''}".strip()
            out.append(
                {
                    "id": r["id"],
                    "workerId": r["worker_id"],
                    "workerName": name,
                    "docType": r["doc_type"],
                    "filename": r["filename"],
                    "expiryDate": r["expiry_date"],
                    "createdAt": r["created_at"],
                    "acknowledged": parsed["acknowledged"],
                    "acknowledgedAt": parsed["acknowledgedAt"],
                    "complianceRequired": parsed["complianceRequired"],
                }
            )
        return out

    def run_stale_review_reminders(
        self, db, *, min_age_days: int = 3, limit: int = 40
    ) -> dict[str, Any]:
        """Re-alert admins for editor docs stuck in_review."""
        import json as _json
        from datetime import datetime, timedelta, timezone

        days = max(1, min(int(min_age_days or 3), 30))
        lim = max(1, min(int(limit or 40), 100))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            rows = db.execute(
                """
                SELECT id, company_id, title, updated_at, status
                FROM editor_documents
                WHERE status = 'in_review'
                  AND (updated_at IS NULL OR updated_at <= ?)
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (cutoff, lim),
            ).fetchall()
        except Exception:
            return {"ok": False, "reminded": 0, "error": "query_failed"}

        from backend.server import create_system_alert
        from backend.app.platform.inbox.events import notify_inbox_changed

        reminded = 0
        for r in rows:
            cid = str(r["company_id"] or "").strip()
            doc_id = str(r["id"] or "").strip()
            title = str(r["title"] or "Dokument").strip() or "Dokument"
            if not cid or not doc_id:
                continue
            try:
                create_system_alert(
                    db,
                    "docs.review.stale",
                    "warning",
                    f"Prüfung überfällig ({days}d+): {title}",
                    details=_json.dumps(
                        {
                            "documentId": doc_id,
                            "companyId": cid,
                            "title": title,
                            "minAgeDays": days,
                            "updatedAt": r["updated_at"],
                        },
                        ensure_ascii=False,
                    ),
                    dedup_minutes=max(60, days * 24 * 60 // 2),
                )
                notify_inbox_changed(
                    cid,
                    source="docs_review_stale",
                    alert_title=f"Prüfung überfällig: {title}",
                    alert_message=f"Dokument wartet seit {days}+ Tagen auf Freigabe.",
                    severity="warning",
                )
                reminded += 1
            except Exception:
                continue
        try:
            db.commit()
        except Exception:
            pass
        return {"ok": True, "reminded": reminded, "minAgeDays": days}

    def create_suggestion(
        self,
        db,
        *,
        document_id: str,
        company_id: str,
        actor_user_id: str | None,
        actor_name: str,
        original_text: str,
        proposed_text: str,
        note: str = "",
        anchor_index: int = 0,
        anchor_length: int = 0,
    ) -> dict[str, Any]:
        doc = self.repo.get_document(db, document_id, company_id=company_id)
        if not doc:
            return {"error": "not_found", "status": 404}
        if str(doc.get("status") or "") == "archived":
            return {"error": "archived", "status": 400}
        original = str(original_text or "").strip()
        proposed = str(proposed_text or "").strip()
        if not original:
            return {"error": "original_required", "status": 400}
        if proposed == original:
            return {"error": "no_change", "status": 400}
        item = self.repo.create_suggestion(
            db,
            document_id=document_id,
            company_id=company_id,
            anchor_index=anchor_index,
            anchor_length=anchor_length or len(original),
            original_text=original,
            proposed_text=proposed,
            note=note,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
        )
        return {"ok": True, "suggestion": item}

    def list_suggestions(
        self, db, *, document_id: str, company_id: str, status: str = ""
    ) -> dict[str, Any]:
        doc = self.repo.get_document(db, document_id, company_id=company_id)
        if not doc:
            return {"error": "not_found", "status": 404}
        items = self.repo.list_suggestions(
            db, document_id=document_id, company_id=company_id, status=status
        )
        pending = sum(1 for it in items if str(it.get("status") or "") == "pending")
        return {"ok": True, "items": items, "pending": pending}

    def resolve_suggestion(
        self,
        db,
        *,
        document_id: str,
        company_id: str,
        suggestion_id: str,
        action: str,
        actor_user_id: str | None,
        actor_role: str = "",
    ) -> dict[str, Any]:
        doc = self.repo.get_document(db, document_id, company_id=company_id)
        if not doc:
            return {"error": "not_found", "status": 404}
        sug = self.repo.get_suggestion(
            db, suggestion_id=suggestion_id, document_id=document_id, company_id=company_id
        )
        if not sug:
            return {"error": "suggestion_not_found", "status": 404}
        if str(sug.get("status") or "") != "pending":
            return {"error": "already_resolved", "status": 400}

        role = (actor_role or "").strip().lower()
        is_admin = role in {"superadmin", "company-admin"}
        is_author = bool(actor_user_id) and str(doc.get("created_by_user_id") or "") == str(actor_user_id)
        if not (is_admin or is_author):
            return {"error": "forbidden", "status": 403}

        act = (action or "").strip().lower()
        if act not in {"accept", "reject"}:
            return {"error": "invalid_action", "status": 400}

        updated_doc = None
        if act == "accept":
            original = str(sug.get("original_text") or "")
            proposed = str(sug.get("proposed_text") or "")
            html = str(doc.get("content_html") or "")
            text = str(doc.get("content_text") or "") or html_to_text(html)
            new_html = html
            new_text = text
            applied = False
            if original and original in html:
                new_html = html.replace(original, proposed, 1)
                applied = True
            if original and original in text:
                new_text = text.replace(original, proposed, 1)
                applied = True
            if not applied and original:
                # Anchor fallback: replace by index in plain text, then mirror into HTML if possible.
                idx = int(sug.get("anchor_index") or 0)
                length = int(sug.get("anchor_length") or len(original))
                if 0 <= idx < len(text) and text[idx : idx + length] == original:
                    new_text = text[:idx] + proposed + text[idx + length :]
                    if original in html:
                        new_html = html.replace(original, proposed, 1)
                    applied = True
            if not applied:
                return {"error": "anchor_mismatch", "status": 409}
            updated_doc = self.update_doc(
                db,
                document_id,
                company_id=company_id,
                actor_user_id=actor_user_id,
                data={
                    "contentHtml": new_html,
                    "contentText": new_text,
                    "versionNote": f"suggestion-accept:{suggestion_id[:8]}",
                },
                save_version=True,
            )
            if not updated_doc:
                return {"error": "update_failed", "status": 500}

        resolved = self.repo.resolve_suggestion(
            db,
            suggestion_id=suggestion_id,
            document_id=document_id,
            company_id=company_id,
            status="accepted" if act == "accept" else "rejected",
            actor_user_id=actor_user_id,
        )
        try:
            from backend.server import log_audit

            log_audit(
                "docs.suggestion_accepted" if act == "accept" else "docs.suggestion_rejected",
                f"Vorschlag {act}: {str(sug.get('note') or sug.get('original_text') or '')[:80]}",
                target_type="editor_document",
                target_id=document_id,
                company_id=company_id,
                actor={"id": actor_user_id, "role": role} if actor_user_id else None,
                details={"suggestionId": suggestion_id, "action": act},
            )
        except Exception:
            pass
        return {
            "ok": True,
            "suggestion": resolved,
            "document": updated_doc or doc,
            "action": act,
        }

    def list_review_comments(self, db, *, document_id: str, company_id: str) -> dict[str, Any]:
        doc = self.repo.get_document(db, document_id, company_id=company_id)
        if not doc:
            return {"error": "not_found", "status": 404}
        items = self.repo.list_review_comments(db, document_id=document_id, company_id=company_id)
        # Nest replies under parents for UI convenience.
        by_id = {str(it["id"]): {**it, "replies": []} for it in items}
        roots = []
        for it in items:
            pid = str(it.get("parent_id") or "").strip()
            if pid and pid in by_id:
                by_id[pid]["replies"].append(by_id[str(it["id"])])
            else:
                roots.append(by_id[str(it["id"])])
        return {"ok": True, "items": roots, "flat": items}

    def create_review_comment(
        self,
        db,
        *,
        document_id: str,
        company_id: str,
        body: str,
        actor_user_id: str | None,
        actor_name: str,
        excerpt: str = "",
        assignee: str = "",
        parent_id: str | None = None,
        anchor_index: int = 0,
        anchor_length: int = 0,
    ) -> dict[str, Any]:
        doc = self.repo.get_document(db, document_id, company_id=company_id)
        if not doc:
            return {"error": "not_found", "status": 404}
        if not str(body or "").strip():
            return {"error": "body_required", "status": 400}
        item = self.repo.create_review_comment(
            db,
            document_id=document_id,
            company_id=company_id,
            body=str(body).strip(),
            excerpt=excerpt,
            assignee=assignee,
            parent_id=parent_id,
            anchor_index=anchor_index,
            anchor_length=anchor_length,
            actor_user_id=actor_user_id,
            actor_name=actor_name,
        )
        return {"ok": True, "comment": item}

    def update_review_comment(
        self,
        db,
        *,
        document_id: str,
        company_id: str,
        comment_id: str,
        body: str | None = None,
        assignee: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        item = self.repo.update_review_comment(
            db,
            comment_id=comment_id,
            document_id=document_id,
            company_id=company_id,
            body=body,
            assignee=assignee,
            status=status,
        )
        if not item:
            return {"error": "not_found", "status": 404}
        return {"ok": True, "comment": item}
