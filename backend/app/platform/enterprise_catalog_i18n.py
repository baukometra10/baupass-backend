"""German (and localized note) strings for enterprise catalog — merged at runtime."""
from __future__ import annotations

LAYER_TITLE_DE: dict[str, str] = {
    "core_workforce": "Kern-Workforce-Infrastruktur",
    "digital_identity": "Digitale Workforce-Identität",
    "access_security": "Zutritts- & physische Sicherheit",
    "automation": "Intelligente Automatisierung",
    "realtime": "Echtzeit-Betrieb",
    "operational_ux": "Betriebserlebnis",
    "security_compliance": "Enterprise-Sicherheit & Compliance",
    "intelligence": "Enterprise-Intelligence + KI",
    "physical_ops": "Intelligenter physischer Betrieb",
    "autonomous": "Autonome Enterprise-Schicht",
    "integrations": "Enterprise-Integrations-Ökosystem",
    "platform_ecosystem": "Plattform-Ökosystem",
    "hyper_scale": "Hyper-Scale-Infrastruktur",
    "saas_business": "Enterprise SaaS & Business",
    "global_command": "Globales Betriebs-Command",
    "vision": "Strategische Zukunftsvision",
}

ITEM_LABEL_DE: dict[str, str] = {
    "employees": "Mitarbeiterverwaltung",
    "workforce_mgmt": "Workforce-Management",
    "attendance": "Anwesenheitsmanagement",
    "gps_attendance": "GPS-Anwesenheit",
    "geofence_att": "Geofence-Anwesenheit",
    "smart_inout": "Smart Check-In / Check-Out",
    "auto_checkin_loc": "Auto Check-In per Standort",
    "shifts": "Schichtverwaltung",
    "shift_mgmt": "Erweiterte Schichtplanung",
    "leave": "Urlaubsverwaltung",
    "sick_leave": "Krankmeldungen",
    "worker_profiles": "Mitarbeiterprofile",
    "worker_documents": "Mitarbeiterdokumente",
    "timesheets": "Arbeitszeitnachweise",
    "scheduling": "Workforce-Planung",
    "presence_tracking": "Anwesenheitsverfolgung",
    "workforce_reporting": "Workforce-Reporting",
    "worker_notifications": "Mitarbeiter-Benachrichtigungen",
    "worker_chat": "Mitarbeiter-Chat",
    "employment_contracts": "AI-Arbeitsverträge",
    "foreman_dashboard": "Vorarbeiter-Dashboard",
    "contractor_mgmt": "Subunternehmer-Verwaltung",
    "visitor": "Besucherverwaltung",
    "rbac": "RBAC-System",
    "workforce_roles": "Rollen & Berechtigungen",
    "multi_tenant": "Multi-Tenant-Architektur",
    "multi_branch": "Multi-Standort",
    "tenant_isolation": "Mandantenisolierung",
    "company_work_rules": "Firmen-Arbeitsregeln",
    "site_work_rules": "Baustellen-Regeln",
    "workforce_compliance": "Workforce-Compliance",
    "worker_hybrid": "Worker-App (Hybrid Flutter)",
    "worker_dashboard": "Mitarbeiter-Dashboard",
    "self_service": "Self-Service-Portal",
    "offline": "Offline-Betrieb",
    "access_logs_wf": "Workforce-Zutrittslogs",
    "analytics_wf": "Workforce-Analytics",
    "workforce_kpi": "Workforce-KPIs",
    "digital_employee_id": "Digitale Mitarbeiter-ID",
    "qr_badge": "QR-Ausweis-System",
    "dynamic_qr": "Dynamische QR-Codes",
    "nfc_id": "NFC-Identität",
    "smart_badge": "Smart-Badge-Infrastruktur",
    "temp_access_pass": "Temporäre Zutrittspässe",
    "identity_tokens": "Identitäts-Tokens",
    "identity_verify": "Sichere Identitätsprüfung",
    "device_trust": "Geräte-Vertrauen",
    "identity_sessions": "Identitäts-Sitzungen",
    "cross_platform_id": "Plattformübergreifende Identität",
    "enterprise_identity": "Enterprise-Identitäts-Engine",
    "unified_identity": "Einheitliche Workforce-Identität",
    "apple_wallet": "Apple Wallet Pass",
    "google_wallet": "Google Wallet Pass",
    "hce": "Android HCE Identität",
    "join_flow": "Identitäts-Onboarding",
    "gates": "Gate-Management",
    "turnstile": "Drehkreuz-Integration",
    "nfc_access": "NFC-Zutrittskontrolle",
    "live_access": "Live-Zutrittsüberwachung",
    "access_logs": "Zutrittslogs",
    "zones": "Smart Access Zones",
    "emergency": "Notfall-Sperrung",
    "cmd_center": "Live Gate Monitoring",
    "deployment_plan": "Monats-Einsatzplan",
    "workflows": "Workflow-Automatisierung",
    "auto_expiry": "Auto-Ablauf-Alerts",
    "dunning": "Auto-Rechnung / Mahnwesen",
    "onboarding_auto": "Auto-Onboarding",
    "event_bus": "Event-gesteuerte Automatisierung",
    "websocket": "WebSocket-Infrastruktur",
    "live_presence": "Live-Anwesenheit",
    "live_metrics": "Echtzeit-Metriken",
    "sse": "Live-Aktivitätsstreams",
    "admin_v2": "Modernes Enterprise-UI",
    "design_tokens": "Design System",
    "offline_sync": "Offline-Sync",
    "flutter": "Cross-Platform-App",
    "zero_trust": "Zero Trust",
    "rbac_adv": "Erweitertes RBAC",
    "audit": "Unveränderliche Audit-Trails",
    "mfa": "MFA / 2FA",
    "siem": "SIEM-Export",
    "encryption": "Verschlüsselungsschicht",
    "ai_assistant": "KI-Assistent",
    "ai_copilot": "KI-Copilot",
    "predictive_att": "Prädiktive Anwesenheit",
    "fraud": "Betrugserkennung",
    "scheduling_ai": "KI-Schichtplanung",
    "heatmap": "Workforce-Heatmaps",
    "nlq": "Natürlichsprachige Abfragen",
    "ops_os": "Physisches Operations-OS",
    "digital_twin": "Digital Twin",
    "site_intel": "Baustellen-Intelligence",
    "camera_ai": "Kamera-Intelligence",
    "iot": "IoT-Infrastruktur",
    "emergency_ops": "Notfall-Intelligence",
    "auto_rules": "Autonome Regeln",
    "self_heal": "Self-Healing-Jobs",
    "auto_incident": "Autonome Incident Response",
    "payroll": "Payroll-Integrationen",
    "sap": "SAP-Integration",
    "oracle": "Oracle-Integration",
    "m365": "Microsoft 365",
    "google": "Google Workspace",
    "webhooks": "Webhooks",
    "api_gateway": "API Gateway / v1",
    "sdk": "SDK-Infrastruktur",
    "marketplace": "Integrations-Marktplatz",
    "white_label": "White-Label",
    "public_api": "Öffentliche Developer-APIs",
    "k8s": "Kubernetes Ready",
    "postgres": "PostgreSQL Clustering",
    "redis": "Queue / Redis",
    "dr": "Disaster Recovery",
    "obs": "Observability Stack",
    "multi_region": "Multi-Region",
    "billing": "Enterprise-Abrechnung",
    "dunning_b": "Mahnwesen-Automatisierung",
    "plans": "Multi-Plan SaaS",
    "command": "Workforce Command Center",
    "global_ready": "Globale Readiness",
    "catalog": "Enterprise-Katalog",
    "wf_os": "Workforce Operating System",
    "ai_cloud": "AI Workforce Cloud",
}

