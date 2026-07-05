/** Live Ops Map — 8 languages. */
window.OpsLiveMapI18n = {
  de: {
    title: "Live Ops Karte",
    loading: "Laden…",
    refresh: "Aktualisieren",
    navCommand: "Command Center",
    navAi: "KI",
    navAdmin: "Betrieb",
    legendOnSite: "Auf Baustelle",
    legendGeofence: "Geofence",
    legendGate: "Gate (heute)",
    statusLine: "{onSite} on-site · {zones} Zonen · {security} Security",
    sidebarTitle: "Auf Baustelle",
    nobodyCheckedIn: "Niemand eingecheckt",
    selectCompany: "Firma wählen (Superadmin)",
    authRequired: "Anmeldung erforderlich",
    companyPlaceholder: "— Firma —",
    uiLang: "Sprache",
  },
  en: {
    title: "Live ops map",
    loading: "Loading…",
    refresh: "Refresh",
    navCommand: "Command center",
    navAi: "AI",
    navAdmin: "Operations",
    legendOnSite: "On site",
    legendGeofence: "Geofence",
    legendGate: "Gate (today)",
    statusLine: "{onSite} on-site · {zones} zones · {security} security",
    sidebarTitle: "On site",
    nobodyCheckedIn: "Nobody checked in",
    selectCompany: "Select company (superadmin)",
    authRequired: "Sign-in required",
    companyPlaceholder: "— Company —",
    uiLang: "Language",
  },
  ar: {
    title: "خريطة العمليات المباشرة",
    loading: "جارٍ التحميل…",
    refresh: "تحديث",
    navCommand: "مركز القيادة",
    navAi: "ذكاء",
    navAdmin: "التشغيل",
    legendOnSite: "على الموقع",
    legendGeofence: "سياج جغرافي",
    legendGate: "بوابة (اليوم)",
    statusLine: "{onSite} على الموقع · {zones} مناطق · {security} أمن",
    sidebarTitle: "على الموقع",
    nobodyCheckedIn: "لا أحد مسجل",
    selectCompany: "اختر الشركة (superadmin)",
    authRequired: "تسجيل الدخول مطلوب",
    companyPlaceholder: "— الشركة —",
    uiLang: "اللغة",
  },
  tr: {
    title: "Canli ops haritasi",
    loading: "Yukleniyor…",
    refresh: "Yenile",
    navCommand: "Komuta merkezi",
    navAi: "AI",
    navAdmin: "Operasyon",
    legendOnSite: "Sahada",
    legendGeofence: "Geofence",
    legendGate: "Gecis (bugun)",
    statusLine: "{onSite} sahada · {zones} bolge · {security} guvenlik",
    sidebarTitle: "Sahada",
    nobodyCheckedIn: "Kimse giris yapmedi",
    selectCompany: "Firma sec (superadmin)",
    authRequired: "Giris gerekli",
    companyPlaceholder: "— Firma —",
    uiLang: "Dil",
  },
  fr: {
    title: "Carte ops live",
    loading: "Chargement…",
    refresh: "Actualiser",
    navCommand: "Centre de commande",
    navAi: "IA",
    navAdmin: "Exploitation",
    legendOnSite: "Sur site",
    legendGeofence: "Geofence",
    legendGate: "Porte (aujourd'hui)",
    statusLine: "{onSite} sur site · {zones} zones · {security} securite",
    sidebarTitle: "Sur site",
    nobodyCheckedIn: "Personne enregistre",
    selectCompany: "Choisir entreprise (superadmin)",
    authRequired: "Connexion requise",
    companyPlaceholder: "— Entreprise —",
    uiLang: "Langue",
  },
  es: {
    title: "Mapa ops en vivo",
    loading: "Cargando…",
    refresh: "Actualizar",
    navCommand: "Centro de mando",
    navAi: "IA",
    navAdmin: "Operaciones",
    legendOnSite: "En obra",
    legendGeofence: "Geocerca",
    legendGate: "Puerta (hoy)",
    statusLine: "{onSite} en obra · {zones} zonas · {security} seguridad",
    sidebarTitle: "En obra",
    nobodyCheckedIn: "Nadie registrado",
    selectCompany: "Elegir empresa (superadmin)",
    authRequired: "Inicio de sesion requerido",
    companyPlaceholder: "— Empresa —",
    uiLang: "Idioma",
  },
  it: {
    title: "Mappa ops live",
    loading: "Caricamento…",
    refresh: "Aggiorna",
    navCommand: "Centro di comando",
    navAi: "IA",
    navAdmin: "Operazioni",
    legendOnSite: "In cantiere",
    legendGeofence: "Geofence",
    legendGate: "Gate (oggi)",
    statusLine: "{onSite} in cantiere · {zones} zone · {security} sicurezza",
    sidebarTitle: "In cantiere",
    nobodyCheckedIn: "Nessuno registrato",
    selectCompany: "Seleziona azienda (superadmin)",
    authRequired: "Accesso richiesto",
    companyPlaceholder: "— Azienda —",
    uiLang: "Lingua",
  },
  pl: {
    title: "Mapa ops na zywo",
    loading: "Ladowanie…",
    refresh: "Odswiez",
    navCommand: "Centrum dowodzenia",
    navAi: "AI",
    navAdmin: "Operacje",
    legendOnSite: "Na budowie",
    legendGeofence: "Geofence",
    legendGate: "Brama (dzis)",
    statusLine: "{onSite} na budowie · {zones} stref · {security} bezpieczenstwo",
    sidebarTitle: "Na budowie",
    nobodyCheckedIn: "Nikt nie zalogowany",
    selectCompany: "Wybierz firme (superadmin)",
    authRequired: "Wymagane logowanie",
    companyPlaceholder: "— Firma —",
    uiLang: "Jezyk",
  },
};

