"""Enterprise + Operations combined PDF report."""
from __future__ import annotations

from typing import Any


def _layer_summary(data: dict[str, Any]) -> str:
    if not isinstance(data, dict):
        return "—"
    status = str(data.get("status") or "active")
    modules = data.get("modules")
    caps = data.get("capabilities")
    count = len(modules) if isinstance(modules, dict) else len(caps or [])
    headline = str(data.get("headline") or data.get("layer") or "").strip()
    if headline:
        return f"{status} — {headline[:60]} ({count})"
    return f"{status} ({count} modules)"


def build_enterprise_layers_snapshot(db, company_id: str) -> dict[str, str]:
    """Compact six-layer status for PDF."""
    cid = str(company_id or "")
    out: dict[str, str] = {}
    specs = (
        ("Intelligence", "backend.app.platform.enterprise_layers.intelligence_hub", "build_intelligence_layer"),
        ("Integrations", "backend.app.platform.enterprise_layers.integration_ecosystem", "build_integration_ecosystem"),
        ("Platform", "backend.app.platform.enterprise_layers.platform_ecosystem", "build_platform_ecosystem_layer"),
        ("Infrastructure", "backend.app.platform.enterprise_layers.infrastructure_layer", "build_infrastructure_layer"),
        ("Security", "backend.app.platform.enterprise_layers.security_compliance", "build_security_compliance_layer"),
        ("Experience", "backend.app.platform.enterprise_layers.operational_experience", "build_operational_experience_layer"),
    )
    from pathlib import Path

    from backend.server import DB_PATH

    for label, module_path, fn_name in specs:
        try:
            import importlib

            mod = importlib.import_module(module_path)
            fn = getattr(mod, fn_name)
            if fn_name == "build_infrastructure_layer":
                data = fn(Path(DB_PATH))
            elif fn_name == "build_platform_ecosystem_layer" or fn_name == "build_operational_experience_layer":
                data = fn()
            else:
                data = fn(db, cid)
            out[label] = _layer_summary(data if isinstance(data, dict) else {})
        except Exception:
            out[label] = "n/a"
    return out


def build_enterprise_ops_pdf(
    db,
    *,
    company_id: str,
    company_name: str,
    role: str = "company-admin",
) -> bytes:
    from backend.app.platform.physical_operations.copilot import build_copilot_context
    from backend.app.platform.reports.guidance import build_operational_guidance
    from backend.app.platform.reports.hr_snapshot import build_hr_compliance_snapshot
    from backend.app.platform.reports.pdf_reports import build_operations_report_pdf

    snapshot = build_copilot_context(db, company_id, role=role)
    snapshot["hrCompliance"] = build_hr_compliance_snapshot(db, company_id)
    snapshot["companyName"] = company_name
    snapshot["enterpriseLayers"] = build_enterprise_layers_snapshot(db, company_id)
    guidance = build_operational_guidance(snapshot)
    return build_operations_report_pdf(
        title="WorkPass Enterprise & Operations Report",
        company_name=company_name or "WorkPass",
        snapshot=snapshot,
        guidance=guidance,
    )
