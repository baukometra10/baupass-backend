"""Sector configuration API."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

sector_bp = Blueprint("sector", __name__)


def register_sector_blueprint(flask_app) -> None:
    from backend.server import get_db, require_auth, row_to_dict

    @sector_bp.get("/platform/sectors")
    def list_sectors():
        from .catalog import all_sectors_public

        lang = (request.args.get("lang") or "de").strip().lower()[:2]
        items = []
        for row in all_sectors_public():
            items.append(
                {
                    "id": row["id"],
                    "label": row["labels"].get(lang) or row["labels"]["de"],
                    "productLine": row["productLine"].get(lang) or row["productLine"]["de"],
                }
            )
        return jsonify({"sectors": items})

    @sector_bp.get("/platform/sector-config")
    @require_auth
    def sector_config_route():
        from .catalog import normalize_operating_sector, sector_config

        db = get_db()
        user = g.current_user
        lang = (request.args.get("lang") or request.headers.get("X-BauPass-Ui-Lang") or "de").strip().lower()[:2]
        company_id = str(user.get("company_id") or request.args.get("company_id") or "").strip()
        if user.get("role") == "superadmin" and request.args.get("company_id"):
            company_id = str(request.args.get("company_id")).strip()

        sector = "construction"
        if company_id:
            row = db.execute(
                "SELECT operating_sector, branding_preset FROM companies WHERE id = ?",
                (company_id,),
            ).fetchone()
            if row:
                keys = row.keys() if hasattr(row, "keys") else []
                if "operating_sector" in keys and row["operating_sector"]:
                    sector = normalize_operating_sector(row["operating_sector"])
                else:
                    # fallback until all tenants migrated
                    preset = str(row["branding_preset"] or "").lower()
                    if preset == "industry":
                        sector = "manufacturing"
        return jsonify(sector_config(sector, lang=lang))

    flask_app.register_blueprint(sector_bp, url_prefix="/api")
