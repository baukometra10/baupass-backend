"""Role-specific dashboard payloads for Admin, Foreman, Superadmin."""
from __future__ import annotations

from typing import Any


def build_role_dashboard(db, *, role: str, company_id: str | None, user: dict) -> dict[str, Any]:
    role = (role or "company-admin").strip()
    cid = str(company_id or user.get("company_id") or "").strip()

    base: dict[str, Any] = {
        "role": role,
        "companyId": cid or None,
        "widgets": [],
        "quickLinks": [],
    }

    if role == "superadmin":
        try:
            companies = db.execute(
                "SELECT COUNT(*) AS c FROM companies WHERE deleted_at IS NULL"
            ).fetchone()["c"]
        except Exception:
            companies = 0
        base["widgets"] = [
            {"id": "companies", "label": "Firmen", "value": int(companies or 0), "severity": "info"},
            {"id": "hint", "label": "Modus", "value": "Global", "severity": "info"},
        ]
        base["quickLinks"] = [
            {"label": "Ops Command Center", "url": "/ops-command-center.html"},
            {"label": "Enterprise Hub", "url": "/enterprise-hub.html"},
            {"label": "KI Command Center", "url": "/ai-command-center.html"},
            {"label": "Admin v2", "url": "/admin-v2/index.html"},
        ]
        return base

    if not cid:
        base["error"] = "company_required"
        return base

    from backend.app.platform.physical_operations._common import count_on_site, today_prefix
    from backend.app.platform.predictions.engine import build_tomorrow_forecast
    from backend.app.platform.inbox.service import build_operations_inbox

    today = today_prefix()
    on_site = count_on_site(db, cid, today)
    forecast = build_tomorrow_forecast(db, cid)
    inbox = build_operations_inbox(db, cid, role=role, limit=20)

    if role == "company-admin":
        base["widgets"] = [
            {"id": "on_site", "label": "Heute on-site", "value": on_site, "severity": "info"},
            {
                "id": "tomorrow",
                "label": "Morgen (Prognose)",
                "value": forecast.get("expectedOnSite"),
                "detail": f"−{forecast.get('expectedAbsent')} Risiko",
                "severity": "medium" if forecast.get("expectedAbsent", 0) > 2 else "low",
            },
            {
                "id": "inbox",
                "label": "Posteingang",
                "value": inbox.get("counts", {}).get("open", 0),
                "severity": "high" if inbox.get("counts", {}).get("critical") else "medium",
            },
        ]
        base["forecast"] = forecast
        base["quickLinks"] = [
            {"label": "Posteingang", "url": "/admin-v2/index.html", "tab": "inbox"},
            {"label": "Live Karte", "url": f"/ops-live-map.html?company_id={cid}"},
            {"label": "KI Assistent", "url": f"/ai-command-center.html?company_id={cid}"},
            {"label": "Ops Center", "url": f"/ops-command-center.html?company_id={cid}"},
        ]
        return base

    # foreman / default
    base["widgets"] = [
        {"id": "on_site", "label": "Team on-site", "value": on_site, "severity": "info"},
        {"id": "tomorrow", "label": "Morgen Prognose", "value": forecast.get("expectedOnSite"), "severity": "info"},
    ]
    base["forecast"] = forecast
    base["quickLinks"] = [
        {"label": "Foreman Dashboard", "url": "/foreman.html"},
        {"label": "Live Karte", "url": f"/ops-live-map.html?company_id={cid}"},
        {"label": "KI", "url": f"/ai-command-center.html?company_id={cid}"},
    ]
    return base
