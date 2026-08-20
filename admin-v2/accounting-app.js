/**
 * Lohn-Zentrale hub — mailbox UI + 8-language i18n.
 * Payslip studio is hosted in-page via app.js accounting-host boot.
 */
const WP = window.WorkPassStorage;
const TOKEN_KEY = WP?.KEYS?.ADMIN_TOKEN || "workpass-admin-token";
const USER_KEY = WP?.KEYS?.ADMIN_USER || "workpass-admin-user";
const COMPANY_KEY = WP?.KEYS?.ADMIN_COMPANY || "workpass-admin-company";
const CONTROL_TOKEN_KEY = WP?.KEYS?.SESSION_TOKEN || "workpass-session-token";
const LANG_KEY = "workpass-ui-lang";

const ACC_I18N = {
  de: {
    boot: "Lade Lohn-Zentrale…",
    title: "Lohn-Zentrale",
    sub: "Buchhaltung, Anfragen und Lohnabrechnungen — alles an einem Ort.",
    lang: "Sprache",
    backBetrieb: "← Betrieb",
    refresh: "Aktualisieren",
    openExternal: "Buchhaltung öffnen",
    backBoxes: "← Postfächer",
    boxProcessTitle: "Zu bearbeiten",
    boxProcessDesc: "Anfragen und fehlende Daten aus der Buchhaltung",
    boxProcessMeta: "Nachrichten · Stammdaten · Hinweise",
    boxConfirmTitle: "Bestätigung",
    boxConfirmDesc: "Perioden-Übergaben freigeben oder ablehnen",
    boxConfirmMeta: "Freigaben von der Plattform",
    boxStudioTitle: "Studio",
    boxStudioDesc: "Lohnabrechnungen prüfen und an die App senden",
    boxStudioMeta: "PDF-Freigabe · Archiv",
    openStudio: "Studio öffnen",
    studioReadyTitle: "Studio bereit",
    studioReadyBody: "Öffne das Studio direkt auf dieser Seite — ohne Extra-Fenster.",
    emptyProcessTitle: "Alles erledigt",
    emptyProcessBody: "Keine offenen Anfragen aus der Buchhaltung.",
    emptyConfirmTitle: "Keine Bestätigungen offen",
    emptyConfirmBody: "Perioden-Anfragen erscheinen hier, sobald die Buchhaltung sie anfordert.",
    payslipPendingTitle: "Lohnabrechnungen zur Prüfung",
    payslipPendingBody: "{n} PDF(s) warten auf Prüfung und Versand.",
    openPayslips: "Jetzt prüfen & senden",
    periodTitle: "Perioden-Übergabe",
    periodBody: "Buchhaltung bittet um Daten für {period}.",
    periodConfirm: "Freigeben",
    periodReject: "Ablehnen",
    missingData: "Fehlende Stammdaten",
    openMaster: "Stammdaten öffnen",
    done: "Erledigt",
    edit: "Bearbeiten",
    selectCompany: "Bitte zuerst eine Firma in Betrieb wählen.",
    forbidden: "Keine Berechtigung für die Lohn-Zentrale.",
    loginRequired: "Bitte über Betrieb anmelden.",
    sessionExpired: "Sitzung abgelaufen — bitte neu anmelden.",
    loading: "Lade Anfragen…",
    updated: "Aktualisiert",
    externalFail: "Buchhaltung nicht erreichbar",
    studioWait: "Studio wird vorbereitet…",
    studioFail: "Studio konnte nicht geöffnet werden.",
  },
  en: {
    boot: "Loading payroll hub…",
    title: "Payroll hub",
    sub: "Accounting requests and payslips — all in one place.",
    lang: "Language",
    backBetrieb: "← Operations",
    refresh: "Refresh",
    openExternal: "Open accounting",
    backBoxes: "← Mailboxes",
    boxProcessTitle: "Needs action",
    boxProcessDesc: "Requests and missing data from accounting",
    boxProcessMeta: "Messages · master data · alerts",
    boxConfirmTitle: "Confirmation",
    boxConfirmDesc: "Approve or reject period handoffs",
    boxConfirmMeta: "Platform confirmations",
    boxStudioTitle: "Studio",
    boxStudioDesc: "Review payslips and send to the worker app",
    boxStudioMeta: "PDF approval · archive",
    openStudio: "Open studio",
    studioReadyTitle: "Studio ready",
    studioReadyBody: "Open the studio on this page — no extra window.",
    emptyProcessTitle: "All clear",
    emptyProcessBody: "No open requests from accounting.",
    emptyConfirmTitle: "No confirmations pending",
    emptyConfirmBody: "Period requests appear here when accounting asks for them.",
    payslipPendingTitle: "Payslips to review",
    payslipPendingBody: "{n} PDF(s) waiting for review and send.",
    openPayslips: "Review & send now",
    periodTitle: "Period handoff",
    periodBody: "Accounting asks for data for {period}.",
    periodConfirm: "Approve",
    periodReject: "Reject",
    missingData: "Missing master data",
    openMaster: "Open master data",
    done: "Done",
    edit: "Edit",
    selectCompany: "Please select a company in Operations first.",
    forbidden: "No permission for the payroll hub.",
    loginRequired: "Please sign in via Operations.",
    sessionExpired: "Session expired — please sign in again.",
    loading: "Loading requests…",
    updated: "Updated",
    externalFail: "Accounting unavailable",
    studioWait: "Preparing studio…",
    studioFail: "Could not open studio.",
  },
  ar: {
    boot: "جاري تحميل مركز الرواتب…",
    title: "مركز الرواتب",
    sub: "طلبات المحاسبة وكشوف الرواتب — في مكان واحد.",
    lang: "اللغة",
    backBetrieb: "← التشغيل",
    refresh: "تحديث",
    openExternal: "فتح المحاسبة",
    backBoxes: "← الصناديق",
    boxProcessTitle: "تحتاج معالجة",
    boxProcessDesc: "طلبات وبيانات ناقصة من نظام المحاسبة",
    boxProcessMeta: "رسائل · بيانات أساسية · تنبيهات",
    boxConfirmTitle: "تأكيد",
    boxConfirmDesc: "الموافقة على تسليم الفترات أو رفضها",
    boxConfirmMeta: "تأكيدات من المنصة",
    boxStudioTitle: "الاستوديو",
    boxStudioDesc: "مراجعة كشوف الرواتب وإرسالها لتطبيق الموظفين",
    boxStudioMeta: "اعتماد PDF · الأرشيف",
    openStudio: "فتح الاستوديو",
    studioReadyTitle: "الاستوديو جاهز",
    studioReadyBody: "يفتح الاستوديو داخل هذه الصفحة مباشرة.",
    emptyProcessTitle: "لا يوجد شيء معلّق",
    emptyProcessBody: "لا توجد طلبات مفتوحة من المحاسبة.",
    emptyConfirmTitle: "لا تأكيدات معلّقة",
    emptyConfirmBody: "تظهر طلبات الفترة هنا عندما تطلبها المحاسبة.",
    payslipPendingTitle: "كشوف بانتظار المراجعة",
    payslipPendingBody: "{n} ملف PDF بانتظار المراجعة والإرسال.",
    openPayslips: "مراجعة وإرسال الآن",
    periodTitle: "تسليم فترة",
    periodBody: "المحاسبة تطلب بيانات لفترة {period}.",
    periodConfirm: "موافقة",
    periodReject: "رفض",
    missingData: "بيانات ناقصة",
    openMaster: "فتح البيانات",
    done: "تم",
    edit: "تعديل",
    selectCompany: "اختر شركة أولاً من التشغيل.",
    forbidden: "لا صلاحية لمركز الرواتب.",
    loginRequired: "سجّل الدخول عبر التشغيل.",
    sessionExpired: "انتهت الجلسة — سجّل الدخول مجدداً.",
    loading: "جاري تحميل الطلبات…",
    updated: "تم التحديث",
    externalFail: "المحاسبة غير متاحة",
    studioWait: "جاري تجهيز الاستوديو…",
    studioFail: "تعذر فتح الاستوديو.",
  },
  tr: {
    boot: "Bordro merkezi yükleniyor…",
    title: "Bordro merkezi",
    sub: "Muhasebe talepleri ve bordrolar — tek yerde.",
    lang: "Dil",
    backBetrieb: "← İşletme",
    refresh: "Yenile",
    openExternal: "Muhasebeyi aç",
    backBoxes: "← Kutular",
    boxProcessTitle: "İşlem gerekli",
    boxProcessDesc: "Muhasebeden gelen talepler ve eksik veriler",
    boxProcessMeta: "Mesajlar · master data · uyarılar",
    boxConfirmTitle: "Onay",
    boxConfirmDesc: "Dönem aktarımlarını onayla veya reddet",
    boxConfirmMeta: "Platform onayları",
    boxStudioTitle: "Stüdyo",
    boxStudioDesc: "Bordroları incele ve uygulamaya gönder",
    boxStudioMeta: "PDF onayı · arşiv",
    openStudio: "Stüdyoyu aç",
    studioReadyTitle: "Stüdyo hazır",
    studioReadyBody: "Stüdyo bu sayfada açılır — ekstra pencere yok.",
    emptyProcessTitle: "Hepsi tamam",
    emptyProcessBody: "Muhasebeden açık talep yok.",
    emptyConfirmTitle: "Bekleyen onay yok",
    emptyConfirmBody: "Muhasebe istediğinde dönem talepleri burada görünür.",
    payslipPendingTitle: "İncelenecek bordrolar",
    payslipPendingBody: "{n} PDF inceleme ve gönderim bekliyor.",
    openPayslips: "Şimdi incele & gönder",
    periodTitle: "Dönem aktarımı",
    periodBody: "Muhasebe {period} için veri istiyor.",
    periodConfirm: "Onayla",
    periodReject: "Reddet",
    missingData: "Eksik master data",
    openMaster: "Master data aç",
    done: "Tamam",
    edit: "Düzenle",
    selectCompany: "Önce İşletme’de bir firma seçin.",
    forbidden: "Bordro merkezi için yetki yok.",
    loginRequired: "Lütfen İşletme üzerinden giriş yapın.",
    sessionExpired: "Oturum doldu — tekrar giriş yapın.",
    loading: "Talepler yükleniyor…",
    updated: "Güncellendi",
    externalFail: "Muhasebe kullanılamıyor",
    studioWait: "Stüdyo hazırlanıyor…",
    studioFail: "Stüdyo açılamadı.",
  },
  fr: {
    boot: "Chargement du hub paie…",
    title: "Hub paie",
    sub: "Demandes comptables et fiches de paie — au même endroit.",
    lang: "Langue",
    backBetrieb: "← Exploitation",
    refresh: "Actualiser",
    openExternal: "Ouvrir la comptabilité",
    backBoxes: "← Boîtes",
    boxProcessTitle: "À traiter",
    boxProcessDesc: "Demandes et données manquantes de la comptabilité",
    boxProcessMeta: "Messages · données · alertes",
    boxConfirmTitle: "Confirmation",
    boxConfirmDesc: "Approuver ou refuser les remises de période",
    boxConfirmMeta: "Confirmations plateforme",
    boxStudioTitle: "Studio",
    boxStudioDesc: "Vérifier les fiches et les envoyer à l’app",
    boxStudioMeta: "Validation PDF · archive",
    openStudio: "Ouvrir le studio",
    studioReadyTitle: "Studio prêt",
    studioReadyBody: "Le studio s’ouvre sur cette page — sans fenêtre extra.",
    emptyProcessTitle: "Tout est à jour",
    emptyProcessBody: "Aucune demande ouverte de la comptabilité.",
    emptyConfirmTitle: "Aucune confirmation",
    emptyConfirmBody: "Les demandes de période apparaissent ici.",
    payslipPendingTitle: "Fiches à vérifier",
    payslipPendingBody: "{n} PDF en attente de contrôle et d’envoi.",
    openPayslips: "Vérifier & envoyer",
    periodTitle: "Remise de période",
    periodBody: "La comptabilité demande des données pour {period}.",
    periodConfirm: "Approuver",
    periodReject: "Refuser",
    missingData: "Données manquantes",
    openMaster: "Ouvrir les données",
    done: "Fait",
    edit: "Modifier",
    selectCompany: "Choisissez d’abord une entreprise.",
    forbidden: "Pas d’autorisation pour le hub paie.",
    loginRequired: "Connectez-vous via Exploitation.",
    sessionExpired: "Session expirée — reconnectez-vous.",
    loading: "Chargement des demandes…",
    updated: "Mis à jour",
    externalFail: "Comptabilité indisponible",
    studioWait: "Préparation du studio…",
    studioFail: "Impossible d’ouvrir le studio.",
  },
  es: {
    boot: "Cargando centro de nómina…",
    title: "Centro de nómina",
    sub: "Solicitudes contables y nóminas — en un solo lugar.",
    lang: "Idioma",
    backBetrieb: "← Operaciones",
    refresh: "Actualizar",
    openExternal: "Abrir contabilidad",
    backBoxes: "← Buzones",
    boxProcessTitle: "Por procesar",
    boxProcessDesc: "Solicitudes y datos faltantes de contabilidad",
    boxProcessMeta: "Mensajes · datos · alertas",
    boxConfirmTitle: "Confirmación",
    boxConfirmDesc: "Aprobar o rechazar entregas de período",
    boxConfirmMeta: "Confirmaciones de la plataforma",
    boxStudioTitle: "Estudio",
    boxStudioDesc: "Revisar nóminas y enviar a la app",
    boxStudioMeta: "Aprobación PDF · archivo",
    openStudio: "Abrir estudio",
    studioReadyTitle: "Estudio listo",
    studioReadyBody: "El estudio se abre en esta página — sin ventana extra.",
    emptyProcessTitle: "Todo al día",
    emptyProcessBody: "No hay solicitudes abiertas de contabilidad.",
    emptyConfirmTitle: "Sin confirmaciones",
    emptyConfirmBody: "Las solicitudes de período aparecen aquí.",
    payslipPendingTitle: "Nóminas por revisar",
    payslipPendingBody: "{n} PDF esperan revisión y envío.",
    openPayslips: "Revisar y enviar",
    periodTitle: "Entrega de período",
    periodBody: "Contabilidad pide datos para {period}.",
    periodConfirm: "Aprobar",
    periodReject: "Rechazar",
    missingData: "Datos faltantes",
    openMaster: "Abrir datos",
    done: "Hecho",
    edit: "Editar",
    selectCompany: "Elige primero una empresa en Operaciones.",
    forbidden: "Sin permiso para el centro de nómina.",
    loginRequired: "Inicia sesión desde Operaciones.",
    sessionExpired: "Sesión caducada — vuelve a entrar.",
    loading: "Cargando solicitudes…",
    updated: "Actualizado",
    externalFail: "Contabilidad no disponible",
    studioWait: "Preparando estudio…",
    studioFail: "No se pudo abrir el estudio.",
  },
  it: {
    boot: "Caricamento hub paghe…",
    title: "Hub paghe",
    sub: "Richieste contabili e cedolini — in un solo posto.",
    lang: "Lingua",
    backBetrieb: "← Operazioni",
    refresh: "Aggiorna",
    openExternal: "Apri contabilità",
    backBoxes: "← Caselle",
    boxProcessTitle: "Da elaborare",
    boxProcessDesc: "Richieste e dati mancanti dalla contabilità",
    boxProcessMeta: "Messaggi · anagrafica · avvisi",
    boxConfirmTitle: "Conferma",
    boxConfirmDesc: "Approvare o rifiutare i passaggi di periodo",
    boxConfirmMeta: "Conferme della piattaforma",
    boxStudioTitle: "Studio",
    boxStudioDesc: "Controllare i cedolini e inviarli all’app",
    boxStudioMeta: "Approvazione PDF · archivio",
    openStudio: "Apri studio",
    studioReadyTitle: "Studio pronto",
    studioReadyBody: "Lo studio si apre in questa pagina — senza finestra extra.",
    emptyProcessTitle: "Tutto ok",
    emptyProcessBody: "Nessuna richiesta aperta dalla contabilità.",
    emptyConfirmTitle: "Nessuna conferma",
    emptyConfirmBody: "Le richieste di periodo compaiono qui.",
    payslipPendingTitle: "Cedolini da verificare",
    payslipPendingBody: "{n} PDF in attesa di verifica e invio.",
    openPayslips: "Verifica e invia",
    periodTitle: "Passaggio periodo",
    periodBody: "La contabilità chiede dati per {period}.",
    periodConfirm: "Approva",
    periodReject: "Rifiuta",
    missingData: "Dati mancanti",
    openMaster: "Apri anagrafica",
    done: "Fatto",
    edit: "Modifica",
    selectCompany: "Seleziona prima un’azienda in Operazioni.",
    forbidden: "Nessun permesso per l’hub paghe.",
    loginRequired: "Accedi tramite Operazioni.",
    sessionExpired: "Sessione scaduta — accedi di nuovo.",
    loading: "Caricamento richieste…",
    updated: "Aggiornato",
    externalFail: "Contabilità non disponibile",
    studioWait: "Preparazione studio…",
    studioFail: "Impossibile aprire lo studio.",
  },
  pl: {
    boot: "Ładowanie centrum płac…",
    title: "Centrum płac",
    sub: "Wnioski księgowe i paski — w jednym miejscu.",
    lang: "Język",
    backBetrieb: "← Operacje",
    refresh: "Odśwież",
    openExternal: "Otwórz księgowość",
    backBoxes: "← Skrzynki",
    boxProcessTitle: "Do obsłużenia",
    boxProcessDesc: "Wnioski i brakujące dane z księgowości",
    boxProcessMeta: "Wiadomości · dane · alerty",
    boxConfirmTitle: "Potwierdzenie",
    boxConfirmDesc: "Zatwierdź lub odrzuć przekazanie okresu",
    boxConfirmMeta: "Potwierdzenia platformy",
    boxStudioTitle: "Studio",
    boxStudioDesc: "Sprawdź paski i wyślij do aplikacji",
    boxStudioMeta: "Akceptacja PDF · archiwum",
    openStudio: "Otwórz studio",
    studioReadyTitle: "Studio gotowe",
    studioReadyBody: "Studio otwiera się na tej stronie — bez dodatkowego okna.",
    emptyProcessTitle: "Wszystko załatwione",
    emptyProcessBody: "Brak otwartych wniosków z księgowości.",
    emptyConfirmTitle: "Brak potwierdzeń",
    emptyConfirmBody: "Wnioski o okres pojawią się tutaj.",
    payslipPendingTitle: "Paski do sprawdzenia",
    payslipPendingBody: "{n} PDF czeka na sprawdzenie i wysyłkę.",
    openPayslips: "Sprawdź i wyślij",
    periodTitle: "Przekazanie okresu",
    periodBody: "Księgowość prosi o dane za {period}.",
    periodConfirm: "Zatwierdź",
    periodReject: "Odrzuć",
    missingData: "Brakujące dane",
    openMaster: "Otwórz dane",
    done: "Gotowe",
    edit: "Edytuj",
    selectCompany: "Najpierw wybierz firmę w Operacjach.",
    forbidden: "Brak uprawnień do centrum płac.",
    loginRequired: "Zaloguj się przez Operacje.",
    sessionExpired: "Sesja wygasła — zaloguj się ponownie.",
    loading: "Ładowanie wniosków…",
    updated: "Zaktualizowano",
    externalFail: "Księgowość niedostępna",
    studioWait: "Przygotowanie studia…",
    studioFail: "Nie udało się otworzyć studia.",
  },
};