NOTE_I18N: dict[str, dict[str, str]] = {
    "dunning": {
        "de": "Hintergrund — Redis verbessert Performance",
        "en": "Background job — Redis improves throughput",
        "ar": "خلفية — Redis يحسّنها",
    },
    "self_heal": {
        "de": "Mit Redis + Worker-Prozess",
        "en": "Requires Redis + worker process",
        "ar": "مع Redis + worker",
    },
    "dunning_b": {
        "de": "Hintergrundjob",
        "en": "Background job",
        "ar": "خلفية",
    },
    "wf_os": {
        "de": "Vision — Aggregation über Ebenen 1–15",
        "en": "Vision — aggregation across layers 1–15",
        "ar": "رؤية — التجميع عبر الطبقات 1–15",
    },
    "ai_cloud": {
        "de": "OPENAI_API_KEY + Intelligence-Ebene",
        "en": "OPENAI_API_KEY + intelligence layer",
        "ar": "OPENAI_API_KEY + طبقة intelligence",
    },
}


HUB_LANGS = ("de", "en", "ar", "tr", "fr", "es", "it", "pl")


def _fill_hub_lang_map(base: dict[str, str]) -> dict[str, str]:
    en = base.get("en") or base.get("de") or ""
    out = dict(base)
    for lang in HUB_LANGS:
        out.setdefault(lang, en)
    return out


def enrich_catalog_i18n(catalog: dict) -> dict:
    """Attach localized titles/labels for all 8 hub languages."""
    from .enterprise_catalog_labels_extra import (
        ITEM_LABEL_EXTRA,
        LAYER_TITLE_EXTRA,
        NOTE_EXTRA,
        SURFACE_LABEL_EXTRA,
    )

    surface_labels = catalog.get("surfaceLabels") or {}
    for surface, row in surface_labels.items():
        if not isinstance(row, dict):
            continue
        extra = SURFACE_LABEL_EXTRA.get(surface) or {}
        row.update({lang: extra[lang] for lang in ("tr", "fr", "es", "it", "pl") if extra.get(lang)})

    for layer in catalog.get("layers") or []:
        lid = str(layer.get("id") or "")
        title_en = str(layer.get("title") or "")
        title_ar = str(layer.get("titleAr") or title_en)
        title_de = LAYER_TITLE_DE.get(lid, title_en)
        title_i18n = _fill_hub_lang_map(
            {
                "de": title_de,
                "en": title_en,
                "ar": title_ar,
                **(LAYER_TITLE_EXTRA.get(lid) or {}),
            }
        )
        layer["titleDe"] = title_i18n["de"]
        layer["titleEn"] = title_i18n["en"]
        layer["titleI18n"] = title_i18n

        for it in layer.get("items") or []:
            iid = str(it.get("id") or "")
            label_en = str(it.get("label") or "")
            label_ar = str(it.get("labelAr") or label_en)
            label_de = ITEM_LABEL_DE.get(iid, label_en)
            label_i18n = _fill_hub_lang_map(
                {
                    "de": label_de,
                    "en": label_en,
                    "ar": label_ar,
                    **(ITEM_LABEL_EXTRA.get(iid) or {}),
                }
            )
            it["labelDe"] = label_i18n["de"]
            it["labelEn"] = label_i18n["en"]
            it["labelI18n"] = label_i18n

            note = str(it.get("note") or "").strip()
            if iid in NOTE_I18N:
                note_map = dict(NOTE_I18N[iid])
                note_map.update(NOTE_EXTRA.get(iid) or {})
                it["noteI18n"] = _fill_hub_lang_map(note_map)
            elif note:
                it["noteI18n"] = _fill_hub_lang_map({"de": note, "en": note, "ar": note})
    return catalog
