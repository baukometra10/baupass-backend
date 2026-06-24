"""
Canonical registration order for SUPPIX domain blueprints.

API domains first (foundation → business). HTTP/static routes last so the
catch-all static proxy does not shadow API paths.
"""
from __future__ import annotations

from typing import NamedTuple


class DomainRegistrar(NamedTuple):
    """Import path and registrar function for one bounded context."""

    name: str
    module: str
    registrar: str
    category: str


# fmt: off
DOMAIN_REGISTRARS: tuple[DomainRegistrar, ...] = (
    # Foundation
    DomainRegistrar("auth", "backend.app.domains.auth.routes", "register_auth_blueprint", "foundation"),
    DomainRegistrar("runtime", "backend.app.domains.runtime.routes", "register_runtime_blueprint", "foundation"),
    DomainRegistrar("settings", "backend.app.domains.settings.routes", "register_settings_blueprint", "foundation"),
    DomainRegistrar("rbac", "backend.app.domains.rbac.routes", "register_rbac_domain_blueprint", "foundation"),
    # Tenant & people
    DomainRegistrar("companies", "backend.app.domains.companies.routes", "register_companies_blueprint", "tenant"),
    DomainRegistrar("workers", "backend.app.domains.workers.routes", "register_workers_blueprint", "tenant"),
    DomainRegistrar("onboarding", "backend.app.domains.onboarding.routes", "register_onboarding_blueprint", "tenant"),
    DomainRegistrar("contracts", "backend.app.domains.contracts.routes", "register_contracts_blueprint", "tenant"),
    # Operations
    DomainRegistrar("access", "backend.app.domains.access.routes", "register_access_blueprint", "operations"),
    DomainRegistrar("devices", "backend.app.domains.devices.routes", "register_devices_blueprint", "operations"),
    DomainRegistrar("workforce", "backend.app.domains.workforce.routes", "register_workforce_blueprint", "operations"),
    DomainRegistrar("operations", "backend.app.domains.operations.routes", "register_operations_blueprint", "operations"),
    DomainRegistrar("compliance", "backend.app.domains.compliance.routes", "register_compliance_blueprint", "operations"),
    DomainRegistrar("chat", "backend.app.domains.chat.routes", "register_chat_blueprint", "operations"),
    # Back-office
    DomainRegistrar("documents", "backend.app.domains.documents.routes", "register_documents_blueprint", "backoffice"),
    DomainRegistrar("billing", "backend.app.domains.billing.routes", "register_billing_blueprint", "backoffice"),
    DomainRegistrar("reporting", "backend.app.domains.reporting.routes", "register_reporting_blueprint", "backoffice"),
    DomainRegistrar("notifications", "backend.app.domains.notifications.routes", "register_notifications_blueprint", "backoffice"),
    DomainRegistrar("admin", "backend.app.domains.admin.routes", "register_admin_blueprint", "backoffice"),
    # Static HTML / assets (must stay last)
    DomainRegistrar("http", "backend.app.domains.http.routes", "register_http_blueprint", "static"),
)
# fmt: on