const qs = new URLSearchParams(location.search);
const state = {
  companyId: String(qs.get("company_id") || "").trim(),
  focus: String(qs.get("focus") || "").trim().toLowerCase(),
  lang: "de",
  messages: [],
  alerts: [],
  periodRequests: [],
  payslipBatches: [],
  payslipCount: 0,
  busy: false,
  panel: "home",
};

function $(id) {
  return document.getElementById(id);
}

function wpGet(key) {
  try {
    return WP?.get?.(key) ?? WP?.getItem?.(key) ?? localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function wpSet(key, value) {
  try {
    if (WP?.set) WP.set(key, value);
    else if (WP?.setItem) WP.setItem(key, value);
    else localStorage.setItem(key, String(value ?? ""));
  } catch {
    /* ignore */
  }
}

function tr(key, vars = {}) {
  const pack = ACC_I18N[state.lang] || ACC_I18N.de;
  let text = pack[key] || ACC_I18N.de[key] || key;
  Object.entries(vars).forEach(([k, v]) => {
    text = text.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
  });
  return text;
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/'/g, "&#39;");
}

function detectLang() {
  const fromQs = String(qs.get("lang") || "").toLowerCase();
  const fromStore = String(wpGet(LANG_KEY) || localStorage.getItem("baupass-ui-lang") || "").toLowerCase();
  const raw = fromQs || fromStore || document.documentElement.lang || "de";
  const lang = raw.slice(0, 2);
  return ACC_I18N[lang] ? lang : "de";
}

function applyI18nDom() {
  document.documentElement.lang = state.lang;
  document.documentElement.dir = state.lang === "ar" ? "rtl" : "ltr";
  document.querySelectorAll("[data-acc-i18n]").forEach((el) => {
    const key = el.getAttribute("data-acc-i18n");
    if (key) el.textContent = tr(key);
  });
  document.title = `SUPPIX — ${tr("title")}`;
  const sel = $("accLangSelect");
  if (sel) sel.value = state.lang;
}

function getToken() {
  return String(WP?.readSessionToken?.() || wpGet(TOKEN_KEY) || wpGet(CONTROL_TOKEN_KEY) || "").trim();
}

function getUser() {
  try {
    return JSON.parse(wpGet(USER_KEY) || "{}") || {};
  } catch {
    return {};
  }
}

function setStatus(msg, kind = "") {
  const el = $("accStatus");
  if (!el) return;
  el.textContent = msg || "";
  el.classList.toggle("is-error", kind === "error");
  el.classList.toggle("is-ok", kind === "ok");
}

async function api(path, options = {}) {
  const token = getToken();
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { ...options, headers, cache: "no-store" });
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = {};
  }
  if (!res.ok) {
    const err = new Error(data.message || data.error || res.statusText || "request_failed");
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

function withTimeout(promise, timeoutMs, fallback) {
  let timer;
  const timed = new Promise((resolve) => {
    timer = setTimeout(() => resolve(fallback), Math.max(500, Number(timeoutMs) || 8000));
  });
  return Promise.race([Promise.resolve(promise).finally(() => clearTimeout(timer)), timed]);
}

function apiSoft(path, fallback = null, timeoutMs = 8000, options = {}) {
  return withTimeout(api(path, options).catch(() => fallback), timeoutMs, fallback);
}

function canAccessLohn() {
  const role = String(getUser()?.role || "").toLowerCase();
  if (role === "office" || role === "turnstile") return false;
  if (!role) return Boolean(getToken());
  return role === "superadmin" || role === "company-admin";
}

function lohnContractsUrl(companyId, workerId, fields, hint) {
  const params = new URLSearchParams();
  params.set("focus", "payroll");
  if (companyId) params.set("company_id", companyId);
  if (workerId) params.set("worker_id", String(workerId));
  if (Array.isArray(fields) && fields.length) params.set("fields", fields.join(","));
  if (hint) params.set("hint", String(hint).slice(0, 180));
  return `/admin-v2/contracts.html?${params.toString()}`;
}

function renderChips(fields) {
  const list = Array.isArray(fields) ? fields.filter(Boolean) : [];
  if (!list.length) return "";
  return `<div class="acc-chips">${list
    .slice(0, 8)
    .map((f) => `<span class="acc-chip">${escapeHtml(f)}</span>`)
    .join("")}</div>`;
}

function setBadge(id, n) {
  const el = $(id);
  if (!el) return;
  const count = Number(n) || 0;
  el.textContent = String(count);
  el.classList.toggle("is-zero", count <= 0);
}

function showHome() {
  state.panel = "home";
  $("accMailboxHome")?.classList.remove("hidden");
  document.querySelectorAll("[data-acc-panel]").forEach((p) => p.classList.add("hidden"));
}

function openPanel(name) {
  state.panel = name;
  $("accMailboxHome")?.classList.add("hidden");
  document.querySelectorAll("[data-acc-panel]").forEach((p) => {
    p.classList.toggle("hidden", p.getAttribute("data-acc-panel") !== name);
  });
  if (name === "studio") {
    // auto-open studio when entering mailbox if requested
  }
}

function paintProcess() {
  const host = $("accProcessBody");
  if (!host) return;
  const parts = [];
  const cid = state.companyId;

  if (state.payslipBatches.length) {
    parts.push(`
      <article class="acc-card is-alert">
        <div class="acc-card-title">${escapeHtml(tr("payslipPendingTitle"))}</div>
        <div class="acc-card-body">${escapeHtml(tr("payslipPendingBody", { n: state.payslipCount }))}</div>
        <div class="acc-card-actions">
          <button type="button" class="primary" data-acc-action="open-studio">${escapeHtml(tr("openPayslips"))}</button>
        </div>
      </article>`);
  }

  for (const a of state.alerts.slice(0, 40)) {
    const id = String(a.id || "");
    const wid = String(a.workerId || a.employeeId || "").trim();
    const fields = a.missingFields || a.missing_fields || [];
    const name =
      String(a.workerDisplayName || "").trim()
      || [a.workerFirstName, a.workerLastName].filter(Boolean).join(" ").trim()
      || a.workerName
      || wid
      || "—";
    const href = lohnContractsUrl(a.companyId || cid, wid, fields, a.message || "");
    parts.push(`
      <article class="acc-card is-alert" data-acc-alert="${escapeAttr(id)}">
        <div class="acc-card-title"><strong>${escapeHtml(name)}</strong>${wid && name !== wid ? ` <span class="muted">(${escapeHtml(wid)})</span>` : ""}</div>
        <div class="acc-card-body">${escapeHtml(a.message || tr("missingData"))}</div>
        ${renderChips(fields)}
        <div class="acc-card-actions">
          <a class="primary" href="${escapeAttr(href)}" target="_blank" rel="noopener">${escapeHtml(tr("openMaster"))}</a>
          <button type="button" data-acc-action="dismiss-alert" data-id="${escapeAttr(id)}">${escapeHtml(tr("done"))}</button>
        </div>
      </article>`);
  }

  for (const m of state.messages.slice(0, 40)) {
    const id = String(m.id || "");
    const fields = m.missingFields || m.missing_fields || [];
    const subject = m.subject || m.kind || "WorkPass Lohn";
    const bodyText = String(m.body || "").trim();
    const wid = String(m.workerId || "").trim();
    const name =
      String(m.workerDisplayName || "").trim()
      || [m.workerFirstName, m.workerLastName].filter(Boolean).join(" ").trim();
    const href = lohnContractsUrl(m.companyId || cid, m.workerId, fields, `${subject} ${bodyText}`);
    parts.push(`
      <article class="acc-card" data-acc-msg="${escapeAttr(id)}">
        <div class="acc-card-title">${escapeHtml(subject)}</div>
        ${name || wid ? `<div class="acc-card-body"><strong>${escapeHtml(name || "—")}</strong>${wid ? ` <span class="muted">(${escapeHtml(wid)})</span>` : ""}</div>` : ""}
        ${bodyText ? `<div class="acc-card-body">${escapeHtml(bodyText.slice(0, 280))}</div>` : ""}
        ${renderChips(fields)}
        <div class="acc-card-meta">${escapeHtml([m.period, name || wid].filter(Boolean).join(" · ") || "—")}</div>
        <div class="acc-card-actions">
          <a class="primary" href="${escapeAttr(href)}" target="_blank" rel="noopener" data-acc-action="open-msg" data-id="${escapeAttr(id)}">${escapeHtml(tr("edit"))}</a>
          <button type="button" data-acc-action="ack-msg" data-id="${escapeAttr(id)}">${escapeHtml(tr("done"))}</button>
        </div>
      </article>`);
  }

  if (!parts.length) {
    host.innerHTML = `<div class="acc-empty"><strong>${escapeHtml(tr("emptyProcessTitle"))}</strong>${escapeHtml(tr("emptyProcessBody"))}</div>`;
  } else {
    host.innerHTML = `<div class="acc-cards">${parts.join("")}</div>`;
  }

  const processCount = state.messages.length + state.alerts.length + (state.payslipCount ? 1 : 0);
  setBadge("badgeProcess", processCount);
}

function paintConfirm() {
  const host = $("accConfirmBody");
  if (!host) return;
  const parts = [];
  for (const req of state.periodRequests.slice(0, 40)) {
    const id = String(req.id || "");
    const period = String(req.period || "—");
    parts.push(`
      <article class="acc-card is-alert" data-acc-period="${escapeAttr(id)}">
        <div class="acc-card-title">${escapeHtml(tr("periodTitle"))}</div>
        <div class="acc-card-body">${escapeHtml(tr("periodBody", { period }))}</div>
        <div class="acc-card-meta">${escapeHtml(period)}</div>
        <div class="acc-card-actions">
          <button type="button" class="primary" data-acc-action="period-confirm" data-id="${escapeAttr(id)}">${escapeHtml(tr("periodConfirm"))}</button>
          <button type="button" class="danger" data-acc-action="period-reject" data-id="${escapeAttr(id)}">${escapeHtml(tr("periodReject"))}</button>
        </div>
      </article>`);
  }
  if (!parts.length) {
    host.innerHTML = `<div class="acc-empty"><strong>${escapeHtml(tr("emptyConfirmTitle"))}</strong>${escapeHtml(tr("emptyConfirmBody"))}</div>`;
  } else {
    host.innerHTML = `<div class="acc-cards">${parts.join("")}</div>`;
  }
  setBadge("badgeConfirm", state.periodRequests.length);
}

function paintStudioHint() {
  setBadge("badgeStudio", state.payslipCount);
  const hint = $("accStudioHint");
  if (!hint) return;
  hint.innerHTML = `<strong>${escapeHtml(tr("studioReadyTitle"))}</strong><span>${escapeHtml(tr("studioReadyBody"))}</span>`;
}

async function loadHub() {
  const cid = state.companyId;
  if (!cid && String(getUser()?.role || "").toLowerCase() === "superadmin") {
    setStatus(tr("selectCompany"), "error");
    $("accProcessBody").innerHTML = `<div class="acc-empty"><strong>${escapeHtml(tr("selectCompany"))}</strong></div>`;
    $("accConfirmBody").innerHTML = "";
    return;
  }
  setStatus(tr("loading"));
  const cq = cid ? `?company_id=${encodeURIComponent(cid)}` : "";
  const msgUrl = `/api/payroll/accounting/messages?sync=1${cid ? `&company_id=${encodeURIComponent(cid)}` : ""}`;
  const [msgRes, alertRes, periodRes, payslipRes] = await Promise.all([
    apiSoft(msgUrl, { messages: [] }, 8000),
    apiSoft(`/api/payroll/accounting/data-alerts${cq}`, { alerts: [] }, 5000),
    apiSoft(
      `/api/payroll/accounting/period-requests?status=pending_confirmation${cid ? `&company_id=${encodeURIComponent(cid)}` : ""}`,
      { requests: [] },
      5000,
    ),
    apiSoft(`/api/payroll/statements/pending${cq}`, { batches: [] }, 6000),
  ]);
  state.messages = Array.isArray(msgRes?.messages) ? msgRes.messages : [];
  state.alerts = Array.isArray(alertRes?.alerts) ? alertRes.alerts : [];
  state.periodRequests = Array.isArray(periodRes?.requests) ? periodRes.requests : [];
  state.payslipBatches = Array.isArray(payslipRes?.batches) ? payslipRes.batches : [];
  state.payslipCount = state.payslipBatches.reduce(
    (n, b) => n + (Array.isArray(b.statements) ? b.statements.length : Number(b.statement_count || 0)),
    0,
  );
  paintProcess();
  paintConfirm();
  paintStudioHint();
  setStatus(`${tr("updated")} · ${new Date().toLocaleTimeString()}`, "ok");
}

function waitForStudio(maxMs = 12000) {
  return new Promise((resolve) => {
    if (window.BaupassPayslipStudio?.open) {
      resolve(window.BaupassPayslipStudio);
      return;
    }
    const onReady = () => {
      cleanup();
      resolve(window.BaupassPayslipStudio || null);
    };
    const cleanup = () => {
      window.clearTimeout(timer);
      window.removeEventListener("baupass-payslip-studio-ready", onReady);
    };
    const timer = window.setTimeout(() => {
      cleanup();
      resolve(window.BaupassPayslipStudio || null);
    }, maxMs);
    window.addEventListener("baupass-payslip-studio-ready", onReady);
  });
}

async function openStudioInPage(extra = {}) {
  setStatus(tr("studioWait"));
  let studio = await waitForStudio(4000);
  if (!studio?.open) {
    // app.js may still be parsing — one more short wait
    studio = await waitForStudio(8000);
  }
  if (!studio?.open) {
    setStatus(tr("studioFail"), "error");
    return;
  }
  try {
    await studio.open({
      forceLocal: true,
      batchId: extra.batchId || qs.get("batch_id") || qs.get("batchId") || "",
      statementId: extra.statementId || qs.get("statement_id") || qs.get("statementId") || "",
    });
    setStatus("", "");
  } catch (e) {
    setStatus(e?.message || tr("studioFail"), "error");
  }
}

async function openExternalAccounting() {
  if (!canAccessLohn()) {
    setStatus(tr("forbidden"), "error");
    return;
  }
  const cid = state.companyId;
  if (!cid) {
    setStatus(tr("selectCompany"), "error");
    return;
  }
  try {
    const res = await api(`/api/payroll/accounting/launch?company_id=${encodeURIComponent(cid)}`);
    if (!res?.ok || !res.url) {
      setStatus(res?.message || tr("externalFail"), "error");
      return;
    }
    const win = window.open(String(res.url), "_blank");
    if (!win) window.location.assign(String(res.url));
  } catch (e) {
    setStatus(e?.message || tr("externalFail"), "error");
  }
}

async function handleAction(ev) {
  const el = ev.target?.closest?.("[data-acc-action]");
  if (!el || state.busy) return;
  const action = el.getAttribute("data-acc-action");
  const id = String(el.getAttribute("data-id") || "").trim();

  if (action === "open-studio") {
    openPanel("studio");
    await openStudioInPage();
    return;
  }

  if (action === "open-msg" && id) {
    ev.preventDefault();
    const href = el.getAttribute("href");
    document.querySelector(`[data-acc-msg="${CSS.escape(id)}"]`)?.remove();
    try {
      await api(`/api/payroll/accounting/messages/${encodeURIComponent(id)}/open`, { method: "POST", body: "{}" });
    } catch {
      /* still open */
    }
    if (href) window.open(href, "_blank", "noopener");
    void loadHub();
    return;
  }

  if (action === "ack-msg" && id) {
    state.busy = true;
    el.disabled = true;
    try {
      await api(`/api/payroll/accounting/messages/${encodeURIComponent(id)}/open`, { method: "POST", body: "{}" });
    } catch (e) {
      setStatus(e?.message || "error", "error");
    } finally {
      state.busy = false;
      void loadHub();
    }
    return;
  }

  if (action === "dismiss-alert" && id) {
    state.busy = true;
    el.disabled = true;
    try {
      await api(`/api/payroll/accounting/data-alerts/${encodeURIComponent(id)}/dismiss`, { method: "POST", body: "{}" });
    } catch (e) {
      setStatus(e?.message || "error", "error");
    } finally {
      state.busy = false;
      void loadHub();
    }
    return;
  }

  if ((action === "period-confirm" || action === "period-reject") && id) {
    state.busy = true;
    el.disabled = true;
    const path =
      action === "period-confirm"
        ? `/api/payroll/accounting/period-requests/${encodeURIComponent(id)}/confirm`
        : `/api/payroll/accounting/period-requests/${encodeURIComponent(id)}/reject`;
    try {
      await api(path, {
        method: "POST",
        body: action === "period-reject" ? JSON.stringify({ reason: "" }) : "{}",
      });
    } catch (e) {
      setStatus(e?.message || "error", "error");
    } finally {
      state.busy = false;
      void loadHub();
    }
  }
}

async function adoptSession() {
  let token = getToken();
  if (!token) {
    token = await new Promise((resolve) => {
      const timer = window.setTimeout(() => {
        window.removeEventListener("message", onMsg);
        resolve(getToken());
      }, 900);
      function onMsg(event) {
        if (event.origin !== window.location.origin) return;
        if (event.data?.type !== "baupass-sync-token" || !event.data.token) return;
        window.clearTimeout(timer);
        window.removeEventListener("message", onMsg);
        wpSet(TOKEN_KEY, event.data.token);
        if (WP?.persistSessionToken) WP.persistSessionToken(event.data.token);
        if (event.data.companyId) {
          state.companyId = String(event.data.companyId);
          wpSet(COMPANY_KEY, state.companyId);
        }
        resolve(String(event.data.token));
      }
      window.addEventListener("message", onMsg);
    });
  }
  if (!token) throw new Error(tr("loginRequired"));

  try {
    const data = await api("/api/v2/auth/session");
    if (data?.user) wpSet(USER_KEY, JSON.stringify(data.user));
    if (!state.companyId) {
      const u = data?.user || getUser();
      state.companyId = String(u.preview_company_id || u.company_id || wpGet(COMPANY_KEY) || "").trim();
    }
    if (state.companyId) wpSet(COMPANY_KEY, state.companyId);
  } catch (e) {
    if (e?.status === 401 || e?.status === 403) throw new Error(tr("sessionExpired"));
    throw e;
  }
}

function wireUi() {
  $("accRefreshBtn")?.addEventListener("click", () => loadHub().catch((e) => setStatus(e.message, "error")));
  $("accOpenExternalBtn")?.addEventListener("click", () => openExternalAccounting());
  $("accOpenStudioBtn")?.addEventListener("click", () => openStudioInPage());
  $("accLangSelect")?.addEventListener("change", (ev) => {
    state.lang = String(ev.target.value || "de");
    wpSet(LANG_KEY, state.lang);
    try {
      localStorage.setItem("baupass-ui-lang", state.lang);
    } catch {
      /* ignore */
    }
    applyI18nDom();
    paintProcess();
    paintConfirm();
    paintStudioHint();
  });

  document.querySelectorAll("[data-acc-box]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const box = btn.getAttribute("data-acc-box");
      openPanel(box);
      if (box === "studio" && (state.focus === "studio" || state.payslipCount > 0)) {
        await openStudioInPage();
      }
    });
  });
  document.querySelectorAll("[data-acc-back]").forEach((btn) => {
    btn.addEventListener("click", () => showHome());
  });
  document.addEventListener("click", (ev) => {
    handleAction(ev).catch((e) => setStatus(e?.message || "error", "error"));
  });

  const back = $("accBackBetrieb");
  if (back && state.companyId) {
    back.href = `/admin-v2/index.html?company_id=${encodeURIComponent(state.companyId)}`;
  }
}

async function boot() {
  state.lang = detectLang();
  applyI18nDom();
  const bootEl = $("accBoot");
  const appEl = $("accApp");
  try {
    await adoptSession();
    if (!canAccessLohn()) throw new Error(tr("forbidden"));
    bootEl?.classList.add("hidden");
    appEl?.classList.remove("hidden");
    wireUi();
    await loadHub();
    if (state.focus === "studio") {
      openPanel("studio");
      await openStudioInPage();
    } else if (state.focus === "confirm") {
      openPanel("confirm");
    } else if (state.focus === "process") {
      openPanel("process");
    } else {
      showHome();
    }
  } catch (e) {
    const msg = e?.message || tr("boot");
    if ($("accBootMsg")) $("accBootMsg").textContent = msg;
    setStatus(msg, "error");
    bootEl?.classList.remove("hidden");
    appEl?.classList.add("hidden");
  }
}

boot();
