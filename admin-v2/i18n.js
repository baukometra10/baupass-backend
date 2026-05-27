const STRINGS = {
  de: {
    "app.title": "BauPass Admin",
    "app.subtitle": "Betrieb — Anwesenheit, Worker-App, Plattform",
    "login.user": "Benutzername",
    "login.pass": "Passwort",
    "login.scope": "Kontotyp",
    "login.btn": "Anmelden",
    "tab.overview": "Übersicht",
    "tab.enterprise": "🏛 Enterprise",
    "tab.workers": "Mitarbeiter",
    "tab.access": "Anwesenheit",
    "tab.mobile": "Worker-App",
    "tab.operations": "Betrieb",
    "tab.tools": "Geofence · Auto · Integration",
    "tab.platform": "Plattform",
    "tools.geofence": "Geofence — Baustellen",
    "tools.mapHint": "Karte anklicken = Koordinaten setzen",
    "tools.addZone": "Zone hinzufügen",
    "tools.automation": "Automatisierung",
    "tools.integrations": "Integrationen",
    "tools.connect": "Verbinden",
    "tools.sync": "Sync",
    "lang": "Sprache",
  },
  en: {
    "app.title": "BauPass Admin",
    "app.subtitle": "Operations — attendance, worker app, platform",
    "login.user": "Username",
    "login.pass": "Password",
    "login.scope": "Account type",
    "login.btn": "Sign in",
    "tab.overview": "Overview",
    "tab.enterprise": "🏛 Enterprise",
    "tab.workers": "Workers",
    "tab.access": "Attendance",
    "tab.mobile": "Worker app",
    "tab.operations": "Operations",
    "tab.tools": "Geofence · Auto · Integrations",
    "tab.platform": "Platform",
    "tools.geofence": "Geofence — sites",
    "tools.mapHint": "Click map to set coordinates",
    "tools.addZone": "Add zone",
    "tools.automation": "Automation",
    "tools.integrations": "Integrations",
    "tools.connect": "Connect",
    "tools.sync": "Sync",
    "lang": "Language",
  },
  ar: {
    "app.title": "BauPass Admin",
    "app.subtitle": "لوحة التشغيل — حضور، تطبيق الموظف، والمنصة",
    "login.user": "اسم المستخدم",
    "login.pass": "كلمة المرور",
    "login.scope": "نوع الحساب",
    "login.btn": "تسجيل الدخول",
    "tab.overview": "نظرة عامة",
    "tab.enterprise": "🏛 المؤسسة",
    "tab.workers": "الموظفون",
    "tab.access": "الحضور",
    "tab.mobile": "تطبيق الموظف",
    "tab.operations": "العمليات",
    "tab.tools": "Geofence · أتمتة · تكامل",
    "tab.platform": "المنصة",
    "tools.geofence": "Geofence — مناطق الحضور",
    "tools.mapHint": "انقر الخريطة لتعيين الإحداثيات",
    "tools.addZone": "إضافة منطقة",
    "tools.automation": "أتمتة",
    "tools.integrations": "تكاملات",
    "tools.connect": "ربط",
    "tools.sync": "مزامنة",
    "lang": "اللغة",
  },
};

const LANG_KEY = "baupass-admin-v2-lang";

export function getLang() {
  return localStorage.getItem(LANG_KEY) || "de";
}

export function setLang(code) {
  localStorage.setItem(LANG_KEY, code);
  applyI18n();
}

export function t(key) {
  const lang = getLang();
  return STRINGS[lang]?.[key] || STRINGS.de[key] || STRINGS.en[key] || key;
}

export function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key) el.textContent = t(key);
  });
  document.documentElement.lang = getLang() === "ar" ? "ar" : getLang();
  document.documentElement.dir = getLang() === "ar" ? "rtl" : "ltr";
}
