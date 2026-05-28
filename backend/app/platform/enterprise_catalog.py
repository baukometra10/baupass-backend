"""
BauPass Enterprise Catalog — maps vision layers to real UI surfaces and APIs.
Used by /api/platform/enterprise-catalog and enterprise-hub.html
"""
from __future__ import annotations

from typing import Any

# surface: legacy | admin-v2 | worker | hub | api | config
_SURFACE_LABELS = {
    "legacy": {"de": "Legacy-Portal", "en": "Legacy portal", "ar": "لوحة Legacy", "color": "#3b82f6"},
    "admin-v2": {"de": "Admin v2", "en": "Admin v2", "ar": "Admin v2", "color": "#14b8a6"},
    "worker": {"de": "Worker-App", "en": "Worker app", "ar": "تطبيق الموظف", "color": "#a855f7"},
    "hub": {"de": "Enterprise-Hub", "en": "Enterprise hub", "ar": "مركز المؤسسة", "color": "#f59e0b"},
    "api": {"de": "Nur API", "en": "API only", "ar": "API فقط", "color": "#64748b"},
    "config": {"de": "Konfiguration", "en": "Configuration", "ar": "يتطلب إعداد", "color": "#ef4444"},
}


def _item(
    key: str,
    label: str,
    label_ar: str,
    surface: str,
    *,
    apis: list[str] | None = None,
    ui: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    return {
        "id": key,
        "label": label,
        "labelAr": label_ar,
        "surface": surface,
        "apis": apis or [],
        "ui": ui or "",
        "note": note,
    }


def get_enterprise_catalog() -> dict[str, Any]:
    layers = [
        {
            "id": "core_workforce",
            "number": 1,
            "title": "Core Workforce Infrastructure",
            "titleAr": "البنية الأساسية للقوى العاملة",
            "items": [
                _item("employees", "Employee Management", "إدارة الموظفين", "legacy", apis=["GET /api/workers"], ui="/index.html#workers"),
                _item("workforce_mgmt", "Workforce Management", "إدارة القوى العاملة", "legacy", ui="/index.html"),
                _item("attendance", "Attendance Management", "إدارة الحضور", "legacy", apis=["GET /api/access-logs"], ui="/index.html#access"),
                _item("gps_attendance", "GPS Attendance", "حضور GPS", "worker", apis=["POST /api/worker-app/attendance/nfc"], ui="/admin-v2/index.html"),
                _item("geofence_att", "Geofence Attendance", "حضور Geofence", "legacy", apis=["GET /api/geofences"], ui="/index.html"),
                _item("smart_inout", "Smart Check-In / Out", "دخول/خروج ذكي", "worker", apis=["POST /api/scan"]),
                _item("auto_checkin_loc", "Auto Check-In by Location", "دخول تلقائي بالموقع", "worker"),
                _item("shifts", "Shift Management", "إدارة الورديات", "legacy", ui="/index.html"),
                _item("shift_mgmt", "Advanced Shift Scheduling", "جدولة ورديات متقدمة", "legacy"),
                _item("leave", "Leave Management", "الإجازات", "legacy", ui="/index.html#leave"),
                _item("sick_leave", "Sick Leave Management", "إجازات مرضية", "legacy", ui="/index.html#leave"),
                _item("worker_profiles", "Worker Profiles", "ملفات الموظف", "legacy", ui="/index.html#workers"),
                _item("worker_documents", "Worker Documents", "مستندات الموظف", "legacy", ui="/index.html"),
                _item("timesheets", "Worker Timesheets", "سجلات الوقت", "legacy", apis=["GET /api/export/timesheets"]),
                _item("scheduling", "Workforce Scheduling", "جدولة القوى العاملة", "legacy"),
                _item("presence_tracking", "Worker Presence Tracking", "تتبع الحضور", "admin-v2", ui="/admin-v2/index.html"),
                _item("workforce_reporting", "Workforce Reporting", "تقارير القوى العاملة", "legacy"),
                _item("worker_notifications", "Worker Notifications", "إشعارات الموظف", "worker"),
                _item("foreman_dashboard", "Foreman Dashboard", "لوحة المشرف", "legacy"),
                _item("contractor_mgmt", "Contractor Management", "المقاولون", "legacy"),
                _item("visitor", "Visitor Management", "الزوار", "legacy", ui="/index.html"),
                _item("rbac", "RBAC System", "صلاحيات RBAC", "legacy", ui="/index.html#admin"),
                _item("workforce_roles", "Workforce Roles & Permissions", "أدوار القوى العاملة", "legacy"),
                _item("multi_tenant", "Multi-Tenant Architecture", "تعدد المستأجرين", "legacy", apis=["GET /api/companies"]),
                _item("multi_branch", "Multi-Branch Support", "فروع متعددة", "legacy"),
                _item("tenant_isolation", "Tenant Isolation", "عزل المستأجر", "api"),
                _item("company_work_rules", "Company Work Rules", "قواعد الشركة", "legacy"),
                _item("site_work_rules", "Site Work Rules", "قواعد الموقع", "legacy"),
                _item("workforce_compliance", "Workforce Compliance", "امتثال القوى العاملة", "legacy"),
                _item("worker_pwa", "Worker App (PWA)", "تطبيق PWA", "worker", ui="/emp-app.html"),
                _item("worker_dashboard", "Worker Dashboard", "لوحة الموظف", "worker", ui="/emp-app.html"),
                _item("self_service", "Worker Self-Service Portal", "بوابة الخدمة الذاتية", "worker"),
                _item("offline", "Offline Workforce Operations", "عمل دون اتصال", "worker"),
                _item("access_logs_wf", "Workforce Access Logs", "سجلات وصول القوى العاملة", "legacy", ui="/index.html#access"),
                _item("analytics_wf", "Workforce Analytics", "تحليلات القوى العاملة", "api", apis=["GET /api/v2/admin/overview"]),
                _item("workforce_kpi", "Workforce KPI System", "مؤشرات الأداء", "api", apis=["GET /api/reporting/summary"]),
            ],
        },
        {
            "id": "digital_identity",
            "number": 2,
            "title": "Workforce Digital Identity Layer",
            "titleAr": "الهوية الرقمية للموظف",
            "items": [
                _item("digital_employee_id", "Digital Employee Identity", "الهوية الرقمية", "worker", ui="/join.html"),
                _item("qr_badge", "QR Badge System", "شارات QR", "legacy", apis=["POST /api/scan"]),
                _item("dynamic_qr", "Dynamic QR Codes", "QR ديناميكي", "api", apis=["POST /api/worker-app/dqr"]),
                _item("nfc_id", "NFC Identity", "هوية NFC", "admin-v2", ui="/admin-v2/index.html"),
                _item("smart_badge", "Smart Badge Infrastructure", "بنية الشارات الذكية", "legacy"),
                _item("temp_access_pass", "Temporary Access Passes", "تصاريح مؤقتة", "legacy"),
                _item("identity_tokens", "Workforce Identity Tokens", "رموز الهوية", "api"),
                _item("identity_verify", "Secure Identity Verification", "التحقق الآمن", "api"),
                _item("device_trust", "Device Trust System", "ثقة الأجهزة", "api"),
                _item("identity_sessions", "Identity Sessions", "جلسات الهوية", "api"),
                _item("cross_platform_id", "Cross-Platform Identity", "هوية متعددة المنصات", "worker"),
                _item("enterprise_identity", "Enterprise Identity Engine", "محرك الهوية المؤسسي", "api"),
                _item("unified_identity", "Unified Workforce Identity", "منصة هوية موحدة", "hub", ui="/enterprise-hub.html"),
                _item("apple_wallet", "Apple Wallet Pass", "Apple Wallet", "config", apis=["GET /api/admin/wallet/runtime-status"]),
                _item("google_wallet", "Google Wallet Pass", "Google Wallet", "config", apis=["GET /api/admin/wallet/runtime-status"]),
                _item("hce", "Android HCE Identity", "HCE أندرويد", "worker"),
                _item("join_flow", "Identity Onboarding", "تفعيل الهوية", "admin-v2", ui="/join.html"),
            ],
        },
        {
            "id": "access_security",
            "number": 3,
            "title": "Access & Physical Security Layer",
            "titleAr": "التحكم بالدخول والأمن الفيزيائي",
            "items": [
                _item("gates", "Gate Management", "إدارة البوابات", "legacy", apis=["POST /api/scan", "GET /api/gates"], ui="/index.html#devices"),
                _item("turnstile", "Turnstile Integration", "التكامل مع البوابة الدوارة", "legacy", apis=["POST /api/scan"], ui="/index.html"),
                _item("nfc_access", "NFC Access Control", "دخول NFC", "worker", apis=["POST /api/worker-app/attendance/nfc", "POST /api/scan"]),
                _item("live_access", "Live Access Monitoring", "مراقبة دخول مباشرة", "admin-v2", apis=["GET /api/v2/access/live"], ui="/admin-v2/index.html"),
                _item("access_logs", "Access Logs", "سجلات الدخول", "legacy", apis=["GET /api/access-logs/export.csv"], ui="/index.html#access"),
                _item("zones", "Smart Access Zones", "مناطق الدخول", "api", apis=["GET /api/enterprise/geofences/admin"]),
                _item("emergency", "Emergency Lockdown", "إغلاق طوارئ", "api", apis=["GET /api/ops-os/emergency"]),
                _item("cmd_center", "Live Gate Monitoring", "مركز البوابات", "hub", apis=["GET /api/ops-os/command-center"], ui="/ops-command-center.html"),
            ],
        },
        {
            "id": "automation",
            "number": 4,
            "title": "Smart Automation Layer",
            "titleAr": "الأتمتة الذكية",
            "items": [
                _item("workflows", "Workflow Automation", "أتمتة سير العمل", "api", apis=["GET /api/automation/rules"]),
                _item("auto_expiry", "Auto Expiry Alerts", "تنبيهات انتهاء", "legacy", apis=["GET /api/system/alerts"], ui="/index.html"),
                _item("dunning", "Auto Invoice / Dunning", "تذكير الفواتير", "api", note="خلفية — Redis يحسّنها"),
                _item("onboarding_auto", "Auto Onboarding", "تأهيل تلقائي", "api", apis=["GET /api/v2/onboarding"]),
                _item("event_bus", "Event-Driven Automation", "أحداث آلية", "api", apis=["POST /api/platform/events (internal)"]),
            ],
        },
        {
            "id": "realtime",
            "number": 5,
            "title": "Real-Time Operations Layer",
            "titleAr": "التشغيل اللحظي",
            "items": [
                _item("websocket", "WebSocket Infrastructure", "WebSocket", "config", apis=["GET /api/realtime/status"], note="BAUPASS_WEBSOCKET_ENABLED=1"),
                _item("live_presence", "Live Presence", "الحضور المباشر", "admin-v2", apis=["GET /api/v2/admin/overview"], ui="/admin-v2/index.html"),
                _item("live_metrics", "Real-Time Metrics", "مقاييس لحظية", "api", apis=["GET /metrics", "GET /api/health"]),
                _item("sse", "Live Activity Streams", "بث الأحداث", "api", apis=["GET /api/realtime/events"]),
            ],
        },
        {
            "id": "operational_ux",
            "number": 6,
            "title": "Operational Experience Layer",
            "titleAr": "تجربة التشغيل",
            "items": [
                _item("admin_v2", "Modern Enterprise UI", "واجهة Enterprise", "admin-v2", ui="/admin-v2/index.html"),
                _item("design_tokens", "Design System", "نظام التصميم", "hub", ui="/design-tokens.css"),
                _item("offline_sync", "Offline Sync", "مزامنة دون اتصال", "worker", apis=["POST /api/worker-app/offline-events"]),
                _item("flutter", "Cross-Platform App", "تطبيق Flutter", "worker", apis=["GET /api/v2/mobile/distribution"]),
            ],
        },
        {
            "id": "security_compliance",
            "number": 7,
            "title": "Enterprise Security & Compliance",
            "titleAr": "الأمان والامتثال",
            "items": [
                _item("zero_trust", "Zero Trust", "Zero Trust", "config", note="BAUPASS_ZERO_TRUST=1"),
                _item("rbac_adv", "Advanced RBAC", "RBAC متقدم", "legacy", ui="/index.html#admin"),
                _item("audit", "Immutable Audit Trails", "سجل تدقيق", "legacy", apis=["GET /api/audit-logs"], ui="/index.html"),
                _item("mfa", "MFA / 2FA", "مصادقة ثنائية", "legacy", apis=["POST /api/login"], ui="/index.html"),
                _item("siem", "SIEM Export", "تصدير SIEM", "api", apis=["GET /api/enterprise/security/siem-export"]),
                _item("encryption", "Encryption Layer", "تشفير", "config", note="BAUPASS_FIELD_ENCRYPTION_KEY"),
            ],
        },
        {
            "id": "intelligence",
            "number": 8,
            "title": "Enterprise Intelligence Layer",
            "titleAr": "الذكاء المؤسسي + AI",
            "items": [
                _item("ai_assistant", "AI Assistant", "مساعد ذكاء", "hub", apis=["POST /api/ai/query", "GET /api/ai/status"], ui="/enterprise-hub.html"),
                _item("ai_copilot", "AI Copilot", "Copilot تشغيلي", "hub", apis=["POST /api/ops-os/copilot"]),
                _item("predictive_att", "Predictive Attendance", "تنبؤ الحضور", "api", apis=["GET /api/ai/predictive-attendance"]),
                _item("fraud", "Fraud Detection", "كشف احتيال", "api", apis=["GET /api/ai/fraud-detection"]),
                _item("scheduling_ai", "AI Scheduling", "جدولة ذكية", "api", apis=["GET /api/operations/intelligence/scheduling"]),
                _item("heatmap", "Workforce Heatmaps", "خرائط حرارية", "api", apis=["GET /api/analytics/workforce-heatmap"]),
                _item("nlq", "Natural Language Queries", "استعلام بلغة طبيعية", "hub", apis=["POST /api/ai/query"]),
            ],
        },
        {
            "id": "physical_ops",
            "number": 9,
            "title": "Smart Physical Operations Layer",
            "titleAr": "العمليات الفيزيائية الذكية",
            "items": [
                _item("ops_os", "Physical Operations OS", "نظام العمليات الفيزيائية", "hub", apis=["GET /api/ops-os/overview"], ui="/ops-command-center.html"),
                _item("digital_twin", "Digital Twin", "توأم رقمي", "api", apis=["GET /api/ops-os/digital-twin"]),
                _item("site_intel", "Site Intelligence", "ذكاء الموقع", "api", apis=["GET /api/ops-os/site-intelligence"]),
                _item("camera_ai", "Camera Intelligence", "ذكاء الكاميرات", "api", apis=["POST /api/integrations/security-cameras/events"]),
                _item("iot", "IoT Infrastructure", "IoT", "api", apis=["GET /api/ops-os/iot"]),
                _item("emergency_ops", "Emergency Intelligence", "طوارئ", "api", apis=["GET /api/ops-os/emergency"]),
            ],
        },
        {
            "id": "autonomous",
            "number": 10,
            "title": "Autonomous Enterprise Layer",
            "titleAr": "المؤسسة الذاتية",
            "items": [
                _item("auto_rules", "Autonomous Rules", "قواعد ذاتية", "api", apis=["GET /api/automation/rules"]),
                _item("self_heal", "Self-Healing Jobs", "مهام ذاتية الإصلاح", "api", note="مع Redis + worker"),
                _item("auto_incident", "Autonomous Incident Response", "استجابة حوادث", "api", apis=["GET /api/incidents"]),
            ],
        },
        {
            "id": "integrations",
            "number": 11,
            "title": "Enterprise Integration Ecosystem",
            "titleAr": "التكاملات المؤسسية",
            "items": [
                _item("payroll", "Payroll Integrations", "الرواتب", "api", apis=["GET /api/integrations/payroll/export"]),
                _item("sap", "SAP Integration", "SAP", "api", apis=["POST /api/integrations/sap/sync"]),
                _item("oracle", "Oracle Integration", "Oracle", "api", apis=["POST /api/integrations/oracle/sync"]),
                _item("m365", "Microsoft 365", "Microsoft 365", "api", apis=["POST /api/integrations/microsoft365/connect"]),
                _item("google", "Google Workspace", "Google", "api", apis=["POST /api/integrations/google/connect"]),
                _item("webhooks", "Webhooks", "Webhooks", "api", apis=["GET /api/developer/webhooks"]),
                _item("api_gateway", "API Gateway / v1", "بوابة API", "api", apis=["GET /api/v1/openapi.json"]),
            ],
        },
        {
            "id": "platform_ecosystem",
            "number": 12,
            "title": "Platform Ecosystem Layer",
            "titleAr": "النظام البيئي للمنصة",
            "items": [
                _item("sdk", "SDK Infrastructure", "SDK", "api", ui="/sdk/baupass_client.py"),
                _item("marketplace", "Integration Marketplace", "سوق التكاملات", "api", apis=["GET /api/marketplace/plugins"]),
                _item("white_label", "White-Label", "علامة بيضاء", "legacy", ui="/index.html#admin"),
                _item("public_api", "Public Developer APIs", "APIs عامة", "api", apis=["GET /api/v1/*"]),
            ],
        },
        {
            "id": "hyper_scale",
            "number": 13,
            "title": "Hyper-Scale Infrastructure",
            "titleAr": "البنية التحتية العالمية",
            "items": [
                _item("k8s", "Kubernetes Ready", "جاهز لـ K8s", "config", ui="/deploy/k8s/"),
                _item("postgres", "PostgreSQL Clustering", "PostgreSQL", "config", apis=["GET /api/platform/database-status"]),
                _item("redis", "Queue / Redis", "Redis", "config", apis=["GET /api/health/queues"], note="REDIS_URL"),
                _item("dr", "Disaster Recovery", "استعادة كوارث", "api", apis=["GET /api/health/dr"]),
                _item("obs", "Observability Stack", "مراقبة", "api", apis=["GET /metrics", "GET /observability/status"]),
                _item("multi_region", "Multi-Region", "تعدد المناطق", "config", note="BAUPASS_REGION_STRATEGY"),
            ],
        },
        {
            "id": "saas_business",
            "number": 14,
            "title": "Enterprise SaaS & Business",
            "titleAr": "الأعمال والـ SaaS",
            "items": [
                _item("billing", "Enterprise Billing", "الفوترة", "legacy", apis=["GET /api/invoices"], ui="/index.html#invoices"),
                _item("dunning_b", "Dunning Automation", "تحصيل آلي", "api", note="خلفية"),
                _item("plans", "Multi-Plan SaaS", "خطط اشتراك", "legacy", ui="/index.html"),
            ],
        },
        {
            "id": "global_command",
            "number": 15,
            "title": "Global Operational Command",
            "titleAr": "مركز التحكم العالمي",
            "items": [
                _item("command", "Workforce Command Center", "مركز قيادة", "hub", apis=["GET /api/ops-os/command-center"], ui="/ops-command-center.html"),
                _item("global_ready", "Global Readiness", "جاهزية عالمية", "hub", apis=["GET /api/platform/global-readiness"]),
                _item("catalog", "Enterprise Catalog", "كتالوج القدرات", "hub", apis=["GET /api/platform/enterprise-catalog"], ui="/enterprise-hub.html"),
            ],
        },
        {
            "id": "vision",
            "number": 16,
            "title": "Future Strategic Vision",
            "titleAr": "الرؤية المستقبلية",
            "items": [
                _item("wf_os", "Workforce Operating System", "نظام تشغيل القوى العاملة", "hub", note="رؤية — التجميع عبر الطبقات 1–15"),
                _item("ai_cloud", "AI Workforce Cloud", "سحابة ذكاء", "api", note="OPENAI_API_KEY + طبقة intelligence"),
            ],
        },
    ]

    stats = {"legacy": 0, "admin-v2": 0, "worker": 0, "hub": 0, "api": 0, "config": 0, "total": 0}
    for layer in layers:
        for it in layer["items"]:
            stats["total"] += 1
            stats[it["surface"]] = stats.get(it["surface"], 0) + 1

    return {
        "product": "BauPass Enterprise Platform",
        "layerCount": len(layers),
        "surfaceLabels": _SURFACE_LABELS,
        "stats": stats,
        "layers": layers,
        "primaryUi": {
            "legacy": "/index.html",
            "adminV2": "/admin-v2/index.html",
            "enterpriseHub": "/enterprise-hub.html",
            "opsCenter": "/ops-command-center.html",
            "workerJoin": "/join.html",
        },
    }