window.getOpsMapLang = function getOpsMapLang() {
  const langs = ["de", "en", "ar", "tr", "fr", "es", "it", "pl"];
  const code = (
    localStorage.getItem("baupass-admin-v2-lang")
    || localStorage.getItem("baupass-ui-lang")
    || "de"
  ).slice(0, 2);
  return langs.includes(code) ? code : "de";
};

window.opsMapT = function opsMapT(key, vars = {}) {
  const lang = window.getOpsMapLang();
  let text = window.OpsLiveMapI18n[lang]?.[key] || window.OpsLiveMapI18n.en?.[key] || key;
  for (const [k, v] of Object.entries(vars)) {
    text = text.replaceAll(`{${k}}`, String(v ?? ""));
  }
  return text;
};

window.applyOpsMapI18n = function applyOpsMapI18n() {
  const lang = window.getOpsMapLang();
  document.documentElement.lang = lang === "ar" ? "ar" : lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  document.title = `SUPPIX — ${window.opsMapT("title")}`;
  const titleEl = document.getElementById("opsMapTitle");
  if (titleEl) titleEl.textContent = window.opsMapT("title");
  const refreshBtn = document.getElementById("refreshBtn");
  if (refreshBtn) refreshBtn.textContent = window.opsMapT("refresh");
  document.querySelectorAll("[data-omapi18n]").forEach((el) => {
    const key = el.getAttribute("data-omapi18n");
    if (!key) return;
    el.textContent = window.opsMapT(key);
  });
  const sel = document.getElementById("opsMapLangSelect");
  if (sel) {
    sel.value = lang;
    sel.setAttribute("aria-label", window.opsMapT("uiLang"));
  }
};

window.initOpsMapLangSync = function initOpsMapLangSync() {
  window.applyOpsMapI18n();
  const sel = document.getElementById("opsMapLangSelect");
  if (sel && !sel.dataset.bound) {
    sel.dataset.bound = "1";
    sel.addEventListener("change", () => {
      localStorage.setItem("baupass-ui-lang", sel.value);
      localStorage.setItem("baupass-admin-v2-lang", sel.value);
      window.applyOpsMapI18n();
      window.dispatchEvent(new CustomEvent("baupass-admin-lang", { detail: { lang: sel.value } }));
      if (typeof window.__opsMapReload === "function") window.__opsMapReload();
    });
  }
  if (!window.__opsMapLangBound) {
    window.__opsMapLangBound = true;
    window.addEventListener("storage", (e) => {
      if ((e.key === "baupass-ui-lang" || e.key === "baupass-admin-v2-lang") && e.newValue) {
        window.applyOpsMapI18n();
        if (typeof window.__opsMapReload === "function") window.__opsMapReload();
      }
    });
    window.addEventListener("baupass-admin-lang", () => window.applyOpsMapI18n());
  }
};
