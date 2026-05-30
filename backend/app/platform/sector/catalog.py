"""Operating sectors, terminology packs, and operation templates."""
from __future__ import annotations

from typing import Any

# branding_preset = UI theme; operating_sector = business vertical vocabulary
VALID_SECTORS = frozenset(
    {
        "construction",
        "manufacturing",
        "logistics",
        "aviation",
        "security",
        "public_sector",
        "government",
    }
)

DEFAULT_SECTOR = "construction"


def normalize_operating_sector(value: str | None) -> str:
    key = str(value or "").strip().lower().replace("-", "_")
    if key in VALID_SECTORS:
        return key
    # legacy aliases
    if key in {"industry", "industrial", "fabrik", "werk"}:
        return "manufacturing"
    if key in {"municipal", "municipality", "stadt"}:
        return "public_sector"
    if key in {"gov", "ministry", "behoerde", "behörde"}:
        return "government"
    if key in {"airport", "aviation", "flughafen", "terminal"}:
        return "aviation"
    return DEFAULT_SECTOR


def _t(de: str, en: str, ar: str) -> dict[str, str]:
    return {"de": de, "en": en, "ar": ar}


SECTOR_META: dict[str, dict[str, Any]] = {
    "construction": {
        "id": "construction",
        "labels": _t("Bau & Baustelle", "Construction", "البناء والمواقع"),
        "productLine": _t(
            "Digitale Identität und Zutrittskontrolle für Baustellen",
            "Digital identity and site access for construction",
            "الهوية الرقمية والدخول لمواقع البناء",
        ),
    },
    "manufacturing": {
        "id": "manufacturing",
        "labels": _t("Industrie & Produktion", "Manufacturing", "الصناعة والإنتاج"),
        "productLine": _t(
            "Identität, Zutritt und Compliance am Werk",
            "Identity, access and compliance at the plant",
            "الهوية والدخول والامتثال في المنشأة الصناعية",
        ),
    },
    "aviation": {
        "id": "aviation",
        "labels": _t("Luftfahrt & Flughafen", "Aviation & airport", "الطيران والمطارات"),
        "productLine": _t(
            "Zutritt, Badges und Compliance am Terminal",
            "Terminal access, badges and compliance",
            "الدخول والشارات والامتثال في المطار",
        ),
    },
    "logistics": {
        "id": "logistics",
        "labels": _t("Logistik & Lager", "Logistics", "اللوجستيات والمستودعات"),
        "productLine": _t(
            "Zutritt, Personal und Nachweise in Logistikzentren",
            "Access, workforce and proof in logistics hubs",
            "الدخول والقوى العاملة والمستندات في مراكز اللوجستيات",
        ),
    },
    "security": {
        "id": "security",
        "labels": _t("Sicherheit & Objektschutz", "Security services", "الأمن وحماية المنشآت"),
        "productLine": _t(
            "Identität, Schichten und Kontrollpunkte",
            "Identity, shifts and control points",
            "الهوية والورديات ونقاط التفتيش",
        ),
    },
    "public_sector": {
        "id": "public_sector",
        "labels": _t("Kommunen & öffentliche Betriebe", "Public sector", "القطاع البلدي والعام"),
        "productLine": _t(
            "Bürger- und Mitarbeiterzugang mit Audit-Trail",
            "Citizen and staff access with audit trail",
            "دخول المواطنين والموظفين مع سجل تدقيق",
        ),
    },
    "government": {
        "id": "government",
        "labels": _t("Behörden & Ministerien", "Government", "الجهات الحكومية والوزارات"),
        "productLine": _t(
            "Enterprise Identity, Zutritt und Compliance",
            "Enterprise identity, access and compliance",
            "الهوية المؤسسية والدخول والامتثال",
        ),
    },
}


