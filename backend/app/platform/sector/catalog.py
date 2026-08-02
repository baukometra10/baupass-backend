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


# UI translation keys overridden per sector (SUPPIX + worker app can consume the same keys)
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


def _admin_access_pack(
    *,
    late: dict[str, str],
    checkins: dict[str, str],
    recent: dict[str, str],
    outside: dict[str, str],
    on_site: dict[str, str],
    attendance_filter: dict[str, str],
    workers_title: dict[str, str],
    access_title: dict[str, str],
    access_desc: dict[str, str],
) -> dict[str, dict[str, str]]:
    return {
        "accessLateCheckIns": late,
        "accessCheckIns": checkins,
        "accessRecentBookings": recent,
        "lageOutsideHours": outside,
        "lageOnSite": on_site,
        "inboxFilterAttendance": attendance_filter,
        "sectionWorkersTitle": workers_title,
        "sectionAccessTitle": access_title,
        "sectionAccessDesc": access_desc,
    }


# Admin-v2 / Betrieb dashboard strings overridden per operating sector
ADMIN_V2_TERM_KEYS: dict[str, dict[str, dict[str, str]]] = {
    "construction": {
        "overviewOnSite": _t("Jetzt auf der Baustelle", "On site now", "على موقع البناء الآن"),
        "overviewOnSiteKpi": _t("auf Baustelle", "on site", "على الموقع"),
        "overviewActiveWorkers": _t("Aktive Mitarbeiter", "Active workers", "عمال نشطون"),
        "toolsGeofence": _t("Geofence — Baustellen", "Geofence — sites", "Geofence — مواقع البناء"),
        "deploymentLocationPh": _t("z. B. Baustelle Berlin, Musterstraße 12", "e.g. Site Berlin, Main St 12", "مثال: موقع برلين"),
        "toolsSitePlaceholder": _t("Standort / Baustelle", "Site / project", "موقع / مشروع"),
        "deploymentColLocation": _t("Einsatzort", "Assignment location", "موقع التكليف"),
        "tabWorkers": _t("Mitarbeiter", "Workers", "العمال"),
        "tabAccess": _t("Anwesenheit", "Attendance", "الحضور"),
        "tabMobile": _t("Mitarbeiter-App", "Worker app", "تطبيق العمال"),
        "navGroupPeople": _t("Personal", "People", "القوى العاملة"),
        "termWorker": _t("Mitarbeiter", "Worker", "عامل"),
        "termWorkers": _t("Mitarbeiter", "Workers", "عمال"),
        "termSite": _t("Baustelle", "Site", "موقع بناء"),
        "termGate": _t("Drehkreuz / Tor", "Turnstile / gate", "بوابة / دروازه"),
        "sectorBanner": _t(
            "Fachsprache: Bau & Baustelle — Begriffe passen sich dem Betriebssektor an.",
            "Terminology: Construction — labels follow the operating sector.",
            "المصطلحات: البناء — تتغير حسب القطاع التشغيلي.",
        ),
        **_admin_access_pack(
            late=_t("Verspätete Check-ins heute", "Late check-ins today", "تسجيلات متأخرة اليوم"),
            checkins=_t("Check-ins heute", "Check-ins today", "تسجيلات الدخول اليوم"),
            recent=_t("Letzte Buchungen", "Recent bookings", "آخر التسجيلات"),
            outside=_t("Außerhalb Arbeitszeit", "Outside working hours", "خارج ساعات العمل"),
            on_site=_t("Auf Baustelle", "On site", "على الموقع"),
            attendance_filter=_t("Anwesenheit", "Attendance", "الحضور"),
            workers_title=_t("Mitarbeiter", "Workers", "العمال"),
            access_title=_t("Anwesenheit & Zutritt", "Attendance & access", "الحضور والدخول"),
            access_desc=_t(
                "Check-ins, Verspätungen und Tore auf der Baustelle.",
                "Check-ins, lateness and gates on site.",
                "تسجيل الدخول والتأخر والبوابات في الموقع.",
            ),
        ),
    },
    "manufacturing": {
        "overviewOnSite": _t("Jetzt im Werk", "In plant now", "في المنشأة الآن"),
        "overviewOnSiteKpi": _t("im Werk", "in plant", "في المنشأة"),
        "overviewActiveWorkers": _t("Aktive Mitarbeiter", "Active employees", "موظفون نشطون"),
        "toolsGeofence": _t("Geofence — Werksbereiche", "Geofence — plant zones", "Geofence — مناطق المصنع"),
        "deploymentLocationPh": _t("z. B. Halle 3, Werk Nord", "e.g. Hall 3, North plant", "مثال: القاعة 3، المصنع الشمالي"),
        "toolsSitePlaceholder": _t("Werk / Halle", "Plant / hall", "مصنع / قاعة"),
        "deploymentColLocation": _t("Werk / Halle", "Plant / hall", "مصنع / قاعة"),
        "tabWorkers": _t("Mitarbeiter", "Employees", "الموظفون"),
        "tabAccess": _t("Schicht-Zutritt", "Shift access", "دخول الوردية"),
        "tabMobile": _t("Mitarbeiter-App", "Employee app", "تطبيق الموظفين"),
        "navGroupPeople": _t("Belegschaft", "Workforce", "القوى العاملة"),
        "termWorker": _t("Mitarbeiter", "Employee", "موظف"),
        "termWorkers": _t("Mitarbeiter", "Employees", "موظفون"),
        "termSite": _t("Werk", "Plant", "منشأة"),
        "termGate": _t("Werktor", "Plant gate", "بوابة المصنع"),
        "sectorBanner": _t(
            "Fachsprache: Industrie & Produktion — Begriffe folgen dem Betriebssektor.",
            "Terminology: Manufacturing — labels follow the operating sector.",
            "المصطلحات: الصناعة — تتغير حسب القطاع التشغيلي.",
        ),
        **_admin_access_pack(
            late=_t("Verspätete Schicht-Check-ins", "Late shift check-ins", "تسجيلات وردية متأخرة"),
            checkins=_t("Check-ins heute", "Check-ins today", "تسجيلات الدخول اليوم"),
            recent=_t("Letzte Werksbuchungen", "Recent plant bookings", "آخر تسجيلات المنشأة"),
            outside=_t("Außerhalb Schichtzeit", "Outside shift hours", "خارج وقت الوردية"),
            on_site=_t("Im Werk", "In plant", "في المنشأة"),
            attendance_filter=_t("Schicht-Zutritt", "Shift access", "دخول الوردية"),
            workers_title=_t("Mitarbeiter", "Employees", "الموظفون"),
            access_title=_t("Schicht-Zutritt", "Shift access", "دخول الوردية"),
            access_desc=_t(
                "Check-ins, Verspätungen und Werkstore.",
                "Check-ins, lateness and plant gates.",
                "تسجيل الدخول والتأخر وبوابات المصنع.",
            ),
        ),
    },
    "aviation": {
        "overviewOnSite": _t("Jetzt im Terminal", "In terminal now", "في المبنى الآن"),
        "overviewOnSiteKpi": _t("im Terminal", "in terminal", "في المبنى"),
        "overviewActiveWorkers": _t("Aktive Berechtigte", "Active authorizees", "مصرّح لهم نشطون"),
        "toolsGeofence": _t("Geofence — Zonen", "Geofence — zones", "Geofence — المناطق"),
        "deploymentLocationPh": _t("z. B. Terminal 1, Zone B", "e.g. Terminal 1, Zone B", "مثال: المبنى 1، المنطقة B"),
        "toolsSitePlaceholder": _t("Terminal / Zone", "Terminal / zone", "مبنى / منطقة"),
        "deploymentColLocation": _t("Terminal / Zone", "Terminal / zone", "مبنى / منطقة"),
        "tabWorkers": _t("Berechtigte", "Authorized staff", "المصرّح لهم"),
        "tabAccess": _t("Zutritt", "Access", "الدخول"),
        "tabMobile": _t("Pass-App", "Pass app", "تطبيق التصريح"),
        "navGroupPeople": _t("Berechtigte", "Authorizees", "المصرّح لهم"),
        "termWorker": _t("Berechtigter", "Authorizee", "مصرّح له"),
        "termWorkers": _t("Berechtigte", "Authorizees", "المصرّح لهم"),
        "termSite": _t("Terminal", "Terminal", "مبنى المطار"),
        "termGate": _t("Kontrollpunkt", "Checkpoint", "نقطة تفتيش"),
        "sectorBanner": _t(
            "Fachsprache: Luftfahrt — Begriffe folgen dem Betriebssektor.",
            "Terminology: Aviation — labels follow the operating sector.",
            "المصطلحات: الطيران — تتغير حسب القطاع التشغيلي.",
        ),
        **_admin_access_pack(
            late=_t("Verspätete Zutritte heute", "Late access today", "دخول متأخر اليوم"),
            checkins=_t("Zutritte heute", "Access events today", "أحداث الدخول اليوم"),
            recent=_t("Letzte Zutritte", "Recent access", "آخر عمليات الدخول"),
            outside=_t("Außerhalb Dienstzeit", "Outside duty hours", "خارج وقت الخدمة"),
            on_site=_t("Im Terminal", "In terminal", "في المبنى"),
            attendance_filter=_t("Zutritt", "Access", "الدخول"),
            workers_title=_t("Berechtigte", "Authorized staff", "المصرّح لهم"),
            access_title=_t("Terminal-Zutritt", "Terminal access", "دخول المطار"),
            access_desc=_t(
                "Zutritte, Verspätungen und Kontrollpunkte im Terminal.",
                "Access, lateness and checkpoints in the terminal.",
                "الدخول والتأخر ونقاط التفتيش في المبنى.",
            ),
        ),
    },
    "logistics": {
        "overviewOnSite": _t("Jetzt im Hub", "At hub now", "في المركز الآن"),
        "overviewOnSiteKpi": _t("im Hub", "at hub", "في المركز"),
        "overviewActiveWorkers": _t("Aktives Personal", "Active staff", "طاقم نشط"),
        "toolsGeofence": _t("Geofence — Depots", "Geofence — depots", "Geofence — المستودعات"),
        "deploymentLocationPh": _t("z. B. Depot Nord, Rampe 4", "e.g. North depot, dock 4", "مثال: مستودع الشمال، رصيف 4"),
        "toolsSitePlaceholder": _t("Depot / Hub", "Depot / hub", "مستودع / مركز"),
        "deploymentColLocation": _t("Depot / Hub", "Depot / hub", "مستودع / مركز"),
        "tabWorkers": _t("Personal", "Staff", "الطاقم"),
        "tabAccess": _t("Tor-Events", "Gate events", "أحداث البوابة"),
        "tabMobile": _t("Personal-App", "Staff app", "تطبيق الطاقم"),
        "navGroupPeople": _t("Personal", "Staff", "الطاقم"),
        "termWorker": _t("Mitarbeiter", "Staff member", "فرد طاقم"),
        "termWorkers": _t("Personal", "Staff", "الطاقم"),
        "termSite": _t("Hub / Depot", "Hub / depot", "مركز / مستودع"),
        "termGate": _t("Tor / Rampe", "Gate / dock", "بوابة / رصيف"),
        "sectorBanner": _t(
            "Fachsprache: Logistik — Begriffe folgen dem Betriebssektor.",
            "Terminology: Logistics — labels follow the operating sector.",
            "المصطلحات: اللوجستيات — تتغير حسب القطاع التشغيلي.",
        ),
        **_admin_access_pack(
            late=_t("Verspätete Tor-Check-ins", "Late gate check-ins", "تسجيلات بوابة متأخرة"),
            checkins=_t("Tor-Events heute", "Gate events today", "أحداث البوابة اليوم"),
            recent=_t("Letzte Tor-Buchungen", "Recent gate bookings", "آخر تسجيلات البوابة"),
            outside=_t("Außerhalb Schicht", "Outside shift", "خارج الوردية"),
            on_site=_t("Im Hub", "At hub", "في المركز"),
            attendance_filter=_t("Tor-Events", "Gate events", "أحداث البوابة"),
            workers_title=_t("Personal", "Staff", "الطاقم"),
            access_title=_t("Tor-Events & Anwesenheit", "Gate events & attendance", "أحداث البوابة والحضور"),
            access_desc=_t(
                "Check-ins, Verspätungen und Rampen im Depot.",
                "Check-ins, lateness and docks at the depot.",
                "تسجيل الدخول والتأخر والأرصفة في المستودع.",
            ),
        ),
    },
    "security": {
        "overviewOnSite": _t("Jetzt im Einsatz", "On assignment now", "في المهمة الآن"),
        "overviewOnSiteKpi": _t("im Einsatz", "on assignment", "في المهمة"),
        "overviewActiveWorkers": _t("Aktive Einsatzkräfte", "Active officers", "عناصر نشطة"),
        "toolsGeofence": _t("Geofence — Objekte", "Geofence — sites", "Geofence — المواقع"),
        "deploymentLocationPh": _t("z. B. Objekt Mitte, Eingang A", "e.g. Central site, entrance A", "مثال: موقع الوسط، المدخل A"),
        "toolsSitePlaceholder": _t("Objekt / Einsatzort", "Site / assignment", "موقع / مهمة"),
        "deploymentColLocation": _t("Objekt / Einsatzort", "Site / assignment", "موقع / مهمة"),
        "tabWorkers": _t("Einsatzkräfte", "Officers", "العناصر"),
        "tabAccess": _t("Kontrollpunkte", "Checkpoints", "نقاط التفتيش"),
        "tabMobile": _t("Dienst-App", "Duty app", "تطبيق الخدمة"),
        "navGroupPeople": _t("Einsatzkräfte", "Officers", "العناصر"),
        "termWorker": _t("Einsatzkraft", "Officer", "عنصر"),
        "termWorkers": _t("Einsatzkräfte", "Officers", "العناصر"),
        "termSite": _t("Objekt", "Site", "منشأة محروسة"),
        "termGate": _t("Kontrollpunkt", "Checkpoint", "نقطة تفتيش"),
        "sectorBanner": _t(
            "Fachsprache: Sicherheit — Begriffe folgen dem Betriebssektor.",
            "Terminology: Security — labels follow the operating sector.",
            "المصطلحات: الأمن — تتغير حسب القطاع التشغيلي.",
        ),
        **_admin_access_pack(
            late=_t("Verspätete Antritte heute", "Late starts today", "بدايات متأخرة اليوم"),
            checkins=_t("Antritte heute", "Check-ins today", "تسجيلات اليوم"),
            recent=_t("Letzte Kontrollpunkt-Buchungen", "Recent checkpoint bookings", "آخر تسجيلات نقطة التفتيش"),
            outside=_t("Außerhalb Dienstzeit", "Outside duty hours", "خارج وقت الخدمة"),
            on_site=_t("Im Einsatz", "On assignment", "في المهمة"),
            attendance_filter=_t("Dienst / Anwesenheit", "Duty / attendance", "الخدمة / الحضور"),
            workers_title=_t("Einsatzkräfte", "Officers", "العناصر"),
            access_title=_t("Kontrollpunkte & Dienst", "Checkpoints & duty", "نقاط التفتيش والخدمة"),
            access_desc=_t(
                "Antritte, Verspätungen und Kontrollpunkte am Objekt.",
                "Check-ins, lateness and checkpoints on site.",
                "التسجيل والتأخر ونقاط التفتيش في المنشأة.",
            ),
        ),
    },
    "public_sector": {
        "overviewOnSite": _t("Jetzt am Standort", "At facility now", "في المنشأة الآن"),
        "overviewOnSiteKpi": _t("am Standort", "at facility", "في المنشأة"),
        "overviewActiveWorkers": _t("Aktive Mitarbeitende", "Active staff", "موظفون نشطون"),
        "toolsGeofence": _t("Geofence — Standorte", "Geofence — facilities", "Geofence — المنشآت"),
        "deploymentLocationPh": _t("z. B. Verwaltungsgebäude, Hauptstraße 1", "e.g. Admin building, Main St 1", "مثال: مبنى الإدارة"),
        "toolsSitePlaceholder": _t("Standort / Gebäude", "Facility", "منشأة / مبنى"),
        "deploymentColLocation": _t("Standort / Gebäude", "Facility", "منشأة / مبنى"),
        "tabWorkers": _t("Mitarbeitende", "Staff", "الموظفون"),
        "tabAccess": _t("Zutrittsprotokoll", "Access log", "سجل الدخول"),
        "tabMobile": _t("Mitarbeiter-App", "Staff app", "تطبيق الموظفين"),
        "navGroupPeople": _t("Personal", "Staff", "الموظفون"),
        "termWorker": _t("Mitarbeitende/r", "Staff member", "موظف"),
        "termWorkers": _t("Mitarbeitende", "Staff", "الموظفون"),
        "termSite": _t("Standort", "Facility", "منشأة"),
        "termGate": _t("Eingang", "Entrance", "مدخل"),
        "sectorBanner": _t(
            "Fachsprache: Öffentlicher Sektor — Begriffe folgen dem Betriebssektor.",
            "Terminology: Public sector — labels follow the operating sector.",
            "المصطلحات: القطاع العام — تتغير حسب القطاع التشغيلي.",
        ),
        **_admin_access_pack(
            late=_t("Verspätete Anmeldungen heute", "Late sign-ins today", "تسجيلات متأخرة اليوم"),
            checkins=_t("Anmeldungen heute", "Sign-ins today", "تسجيلات اليوم"),
            recent=_t("Letzte Zutritte", "Recent access", "آخر عمليات الدخول"),
            outside=_t("Außerhalb Dienstzeit", "Outside service hours", "خارج وقت الخدمة"),
            on_site=_t("Am Standort", "At facility", "في المنشأة"),
            attendance_filter=_t("Zutritt", "Access", "الدخول"),
            workers_title=_t("Mitarbeitende", "Staff", "الموظفون"),
            access_title=_t("Zutrittsprotokoll", "Access log", "سجل الدخول"),
            access_desc=_t(
                "Anmeldungen, Verspätungen und Eingänge am Standort.",
                "Sign-ins, lateness and entrances at the facility.",
                "التسجيل والتأخر والمداخل في المنشأة.",
            ),
        ),
    },
    "government": {
        "overviewOnSite": _t("Jetzt in der Dienststelle", "At office now", "في الدائرة الآن"),
        "overviewOnSiteKpi": _t("in Dienststelle", "at office", "في الدائرة"),
        "overviewActiveWorkers": _t("Aktive Berechtigte", "Active authorizees", "مصرّح لهم نشطون"),
        "toolsGeofence": _t("Geofence — Liegenschaften", "Geofence — premises", "Geofence — المباني"),
        "deploymentLocationPh": _t("z. B. Dienststelle Mitte, Raum 204", "e.g. Central office, room 204", "مثال: الدائرة المركزية"),
        "toolsSitePlaceholder": _t("Standort / Dienststelle", "Office / site", "موقع / دائرة"),
        "deploymentColLocation": _t("Standort / Dienststelle", "Office / site", "موقع / دائرة"),
        "tabWorkers": _t("Berechtigte", "Authorized persons", "المصرّح لهم"),
        "tabAccess": _t("Zutrittskontrolle", "Access control", "التحكم بالدخول"),
        "tabMobile": _t("Dienst-App", "Official app", "تطبيق الخدمة"),
        "navGroupPeople": _t("Berechtigte", "Authorizees", "المصرّح لهم"),
        "termWorker": _t("Berechtigter", "Authorizee", "مصرّح له"),
        "termWorkers": _t("Berechtigte", "Authorizees", "المصرّح لهم"),
        "termSite": _t("Dienststelle", "Office", "دائرة"),
        "termGate": _t("Zugangskontrolle", "Access point", "نقطة دخول"),
        "sectorBanner": _t(
            "Fachsprache: Behörden — Begriffe folgen dem Betriebssektor.",
            "Terminology: Government — labels follow the operating sector.",
            "المصطلحات: الجهات الحكومية — تتغير حسب القطاع التشغيلي.",
        ),
        **_admin_access_pack(
            late=_t("Verspätete Anmeldungen heute", "Late sign-ins today", "تسجيلات متأخرة اليوم"),
            checkins=_t("Anmeldungen heute", "Sign-ins today", "تسجيلات اليوم"),
            recent=_t("Letzte Zutritte", "Recent access", "آخر عمليات الدخول"),
            outside=_t("Außerhalb Dienstzeit", "Outside office hours", "خارج وقت الدوام"),
            on_site=_t("In der Dienststelle", "At office", "في الدائرة"),
            attendance_filter=_t("Zutritt", "Access", "الدخول"),
            workers_title=_t("Berechtigte", "Authorized persons", "المصرّح لهم"),
            access_title=_t("Zutrittskontrolle", "Access control", "التحكم بالدخول"),
            access_desc=_t(
                "Anmeldungen, Verspätungen und Zugangspunkte in der Dienststelle.",
                "Sign-ins, lateness and access points at the office.",
                "التسجيل والتأخر ونقاط الدخول في الدائرة.",
            ),
        ),
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


def _worker_attendance_msgs(site_de: str, site_en: str, site_ar: str) -> dict[str, dict[str, str]]:
    """Worker PWA + GPS attendance copy per workplace type."""
    return {
        "proximityNotScheduledToday": _t(
            f"Heute frei laut Einsatzplan – keine automatische Anmeldung ({site_de}).",
            f"Free day per plan – no automatic sign-in ({site_en}).",
            f"يوم حر – لا تسجيل تلقائي ({site_ar}).",
        ),
        "proximityOnLeave": _t(
            "Heute genehmigter Urlaub – keine automatische Anmeldung.",
            "Approved leave today – no automatic sign-in.",
            "إجازة معتمدة اليوم – لا تسجيل تلقائي.",
        ),
        "proximityOutsideWorkHours": _t(
            "Automatische Anmeldung nur während der geplanten Schichtzeit.",
            "Automatic sign-in only during scheduled shift hours.",
            "التسجيل التلقائي فقط خلال وقت الوردية المحدد.",
        ),
        "offlineLoginOnSiteOnly": _t(
            f"Offline-Login nur {site_de} möglich. Aktuell ca. {{meters}} m entfernt.",
            f"Offline login only {site_en}. Currently about {{meters}} m away.",
            f"تسجيل دون اتصال فقط {site_ar}. المسافة حوالي {{meters}} م.",
        ),
        "geolocationHint": _t(
            f"Standort optional — {site_de} wird die Anwesenheit automatisch erfasst",
            f"Location optional — presence is captured automatically at the {site_en}",
            f"الموقع اختياري — يُسجَّل الحضور تلقائياً في {site_ar}",
        ),
        "geolocationRequired": _t(
            f"Standortfreigabe für automatische Erfassung {site_de} (Login auch ohne GPS möglich).",
            f"Location permission for automatic capture at {site_en} (login possible without GPS).",
            f"إذن الموقع للتسجيل التلقائي في {site_ar} (يمكن الدخول بدون GPS).",
        ),
        "attendanceNotScheduledToday": _t(
            f"Heute frei laut Einsatzplan – keine automatische Anmeldung ({site_de}).",
            f"Free day per plan – no automatic sign-in ({site_en}).",
            f"يوم حر – لا تسجيل تلقائي ({site_ar}).",
        ),
        "attendanceOnLeave": _t(
            "Heute genehmigter Urlaub – keine automatische Anmeldung.",
            "Approved leave today – no automatic sign-in.",
            "إجازة معتمدة اليوم – لا تسجيل تلقائي.",
        ),
        "attendanceOutsideShift": _t(
            "Automatische Anmeldung nur während der geplanten Schichtzeit.",
            "Automatic sign-in only during scheduled shift hours.",
            "التسجيل التلقائي فقط خلال وقت الوردية المحدد.",
        ),
        "attendanceShiftTimesRequired": _t(
            "Einsatz ohne Schichtzeit im Plan – bitte Arbeitgeber informieren. Keine automatische Anmeldung.",
            "Assignment without shift times in the plan – contact your employer. No automatic sign-in.",
            "تكليف بدون أوقات وردية في الخطة – تواصل مع صاحب العمل. لا تسجيل تلقائي.",
        ),
        "attendanceOutsideWorkHours": _t(
            "Automatische Anmeldung nur während der Arbeitszeit.",
            "Automatic sign-in only during work hours.",
            "التسجيل التلقائي فقط خلال ساعات العمل.",
        ),
        "attendanceDeploymentDeclined": _t(
            "Einsatztag wurde abgelehnt – keine automatische Anmeldung.",
            "Assignment declined – no automatic sign-in.",
            "تم رفض يوم التكليف – لا تسجيل تلقائي.",
        ),
        "attendanceNotWorkday": _t(
            "Heute kein Arbeitstag.",
            "Not a work day today.",
            "ليس يوم عمل اليوم.",
        ),
    }


WORKER_SECTOR_TERM_KEYS: dict[str, dict[str, dict[str, str]]] = {
    "construction": {
        **_worker_attendance_msgs("am Standort / Baustelle", "on site", "في الموقع"),
        "fieldSite": _t("Standort / Baustelle", "Site", "الموقع"),
        "nextStepConstructionTitle": _t("Standort zuerst", "Site first", "الموقع أولًا"),
        "nextStepConstructionCopy": _t(
            "Direkt auf den Standort {site} und die wichtigsten Standortinfos zugreifen.",
            "Go straight to {site} and the most important site details.",
            "انتقل مباشرة إلى {site} وأهم معلومات الموقع.",
        ),
        "smartHubFocusConstruction": _t("Baustellenfluss", "Site workflow", "سير الموقع"),
        "companyModeConstructionLead": _t(
            "Baustellenfokus mit schneller Zutrittsabwicklung.",
            "Site-focused access workflow.",
            "تركيز على الموقع مع دخول سريع.",
        ),
        "companyModeConstructionItem1": _t(
            "Schneller Zugang für Standort-Check-in",
            "Fast site check-in",
            "تسجيل دخول سريع في الموقع",
        ),
    },
    "manufacturing": {
        **_worker_attendance_msgs("im Werk", "in the plant", "في المنشأة"),
        "fieldSite": _t("Werk / Halle", "Plant / hall", "المصنع / القاعة"),
        "nextStepConstructionTitle": _t("Werk zuerst", "Plant first", "المصنع أولًا"),
        "nextStepConstructionCopy": _t(
            "Direkt ins Werk {site} und zu den wichtigsten Schichtinfos.",
            "Go straight to plant {site} and key shift details.",
            "انتقل مباشرة إلى {site} وأهم معلومات الوردية.",
        ),
        "smartHubFocusConstruction": _t("Werkfluss", "Plant workflow", "سير المصنع"),
        "companyModeConstructionLead": _t(
            "Werkfokus mit Schicht- und Zutrittssteuerung.",
            "Plant focus with shift and access control.",
            "تركيز على المصنع مع التحكم بالورديات.",
        ),
        "companyModeConstructionItem1": _t(
            "Schneller Zugang für Werk-Check-in",
            "Fast plant check-in",
            "تسجيل دخول سريع في المصنع",
        ),
    },
    "aviation": {
        **_worker_attendance_msgs("im Terminal", "in the terminal", "في المبنى"),
        "fieldSite": _t("Terminal / Zone", "Terminal / zone", "المبنى / المنطقة"),
        "nextStepConstructionTitle": _t("Terminal zuerst", "Terminal first", "المبنى أولًا"),
        "nextStepConstructionCopy": _t(
            "Direkt ins Terminal {site} und zu den wichtigsten Zutrittsinfos.",
            "Go straight to terminal {site} and key access details.",
            "انتقل مباشرة إلى {site} وأهم معلومات الدخول.",
        ),
        "smartHubFocusConstruction": _t("Terminalfluss", "Terminal workflow", "سير المبنى"),
        "companyModeConstructionLead": _t(
            "Terminal-Zutritt mit klaren Zonen und Berechtigungen.",
            "Terminal access with clear zones and permissions.",
            "دخول المبنى مع مناطق وصلاحيات واضحة.",
        ),
        "companyModeConstructionItem1": _t(
            "Schneller Zugang für Terminal-Check-in",
            "Fast terminal check-in",
            "تسجيل دخول سريع في المبنى",
        ),
    },
    "logistics": {
        **_worker_attendance_msgs("im Hub / Depot", "at the hub", "في المركز"),
        "fieldSite": _t("Depot / Hub", "Depot / hub", "المستودع / المركز"),
        "nextStepConstructionTitle": _t("Hub zuerst", "Hub first", "المركز أولًا"),
        "nextStepConstructionCopy": _t(
            "Direkt zum Hub {site} und zu den wichtigsten Einsatzinfos.",
            "Go straight to hub {site} and key assignment details.",
            "انتقل مباشرة إلى {site} وأهم معلومات التكليف.",
        ),
        "smartHubFocusConstruction": _t("Hub-Fluss", "Hub workflow", "سير المركز"),
        "companyModeConstructionLead": _t(
            "Logistikfokus mit Tor- und Schichtsteuerung.",
            "Logistics focus with gate and shift control.",
            "تركيز لوجستي مع التحكم بالبوابات.",
        ),
        "companyModeConstructionItem1": _t(
            "Schneller Zugang für Hub-Check-in",
            "Fast hub check-in",
            "تسجيل دخول سريع في المركز",
        ),
    },
    "security": {
        **_worker_attendance_msgs("am Einsatzort", "on assignment", "في موقع المهمة"),
        "fieldSite": _t("Objekt / Einsatzort", "Site / assignment", "الموقع / المهمة"),
        "nextStepConstructionTitle": _t("Einsatzort zuerst", "Assignment first", "موقع المهمة أولًا"),
        "nextStepConstructionCopy": _t(
            "Direkt zum Einsatzort {site} und zu den wichtigsten Objektinfos.",
            "Go straight to assignment {site} and key site details.",
            "انتقل مباشرة إلى {site} وأهم معلومات الموقع.",
        ),
        "smartHubFocusConstruction": _t("Einsatzfluss", "Assignment workflow", "سير المهمة"),
        "companyModeConstructionLead": _t(
            "Objektschutz mit klaren Einsatz- und Kontrollpunkten.",
            "Security operations with clear assignment checkpoints.",
            "حماية المواقع مع نقاط تفتيش واضحة.",
        ),
        "companyModeConstructionItem1": _t(
            "Schneller Zugang am Einsatzort",
            "Fast on-assignment check-in",
            "تسجيل دخول سريع في موقع المهمة",
        ),
    },
    "public_sector": {
        **_worker_attendance_msgs("am Standort / Gebäude", "at the facility", "في المنشأة"),
        "fieldSite": _t("Standort / Gebäude", "Facility", "المنشأة / المبنى"),
        "nextStepConstructionTitle": _t("Standort zuerst", "Facility first", "المنشأة أولًا"),
        "nextStepConstructionCopy": _t(
            "Direkt zum Standort {site} und zu den wichtigsten Infos.",
            "Go straight to facility {site} and key details.",
            "انتقل مباشرة إلى {site} وأهم المعلومات.",
        ),
        "smartHubFocusConstruction": _t("Standortfluss", "Facility workflow", "سير المنشأة"),
        "companyModeConstructionLead": _t(
            "Standortfokus mit nachvollziehbarem Zutrittsprotokoll.",
            "Facility focus with auditable access logging.",
            "تركيز على المنشأة مع سجل دخول قابل للتدقيق.",
        ),
        "companyModeConstructionItem1": _t(
            "Schneller Zugang am Standort",
            "Fast facility check-in",
            "تسجيل دخول سريع في المنشأة",
        ),
    },
    "government": {
        **_worker_attendance_msgs("in der Dienststelle", "at the office", "في الدائرة"),
        "fieldSite": _t("Standort / Dienststelle", "Office / site", "الموقع / الدائرة"),
        "nextStepConstructionTitle": _t("Dienststelle zuerst", "Office first", "الدائرة أولًا"),
        "nextStepConstructionCopy": _t(
            "Direkt zur Dienststelle {site} und zu den wichtigsten Zutrittsinfos.",
            "Go straight to office {site} and key access details.",
            "انتقل مباشرة إلى {site} وأهم معلومات الدخول.",
        ),
        "smartHubFocusConstruction": _t("Dienststellenfluss", "Office workflow", "سير الدائرة"),
        "companyModeConstructionLead": _t(
            "Enterprise-Zutritt mit Compliance und Audit-Trail.",
            "Enterprise access with compliance and audit trail.",
            "دخول مؤسسي مع امتثال وسجل تدقيق.",
        ),
        "companyModeConstructionItem1": _t(
            "Schneller Zugang in der Dienststelle",
            "Fast office check-in",
            "تسجيل دخول سريع في الدائرة",
        ),
    },
}


def resolve_company_operating_sector(db, company_id: str) -> str:
    row = db.execute(
        "SELECT operating_sector, branding_preset FROM companies WHERE id = ? LIMIT 1",
        (str(company_id),),
    ).fetchone()
    if not row:
        return DEFAULT_SECTOR
    keys = row.keys() if hasattr(row, "keys") else []
    if "operating_sector" in keys and row["operating_sector"]:
        return normalize_operating_sector(row["operating_sector"])
    preset = str(row["branding_preset"] or "").lower()
    if preset == "industry":
        return "manufacturing"
    return DEFAULT_SECTOR


def sector_terms_for_company(db, company_id: str, *, lang: str = "de") -> dict[str, str]:
    """Resolved terminology pack for one tenant (safe for AI/PDF/UI injection)."""
    try:
        sector = resolve_company_operating_sector(db, company_id)
        cfg = sector_config(sector, lang=lang)
        terms = dict(cfg.get("terms") or {})
        terms["_sector"] = str(cfg.get("sector") or sector)
        terms["_sectorLabel"] = str(cfg.get("label") or "")
        return terms
    except Exception:
        cfg = sector_config(DEFAULT_SECTOR, lang=lang)
        terms = dict(cfg.get("terms") or {})
        terms["_sector"] = DEFAULT_SECTOR
        terms["_sectorLabel"] = str(cfg.get("label") or "")
        return terms


def sector_noun(terms: dict[str, str] | None, key: str, fallback: str) -> str:
    value = str((terms or {}).get(key) or "").strip()
    return value or fallback


def sector_attendance_message(
    db,
    company_id: str,
    message_key: str,
    *,
    lang: str = "de",
) -> str:
    cfg = sector_config(resolve_company_operating_sector(db, company_id), lang=lang)
    terms = cfg.get("terms") or {}
    text = str(terms.get(message_key) or "").strip()
    if text:
        return text
    neutral = sector_config("public_sector", lang=lang).get("terms") or {}
    return str(neutral.get(message_key) or "").strip()


def sector_config(sector_id: str, *, lang: str = "de") -> dict[str, Any]:
    sector_id = normalize_operating_sector(sector_id)
    lang = str(lang or "de").strip().lower()[:2] or "de"
    meta = SECTOR_META[sector_id]
    terms_raw = SECTOR_TERM_KEYS.get(sector_id, {})
    admin_terms = ADMIN_V2_TERM_KEYS.get(sector_id, ADMIN_V2_TERM_KEYS["construction"])
    worker_terms = WORKER_SECTOR_TERM_KEYS.get(sector_id, WORKER_SECTOR_TERM_KEYS["construction"])
    merged_terms = {**terms_raw, **admin_terms, **worker_terms}
    terms = {k: (v.get(lang) or v.get("en") or v.get("de") or "") for k, v in merged_terms.items()}
    label = meta["labels"].get(lang) or meta["labels"].get("en") or meta["labels"]["de"]
    product_line = meta["productLine"].get(lang) or meta["productLine"].get("en") or meta["productLine"]["de"]
    return {
        "sector": sector_id,
        "label": label,
        "productLine": product_line,
        "terms": terms,
        "template": OPERATION_TEMPLATES.get(sector_id, {}),
        "availableSectors": [
            {
                "id": sid,
                "label": SECTOR_META[sid]["labels"].get(lang) or SECTOR_META[sid]["labels"].get("en") or SECTOR_META[sid]["labels"]["de"],
            }
            for sid in sorted(VALID_SECTORS)
        ],
    }


def all_sectors_public() -> list[dict[str, str]]:
    return [
        {"id": sid, "labels": SECTOR_META[sid]["labels"], "productLine": SECTOR_META[sid]["productLine"]}
        for sid in sorted(VALID_SECTORS)
    ]
