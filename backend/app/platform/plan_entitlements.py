"""
Plan-based entitlements for the 16-layer enterprise catalog.
Single mapping: catalog capability id -> minimum plan (tageskarte | starter | professional | enterprise).
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

PLAN_ORDER = ("tageskarte", "starter", "professional", "enterprise")
PLAN_RANK = {p: i for i, p in enumerate(PLAN_ORDER)}

PLAN_META: dict[str, dict[str, Any]] = {
    "tageskarte": {
        "label": "Tageskarte",
        "labelAr": "بطاقة يومية",
        "priceEur": 29,
        "priceUnit": "day",
        "workersIncluded": 0,
        "workerOverageEur": 0,
        "taglineDe": "Besucher & Kurzzeit-Zutritt",
        "taglineEn": "Visitors and short-term site access",
        "taglineAr": "زوار ودخول مؤقت للموقع",
    },
    "starter": {
        "label": "Starter",
        "labelAr": "مبتدئ",
        "priceEur": 69,
        "priceUnit": "month",
        "workersIncluded": 10,
        "workerOverageEur": 5.99,
        "taglineDe": "Worker-App, NFC, Urlaub — 10 MA inkl.",
        "taglineEn": "Worker app, NFC, leave — 10 workers included",
        "taglineAr": "تطبيق الموظف + NFC + إجازات — 10 موظفين",
    },
    "professional": {
        "label": "Professional",
        "labelAr": "احترافي",
        "priceEur": 249,
        "priceUnit": "month",
        "workersIncluded": 25,
        "workerOverageEur": 7.50,
        "taglineDe": "Echtzeit, Automatisierung, Fakturierung",
        "taglineEn": "Real-time ops, automation, invoicing",
        "taglineAr": "تشغيل لحظي + أتمتة + فوترة + تذكيرات",
    },
    "enterprise": {
        "label": "Enterprise",
        "labelAr": "مؤسسي",
        "priceEur": 599,
        "priceUnit": "month",
        "workersIncluded": 50,
        "workerOverageEur": 9.50,
        "taglineDe": "KI, Wallet, Integrationen, Command Center",
        "taglineEn": "AI, wallet passes, integrations, command center",
        "taglineAr": "AI + محافظ + تكاملات + قيادة مركزية",
    },
}

# Maps every catalog item id -> minimum plan (defaults to enterprise if missing)
CATALOG_MIN_PLAN: dict[str, str] = {
    # Layer 1 — Core Workforce
    "employees": "tageskarte",
    "workforce_mgmt": "starter",
    "attendance": "tageskarte",
    "gps_attendance": "starter",
    "geofence_att": "starter",
    "smart_inout": "starter",
    "auto_checkin_loc": "professional",
    "shifts": "starter",
    "shift_mgmt": "professional",
    "leave": "starter",
    "sick_leave": "starter",
    "timesheets": "professional",
    "worker_profiles": "tageskarte",
    "worker_documents": "starter",
    "scheduling": "professional",
    "deployment_plan": "starter",
    "deployment_plan_bulk": "enterprise",
    "presence_tracking": "professional",
    "workforce_reporting": "professional",
    "worker_notifications": "starter",
    "foreman_dashboard": "professional",
    "contractor_mgmt": "professional",
    "visitor": "tageskarte",
    "rbac": "tageskarte",
    "workforce_roles": "starter",
    "multi_tenant": "enterprise",
    "multi_branch": "enterprise",
    "tenant_isolation": "enterprise",
    "company_work_rules": "professional",
    "site_work_rules": "professional",
    "workforce_compliance": "professional",
    "worker_pwa": "starter",
    "worker_dashboard": "starter",
    "self_service": "starter",
    "offline": "starter",
    "access_logs_wf": "tageskarte",
    "analytics_wf": "professional",
    "workforce_kpi": "professional",
    # Layer 2 — Identity
    "qr_badge": "tageskarte",
    "dynamic_qr": "professional",
    "nfc_id": "starter",
    "digital_employee_id": "starter",
    "apple_wallet": "enterprise",
    "google_wallet": "enterprise",
    "hce": "enterprise",
    "smart_badge": "professional",
    "temp_access_pass": "professional",
    "identity_tokens": "enterprise",
    "identity_verify": "professional",
    "device_trust": "enterprise",
    "identity_sessions": "professional",
    "cross_platform_id": "starter",
    "enterprise_identity": "enterprise",
    "unified_identity": "enterprise",
    "join_flow": "starter",
    # Layer 3 — Access & Security
    "gates": "tageskarte",
    "turnstile": "tageskarte",
    "nfc_access": "starter",
    "wallet_access": "enterprise",
    "hce_access": "enterprise",
    "entry_exit_track": "tageskarte",
    "live_access": "professional",
    "access_logs": "tageskarte",
    "device_heartbeats": "professional",
    "gate_devices": "starter",
    "zones": "professional",
    "temp_access_perm": "professional",
    "site_access_ctrl": "professional",
    "security_alerts": "professional",
    "unauthorized_detect": "professional",
    "security_policies": "enterprise",
    "emergency": "enterprise",
    "incident_detect": "professional",
    "visitor_access": "starter",
    "contractor_access": "professional",
    "physical_access_analytics": "professional",
    "security_compliance": "enterprise",
    "entry_validation": "starter",
    "cmd_center": "enterprise",
    # Layer 4 — Automation
    "workflows": "professional",
    "approval_chains": "professional",
    "auto_notifications": "starter",
    "auto_expiry": "professional",
    "auto_revocation": "professional",
    "auto_onboarding": "professional",
    "auto_compliance": "enterprise",
    "auto_attendance": "professional",
    "event_bus": "professional",
    "rules_engine": "professional",
    "queue_processing": "professional",
    "scheduled_auto": "professional",
    "realtime_triggers": "professional",
    "autonomous_ops": "enterprise",
    "auto_escalation": "enterprise",
    "dunning": "professional",
    "auto_invoice": "professional",
    "auto_reminders": "professional",
    "self_healing_jobs": "enterprise",
    "smart_tasks": "professional",
    "workflow_routing": "enterprise",
    "onboarding_auto": "professional",
    # Layer 5 — Real-time
    "websocket": "professional",
    "live_tracking": "professional",
    "live_presence": "professional",
    "live_dashboards": "professional",
    "realtime_notifications": "professional",
    "live_gate_mon": "enterprise",
    "live_device_mon": "professional",
    "live_metrics": "professional",
    "alerts_engine": "professional",
    "streaming": "enterprise",
    "live_events": "professional",
    "instant_sync": "professional",
    "rt_analytics": "enterprise",
    "rt_incidents": "enterprise",
    "ops_command": "enterprise",
    "rt_access_logs": "professional",
    "workforce_heatmaps": "enterprise",
    "live_device_status": "professional",
    "activity_streams": "professional",
    "sse": "professional",
    # Layer 6 — UX
    "admin_v2": "starter",
    "design_tokens": "starter",
    "offline_sync": "starter",
    "flutter": "starter",
    "ultra_fast_ux": "starter",
    "enterprise_ui": "professional",
    "mobile_first": "starter",
    "offline_mode": "starter",
    "conflict_resolution": "professional",
    "cross_platform_apps": "starter",
    "dashboard_ux": "professional",
    # Layer 7 — Security
    "zero_trust": "enterprise",
    "rbac_adv": "professional",
    "access_governance": "enterprise",
    "audit": "starter",
    "security_monitoring": "enterprise",
    "threat_detection": "enterprise",
    "security_analytics": "enterprise",
    "device_trust_sec": "enterprise",
    "session_security": "professional",
    "mfa": "professional",
    "encryption": "enterprise",
    "ip_whitelist": "enterprise",
    "compliance_mon": "enterprise",
    "gdpr": "enterprise",
    "iso_soc": "enterprise",
    "tenant_domain": "enterprise",
    "siem": "enterprise",
    # Layer 8 — Intelligence
    "ai_assistant": "enterprise",
    "ai_copilot": "enterprise",
    "predictive_att": "enterprise",
    "predictive_ops": "enterprise",
    "scheduling_ai": "enterprise",
    "workforce_optimization": "enterprise",
    "fraud": "enterprise",
    "productivity_intel": "enterprise",
    "behavioral_analytics": "enterprise",
    "kpi_analysis": "professional",
    "heatmap": "enterprise",
    "risk_detection": "enterprise",
    "ai_recommendations": "enterprise",
    "ai_decision": "enterprise",
    "operational_insights": "professional",
    "nlq": "enterprise",
    "ai_forecasting": "enterprise",
    "graph_intelligence": "enterprise",
    "ai_compliance": "enterprise",
    "predictive_incident": "enterprise",
    "workforce_scoring": "enterprise",
    # Layer 9 — Physical ops
    "ops_os": "professional",
    "site_intelligence": "professional",
    "facility_monitoring": "enterprise",
    "iot": "enterprise",
    "security_ops": "enterprise",
    "movement_intel": "enterprise",
    "zone_monitoring": "professional",
    "emergency_intel": "enterprise",
    "evacuation": "enterprise",
    "resource_allocation": "enterprise",
    "camera_ai": "enterprise",
    "digital_twin": "enterprise",
    "physical_analytics": "professional",
    "site_heatmaps": "enterprise",
    "flow_analytics": "enterprise",
    "safety_intel": "enterprise",
    "operational_awareness": "enterprise",
    "site_intel": "professional",
    "emergency_ops": "enterprise",
    # Layer 10 — Autonomous
    "auto_rules": "enterprise",
    "self_heal": "enterprise",
    "auto_incident": "enterprise",
    "autonomous_wf_opt": "enterprise",
    "autonomous_security": "enterprise",
    "ai_access_decisions": "enterprise",
    "autonomous_compliance": "enterprise",
    "autonomous_workflow": "enterprise",
    "ai_resource_alloc": "enterprise",
    # Layer 11 — Integrations
    "payroll": "professional",
    "erp": "enterprise",
    "sap": "enterprise",
    "oracle": "enterprise",
    "m365": "enterprise",
    "google": "enterprise",
    "smtp_imap": "professional",
    "security_integration": "enterprise",
    "camera_integration": "enterprise",
    "iot_integrations": "enterprise",
    "device_apis": "professional",
    "hardware_apis": "professional",
    "accounting": "professional",
    "hr_systems": "enterprise",
    "webhooks": "enterprise",
    "api_gateway": "enterprise",
    "enterprise_apis": "enterprise",
    "public_apis": "enterprise",
    "sdk": "enterprise",
    "plugins": "enterprise",
    "third_party_ext": "enterprise",
    "marketplace": "enterprise",
    "integration_hub": "enterprise",
    # Layer 12 — Platform ecosystem
    "saas_infra": "enterprise",
    "dev_platform": "enterprise",
    "sdk_ecosystem": "enterprise",
    "plugin_marketplace": "enterprise",
    "white_label": "enterprise",
    "partner_system": "enterprise",
    "dev_ecosystem": "enterprise",
    "app_store": "enterprise",
    "multi_country": "enterprise",
    "global_governance": "enterprise",
    "distribution_network": "enterprise",
    "global_scaling": "enterprise",
    "developer_apis": "enterprise",
    "monetization": "enterprise",
    "public_api": "enterprise",
    # Layer 13 — Hyper-scale (platform ops — visible to all admins, config-gated)
    "k8s": "enterprise",
    "postgres": "enterprise",
    "redis": "professional",
    "dr": "enterprise",
    "obs": "professional",
    "multi_region": "enterprise",
    "cloud_native": "enterprise",
    "cdn": "enterprise",
    "load_balancing": "enterprise",
    # Layer 14 — SaaS business
    "billing": "professional",
    "dunning_b": "professional",
    "plans": "tageskarte",
    "subscription_mgmt": "professional",
    "usage_analytics": "enterprise",
    "revenue_analytics": "enterprise",
    # Layer 15 — Global command
    "command": "enterprise",
    "global_ready": "enterprise",
    "catalog": "starter",
    "multi_country_ops": "enterprise",
    "cross_region": "enterprise",
    "global_incidents": "enterprise",
    "control_towers": "enterprise",
    "global_analytics": "enterprise",
    "worldwide_tenant": "enterprise",
    # Layer 16 — Vision (always shown, enabled at enterprise)
    "wf_os": "enterprise",
    "ai_cloud": "enterprise",
    "physical_os_vision": "enterprise",
    "autonomous_platform": "enterprise",
    "global_network": "enterprise",
}


def plan_includes(user_plan: str, required_plan: str) -> bool:
    up = str(user_plan or "starter").strip().lower()
    rp = str(required_plan or "enterprise").strip().lower()
    if up not in PLAN_RANK:
        up = "starter"
    if rp not in PLAN_RANK:
        rp = "enterprise"
    return PLAN_RANK[up] >= PLAN_RANK[rp]


def min_plan_for_capability(capability_id: str) -> str:
    return CATALOG_MIN_PLAN.get(capability_id, "enterprise")


def apply_plan_to_catalog(catalog: dict[str, Any], plan: str) -> dict[str, Any]:
    """Annotate each catalog item with minPlan, enabled, upgradeRequired."""
    out = deepcopy(catalog)
    enabled_count = 0
    locked_count = 0
    by_plan: dict[str, int] = {p: 0 for p in PLAN_ORDER}

    for layer in out.get("layers", []):
        layer_enabled = 0
        for it in layer.get("items", []):
            cid = it.get("id", "")
            mp = min_plan_for_capability(cid)
            it["minPlan"] = mp
            it["enabled"] = plan_includes(plan, mp)
            if it["enabled"]:
                enabled_count += 1
                layer_enabled += 1
            else:
                locked_count += 1
                it["upgradeRequired"] = True
            by_plan[mp] = by_plan.get(mp, 0) + 1
        layer["enabledCount"] = layer_enabled
        layer["totalCount"] = len(layer.get("items", []))

    out["entitlements"] = {
        "plan": plan,
        "enabledCount": enabled_count,
        "lockedCount": locked_count,
        "totalCapabilities": enabled_count + locked_count,
        "coveragePercent": round(100 * enabled_count / max(1, enabled_count + locked_count), 1),
        "byRequiredPlan": by_plan,
    }
    out["plans"] = PLAN_META
    out["planOrder"] = list(PLAN_ORDER)
    return out


def build_plan_comparison_matrix(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-plan: how many capabilities unlock at that tier (cumulative)."""
    rows = []
    for plan in PLAN_ORDER:
        applied = apply_plan_to_catalog(catalog, plan)
        rows.append(
            {
                "plan": plan,
                "meta": PLAN_META[plan],
                "enabledCount": applied["entitlements"]["enabledCount"],
                "total": applied["entitlements"]["totalCapabilities"],
                "coveragePercent": applied["entitlements"]["coveragePercent"],
            }
        )
    return rows


def catalog_keys_for_server_plan_features() -> dict[str, str]:
    """Sync keys for server.PLAN_FEATURES (legacy feature gate names)."""
    return {
        **CATALOG_MIN_PLAN,
        "access_logging": "tageskarte",
        "worker_management": "tageskarte",
        "qr_badges": "tageskarte",
        "worker_app": "starter",
        "nfc_badges": "starter",
        "leave_management": "starter",
        "document_upload": "starter",
        "invoicing": "professional",
        "email_notifications": "professional",
        "worker_hours_report": "professional",
        "late_checkin_alert": "professional",
        "subcompanies": "professional",
        "white_label": "enterprise",
        "api_access": "enterprise",
        "multi_site": "enterprise",
        "premium_support": "enterprise",
        "custom_pricing": "enterprise",
        "ai_assistant": "enterprise",
        "ai_copilot": "enterprise",
        "ops_command_center": "enterprise",
        "physical_operations_os": "professional",
        "enterprise_integrations": "enterprise",
        "realtime_operations": "professional",
        "automation_suite": "professional",
        "enterprise_hub": "starter",
    }