# UI translation keys overridden per sector (Control Pass + worker app can consume the same keys)
SECTOR_TERM_KEYS: dict[str, dict[str, dict[str, str]]] = {
    "construction": {
        "topbarHeading": _t(
            "Digitale Baustellenkontrolle",
            "Digital site access control",
            "التحكم الرقمي في مواقع البناء",
        ),
        "navWorkers": _t("Mitarbeiter", "Workers", "العمال"),
        "workersListH3": _t("Registrierte Mitarbeiter", "Registered workers", "العمال المسجلون"),
        "labelSite": _t("Standort / Baustelle", "Site", "موقع البناء"),
        "labelFirm": _t("Firma", "Company", "الشركة"),
        "accessFormH3": _t("An- und Abmeldung", "Check-in / out", "تسجيل دخول وخروج"),
        "badgeH3": _t("Badge-Vorschau", "Badge preview", "معاينة البطاقة"),
    },
    "manufacturing": {
        "topbarHeading": _t(
            "Werk-Zutritt & Identität",
            "Plant access & identity",
            "الدخول والهوية في المنشأة",
        ),
        "navWorkers": _t("Mitarbeiter", "Employees", "الموظفون"),
        "workersListH3": _t("Registrierte Mitarbeiter", "Registered employees", "الموظفون المسجلون"),
        "labelSite": _t("Werk / Halle", "Plant / hall", "المصنع / القاعة"),
        "labelFirm": _t("Betrieb", "Operation", "المنشأة"),
        "accessFormH3": _t("Schicht-Zutritt", "Shift access", "دخول الوردية"),
        "badgeH3": _t("Ausweis-Vorschau", "ID preview", "معاينة الهوية"),
    },
    "aviation": {
        "topbarHeading": _t(
            "Terminal-Zutritt & Identität",
            "Terminal access & identity",
            "دخول المطار والهوية",
        ),
        "navWorkers": _t("Berechtigte", "Authorized staff", "الموظفون المصرّح لهم"),
        "workersListH3": _t("Registrierte Berechtigte", "Registered authorizees", "المصرّح لهم"),
        "labelSite": _t("Terminal / Zone", "Terminal / zone", "المبنى / المنطقة"),
        "labelFirm": _t("Betreiber / Zeugfirma", "Operator / contractor", "المشغّل / المقاول"),
        "accessFormH3": _t("Zutrittsereignis", "Access event", "حدث الدخول"),
        "badgeH3": _t("Airside-Pass", "Airside pass", "تصريح المنطقة المحظورة"),
    },
    "logistics": {
        "topbarHeading": _t(
            "Hub-Zutritt & Personal",
            "Hub access & workforce",
            "دخول المركز والقوى العاملة",
        ),
        "navWorkers": _t("Personal", "Staff", "الطاقم"),
        "workersListH3": _t("Registriertes Personal", "Registered staff", "الطاقم المسجل"),
        "labelSite": _t("Depot / Hub", "Depot / hub", "المستودع / المركز"),
        "labelFirm": _t("Logistikpartner", "Logistics partner", "شريك اللوجستيات"),
        "accessFormH3": _t("Tor-Events", "Gate events", "أحداث البوابة"),
        "badgeH3": _t("Pass-Vorschau", "Pass preview", "معاينة التصريح"),
    },
    "security": {
        "topbarHeading": _t(
            "Kontrollpunkte & Identität",
            "Checkpoints & identity",
            "نقاط التفتيش والهوية",
        ),
        "navWorkers": _t("Einsatzkräfte", "Officers", "العناصر"),
        "workersListH3": _t("Einsatzkräfte", "Officers on file", "العناصر المسجلون"),
        "labelSite": _t("Objekt / Einsatzort", "Site / assignment", "الموقع / المهمة"),
        "labelFirm": _t("Sicherheitsfirma", "Security firm", "شركة الأمن"),
        "accessFormH3": _t("Kontrollpunkt", "Checkpoint", "نقطة التفتيش"),
        "badgeH3": _t("Dienstausweis", "Service ID", "بطاقة الخدمة"),
    },
    "public_sector": {
        "topbarHeading": _t(
            "Zutritt & Nachweise (öffentlich)",
            "Public access & compliance",
            "الدخول والامتثال (قطاع عام)",
        ),
        "navWorkers": _t("Mitarbeitende", "Staff", "الموظفون"),
        "workersListH3": _t("Registrierte Personen", "Registered persons", "الأشخاص المسجلون"),
        "labelSite": _t("Standort / Gebäude", "Facility", "المنشأة / المبنى"),
        "labelFirm": _t("Organisation", "Organization", "الجهة"),
        "accessFormH3": _t("Zutrittsprotokoll", "Access log", "سجل الدخول"),
        "badgeH3": _t("Ausweis-Vorschau", "ID preview", "معاينة الهوية"),
    },
    "government": {
        "topbarHeading": _t(
            "Enterprise Identity & Zutritt",
            "Enterprise identity & access",
            "الهوية المؤسسية والدخول",
        ),
        "navWorkers": _t("Berechtigte", "Authorized persons", "المصرّح لهم"),
        "workersListH3": _t("Registrierte Berechtigte", "Registered authorizees", "المصرّح لهم المسجلون"),
        "labelSite": _t("Standort / Dienststelle", "Office / site", "الموقع / الدائرة"),
        "labelFirm": _t("Behörde / Ministerium", "Agency / ministry", "الجهة / الوزارة"),
        "accessFormH3": _t("Zutrittskontrolle", "Access control", "التحكم بالدخول"),
        "badgeH3": _t("Dienstausweis", "Official ID", "الهوية الرسمية"),
    },
}


