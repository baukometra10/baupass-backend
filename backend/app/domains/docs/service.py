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
        if worker_id:
            worker = None
            try:
                worker = db.execute(
                    """
                    SELECT id, first_name, last_name, badge_id, email, phone
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
            date_iso = datetime.now(ZoneInfo("Europe/Berlin")).strftime("%Y-%m-%d")
        except Exception:
            date_iso = datetime.now().strftime("%Y-%m-%d")

        fields = {
            "company.name": company_name or "—",
            "company.contact": contact or "—",
            "company.email": email or "—",
            "company.address": address_line or "—",
            "company.street": street or "—",
            "company.zipCity": zip_city or "—",
            "company.phone": contact or "—",
            "worker.name": worker_name or "—",
            "worker.firstName": worker_first or "—",
            "worker.lastName": worker_last or "—",
            "worker.badge": worker_badge or "—",
            "worker.email": worker_email or "—",
            "worker.phone": worker_phone or "—",
            "site.name": site_name or "—",
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

    def suggest(
        self,
        db,
        *,
        company_id: str,
        content_html: str,
        action: str = "improve",
        lang: str = "de",
    ) -> dict[str, Any]:
        text = html_to_text(content_html or "")
        action = (action or "improve").strip().lower()
        lang = (lang or "de")[:2]

        prompts = {
            "improve": "Improve the following text for clarity and style. Keep the meaning. Reply with the improved text only.",
            "shorten": "Shorten the following text clearly while keeping the key points. Reply with the shortened text only.",
            "formal": "Rewrite the following text in a more formal business tone. Reply with the text only.",
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
        question = f"{instruction}\n\n---\n{text[:6000]}"

        openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if openai_key and text.strip():
            try:
                from backend.app.platform.ai.assistant import natural_language_query

                result = natural_language_query(company_id, question, {"mode": "docs_editor"}, lang=lang)
                answer = str(result.get("answer") or "").strip()
                if answer:
                    html = "".join(f"<p>{line}</p>" if line.strip() else "<p><br></p>" for line in answer.splitlines())
                    return {
                        "ok": True,
                        "action": action,
                        "provider": "openai",
                        "contentHtml": html,
                        "contentText": answer,
                    }
            except Exception as exc:
                return {
                    "ok": False,
                    "action": action,
                    "provider": "openai",
                    "error": str(exc),
                    "fallbackHtml": content_html,
                }

        # Deterministic offline fallback
        if action == "shorten" and text:
            parts = [p.strip() for p in re.split(r"[.\n]+", text) if p.strip()]
            short = ". ".join(parts[: max(1, len(parts) // 2)])
            if short and not short.endswith("."):
                short += "."
            html = f"<p>{short}</p>"
            return {"ok": True, "action": action, "provider": "local", "contentHtml": html, "contentText": short}
        if action == "formal" and text:
            formal = text.replace("Hallo", "Sehr geehrte Damen und Herren").replace("hiermit teilen wir", "hiermit teilen wir Ihnen förmlich")
            html = "".join(f"<p>{line}</p>" if line.strip() else "<p><br></p>" for line in formal.splitlines())
            return {"ok": True, "action": action, "provider": "local", "contentHtml": html, "contentText": formal}

        return {
            "ok": True,
            "action": action,
            "provider": "local",
            "contentHtml": content_html,
            "contentText": text,
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
        status = str(status or "").strip().lower()
        if status not in self._ALLOWED_STATUSES:
            return {"error": "invalid_status"}
        return self.update_doc(
            db,
            doc_id,
            company_id=company_id,
            actor_user_id=actor_user_id,
            data={"status": status, "versionNote": f"status:{status}"},
            save_version=False,
        )

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
    ) -> dict[str, Any]:
        """Approve document, archive HTML copy into worker_documents, notify worker."""
        import secrets

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
        if not updated:
            return {"error": "update_failed", "status": 500}

        title = str(doc.get("title") or "Dokument").strip() or "Dokument"
        html_body = str(doc.get("content_html") or "")
        safe_title = re.sub(r"[^a-zA-Z0-9_\-äöüÄÖÜß]+", "_", title)[:60] or "dokument"

        # Prefer PDF archive; fall back to HTML
        file_data: bytes
        filename: str
        try:
            brand = None
            try:
                brand = self.build_merge_context(db, company_id=company_id).get("branding")
            except Exception:
                brand = None
            payload = self.export_payload(doc, fmt="pdf", branding=brand)
            file_data = payload["content"] if isinstance(payload["content"], (bytes, bytearray)) else bytes(payload["content"])
            filename = str(payload.get("filename") or f"{safe_title}.pdf")
        except Exception:
            full_html = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font-family:Segoe UI,Calibri,sans-serif;line-height:1.55;max-width:800px;margin:2rem auto;padding:0 1rem;color:#0f172a}}</style>
</head><body><h1>{title}</h1>{html_body}</body></html>"""
            file_data = full_html.encode("utf-8")
            filename = f"{safe_title}.html"

        from backend.server import DOCS_UPLOAD_DIR, _sanitize_attachment_filename, _stored_file_path, now_iso, utc_now

        worker_doc_dir = (DOCS_UPLOAD_DIR / wid).resolve()
        worker_doc_dir.mkdir(parents=True, exist_ok=True)
        ts = utc_now().strftime("%Y%m%d_%H%M%S")
        safe_name = _sanitize_attachment_filename(filename)
        dtype = str(doc_type or "sonstiges").strip().lower() or "sonstiges"
        path = (worker_doc_dir / f"{dtype}_{ts}_{safe_name}").resolve()
        path.write_bytes(file_data)
        stored_path = _stored_file_path(path)

        archive_id = f"doc-{secrets.token_hex(8)}"
        created_at = now_iso()
        notes = f"Aus Dokumenteneditor freigegeben ({doc_id[:8]}…)"
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
            expiry_date=None,
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
            db.commit()
        except Exception:
            pass

        return {
            "ok": True,
            "document": updated,
            "workerDocumentId": archive_id,
            "filename": safe_name,
            "workerId": wid,
            "notify": notify_result,
        }
