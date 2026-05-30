"""Enterprise role catalog — mapped gradually onto legacy roles."""
from __future__ import annotations

from typing import Any

# Legacy roles still enforced in require_roles(); enterprise roles are additive targets.
ENTERPRISE_ROLES: list[dict[str, Any]] = [
    {
        "id": "superadmin",
        "legacy": ["superadmin"],
        "labels": {"de": "Plattform-Admin", "en": "Platform admin", "ar": "مشرف المنصة"},
        "scope": "global",
    },
    {
        "id": "company_admin",
        "legacy": ["company-admin"],
        "labels": {"de": "Mandanten-Admin", "en": "Tenant admin", "ar": "مدير المستأجر"},
        "scope": "company",
    },
    {
        "id": "department_admin",
        "legacy": ["company-admin"],
        "labels": {"de": "Abteilungs-Admin", "en": "Department admin", "ar": "مدير القسم"},
        "scope": "department",
        "status": "planned",
    },
    {
        "id": "department_manager",
        "legacy": ["company-admin"],
        "labels": {"de": "Abteilungsleitung", "en": "Department manager", "ar": "مدير الإدارة"},
        "scope": "department",
        "status": "planned",
    },
    {
        "id": "site_manager",
        "legacy": ["company-admin"],
        "labels": {"de": "Standort-Leitung", "en": "Site manager", "ar": "مدير الموقع"},
        "scope": "site",
        "status": "planned",
    },
    {
        "id": "regional_manager",
        "legacy": ["company-admin"],
        "labels": {"de": "Regionalleitung", "en": "Regional manager", "ar": "مدير إقليمي"},
        "scope": "region",
        "status": "planned",
    },
    {
        "id": "security_officer",
        "legacy": ["company-admin"],
        "labels": {"de": "Sicherheitsbeauftragter", "en": "Security officer", "ar": "مسؤول الأمن"},
        "scope": "security",
        "status": "planned",
    },
    {
        "id": "compliance_officer",
        "legacy": ["company-admin"],
        "labels": {"de": "Compliance Officer", "en": "Compliance officer", "ar": "مسؤول الامتثال"},
        "scope": "compliance",
        "status": "planned",
    },
    {
        "id": "auditor",
        "legacy": ["company-admin"],
        "labels": {"de": "Prüfer (nur lesen)", "en": "Auditor (read-only)", "ar": "مدقق (قراءة فقط)"},
        "scope": "audit",
        "status": "planned",
    },
    {
        "id": "turnstile",
        "legacy": ["turnstile"],
        "labels": {"de": "Zutrittspunkt", "en": "Access endpoint", "ar": "نقطة الدخول"},
        "scope": "gate",
    },
]


def rbac_catalog(lang: str = "de") -> dict[str, Any]:
    lang = (lang or "de")[:2]
    roles = []
    for r in ENTERPRISE_ROLES:
        roles.append(
            {
                "id": r["id"],
                "legacy": r.get("legacy", []),
                "label": (r.get("labels") or {}).get(lang) or r["id"],
                "scope": r.get("scope"),
                "status": r.get("status", "active"),
            }
        )
    return {
        "roles": roles,
        "sso": {
            "catalogPath": "/api/auth/sso/catalog",
            "oidc": "active",
            "entra": "active",
            "google": "active",
            "keycloak": "available",
            "saml": "scaffold",
            "ad_ldap": "federation",
        },
        "permissionModel": "planned",
        "notes": "Enterprise roles are catalogued; enforcement extends legacy require_roles() incrementally.",
    }