OPERATION_TEMPLATES: dict[str, dict[str, Any]] = {
    "construction": {
        "id": "construction-default",
        "features": ["geofence", "visitor_day_pass", "subcontractors", "safety_docs", "gate_latency"],
        "defaultRoles": ["site_manager", "company_admin", "turnstile"],
        "complianceFocus": ["safety", "insurance", "visitor_log"],
    },
    "manufacturing": {
        "id": "manufacturing-shift",
        "features": ["shifts", "ppe_checklist", "machine_zones", "overtime_export"],
        "defaultRoles": ["site_manager", "compliance_officer", "company_admin"],
        "complianceFocus": ["shift_hours", "training", "lockout_tagout"],
    },
    "aviation": {
        "id": "aviation-terminal",
        "features": ["airside_zones", "temp_badges", "escort_visitors", "security_screening_log"],
        "defaultRoles": ["security_officer", "site_manager", "compliance_officer"],
        "complianceFocus": ["icao", "avsec", "escort_policy"],
    },
    "logistics": {
        "id": "logistics-hub",
        "features": ["vehicle_gates", "temp_badges", "dock_assignments", "carrier_visitors"],
        "defaultRoles": ["site_manager", "security_officer", "company_admin"],
        "complianceFocus": ["carrier_sla", "dock_safety", "visitor_escort"],
    },
    "security": {
        "id": "security-ops",
        "features": ["patrol_checkpoints", "incident_report", "guard_roster", "client_sites"],
        "defaultRoles": ["security_officer", "site_manager", "company_admin"],
        "complianceFocus": ["incidents", "licensing", "client_audit"],
    },
    "public_sector": {
        "id": "public-access",
        "features": ["citizen_visitors", "retention_policy", "audit_export", "department_scopes"],
        "defaultRoles": ["compliance_officer", "auditor", "department_admin"],
        "complianceFocus": ["foia", "retention", "public_audit"],
    },
    "government": {
        "id": "government-enterprise",
        "features": ["sso", "classification_labels", "siem_hooks", "signed_reports", "dr_drill"],
        "defaultRoles": ["security_officer", "compliance_officer", "auditor", "regional_manager"],
        "complianceFocus": ["iso27001", "data_classification", "sovereign_hosting"],
    },
}


def sector_config(sector_id: str, *, lang: str = "de") -> dict[str, Any]:
    sector_id = normalize_operating_sector(sector_id)
    lang = str(lang or "de").strip().lower()[:2] or "de"
    meta = SECTOR_META[sector_id]
    terms_raw = SECTOR_TERM_KEYS.get(sector_id, {})
    terms = {k: (v.get(lang) or v.get("de") or "") for k, v in terms_raw.items()}
    label = meta["labels"].get(lang) or meta["labels"]["de"]
    product_line = meta["productLine"].get(lang) or meta["productLine"]["de"]
    return {
        "sector": sector_id,
        "label": label,
        "productLine": product_line,
        "terms": terms,
        "template": OPERATION_TEMPLATES.get(sector_id, {}),
        "availableSectors": [
            {
                "id": sid,
                "label": SECTOR_META[sid]["labels"].get(lang) or SECTOR_META[sid]["labels"]["de"],
            }
            for sid in sorted(VALID_SECTORS)
        ],
    }


def all_sectors_public() -> list[dict[str, str]]:
    return [
        {"id": sid, "labels": SECTOR_META[sid]["labels"], "productLine": SECTOR_META[sid]["productLine"]}
        for sid in sorted(VALID_SECTORS)
    ]
