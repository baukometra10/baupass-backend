const DEFAULT_RENDER_API_BASE = "https://baupass-production.up.railway.app";
const WP = window.WorkPassStorage;
function workpassMemoryStore() {
  window.__workpassMemStore = window.__workpassMemStore || {};
  return window.__workpassMemStore;
}
function wpSet(key, value) {
  if (key) {
    workpassMemoryStore()[key] = value;
  }
  try {
    if (WP) WP.setItem(key, value);
    else window.localStorage.setItem(key, value);
  } catch {
    // ignore localStorage failures (Lockdown Mode / private mode)
  }
  try {
    sessionStorage.setItem(key, value);
  } catch {
    // ignore sessionStorage failures (Safari private mode)
  }
}
function wpRemove(key) {
  if (key) {
    delete workpassMemoryStore()[key];
  }
  try {
    if (WP) WP.removeItem(key);
    else window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
  try {
    sessionStorage.removeItem(key);
  } catch {
    // ignore
  }
}
function wpGet(key) {
  const memoryValue = workpassMemoryStore()[key];
  if (memoryValue !== undefined && memoryValue !== null && memoryValue !== "") {
    return memoryValue;
  }
  let value = null;
  try {
    value = WP ? WP.getItem(key) : window.localStorage.getItem(key);
  } catch {
    value = null;
  }
  if (value !== null && value !== "") {
    workpassMemoryStore()[key] = value;
    return value;
  }
  try {
    value = sessionStorage.getItem(key);
    if (value !== null && value !== "") {
      workpassMemoryStore()[key] = value;
      return value;
    }
  } catch {
    // ignore
  }
  return null;
}
const API_BASE_STORAGE_KEY = WP?.KEYS?.API_BASE || "workpass-api-base";
const WORKER_BUILD_TAG = "20260702a";
const WORKER_DEBUG = (() => {
  try {
    return new URLSearchParams(window.location.search).get("debug") === "1"
      || localStorage.getItem("worker-debug") === "1";
  } catch {
    return false;
  }
})();
function workerDebug(...args) {
  if (WORKER_DEBUG) console.log(...args);
}
const WORKER_GEO_ACCURACY_BUFFER_METERS = 80;
const WORKER_GEO_MAX_ACCURACY_METERS = 200;
const SITE_GEOFENCE_WATCH_INTERVAL_MS = 10000;
const SITE_OFF_SITE_STRIKES_REQUIRED = 2;
const PROXIMITY_LOGIN_POLL_MS = 10000;
const PROXIMITY_LOGIN_DWELL_MS = 15000;
const RETIRED_WORKER_API_HOSTS = new Set([
  "baupass-control.up.railway.app",
  "web-production-c21ed.up.railway.app",
]);
const WORKER_PLAN_TAB_FEATURES = {
  vacation: "leave_management",
  timesheet: "worker_hours_report",
  documents: "document_upload",
  chat: "worker_chat",
};

function normalizeApiBase(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function sanitizeApiBase(value) {
  const normalized = normalizeApiBase(value);
  if (!normalized) {
    return "";
  }

  let parsed;
  try {
    parsed = new URL(normalized);
  } catch {
    return "";
  }

  if (window.location.protocol === "https:" && parsed.protocol === "http:") {
    const host = (parsed.hostname || "").toLowerCase();
    const localHosts = new Set(["localhost", "127.0.0.1", "::1"]);
    if (!localHosts.has(host)) {
      return "";
    }
  }

  const host = (parsed.hostname || "").toLowerCase();
  if (RETIRED_WORKER_API_HOSTS.has(host)) {
    return "";
  }

  return parsed.toString().replace(/\/+$/, "");
}

function apiBaseMatchesCurrentOrigin(value) {
  const normalized = sanitizeApiBase(value);
  if (!normalized) {
    return false;
  }
  try {
    const configuredOrigin = new URL(normalized).origin.replace(/\/+$/, "");
    const currentOrigin = String(window.location.origin || "").replace(/\/+$/, "");
    return configuredOrigin === currentOrigin;
  } catch {
    return false;
  }
}

function isLocalWorkerHost(hostname) {
  const host = String(hostname || "").toLowerCase();
  return host === "localhost" || host === "127.0.0.1" || host === "::1";
}

function isStaticFrontendHost(hostname) {
  const host = String(hostname || "").toLowerCase();
  return host.endsWith("github.io") || host.endsWith(".pages.dev") || host.endsWith(".web.app");
}

function isUnreachableLocalApiBase(value) {
  const normalized = sanitizeApiBase(value);
  if (!normalized) {
    return false;
  }
  try {
    const host = new URL(normalized).hostname.toLowerCase();
    return isLocalWorkerHost(host) && !isLocalWorkerHost(window.location.hostname);
  } catch {
    return false;
  }
}

function resolveSameOriginWorkerApiBase() {
  if (window.location.protocol === "file:") {
    return "";
  }
  const origin = String(window.location.origin || "").replace(/\/+$/, "");
  if (!origin || origin === "null") {
    return "";
  }
  return `${origin}/api/worker-app`;
}

function resolveWorkerApiBase() {
  const params = new URL(window.location.href).searchParams;
  const queryValue = sanitizeApiBase(params.get("apiBase"));
  const currentHost = window.location.hostname.toLowerCase();
  const staticHost = isStaticFrontendHost(currentHost);
  const sameOriginApi = resolveSameOriginWorkerApiBase();

  if (isLocalWorkerHost(currentHost)) {
    if (queryValue) {
      wpSet(API_BASE_STORAGE_KEY, queryValue);
      return `${queryValue}/api/worker-app`;
    }
    try {
      wpRemove(API_BASE_STORAGE_KEY);
    } catch {
      // ignore
    }
    return sameOriginApi || "/api/worker-app";
  }

  // Platform deployment: API always lives on the same host as the PWA shell.
  if (!staticHost && sameOriginApi) {
    const storedValue = sanitizeApiBase(wpGet(API_BASE_STORAGE_KEY));
    if (storedValue && !apiBaseMatchesCurrentOrigin(storedValue)) {
      try {
        wpRemove(API_BASE_STORAGE_KEY);
      } catch {
        // ignore
      }
    }
    if (queryValue && !apiBaseMatchesCurrentOrigin(queryValue)) {
      try {
        wpRemove(API_BASE_STORAGE_KEY);
      } catch {
        // ignore
      }
    } else if (queryValue) {
      wpSet(API_BASE_STORAGE_KEY, queryValue);
    }
    return sameOriginApi;
  }

  let configuredValue = queryValue || sanitizeApiBase(wpGet(API_BASE_STORAGE_KEY));
  if (configuredValue && isUnreachableLocalApiBase(configuredValue)) {
    configuredValue = "";
    wpRemove(API_BASE_STORAGE_KEY);
  }
  if (configuredValue) {
    try {
      const configuredHost = new URL(configuredValue).hostname.toLowerCase();
      if (RETIRED_WORKER_API_HOSTS.has(configuredHost)) {
        configuredValue = "";
        wpRemove(API_BASE_STORAGE_KEY);
      }
    } catch {
      configuredValue = "";
      wpRemove(API_BASE_STORAGE_KEY);
    }
  }

  if (configuredValue) {
    wpSet(API_BASE_STORAGE_KEY, configuredValue);
    return `${configuredValue}/api/worker-app`;
  }

  if (wpGet(API_BASE_STORAGE_KEY)) {
    wpRemove(API_BASE_STORAGE_KEY);
  }

  return `${DEFAULT_RENDER_API_BASE}/api/worker-app`;
}

let API_BASE = resolveWorkerApiBase();
let API_ROOT = resolveApiRoot(API_BASE);

function refreshWorkerApiBase() {
  API_BASE = resolveWorkerApiBase();
  API_ROOT = resolveApiRoot(API_BASE);
}
const WORKER_TOKEN_KEY = WP?.KEYS?.WORKER_TOKEN || "workpass-worker-token";
const WORKER_ACCESS_TOKEN_KEY = WP?.KEYS?.WORKER_ACCESS_TOKEN || "workpass-worker-access-token";
const PENDING_ACCESS_TOKEN_KEY = WP?.KEYS?.PENDING_ACCESS_TOKEN || "workpass-pending-access-token";
function readBootstrapBadgeId(params) {
  const urlBadge = getQrLaunchBadgeId(params);
  if (urlBadge) {
    return urlBadge;
  }
  try {
    const pending = normalizeBadgeIdInput(sessionStorage.getItem(PENDING_QR_BADGE_KEY) || "");
    if (pending) {
      return pending;
    }
  } catch {
    // ignore sessionStorage failures
  }
  return normalizeBadgeIdInput(wpGet(WORKER_BADGE_LOGIN_KEY) || "");
}

function readBootstrapAccessToken(params) {
  const urlToken = (params.get("access") || "").trim();
  if (urlToken) return urlToken;
  const storedAccess = String(wpGet(WORKER_ACCESS_TOKEN_KEY) || "").trim();
  if (storedAccess) return storedAccess;
  return String(wpGet(PENDING_ACCESS_TOKEN_KEY) || "").trim();
}

function clearBootstrapAccessTokens() {
  wpRemove(WORKER_ACCESS_TOKEN_KEY);
  wpRemove(PENDING_ACCESS_TOKEN_KEY);
}

function isWorkerShellAuthenticated() {
  return Boolean(workerToken) && document.body.classList.contains("worker-loaded");
}

function isQrBootstrapEntry(params = null) {
  try {
    const search = params || new URLSearchParams(window.location.search);
    if (search.get("session") === "1") {
      return false;
    }
    return Boolean((search.get("access") || "").trim())
      || search.get("fast") === "1"
      || search.get("launch") === "1"
      || Boolean(normalizeBadgeIdInput(search.get("badge") || ""));
  } catch {
    return false;
  }
}

function resetWorkerSessionForQrEntry({ keepBadge = true } = {}) {
  wpRemove(WORKER_TOKEN_KEY);
  wpRemove(WORKER_JWT_KEY);
  wpRemove(WORKER_DEVICE_ID_KEY);
  wpRemove(WORKER_CACHED_PAYLOAD_KEY);
  if (!keepBadge) {
    wpRemove(WORKER_BADGE_LOGIN_KEY);
  }
  workerToken = "";
  workerBearerToken = "";
  offlineWorkerSessionActive = false;
  document.body.classList.remove("worker-loaded");
}

function markWorkerLoginCompleted() {
  window.__workerLoginCompletedAt = Date.now();
}

function getOrCreateWorkerDeviceFingerprint() {
  let fp = String(wpGet(WORKER_DEVICE_FP_KEY) || "").trim();
  if (fp) {
    return fp;
  }
  try {
    fp = `wp-${crypto.randomUUID()}`;
  } catch {
    fp = `wp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
  wpSet(WORKER_DEVICE_FP_KEY, fp);
  return fp;
}

function buildWorkerDevicePayload() {
  if (!window.FlutterWorkerBridge && !window.workpassNativeDevice) {
    return null;
  }
  return {
    fingerprint: getOrCreateWorkerDeviceFingerprint(),
    name: isIosDevice() ? "iPhone" : (isStandaloneDisplay() ? "Installed PWA" : "Mobile Web"),
    platform: isIosDevice() ? "ios" : "web",
  };
}

function getWorkerAuthorizationValue() {
  const session = String(workerToken || wpGet(WORKER_TOKEN_KEY) || "").trim();
  if (session) {
    return session;
  }
  const jwt = String(workerBearerToken || wpGet(WORKER_JWT_KEY) || "").trim();
  if (jwt.includes(".")) {
    return jwt;
  }
  return "";
}

function buildWorkerAuthHeaders(extraHeaders = {}) {
  const headers = { ...(extraHeaders || {}) };
  const auth = getWorkerAuthorizationValue();
  if (auth && !headers.Authorization) {
    headers.Authorization = `Bearer ${auth}`;
  }
  const sendDeviceHeader = Boolean(window.FlutterWorkerBridge || window.workpassNativeDevice);
  const deviceId = sendDeviceHeader ? String(wpGet(WORKER_DEVICE_ID_KEY) || "").trim() : "";
  if (deviceId && !headers["X-Device-Id"]) {
    headers["X-Device-Id"] = deviceId;
  }
  return headers;
}

function persistWorkerSessionCredentials(payload) {
  if (!payload) {
    return;
  }
  const sessionToken = String(payload.token || "").trim();
  if (sessionToken) {
    workerToken = sessionToken;
    wpSet(WORKER_TOKEN_KEY, sessionToken);
  }
  const jwt = String(payload.jwt || "").trim();
  if (jwt) {
    workerBearerToken = jwt;
    wpSet(WORKER_JWT_KEY, jwt);
  } else if (sessionToken) {
    workerBearerToken = sessionToken;
    wpRemove(WORKER_JWT_KEY);
  }
  const deviceId = String(payload.deviceId || "").trim();
  if (deviceId) {
    wpSet(WORKER_DEVICE_ID_KEY, deviceId);
  } else if (!window.FlutterWorkerBridge && !window.workpassNativeDevice) {
    wpRemove(WORKER_DEVICE_ID_KEY);
  }
}

function shouldKeepWorkerShellAfterSyncError(error = null) {
  if (!document.body.classList.contains("worker-loaded")) {
    return false;
  }
  const loginGraceMs = Date.now() - Number(window.__workerLoginCompletedAt || 0);
  if (loginGraceMs <= 120000) {
    return true;
  }
  if (wpGet(WORKER_CACHED_PAYLOAD_KEY)) {
    return true;
  }
  if (error && !isWorkerSessionAuthError(error?.code)) {
    return true;
  }
  return false;
}

function isWorkerAnonymousRequest(url) {
  const value = String(url || "");
  return value.includes("/login")
    || value.includes("/join-preview")
    || value.includes("/proximity-site-hint")
    || value.includes("/proximity-login");
}
const WORKER_BADGE_LOGIN_KEY = WP?.KEYS?.WORKER_BADGE_LOGIN || "workpass-worker-badge-login";
const PENDING_QR_BADGE_KEY = "workpass-qr-pending-badge";
const LOCAL_LAST_PHOTO_KEY = WP?.KEYS?.LOCAL_LAST_PHOTO || "workpass-last-local-photo";
const OFFLINE_PHOTO_QUEUE_KEY = WP?.KEYS?.OFFLINE_PHOTO_QUEUE || "workpass-offline-photo-queue";
const OFFLINE_EVENT_QUEUE_KEY = WP?.KEYS?.OFFLINE_EVENT_QUEUE || "workpass-offline-event-queue";
const WORKER_OFFLINE_LOGIN_PROFILE_KEY = WP?.KEYS?.WORKER_OFFLINE_LOGIN_PROFILE || "workpass-worker-offline-login-profile";
const WORKER_PROXIMITY_PIN_KEY = WP?.KEYS?.WORKER_PROXIMITY_PIN || "workpass-worker-proximity-pin";
const QR_CACHE_PREFIX = WP?.KEYS?.QR_CACHE_PREFIX || "workpass-worker-qr-cache";
const QR_HIGH_CONTRAST_KEY = WP?.KEYS?.QR_HIGH_CONTRAST || "workpass-qr-high-contrast";
const AUTO_OPEN_SCANNER_KEY = WP?.KEYS?.AUTO_OPEN_SCANNER || "workpass-auto-open-scanner";
const WORKER_CACHED_PAYLOAD_KEY = WP?.KEYS?.WORKER_CACHED_PAYLOAD || "workpass-worker-cached-payload";
const WORKER_JWT_KEY = WP?.KEYS?.WORKER_JWT || "workpass-worker-jwt";
const WORKER_DEVICE_ID_KEY = WP?.KEYS?.WORKER_DEVICE_ID || "workpass-worker-device-id";
const WORKER_DEVICE_FP_KEY = WP?.KEYS?.WORKER_DEVICE_FP || "workpass-worker-device-fp";
const WORKER_LANG_KEY = WP?.KEYS?.WORKER_LANG || "workpass-worker-lang";
const WORKER_INACTIVITY_TIMEOUT_MS = 60 * 1000;
const WORKER_PASS_LOCK_TIMEOUT_MS = 2 * 60 * 1000;
const WORKER_THEME_KEY = WP?.KEYS?.WORKER_THEME || "workpass-worker-theme";
const WORKER_DAY_PLANNER_KEY = WP?.KEYS?.WORKER_DAY_PLANNER || "workpass-worker-day-planner";
const SMART_HUB_NOTIFY_KEY = WP?.KEYS?.SMART_HUB_NOTIFY || "workpass-smart-hub-notify";

// i18n runtime is loaded from worker-i18n.js to keep this file focused on app behavior.
const I18N_RUNTIME = window.WorkerI18N;
if (!I18N_RUNTIME) {
  throw new Error("worker-i18n.js failed to load before worker-app.js");
}
const {
  TRANSLATIONS,
  LANG_META,
  t,
  tf,
  getCurrentLocale,
  isSupportedLang,
  getCurrentLang,
  setCurrentLang,
} = I18N_RUNTIME;
let currentLang = getCurrentLang(WORKER_LANG_KEY);
function normalizeCompanyBrandingPreset(value) {
  const preset = String(value || "").trim().toLowerCase();
  if (preset === "industry" || preset === "premium") {
    return preset;
  }
  return "construction";
}

function normalizeHexColor(value, fallback = "") {
  const raw = String(value || "").trim();
  return /^#[0-9a-fA-F]{6}$/.test(raw) ? raw.toLowerCase() : fallback;
}

function shadeHexColor(hex, amount) {
  const normalized = normalizeHexColor(hex, "");
  if (!normalized) return "";
  const channel = normalized.slice(1);
  const parts = [channel.slice(0, 2), channel.slice(2, 4), channel.slice(4, 6)].map((part) => {
    const value = parseInt(part, 16);
    const next = Math.min(255, Math.max(0, value + amount));
    return next.toString(16).padStart(2, "0");
  });
  return `#${parts.join("")}`;
}

function getWorkerBrandTitle() {
  return String(currentAppBrandTitle || "").trim() || t("workerChatFromCompany");
}

function resolveWorkerTenantIconHref({ brandTitle, logoData, accentColor } = {}) {
  if (window.TenantBrandIcon?.resolveTenantIconHref) {
    return window.TenantBrandIcon.resolveTenantIconHref({
      brandTitle,
      logoData,
      accentColor,
      size: 192,
    });
  }
  return String(logoData || "").trim();
}

function applyWorkerAppIcons(iconHref, brandTitle) {
  const href = String(iconHref || "").trim();
  if (!href) return;
  currentWorkerIconHref = href;
  document.querySelectorAll('link[rel="icon"], link[rel="shortcut icon"]').forEach((link) => {
    link.href = href;
  });
  document.querySelectorAll('link[rel="apple-touch-icon"]').forEach((link) => {
    link.href = href;
  });
  const splashIcon = document.getElementById("workerSplashIconMark") || document.querySelector(".splash-icon");
  if (splashIcon) {
    const safeHref = href.replace(/"/g, "&quot;");
    splashIcon.innerHTML = `<img src="${safeHref}" width="50" height="50" alt="" class="splash-icon-img" />`;
  }
  const storedToken = wpGet(WORKER_TOKEN_KEY) || "";
  if (storedToken) applyDynamicManifestStartUrl(storedToken, brandTitle || currentAppBrandTitle);
}

function updateWorkerChatBranding(brandTitle) {
  const title = String(brandTitle || "").trim();
  if (!title) return;
  const chatHeading = document.getElementById("workerChatSectionTitle")
    || document.querySelector("#chatCard .section-head h3");
  if (chatHeading) {
    chatHeading.textContent = tf("workerChatWithBrand", { brand: title });
  }
  const hubChatLabels = document.querySelectorAll('[data-worker-menu="chat"] .worker-menu-label, [data-tab-link="chat"] .worker-menu-label');
  hubChatLabels.forEach((el) => {
    el.textContent = tf("workerChatWithBrand", { brand: title });
  });
}

function applyWorkerBrandLabels(brandTitle) {
  const title = String(brandTitle || "").trim();
  if (!title) return;
  currentAppBrandTitle = title;
  document.title = `${title} – ${t("splashSub")}`;
  const targets = [
    document.getElementById("workerBrandName"),
    document.getElementById("dashboardBrandName"),
    document.getElementById("visitorBrandName"),
    document.getElementById("workerAppTitle"),
    document.getElementById("workerSplashTitle"),
    document.getElementById("workerBrandChip"),
    document.querySelector(".stb-brand-name"),
    document.querySelector(".login-brand-title"),
  ];
  targets.forEach((el) => {
    if (!el) return;
    const isCardBrand = el.id === "workerBrandName" || el.id === "dashboardBrandName" || el.id === "visitorBrandName";
    el.textContent = isCardBrand ? title.toUpperCase() : title;
  });
  updateWorkerChatBranding(title);
  const aiTitleEl = document.getElementById("workerAiTitle") || document.querySelector("#workerAiCard h3");
  if (aiTitleEl) {
    aiTitleEl.textContent = `${title} AI`;
  }
  const metaAppTitle = document.querySelector('meta[name="apple-mobile-web-app-title"]');
  if (metaAppTitle) metaAppTitle.setAttribute("content", title);
  const metaAppName = document.querySelector('meta[name="application-name"]');
  if (metaAppName) metaAppName.setAttribute("content", `${title} ${t("splashSub")}`);
  const storedToken = wpGet(WORKER_TOKEN_KEY) || "";
  if (storedToken) applyDynamicManifestStartUrl(storedToken, title);
}

function resolveWorkerCardBrandTitle({ portalDisplayName, companyName } = {}) {
  return String(portalDisplayName || companyName || "").trim() || t("companyFallback");
}

function renderWorkerBrandInitials(mark, brandTitle, accentColor) {
  if (!mark) return;
  const initials = window.TenantBrandIcon?.deriveBrandInitials(brandTitle) || "WP";
  const accent = /^#[0-9a-f]{6}$/i.test(String(accentColor || "").trim()) ? accentColor : "";
  if (accent) {
    mark.style.setProperty("--brand-initials-accent", accent);
    mark.style.background = accent;
  }
  mark.innerHTML = `<span class="wc-brand-initials">${initials.replace(/[<>&"]/g, "")}</span>`;
}

function applyWorkerBrandMarkElement(mark, logoData, brandTitle, accentColor) {
  if (!mark) return;
  const logoSrc = String(logoData || "").trim();
  if (logoSrc) {
    mark.innerHTML = `<img class="wc-brand-logo" src="${logoSrc.replace(/"/g, "&quot;")}" alt="" />`;
    mark.style.removeProperty("background");
    return;
  }
  renderWorkerBrandInitials(mark, brandTitle, accentColor);
}

function applyWorkerLogoMarks(logoData, brandTitle, accentColor) {
  document.querySelectorAll(".wc-brand-mark, .stb-logo-mark").forEach((mark) => {
    applyWorkerBrandMarkElement(mark, logoData, brandTitle, accentColor);
  });
}

function applyWorkerSectorTerms(company = {}) {
  const terms = company.sectorTerms || company.sector_terms || {};
  window.__workerSectorTerms = terms && typeof terms === "object" ? terms : {};
  const sector = String(company.operatingSector || company.operating_sector || "construction").trim();
  if (sector) {
    document.body.setAttribute("data-operating-sector", sector);
  }
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (!key || !window.__workerSectorTerms[key]) return;
    const value = window.__workerSectorTerms[key];
    if (el.hasAttribute("data-i18n-placeholder")) {
      el.placeholder = value;
    } else if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
      el.placeholder = value;
    } else {
      el.textContent = value;
    }
  });
  const smartHubFocus = document.getElementById("smartHubFocusValue");
  if (smartHubFocus && window.__workerSectorTerms.smartHubFocusConstruction) {
    smartHubFocus.textContent = window.__workerSectorTerms.smartHubFocusConstruction;
  }
}

function applyWorkerCompanyBranding({
  companyPreset,
  companyName,
  portalDisplayName,
  brandingAccentColor,
  brandingLogoData,
} = {}) {
  const preset = normalizeCompanyBrandingPreset(companyPreset);
  document.body.setAttribute("data-branding-preset", preset);
  const brandTitle = resolveWorkerCardBrandTitle({ portalDisplayName, companyName });
  applyWorkerBrandLabels(brandTitle);

  const accent = String(brandingAccentColor || "").trim();
  const logoSrc = String(brandingLogoData || "").trim();
  const hasCustomBranding = Boolean(logoSrc) || /^#[0-9a-f]{6}$/i.test(accent);

  if (/^#[0-9a-f]{6}$/i.test(accent)) {
    if (window.TenantBrandIcon?.applyAccentVariables) {
      window.TenantBrandIcon.applyAccentVariables(document.documentElement, accent);
    } else {
      document.documentElement.style.setProperty("--worker-card-accent", accent);
      document.documentElement.style.setProperty("--accent", accent);
      document.documentElement.style.setProperty("--corp-primary", accent);
    }
  } else if (window.TenantBrandIcon?.clearAccentVariables) {
    window.TenantBrandIcon.clearAccentVariables(document.documentElement);
  } else {
    document.documentElement.style.removeProperty("--worker-card-accent");
    document.documentElement.style.removeProperty("--corp-primary");
  }

  applyWorkerLogoMarks(logoSrc, brandTitle, accent);
  const iconHref = resolveWorkerTenantIconHref({
    brandTitle,
    logoData: logoSrc,
    accentColor: accent,
  });
  applyWorkerAppIcons(iconHref, brandTitle);

  document.querySelectorAll(".wallet-card").forEach((card) => {
    card.classList.remove("preset-construction", "preset-industry", "preset-premium", "branding-custom");
    card.classList.add(`preset-${preset}`);
    card.classList.toggle("branding-custom", hasCustomBranding);
    card.style.removeProperty("--worker-card-primary");
    card.style.removeProperty("--worker-card-primary-dark");
    card.style.removeProperty("--worker-card-primary-light");
    if (!/^#[0-9a-f]{6}$/i.test(accent)) {
      card.style.removeProperty("--worker-card-accent");
    } else {
      card.style.setProperty("--worker-card-accent", accent);
      card.style.setProperty("--worker-card-primary", accent);
      card.style.setProperty("--worker-card-primary-dark", shadeHexColor(accent, -35));
      card.style.setProperty("--worker-card-primary-light", shadeHexColor(accent, 40));
    }
  });
}

function applyWorkerBrandingFromCompanyPayload(company = {}, extras = {}) {
  if (!company || typeof company !== "object") return;
  applyWorkerCompanyBranding({
    companyPreset: company.brandingPreset || company.branding_preset || extras.preset,
    companyName: company.name || extras.companyName || "",
    portalDisplayName: company.portalDisplayName || company.portal_display_name || extras.portalDisplayName || "",
    brandingAccentColor: company.brandingAccentColor || company.branding_accent_color || extras.accent || "",
    brandingLogoData: company.brandingLogoData || company.branding_logo_data || extras.logoData || "",
  });
  applyWorkerSectorTerms(company);
}

function applyJoinPreviewBranding(preview) {
  if (!preview || typeof preview !== "object") return;
  applyWorkerBrandingFromCompanyPayload(preview.company || {}, {
    preset: preview.preset || preview.brandingPreset,
    companyName: preview.companyName,
    portalDisplayName: preview.portalDisplayName,
    accent: preview.accent || preview.brandingAccentColor,
    logoData: preview.logoData || preview.brandingLogoData,
  });
}

async function preloadWorkerTenantBranding() {
  try {
    const params = new URLSearchParams(window.location.search);
    const companyId = String(params.get("company_id") || "").trim();
    const accessToken = readBootstrapAccessToken(params);
    const host = window.location.hostname || "";

    if (accessToken && !companyId) {
      const preview = await fetchJoinPreview(accessToken);
      if (preview?.company || preview?.portalDisplayName) {
        applyJoinPreviewBranding(preview);
        return;
      }
    }

    let query = `?host=${encodeURIComponent(host)}`;
    if (companyId) query += `&company_id=${encodeURIComponent(companyId)}`;
    const res = await fetch(`${resolveApiRoot(API_BASE)}/api/public/tenant-branding${query}`, { credentials: "include" });
    if (!res.ok) return;
    const branding = await res.json();
    if (!branding || typeof branding !== "object") return;
    const displayName = String(
      branding.portalDisplayName || branding.companyName || branding.platformName || "",
    ).trim();
    if (!displayName && !branding.logoData && !branding.brandingLogoData) return;
    applyWorkerCompanyBranding({
      companyPreset: branding.preset || branding.brandingPreset,
      companyName: branding.companyName || displayName,
      portalDisplayName: displayName,
      brandingAccentColor: branding.accent || branding.brandingAccentColor || branding.primaryColor,
      brandingLogoData: branding.logoData || branding.brandingLogoData,
    });
  } catch {
    // optional pre-login branding
  }
}

function finishWorkerLoginUi() {
  stopProximityLoginWatcher();
  if (isWorkerCardInstallEntry()) {
    applyWorkerCardInstallView();
    return;
  }
  switchToTab("home");
}

function updateWorkerNextStepPanel({ worker, companyPreset, isVisitor }) {
  if (!elements.workerNextStepPanel) {
    return;
  }

  const siteName = String(worker?.site || "").trim() || t("companyFallback");
  const roleName = String(worker?.role || "").trim() || t("workerDefaultRole");
  const hostName = String(worker?.hostName || "").trim() || t("workerDefaultName");
  const validUntil = String(worker?.validUntil || "").trim();

  let titleKey = "nextStepWorkerTitle";
  let copyKey = "nextStepWorkerCopy";
  let copyArgs = { role: roleName, site: siteName, validUntil };

  if (isVisitor) {
    titleKey = "nextStepVisitorTitle";
    copyKey = "nextStepVisitorCopy";
    copyArgs = { site: siteName, host: hostName, validUntil };
  } else if (companyPreset === "premium") {
    titleKey = "nextStepPremiumTitle";
    copyKey = "nextStepPremiumCopy";
    copyArgs = { role: roleName, site: siteName, validUntil };
  } else if (companyPreset === "industry") {
    titleKey = "nextStepIndustryTitle";
    copyKey = "nextStepIndustryCopy";
    copyArgs = { role: roleName, site: siteName, validUntil };
  } else {
    titleKey = "nextStepConstructionTitle";
    copyKey = "nextStepConstructionCopy";
    copyArgs = { role: roleName, site: siteName, validUntil };
  }

  if (elements.workerNextStepTitle) {
    elements.workerNextStepTitle.textContent = t(titleKey);
  }
  if (elements.workerNextStepCopy) {
    elements.workerNextStepCopy.textContent = tf(copyKey, copyArgs);
  }
}

function formatHoursFromMinutes(totalMin) {
  const safeMin = Math.max(0, Number(totalMin) || 0);
  const hours = Math.floor(safeMin / 60);
  const minutes = safeMin % 60;
  return `${hours}:${String(minutes).padStart(2, "0")}`;
}

function getLocalIsoDate(date = new Date()) {
  const parsed = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getLocalIsoDateFromTimestamp(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "";
  }
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) {
    return raw.slice(0, 10);
  }
  return getLocalIsoDate(parsed);
}

function formatAccessTimeLocal(value) {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    const raw = String(value);
    return raw.length >= 16 ? raw.slice(11, 16) : raw;
  }
  return new Intl.DateTimeFormat(getCurrentLocale(), {
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function extractTodayTimesheetSummary(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return { hasRows: false, totalMin: 0, isOpen: false };
  }

  const today = getLocalIsoDate();
  const todayRows = rows
    .filter((row) => getLocalIsoDateFromTimestamp(row.timestamp) === today)
    .sort((a, b) => String(a.timestamp || "") > String(b.timestamp || "") ? 1 : -1);

  if (todayRows.length === 0) {
    return { hasRows: false, totalMin: 0, isOpen: false };
  }

  const sessions = pairWorkerPresenceSessions(todayRows);
  const totalMin = summarizeWorkerPresenceMinutes(todayRows);
  const isOpen = sessions.some((session) => session.checkIn && !session.checkOut);

  return {
    hasRows: true,
    totalMin,
    isOpen,
  };
}

function getOfflineQueueCount() {
  const photoQueue = readStoredJson(OFFLINE_PHOTO_QUEUE_KEY, []);
  const eventQueue = readStoredJson(OFFLINE_EVENT_QUEUE_KEY, []);
  const photoCount = Array.isArray(photoQueue) ? photoQueue.length : 0;
  const eventCount = Array.isArray(eventQueue) ? eventQueue.length : 0;
  return photoCount + eventCount;
}

function summarizeDocuments(rows, companyPreset) {
  const safeRows = Array.isArray(rows) ? rows : [];
  const today = getLocalIsoDate();
  const soon = new Date();
  soon.setDate(soon.getDate() + 30);
  const soonStr = getLocalIsoDate(soon);
  const expired = safeRows.filter((doc) => doc.expiry_date && doc.expiry_date <= today);
  const expiringSoon = safeRows.filter((doc) => doc.expiry_date && doc.expiry_date > today && doc.expiry_date <= soonStr);
  const presentTypes = new Set(safeRows.map((doc) => String(doc.doc_type || "").trim().toLowerCase()).filter(Boolean));

  const requiredByPreset = {
    construction: ["id_card", "safety_training", "work_permit"],
    industry: ["id_card", "safety_training", "machine_clearance"],
    premium: ["id_card", "compliance_training", "nda"]
  };
  const requiredTypes = requiredByPreset[companyPreset] || requiredByPreset.construction;
  const missingTypes = requiredTypes.filter((type) => !presentTypes.has(type));

  return {
    total: safeRows.length,
    expiredCount: expired.length,
    expiringSoonCount: expiringSoon.length,
    missingTypes,
    criticalCount: expired.length + expiringSoon.length,
  };
}

function getPlannerStorageKey(worker) {
  const badge = normalizeBadgeIdInput(worker?.badgeId || worker?.badge_id || "unknown");
  const dateKey = getLocalIsoDate();
  return `${WORKER_DAY_PLANNER_KEY}:${badge}:${dateKey}`;
}

function buildDayPlannerTasks(timesheetSummary, docsSummary) {
  const hasDocsRisk = (docsSummary.expiredCount + docsSummary.expiringSoonCount) > 0;
  return [
    { id: "checkin", label: t("smartHubPlannerTaskCheckin"), done: timesheetSummary.hasRows },
    { id: "checkout", label: t("smartHubPlannerTaskCheckout"), done: timesheetSummary.hasRows && !timesheetSummary.isOpen },
    { id: "docs", label: t("smartHubPlannerTaskDocs"), done: !hasDocsRisk },
    { id: "safety", label: t("smartHubPlannerTaskSafety"), done: false },
  ];
}

function loadPlannerState(storageKey) {
  return readStoredJson(storageKey, {});
}

function savePlannerState(storageKey, state) {
  writeStoredJson(storageKey, state || {});
}

function renderDayPlanner(payload, timesheetSummary, docsSummary) {
  if (!elements.dayPlannerList || !payload?.worker) {
    return;
  }
  const storageKey = getPlannerStorageKey(payload.worker);
  const savedState = loadPlannerState(storageKey);
  const tasks = buildDayPlannerTasks(timesheetSummary, docsSummary);
  const mergedTasks = tasks.map((task) => ({
    ...task,
    done: typeof savedState[task.id] === "boolean" ? savedState[task.id] : task.done,
  }));

  elements.dayPlannerList.dataset.storageKey = storageKey;
  elements.dayPlannerList.innerHTML = mergedTasks.map((task) => {
    const checked = task.done ? "checked" : "";
    const doneClass = task.done ? " done" : "";
    return `<label class="day-planner-item${doneClass}">
      <input type="checkbox" data-planner-task-id="${escapeHtmlBasic(task.id)}" ${checked} />
      <span class="day-planner-text">${escapeHtmlBasic(task.label)}</span>
    </label>`;
  }).join("");
}

function renderDocumentChecklist(docsSummary) {
  if (!elements.smartHubDocChecklist) {
    return;
  }
  const items = [];
  if (docsSummary.expiredCount > 0) {
    items.push(`<div class="smart-hub-check-item alert">${escapeHtmlBasic(tf("smartHubChecklistExpired", { count: String(docsSummary.expiredCount) }))}</div>`);
  }
  if (docsSummary.expiringSoonCount > 0) {
    items.push(`<div class="smart-hub-check-item warn">${escapeHtmlBasic(tf("smartHubChecklistSoon", { count: String(docsSummary.expiringSoonCount) }))}</div>`);
  }
  if (docsSummary.missingTypes.length > 0) {
    const missing = docsSummary.missingTypes.map((item) => item.replace(/_/g, " ")).join(", ");
    items.push(`<div class="smart-hub-check-item warn">${escapeHtmlBasic(tf("smartHubChecklistMissing", { types: missing }))}</div>`);
  }
  if (!items.length) {
    items.push(`<div class="smart-hub-check-item ok">${escapeHtmlBasic(t("smartHubChecklistOk"))}</div>`);
  }
  elements.smartHubDocChecklist.innerHTML = items.join("");
}

function notifySmartHub(type, title, body) {
  if (!("Notification" in window) || Notification.permission !== "granted") {
    return;
  }
  const today = getLocalIsoDate();
  const key = `${SMART_HUB_NOTIFY_KEY}:${type}:${today}`;
  if (wpGet(key) === "1") {
    return;
  }
  try {
    new Notification(title, { body, tag: `${type}-${today}` });
    wpSet(key, "1");
    
    // Also store in notification history
    addNotificationToHistory({ type, title, body, timestamp: now_iso() });
  } catch {
    // Ignore notification errors in restricted contexts.
  }
}

// ─ ENHANCED NOTIFICATION SYSTEM ─────────────────────────────────────────────
const NOTIFICATION_HISTORY_KEY = WP?.KEYS?.NOTIFICATION_HISTORY || "workpass-notification-history";
const MAX_NOTIFICATIONS_STORED = 50;

function addNotificationToHistory(notif) {
  try {
    const history = JSON.parse(wpGet(NOTIFICATION_HISTORY_KEY) || "[]");
    const newNotif = {
      id: `notif-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      type: notif.type || "general",
      title: notif.title || "",
      body: notif.body || "",
      message: notif.body || "",
      timestamp: notif.timestamp || new Date().toISOString(),
      read: false,
    };
    
    history.unshift(newNotif);
    if (history.length > MAX_NOTIFICATIONS_STORED) {
      history.pop();
    }
    
    wpSet(NOTIFICATION_HISTORY_KEY, JSON.stringify(history));
  } catch (err) {
    console.error("Failed to add notification to history:", err);
  }
}

function getNotificationHistory() {
  try {
    return JSON.parse(wpGet(NOTIFICATION_HISTORY_KEY) || "[]");
  } catch {
    return [];
  }
}

function clearNotificationHistory() {
  wpRemove(NOTIFICATION_HISTORY_KEY);
}

function markNotificationAsRead(notifId) {
  try {
    const history = JSON.parse(wpGet(NOTIFICATION_HISTORY_KEY) || "[]");
    const notif = history.find(n => n.id === notifId);
    if (notif) {
      notif.read = true;
      wpSet(NOTIFICATION_HISTORY_KEY, JSON.stringify(history));
    }
  } catch (err) {
    console.error("Failed to mark notification as read:", err);
  }
}

function dismissLocalNotification(notifId) {
  try {
    const history = getNotificationHistory().filter((entry) => entry.id !== notifId);
    wpSet(NOTIFICATION_HISTORY_KEY, JSON.stringify(history));
  } catch (err) {
    console.error("Failed to dismiss notification:", err);
  }
}

function isNotificationUnread(item) {
  return !item?.isRead && !item?.read;
}

function getUnreadNotifications(items) {
  return (items || []).filter(isNotificationUnread);
}

async function fetchServerNotifications() {
  if (!workerToken) return [];
  try {
    const data = await fetchJson(`${API_BASE}/notifications`, {
      headers: { Authorization: `Bearer ${workerToken}` },
    });
    return Array.isArray(data?.notifications)
      ? data.notifications.filter((row) => String(row?.type || "").toLowerCase() !== "worker_chat_admin")
      : [];
  } catch (err) {
    console.warn("[notifications] server fetch failed:", err?.message || err);
    return [];
  }
}

async function markServerNotificationRead(notifId) {
  if (!workerToken || !notifId) return;
  try {
    await fetchJson(`${API_BASE}/notifications/${encodeURIComponent(notifId)}/mark-read`, {
      method: "POST",
      headers: { Authorization: `Bearer ${workerToken}` },
      body: {},
    });
  } catch (err) {
    console.warn("[notifications] mark-read failed:", err?.message || err);
  }
}

function updateNotificationBadge(count) {
  const badge = elements.notificationBadge;
  if (!badge) return;
  const unread = Math.max(0, Number(count) || 0);
  if (unread > 0) {
    badge.textContent = unread > 9 ? "9+" : String(unread);
    badge.classList.remove("hidden");
  } else {
    badge.textContent = "0";
    badge.classList.add("hidden");
  }
}

function formatNotificationTimestamp(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  try {
    return new Date(raw).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
  } catch {
    return raw;
  }
}

function formatChatTimestamp(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  const locale = getWorkerLang() === "en" ? "en-GB" : "de-DE";
  const timeStr = date.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
  const now = new Date();
  if (date.toDateString() === now.toDateString()) {
    return timeStr;
  }
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) {
    return `${t("chatYesterday")}, ${timeStr}`;
  }
  const dateStr = date.toLocaleDateString(locale, { day: "2-digit", month: "2-digit", year: "numeric" });
  return `${dateStr}, ${timeStr}`;
}

function workerChatReadLabel(msg, side) {
  if (side !== "mine") {
    return "";
  }
  const read = msg.readByRecipient === true || msg.read_by_recipient === true;
  if (read) {
    return `✓✓ ${t("workerChatRead")}`;
  }
  return `✓ ${t("workerChatDelivered")}`;
}

function workerChatSenderSide(msg) {
  const senderType = String(msg?.senderType || msg?.sender_type || "").toLowerCase();
  if (senderType === "worker") {
    return "mine";
  }
  const senderWorkerId = String(msg?.senderWorkerId || msg?.sender_worker_id || "").trim();
  const currentWorkerId = String(lastWorkerPayload?.worker?.id || "").trim();
  if (senderWorkerId && currentWorkerId && senderWorkerId === currentWorkerId) {
    return "mine";
  }
  return "company";
}

function notificationCenterTypeMeta(item) {
  const type = String(item?.type || item?.actionUrl || "").toLowerCase();
  if (type.includes("document") || type.includes("doc") || type.includes("payroll")) {
    return { icon: "📄", label: t("documentsTitle") };
  }
  if (type.includes("chat") || type.includes("message")) {
    return { icon: "💬", label: t("workerChatTitle") };
  }
  return { icon: "🔔", label: t("notificationsCenterTitle") };
}

function renderNotificationCenterList(items) {
  const list = elements.notificationCenterList;
  if (!list) return;
  const unreadItems = getUnreadNotifications(items);
  if (!unreadItems.length) {
    list.innerHTML = `<p class="muted-info notification-center-empty">${escapeHtmlBasic(t("notificationsEmpty"))}</p>`;
    return;
  }
  list.innerHTML = unreadItems
    .map((item) => {
      const title = String(item.title || "").trim() || t("notificationsDefaultTitle");
      const message = String(item.message || item.body || "").trim();
      const createdAt = formatNotificationTimestamp(item.createdAt || item.timestamp);
      const actionUrl = String(item.actionUrl || "").trim().toLowerCase();
      const typeMeta = notificationCenterTypeMeta({ ...item, actionUrl });
      return `
        <button type="button" class="notification-center-item unread" data-notif-id="${escapeHtmlBasic(String(item.id || ""))}" data-notif-action="${escapeHtmlBasic(actionUrl)}">
          <span class="notification-center-item-icon" aria-hidden="true">${typeMeta.icon}</span>
          <span class="notification-center-item-content">
            <span class="notification-center-item-type">${escapeHtmlBasic(typeMeta.label)}</span>
            <span class="notification-center-item-title">${escapeHtmlBasic(title)}</span>
            ${message ? `<span class="notification-center-item-body">${escapeHtmlBasic(message)}</span>` : ""}
            ${createdAt ? `<span class="notification-center-item-time">${escapeHtmlBasic(createdAt)}</span>` : ""}
          </span>
          <span class="notification-center-item-chevron" aria-hidden="true">›</span>
        </button>
      `;
    })
    .join("");
  list.querySelectorAll(".notification-center-item").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const notifId = btn.getAttribute("data-notif-id") || "";
      const action = btn.getAttribute("data-notif-action") || "";
      btn.classList.add("is-dismissing");
      await new Promise((resolve) => window.setTimeout(resolve, 220));
      if (notifId.startsWith("notif-")) {
        await markServerNotificationRead(notifId);
      } else {
        dismissLocalNotification(notifId);
      }
      closeNotificationCenter();
      openWorkerNotificationTarget(action);
      void refreshWorkerNotificationCenter({ silent: true });
    });
  });
}

function refreshTopBarElements() {
  elements.topPanel = document.getElementById("topPanel");
  elements.notificationCenterBtn = document.getElementById("notificationCenterBtn");
  elements.workerDocumentsQuickBtn = document.getElementById("workerDocumentsQuickBtn");
  elements.notificationCenterPanel = document.getElementById("notificationCenterPanel");
  elements.notificationCenterList = document.getElementById("notificationCenterList");
  elements.notificationCenterClose = document.getElementById("notificationCenterClose");
  elements.notificationBadge = document.getElementById("notificationBadge");
  elements.topLogoutButton = document.getElementById("topLogoutButton");
  elements.forceRefreshButton = document.getElementById("forceRefreshButton");
  elements.installButton = document.getElementById("installButton");
}

function bindWorkerLogoutButtons() {
  const selectors = ["#topLogoutButton", "#logoutButton", "#pinLockLogoutButton"];
  selectors.forEach((selector) => {
    const button = document.querySelector(selector);
    if (!button || button.dataset.logoutBound === "1") {
      return;
    }
    button.dataset.logoutBound = "1";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      void workerLogout();
    });
  });
}

function bindTopBarActions() {
  refreshTopBarElements();
  bindWorkerLogoutButtons();
  const topPanel = elements.topPanel;
  if (topPanel && !topPanel.dataset.topBarBound) {
    topPanel.dataset.topBarBound = "1";
    topPanel.addEventListener("click", (event) => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      if (target.closest("#topLogoutButton")) {
        event.preventDefault();
        event.stopPropagation();
        void workerLogout();
        return;
      }
      if (target.closest("#notificationCenterBtn")) {
        event.preventDefault();
        event.stopPropagation();
        openNotificationCenter();
        return;
      }
      if (target.closest("#workerDocumentsQuickBtn")) {
        event.preventDefault();
        event.stopPropagation();
        openWorkerDocumentsQuickScreen();
      }
    });
  }
  if (elements.notificationCenterClose && !elements.notificationCenterClose.dataset.bound) {
    elements.notificationCenterClose.dataset.bound = "1";
    elements.notificationCenterClose.addEventListener("click", closeNotificationCenter);
  }
  if (elements.notificationCenterPanel && !elements.notificationCenterPanel.dataset.bound) {
    elements.notificationCenterPanel.dataset.bound = "1";
    elements.notificationCenterPanel.addEventListener("click", (event) => {
      if (event.target === elements.notificationCenterPanel) {
        closeNotificationCenter();
      }
    });
  }
}

function openNotificationCenter() {
  refreshTopBarElements();
  const panel = elements.notificationCenterPanel || document.getElementById("notificationCenterPanel");
  if (!panel) return;
  panel.classList.remove("hidden");
  panel.setAttribute("aria-hidden", "false");
  document.body.classList.add("notification-center-open");
  void refreshWorkerNotificationCenter();
}

function closeNotificationCenter() {
  const panel = elements.notificationCenterPanel || document.getElementById("notificationCenterPanel");
  if (!panel) return;
  panel.classList.add("hidden");
  panel.setAttribute("aria-hidden", "true");
  document.body.classList.remove("notification-center-open");
}

function openWorkerDocumentsQuickScreen() {
  closeNotificationCenter();
  switchToTab("documents");
  if (workerToken && workerPlanAllowsFeature(WORKER_PLAN_TAB_FEATURES.documents)) {
    void loadMyDocuments();
  }
}

let workerNotificationGreeted = false;

function openWorkerNotificationTarget(action) {
  const raw = String(action || "").trim().toLowerCase();
  if (!raw) return;
  if (
    raw === "documents" ||
    raw === "payroll_document" ||
    raw === "worker_document" ||
    raw.includes("document")
  ) {
    switchToTab("documents");
    void loadMyDocuments();
    return;
  }
  if (raw === "deployment-plan" || raw === "deployment_plan" || raw === "einsatzplan") {
    void openWorkerDeploymentPlanScreen();
    return;
  }
  if (raw === "chat" || raw === "worker_chat" || raw.includes("chat")) {
    void openWorkerChatScreen();
    return;
  }
  if (raw === "leave" || raw === "leave_request" || raw.includes("leave")) {
    switchToTab("vacation");
    if (workerToken) void loadLeaveRequests();
  }
}

async function refreshWorkerNotificationCenter(options = {}) {
  const serverItems = await fetchServerNotifications();
  const localItems = getNotificationHistory().map((entry) => ({
    id: entry.id,
    type: entry.type,
    title: entry.title,
    message: entry.body || entry.message,
    isRead: Boolean(entry.read),
    createdAt: entry.timestamp,
    actionUrl: "",
  }));
  const merged = [...serverItems, ...localItems].slice(0, 50);
  const unreadItems = getUnreadNotifications(merged);
  updateNotificationBadge(unreadItems.length);
  const onHome = currentActiveTab === "home";
  if (workerToken && workerPlanAllowsFeature("worker_chat") && currentActiveTab === "chat") {
    void loadWorkerChat({ quiet: true });
  }
  if (
    options.notifyNew &&
    !workerNotificationGreeted &&
    unreadItems.length > 0 &&
    workerToken
  ) {
    workerNotificationGreeted = true;
    const firstUnread = unreadItems[0];
    const title = String(firstUnread?.title || "").trim() || t("notificationsDefaultTitle");
    showWorkerNotice(tf("notificationsNewArrival", { title }));
  }
  if (!options.silent || !elements.notificationCenterPanel?.classList.contains("hidden")) {
    renderNotificationCenterList(unreadItems);
  }
}

// ─ OFFLINE SYNC CONFLICT DETECTION & RESOLUTION ────────────────────────────
const SYNC_CONFLICTS_KEY = WP?.KEYS?.SYNC_CONFLICTS || "workpass-sync-conflicts";

function reportSyncConflict(conflictType, localData, serverData) {
  try {
    const conflicts = JSON.parse(wpGet(SYNC_CONFLICTS_KEY) || "[]");
    const newConflict = {
      id: `conflict-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      conflictType: conflictType,
      localData: typeof localData === 'string' ? localData : JSON.stringify(localData),
      serverData: typeof serverData === 'string' ? serverData : JSON.stringify(serverData),
      resolution: 'pending',
      createdAt: new Date().toISOString(),
    };
    
    conflicts.unshift(newConflict);
    if (conflicts.length > 20) {
      conflicts.pop();
    }
    
    wpSet(SYNC_CONFLICTS_KEY, JSON.stringify(conflicts));
    return newConflict.id;
  } catch (err) {
    console.error("Failed to report sync conflict:", err);
  }
}

function getSyncConflicts(resolution = 'pending') {
  try {
    const conflicts = JSON.parse(wpGet(SYNC_CONFLICTS_KEY) || "[]");
    return resolution ? conflicts.filter(c => c.resolution === resolution) : conflicts;
  } catch {
    return [];
  }
}

function resolveSyncConflict(conflictId, resolution) {
  try {
    const conflicts = JSON.parse(wpGet(SYNC_CONFLICTS_KEY) || "[]");
    const conflict = conflicts.find(c => c.id === conflictId);
    if (conflict) {
      conflict.resolution = resolution;
      conflict.resolvedAt = new Date().toISOString();
      wpSet(SYNC_CONFLICTS_KEY, JSON.stringify(conflicts));
    }
  } catch (err) {
    console.error("Failed to resolve sync conflict:", err);
  }
}

function autoResolveSyncConflicts(strategy = 'server_win') {
  try {
    const conflicts = JSON.parse(wpGet(SYNC_CONFLICTS_KEY) || "[]");
    conflicts.forEach(c => {
      if (c.resolution === 'pending') {
        c.resolution = strategy;
        c.resolvedAt = new Date().toISOString();
      }
    });
    wpSet(SYNC_CONFLICTS_KEY, JSON.stringify(conflicts));
  } catch (err) {
    console.error("Failed to auto-resolve sync conflicts:", err);
  }
}

function updateSmartWorkHub(payload = lastWorkerPayload, rows = lastTimesheetRows) {
  if (!elements.smartWorkHubCard || !payload) {
    return;
  }

  const worker = payload.worker || {};
  const company = payload.company || {};
  const companyPreset = normalizeCompanyBrandingPreset(company.brandingPreset || company.branding_preset);
  const workerType = String(worker.workerType || "worker").trim().toLowerCase();
  const isVisitor = workerType === "visitor";
  elements.smartWorkHubCard.classList.toggle("hidden", isVisitor);
  if (isVisitor) {
    return;
  }

  const lateInfo = payload.lateCheckIn || {};
  const isLate = Boolean(lateInfo.isLate || lateInfo.late || Number(lateInfo.minutes || lateInfo.minutesLate || 0) > 0);
  const rawStatus = String(worker.status || "").trim().toLowerCase();
  const needsAttention = rawStatus.includes("sperr") || rawStatus.includes("inaktiv") || String(worker.banned || "").trim().toLowerCase() === "true";

  let priorityText = t("smartHubPriorityOnTrack");
  if (offlineWorkerSessionActive) {
    priorityText = t("smartHubPriorityOffline");
  } else if (isLate) {
    priorityText = t("smartHubPriorityLate");
  } else if (needsAttention) {
    priorityText = t("smartHubPriorityAttention");
  }

  let focusText = t("smartHubFocusConstruction");
  if (companyPreset === "industry") focusText = t("smartHubFocusIndustry");
  if (companyPreset === "premium") focusText = t("smartHubFocusPremium");

  const summary = extractTodayTimesheetSummary(rows);
  const hoursLabel = formatHoursFromMinutes(summary.totalMin);
  const momentumText = summary.hasRows
    ? summary.isOpen
      ? tf("smartHubMomentumOpenShift", { hours: hoursLabel })
      : tf("smartHubMomentumClosedShift", { hours: hoursLabel })
    : t("smartHubMomentumPending");

  const docsSummary = summarizeDocuments(lastDocumentRows, companyPreset);
  const queueCount = getOfflineQueueCount();

  let recommendationText = t("smartHubRecommendationTimes");
  let primaryActionLabel = t("smartHubPrimaryActionTimes");
  let primaryActionTarget = "timesheetCard";

  if (!summary.hasRows) {
    recommendationText = t("smartHubRecommendationOpenGate");
    primaryActionLabel = t("smartHubPrimaryActionOpenGate");
    primaryActionTarget = "actionsPanel";
  } else if (summary.isOpen && summary.totalMin >= 9 * 60) {
    recommendationText = t("smartHubRecommendationCheckout");
    primaryActionLabel = t("smartHubPrimaryActionCheckout");
    primaryActionTarget = "timesheetCard";
  }

  if (docsSummary.criticalCount > 0) {
    recommendationText = t("smartHubRecommendationDocs");
    primaryActionLabel = t("smartHubPrimaryActionDocs");
    primaryActionTarget = "documentsCard";
  }

  if (elements.smartHubPriorityValue) elements.smartHubPriorityValue.textContent = priorityText;
  if (elements.smartHubFocusValue) elements.smartHubFocusValue.textContent = focusText;
  if (elements.smartHubMomentumValue) elements.smartHubMomentumValue.textContent = momentumText;
  if (elements.smartHubRecommendationText) elements.smartHubRecommendationText.textContent = recommendationText;
  if (elements.smartHubPrimaryActionBtn) {
    elements.smartHubPrimaryActionBtn.textContent = primaryActionLabel;
    elements.smartHubPrimaryActionBtn.setAttribute("data-worker-page-target", primaryActionTarget);
  }
  if (elements.smartHubSyncQueueValue) {
    elements.smartHubSyncQueueValue.textContent = String(queueCount);
  }
  if (elements.smartHubSyncQueueMeta) {
    elements.smartHubSyncQueueMeta.textContent = queueCount > 0
      ? tf("smartHubSyncQueuePending", { count: String(queueCount) })
      : t("smartHubSyncQueueMeta");
  }
  if (elements.manualSyncBtn) {
    try {
      const isWorkerMode = new URLSearchParams(window.location.search).get("worker") === "1";
      const hasOfflineData = queueCount > 0 || (Array.isArray(readStoredJson(OFFLINE_PHOTO_QUEUE_KEY, [])) && readStoredJson(OFFLINE_PHOTO_QUEUE_KEY, []).length > 0);
      const canSync = navigator.onLine && !!workerToken;
      elements.manualSyncBtn.classList.toggle("hidden", !(isWorkerMode && hasOfflineData && canSync));
    } catch (e) {
      // ignore
    }
  }
  if (elements.smartHubDocRiskValue) {
    elements.smartHubDocRiskValue.textContent = String(docsSummary.criticalCount);
  }
  if (elements.smartHubDocRiskMeta) {
    elements.smartHubDocRiskMeta.textContent = docsSummary.criticalCount > 0
      ? tf("smartHubDocRiskAlert", { count: String(docsSummary.criticalCount) })
      : t("smartHubDocRiskMeta");
  }
  if (elements.smartHubCrewValue) {
    const crew = payload.teamSnapshot || {};
    const present = Number(crew.present || 0);
    const expected = Number(crew.expected || 0);
    const openCheckouts = Number(crew.openCheckouts || 0);
    if (expected > 0) {
      elements.smartHubCrewValue.textContent = tf("smartHubCrewLive", {
        present: String(present),
        expected: String(expected)
      });
      if (elements.smartHubCrewMeta) {
        elements.smartHubCrewMeta.textContent = tf("smartHubCrewOpen", { open: String(openCheckouts) });
      }
    } else {
      elements.smartHubCrewValue.textContent = "--";
      if (elements.smartHubCrewMeta) {
        elements.smartHubCrewMeta.textContent = t("smartHubCrewMeta");
      }
    }
  }

  renderDayPlanner(payload, summary, docsSummary);
  renderDocumentChecklist(docsSummary);

  if (summary.isOpen && summary.totalMin >= 9 * 60) {
    notifySmartHub("checkout", t("smartHubNotifyCheckoutTitle"), t("smartHubNotifyCheckoutBody"));
  }
  if (docsSummary.criticalCount > 0) {
    notifySmartHub("docs", t("smartHubNotifyDocsTitle"), t("smartHubNotifyDocsBody"));
  }
  if (isLate) {
    notifySmartHub("late", t("smartHubNotifyLateTitle"), t("smartHubNotifyLateBody"));
  }
}

function applyTranslations() {
  const lang = currentLang;
  const dir = LANG_META[lang]?.dir || "ltr";
  document.documentElement.lang = lang;
  document.documentElement.dir = dir;
  // Use company brand title (KontrolPass/SUPPIX) if already loaded, otherwise fallback to i18n key
  const brandPrefix = currentAppBrandTitle || "";
  document.title = brandPrefix ? `${brandPrefix} – ${t("splashSub")}` : t("pageTitle");

  const langSelect = document.querySelector("#workerLanguageSelect");
  if (langSelect && langSelect.value !== lang) {
    langSelect.value = lang;
  }

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    const attr = el.dataset.i18nAttr;
    // Skip brand title elements – managed dynamically by renderWorker()
    if (!attr && el.id && [
      "workerAppTitle",
      "workerBrandChip",
      "workerSplashTitle",
      "workerBrandName",
      "dashboardBrandName",
      "visitorBrandName",
      "workerChatSectionTitle",
    ].includes(el.id)) {
      return;
    }
    if (el.classList.contains("login-copy-sparkasse") && document.body.classList.contains("qr-fast-login")) {
      const badgeLabel = normalizeBadgeIdInput(elements.workerAccessToken?.value || "");
      if (badgeLabel) {
        el.textContent = tf("loginCopyQrFast", { badge: badgeLabel });
        return;
      }
    }
    if (attr) {
      el.setAttribute(attr, t(key));
    } else {
      el.textContent = t(key);
    }
  });
  // Re-apply company brand label after translations
  if (currentAppBrandTitle) {
    applyWorkerBrandLabels(currentAppBrandTitle);
  }
  if (lastWorkerPayload?.company) {
    applyWorkerSectorTerms(lastWorkerPayload.company);
  }
  updateWorkerHubToggleLabel();
}

function setLang(lang) {
  if (!isSupportedLang(lang)) return;
  const nextLang = setCurrentLang(lang, WORKER_LANG_KEY);
  if (!nextLang) return;
  currentLang = nextLang;
  applyTranslations();
  if (typeof I18N_RUNTIME.applyDomTranslations === "function") {
    I18N_RUNTIME.applyDomTranslations(document);
  }
  updateLastSyncDisplay();
  updateConnectionState();
  updatePlatformInstallHint();
  applyQrContrastState();
  if (workerToken) {
    void loadWorkerData();
  }
}
// ─────────────────────────────────────────────────────────────────────

let workerToken = "";
let workerBearerToken = "";
let workerLoginInFlight = false;
let showcaseTimeoutId = null;
let currentActiveTab = "home";
let bottomTabNavInitialized = false;
// One-time QR/link codes must not survive a cold start; bearer session may persist for PWA/offline sync.
wpRemove(WORKER_ACCESS_TOKEN_KEY);
const __workerBootParams = new URLSearchParams(window.location.search);
if (isQrBootstrapEntry(__workerBootParams)) {
  resetWorkerSessionForQrEntry({ keepBadge: true });
} else {
  workerToken = (wpGet(WORKER_TOKEN_KEY) || "").trim();
  workerBearerToken = (wpGet(WORKER_JWT_KEY) || workerToken || "").trim();
}
let deferredInstallPrompt = null;
let cameraStream = null;
let lastCameraPhotoDataUrl = null;
let lastCameraPhotoRotation = 0;
let wakeLockHandle = null;
let dynamicManifestUrl = "";
let currentAppBrandTitle = ""; // tracks the company-specific brand label
let currentWorkerIconHref = "";
let workerSessionExpiryTimeout = null;
let workerSessionCountdownInterval = null;

let inactivityCheckInterval = null;
let qrHighContrastEnabled = wpGet(QR_HIGH_CONTRAST_KEY) === "1";
let sessionExpiringSoonNotified = false;
let ambientLightSensorHandle = null;
let ambientLowLightRecommended = false;
let gateAutoOpenTriggered = false;
let lastUserInteractionAt = Date.now();
let autoOpenScannerEnabled = wpGet(AUTO_OPEN_SCANNER_KEY) !== "0";
let offlineWorkerSessionActive = false;
let siteGeofenceWatchTimer = null;
let siteOffSiteStrikeCount = 0;
let siteGeofenceLeaveInProgress = false;
let lastSitePresenceNoticeKey = "";
let siteAccessGateModeNoticeShown = false;
let lastSiteAccessCfg = null;
let proximityLoginWatchTimer = null;
let proximityInsideSince = 0;
let proximityLoginInProgress = false;
let proximityLoginNoticeShownAt = 0;
let proximitySiteHintCache = null;
let proximitySiteHintCacheBadgeId = "";
let pinLockEnabled = false; // Wird vom Backend gesetzt
let isPassLocked = false; // Aktueller Status
let lastPassInteractionAt = Date.now();
let passLockTimer = null;
let lastSubmittedLeaveRequestId = "";
let leaveRefreshInterval = null;
let quickMenuObserver = null;
let activeWorkerPageTarget = "";
let iosWalletImmersive = false;
let workerHubExpanded = false;
let timesheetCompactExpanded = false;
let documentsCompactExpanded = false;
let leaveCompactExpanded = false;
let workerLastSyncAt = null;
let batteryLevelPct = null;
let batteryCharging = null;
let lastWorkerPayload = null;
let lastTimesheetRows = [];
let lastDocumentRows = [];
// ── Dynamic QR state ─────────────────────────────────────────────────────────
let dqrCountdownInterval = null; // setInterval for per-second countdown
let dqrRemainingSeconds = 60;    // seconds until next QR refresh
let dqrCurrentToken = "";        // last fetched DQR token
let dqrWorkerBadgeId = "";       // fallback static badge id
let dqrWindowSeconds = 60;        // full token lifetime window from backend
let dqrRefreshTimeout = null;     // adaptive refresh timer
let gateFeedbackResetTimeout = null;
let gateEventPollTimeout = null;
let gateEventPollInFlight = false;
let gateLastSeenEventId = "";
let workerChatThreadId = "";
let workerChatPollTimer = null;
let workerNotificationPollTimer = null;

const elements = {
  loginCard: document.querySelector("#loginCard"),
  badgeCard: document.querySelector("#badgeCard"),
  workerNotice: document.querySelector("#workerNotice"),
  workerResumeLoginRow: document.querySelector("#workerResumeLoginRow"),
  workerResumeLoginButton: document.querySelector("#workerResumeLoginButton"),
  workerLoginForm: document.querySelector("#workerLoginForm"),
  workerAccessToken: document.querySelector("#workerAccessToken"),
  workerBadgePin: document.querySelector("#workerBadgePin"),
  companyName: document.querySelector("#companyName"),
    workerSubcompany: document.querySelector("#workerSubcompany"),
  workerName: document.querySelector("#workerName"),
  workerRole: document.querySelector("#workerRole"),
  workerPassTitle: document.querySelector("#workerPassTitle"),
  workerNextStepPanel: document.querySelector("#workerNextStepPanel"),
  workerNextStepTitle: document.querySelector("#workerNextStepTitle"),
  workerNextStepCopy: document.querySelector("#workerNextStepCopy"),
  smartWorkHubCard: document.querySelector("#smartWorkHubCard"),
  smartHubPriorityValue: document.querySelector("#smartHubPriorityValue"),
  smartHubFocusValue: document.querySelector("#smartHubFocusValue"),
  smartHubMomentumValue: document.querySelector("#smartHubMomentumValue"),
  smartHubRecommendationText: document.querySelector("#smartHubRecommendationText"),
  smartHubPrimaryActionBtn: document.querySelector("#smartHubPrimaryActionBtn"),
  smartHubSyncQueueValue: document.querySelector("#smartHubSyncQueueValue"),
  smartHubSyncQueueMeta: document.querySelector("#smartHubSyncQueueMeta"),
  manualSyncBtn: document.querySelector("#manualSyncBtn"),
  smartHubDocRiskValue: document.querySelector("#smartHubDocRiskValue"),
  smartHubDocRiskMeta: document.querySelector("#smartHubDocRiskMeta"),
  smartHubCrewValue: document.querySelector("#smartHubCrewValue"),
  smartHubCrewMeta: document.querySelector("#smartHubCrewMeta"),
  dayPlannerList: document.querySelector("#dayPlannerList"),
  dayPlannerResetBtn: document.querySelector("#dayPlannerResetBtn"),
  smartHubDocChecklist: document.querySelector("#smartHubDocChecklist"),
  workerPassSubLabels: document.querySelectorAll("[data-pass-sub-label]"),
  walletCard: document.querySelector("#badgeCard .wallet-card"),
  workerStatus: document.querySelector("#workerStatus"),
  workerPhoto: document.querySelector("#workerPhoto"),
  workerBadgeId: document.querySelector("#workerBadgeId"),
  workerSite: document.querySelector("#workerSite"),
  workerSiteMapLink: document.querySelector("#workerSiteMapLink"),
  workerValidUntil: document.querySelector("#workerValidUntil"),
  workerDayCardValidity: document.querySelector("#workerDayCardValidity"),
  workerVisitorMeta: document.querySelector("#workerVisitorMeta"),
  workerVisitorCompany: document.querySelector("#workerVisitorCompany"),
  workerVisitPurpose: document.querySelector("#workerVisitPurpose"),
  workerHostName: document.querySelector("#workerHostName"),
  workerVisitEndAt: document.querySelector("#workerVisitEndAt"),
  workerQr: document.querySelector("#workerQr"),
  workerSessionCountdown: document.querySelector("#workerSessionCountdown"),
  autoOpenScannerToggle: document.querySelector("#autoOpenScannerToggle"),
  qrContrastToggle: document.querySelector("#qrContrastToggle"),
  qrFallbackText: document.querySelector("#qrFallbackText"),
  refreshButton: document.querySelector("#refreshButton"),
  logoutButton: document.querySelector("#logoutButton"),
  topLogoutButton: document.querySelector("#topLogoutButton"),
  topPanel: document.querySelector("#topPanel"),
  installButton: document.querySelector("#installButton"),
  forceRefreshButton: document.querySelector("#forceRefreshButton"),
  installPlatformHint: document.querySelector("#installPlatformHint"),
  gateModeButton: document.querySelector("#gateModeButton"),
  quickGateModeButton: document.querySelector("#quickGateModeButton"),
  gateScannerOverlay: document.querySelector("#gateScannerOverlay"),
  gateQr: document.querySelector("#gateQr"),
  gateBadgeId: document.querySelector("#gateBadgeId"),
  gateWorkerName: document.querySelector("#gateWorkerName"),
  gateBrightnessHint: document.querySelector("#gateBrightnessHint"),
  closeGateModeButton: document.querySelector("#closeGateModeButton"),
  changePhotoButton: document.querySelector("#changePhotoButton"),
  photoInput: document.querySelector("#photoInput"),
  cameraOverlay: document.querySelector("#cameraOverlay"),
  cameraVideo: document.querySelector("#cameraVideo"),
  cameraCanvas: document.querySelector("#cameraCanvas"),
  takePhotoButton: document.querySelector("#takePhotoButton"),
  confirmPhotoButton: document.querySelector("#confirmPhotoButton"),
  retakePhotoButton: document.querySelector("#retakePhotoButton"),
  closeCameraButton: document.querySelector("#closeCameraButton"),
  photoPreviewWrap: document.querySelector("#photoPreviewWrap"),
  rotatePhotoButton: document.querySelector("#rotatePhotoButton"),
  deletePhotoButton: document.querySelector("#deletePhotoButton"),
  workerStatusBanner: document.querySelector("#workerStatusBanner"),
  workerStatusText: document.querySelector("#workerStatusText"),
  gateStatusFeedback: document.querySelector("#gateStatusFeedback"),
  gateContrastToggle: document.querySelector("#gateContrastToggle"),
  connectionBanner: document.querySelector("#connectionBanner"),
  connectionStatusLabel: document.querySelector("#connectionStatusLabel"),
  lastSyncInfo: document.querySelector("#lastSyncInfo"),
  workerBuildBadge: document.querySelector("#workerBuildBadge"),
  workerPulsePanel: document.querySelector("#workerPulsePanel"),
  pulseNetworkValue: document.querySelector("#pulseNetworkValue"),
  pulseNetworkMeta: document.querySelector("#pulseNetworkMeta"),
  pulseSyncValue: document.querySelector("#pulseSyncValue"),
  pulseSyncMeta: document.querySelector("#pulseSyncMeta"),
  pulsePowerValue: document.querySelector("#pulsePowerValue"),
  pulsePowerMeta: document.querySelector("#pulsePowerMeta"),
  pulseFlowValue: document.querySelector("#pulseFlowValue"),
  pulseFlowMeta: document.querySelector("#pulseFlowMeta"),
  pinLockOverlay: document.querySelector("#pinLockOverlay"),
  pinLockForm: document.querySelector("#pinLockForm"),
  pinLockInput: document.querySelector("#pinLockInput"),
  pinLockError: document.querySelector("#pinLockError"),
  pinLockLogoutButton: document.querySelector("#pinLockLogoutButton"),
  geolocationHint: document.querySelector("#geolocationHint"),
  themeToggleBtn: document.querySelector("#themeToggleBtn"),
  voiceCommandBtn: document.querySelector("#voiceCommandBtn"),
  notificationPermissionBtn: document.querySelector("#notificationPermissionBtn"),
  enableNotificationsBtn: document.querySelector("#enableNotificationsBtn"),
  notificationBanner: document.querySelector("#notificationBanner"),
  notificationCenterBtn: document.querySelector("#notificationCenterBtn"),
  workerDocumentsQuickBtn: document.querySelector("#workerDocumentsQuickBtn"),
  notificationCenterPanel: document.querySelector("#notificationCenterPanel"),
  notificationCenterList: document.querySelector("#notificationCenterList"),
  notificationCenterClose: document.querySelector("#notificationCenterClose"),
  notificationBadge: document.querySelector("#notificationBadge"),
  leaveRequestCard: document.querySelector("#leaveRequestCard"),
  leaveRequestForm: document.querySelector("#leaveRequestForm"),
  leaveRequestFormWrapper: document.querySelector("#leaveRequestFormWrapper"),
  leaveRequestListWrapper: document.querySelector("#leaveRequestListWrapper"),
  leaveRequestList: document.querySelector("#leaveRequestList"),
  leaveRequestToggleBtn: document.querySelector("#leaveRequestToggleBtn"),
  leaveRequestType: document.querySelector("#leaveRequestType"),
  leaveRequestStart: document.querySelector("#leaveRequestStart"),
  leaveRequestEnd: document.querySelector("#leaveRequestEnd"),
  leaveRequestNote: document.querySelector("#leaveRequestNote"),
  leaveRequestAiBtn: document.querySelector("#leaveRequestAiBtn"),
  leaveRequestBossEmail: document.querySelector("#leaveRequestBossEmail"),
  incidentCard: document.querySelector("#incidentCard"),
  incidentForm: document.querySelector("#incidentForm"),
  incidentType: document.querySelector("#incidentType"),
  incidentSeverity: document.querySelector("#incidentSeverity"),
  incidentDescription: document.querySelector("#incidentDescription"),
  incidentList: document.querySelector("#incidentList"),
  walletAppleBtn: document.querySelector("#walletAppleBtn"),
  walletGoogleBtn: document.querySelector("#walletGoogleBtn"),
  workerHubToggle: document.querySelector("#workerHubToggle"),
  workerHubPanel: document.querySelector("#workerHubPanel"),
  workerMenuCard: document.querySelector("#workerMenuCard"),
  workerQuickMenu: document.querySelector("#workerQuickMenu"),
  quickMenuButtons: document.querySelectorAll(".quick-menu-btn"),
  workerMenuButtons: document.querySelectorAll("[data-worker-page-target]"),
  workerPageNav: document.querySelector("#workerPageNav"),
  workerPageBackButton: document.querySelector("#workerPageBackButton"),
  workerPageLabel: document.querySelector("#workerPageLabel"),
  sendToBossPanel: document.querySelector("#sendToBossPanel"),
  bossEmailInput: document.querySelector("#bossEmailInput"),
  sendToBossBtn: document.querySelector("#sendToBossBtn"),
  timesheetCard: document.querySelector("#timesheetCard"),
  timesheetList: document.querySelector("#timesheetList"),
  timesheetRefreshBtn: document.querySelector("#timesheetRefreshBtn"),
  dailyInsightsCard: document.querySelector("#dailyInsightsCard"),
  dailyCheckinsValue: document.querySelector("#dailyCheckinsValue"),
  dailyCheckoutsValue: document.querySelector("#dailyCheckoutsValue"),
  dailyHoursValue: document.querySelector("#dailyHoursValue"),
  dailyBalanceValue: document.querySelector("#dailyBalanceValue"),
  companyModeCard: document.querySelector("#companyModeCard"),
  companyModeTitle: document.querySelector("#companyModeTitle"),
  companyModeLead: document.querySelector("#companyModeLead"),
  companyModeFeatureList: document.querySelector("#companyModeFeatureList"),
  documentsCard: document.querySelector("#documentsCard"),
  documentsList: document.querySelector("#documentsList"),
  chatCard: document.querySelector("#chatCard"),
  workerChatMessages: document.querySelector("#workerChatMessages"),
  workerChatInput: document.querySelector("#workerChatInput"),
  workerChatSendBtn: document.querySelector("#workerChatSendBtn"),
  workerChatFileInput: document.querySelector("#workerChatFileInput"),
  workerChatFileHint: document.querySelector("#workerChatFileHint"),
  deploymentPlanCard: document.querySelector("#deploymentPlanCard"),
  deploymentPlanList: document.querySelector("#deploymentPlanList"),
  deploymentPlanMonthSelect: document.querySelector("#deploymentPlanMonthSelect"),
  deploymentPlanMeta: document.querySelector("#deploymentPlanMeta"),
  deploymentPlanPdfBtn: document.querySelector("#deploymentPlanPdfBtn"),
  deploymentPlanPrintBtn: document.querySelector("#deploymentPlanPrintBtn"),
  workerAiCard: document.querySelector("#workerAiCard"),
  workerAiLog: document.querySelector("#workerAiLog"),
  workerAiForm: document.querySelector("#workerAiForm"),
  workerAiQuestion: document.querySelector("#workerAiQuestion"),
  workerAiVoiceBtn: document.querySelector("#workerAiVoiceBtn"),
};

const splashStartedAt = performance.now();
const SPLASH_MIN_MS = 0;

function dismissSplash() {
  if (document.body.dataset.splashDismissed === "1") {
    return;
  }
  document.body.dataset.splashDismissed = "1";
  const elapsed = performance.now() - splashStartedAt;
  const delay = Math.max(0, SPLASH_MIN_MS - elapsed);
  setTimeout(() => {
    document.body.classList.add("splash-released");
    const el = document.getElementById("splashScreen");
    if (!el) return;
    el.classList.add("splash-done");
    el.addEventListener("transitionend", () => el.remove(), { once: true });
    setTimeout(() => { if (el.parentNode) el.remove(); }, 800);
  }, delay);
}

function releaseSplashEarly() {
  dismissSplash();
}

function updateWorkerBuildBadge() {
  if (!elements.workerBuildBadge) {
    return;
  }

  const modeLabel = isStandaloneDisplay() ? "Home" : "Web";
  const swActive = Boolean(navigator.serviceWorker && navigator.serviceWorker.controller);
  const swLabel = swActive ? "SW On" : "SW Off";
  elements.workerBuildBadge.textContent = `Build ${WORKER_BUILD_TAG} | ${modeLabel} | ${swLabel}`;
}

function updateLastSyncDisplay() {
  if (!elements.lastSyncInfo) {
    return;
  }
  if (!workerLastSyncAt) {
    elements.lastSyncInfo.textContent = t("lastSyncInitial");
    return;
  }
  const formatted = new Intl.DateTimeFormat(getCurrentLocale(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(workerLastSyncAt);
  elements.lastSyncInfo.textContent = `${t("lastSync")}: ${formatted}`;
}

function markWorkerSyncedNow() {
  workerLastSyncAt = new Date();
  updateLastSyncDisplay();
}

function getFlowStateLabel() {
  if (!workerToken) {
    return t("pulseFlowLogin");
  }
  if (activeWorkerPageTarget) {
    const pageName = getWorkerPageTitle(activeWorkerPageTarget);
    return pageName.length > 14 ? `${pageName.slice(0, 14)}...` : pageName;
  }
  return t("pulseFlowDashboard");
}

function updateWorkerPulsePanel() {
  if (!elements.workerPulsePanel) {
    return;
  }

  const networkOnline = navigator.onLine;
  const minutesSinceSync = workerLastSyncAt ? Math.max(0, Math.floor((Date.now() - workerLastSyncAt.getTime()) / 60000)) : null;
  const syncFresh = minutesSinceSync !== null && minutesSinceSync <= 5;
  const syncStale = minutesSinceSync !== null && minutesSinceSync > 30;
  const powerLow = typeof batteryLevelPct === "number" && batteryLevelPct <= 20 && batteryCharging === false;
  const flowLabel = getFlowStateLabel();

  if (elements.pulseNetworkValue) {
    elements.pulseNetworkValue.textContent = networkOnline ? t("online") : t("offline");
  }
  if (elements.pulseNetworkMeta) {
    elements.pulseNetworkMeta.textContent = networkOnline ? t("pulseNetworkLive") : t("pulseNetworkCache");
  }
  if (elements.pulseSyncValue) {
    if (minutesSinceSync === null) {
      elements.pulseSyncValue.textContent = "-";
    } else if (minutesSinceSync === 0) {
      elements.pulseSyncValue.textContent = t("pulseSyncNow");
    } else {
      elements.pulseSyncValue.textContent = `${minutesSinceSync}m`;
    }
  }
  if (elements.pulseSyncMeta) {
    if (minutesSinceSync === null) {
      elements.pulseSyncMeta.textContent = t("pulseSyncPending");
    } else if (syncFresh) {
      elements.pulseSyncMeta.textContent = t("pulseSyncFresh");
    } else if (syncStale) {
      elements.pulseSyncMeta.textContent = t("pulseSyncNeedsRefresh");
    } else {
      elements.pulseSyncMeta.textContent = t("pulseSyncStable");
    }
  }
  if (elements.pulsePowerValue) {
    elements.pulsePowerValue.textContent = typeof batteryLevelPct === "number" ? `${batteryLevelPct}%` : "--%";
  }
  if (elements.pulsePowerMeta) {
    if (batteryCharging === true) {
      elements.pulsePowerMeta.textContent = t("pulsePowerCharging");
    } else if (batteryCharging === false) {
      elements.pulsePowerMeta.textContent = powerLow ? t("pulsePowerLow") : t("pulsePowerOk");
    } else {
      elements.pulsePowerMeta.textContent = t("pulsePowerUnknown");
    }
  }
  if (elements.pulseFlowValue) {
    elements.pulseFlowValue.textContent = flowLabel;
  }
  if (elements.pulseFlowMeta) {
    elements.pulseFlowMeta.textContent = isStandaloneDisplay() ? t("pulseFlowAppMode") : t("pulseFlowWebMode");
  }

  const networkItem = elements.workerPulsePanel.querySelector(".pulse-item-network");
  const syncItem = elements.workerPulsePanel.querySelector(".pulse-item-sync");
  const powerItem = elements.workerPulsePanel.querySelector(".pulse-item-power");
  const flowItem = elements.workerPulsePanel.querySelector(".pulse-item-flow");

  networkItem?.classList.toggle("is-offline", !networkOnline);
  syncItem?.classList.toggle("is-fresh", syncFresh);
  syncItem?.classList.toggle("is-stale", syncStale);
  powerItem?.classList.toggle("is-low", powerLow);
  flowItem?.classList.toggle("is-active", Boolean(workerToken));
}

function initBatteryTelemetry() {
  if (!navigator.getBattery) {
    updateWorkerPulsePanel();
    return;
  }
  navigator.getBattery().then((battery) => {
    const applyBatteryState = () => {
      batteryLevelPct = Math.round((battery.level || 0) * 100);
      batteryCharging = Boolean(battery.charging);
      updateWorkerPulsePanel();
    };
    applyBatteryState();
    battery.addEventListener("levelchange", applyBatteryState);
    battery.addEventListener("chargingchange", applyBatteryState);
  }).catch(() => {
    updateWorkerPulsePanel();
  });
}

function focusWorkerPassOnLoad() {
  const target = elements.badgeCard;
  if (!target) {
    return;
  }

  const scrollToPass = () => {
    try {
      target.scrollIntoView({ behavior: "auto", block: "start" });
    } catch {
      window.scrollTo(0, 0);
    }
  };

  window.scrollTo(0, 0);
  if ("requestAnimationFrame" in window) {
    window.requestAnimationFrame(scrollToPass);
    window.requestAnimationFrame(scrollToPass);
  } else {
    scrollToPass();
  }
}

let vapidMissingLogged = false;
let userHasGestured = false;
let hapticUnlocked = false;

function markUserInteraction() {
  lastUserInteractionAt = Date.now();
  userHasGestured = true;
}

function unlockHaptic() {
  hapticUnlocked = true;
  userHasGestured = true;
  lastUserInteractionAt = Date.now();
}

function isIosDevice() {
  const ua = navigator.userAgent || "";
  return /iPhone|iPad|iPod/i.test(ua);
}

function isStandaloneDisplay() {
  return Boolean(window.matchMedia?.("(display-mode: standalone)")?.matches) || Boolean(window.navigator.standalone);
}

function shouldTreatLoginAsQrLaunch(params = null) {
  return isQrLaunchLogin(params)
    || document.body.classList.contains("qr-fast-login")
    || isStandaloneDisplay();
}

function updateWalletImmersiveMode() {
  iosWalletImmersive = isIosDevice() && isStandaloneDisplay() && Boolean(workerToken);
  document.body.classList.toggle("wallet-immersive", iosWalletImmersive);
  if (iosWalletImmersive) {
    applyWorkerPageView("badgeCard");
  }
}

function isWorkerCardInstallEntry() {
  try {
    return (new URLSearchParams(window.location.search).get("view") || "").toLowerCase() === "card";
  } catch {
    return false;
  }
}

function replaceWorkerHistoryAfterLogin() {
  try {
    document.body.classList.remove("qr-fast-login");
    const next = new URL(window.location.href);
    next.searchParams.set("worker", "1");
    next.searchParams.set("v", WORKER_BUILD_TAG);
    next.searchParams.set("session", "1");
    next.searchParams.delete("access");
    next.searchParams.delete("badge");
    next.searchParams.delete("fast");
    next.searchParams.delete("launch");
    next.searchParams.delete("apiBase");
    next.searchParams.delete("refresh");
    window.history.replaceState({}, document.title, next.toString());
  } catch {
    window.history.replaceState({}, document.title, `./emp-app.html?worker=1&session=1&v=${WORKER_BUILD_TAG}`);
  }
}

function clearQrBootstrapUiState() {
  document.body.classList.remove("qr-fast-login");
  const pinInput = elements.workerBadgePin || document.querySelector("#workerBadgePin");
  if (pinInput) {
    pinInput.dataset.qrAutoSubmitting = "0";
  }
}

function getWorkerPassStage() {
  return elements.badgeCard?.querySelector(".pass-stage") || null;
}

function syncHomeCompactInfo(payload) {
  if (!payload) return;
  const worker = payload.worker || {};
  const company = payload.company || {};
  const brandTitle = resolveWorkerCardBrandTitle({
    portalDisplayName: company.portalDisplayName || company.portal_display_name,
    companyName: company.name || "",
  });
  const homeInfoStatus = document.getElementById("homeInfoStatus");
  const homeInfoSite = document.getElementById("homeInfoSite");
  const homeInfoCompany = document.getElementById("homeInfoCompany");
  const homeInfoValidUntil = document.getElementById("homeInfoValidUntil");
  const statusText = elements.workerStatus?.textContent || worker.status || "Aktiv";
  if (homeInfoStatus) {
    homeInfoStatus.textContent = statusText;
  }
  if (homeInfoSite) {
    const siteText = elements.workerSite?.textContent || worker.site || "-";
    homeInfoSite.textContent = siteText;
    if (elements.workerSite instanceof HTMLAnchorElement) {
      homeInfoSite.href = elements.workerSite.getAttribute("href") || "#";
      if (elements.workerSite.getAttribute("aria-disabled") === "true") {
        homeInfoSite.setAttribute("aria-disabled", "true");
      } else {
        homeInfoSite.removeAttribute("aria-disabled");
      }
    }
  }
  if (homeInfoCompany) {
    homeInfoCompany.textContent = brandTitle || t("companyFallback");
  }
  if (homeInfoValidUntil) {
    const validText = elements.workerValidUntil?.textContent || formatDate(worker.validUntil) || "-";
    homeInfoValidUntil.textContent = validText;
  }
}

function updateWorkHoursBannerVisibility(tabName = currentActiveTab) {
  const banner = document.getElementById("workerWorkHoursBanner");
  if (!banner || !lastSiteAccessCfg?.siteApp) {
    return;
  }
  banner.classList.toggle("hidden", tabName !== "home");
}

function bindWorkerFeatureTabActions() {
  if (document.body.dataset.featureTabActionsBound === "1") {
    return;
  }
  document.body.dataset.featureTabActionsBound = "1";
  document.addEventListener("click", (event) => {
    const backBtn = event.target instanceof Element ? event.target.closest("#workerPageBackButton") : null;
    if (backBtn) {
      event.preventDefault();
      event.stopPropagation();
      switchToTab("home");
      return;
    }
    const leaveToggle = event.target instanceof Element ? event.target.closest("#leaveRequestToggleBtn") : null;
    if (leaveToggle) {
      event.preventDefault();
      event.stopPropagation();
      toggleLeaveRequestForm();
    }
  });
}

function bindWorkerChatMessageActions() {
  const host = elements.workerChatMessages || document.getElementById("workerChatMessages");
  if (!host || host.dataset.chatActionsBound === "1") {
    return;
  }
  host.dataset.chatActionsBound = "1";
  host.addEventListener("click", (event) => {
    const deleteBtn = event.target instanceof Element ? event.target.closest("[data-chat-delete-id]") : null;
    if (!deleteBtn) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const messageId = deleteBtn.getAttribute("data-chat-delete-id") || "";
    if (messageId) {
      void deleteWorkerChatMessage(messageId);
    }
  });
}

async function deleteWorkerChatMessage(messageId) {
  if (!workerToken || !messageId) {
    return;
  }
  try {
    await fetchJson(`${API_BASE}/chat/messages/${encodeURIComponent(messageId)}`, {
      method: "DELETE",
      headers: buildWorkerAuthHeaders(),
    });
    await loadWorkerChat();
    showWorkerNotice(t("workerChatDeleted"));
  } catch (error) {
    showWorkerNotice(formatWorkerApiError(error));
  }
}

/** Dashboard-Karte vs. QR-Pass vs. Hub-Bereiche (Urlaub/Zeiten/Docs) sichtbar schalten. */
function updateWorkerShellForTab(tabName) {
  const cardInstall = document.body.classList.contains("worker-card-install");
  const dashboardEl = document.getElementById("workerDashboard");
  const homeInfo = document.getElementById("homeCompactInfo");
  const hubPanel = elements.workerHubPanel || document.getElementById("workerHubPanel");
  const passStage = getWorkerPassStage();
  const visitorCard = document.getElementById("visitorCardContainer");
  const hubToggleRow = document.querySelector(".worker-hub-toggle-row");
  const isHome = tabName === "home";

  if (dashboardEl) {
    const showDashboard = isHome && !cardInstall;
    dashboardEl.classList.toggle("hidden", !showDashboard);
    if (showDashboard) {
      dashboardEl.style.removeProperty("display");
    } else {
      dashboardEl.style.setProperty("display", "none", "important");
    }
  }

  if (homeInfo) {
    const showHomeInfo = isHome;
    homeInfo.classList.toggle("hidden", !showHomeInfo);
    if (showHomeInfo) {
      homeInfo.style.removeProperty("display");
    } else {
      homeInfo.style.setProperty("display", "none", "important");
    }
  }

  if (elements.badgeCard) {
    const showBadgeShell = cardInstall || !isHome;
    elements.badgeCard.classList.toggle("hidden", !showBadgeShell);
    if (showBadgeShell) {
      elements.badgeCard.style.removeProperty("display");
    } else {
      elements.badgeCard.style.setProperty("display", "none", "important");
    }
  }

  if (passStage) {
    const showPass = isHome && (cardInstall || !dashboardEl);
    passStage.classList.toggle("hidden", !showPass);
    if (showPass) {
      passStage.style.removeProperty("display");
    } else {
      passStage.style.setProperty("display", "none", "important");
    }
  }

  if (visitorCard) {
    const showVisitorCard = isHome && !visitorCard.classList.contains("hidden") && (cardInstall || !dashboardEl);
    if (showVisitorCard) {
      visitorCard.style.removeProperty("display");
    } else {
      visitorCard.style.setProperty("display", "none", "important");
    }
  }

  if (hubToggleRow) {
    const showHubToggle = isHome;
    hubToggleRow.classList.toggle("hidden", !showHubToggle);
    if (showHubToggle) {
      hubToggleRow.style.removeProperty("display");
    } else {
      hubToggleRow.style.setProperty("display", "none", "important");
    }
  }

  if (hubPanel) {
    const showHub = !isHome || Boolean(activeWorkerPageTarget);
    hubPanel.classList.toggle("hidden", !showHub);
    if (showHub) {
      hubPanel.style.removeProperty("display");
    } else {
      hubPanel.style.setProperty("display", "none", "important");
    }
  }
  updateWorkHoursBannerVisibility(tabName);
}

function showOnlyWorkerFeaturePanel(panelId) {
  const panelFeatureMap = {
    leaveRequestCard: "worker-leave",
    timesheetCard: "worker-timesheets",
    documentsCard: "worker-documents",
    chatCard: "worker-chat",
    deploymentPlanCard: "worker-deployment",
    workerAiCard: "worker-ai",
  };
  if (globalThis.BaupassUsage?.track && panelFeatureMap[panelId]) {
    globalThis.BaupassUsage.track(panelFeatureMap[panelId], "worker-app");
  }
  const panelIds = [
    "routeCard",
    "sessionInfoCard",
    "companyModeCard",
    "dailyInsightsCard",
    "smartWorkHubCard",
    "workerMenuCard",
    "actionsPanel",
    "leaveRequestCard",
    "timesheetCard",
    "documentsCard",
    "chatCard",
    "deploymentPlanCard",
    "incidentCard",
    "notificationBanner",
  ];

  panelIds.forEach((id) => {
    const panel = document.getElementById(id);
    if (!panel) return;
    const isActive = id === panelId;
    panel.classList.toggle("hidden", !isActive);
    if (isActive) {
      panel.style.removeProperty("display");
    } else {
      panel.style.setProperty("display", "none", "important");
    }
  });
  applyWorkerFeaturePanelLayout(panelId);
}

function applyWorkerFeaturePanelLayout(panelId) {
  const hubPanel = elements.workerHubPanel || document.getElementById("workerHubPanel");
  const badgeCard = elements.badgeCard || document.getElementById("badgeCard");
  if (badgeCard) {
    badgeCard.style.setProperty("display", "flex", "important");
    badgeCard.style.flexDirection = "column";
    badgeCard.style.flex = "1";
    badgeCard.style.minHeight = "0";
    badgeCard.style.overflow = "hidden";
  }
  if (!hubPanel || !panelId) return;
  hubPanel.style.setProperty("display", "flex", "important");
  hubPanel.style.flexDirection = "column";
  hubPanel.style.flex = "1";
  hubPanel.style.minHeight = "0";
  hubPanel.style.overflow = "hidden";

  const panel = document.getElementById(panelId);
  if (!panel) return;

  if (panelId === "chatCard") {
    applyWorkerChatTabLayout(panel);
    return;
  }

  panel.style.setProperty("display", "flex", "important");
  panel.style.flexDirection = "column";
  panel.style.flex = "1";
  panel.style.minHeight = "0";
  panel.style.overflowY = "auto";
  panel.style.overflowX = "hidden";
  panel.style.webkitOverflowScrolling = "touch";

  const scrollTargets = [
    ".timesheet-list",
    ".leave-request-list",
    ".documents-list",
    ".deployment-plan-list",
    ".worker-chat-messages",
  ];
  scrollTargets.forEach((selector) => {
    panel.querySelectorAll(selector).forEach((el) => {
      el.style.flex = "1";
      el.style.minHeight = "0";
      el.style.overflowY = "auto";
      el.style.webkitOverflowScrolling = "touch";
    });
  });
}

function applyWorkerCardInstallView() {
  document.body.classList.add("worker-card-install");
  updateWorkerShellForTab("home");
  document.body.classList.remove("worker-tile-overview");
  activeWorkerPageTarget = "";
  window.scrollTo(0, 0);
}

function setActiveQuickMenuTarget(targetId) {
  if (!elements.quickMenuButtons?.length) return;
  elements.quickMenuButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-scroll-target") === targetId);
  });
}

function updateWorkerHubToggleLabel() {
  if (!elements.workerHubToggle) return;
  elements.workerHubToggle.textContent = workerHubExpanded ? t("workerHubHideBtn") : t("workerHubShowBtn");
}

function setWorkerHubExpanded(expanded, options = {}) {
  const shouldExpand = Boolean(expanded);
  workerHubExpanded = shouldExpand;
  document.body.classList.toggle("wallet-immersive-sections-open", shouldExpand);
  if (elements.workerHubPanel) {
    elements.workerHubPanel.classList.toggle("hidden", !shouldExpand);
  }
  updateWorkerHubToggleLabel();
  if (options.scrollToPanel && shouldExpand && elements.workerHubPanel) {
    elements.workerHubPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function getWorkerPageTitle(targetId) {
  if (targetId === "routeCard") return t("routeTodayTitle");
  if (targetId === "sessionInfoCard") return t("sessionTitle");
  if (targetId === "companyModeCard") return t("companyModeTitle");
  if (targetId === "dailyInsightsCard") return t("dailyInsightsTitle");
  if (targetId === "actionsPanel") return t("actionsTitle");
  if (targetId === "leaveRequestCard") return t("leaveRequestTitle");
  if (targetId === "workerAiCard") return t("workerAiTitle");
  if (targetId === "incidentCard") return t("incidentTitle");
  if (targetId === "timesheetCard") return t("timesheetCardTitle");
  if (targetId === "documentsCard") return t("documentsTitle");
  if (targetId === "chatCard") return t("workerChatTitle");
  if (targetId === "deploymentPlanCard") return t("deploymentPlanTitle");
  return t("workerPageDefault");
}

function getWorkerPageSections() {
  return [
    document.querySelector("#routeCard"),
    document.querySelector("#sessionInfoCard"),
    document.querySelector("#companyModeCard"),
    document.querySelector("#dailyInsightsCard"),
    document.querySelector("#actionsPanel"),
    elements.leaveRequestCard,
    elements.workerAiCard,
    elements.incidentCard,
    elements.timesheetCard,
    elements.documentsCard,
    elements.chatCard,
    elements.deploymentPlanCard,
  ].filter(Boolean);
}

const WORKER_CHAT_SHELL_FIX_CSS = [
  "body.worker-loaded.worker-feature-tab-active #workerHubPanel:not(.hidden){display:flex!important;flex-direction:column;flex:1;min-height:0;overflow:hidden}",
  "body.worker-loaded.worker-feature-tab-active #chatCard.worker-feature-chat-card:not(.hidden){display:flex!important;flex-direction:column;flex:1;min-height:0;padding:0;border:none;border-radius:0;background:transparent;box-shadow:none;overflow:hidden}",
  "body.worker-loaded.worker-feature-tab-active #chatCard .worker-chat-messages{flex:1 1 auto;min-height:0;max-height:none!important;margin:0;overflow-y:auto;overflow-x:hidden;overscroll-behavior:contain;-webkit-overflow-scrolling:touch}",
  "body.worker-loaded.worker-feature-tab-active #chatCard .worker-chat-compose{flex:0 0 auto;flex-shrink:0;display:block!important;margin:0;padding:8px 10px max(8px,env(safe-area-inset-bottom,0px));background:#fff;border-top:1px solid rgba(60,94,139,.22);box-shadow:0 -4px 18px rgba(8,28,54,.07)}",
  "body.worker-loaded.worker-feature-tab-active #chatCard .worker-chat-compose-bar{display:flex;align-items:flex-end;gap:8px}",
  "body.worker-loaded.worker-feature-tab-active #chatCard .worker-chat-compose-bar textarea{flex:1;min-width:0;min-height:46px;max-height:120px;border-radius:22px;font-size:1rem}",
  "body.worker-loaded.worker-feature-tab-active #chatCard .worker-chat-send-btn{display:inline-flex;align-items:center;justify-content:center;width:46px;height:46px;border:none;border-radius:50%;background:#0a57c0;color:#fff}",
  "#chatCard .worker-chat-messages{display:flex;flex-direction:column;gap:12px}",
  "#chatCard .worker-chat-row{display:flex;flex-direction:column;width:100%;gap:4px}",
  "#chatCard .worker-chat-row.is-company{align-items:flex-start;padding-right:12%}",
  "#chatCard .worker-chat-row.is-mine{align-items:flex-end;padding-left:12%}",
  "#chatCard .worker-chat-sender{font-size:.72rem;font-weight:800;letter-spacing:.03em;text-transform:uppercase;padding:0 6px}",
  "#chatCard .worker-chat-row.is-company .worker-chat-sender{color:#c2410c}",
  "#chatCard .worker-chat-row.is-mine .worker-chat-sender{color:#1d4ed8}",
  "#chatCard .worker-chat-bubble{max-width:min(92%,340px);width:fit-content;padding:12px 14px 10px;border-radius:16px;border-width:1.5px;word-break:break-word;font-size:.98rem;line-height:1.45;box-shadow:0 2px 10px rgba(15,23,42,.06)}",
  "#chatCard .worker-chat-bubble.is-company{background:#fff7ed;border:1.5px solid #fdba74;color:#7c2d12;border-bottom-left-radius:5px}",
  "#chatCard .worker-chat-bubble.is-mine{background:#eff6ff;border:1.5px solid #93c5fd;color:#1e3a8a;border-bottom-right-radius:5px}",
  "#chatCard .worker-chat-body{font-size:1rem;line-height:1.5;font-weight:500}",
  "#chatCard .worker-chat-meta{display:flex;justify-content:flex-end;gap:6px;margin-top:8px;font-size:.78rem;color:#64748b}",
  "#chatCard .worker-chat-bubble.is-company .worker-chat-meta{color:#9a3412}",
  "#chatCard .worker-chat-bubble.is-mine .worker-chat-meta{color:#2563eb}",
  "#chatCard .worker-chat-read.is-read{color:#059669;font-weight:700}",
  "#chatCard .worker-chat-attachment-btn{min-height:44px;padding:10px 14px;font-size:.92rem;font-weight:700;border-radius:12px;width:100%;max-width:100%}",
  "#chatCard .chat-layout-version{margin:0 0 8px;padding:6px 10px;border-radius:8px;background:#e8f4ff;color:#0a57c0;font-size:.72rem;font-weight:700;text-align:center}",
  "body.worker-feature-tab-active #chatCard .chat-layout-version{display:none}",
  ".stb-build-tag{font-size:.62rem;font-weight:700;color:var(--corp-muted,#607995);margin-left:6px;opacity:.85}",
].join("");

function ensureWorkerChatShellStyles() {
  let style = document.getElementById("workerChatShellFix");
  if (!style) {
    style = document.createElement("style");
    style.id = "workerChatShellFix";
    document.head.appendChild(style);
  }
  if (style.textContent !== WORKER_CHAT_SHELL_FIX_CSS) {
    style.textContent = WORKER_CHAT_SHELL_FIX_CSS;
  }
}

function ensureWorkerChatComposeBar() {
  const compose = document.querySelector("#chatCard .worker-chat-compose");
  if (!compose || compose.querySelector(".worker-chat-compose-bar")) {
    return;
  }
  const fileHint = compose.querySelector("#workerChatFileHint");
  const fileLabel = compose.querySelector(".worker-chat-file-label");
  const input = compose.querySelector("#workerChatInput");
  const sendBtn = compose.querySelector("#workerChatSendBtn");
  if (!input || !sendBtn) {
    return;
  }
  const bar = document.createElement("div");
  bar.className = "worker-chat-compose-bar";
  if (fileLabel) {
    fileLabel.classList.add("worker-chat-compose-attach");
    bar.appendChild(fileLabel);
  }
  input.rows = 1;
  sendBtn.classList.remove("primary", "small-btn");
  sendBtn.classList.add("worker-chat-send-btn");
  if (!sendBtn.querySelector("svg")) {
    sendBtn.textContent = "";
    sendBtn.insertAdjacentHTML(
      "beforeend",
      `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h12M13 7l5 5-5 5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`
    );
  }
  bar.appendChild(input);
  bar.appendChild(sendBtn);
  compose.textContent = "";
  if (fileHint) {
    compose.appendChild(fileHint);
  }
  compose.appendChild(bar);
  elements.workerChatInput = input;
  elements.workerChatSendBtn = sendBtn;
  elements.workerChatFileInput = compose.querySelector("#workerChatFileInput");
  elements.workerChatFileHint = fileHint || document.getElementById("workerChatFileHint");
  bindWorkerChatComposeEvents();
  applyTranslations();
}

function applyWorkerChatTabLayout(chatCard) {
  const card = chatCard || elements.chatCard || document.getElementById("chatCard");
  if (!card || currentActiveTab !== "chat") {
    return;
  }
  card.classList.add("worker-feature-chat-card");
  const hubPanel = card.closest("#workerHubPanel") || elements.workerHubPanel || document.getElementById("workerHubPanel");
  if (hubPanel) {
    hubPanel.style.setProperty("display", "flex", "important");
    hubPanel.style.flexDirection = "column";
    hubPanel.style.flex = "1";
    hubPanel.style.minHeight = "0";
    hubPanel.style.overflow = "hidden";
  }
  card.style.setProperty("display", "flex", "important");
  card.style.flexDirection = "column";
  card.style.flex = "1";
  card.style.minHeight = "0";
  card.style.overflow = "hidden";
  const messages = card.querySelector(".worker-chat-messages");
  if (messages) {
    messages.style.flex = "1";
    messages.style.minHeight = "0";
    messages.style.maxHeight = "none";
    messages.style.overflowY = "auto";
  }
  const compose = card.querySelector(".worker-chat-compose");
  if (compose) {
    compose.style.flex = "0 0 auto";
    compose.style.flexShrink = "0";
    compose.style.display = "block";
  }
}

function ensureWorkerChatNavDom() {
  let navChat = document.getElementById("navChat");
  if (navChat) {
    return navChat;
  }
  const navContainer = document.getElementById("workerBottomNav");
  if (!navContainer) {
    return null;
  }
  navChat = document.createElement("button");
  navChat.id = "navChat";
  navChat.className = "nav-tab";
  navChat.type = "button";
  navChat.setAttribute("role", "tab");
  navChat.setAttribute("aria-selected", "false");
  navChat.dataset.tab = "chat";
  navChat.innerHTML = `
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 6.5h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H9.4L5 20.5V8.5a2 2 0 0 1 2-2z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>
      <path d="M8.2 11h7.6M8.2 14.2h4.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
    </svg>
    <span class="nav-label" data-i18n="navChat">Chat</span>
  `;
  navContainer.appendChild(navChat);
  applyTranslations();
  return navChat;
}

function resolveWorkerChatAnchor() {
  const hubPanel = elements.workerHubPanel || document.getElementById("workerHubPanel");
  const documentsCard = elements.documentsCard || document.getElementById("documentsCard");
  if (documentsCard?.parentElement === hubPanel) {
    return documentsCard;
  }
  return hubPanel || documentsCard || document.querySelector(".app-shell");
}

function placeWorkerChatCard(chatCard) {
  if (!chatCard) {
    return;
  }
  const anchor = resolveWorkerChatAnchor();
  if (!anchor) {
    return;
  }
  if (anchor.id === "documentsCard") {
    if (anchor.nextElementSibling === chatCard) {
      return;
    }
    anchor.insertAdjacentElement("afterend", chatCard);
    return;
  }
  if (chatCard.parentElement === anchor && anchor.lastElementChild === chatCard) {
    return;
  }
  anchor.appendChild(chatCard);
}

/** Inject chat UI when Safari/PWA still serves cached emp-app.html without #chatCard. */
function ensureWorkerChatDom() {
  let chatCard = document.getElementById("chatCard");
  if (!chatCard) {
    const anchor = resolveWorkerChatAnchor() || document.querySelector(".app-shell");
    if (!anchor) {
      return null;
    }
    chatCard = document.createElement("div");
    chatCard.id = "chatCard";
    chatCard.className = "below-card chat-card worker-feature-chat-card hidden";
    chatCard.innerHTML = `
      <p id="chatLayoutVersion" class="chat-layout-version" aria-live="polite">Chat-Layout v${WORKER_BUILD_TAG}</p>
      <div class="section-head compact-head">
        <p class="section-kicker" data-i18n="workerChatKicker">Kommunikation</p>
        <h3 data-i18n="workerChatTitle">Chat mit Firma</h3>
      </div>
      <div id="workerChatMessages" class="worker-chat-messages">
        <p class="muted-info" data-i18n="workerChatEmpty">Noch keine Nachrichten.</p>
      </div>
      <div class="worker-chat-compose">
        <p id="workerChatFileHint" class="worker-chat-file-hint muted-info hidden"></p>
        <div class="worker-chat-compose-bar">
          <label class="worker-chat-file-label worker-chat-compose-attach" for="workerChatFileInput">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M12 5v10M8.5 11.5 12 15l3.5-3.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M5 19h14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            <span class="sr-only" data-i18n="workerChatAttach">Unterlage anfügen</span>
            <input type="file" id="workerChatFileInput" accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,image/*" />
          </label>
          <textarea id="workerChatInput" rows="1" data-i18n="workerChatPlaceholder" placeholder="Nachricht schreiben…"></textarea>
          <button type="button" id="workerChatSendBtn" class="worker-chat-send-btn" data-i18n="workerChatSend" data-i18n-attr="aria-label" aria-label="Senden">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M5 12h12M13 7l5 5-5 5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </button>
        </div>
      </div>
    `;
    if (anchor.id === "badgeCard" || anchor.id === "homeCompactInfo") {
      anchor.insertAdjacentElement("afterend", chatCard);
    } else {
      anchor.appendChild(chatCard);
    }
    applyTranslations();
    bindWorkerChatComposeEvents();
  }
  elements.chatCard = chatCard;
  elements.workerChatMessages = document.getElementById("workerChatMessages");
  elements.workerChatInput = document.getElementById("workerChatInput");
  elements.workerChatSendBtn = document.getElementById("workerChatSendBtn");
  elements.workerChatFileInput = document.getElementById("workerChatFileInput");
  elements.workerChatFileHint = document.getElementById("workerChatFileHint");
  placeWorkerChatCard(chatCard);
  ensureWorkerChatComposeBar();
  if (currentActiveTab === "chat") {
    applyWorkerChatTabLayout(chatCard);
  }
  return chatCard;
}

function syncWorkerChatComposeRefs() {
  const chatCard = elements.chatCard || document.getElementById("chatCard");
  if (!chatCard) {
    return;
  }
  elements.chatCard = chatCard;
  elements.workerChatMessages = chatCard.querySelector("#workerChatMessages");
  elements.workerChatInput = chatCard.querySelector("#workerChatInput");
  elements.workerChatSendBtn = chatCard.querySelector("#workerChatSendBtn");
  elements.workerChatFileInput = chatCard.querySelector("#workerChatFileInput");
  elements.workerChatFileHint = chatCard.querySelector("#workerChatFileHint");
}

function setWorkerChatComposeEnabled(enabled) {
  syncWorkerChatComposeRefs();
  if (elements.workerChatInput) {
    elements.workerChatInput.disabled = !enabled;
  }
  if (elements.workerChatSendBtn) {
    elements.workerChatSendBtn.disabled = !enabled;
    if (enabled) {
      elements.workerChatSendBtn.removeAttribute("disabled");
    } else {
      elements.workerChatSendBtn.setAttribute("disabled", "true");
    }
  }
}

function bindWorkerChatComposeEvents() {
  syncWorkerChatComposeRefs();
  const chatCard = elements.chatCard || document.getElementById("chatCard");
  const compose = chatCard?.querySelector(".worker-chat-compose");
  if (compose && !compose.dataset.chatDelegateBound) {
    compose.dataset.chatDelegateBound = "1";
    compose.addEventListener("click", (event) => {
      const sendBtn = event.target instanceof Element ? event.target.closest("#workerChatSendBtn") : null;
      if (!sendBtn || sendBtn.disabled) {
        return;
      }
      event.preventDefault();
      void sendWorkerChatMessage();
    });
  }
  const input = elements.workerChatInput || chatCard?.querySelector("#workerChatInput");
  const fileInput = elements.workerChatFileInput || chatCard?.querySelector("#workerChatFileInput");
  if (input && !input.dataset.chatBound) {
    input.dataset.chatBound = "1";
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        void sendWorkerChatMessage();
      }
    });
  }
  if (fileInput && !fileInput.dataset.chatBound) {
    fileInput.dataset.chatBound = "1";
    fileInput.addEventListener("change", () => {
      updateWorkerChatFileHint();
    });
  }
  const messagesHost = elements.workerChatMessages || document.getElementById("workerChatMessages");
  if (messagesHost && !messagesHost.dataset.chatDownloadBound) {
    messagesHost.dataset.chatDownloadBound = "1";
    messagesHost.addEventListener("click", (event) => {
      const target = event.target instanceof Element ? event.target.closest("[data-attachment-id]") : null;
      if (!target) {
        return;
      }
      const attachmentId = target.getAttribute("data-attachment-id") || "";
      const filename = target.getAttribute("data-filename") || "download";
      if (attachmentId) {
        void downloadWorkerChatAttachment(attachmentId, filename);
      }
    });
  }
}

function updateWorkerChatFileHint() {
  const hint = elements.workerChatFileHint || document.getElementById("workerChatFileHint");
  const fileInput = elements.workerChatFileInput || document.getElementById("workerChatFileInput");
  if (!hint || !fileInput) {
    return;
  }
  const file = fileInput.files?.[0];
  if (!file) {
    hint.textContent = "";
    hint.classList.add("hidden");
    return;
  }
  hint.textContent = tf("workerChatFileSelected", { name: file.name });
  hint.classList.remove("hidden");
}

function applyWorkerPageView(targetId = "") {
  const sections = getWorkerPageSections();
  const useFocusMode = Boolean(targetId);
  const useTileOverview = document.body.classList.contains("worker-loaded");
  activeWorkerPageTarget = useFocusMode ? targetId : "";

  if (!useFocusMode) {
    document.body.classList.remove("worker-page-focus");
    if (currentActiveTab === "home") {
      document.body.classList.remove("worker-feature-tab-active");
    }
    sections.forEach((section) => {
      if (useTileOverview) {
        section.classList.add("hidden");
        delete section.dataset.pageWasVisible;
      } else if (section.dataset.pageWasVisible !== undefined) {
        section.classList.toggle("hidden", section.dataset.pageWasVisible !== "1");
        delete section.dataset.pageWasVisible;
      }
      section.classList.remove("worker-page-active");
    });

    if (elements.workerPageNav) {
      elements.workerPageNav.classList.add("hidden");
    }
    if (elements.workerPageLabel) {
      elements.workerPageLabel.textContent = "";
    }
    refreshWorkerChatPanel();
    return;
  }

  sections.forEach((section) => {
    if (section.dataset.pageWasVisible === undefined) {
      section.dataset.pageWasVisible = section.classList.contains("hidden") ? "0" : "1";
    }
    const shouldShow = section.id === targetId;
    section.classList.toggle("hidden", !shouldShow);
    section.classList.toggle("worker-page-active", shouldShow);
    if (shouldShow) {
      section.style.removeProperty("display");
    }
  });

  document.body.classList.add("worker-page-focus", "worker-feature-tab-active");
  ensureWorkerFeatureHubVisible();
  showOnlyWorkerFeaturePanel(targetId);
  applyWorkerFeaturePanelLayout(targetId);

  if (elements.workerPageNav) {
    elements.workerPageNav.classList.remove("hidden");
  }
  document.body.classList.remove("worker-tile-overview");
  if (elements.workerPageLabel) {
    elements.workerPageLabel.textContent = tf("workerPageOpened", { page: getWorkerPageTitle(targetId) });
  }
}

init().finally(dismissSplash);

async function init() {
  const params = new URL(window.location.href).searchParams;
  if (isQrBootstrapEntry(params)) {
    resetWorkerSessionForQrEntry({ keepBadge: true });
  } else {
    workerToken = (wpGet(WORKER_TOKEN_KEY) || "").trim();
    workerBearerToken = (wpGet(WORKER_JWT_KEY) || workerToken || "").trim();
  }
  applyTranslations();
  enforceUiVisibilityGuard();
  updateWorkerBuildBadge();
  refreshTopBarElements();
  bindTopBarActions();
  bindEvents();
  initBottomTabNavigation();
  updateWalletImmersiveMode();
  applyQrContrastState();
  applyAutoOpenScannerState();
  enforceWorkerBuildFreshness(params);
  const deferChatShell = () => {
    ensureWorkerChatShellStyles();
    ensureWorkerChatNavDom();
    ensureWorkerChatDom();
    ensureWorkerChatComposeBar();
  };
  if (typeof requestIdleCallback === "function") {
    requestIdleCallback(deferChatShell, { timeout: 1200 });
  } else {
    setTimeout(deferChatShell, 0);
  }
  if (params.get("session") === "1" && workerToken) {
    const cachedRaw = wpGet(WORKER_CACHED_PAYLOAD_KEY);
    if (cachedRaw) {
      try {
        renderWorker(JSON.parse(cachedRaw));
        markWorkerLoginCompleted();
        finishWorkerLoginUi();
        releaseSplashEarly();
      } catch {
        // fall through to network sync
      }
    }
    const loaded = await loadWorkerData();
    if (loaded || document.body.classList.contains("worker-loaded")) {
      window.__workerAppInitDone = true;
      return;
    }
  }
  if ("scrollRestoration" in history) {
    history.scrollRestoration = "manual";
  }
  window.scrollTo(0, 0);
  
  // Enable Dark Mode support
  if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    document.documentElement.style.colorScheme = "dark";
  }

  const urlApiBase = sanitizeApiBase(params.get("apiBase"));
  if (urlApiBase) {
    wpSet(API_BASE_STORAGE_KEY, urlApiBase);
  }
  refreshWorkerApiBase();
  const bootstrapAccessToken = readBootstrapAccessToken(params);
  const viewParam = (params.get("view") || "").trim().toLowerCase();
  if (viewParam === "card") {
    document.body.classList.add("worker-card-install");
  }
  const urlBadgeParam = getQrLaunchBadgeId(params);
  const urlFastLogin = params.get("fast") === "1" || params.get("launch") === "1";
  const storedBadgeId = readBootstrapBadgeId(params);
  const accessInUrl = (params.get("access") || "").trim();
  let qrBadgeId = storedBadgeId;

  if (bootstrapAccessToken) {
    window.wpSet(WORKER_ACCESS_TOKEN_KEY, bootstrapAccessToken);
    applyDynamicManifestStartUrl(bootstrapAccessToken);
  }

  registerWorkerSw();
  wireInstallPrompt();
  void preloadWorkerTenantBranding();
  updateConnectionState();
  updateWorkerBuildBadge();
  initBatteryTelemetry();
  updateWorkerPulsePanel();

  if (bootstrapAccessToken && !qrBadgeId) {
    qrBadgeId = await resolveBadgeIdFromAccessToken(bootstrapAccessToken);
  }

  if (qrBadgeId && !workerToken) {
    prefillWorkerBadgeField(qrBadgeId, {
      readOnly: Boolean(accessInUrl || urlFastLogin),
      focusPin: Boolean(accessInUrl || urlFastLogin),
    });
    if (accessInUrl || urlFastLogin) {
      document.body.classList.add("qr-fast-login");
      const loginCopy = document.querySelector(".login-copy-sparkasse");
      if (loginCopy) {
        loginCopy.textContent = tf("loginCopyQrFast", { badge: qrBadgeId });
      }
    }
  }

  if (bootstrapAccessToken && accessInUrl) {
    if (workerToken) {
      const loaded = await loadWorkerData();
      if (loaded) {
        window.__workerAppInitDone = true;
        return;
      }
      workerToken = "";
      wpRemove(WORKER_TOKEN_KEY);
    }
    let joinPreview = null;
    try {
      joinPreview = await fetchJoinPreview(bootstrapAccessToken);
      if (joinPreview?.badgeId) {
        qrBadgeId = normalizeBadgeIdInput(joinPreview.badgeId);
        prefillWorkerBadgeField(qrBadgeId, { readOnly: true, focusPin: true });
      }
      applyJoinPreviewBranding(joinPreview);
    } catch {
      // ignore preview failures
    }
    if (qrBadgeId) {
      prepareQrPinOnlyLogin(qrBadgeId, { readOnly: true, focusPin: true });
    }
    if ((joinPreview?.tokenUsed || joinPreview?.tokenExpired) && qrBadgeId) {
      showLoginError(
        joinPreview?.tokenUsed ? t("qrLinkUsedEnterPin") : t("qrLinkInvalidRescan"),
        { focusPin: true },
      );
      startProximityLoginWatcher();
      window.__workerAppInitDone = true;
      return;
    }
    if (joinPreview?.tokenValid) {
      await loginWithAccessToken(bootstrapAccessToken, {
        keepUrlToken: false,
        silent: false,
        locationPayload: null,
      });
    }
    if (isWorkerShellAuthenticated() || workerToken) {
      startProximityLoginWatcher();
      window.__workerAppInitDone = true;
      return;
    }
    if (qrBadgeId) {
      showLoginError(t("qrLinkUsedEnterPin"), { focusPin: true });
    } else {
      showLogin();
    }
    startProximityLoginWatcher();
    window.__workerAppInitDone = true;
    return;
  }

  if (workerToken) {
    const loaded = await loadWorkerData();
    if (loaded) {
      return;
    }
  }

  if (bootstrapAccessToken && !accessInUrl && !workerToken) {
    if (!qrBadgeId) {
      qrBadgeId = await resolveBadgeIdFromAccessToken(bootstrapAccessToken);
    }
    if (qrBadgeId) {
      prepareQrPinOnlyLogin(qrBadgeId, { readOnly: false, focusPin: true });
      return;
    }
    const locationPayload = await resolveLoginLocation({ timeoutMs: 10000 });
    await loginWithAccessToken(bootstrapAccessToken, { keepUrlToken: false, silent: true, locationPayload });
    if (workerToken) {
      applyWorkerPageView("badgeCard");
      return;
    }
  }

  if (urlBadgeParam) {
    if (workerToken) {
      const cachedRaw = wpGet(WORKER_CACHED_PAYLOAD_KEY);
      if (cachedRaw) {
        try {
          renderWorker(JSON.parse(cachedRaw));
          markWorkerLoginCompleted();
          finishWorkerLoginUi();
          releaseSplashEarly();
          void loadWorkerData({ quiet: true });
          window.__workerAppInitDone = true;
          return;
        } catch {
          // fall through to network restore
        }
      }
      const loaded = await loadWorkerData();
      if (loaded || isWorkerShellAuthenticated()) {
        if (viewParam === "card") applyWorkerPageView("badgeCard");
        window.__workerAppInitDone = true;
        return;
      }
    }
    if (urlFastLogin) {
      prepareQrPinOnlyLogin(urlBadgeParam, { readOnly: true, focusPin: true });
      startProximityLoginWatcher();
      window.__workerAppInitDone = true;
      return;
    }
    prefillWorkerBadgeField(urlBadgeParam, { readOnly: false });
    showLogin();
    return;
  }

  if (storedBadgeId) {
    prefillWorkerBadgeField(storedBadgeId, { readOnly: false });
  }
  if (!workerToken) {
    if (isStandaloneDisplay()) {
      const standaloneBadge = normalizeBadgeIdInput(
        storedBadgeId || readBootstrapBadgeId(params) || wpGet(WORKER_BADGE_LOGIN_KEY) || "",
      );
      if (standaloneBadge && !isVisitorBadgeId(standaloneBadge)) {
        prepareQrPinOnlyLogin(standaloneBadge, { readOnly: true, focusPin: true });
        startProximityLoginWatcher();
        window.__workerAppInitDone = true;
        return;
      }
    }
    showLogin();
    if (qrBadgeId || storedBadgeId) {
      prefillWorkerBadgeField(qrBadgeId || storedBadgeId, { readOnly: false });
    }
  }
  startProximityLoginWatcher();
  window.__workerAppInitDone = true;
}

function applyDynamicManifestStartUrl(accessToken, platformName) {
  const manifestLink = document.querySelector('link[rel="manifest"]');
  if (!manifestLink || !accessToken) {
    return;
  }

  fetch(`./emp-app-manifest.json?v=${WORKER_BUILD_TAG}`, { cache: "no-store" })
    .then((response) => response.json())
    .then((manifest) => {
      const origin = window.location.origin;
      const abs = (path) => {
        const p = String(path || "").trim();
        if (!p) return `${origin}/`;
        if (/^https?:\/\//i.test(p)) return p;
        return `${origin}${p.startsWith("/") ? p : `/${p}`}`;
      };

      const params = new URLSearchParams();
      params.set("access", accessToken);
      const badgeForStart = normalizeBadgeIdInput(
        wpGet(WORKER_BADGE_LOGIN_KEY)
        || document.getElementById("workerQrBadgeSeed")?.value
        || new URL(window.location.href).searchParams.get("badge")
        || "",
      );
      if (badgeForStart) {
        params.set("badge", badgeForStart);
        params.set("fast", "1");
      }

      const apiBaseParam = new URL(window.location.href).searchParams.get("apiBase");
      if (apiBaseParam) {
        params.set("apiBase", apiBaseParam);
      }

      params.set("view", "card");
      params.set("v", WORKER_BUILD_TAG);
      const startUrl = `${origin}/emp-app.html?${params.toString()}`;

      // Blob-Manifest: alle URLs müssen absolut sein, sonst „URL is invalid“.
      manifest.id = `${origin}/emp-app.html`;
      manifest.start_url = startUrl;
      manifest.scope = `${origin}/`;
      const tenantIcon = String(currentWorkerIconHref || "").trim();
      if (Array.isArray(manifest.icons)) {
        manifest.icons = manifest.icons.map((icon) => ({
          ...icon,
          src: tenantIcon || abs(icon.src),
        }));
      }
      if (platformName) {
        manifest.name = `${platformName} – ${t("splashSub")}`;
        manifest.short_name = platformName.length > 12 ? platformName.slice(0, 12) : platformName;
      }
      if (Array.isArray(manifest.shortcuts)) {
        manifest.shortcuts = manifest.shortcuts.map((shortcut) => ({
          ...shortcut,
          url: startUrl,
          icons: Array.isArray(shortcut.icons)
            ? shortcut.icons.map((icon) => ({
              ...icon,
              src: tenantIcon || abs(icon.src),
            }))
            : shortcut.icons,
        }));
      }

      const blob = new Blob([JSON.stringify(manifest)], { type: "application/manifest+json" });
      if (dynamicManifestUrl) {
        URL.revokeObjectURL(dynamicManifestUrl);
      }
      dynamicManifestUrl = URL.createObjectURL(blob);
      manifestLink.href = dynamicManifestUrl;
    })
    .catch(() => {
      // ignore manifest customization failures
    });
}

function bindEvents() {
  window.__workerAppBindReady = true;
  const langSelect = document.querySelector("#workerLanguageSelect");
  if (langSelect) {
    langSelect.value = currentLang;
    if (langSelect.dataset.langBound !== "1") {
      langSelect.dataset.langBound = "1";
      langSelect.addEventListener("change", () => setLang(langSelect.value));
    }
  }

  window.addEventListener("online", () => {
    updateConnectionState();
    if (workerToken) {
      void syncOfflinePhotoQueue();
      void syncOfflineEventQueue();
    }
  });
  window.addEventListener("offline", updateConnectionState);
  window.addEventListener("pointerdown", unlockHaptic, { passive: true });
  window.addEventListener("touchstart", unlockHaptic, { passive: true });
  window.addEventListener("keydown", markUserInteraction, { passive: true });
  window.addEventListener("scroll", markUserInteraction, { passive: true });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      markUserInteraction();
      updateWorkerPulsePanel();
      ensureWorkerChatDom();
      if (workerToken) {
        refreshWorkerChatPanel();
        void requestWakeLock();
        void fetchAndDisplayDynamicQr();
        void loadWorkerData({ quiet: true });
        if (lastSiteAccessCfg?.siteApp && hasSiteGeofenceConfig(lastSiteAccessCfg)) {
          siteOffSiteStrikeCount = 0;
          void pollSitePresence(lastSiteAccessCfg);
        }
      }
    } else {
      releaseWakeLock();
    }
  });
  window.addEventListener("pageshow", () => {
    updateWalletImmersiveMode();
    updateWorkerPulsePanel();
    ensureWorkerChatDom();
    if (workerToken) {
      refreshWorkerChatPanel();
      void requestWakeLock();
      void fetchAndDisplayDynamicQr();
    }
  });
  window.addEventListener("pagehide", () => {
    releaseWakeLock();
  });

  if (elements.workerAccessToken) {
    const pinWrapper = document.querySelector("#pinFieldWrapper");
    elements.workerAccessToken.addEventListener("input", () => {
      const rawValue = elements.workerAccessToken.value || "";
      const normalizedCandidate = normalizeBadgeIdInput(rawValue);
      const shouldNormalizeBadgeInput =
        looksLikeBadgeId(normalizedCandidate)
        || /^\s*(BP|VS|WRK)[\s\-‐‑–—‒_]/i.test(rawValue);

      if (shouldNormalizeBadgeInput && normalizedCandidate && rawValue !== normalizedCandidate) {
        elements.workerAccessToken.value = normalizedCandidate;
      }

      const val = (elements.workerAccessToken.value || "").trim();
      syncLoginPinFieldVisibility(val);
      const isBadge = looksLikeBadgeId(val) && !isVisitorBadgeId(val);
      if (elements.geolocationHint) {
        elements.geolocationHint.classList.toggle("hidden", !isBadge);
      }
    });
  }

  if (elements.workerResumeLoginButton) {
    elements.workerResumeLoginButton.addEventListener("click", () => {
      const savedBadgeId = normalizeBadgeIdInput(wpGet(WORKER_BADGE_LOGIN_KEY) || "");
      if (!savedBadgeId || !elements.workerAccessToken) {
        return;
      }

      elements.workerAccessToken.value = savedBadgeId;
      elements.workerAccessToken.dispatchEvent(new Event("input", { bubbles: true }));

      const pinInput = document.querySelector("#workerBadgePin");
      if (pinInput) {
        pinInput.focus();
        pinInput.select?.();
      }
    });
  }

  if (elements.workerLoginForm) {
    elements.workerLoginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submitBtn = elements.workerLoginForm.querySelector('button[type="submit"]');
      const submitLabel = submitBtn?.textContent || "";
      clearLoginError();
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = t("loginProgress");
      }
      try {
        const qrLaunch = shouldTreatLoginAsQrLaunch();
        let credential = (elements.workerAccessToken?.value || "").trim();
        if ((!credential || !looksLikeBadgeId(credential)) && qrLaunch) {
          credential = getLoginBadgeCredential();
        }
        const isBadgeLogin = looksLikeBadgeId(credential);
        const isVisitor = isVisitorBadgeId(credential);
        const isAccessTokenLogin = !isBadgeLogin && looksLikeAccessToken(credential);

        if (isBadgeLogin && !isVisitor) {
          syncLoginPinFieldVisibility(credential);
          const badgePin = normalizeBadgePinInput(elements.workerBadgePin?.value || "");
          if (!badgePin) {
            showLoginError(t("enterPin"), { focusPin: true });
            return;
          }
          if (qrLaunch) {
            if (credential) {
              prefillWorkerBadgeField(credential, { readOnly: true });
            }
            await executeQrPinLogin(credential, badgePin, { qrLaunch: true, silent: false });
            return;
          }
        }

        let locationPayload = null;
        if (isBadgeLogin && !isVisitor && !qrLaunch) {
          if (submitBtn) submitBtn.textContent = t("loginGeoProgress");
          locationPayload = await resolveLoginLocation({ timeoutMs: 10000 });
        } else if (isAccessTokenLogin || isVisitor) {
          if (submitBtn) submitBtn.textContent = t("loginGeoProgress");
          locationPayload = await resolveLoginLocation({ timeoutMs: 12000 });
        }
        if (submitBtn) submitBtn.textContent = t("loginProgress");
        if (isBadgeLogin) {
          const badgePin = isVisitor ? "" : normalizeBadgePinInput(elements.workerBadgePin?.value || "");
          await loginWithBadgeId(credential, badgePin, { locationPayload, qrLaunch });
          return;
        }
        await loginWithAccessToken(credential, { locationPayload });
      } catch (error) {
        console.error("[workerLoginForm] submit failed:", error);
        showLoginError(
          workerLoginErrorMessage(error) || t("loginFailed"),
          { code: error?.code || "" },
        );
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = submitLabel || t("loginBtn");
        }
      }
    });
  }

  if (elements.refreshButton) {
    elements.refreshButton.addEventListener("click", loadWorkerData);
  }

  bindWorkerLogoutButtons();

  if (elements.installButton) {
    elements.installButton.addEventListener("click", triggerInstall);
  }

  if (elements.forceRefreshButton) {
    elements.forceRefreshButton.addEventListener("click", () => {
      void forceRefreshApp();
    });
  }

  if (elements.gateModeButton) {
    elements.gateModeButton.addEventListener("click", openGateMode);
  }

  if (elements.quickGateModeButton) {
    elements.quickGateModeButton.addEventListener("click", openGateMode);
  }

  if (elements.closeGateModeButton) {
    elements.closeGateModeButton.addEventListener("click", closeGateMode);
  }

  if (elements.qrContrastToggle) {
    elements.qrContrastToggle.addEventListener("click", toggleQrContrastMode);
  }

  if (elements.gateContrastToggle) {
    elements.gateContrastToggle.addEventListener("click", toggleQrContrastMode);
  }

  if (elements.autoOpenScannerToggle) {
    elements.autoOpenScannerToggle.addEventListener("change", () => {
      autoOpenScannerEnabled = Boolean(elements.autoOpenScannerToggle?.checked);
      wpSet(AUTO_OPEN_SCANNER_KEY, autoOpenScannerEnabled ? "1" : "0");
      applyAutoOpenScannerState();
    });
  }

  if (elements.changePhotoButton) {
    elements.changePhotoButton.addEventListener("click", openCameraOverlay);
  }

  if (elements.photoInput) {
    elements.photoInput.addEventListener("change", handlePhotoSelected);
  }

  if (elements.takePhotoButton) {
    elements.takePhotoButton.addEventListener("click", takePhotoFromCamera);
  }
  if (elements.confirmPhotoButton) {
    elements.confirmPhotoButton.addEventListener("click", confirmCameraPhoto);
  }
  if (elements.retakePhotoButton) {
    elements.retakePhotoButton.addEventListener("click", retakeCameraPhoto);
  }
  if (elements.closeCameraButton) {
    elements.closeCameraButton.addEventListener("click", closeCameraOverlay);
  }
  if (elements.rotatePhotoButton) {
    elements.rotatePhotoButton.addEventListener("click", rotateCameraPhoto);
  }
  if (elements.deletePhotoButton) {
    elements.deletePhotoButton.addEventListener("click", deleteCameraPhoto);
  }

  // ── PIN-Lock Event-Listener ──
  if (elements.pinLockForm) {
    elements.pinLockForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const pin = elements.pinLockInput?.value || "";
      await handlePassLockUnlock(pin);
    });
  }


  // ── Tracking für Pass-Interaktionen ──
  if (elements.badgeCard) {
    elements.badgeCard.addEventListener("pointerdown", markPassInteraction, { passive: true });
    elements.badgeCard.addEventListener("touchstart", markPassInteraction, { passive: true });
    elements.badgeCard.addEventListener("scroll", markPassInteraction, { passive: true });
  }

  // ── NEW FEATURES EVENT LISTENERS ──
  if (elements.themeToggleBtn) {
    elements.themeToggleBtn.addEventListener("click", toggleTheme);
  }
  
  if (elements.voiceCommandBtn) {
    elements.voiceCommandBtn.addEventListener("click", initVoiceCommands);
  }
  
  if (elements.enableNotificationsBtn) {
    elements.enableNotificationsBtn.addEventListener("click", requestNotificationPermission);
  }

  bindTopBarActions();
  
  if (elements.leaveRequestToggleBtn) {
    elements.leaveRequestToggleBtn.addEventListener("click", toggleLeaveRequestForm);
  }
  
  if (elements.leaveRequestForm) {
    elements.leaveRequestForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      await submitLeaveRequest();
    });
  }

  if (elements.workerHubToggle) {
    elements.workerHubToggle.addEventListener("click", () => {
      setWorkerHubExpanded(!workerHubExpanded, { scrollToPanel: true });
    });
  }

  if (elements.quickMenuButtons?.length) {
    elements.quickMenuButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const targetId = btn.getAttribute("data-scroll-target") || "";
        if (!targetId) return;
        setActiveQuickMenuTarget(targetId);
        const target = document.getElementById(targetId);
        if (target) {
          target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });
  }

  if (elements.workerMenuButtons?.length) {
    elements.workerMenuButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const targetId = btn.getAttribute("data-worker-page-target") || "";
        if (!targetId) return;
        if (targetId === "deploymentPlanCard") {
          void openWorkerDeploymentPlanScreen();
          return;
        }
        if (targetId === "chatCard") {
          void openWorkerChatScreen();
          return;
        }
        applyWorkerPageView(targetId);
        const target = document.getElementById(targetId);
        if (target) {
          target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    });
  }

  if (elements.deploymentPlanMonthSelect) {
    elements.deploymentPlanMonthSelect.addEventListener("change", () => {
      void loadDeploymentPlan();
    });
  }
  if (elements.deploymentPlanPdfBtn) {
    elements.deploymentPlanPdfBtn.addEventListener("click", () => {
      void openDeploymentPlanPdf(false);
    });
  }
  if (elements.deploymentPlanPrintBtn) {
    elements.deploymentPlanPrintBtn.addEventListener("click", () => {
      void openDeploymentPlanPdf(true);
    });
  }
  bindDeploymentPlanInteractions();

  bindWorkerChatComposeEvents();

  bindWorkerFeatureTabActions();

  if (elements.workerPageBackButton) {
    elements.workerPageBackButton.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      switchToTab("home");
    });
  }

  if (elements.leaveRequestAiBtn) {
    elements.leaveRequestAiBtn.addEventListener("click", applyAiLeaveSuggestion);
  }

  if (elements.workerAiForm) {
    elements.workerAiForm.addEventListener("submit", (event) => {
      event.preventDefault();
      void submitWorkerAiQuestion();
    });
  }
  if (globalThis.BaupassAiUi?.bindVoiceInput && elements.workerAiQuestion) {
    globalThis.BaupassAiUi.bindVoiceInput({
      inputId: "workerAiQuestion",
      buttonId: "workerAiVoiceBtn",
      sendId: "workerAiSendBtn",
      formId: "workerAiForm",
      get lang() { return getWorkerLang(); },
      multilingual: true,
      transcribeUrl: `${API_ROOT}/worker-ai/transcribe`,
      authHeaders: () => ({ Authorization: `Bearer ${workerToken}` }),
      onMicError: (err) => showWorkerNotice(
        globalThis.BaupassAiUi?.voiceErrorMessage?.(err, getWorkerLang()) || t("microphoneAccessBlocked"),
      ),
      onTranscribeError: (err) => showWorkerNotice(
        globalThis.BaupassAiUi?.voiceErrorMessage?.(err, getWorkerLang()) || String(err?.message || err),
      ),
    });
  }

  // Urlaubstage live berechnen
  const calcDays = () => {
    const start = elements.leaveRequestStart?.value;
    const end = elements.leaveRequestEnd?.value;
    const hint = document.getElementById("leaveDaysHint");
    if (!hint) return;
    if (start && end && end >= start) {
      const days = countWorkingDays(start, end);
      hint.textContent = `${days} Arbeitstag${days !== 1 ? "e" : ""}`;
      hint.className = "leave-days-hint";
    } else {
      hint.textContent = "";
    }
  };
  if (elements.leaveRequestStart) elements.leaveRequestStart.addEventListener("change", calcDays);
  if (elements.leaveRequestEnd) elements.leaveRequestEnd.addEventListener("change", calcDays);

    if (elements.sendToBossBtn) {
    elements.sendToBossBtn.addEventListener("click", async () => {
      await sendLastLeaveRequestToBoss();
    });
  }

  if (elements.timesheetRefreshBtn) {
    elements.timesheetRefreshBtn.addEventListener("click", () => void loadMyTimesheets());
  }

  if (elements.incidentForm) {
    elements.incidentForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      await submitIncidentReport();
    });
  }

  if (elements.walletAppleBtn) {
    elements.walletAppleBtn.addEventListener("click", () => void addWorkerPassToWallet("apple"));
  }

  if (elements.walletGoogleBtn) {
    elements.walletGoogleBtn.addEventListener("click", () => void addWorkerPassToWallet("google"));
  }

  if (elements.dayPlannerList) {
    elements.dayPlannerList.addEventListener("change", (event) => {
      const input = event.target;
      if (!(input instanceof HTMLInputElement) || input.type !== "checkbox") {
        return;
      }
      const taskId = String(input.getAttribute("data-planner-task-id") || "").trim();
      const storageKey = String(elements.dayPlannerList?.dataset.storageKey || "").trim();
      if (!taskId || !storageKey) {
        return;
      }
      const nextState = loadPlannerState(storageKey);
      nextState[taskId] = input.checked;
      savePlannerState(storageKey, nextState);
      const row = input.closest(".day-planner-item");
      if (row) {
        row.classList.toggle("done", input.checked);
      }
    });
  }

  if (elements.dayPlannerResetBtn) {
    elements.dayPlannerResetBtn.addEventListener("click", () => {
      const storageKey = String(elements.dayPlannerList?.dataset.storageKey || "").trim();
      if (storageKey) {
        savePlannerState(storageKey, {});
      }
      updateSmartWorkHub(lastWorkerPayload, lastTimesheetRows);
    });
  }

  window.addEventListener("beforeunload", stopCameraStream);
}

function savePhotoToOfflineQueue(dataUrl) {
  let queue = [];
  try {
    queue = JSON.parse(wpGet(OFFLINE_PHOTO_QUEUE_KEY) || "[]");
  } catch {
    queue = [];
  }
  queue.push({ dataUrl, timestamp: Date.now() });
  wpSet(OFFLINE_PHOTO_QUEUE_KEY, JSON.stringify(queue));
  updateSmartWorkHub(lastWorkerPayload, lastTimesheetRows);
}

function readStoredJson(key, fallbackValue) {
  try {
    const raw = wpGet(key);
    if (!raw) {
      return fallbackValue;
    }
    return JSON.parse(raw);
  } catch {
    return fallbackValue;
  }
}

function writeStoredJson(key, value) {
  wpSet(key, JSON.stringify(value));
}

function clearOfflineLoginData() {
  wpRemove(WORKER_OFFLINE_LOGIN_PROFILE_KEY);
  wpRemove(WORKER_CACHED_PAYLOAD_KEY);
}

function resolveExpiryTimestamp(value) {
  if (!value) {
    return Number.POSITIVE_INFINITY;
  }
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(String(value)) ? `${value}T23:59:59` : value;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? Number.POSITIVE_INFINITY : parsed.getTime();
}

function isCachedWorkerPayloadUsable(payload) {
  const worker = payload?.worker;
  if (!worker || !worker.badgeId) {
    return false;
  }
  if (resolveExpiryTimestamp(worker.validUntil) < Date.now()) {
    return false;
  }
  if (worker.visitEndAt && resolveExpiryTimestamp(worker.visitEndAt) < Date.now()) {
    return false;
  }
  return true;
}

async function hashSensitiveValue(value) {
  const encoded = new TextEncoder().encode(String(value || ""));
  const digest = await crypto.subtle.digest("SHA-256", encoded);
  return Array.from(new Uint8Array(digest)).map((item) => item.toString(16).padStart(2, "0")).join("");
}

function calculateDistanceMeters(latitudeA, longitudeA, latitudeB, longitudeB) {
  const earthRadiusMeters = 6371000;
  const toRadians = (value) => value * (Math.PI / 180);
  const lat1 = toRadians(Number(latitudeA));
  const lon1 = toRadians(Number(longitudeA));
  const lat2 = toRadians(Number(latitudeB));
  const lon2 = toRadians(Number(longitudeB));
  const dLat = lat2 - lat1;
  const dLon = lon2 - lon1;
  const haversine = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * earthRadiusMeters * Math.asin(Math.sqrt(haversine));
}

async function resolveLoginLocation(options = {}) {
  const timeoutMs = Number(options.timeoutMs) > 0 ? Number(options.timeoutMs) : 10000;
  const maxWaitMs = Math.max(2500, Math.min(timeoutMs - 500, 8000));
  return Promise.race([
    resolveSiteLocation({ preferFast: true, maxWaitMs }),
    new Promise((resolve) => setTimeout(() => resolve(null), timeoutMs)),
  ]);
}

async function resolveSiteLocation({ preferFast = false, maxWaitMs = null } = {}) {
  if (!navigator.geolocation) {
    return null;
  }

  const precisePreset = preferFast ? "fast" : "site";
  const preciseMaxWait = Number.isFinite(Number(maxWaitMs)) && Number(maxWaitMs) > 0
    ? Number(maxWaitMs)
    : (preferFast ? 18000 : 12000);
  const preciseTargetAccuracy = preferFast ? 40 : 25;
  const preciseAcceptAccuracy = preferFast ? 100 : 200;

  if (typeof capturePreciseGeolocation === "function") {
    try {
      const position = await capturePreciseGeolocation({
        preset: precisePreset,
        maxWaitMs: preciseMaxWait,
        targetAccuracyMeters: preciseTargetAccuracy,
        acceptAccuracyMeters: preciseAcceptAccuracy,
        minSamples: 1,
        maxSamples: preferFast ? 10 : 8,
      });
      if (
        position &&
        Number.isFinite(Number(position.latitude)) &&
        Number.isFinite(Number(position.longitude))
      ) {
        return {
          latitude: position.latitude,
          longitude: position.longitude,
          accuracy: position.accuracy,
        };
      }
    } catch {
      // fall through to lighter readers
    }
  }

  if (typeof capturePointGeolocation === "function") {
    try {
      const position = await capturePointGeolocation({
        maxWaitMs: 15000,
        cachedMaximumAgeMs: 300000,
      });
      return {
        latitude: position.latitude,
        longitude: position.longitude,
        accuracy: position.accuracy,
      };
    } catch {
      // fall through to instant reading
    }
  }

  if (typeof captureInstantGeolocation === "function") {
    try {
      const position = await captureInstantGeolocation();
      return {
        latitude: position.latitude,
        longitude: position.longitude,
        accuracy: position.accuracy,
      };
    } catch {
      // fall through to single reading
    }
  }

  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
        });
      },
      () => {
        // Permission denied or unavailable – try one relaxed cached reading before giving up.
        navigator.geolocation.getCurrentPosition(
          (position) => {
            resolve({
              latitude: position.coords.latitude,
              longitude: position.coords.longitude,
              accuracy: position.coords.accuracy,
            });
          },
          () => resolve(null),
          { enableHighAccuracy: false, timeout: 25000, maximumAge: 600000 }
        );
      },
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 120000 }
    );
  });
}

async function captureLoginGeolocation({ showProgress = false } = {}) {
  if (!navigator.geolocation) {
    return { location: null, reason: "unsupported" };
  }
  if (showProgress) {
    showWorkerNotice(t("geolocationCapturing"));
  }
  let location = await resolveLoginLocation({ timeoutMs: 10000 });
  if (!location && navigator.geolocation.watchPosition) {
    location = await new Promise((resolve) => {
      let watchId = 0;
      const stop = (value) => {
        if (watchId) {
          try {
            navigator.geolocation.clearWatch(watchId);
          } catch {
            // ignore
          }
        }
        resolve(value);
      };
      const timer = setTimeout(() => stop(null), 12000);
      watchId = navigator.geolocation.watchPosition(
        (position) => {
          clearTimeout(timer);
          stop({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracy: position.coords.accuracy,
          });
        },
        () => {
          clearTimeout(timer);
          stop(null);
        },
        { enableHighAccuracy: true, maximumAge: 0, timeout: 12000 }
      );
    });
  }
  if (location) {
    return { location, reason: "" };
  }
  return { location: null, reason: "unavailable" };
}

async function persistOfflineBadgeProfile(badgeId, badgePin, payload) {
  if (!badgeId || !badgePin || !payload?.worker) {
    return;
  }
  const pinHash = await hashSensitiveValue(`${normalizeBadgeIdInput(badgeId)}:${normalizeBadgePinInput(badgePin)}`);
  writeStoredJson(WORKER_OFFLINE_LOGIN_PROFILE_KEY, {
    badgeId: normalizeBadgeIdInput(badgeId),
    pinHash,
    workerId: payload.worker.id,
    payload,
    savedAt: new Date().toISOString(),
  });
}

function queueOfflineEvent(eventPayload) {
  const queue = readStoredJson(OFFLINE_EVENT_QUEUE_KEY, []);
  queue.push(eventPayload);
  writeStoredJson(OFFLINE_EVENT_QUEUE_KEY, queue.slice(-50));
  updateSmartWorkHub(lastWorkerPayload, lastTimesheetRows);
}

async function tryOfflineBadgeLogin(badgeId, badgePin, locationPayload) {
  const offlineProfile = readStoredJson(WORKER_OFFLINE_LOGIN_PROFILE_KEY, null);
  const cachedPayload = readStoredJson(WORKER_CACHED_PAYLOAD_KEY, null);
  const normalizedBadgeId = normalizeBadgeIdInput(badgeId);
  if (!offlineProfile || !cachedPayload || !isCachedWorkerPayloadUsable(cachedPayload)) {
    clearOfflineLoginData();
    return { restored: false, message: t("offlineLoginFailed") };
  }
  if (normalizeBadgeIdInput(offlineProfile.badgeId) !== normalizedBadgeId) {
    return { restored: false, message: t("offlineLoginFailed") };
  }

  const expectedPinHash = await hashSensitiveValue(`${normalizedBadgeId}:${normalizeBadgePinInput(badgePin)}`);
  if (offlineProfile.pinHash !== expectedPinHash) {
    return { restored: false, message: t("badgePinWrong"), code: "invalid_badge_pin" };
  }

  const siteLocation = cachedPayload?.worker?.siteLocation;
  const hasSiteGeo = siteLocation && typeof siteLocation.latitude === "number" && typeof siteLocation.longitude === "number";
  let distanceMeters = null;
  if (hasSiteGeo && locationPayload) {
    distanceMeters = Math.round(calculateDistanceMeters(siteLocation.latitude, siteLocation.longitude, locationPayload.latitude, locationPayload.longitude));
    if (distanceMeters > Number(siteLocation.radiusMeters || 100)) {
      return { restored: false, message: tf("offlineLoginOnSiteOnly", { meters: distanceMeters }) };
    }
  }
  // No GPS available or no site location configured → allow PIN-based offline login

  offlineWorkerSessionActive = true;
  workerToken = wpGet(WORKER_TOKEN_KEY) || "";
  wpSet(WORKER_BADGE_LOGIN_KEY, normalizedBadgeId);
  renderWorker(cachedPayload);
  updateConnectionState();
  if (elements.lastSyncInfo) {
    elements.lastSyncInfo.textContent = t("offlineLoginActiveWaitingSync");
  }
  queueOfflineEvent({
    type: "offline_login",
    occurredAt: new Date().toISOString(),
    distanceMeters,
  });
  initializeSessionInactivityProtection();
  return { restored: true };
}

async function syncOfflinePhotoQueue() {
  let queue = [];
  try {
    queue = JSON.parse(wpGet(OFFLINE_PHOTO_QUEUE_KEY) || "[]");
  } catch {
    queue = [];
  }

  if (!queue.length || !workerToken) {
    return;
  }

  const pending = [];
  for (const item of queue) {
    try {
      await fetchJson(`${API_BASE}/photo`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${workerToken}`
        },
        body: JSON.stringify({ photoData: item.dataUrl })
      });
    } catch {
      pending.push(item);
    }
  }

  wpSet(OFFLINE_PHOTO_QUEUE_KEY, JSON.stringify(pending));
  updateSmartWorkHub(lastWorkerPayload, lastTimesheetRows);
}

async function syncOfflineEventQueue() {
  const queue = readStoredJson(OFFLINE_EVENT_QUEUE_KEY, []);
  if (!queue.length || !workerToken) {
    return;
  }

  try {
    await fetchJson(`${API_BASE}/offline-events`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${workerToken}`
      },
      body: JSON.stringify({ events: queue })
    });
    writeStoredJson(OFFLINE_EVENT_QUEUE_KEY, []);
    updateSmartWorkHub(lastWorkerPayload, lastTimesheetRows);
  } catch {
    // keep queue for next sync attempt
    updateSmartWorkHub(lastWorkerPayload, lastTimesheetRows);
  }
}

async function manualSyncOfflineData() {
  if (!navigator.onLine) {
    showWorkerNotice(t("syncOfflineNoConnection"));
    return;
  }

  if (!workerToken) {
    showWorkerNotice(t("syncOfflineNotLoggedIn"));
    return;
  }

  try {
    showWorkerNotice(t("syncOfflineStarting"));
    
    // Sync offline events first
    await syncOfflineEventQueue();
    
    // Sync offline photos
    await syncOfflinePhotoQueue();
    
    await loadWorkerData();
    
    showWorkerNotice(t("syncOfflineCompleted"));
    updateConnectionState();
    
  } catch (error) {
    console.error("Manual sync failed:", error);
    showWorkerNotice(t("syncOfflineFailed"));
  }
}

function registerWorkerSw() {
  if (!("serviceWorker" in navigator)) {
    return;
  }

  // iPhone: SW update reload during PIN entry was logging users out — register after login.
  if (isIosDevice() && !getWorkerAuthorizationValue()) {
    window.__deferredWorkerSwRegistration = true;
    return;
  }
  
  // CRITICAL: Clear old SW registrations from worker.html path before registering new emp-app.js SW
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.getRegistrations()
      .then((regs) => {
        regs.forEach((reg) => {
          // Unregister old worker.html SWs to prevent conflicts
          if (reg.scope.includes("worker.html")) {
            reg.unregister().catch(() => {});
          }
        });
      })
      .catch(() => {});
  }
  
  navigator.serviceWorker.addEventListener("message", (event) => {
    if (event.data?.type === "NAVIGATE_WORKER_APP") {
      navigateWorkerAppFromNotification(event.data.url);
    }
  });

  navigator.serviceWorker.register(`./worker-sw.js?v=${WORKER_BUILD_TAG}`).then((registration) => {
    registration.update().catch(() => {});

    const handleControllerChange = () => {
      updateWorkerBuildBadge();
      if (sessionStorage.getItem("workpass-sw-reloaded")) {
        return;
      }
      const loginGraceMs = Date.now() - Number(window.__workerLoginCompletedAt || 0);
      if (
        document.body.classList.contains("worker-loaded")
        || getWorkerAuthorizationValue()
        || document.body.classList.contains("qr-fast-login")
        || loginGraceMs <= 120000
      ) {
        return;
      }
      sessionStorage.setItem("workpass-sw-reloaded", "1");
      window.location.reload();
    };
    navigator.serviceWorker.addEventListener("controllerchange", handleControllerChange);

    // Force-activate waiting SW immediately without delay.
    function activateWaiting(sw) {
      if (!sw) return;
      sw.postMessage({ type: "SKIP_WAITING" });
    }

    if (registration.waiting) {
      // There's already a waiting SW — activate it now.
      activateWaiting(registration.waiting);
    }
    registration.addEventListener("updatefound", () => {
      const newSw = registration.installing;
      if (!newSw) return;
      newSw.addEventListener("statechange", () => {
        if (newSw.state === "installed") {
          // Activate immediately — no user confirmation needed.
          activateWaiting(newSw);
        }
      });
    });
  }).catch(() => {});
}

function workerSwCachePrefixes() {
  return ["baupass-worker-", "workpass-worker-"];
}

function deleteStaleWorkerCaches(exceptBuild = WORKER_BUILD_TAG) {
  if (!("caches" in window)) {
    return Promise.resolve();
  }
  return caches.keys().then((keys) => Promise.all(
    keys
      .filter((key) => workerSwCachePrefixes().some((prefix) => key.startsWith(prefix)) && !key.includes(exceptBuild))
      .map((key) => caches.delete(key))
  ));
}

function enforceWorkerBuildFreshness(params = null) {
  const buildTag = WORKER_BUILD_TAG;
  const LAST_BUILD_VERSION_KEY = WP?.KEYS?.WORKER_LAST_BUILD_TAG || "workpass-worker-last-build-tag";
  const lastBuildTag = window.localStorage.getItem(LAST_BUILD_VERSION_KEY);
  const qrBootstrap = isQrBootstrapEntry(params);

  if (lastBuildTag && lastBuildTag !== buildTag) {
    void deleteStaleWorkerCaches(buildTag);
    try {
      if (!getWorkerAuthorizationValue() && !qrBootstrap) {
        wpRemove(WORKER_CACHED_PAYLOAD_KEY);
        wpRemove(WORKER_OFFLINE_LOGIN_PROFILE_KEY);
      }
    } catch {
      // ignore localStorage failures
    }
  }

  try {
    window.localStorage.setItem(LAST_BUILD_VERSION_KEY, buildTag);
  } catch {
    // ignore localStorage failures
  }

  try {
    const url = new URL(window.location.href);
    url.searchParams.delete("refresh");
    if (url.searchParams.get("v") !== buildTag) {
      url.searchParams.set("v", buildTag);
    }
    if (url.toString() !== window.location.href) {
      window.history.replaceState({}, "", url.toString());
    }
  } catch {
    // ignore URL rewrite failures
  }

  void deleteStaleWorkerCaches(buildTag);

  if ("serviceWorker" in navigator && getWorkerAuthorizationValue()) {
    navigator.serviceWorker.getRegistrations()
      .then((regs) => Promise.all(regs.map((reg) => reg.update().catch(() => {}))))
      .catch(() => {});
  }
}

function wireInstallPrompt() {
  updatePlatformInstallHint();
  window.addEventListener("beforeinstallprompt", (event) => {
    deferredInstallPrompt = event;
    if (elements.installButton) {
      elements.installButton.hidden = false;
    }
  });
}

function isStandaloneMode() {
  return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

async function triggerInstall() {
  if (deferredInstallPrompt) {
    deferredInstallPrompt.prompt();
    await deferredInstallPrompt.userChoice;
    deferredInstallPrompt = null;
    if (elements.installButton) {
      elements.installButton.hidden = true;
    }
    return;
  }

  if (isStandaloneMode()) {
    showWorkerNotice(t("installAlreadyInstalled"));
    return;
  }

  if (isIosDevice()) {
    showWorkerNotice(t("installIosHowto"));
    return;
  }

  if (isAndroidDevice()) {
    showWorkerNotice(t("installAndroidHowto"));
    return;
  }

  showWorkerNotice(t("installManual"));
}

async function forceRefreshApp() {
  showWorkerNotice("Aktualisiere App-Version ...");

  if ("serviceWorker" in navigator) {
    try {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map(async (reg) => {
        try {
          await reg.update();
        } catch {
          // ignore update failures
        }
        if (reg.waiting) {
          reg.waiting.postMessage({ type: "SKIP_WAITING" });
        }
      }));
    } catch {
      // ignore registration failures
    }
  }

  if ("caches" in window) {
    try {
      await deleteStaleWorkerCaches();
    } catch {
      // ignore cache failures
    }
  }

  try {
    const nextUrl = new URL(window.location.href);
    nextUrl.searchParams.set("v", WORKER_BUILD_TAG);
    nextUrl.searchParams.delete("refresh");
    window.history.replaceState({}, "", nextUrl.toString());
  } catch {
    // ignore URL cleanup failures
  }
  window.location.reload();
}

function workerLoginConnectionErrorMessage(error) {
  refreshWorkerApiBase();
  if (typeof tf === "function") {
    return tf("loginServerUnreachable", { server: API_BASE });
  }
  return `${t("connError")} (${API_BASE})`;
}

async function loginWithAccessToken(accessToken, { keepUrlToken = false, silent = false, locationPayload = null } = {}) {
  if (!accessToken) {
    if (!silent) {
      showWorkerNotice(t("enterAccessCode"));
    }
    return;
  }
  if (isWorkerShellAuthenticated()) {
    return;
  }

  if (!silent) {
    clearLoginError();
  }

  try {
    const devicePayload = buildWorkerDevicePayload();
    const payload = await fetchJson(`${API_BASE}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        accessToken,
        location: locationPayload,
        ...(devicePayload ? { device: devicePayload } : {}),
      })
    });

    offlineWorkerSessionActive = false;
    persistWorkerSessionCredentials(payload);
    wpSet(WORKER_ACCESS_TOKEN_KEY, accessToken);
    wpRemove(WORKER_BADGE_LOGIN_KEY);
    applyDynamicManifestStartUrl(accessToken);
    persistLoginBootstrapPayload(payload);
    await completeWorkerLogin(payload, {
      autoCheckInLogId: payload.autoCheckInLogId,
      showInstallTip: !silent,
    });

    clearBootstrapAccessTokens();
    try {
      const cached = JSON.parse(wpGet(WORKER_CACHED_PAYLOAD_KEY) || "{}");
      const badgeId = cached.worker?.badgeId || cached.badgeId || "";
      if (badgeId) {
        wpSet(WORKER_BADGE_LOGIN_KEY, badgeId);
      }
    } catch {
      // Nicht kritisch
    }
  } catch (error) {
    if (isWorkerShellAuthenticated() || workerToken) {
      return;
    }
    if (isWorkerLoginNetworkError(error)) {
      clearBootstrapAccessTokens();
      if (!silent) {
        showLoginError(workerLoginConnectionErrorMessage(error), { code: "network_error" });
      } else {
        showLogin();
      }
      return;
    }
    if (error.code === "access_token_already_used") {
      clearBootstrapAccessTokens();
      if (workerToken || isWorkerShellAuthenticated()) {
        return;
      }
      const existingToken = wpGet(WORKER_TOKEN_KEY);
      if (existingToken) {
        workerToken = existingToken;
        const loaded = await loadWorkerData();
        if (loaded || isWorkerShellAuthenticated()) {
          return;
        }
      }
      const fallbackBadgeId = normalizeBadgeIdInput(
        error?.payload?.badgeId || error?.payload?.badge_id || getLoginBadgeCredential(),
      );
      if (fallbackBadgeId && !isWorkerShellAuthenticated()) {
        wpSet(WORKER_BADGE_LOGIN_KEY, fallbackBadgeId);
        prepareQrPinOnlyLogin(fallbackBadgeId);
        showLoginError(
          t("qrLinkUsedEnterPin") + " " + t("oneTimeLinkMobileHint"),
          { focusPin: true },
        );
      } else if (!isWorkerShellAuthenticated()) {
        showLoginError(t("qrLinkInvalidRescan") + " " + t("oneTimeLinkMobileHint"));
      }
      return;
    }
    if (["invalid_access_token", "access_token_revoked", "access_token_expired"].includes(error.code)) {
      clearBootstrapAccessTokens();
      if (workerToken || isWorkerShellAuthenticated()) {
        return;
      }
      const fallbackBadge = getLoginBadgeCredential();
      if (fallbackBadge) {
        prepareQrPinOnlyLogin(fallbackBadge);
      }
      showLoginError(t("qrLinkInvalidRescan") + " " + t("oneTimeLinkMobileHint"));
      return;
    }
    if (error.code === "visitor_visit_expired") {
      clearBootstrapAccessTokens();
      showLoginError(t("visitorExpiredNeedLink"));
      return;
    }
    if (silent) {
      showLogin();
      return;
    }
    if (error.code === "worker_app_disabled" || error.code === "feature_not_available") {
      showLoginError(t("workerAppDisabled"));
      return;
    }
    showLoginError(`${t("accessFailed")}: ${error.message || t("loginFailed")}`);
  }
}

async function loginWithBadgeId(badgeId, badgePin, { silent = false, locationPayload = null, qrLaunch = false } = {}) {
  if (isWorkerShellAuthenticated()) {
    return;
  }
  const normalizedBadgeId = normalizeBadgeIdInput(badgeId);
  const normalizedBadgePin = normalizeBadgePinInput(badgePin);
  if (!normalizedBadgeId) {
    if (!silent) {
      showLoginError(t("enterBadgeId"), { code: "invalid_badge_id" });
    }
    return;
  }
  const visitorLogin = isVisitorBadgeId(normalizedBadgeId);
  if (!visitorLogin && !normalizedBadgePin) {
    if (!silent) {
      showLoginError(t("enterPin"), { focusPin: true });
    }
    return;
  }

  if (!silent) {
    clearLoginError();
  }

  const effectiveLocation = locationPayload || null;

  workerLoginInFlight = true;
  try {
    const devicePayload = buildWorkerDevicePayload();
    const payload = await fetchJson(`${API_BASE}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        badgeId: normalizedBadgeId,
        badgePin: normalizedBadgePin,
        qrLaunch: qrLaunch || shouldTreatLoginAsQrLaunch(),
        ...(devicePayload ? { device: devicePayload } : {}),
        ...(effectiveLocation ? { location: effectiveLocation } : {}),
      })
    });

    offlineWorkerSessionActive = false;
    persistWorkerSessionCredentials(payload);
    wpSet(WORKER_BADGE_LOGIN_KEY, normalizedBadgeId);
    wpRemove(WORKER_ACCESS_TOKEN_KEY);
    if (elements.workerAccessToken) {
      elements.workerAccessToken.value = normalizedBadgeId;
    }
    if (elements.workerBadgePin) {
      elements.workerBadgePin.value = "";
    }
    // Store PIN in sessionStorage for offline fallback (not persisted, not in DOM)
    if (normalizedBadgePin) {
      try { sessionStorage.setItem("_wpf", normalizedBadgePin); } catch (_) {}
      storeProximityPin(normalizedBadgePin);
    }
    persistLoginBootstrapPayload(payload);
    await persistOfflineBadgeProfile(normalizedBadgeId, normalizedBadgePin, payload);
    await completeWorkerLogin(payload, {
      autoCheckInLogId: payload.autoCheckInLogId,
      siteLoginLogId: payload.siteLoginLogId,
      showInstallTip: !silent,
    });
  } catch (error) {
    if (shouldAttemptOfflineWorkerLogin(error)) {
      const restoreResult = await tryOfflineBadgeLogin(normalizedBadgeId, normalizedBadgePin, locationPayload);
      if (restoreResult.restored) {
        return;
      }
      if (!silent) {
        const authCode = restoreResult.code || error.code || "";
        let notice = "";
        if (authCode === "invalid_badge_pin") {
          notice = t("badgePinWrong");
        } else if (authCode === "invalid_badge_id") {
          notice = t("badgeNotFound");
        } else if (isWorkerLoginNetworkError(error)) {
          notice = workerLoginConnectionErrorMessage(error);
        } else {
          notice = restoreResult.message || `${t("loginFailed")}: ${workerLoginErrorMessage(error)}`;
        }
        if (notice) {
          showLoginError(notice, { code: authCode, focusPin: authCode === "invalid_badge_pin" });
        }
      }
      return;
    }
    if (silent && !document.body.classList.contains("qr-fast-login")) {
      showLogin();
      return;
    }
    if (error.code === "visitor_visit_expired") {
      wpRemove(WORKER_BADGE_LOGIN_KEY);
      showLoginError(t("visitorExpiredBadgeLogin"));
      return;
    }
    if (error.code === "worker_app_disabled") {
      showLoginError(t("workerAppDisabled"));
      return;
    }
    if (error.code === "worker_geolocation_required") {
      showLoginError(t("geolocationRequiredLogin"), { code: error.code });
      return;
    }
    if (error.code === "outside_site_radius") {
      showLoginError(error.message || t("outsideSiteRadius"), { code: error.code });
      return;
    }
    if (error.message === "site_location_unavailable") {
      showLoginError(t("siteLocationUnavailable"));
      return;
    }
    showLoginError(workerLoginErrorMessage(error), {
      code: error.code || "",
      focusPin: error.code === "invalid_badge_pin" || error.code === "missing_badge_pin",
    });
    if (normalizedBadgeId && !isWorkerShellAuthenticated()) {
      prepareQrPinOnlyLogin(normalizedBadgeId, { readOnly: true, focusPin: true });
    }
  } finally {
    workerLoginInFlight = false;
  }
}

async function loadWorkerData(options = {}) {
  const quiet = Boolean(options.quiet);
  if (!workerToken) {
    console.warn("[loadWorkerData] No worker token – showing login");
    showLogin();
    return false;
  }
  const tokenAtRequest = workerToken;

  workerDebug("[loadWorkerData] Starting fetch for /me...");
  try {
    const payload = await fetchJson(`${API_BASE}/me?lang=${encodeURIComponent(currentLang || "de")}`);
    if (!tokenAtRequest || tokenAtRequest !== workerToken) {
      // Ignore stale response after logout/login switch.
      return false;
    }
    workerDebug("[loadWorkerData] Success:", payload);
    const nextSerialized = JSON.stringify(payload);
    const cachedRaw = wpGet(WORKER_CACHED_PAYLOAD_KEY);
    const unchanged = cachedRaw === nextSerialized && document.body.classList.contains("worker-loaded");
    wpSet(WORKER_CACHED_PAYLOAD_KEY, nextSerialized);
    offlineWorkerSessionActive = false;
    if (!unchanged) {
      renderWorker(payload);
    } else if (quiet) {
      markWorkerSyncedNow();
      updateConnectionState();
    } else {
      restoreWorkerPassLayout(payload);
      markWorkerSyncedNow();
      updateConnectionState();
    }
    if (!unchanged || !quiet) {
      releaseSplashEarly();
    }
    void syncOfflinePhotoQueue();
    void syncOfflineEventQueue();
    return true;
  } catch (error) {
    if (!tokenAtRequest || tokenAtRequest !== workerToken) {
      // Ignore stale request failures after auth state changes.
      return false;
    }
    // Session expired or revoked — keep shell right after login or when cache exists
    if (isWorkerSessionAuthError(error?.code)) {
      if (shouldKeepWorkerShellAfterSyncError(error)) {
        return true;
      }
      invalidateWorkerSession({ showNotice: true });
      return false;
    }
    if (shouldKeepWorkerShellAfterSyncError(error)) {
      return true;
    }
    // Network error — show cached data if available
    console.warn("[loadWorkerData] Network error:", error.message);
    const cachedRaw = wpGet(WORKER_CACHED_PAYLOAD_KEY);
    if (cachedRaw) {
      try {
        const cachedPayload = JSON.parse(cachedRaw);
        workerDebug("[loadWorkerData] Rendering cached payload:", cachedPayload);
        offlineWorkerSessionActive = true;
        renderWorker(cachedPayload);
        releaseSplashEarly();
        if (elements.lastSyncInfo) {
          elements.lastSyncInfo.textContent = t("offlineBanner");
        }
        updateWorkerPulsePanel();
        return true;
      } catch (cacheErr) {
        console.error("[loadWorkerData] Cache parse error:", cacheErr);
        // corrupt cache — fall through to logout
      }
    }
    console.warn("[loadWorkerData] No cache available – keeping login shell UI");
    if (!document.body.classList.contains("worker-loaded")) {
      wpRemove(WORKER_TOKEN_KEY);
      wpRemove(WORKER_JWT_KEY);
      workerToken = "";
      workerBearerToken = "";
      clearWorkerSessionExpiryTimer();
      showWorkerNotice(`${t("connError")}: ${error.message}`);
      showLogin(true);
    }
    return false;
  }
}

function restoreWorkerPassLayout(payload) {
  if (!payload || !document.body.classList.contains("worker-loaded")) {
    return;
  }
  const worker = payload.worker || {};
  const identityLock = payload.identityLock || null;
  const identityBlocked = String(worker.workerType || "worker").trim().toLowerCase() !== "visitor"
    && Boolean(identityLock?.identityBlocked);
  const qrPayload = identityBlocked ? "" : buildQrPayload(worker);
  const isCompactViewport = window.matchMedia("(max-width: 520px)").matches;
  const workerQrSize = isCompactViewport ? 520 : 460;
  if (elements.workerQr && qrPayload) {
    elements.workerQr.classList.remove("hidden");
    void setQrImage(elements.workerQr, qrPayload, workerQrSize);
  }
  if (elements.badgeCard) {
    elements.badgeCard.classList.remove("card-entrance-active", "card-transition-top");
  }
  document.body.classList.remove("card-animating", "card-transitioned");
  if (document.body.classList.contains("worker-loaded")) {
    switchToTab(currentActiveTab);
  }
}

function renderWorker(payload) {
  const previousPayload = lastWorkerPayload;
  const planFeatures = payload.planFeatures && Object.keys(payload.planFeatures).length
    ? payload.planFeatures
    : (previousPayload?.planFeatures && Object.keys(previousPayload.planFeatures).length
      ? previousPayload.planFeatures
      : (payload.planFeatures || {}));
  lastWorkerPayload = { ...payload, planFeatures };
  const worker = payload.worker || {};
  const company = payload.company || {};
  const subcompany = payload.subcompany || {};
  const workerBadgeId = String(worker.badgeId || worker.badge_id || "").trim();
  const companyPreset = normalizeCompanyBrandingPreset(company.brandingPreset || company.branding_preset);
  const normalizedStatus = String(worker.status || "").trim().toLowerCase();
  const workerType = String(worker.workerType || "worker").trim().toLowerCase();
  const isVisitor = workerType === "visitor";
  const sessionExpiresAt = String(payload.sessionExpiresAt || "").trim();

  // ── Pass-Lock aktivieren wenn Admin-Setting es erlaubt ──
  pinLockEnabled = payload.settings?.workerPassLockEnabled === 1 || payload.settings?.workerPassLockEnabled === "1";
  if (pinLockEnabled) {
    initializePassLockProtection();
  }

  applyWorkerCompanyBranding({
    companyPreset,
    companyName: company.name || "",
    portalDisplayName: company.portalDisplayName || company.portal_display_name,
    brandingAccentColor: company.brandingAccentColor || company.branding_accent_color,
    brandingLogoData: company.brandingLogoData || company.branding_logo_data,
  });
  applyWorkerSectorTerms(company);

  if (elements.workerPassTitle) {
    elements.workerPassTitle.textContent = isVisitor ? t("visitorCardTitle") : t("workerCardTitle");
  }
  if (elements.workerPassSubLabels && elements.workerPassSubLabels.length) {
    const passSubLabel = isVisitor ? t("visitorPassSubLabel") : t("workerPassSubLabel");
    elements.workerPassSubLabels.forEach((el) => {
      el.textContent = passSubLabel;
    });
  }

  if (elements.companyName) {
    elements.companyName.textContent = resolveWorkerCardBrandTitle({
      portalDisplayName: company.portalDisplayName || company.portal_display_name,
      companyName: company.name || "",
    }) || t("companyFallback");
  }
  if (elements.workerSubcompany) {
    const subcompanyName = String(subcompany.name || "").trim();
    if (subcompanyName) {
      elements.workerSubcompany.textContent = `Sub: ${subcompanyName}`;
      elements.workerSubcompany.title = `Sub: ${subcompanyName}`;
      elements.workerSubcompany.classList.remove("hidden");
    } else {
      elements.workerSubcompany.textContent = "";
      elements.workerSubcompany.title = "";
      elements.workerSubcompany.classList.add("hidden");
    }
  }
  if (elements.workerName) elements.workerName.textContent = `${worker.firstName || ""} ${worker.lastName || ""}`.trim();
  if (elements.workerRole) elements.workerRole.textContent = isVisitor ? t("visitorRole") : (worker.role || "-");
  if (elements.workerStatus) {
    elements.workerStatus.textContent = worker.status || "-";
    elements.workerStatus.dataset.status = normalizedStatus;
  }
  updateWorkerNextStepPanel({ worker, companyPreset, isVisitor });
  void refreshWorkerNotificationCenter({ silent: true, notifyNew: true });
  startWorkerNotificationPolling();
  updateSmartWorkHub(payload, lastTimesheetRows);
  applySiteAccessUi(payload);
  if (elements.workerBadgeId) elements.workerBadgeId.textContent = workerBadgeId || "-";
  if (elements.workerSite) elements.workerSite.textContent = worker.site || "-";
  updateSiteMapLink(worker.site || "");
  if (elements.workerValidUntil) elements.workerValidUntil.textContent = formatDate(worker.validUntil);
  renderDayCardValidity(sessionExpiresAt);
  scheduleWorkerSessionExpiry(sessionExpiresAt);
  if (elements.workerVisitorMeta) {
    elements.workerVisitorMeta.classList.toggle("hidden", !isVisitor);
  }
  if (elements.workerVisitorCompany) {
    elements.workerVisitorCompany.textContent = worker.visitorCompany || "-";
  }
  if (elements.workerVisitPurpose) {
    elements.workerVisitPurpose.textContent = worker.visitPurpose || "-";
  }
  if (elements.workerHostName) {
    elements.workerHostName.textContent = worker.hostName || "-";
  }
  if (elements.workerVisitEndAt) {
    elements.workerVisitEndAt.textContent = worker.visitEndAt ? formatDateTime(worker.visitEndAt) : "-";
  }

  if (elements.workerPhoto) {
    if (worker.photoData && String(worker.photoData).startsWith("data:image")) {
      elements.workerPhoto.src = worker.photoData;
      wpSet(LOCAL_LAST_PHOTO_KEY, worker.photoData);
    } else {
      const localPhoto = wpGet(LOCAL_LAST_PHOTO_KEY);
      elements.workerPhoto.src = localPhoto && localPhoto.startsWith("data:image")
        ? localPhoto
        : createAvatar(worker.firstName, worker.lastName);
    }
  }

  dqrWorkerBadgeId = workerBadgeId;
  const identityLock = payload.identityLock || null;
  const identityBlocked = !isVisitor && Boolean(identityLock?.identityBlocked);
  const qrPayload = identityBlocked ? "" : buildQrPayload(worker);
  const isCompactViewport = window.matchMedia("(max-width: 520px)").matches;
  const workerQrSize = isCompactViewport ? 520 : 460;
  const gateQrSize = isCompactViewport ? 520 : 420;
  if (elements.workerQr) {
    if (!qrPayload) {
      elements.workerQr.removeAttribute("src");
      elements.workerQr.classList.add("hidden");
    } else {
      elements.workerQr.classList.remove("hidden");
      void setQrImage(elements.workerQr, qrPayload, workerQrSize);
    }
  }

  if (elements.qrFallbackText) {
    if (!qrPayload) {
      elements.qrFallbackText.textContent = t("noQrAvailable");
      elements.qrFallbackText.classList.remove("hidden");
    } else {
      elements.qrFallbackText.textContent = `Code: ${qrPayload}`;
      elements.qrFallbackText.classList.remove("hidden");
    }
  }

  if (elements.gateQr) {
    if (!qrPayload) {
      elements.gateQr.removeAttribute("src");
      elements.gateQr.classList.add("hidden");
    } else {
      elements.gateQr.classList.remove("hidden");
      void setQrImage(elements.gateQr, qrPayload, gateQrSize);
    }
  }

  if (elements.gateBadgeId) {
    elements.gateBadgeId.textContent = qrPayload ? tf("badgeValue", { value: qrPayload }) : t("badgeUnset");
  }

  if (elements.gateWorkerName) {
    elements.gateWorkerName.textContent = `${worker.firstName || ""} ${worker.lastName || ""}`.trim() || t("workerDefaultName");
  }

  // Update Status Banner
  if (elements.workerStatusBanner && elements.workerStatusText) {
    const banned = String(worker.banned || "false").trim().toLowerCase() === "true";
    const validUntilDate = new Date(worker.validUntil || "");
    const isExpired = validUntilDate < new Date();
    
    elements.workerStatusBanner.classList.remove("status-banner-hidden");
    
    if (identityBlocked) {
      elements.workerStatusBanner.className = "status-banner warning";
      elements.workerStatusText.textContent = identityLock?.lockReason || identityLock?.message || "Badge inactive";
    } else if (banned) {
      elements.workerStatusBanner.className = "status-banner error";
      elements.workerStatusText.textContent = t("statusRevoked");
    } else if (isExpired) {
      elements.workerStatusBanner.className = "status-banner warning";
      elements.workerStatusText.textContent = t("statusExpired");
    } else {
      elements.workerStatusBanner.className = "status-banner active";
      elements.workerStatusText.textContent = t("statusActive");
    }
  }

  // ════════════════════════════════════════════════════════════════
  // PREMIUM VISITOR CARD RENDERING
  // ════════════════════════════════════════════════════════════════
  const visitorCardContainer = document.getElementById("visitorCardContainer");
  if (visitorCardContainer) {
    visitorCardContainer.classList.toggle("hidden", !isVisitor);
    
    if (isVisitor) {
      // Update visitor card with premium styling
      const visitorName = document.getElementById("visitorName");
      const visitorCompany = document.getElementById("visitorCompany");
      const visitorPurpose = document.getElementById("visitorPurpose");
      const visitorHost = document.getElementById("visitorHost");
      const visitorEndTime = document.getElementById("visitorEndTime");
      const visitorBadgeId = document.getElementById("visitorBadgeId");
      const visitorPhoto = document.getElementById("visitorPhoto");
      const visitorQr = document.getElementById("visitorQr");
      
      // Set visitor information
      if (visitorName) visitorName.textContent = `${worker.firstName || ""} ${worker.lastName || ""}`.trim() || t("workerDefaultName");
      if (visitorCompany) visitorCompany.textContent = worker.visitorCompany || "-";
      if (visitorPurpose) visitorPurpose.textContent = worker.visitPurpose || "-";
      if (visitorHost) visitorHost.textContent = worker.hostName || "-";
      if (visitorEndTime) visitorEndTime.textContent = worker.visitEndAt ? formatDateTime(worker.visitEndAt) : "-";
      if (visitorBadgeId) visitorBadgeId.textContent = workerBadgeId || "-";
      
      // Set visitor photo
      if (visitorPhoto) {
        if (worker.photoData && String(worker.photoData).startsWith("data:image")) {
          visitorPhoto.src = worker.photoData;
        } else {
          const localPhoto = wpGet(LOCAL_LAST_PHOTO_KEY);
          visitorPhoto.src = localPhoto && localPhoto.startsWith("data:image")
            ? localPhoto
            : createAvatar(worker.firstName, worker.lastName);
        }
      }
      
      // Set visitor QR code
      if (visitorQr && qrPayload) {
        void setQrImage(visitorQr, qrPayload, 160);
      }
      
      // Start visitor countdown timer
      startVisitorCountdownTimer(worker.visitEndAt);
      
      // Keep the badge card container visible, but hide the worker wallet content
      if (elements.walletCard) elements.walletCard.classList.add("hidden");

        // Apply the same card preset to the visitor badge card
        const visitorWalletCard = document.getElementById("visitorWalletCard");
        if (visitorWalletCard) {
          visitorWalletCard.classList.remove("preset-construction", "preset-industry", "preset-premium", "preset-visitor");
          visitorWalletCard.classList.add(`preset-${companyPreset}`);
        }
    } else {
      // Stop visitor timer if switching to worker
      stopVisitorCountdownTimer();
      if (elements.walletCard) elements.walletCard.classList.remove("hidden");
    }
  }

  if (elements.loginCard) elements.loginCard.classList.add("hidden");
  document.body.classList.add("worker-loaded");
  window.scrollTo(0, 0);
  document.documentElement.scrollTop = 0;
  document.body.scrollTop = 0;
  updateWalletImmersiveMode();
  setWorkerHubExpanded(false);
  haptic([18, 35, 22]);

  if (!isWorkerCardInstallEntry()) {
    syncWorkerDataToDashboard(lastWorkerPayload);
  }
  syncHomeCompactInfo(lastWorkerPayload);
  
  // Keep the UX stable after login: no forced fullscreen showcase.
  
  // Show bottom nav immediately after login
  const bottomNav = document.getElementById("workerBottomNav");
  if (bottomNav) {
    bottomNav.classList.remove("hidden");
  }
  
  // Show top bar
  const topBar = document.getElementById("topPanel");
  if (topBar) {
    topBar.classList.remove("hidden");
  }

  enforceUiVisibilityGuard();

  // Disable legacy entrance flow in the tab-first UI.
  clearCardEntranceAnimation();
  
  // Start dynamic QR lifecycle as soon as pass is visible.
  if (identityBlocked) {
    stopDynamicQrRefresh();
    showWorkerNotice(identityLock?.lockReason || identityLock?.message || "Badge inactive");
  } else {
    hideWorkerNotice();
    startDynamicQrRefresh();
  }
  if (elements.workerQuickMenu) {
    elements.workerQuickMenu.classList.add("hidden");
  }
  if (quickMenuObserver) {
    quickMenuObserver.disconnect();
    quickMenuObserver = null;
  }
  
  // Keep leave page hidden until user opens the Vacation tab.
  if (elements.leaveRequestCard) {
    elements.leaveRequestCard.classList.add("hidden");
  }
  if (elements.quickGateModeButton) {
    elements.quickGateModeButton.classList.add("hidden");
  }

  // Show leave balance badge
  const leaveStats = payload.leaveStats;
  const balanceBadge = document.getElementById("leaveBalanceBadge");
  const balanceRemaining = document.getElementById("leaveBalanceRemaining");
  if (leaveStats && balanceBadge && balanceRemaining && !isVisitor) {
    balanceRemaining.textContent = leaveStats.remaining;
    balanceBadge.classList.remove("hidden");
    balanceBadge.title = `Anspruch: ${leaveStats.balance} Tage · Genommen: ${leaveStats.taken} Tage`;
    const pct = leaveStats.balance > 0 ? leaveStats.remaining / leaveStats.balance : 1;
    balanceBadge.className = "leave-balance-badge" + (pct <= 0.1 ? " low" : pct <= 0.3 ? " medium" : "");
  }

  // Late check-in notification banner
  const lateInfo = payload.lateCheckIn;
  showLateCheckInBanner(lateInfo, isVisitor);

  // Plan-Feature-Gates (keep last known entitlements when offline cache omits planFeatures)
  applyWorkerPlanNavState(planFeatures);
  applyWorkerDeploymentMenuState(planFeatures);
  applyWorkerChatMenuState(planFeatures);
  if (workerToken && workerPlanAllowsFeature("worker_chat")) {
    startWorkerChatPolling();
  }
  void refreshHomeDeploymentTeaser().catch(() => {});
  const hasLateAlert    = !!planFeatures.late_checkin_alert;   // ab professional

  // Show voice control for workers. If API is unavailable, fallback input is used.
  if (elements.voiceCommandBtn) {
    const SpeechRecognitionApi = window.SpeechRecognition || window.webkitSpeechRecognition;
    const voiceSupported = Boolean(SpeechRecognitionApi);
    const secureContextOk = Boolean(window.isSecureContext);
    const canUseVoice = !isVisitor;

    elements.voiceCommandBtn.classList.toggle("hidden", !canUseVoice);
    elements.voiceCommandBtn.disabled = !canUseVoice;
    elements.voiceCommandBtn.classList.remove("listening");

    if (!voiceSupported || !secureContextOk) {
      elements.voiceCommandBtn.title = t("voiceFallbackHint");
    } else {
      elements.voiceCommandBtn.title = "";
    }
  }

  // Re-show late banner only if plan allows it
  if (!hasLateAlert) {
    const lateBanner = document.getElementById("lateCheckInBanner");
    if (lateBanner) lateBanner.remove();
  }

  // Keep bottom-tab pages in sync with the active tab (avoid breaking pass layout on background refresh).
  if (document.body.classList.contains("worker-loaded")) {
    switchToTab(currentActiveTab);
  } else {
    if (elements.timesheetCard) {
      elements.timesheetCard.classList.add("hidden");
    }
    if (elements.documentsCard) {
      elements.documentsCard.classList.add("hidden");
    }
    const leaveCard = document.getElementById("leaveRequestCard");
    if (leaveCard) {
      leaveCard.classList.add("hidden");
    }
  }

  // Load section data after render.
  if (!isVisitor && (currentActiveTab === "vacation" || !document.body.classList.contains("worker-loaded"))) {
    void loadLeaveRequests();
  }
  if (!isVisitor && currentActiveTab === "vacation") {
    void loadIncidents();
  }
  if (leaveRefreshInterval) {
    clearInterval(leaveRefreshInterval);
  }
  if (!isVisitor) {
    leaveRefreshInterval = setInterval(() => {
      if (workerToken && currentActiveTab === "vacation") {
        void loadLeaveRequests();
      }
    }, 60000);
  }
  if (!isVisitor) void loadMyTimesheets();
  if (!isVisitor) void loadMyDocuments();
  renderCompanyModeExperience(companyPreset, isVisitor);
  void prefillCompanyAdminEmails();
  updateWorkerPulsePanel();

  if (isWorkerCardInstallEntry()) {
    document.body.classList.add("worker-card-install");
  }
  if (!isVisitor) {
    void ensureWorkerPushNotifications({ promptIfNeeded: false });
  }

  const launchHash = (window.location.hash || "").toLowerCase();
  if (!isVisitor && (launchHash === "#einsatzplan" || launchHash === "#deployment")) {
    void openWorkerDeploymentPlanScreen();
  } else {
    switchToTab(currentActiveTab || "home");
  }
}

function showLogin(force = false) {
  if (!force && isWorkerShellAuthenticated()) {
    return;
  }
  clearWorkerSessionExpiryTimer();
  clearWorkerSessionCountdown();
  sessionExpiringSoonNotified = false;
  gateAutoOpenTriggered = false;
  stopAmbientLightRecommendation();
    stopDynamicQrRefresh();
  clearCardEntranceAnimation();  // Clear card animation when showing login
  if (elements.badgeCard) elements.badgeCard.classList.add("hidden");
  const dashboardEl = document.getElementById("workerDashboard");
  if (dashboardEl) dashboardEl.classList.add("hidden");
  if (elements.walletCard) elements.walletCard.classList.add("hidden");
  if (elements.loginCard) {
    elements.loginCard.classList.remove("hidden");
    elements.loginCard.style.removeProperty("display");
  }
  document.body.removeAttribute("data-company-mode");
  resetDailyInsights();
  setWorkerHubExpanded(false);
  document.body.classList.remove("worker-loaded");
  enforceUiVisibilityGuard();
  if (elements.workerQuickMenu) elements.workerQuickMenu.classList.add("hidden");
  applyWorkerPageView("");
  if (quickMenuObserver) {
    quickMenuObserver.disconnect();
    quickMenuObserver = null;
  }
  updateWalletImmersiveMode();
  updateWorkerPulsePanel();

  // Keep stored badge for GPS auto-login; only clear one-time tokens from the field.
  const storedBadgeId = normalizeBadgeIdInput(
    wpGet(WORKER_BADGE_LOGIN_KEY) || sessionStorage.getItem(PENDING_QR_BADGE_KEY) || "",
  );
  const currentValue = String(elements.workerAccessToken?.value || "").trim();
  if (elements.workerAccessToken) {
    let nextBadge = storedBadgeId;
    if (currentValue && looksLikeBadgeId(currentValue)) {
      nextBadge = normalizeBadgeIdInput(currentValue);
    } else if (currentValue && !looksLikeAccessToken(currentValue)) {
      nextBadge = normalizeBadgeIdInput(currentValue) || storedBadgeId;
    }
    if (nextBadge) {
      elements.workerAccessToken.value = nextBadge;
      wpSet(WORKER_BADGE_LOGIN_KEY, nextBadge);
    } else if (currentValue && looksLikeBadgeId(currentValue)) {
      elements.workerAccessToken.value = normalizeBadgeIdInput(currentValue);
      wpSet(WORKER_BADGE_LOGIN_KEY, normalizeBadgeIdInput(currentValue));
    } else if (looksLikeAccessToken(currentValue)) {
      elements.workerAccessToken.value = storedBadgeId || "";
    }
    if (!document.body.classList.contains("qr-fast-login")) {
      elements.workerAccessToken.readOnly = false;
      elements.workerAccessToken.removeAttribute("readonly");
      elements.workerAccessToken.removeAttribute("aria-readonly");
      elements.workerAccessToken.classList.remove("form-input-readonly");
    }
  }
  syncLoginPinFieldVisibility(elements.workerAccessToken?.value || storedBadgeId);
  if (document.body.classList.contains("qr-fast-login") || shouldTreatLoginAsQrLaunch()) {
    const badgeLabel = normalizeBadgeIdInput(elements.workerAccessToken?.value || storedBadgeId || "");
    const loginCopy = document.querySelector(".login-copy-sparkasse");
    if (loginCopy && badgeLabel) {
      loginCopy.textContent = `Badge ${badgeLabel} erkannt – nur noch PIN eingeben.`;
    }
  }
  const pinInput = document.querySelector("#workerBadgePin");
  if (pinInput && !storedBadgeId) {
    pinInput.value = "";
  }

  const resumeRow = elements.workerResumeLoginRow;
  if (resumeRow) {
    resumeRow.classList.add("hidden");
  }
  startProximityLoginWatcher();
}

function updateConnectionState() {
  if (!elements.connectionBanner) {
    return;
  }
  if (navigator.onLine) {
    elements.connectionBanner.textContent = "";
    elements.connectionBanner.className = "stb-connection-dot online";
    if (elements.connectionStatusLabel) {
      elements.connectionStatusLabel.textContent = t("online");
    }
  } else {
    elements.connectionBanner.textContent = "";
    elements.connectionBanner.className = "stb-connection-dot offline";
    if (elements.connectionStatusLabel) {
      elements.connectionStatusLabel.textContent = t("offline");
    }
  }
  updateWorkerPulsePanel();
  updateSmartWorkHub(lastWorkerPayload, lastTimesheetRows);
}

function showLoginError(message, { code = "", focusPin = false } = {}) {
  const text = String(message || "").trim();
  if (!text) {
    clearLoginError();
    return;
  }
  const loginCard = elements.loginCard || document.getElementById("loginCard");
  if (loginCard) {
    loginCard.classList.remove("hidden");
    loginCard.style.removeProperty("display");
  }
  const inlineError = document.getElementById("loginInlineError");
  if (inlineError) {
    inlineError.textContent = text;
    inlineError.classList.remove("hidden");
    inlineError.setAttribute("role", "alert");
  }
  if (elements.workerNotice) {
    elements.workerNotice.textContent = text;
    elements.workerNotice.classList.remove("hidden", "force-hidden");
    elements.workerNotice.classList.add("login-error-visible");
    elements.workerNotice.setAttribute("role", "alert");
    requestAnimationFrame(() => {
      elements.workerNotice.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }
  const tokenInput = elements.workerAccessToken;
  const pinInput = elements.workerBadgePin;
  if (tokenInput) {
    tokenInput.classList.toggle("input-error", code === "invalid_badge_id");
  }
  if (pinInput) {
    const pinError = code === "invalid_badge_pin" || focusPin || code === "missing_badge_pin";
    pinInput.classList.toggle("input-error", pinError);
    if (pinError) {
      syncLoginPinFieldVisibility();
      setTimeout(() => pinInput.focus(), 120);
    }
  }
}

function clearLoginError() {
  const inlineError = document.getElementById("loginInlineError");
  if (inlineError) {
    inlineError.textContent = "";
    inlineError.classList.add("hidden");
  }
  if (elements.workerNotice) {
    elements.workerNotice.classList.remove("login-error-visible");
  }
  elements.workerAccessToken?.classList.remove("input-error");
  elements.workerBadgePin?.classList.remove("input-error");
  hideWorkerNotice();
}

function showWorkerNotice(message) {
  if (!elements.workerNotice) {
    return;
  }
  elements.workerNotice.textContent = message;
  elements.workerNotice.classList.remove("hidden");
}

function hideWorkerNotice() {
  if (!elements.workerNotice) {
    return;
  }
  elements.workerNotice.textContent = "";
  elements.workerNotice.classList.add("hidden");
}

// ═════════════════════════════════════════════════════════════════════
// ── SESSION PROTECTION: Aggressive Inactivity Timeout ──
// Schützt gegen Telefon-Weitergabe durch autom. Logout nach 60s ohne Interaktion
// ═════════════════════════════════════════════════════════════════════

function initializeSessionInactivityProtection() {
  // Stoppe jeden existierenden Timer
  if (inactivityCheckInterval) {
    clearInterval(inactivityCheckInterval);
  }

  lastUserInteractionAt = Date.now();

  // Prüfe alle 5 Sekunden auf Inaktivität, damit Logout nah an 60s erfolgt
  inactivityCheckInterval = setInterval(() => {
    const timeSinceLastInteraction = Date.now() - lastUserInteractionAt;
    if (timeSinceLastInteraction > WORKER_INACTIVITY_TIMEOUT_MS) {
      console.warn("🔐 Session timeout: Zu lange inaktiv, Auto-Logout für Sicherheit");
      showWorkerNotice(t("inactiveReLogin"));
      workerLogout();
    }
  }, 5 * 1000);

  console.log("✓ Session protection: 60s Inaktivitäts-Monitor gestartet");
}

// ═════════════════════════════════════════════════════════════════════
// ── PASS LOCK: 2min Inaktivitäts-Sperre zum Schutz vor Diebstahl ──
// ═════════════════════════════════════════════════════════════════════

function initializePassLockProtection() {
  if (!pinLockEnabled) {
    console.log("⚠️  Pass-Lock deaktiviert (Admin-Setting)");
    return;
  }

  // Stoppe existierenden Timer
  if (passLockTimer) clearTimeout(passLockTimer);

  lastPassInteractionAt = Date.now();
  isPassLocked = false;
  hidePassLockOverlay();

  // Überwache Inaktivität auf Ausweis-Seite
  const checkPassLock = () => {
    if (!elements.badgeCard || elements.badgeCard.classList.contains("hidden")) {
      // Nicht auf Ausweis-Seite, timer neustarten
      if (passLockTimer) clearTimeout(passLockTimer);
      passLockTimer = setTimeout(checkPassLock, 30 * 1000);
      return;
    }

    const timeSinceLastInteraction = Date.now() - lastPassInteractionAt;
    if (timeSinceLastInteraction > WORKER_PASS_LOCK_TIMEOUT_MS && !isPassLocked) {
      console.log("🔒 Pass-Lock: 2min Inaktivität → Ausweis sperren");
      isPassLocked = true;
      showPassLockOverlay();
    }

    passLockTimer = setTimeout(checkPassLock, 30 * 1000);
  };

  passLockTimer = setTimeout(checkPassLock, 30 * 1000);
  console.log("✓ Pass-Lock: 2min Inaktivitäts-Sperre gestartet");
}

function markPassInteraction() {
  if (isPassLocked) return; // Keine Interaktion möglich wenn gesperrt
  lastPassInteractionAt = Date.now();
  if (isPassLocked) {
    isPassLocked = false;
    hidePassLockOverlay();
    // Timer neustarten
    if (passLockTimer) clearTimeout(passLockTimer);
    initializePassLockProtection();
  }
}

function showPassLockOverlay() {
  if (elements.pinLockOverlay) {
    elements.pinLockOverlay.classList.remove("hidden");
    if (elements.pinLockInput) {
      elements.pinLockInput.focus();
    }
  }
}

function hidePassLockOverlay() {
  if (elements.pinLockOverlay) {
    elements.pinLockOverlay.classList.add("hidden");
  }
  if (elements.pinLockError) {
    elements.pinLockError.classList.add("hidden");
  }
  if (elements.pinLockInput) {
    elements.pinLockInput.value = "";
  }
}

async function handlePassLockUnlock(pin) {
  if (!pin || !workerToken) {
    showPassLockError(t("pinLockTitle"));
    return;
  }

  try {
    // Verifizierung gegen Backend (oder lokal wenn PIN im Token gespeichert)
    const payload = await fetchJson(`${API_BASE}/verify-pin`, {
      method: "POST",
      headers: { Authorization: `Bearer ${workerToken}`, "Content-Type": "application/json" },
      body: JSON.stringify({ pin: normalizeBadgePinInput(pin) })
    });

    if (payload.valid) {
      isPassLocked = false;
      hidePassLockOverlay();
      lastPassInteractionAt = Date.now();
      // Timer neustarten
      if (passLockTimer) clearTimeout(passLockTimer);
      initializePassLockProtection();
      console.log("✓ Pass entsperrt");
    } else if (payload.error === "too_many_attempts") {
      showPassLockError(t("pinLockTooManyAttempts") || "Zu viele Versuche – bitte warte kurz.");
    } else {
      showPassLockError(t("wrongPinRetry"));
    }
  } catch (error) {
    // Fallback: Locally verify using sessionStorage (used when backend unreachable)
    const storedPin = (() => { try { return sessionStorage.getItem("_wpf") || ""; } catch (_) { return ""; } })();
    if (storedPin && storedPin === normalizeBadgePinInput(pin)) {
      isPassLocked = false;
      hidePassLockOverlay();
      lastPassInteractionAt = Date.now();
      if (passLockTimer) clearTimeout(passLockTimer);
      initializePassLockProtection();
      console.log("✓ Pass entsperrt (lokal)");
    } else {
      showPassLockError(t("wrongPinRetry"));
    }
  }
}

function showPassLockError(message) {
  if (elements.pinLockError) {
    elements.pinLockError.textContent = message;
    elements.pinLockError.classList.remove("hidden");
  }
}

let workerLogoutInFlight = false;

async function finalizeWorkerLogoutSession(tokenForRevoke, cfg) {
  if (!tokenForRevoke) {
    return;
  }
  if (cfg?.siteApp) {
    try {
      const locationPayload = await Promise.race([
        resolveSiteLocation({ preferFast: true, maxWaitMs: 3500 }),
        new Promise((resolve) => setTimeout(() => resolve(null), 3500)),
      ]);
      if (locationPayload) {
        await fetchJson(`${API_BASE}/site-leave`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${tokenForRevoke}`,
          },
          body: JSON.stringify({ location: locationPayload }),
        });
      }
    } catch {
      // best-effort; backend logout still records app-logout when needed
    }
  }
  fetchJson(`${API_BASE}/logout`, {
    method: "POST",
    headers: { Authorization: `Bearer ${tokenForRevoke}` },
  }).catch(() => {
    // ignore logout call failures
  });
}

async function workerLogout() {
  if (workerLogoutInFlight) {
    return;
  }
  workerLogoutInFlight = true;
  try {
    stopSiteGeofenceMonitor();
    stopDynamicQrRefresh();
    const tokenForRevoke = workerToken;
    const cfg = lastSiteAccessCfg;

    wpRemove(WORKER_TOKEN_KEY);
    wpRemove(WORKER_ACCESS_TOKEN_KEY);
    wpRemove(WORKER_CACHED_PAYLOAD_KEY);
    wpRemove(WORKER_OFFLINE_LOGIN_PROFILE_KEY);
    wpRemove(OFFLINE_EVENT_QUEUE_KEY);
    offlineWorkerSessionActive = false;
    workerToken = "";
    clearWorkerSessionExpiryTimer();
    if (inactivityCheckInterval) {
      clearInterval(inactivityCheckInterval);
      inactivityCheckInterval = null;
    }
    if (leaveRefreshInterval) {
      clearInterval(leaveRefreshInterval);
      leaveRefreshInterval = null;
    }
    closeGateMode();
    hidePassLockOverlay();
    isPassLocked = false;
    showLogin();
    startProximityLoginWatcher();

    void finalizeWorkerLogoutSession(tokenForRevoke, cfg);
  } finally {
    workerLogoutInFlight = false;
  }
}

async function openGateMode() {
  if (!elements.gateScannerOverlay) {
    return;
  }
  elements.gateScannerOverlay.classList.remove("hidden");
  setGateScannerFeedbackState("ready");
  haptic([14, 24, 14]);
  startGateEventFeedbackPolling();
  
  showBrightnessHintTemporarily();
  await requestWakeLock();
  await requestGateFullscreen();
  startAmbientLightRecommendation();
}

function closeGateMode() {
  if (gateFeedbackResetTimeout) {
    clearTimeout(gateFeedbackResetTimeout);
    gateFeedbackResetTimeout = null;
  }
  if (elements.gateScannerOverlay) {
    elements.gateScannerOverlay.classList.remove("is-ready", "is-refresh", "is-error");
    elements.gateScannerOverlay.classList.add("hidden");
  }
  if (elements.gateStatusFeedback) {
    elements.gateStatusFeedback.textContent = "";
  }
  stopGateEventFeedbackPolling();
  void exitGateFullscreen();
  stopAmbientLightRecommendation();
  releaseWakeLock();
}

function applyQrContrastState() {
  document.body.classList.toggle("qr-high-contrast", qrHighContrastEnabled);
  const label = qrHighContrastEnabled ? t("qrContrastOn") : t("qrContrastOff");
  if (elements.qrContrastToggle) {
    elements.qrContrastToggle.textContent = label;
  }
  if (elements.gateContrastToggle) {
    elements.gateContrastToggle.textContent = label;
  }
}

function toggleQrContrastMode() {
  qrHighContrastEnabled = !qrHighContrastEnabled;
  wpSet(QR_HIGH_CONTRAST_KEY, qrHighContrastEnabled ? "1" : "0");
  applyQrContrastState();
}

function applyAutoOpenScannerState() {
  if (elements.autoOpenScannerToggle) {
    elements.autoOpenScannerToggle.checked = autoOpenScannerEnabled;
  }
}

function showGateFeedback(message, color = "rgba(255, 255, 255, 0.78)") {
  if (!elements.gateStatusFeedback) {
    return;
  }
  elements.gateStatusFeedback.textContent = message;
  elements.gateStatusFeedback.style.color = color;
}

function setGateScannerFeedbackState(state, message = "") {
  if (!elements.gateScannerOverlay) {
    return;
  }
  elements.gateScannerOverlay.classList.remove("is-ready", "is-refresh", "is-error");
  if (state === "refresh") {
    elements.gateScannerOverlay.classList.add("is-refresh");
    showGateFeedback(message || t("gateQrRefreshed"), "#e8f6ff");
    return;
  }
  if (state === "error") {
    elements.gateScannerOverlay.classList.add("is-error");
    showGateFeedback(message || t("gateScanSyncDelayed"), "#ffd3d3");
    return;
  }
  elements.gateScannerOverlay.classList.add("is-ready");
  showGateFeedback(message || t("gateReadyScan"), "rgba(255, 255, 255, 0.7)");
}

function queueGateScannerReadyState(delayMs = 900) {
  if (gateFeedbackResetTimeout) {
    clearTimeout(gateFeedbackResetTimeout);
    gateFeedbackResetTimeout = null;
  }
  gateFeedbackResetTimeout = setTimeout(() => {
    setGateScannerFeedbackState("ready");
  }, Math.max(120, delayMs));
}

function stopGateEventFeedbackPolling() {
  if (gateEventPollTimeout) {
    clearTimeout(gateEventPollTimeout);
    gateEventPollTimeout = null;
  }
  gateEventPollInFlight = false;
  gateLastSeenEventId = "";
}

function scheduleGateEventFeedbackPolling(delayMs = 1200) {
  if (gateEventPollTimeout) {
    clearTimeout(gateEventPollTimeout);
    gateEventPollTimeout = null;
  }
  gateEventPollTimeout = setTimeout(() => {
    void pollLatestGateEvent();
  }, Math.max(500, delayMs));
}

function getGateEventFeedbackMessage(direction) {
  const normalized = String(direction || "").toLowerCase();
  if (normalized === "in") {
    return t("gateScanAccessGrantedIn");
  }
  if (normalized === "out") {
    return t("gateScanAccessGrantedOut");
  }
  return t("gateScanAccessGrantedGeneric");
}

function getGateDeniedFeedbackMessage(feedback) {
  const explicit = String(feedback?.message || "").trim();
  if (explicit) {
    return explicit;
  }
  return t("gateScanAccessDenied");
}

async function pollLatestGateEvent() {
  if (!workerToken || !elements.gateScannerOverlay || elements.gateScannerOverlay.classList.contains("hidden")) {
    stopGateEventFeedbackPolling();
    return;
  }
  if (gateEventPollInFlight) {
    scheduleGateEventFeedbackPolling(900);
    return;
  }

  gateEventPollInFlight = true;
  try {
    const payload = await fetchJson(`${API_BASE}/access-last`, {
      headers: { Authorization: `Bearer ${workerToken}` }
    });
    const feedback = payload?.gateFeedback || null;
    const feedbackId = String(feedback?.id || "").trim();
    const feedbackStatus = String(feedback?.status || "").trim().toLowerCase();
    const fallbackEventId = String(payload?.event?.id || "").trim();
    const currentId = feedbackId || fallbackEventId;
    if (currentId && gateLastSeenEventId && currentId !== gateLastSeenEventId) {
      if (feedbackStatus === "deny") {
        setGateScannerFeedbackState("error", getGateDeniedFeedbackMessage(feedback));
        queueGateScannerReadyState(2400);
        haptic([30, 40, 30]);
      } else {
        setGateScannerFeedbackState("refresh", getGateEventFeedbackMessage(feedback?.direction || payload?.event?.direction));
        queueGateScannerReadyState(1700);
        haptic([20, 28, 20]);
      }
    }
    if (currentId) {
      gateLastSeenEventId = currentId;
    }
  } catch {
    // Keep scanner usable even if backend ack polling is temporarily unavailable.
  } finally {
    gateEventPollInFlight = false;
    if (elements.gateScannerOverlay && !elements.gateScannerOverlay.classList.contains("hidden")) {
      scheduleGateEventFeedbackPolling(1200);
    }
  }
}

function startGateEventFeedbackPolling() {
  stopGateEventFeedbackPolling();
  void pollLatestGateEvent();
}

function startAmbientLightRecommendation() {
  ambientLowLightRecommended = false;
  if (typeof window.AmbientLightSensor !== "function") {
    return;
  }
  try {
    ambientLightSensorHandle = new window.AmbientLightSensor({ frequency: 0.5 });
    ambientLightSensorHandle.addEventListener("reading", () => {
      const lux = Number(ambientLightSensorHandle.illuminance || 0);
      if (lux > 0 && lux < 20 && !ambientLowLightRecommended) {
        ambientLowLightRecommended = true;
        showGateFeedback(t("lowLightDetected"), "#ffd5a3");
      }
    });
    ambientLightSensorHandle.addEventListener("error", () => {
      stopAmbientLightRecommendation();
    });
    ambientLightSensorHandle.start();
  } catch {
    stopAmbientLightRecommendation();
  }
}

function stopAmbientLightRecommendation() {
  ambientLowLightRecommended = false;
  if (!ambientLightSensorHandle) {
    return;
  }
  try {
    ambientLightSensorHandle.stop();
  } catch {
    // ignore sensor stop issues
  }
  ambientLightSensorHandle = null;
}

// ── Dynamic QR System ────────────────────────────────────────────────────────
function buildQrPayload(worker) {
  // Returns current DQR token if available, else falls back to static badge id.
  if (dqrCurrentToken) return dqrCurrentToken;
  const badge = String(worker?.badgeId || worker?.badge_id || "").trim();
  return badge || String(worker?.id || "").trim();
}

/** Vibrate the device (silent fail on unsupported devices) */
function haptic(pattern) {
  if (!hapticUnlocked) return;
  try { if (navigator.vibrate) navigator.vibrate(pattern); } catch {}
}

/** Update the QR countdown ring and text */
function _updateQrCountdownDisplay() {
  const el = document.getElementById("dqrCountdownRing");
  const textEl = document.getElementById("dqrCountdownText");
  if (!el && !textEl) return;
  const sec = Math.max(0, dqrRemainingSeconds);
  if (textEl) textEl.textContent = sec + "s";
  if (el) {
    const radius = 10;
    const circ = 2 * Math.PI * radius;
    const total = Math.max(20, Number(dqrWindowSeconds) || 60);
    const fraction = Math.min(1, Math.max(0, sec / total));
    el.style.strokeDashoffset = String(circ * (1 - fraction));
  }
  // Sync countdown to dashboard
  syncDashboardQrCountdown();
}

function scheduleNextDynamicQrRefresh() {
  if (dqrRefreshTimeout) {
    clearTimeout(dqrRefreshTimeout);
    dqrRefreshTimeout = null;
  }
  const remaining = Math.max(8, Number(dqrRemainingSeconds) || 60);
  const nextInMs = Math.max(8_000, (remaining - 3) * 1000);
  dqrRefreshTimeout = setTimeout(() => {
    void fetchAndDisplayDynamicQr();
  }, nextInMs);
}

/** Fetch one dynamic QR token from the backend and update the QR image */
async function fetchAndDisplayDynamicQr() {
  if (!workerToken) return;
  try {
    const data = await fetchJson(`${API_BASE}/dynamic-qr`, {
      headers: { Authorization: `Bearer ${workerToken}` }
    });
    if (data?.qrToken) {
      dqrCurrentToken = data.qrToken;
      dqrRemainingSeconds = data.remainingSec ?? 60;
      dqrWindowSeconds = data.windowSec ?? Math.max(20, dqrRemainingSeconds || 60);
      // Re-render QR image
      const isCompact = window.matchMedia("(max-width: 520px)").matches;
      const sz = isCompact ? 520 : 460;
      if (elements.workerQr) {
        elements.workerQr.classList.remove("hidden");
        void setQrImage(elements.workerQr, dqrCurrentToken, sz);
        // Animate a quick flash on refresh
        elements.workerQr.style.opacity = "0.4";
        requestAnimationFrame(() => {
          elements.workerQr.style.transition = "opacity 0.35s ease";
          elements.workerQr.style.opacity = "1";
        });
      }
      // Also update gate QR if open
      if (elements.gateQr && !elements.gateQr.classList.contains("hidden")) {
        const gSz = isCompact ? 520 : 420;
        void setQrImage(elements.gateQr, dqrCurrentToken, gSz);
        setGateScannerFeedbackState("refresh", t("gateQrRefreshed"));
        queueGateScannerReadyState(1000);
      }
      // Also update dashboard QR if visible
      const dashboardQr = document.getElementById("dashboardQr");
      if (dashboardQr && !dashboardQr.classList.contains("hidden")) {
        const dSz = isCompact ? 320 : 280;
        void setQrImage(dashboardQr, dqrCurrentToken, dSz);
        dashboardQr.style.opacity = "0.4";
        requestAnimationFrame(() => {
          dashboardQr.style.transition = "opacity 0.35s ease";
          dashboardQr.style.opacity = "1";
        });
      }
      // Update fallback text
      if (elements.qrFallbackText) elements.qrFallbackText.textContent = `Code: ${data.badgeId}`;
      haptic(30); // subtle pulse on QR refresh
      _updateQrCountdownDisplay();
      scheduleNextDynamicQrRefresh();
    }
  } catch (error) {
    if (
      error?.code === "handover_signature_missing"
      || error?.payload?.lockReasonCode === "missing_handover_signature"
      || error?.code === "worker_documents_missing"
      || error?.code === "worker_documents_expired"
    ) {
      stopDynamicQrRefresh();
      if (elements.workerQr) {
        elements.workerQr.removeAttribute("src");
        elements.workerQr.classList.add("hidden");
      }
      if (elements.qrFallbackText) {
        elements.qrFallbackText.textContent = error.message || t("noQrAvailable");
        elements.qrFallbackText.classList.remove("hidden");
      }
      showWorkerNotice(error.message || t("noQrAvailable"));
      return;
    }
    // offline or expired session — keep showing last token
    if (elements.gateScannerOverlay && !elements.gateScannerOverlay.classList.contains("hidden")) {
      setGateScannerFeedbackState("error", t("gateScanSyncDelayed"));
      queueGateScannerReadyState(2200);
      haptic([16, 34, 16]);
    }
    scheduleNextDynamicQrRefresh();
  }
}

/** Start polling for fresh dynamic QR tokens */
function startDynamicQrRefresh() {
  stopDynamicQrRefresh();
  // Fetch immediately
  void fetchAndDisplayDynamicQr();
  // Countdown every second
  dqrCountdownInterval = setInterval(() => {
    dqrRemainingSeconds = Math.max(0, dqrRemainingSeconds - 1);
    _updateQrCountdownDisplay();
  }, 1000);
}

/** Stop dynamic QR polling (e.g. on logout or when card is hidden) */
function stopDynamicQrRefresh() {
  if (dqrRefreshTimeout) { clearTimeout(dqrRefreshTimeout); dqrRefreshTimeout = null; }
  if (dqrCountdownInterval) { clearInterval(dqrCountdownInterval); dqrCountdownInterval = null; }
  dqrCurrentToken = "";
  dqrRemainingSeconds = 60;
  dqrWindowSeconds = 60;
}

function normalizeBadgeIdInput(value) {
  return String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]/g, "-")
    .replace(/\s+/g, "");
}

function normalizeBadgePinInput(value) {
  return String(value || "").replace(/\s+/g, "").trim();
}

function looksLikeAccessToken(value) {
  const raw = String(value || "").trim();
  if (!raw || raw.length < 24) {
    return false;
  }
  if (looksLikeBadgeId(raw)) {
    return false;
  }
  return /^[A-Za-z0-9_-]+$/.test(raw);
}

function syncLoginPinFieldVisibility(credential = "") {
  const pinWrapper = document.querySelector("#pinFieldWrapper");
  if (!pinWrapper) {
    return;
  }
  // PIN-Feld auf dem Handy immer sichtbar lassen — Badge-Login braucht PIN.
  pinWrapper.classList.remove("hidden");
  const val = normalizeBadgeIdInput(credential || elements.workerAccessToken?.value || "");
  if (val && !looksLikeBadgeId(val) && looksLikeAccessToken(val) && elements.workerBadgePin) {
    elements.workerBadgePin.value = "";
  }
}

function buildLoginShellPayload(payload) {
  return {
    worker: payload?.worker || {},
    sessionExpiresAt: payload?.sessionExpiresAt || "",
    cardType: payload?.cardType || "",
    company: payload?.company || {},
    subcompany: payload?.subcompany || {},
    settings: payload?.settings || {},
    leaveStats: payload?.leaveStats || null,
    planFeatures: payload?.planFeatures || null,
    siteAccess: payload?.siteAccess || null,
  };
}

async function completeWorkerLogin(payload, extras = {}) {
  const shell = buildLoginShellPayload(payload);
  persistLoginBootstrapPayload(payload);
  wpSet(WORKER_CACHED_PAYLOAD_KEY, JSON.stringify(shell));
  offlineWorkerSessionActive = false;
  clearQrBootstrapUiState();
  replaceWorkerHistoryAfterLogin();
  renderWorker(shell);
  markWorkerLoginCompleted();
  markWorkerSyncedNow();
  updateConnectionState();
  finishWorkerLoginUi();
  if (extras.autoCheckInLogId) {
    showWorkerNotice(t("siteAutoCheckIn"));
  } else if (extras.siteLoginLogId) {
    showWorkerNotice(t("siteGpsRegistered"));
  }
  if (!isStandaloneMode() && elements.installButton) {
    elements.installButton.hidden = false;
    if (extras.showInstallTip) {
      showWorkerNotice(t("installTip"));
    }
  }
  initializeSessionInactivityProtection();
  if (window.__deferredWorkerSwRegistration) {
    window.__deferredWorkerSwRegistration = false;
    registerWorkerSw();
  }
  void ensureWorkerPushNotifications({ promptIfNeeded: true });
  void loadWorkerData();
  void syncOfflinePhotoQueue();
  void syncOfflineEventQueue();
}

function getLoginBadgeCredential() {
  const fromInput = normalizeBadgeIdInput(elements.workerAccessToken?.value || "");
  if (fromInput && looksLikeBadgeId(fromInput)) {
    return fromInput;
  }
  const fromHidden = normalizeBadgeIdInput(document.getElementById("workerQrBadgeSeed")?.value || "");
  if (fromHidden) {
    return fromHidden;
  }
  const fromForm = normalizeBadgeIdInput(elements.workerLoginForm?.dataset?.qrBadge || "");
  if (fromForm) {
    return fromForm;
  }
  return readBootstrapBadgeId(new URLSearchParams(window.location.search));
}

async function fetchJoinPreview(accessToken) {
  const token = String(accessToken || "").trim();
  if (!token) {
    return null;
  }
  return fetchJson(`${API_BASE}/join-preview?access=${encodeURIComponent(token)}`, {
    method: "GET",
    cache: "no-store",
  });
}

async function executeQrPinLogin(badgeId, pin, { qrLaunch = true, silent = false } = {}) {
  const normalizedBadge = normalizeBadgeIdInput(badgeId || getLoginBadgeCredential());
  const normalizedPin = normalizeBadgePinInput(pin);
  if (!normalizedBadge) {
    if (!silent) {
      showLoginError(t("enterBadgeId"), { code: "invalid_badge_id" });
    }
    return false;
  }
  if (!normalizedPin || normalizedPin.length < 4) {
    if (!silent) {
      showLoginError(t("enterPin"), { focusPin: true });
    }
    return false;
  }
  prefillWorkerBadgeField(normalizedBadge, { readOnly: true });
  const submitBtn = elements.workerLoginForm?.querySelector('button[type="submit"]');
  const submitLabel = submitBtn?.textContent || "";
  if (submitBtn && !silent) {
    submitBtn.disabled = true;
    submitBtn.textContent = t("loginProgress");
  }
  try {
    await loginWithBadgeId(normalizedBadge, normalizedPin, {
      locationPayload: null,
      qrLaunch,
      silent,
    });
    if (!workerToken) {
      if (!silent) {
        showLoginError(t("loginFailed") + " (Sitzung konnte nicht gespeichert werden – bitte erneut versuchen.)", {
          focusPin: true,
        });
      }
      return false;
    }
    return true;
  } finally {
    if (submitBtn && !silent) {
      submitBtn.disabled = false;
      submitBtn.textContent = submitLabel || t("loginBtn");
    }
  }
}

function persistLoginBootstrapPayload(payload) {
  if (!payload || !payload.token) {
    return;
  }
  const worker = payload.worker || {};
  const badgeId = String(worker.badgeId || worker.badge_id || "").trim();
  if (badgeId) {
    wpSet(WORKER_BADGE_LOGIN_KEY, normalizeBadgeIdInput(badgeId));
  }
  if (!worker.id && !badgeId) {
    return;
  }
  const existing = readStoredJson(WORKER_CACHED_PAYLOAD_KEY, null) || {};
  wpSet(WORKER_CACHED_PAYLOAD_KEY, JSON.stringify({
    worker,
    sessionExpiresAt: payload.sessionExpiresAt || "",
    cardType: payload.cardType || "",
    company: payload.company || {},
    subcompany: payload.subcompany || {},
    settings: payload.settings || {},
    leaveStats: payload.leaveStats || null,
    planFeatures: payload.planFeatures || existing.planFeatures || null,
    siteAccess: payload.siteAccess || existing.siteAccess || null,
  }));
}

function showBadgePinLoginMode(badgeId = "", { message = "", focusPin = false } = {}) {
  document.body.classList.remove("qr-fast-login");
  const normalized = normalizeBadgeIdInput(
    badgeId || wpGet(WORKER_BADGE_LOGIN_KEY) || elements.workerAccessToken?.value || "",
  );
  if (elements.workerAccessToken) {
    if (normalized && looksLikeBadgeId(normalized)) {
      elements.workerAccessToken.value = normalized;
    } else if (looksLikeAccessToken(elements.workerAccessToken.value)) {
      elements.workerAccessToken.value = normalized || "";
    }
  }
  syncLoginPinFieldVisibility(normalized);
  if (message) {
    showLoginError(message, { focusPin: focusPin || Boolean(normalized) });
  }
  const pinInput = elements.workerBadgePin || document.querySelector("#workerBadgePin");
  if (pinInput && normalized && !isVisitorBadgeId(normalized) && (focusPin || message)) {
    setTimeout(() => pinInput.focus(), 120);
  }
}

function isQrLaunchLogin(params = null) {
  try {
    const search = params || new URLSearchParams(window.location.search);
    return search.get("launch") === "1" || search.get("fast") === "1";
  } catch {
    return false;
  }
}

function getQrLaunchBadgeId(params = null) {
  try {
    const search = params || new URLSearchParams(window.location.search);
    return normalizeBadgeIdInput(search.get("badge") || "");
  } catch {
    return "";
  }
}

function prefillWorkerBadgeField(badgeId, { readOnly = false, focusPin = false } = {}) {
  const normalized = normalizeBadgeIdInput(badgeId || "");
  if (!normalized) {
    return "";
  }
  wpSet(WORKER_BADGE_LOGIN_KEY, normalized);
  try {
    sessionStorage.setItem(PENDING_QR_BADGE_KEY, normalized);
  } catch {
    // ignore sessionStorage failures
  }
  const badgeInput = elements.workerAccessToken || document.querySelector("#workerAccessToken");
  if (badgeInput) {
    badgeInput.value = normalized;
    badgeInput.readOnly = Boolean(readOnly);
    badgeInput.toggleAttribute("readonly", Boolean(readOnly));
    badgeInput.classList.toggle("form-input-readonly", Boolean(readOnly));
    if (readOnly) {
      badgeInput.setAttribute("aria-readonly", "true");
    } else {
      badgeInput.removeAttribute("aria-readonly");
    }
  }
  const seedInput = document.getElementById("workerQrBadgeSeed");
  if (seedInput) {
    seedInput.value = normalized;
  }
  if (elements.workerLoginForm) {
    elements.workerLoginForm.dataset.qrBadge = normalized;
  }
  syncLoginPinFieldVisibility(normalized);
  const loginCard = elements.loginCard || document.getElementById("loginCard");
  if (loginCard) {
    loginCard.classList.remove("hidden");
    loginCard.style.removeProperty("display");
  }
  const pinInput = elements.workerBadgePin || document.querySelector("#workerBadgePin");
  if (pinInput && focusPin) {
    setTimeout(() => pinInput.focus(), 120);
  }
  return normalized;
}

async function resolveBadgeIdFromAccessToken(accessToken) {
  const token = String(accessToken || "").trim();
  if (!token) {
    return "";
  }
  const stored = normalizeBadgeIdInput(wpGet(WORKER_BADGE_LOGIN_KEY) || "");
  if (stored) {
    return stored;
  }
  try {
    const payload = await fetchJoinPreview(token);
    const badgeId = normalizeBadgeIdInput(payload?.badgeId || payload?.badge_id || "");
    if (badgeId) {
      wpSet(WORKER_BADGE_LOGIN_KEY, badgeId);
    }
    return badgeId;
  } catch {
    return "";
  }
}

function prepareQrPinOnlyLogin(badgeId, { tryAutoLogin = false, readOnly = true, focusPin = true } = {}) {
  if (isWorkerShellAuthenticated()) {
    return true;
  }
  const normalized = prefillWorkerBadgeField(badgeId, { readOnly, focusPin });
  if (!normalized || isVisitorBadgeId(normalized)) {
    return false;
  }
  document.body.classList.add("qr-fast-login");
  const loginCopy = document.querySelector(".login-copy-sparkasse");
  if (loginCopy) {
    loginCopy.textContent = tf("loginCopyQrFast", { badge: normalized });
  }
  setupQrPinAutoSubmit(normalized);
  if (tryAutoLogin) {
    void tryFastBadgeLoginFromQr(normalized, { qrLaunch: true });
  }
  return true;
}

async function tryFastBadgeLoginFromQr(badgeId, { qrLaunch = true } = {}) {
  if (!badgeId || isVisitorBadgeId(badgeId)) {
    return false;
  }
  let storedPin = "";
  try {
    storedPin = sessionStorage.getItem("_wpf") || "";
  } catch {
    storedPin = "";
  }
  if (storedPin.length < 4) {
    return false;
  }
  return executeQrPinLogin(badgeId, storedPin, { qrLaunch, silent: true });
}

function setupQrPinAutoSubmit(badgeId) {
  const pinInput = elements.workerBadgePin || document.querySelector("#workerBadgePin");
  if (!pinInput || isVisitorBadgeId(badgeId)) {
    return;
  }
  if (isIosDevice()) {
    return;
  }
  if (pinInput.dataset.qrAutoBound === "1") {
    return;
  }
  pinInput.dataset.qrAutoBound = "1";
  pinInput.addEventListener("input", async () => {
    if (workerToken) {
      return;
    }
    const pin = normalizeBadgePinInput(pinInput.value);
    if (pin.length < 4) {
      return;
    }
    if (pinInput.dataset.qrAutoSubmitting === "1") {
      return;
    }
    pinInput.dataset.qrAutoSubmitting = "1";
    try {
      await executeQrPinLogin(badgeId || getLoginBadgeCredential(), pin, { qrLaunch: true, silent: false });
    } finally {
      pinInput.dataset.qrAutoSubmitting = "0";
    }
  });
}

function looksLikeBadgeId(value) {
  const normalized = normalizeBadgeIdInput(value);
  if (!normalized || normalized.length < 4 || normalized.length > 32) {
    return false;
  }
  if (!/^[A-Z0-9-]+$/.test(normalized)) {
    return false;
  }
  if (/^(BP|VS|WRK)/.test(normalized)) {
    return true;
  }
  return normalized.includes("-");
}

function isVisitorBadgeId(value) {
  return normalizeBadgeIdInput(value).startsWith("VS-") || normalizeBadgeIdInput(value).startsWith("VS");
}

function updateSiteMapLink(site) {
  if (!elements.workerSite) {
    return;
  }

  const normalizedSite = String(site || "").trim();
  if (!normalizedSite) {
    elements.workerSite.textContent = "-";
    elements.workerSite.setAttribute("href", "#");
    elements.workerSite.setAttribute("aria-disabled", "true");
    const homeInfoSite = document.getElementById("homeInfoSite");
    if (homeInfoSite) {
      homeInfoSite.textContent = "-";
      homeInfoSite.setAttribute("href", "#");
      homeInfoSite.setAttribute("aria-disabled", "true");
    }
    return;
  }

  const mapsUrl = new URL("https://www.google.com/maps/search/");
  mapsUrl.searchParams.set("api", "1");
  mapsUrl.searchParams.set("query", normalizedSite);
  elements.workerSite.textContent = normalizedSite;
  elements.workerSite.href = mapsUrl.toString();
  elements.workerSite.removeAttribute("aria-disabled");
  const homeInfoSite = document.getElementById("homeInfoSite");
  if (homeInfoSite) {
    homeInfoSite.textContent = normalizedSite;
    homeInfoSite.href = mapsUrl.toString();
    homeInfoSite.removeAttribute("aria-disabled");
  }
}

function resolveApiRoot(workerApiBase) {
  return String(workerApiBase || "").replace(/\/api\/worker-app\/?$/, "");
}

function apiPath(path) {
  const clean = String(path || "").replace(/^\//, "");
  const root = String(API_ROOT || "").replace(/\/$/, "");
  return clean.startsWith("api/") ? `${root}/${clean}` : `${root}/api/${clean}`;
}

function buildQrImageUrl(payload, size = 280) {
  const text = String(payload || "").trim();
  if (!text) {
    return "";
  }

  if (/^https?:\/\//i.test(API_ROOT)) {
    const url = new URL("/api/qr.png", API_ROOT);
    url.searchParams.set("data", text);
    url.searchParams.set("size", String(size));
    return url.toString();
  }

  const url = new URL("/api/qr.png", window.location.origin);
  url.searchParams.set("data", text);
  url.searchParams.set("size", String(size));
  return `${url.pathname}${url.search}`;
}

function getQrCacheKey(payload, size) {
  return `${QR_CACHE_PREFIX}:${size}:${payload}`;
}

function getCachedQr(payload, size) {
  const key = getQrCacheKey(payload, size);
  return wpGet(key) || "";
}

function setCachedQr(payload, size, dataUrl) {
  if (!dataUrl || !dataUrl.startsWith("data:image/png")) {
    return;
  }
  const key = getQrCacheKey(payload, size);
  wpSet(key, dataUrl);
}

async function fetchQrAsDataUrl(payload, size) {
  const url = buildQrImageUrl(payload, size);
  if (!url) {
    return "";
  }
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`qr_fetch_failed_${response.status}`);
  }
  const blob = await response.blob();
  return await blobToDataUrl(blob);
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => reject(new Error("blob_to_dataurl_failed"));
    reader.readAsDataURL(blob);
  });
}

async function setQrImage(imgElement, payload, size) {
  if (!imgElement || !payload) {
    return;
  }

  const cached = getCachedQr(payload, size);
  if (cached) {
    imgElement.src = cached;
  } else {
    const directUrl = buildQrImageUrl(payload, size);
    if (directUrl) {
      imgElement.src = directUrl;
    }
  }

  try {
    const freshDataUrl = await fetchQrAsDataUrl(payload, size);
    if (freshDataUrl) {
      setCachedQr(payload, size, freshDataUrl);
      imgElement.src = freshDataUrl;
    }
  } catch {
    if (!cached) {
      imgElement.alt = t("qrLoadFailedAlt");
    }
  }
}

function showBrightnessHintTemporarily() {
  if (!elements.gateBrightnessHint) {
    return;
  }
  elements.gateBrightnessHint.classList.remove("hidden");
  window.setTimeout(() => {
    if (elements.gateBrightnessHint) {
      elements.gateBrightnessHint.classList.add("hidden");
    }
  }, 6000);
}

async function requestGateFullscreen() {
  const panel = elements.gateScannerOverlay;
  if (!panel || document.fullscreenElement) {
    return;
  }
  const requestFullscreen = panel.requestFullscreen || panel.webkitRequestFullscreen;
  if (typeof requestFullscreen !== "function") {
    return;
  }
  try {
    await requestFullscreen.call(panel);
  } catch {
    // ignore fullscreen failures
  }
}

async function exitGateFullscreen() {
  const exitFullscreen = document.exitFullscreen || document.webkitExitFullscreen;
  if (typeof exitFullscreen !== "function" || !document.fullscreenElement) {
    return;
  }
  try {
    await exitFullscreen.call(document);
  } catch {
    // ignore fullscreen exit failures
  }
}

function isIosDevice() {
  const ua = navigator.userAgent || "";
  const platform = navigator.platform || "";
  const touchMac = platform === "MacIntel" && navigator.maxTouchPoints > 1;
  return /iPhone|iPad|iPod/i.test(ua) || touchMac;
}

function isAndroidDevice() {
  return /Android/i.test(navigator.userAgent || "");
}

  function isAndroidChrome() {
    const ua = navigator.userAgent || "";
    const isChrome = /Chrome\//i.test(ua) && !/EdgA\//i.test(ua) && !/OPR\//i.test(ua) && !/SamsungBrowser\//i.test(ua);
    return isAndroidDevice() && isChrome;
  }

function updatePlatformInstallHint() {
  if (!elements.installPlatformHint) {
    return;
  }

  if (isStandaloneMode()) {
    elements.installPlatformHint.textContent = t("installHintStandalone");
    return;
  }

  if (isIosDevice()) {
    elements.installPlatformHint.textContent = t("installHintIos");
    return;
  }

  if (isAndroidDevice()) {
      if (isAndroidChrome()) {
        elements.installPlatformHint.textContent = t("installHintAndroidChrome");
      } else {
        elements.installPlatformHint.textContent = t("installHintAndroidOther");
      }
    return;
  }

  elements.installPlatformHint.textContent = t("installHint");
}

async function requestWakeLock() {
  if (!navigator.wakeLock || wakeLockHandle) {
    return;
  }
  try {
    wakeLockHandle = await navigator.wakeLock.request("screen");
    wakeLockHandle.addEventListener("release", () => {
      wakeLockHandle = null;
    });
  } catch {
    wakeLockHandle = null;
  }
}

function releaseWakeLock() {
  if (!wakeLockHandle) {
    return;
  }
  wakeLockHandle.release().catch(() => {
    // ignore release failures
  });
  wakeLockHandle = null;
}

async function openCameraOverlay() {
  if (!elements.cameraOverlay || !elements.cameraVideo) {
    return;
  }

  const legacyGetUserMedia = navigator.getUserMedia || navigator.webkitGetUserMedia || navigator.mozGetUserMedia || navigator.msGetUserMedia;
  const requestUserMedia = async (constraints) => {
    if (navigator.mediaDevices?.getUserMedia) {
      return navigator.mediaDevices.getUserMedia(constraints);
    }
    if (legacyGetUserMedia) {
      return new Promise((resolve, reject) => {
        legacyGetUserMedia.call(navigator, constraints, resolve, reject);
      });
    }
    throw new Error("getUserMedia_not_supported");
  };
  const describeCameraError = (error) => {
    const name = String(error?.name || "").trim();
    const message = String(error?.message || "").trim();
    return [name, message].filter(Boolean).join(": ") || "unknown error";
  };
  const cameraDiagCodeForError = (error) => {
    const errorName = String(error?.name || "").trim();
    if (!window.isSecureContext) {
      return "CAM-HTTPS";
    }
    if (errorName === "NotAllowedError" || errorName === "SecurityError") {
      return "CAM-PERM";
    }
    if (errorName === "NotFoundError" || errorName === "DevicesNotFoundError") {
      return "CAM-NODEVICE";
    }
    if (errorName === "NotReadableError" || errorName === "TrackStartError") {
      return "CAM-INUSE";
    }
    if (errorName === "OverconstrainedError" || errorName === "ConstraintNotSatisfiedError") {
      return "CAM-CONSTRAINT";
    }
    if (errorName === "" && error?.message === "getUserMedia_not_supported") {
      return "CAM-API";
    }
    return "CAM-START";
  };
  const withCameraDiagCode = (message, code) => `${message} [${code}]`;

  if (!navigator.mediaDevices?.getUserMedia && !legacyGetUserMedia) {
    showWorkerNotice(withCameraDiagCode(t("cameraBlocked"), "CAM-API"));
    elements.photoInput?.click();
    return;
  }

  if (elements.photoPreviewWrap) elements.photoPreviewWrap.style.display = "none";
  if (elements.cameraCanvas) elements.cameraCanvas.style.display = "none";
  elements.cameraVideo.style.display = "block";
  if (elements.takePhotoButton) elements.takePhotoButton.style.display = "inline-block";
  if (elements.confirmPhotoButton) elements.confirmPhotoButton.style.display = "none";
  if (elements.retakePhotoButton) elements.retakePhotoButton.style.display = "none";

  elements.cameraOverlay.style.display = "flex";
  lastCameraPhotoDataUrl = null;
  lastCameraPhotoRotation = 0;

  const videoConstraintCandidates = [
    {
      facingMode: { ideal: "environment" },
      width: { ideal: 1280 },
      height: { ideal: 720 }
    },
    {
      facingMode: "environment"
    },
    {
      facingMode: { ideal: "user" },
      width: { ideal: 1280 },
      height: { ideal: 720 }
    },
    {
      facingMode: "user"
    },
    {
      width: { ideal: 1280 },
      height: { ideal: 720 }
    },
    {},
    true
  ];

  try {
    stopCameraStream();
    let stream = null;
    let lastError = null;

    for (const videoConstraint of videoConstraintCandidates) {
      try {
        stream = await requestUserMedia({
          video: videoConstraint,
          audio: false
        });
        if (stream) {
          break;
        }
      } catch (error) {
        lastError = error;
        // try next fallback constraint
      }
    }

    if (!stream && navigator.mediaDevices?.enumerateDevices) {
      const devices = await navigator.mediaDevices.enumerateDevices().catch(() => []);
      const videoInputs = devices.filter((device) => device.kind === "videoinput");
      for (const device of videoInputs) {
        try {
          stream = await requestUserMedia({
            video: { deviceId: { exact: device.deviceId } },
            audio: false
          });
          if (stream) {
            break;
          }
        } catch (error) {
          lastError = error;
        }
      }
    }

    if (!stream) {
      throw lastError || new Error("camera_unavailable");
    }

    cameraStream = stream;
    elements.cameraVideo.srcObject = stream;
    elements.cameraVideo.muted = true;
    elements.cameraVideo.autoplay = true;
    elements.cameraVideo.setAttribute("playsinline", "true");
    elements.cameraVideo.setAttribute("webkit-playsinline", "true");
    elements.cameraVideo.playsInline = true;
    await new Promise((resolve) => {
      const finalize = () => resolve();
      elements.cameraVideo.onloadedmetadata = finalize;
      window.setTimeout(finalize, 1200);
    });
    try {
      await elements.cameraVideo.play();
    } catch {
      // Keep stream active even if playback promise is blocked.
    }
  } catch (error) {
    const reason = describeCameraError(error);
    const diagCode = cameraDiagCodeForError(error);
    showWorkerNotice(
      window.isSecureContext
        ? withCameraDiagCode(`${t("cameraStartFailed")} (${reason})`, diagCode)
        : withCameraDiagCode(t("cameraHttpsHint"), "CAM-HTTPS")
    );
    closeCameraOverlay();
    elements.photoInput?.click();
  }
}

function stopCameraStream() {
  if (!cameraStream) {
    return;
  }
  cameraStream.getTracks().forEach((track) => track.stop());
  cameraStream = null;
}

function closeCameraOverlay() {
  if (elements.cameraOverlay) {
    elements.cameraOverlay.style.display = "none";
  }
  stopCameraStream();
  lastCameraPhotoDataUrl = null;
  lastCameraPhotoRotation = 0;
}

function takePhotoFromCamera() {
  if (!elements.cameraVideo || !elements.cameraCanvas) {
    return;
  }

  const video = elements.cameraVideo;
  if (!video.videoWidth || !video.videoHeight) {
    showWorkerNotice(t("cameraWaitReady"));
    return;
  }

  const canvas = elements.cameraCanvas;
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return;
  }

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  lastCameraPhotoDataUrl = canvas.toDataURL("image/jpeg", 0.92);

  canvas.style.display = "block";
  video.style.display = "none";
  if (elements.photoPreviewWrap) elements.photoPreviewWrap.style.display = "flex";
  if (elements.takePhotoButton) elements.takePhotoButton.style.display = "none";
  if (elements.confirmPhotoButton) elements.confirmPhotoButton.style.display = "inline-block";
  if (elements.retakePhotoButton) elements.retakePhotoButton.style.display = "inline-block";
}

function retakeCameraPhoto() {
  if (!elements.cameraVideo || !elements.cameraCanvas) {
    return;
  }
  elements.cameraCanvas.style.display = "none";
  elements.cameraVideo.style.display = "block";
  if (elements.photoPreviewWrap) elements.photoPreviewWrap.style.display = "none";
  if (elements.takePhotoButton) elements.takePhotoButton.style.display = "inline-block";
  if (elements.confirmPhotoButton) elements.confirmPhotoButton.style.display = "none";
  if (elements.retakePhotoButton) elements.retakePhotoButton.style.display = "none";
  lastCameraPhotoDataUrl = null;
  lastCameraPhotoRotation = 0;
}

function rotateCameraPhoto() {
  if (!elements.cameraCanvas || !lastCameraPhotoDataUrl) {
    return;
  }
  lastCameraPhotoRotation = (lastCameraPhotoRotation + 90) % 360;

  const img = new window.Image();
  img.onload = () => {
    const canvas = elements.cameraCanvas;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }

    if (lastCameraPhotoRotation % 180 === 0) {
      canvas.width = img.width;
      canvas.height = img.height;
    } else {
      canvas.width = img.height;
      canvas.height = img.width;
    }

    ctx.save();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.translate(canvas.width / 2, canvas.height / 2);
    ctx.rotate((lastCameraPhotoRotation * Math.PI) / 180);
    ctx.drawImage(img, -img.width / 2, -img.height / 2);
    ctx.restore();

    lastCameraPhotoDataUrl = canvas.toDataURL("image/jpeg", 0.92);
  };
  img.src = lastCameraPhotoDataUrl;
}

function deleteCameraPhoto() {
  retakeCameraPhoto();
}

function confirmCameraPhoto() {
  if (!lastCameraPhotoDataUrl) {
    return;
  }

  closeCameraOverlay();

  if (elements.workerPhoto) {
    elements.workerPhoto.src = lastCameraPhotoDataUrl;
  }
  wpSet(LOCAL_LAST_PHOTO_KEY, lastCameraPhotoDataUrl);

  uploadPhotoToBackend(lastCameraPhotoDataUrl).catch(() => {
    savePhotoToOfflineQueue(lastCameraPhotoDataUrl);
    showWorkerNotice(t("photoOfflineQueued"));
  });
}

function handlePhotoSelected(event) {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }

  if (event.target) {
    event.target.value = "";
  }

  const reader = new FileReader();
  reader.onload = (loadEvent) => {
    const dataUrl = typeof loadEvent.target?.result === "string" ? loadEvent.target.result : "";
    if (!dataUrl) {
      return;
    }

    if (elements.workerPhoto) {
      elements.workerPhoto.src = dataUrl;
    }
    wpSet(LOCAL_LAST_PHOTO_KEY, dataUrl);

    uploadPhotoToBackend(dataUrl).catch(() => {
      savePhotoToOfflineQueue(dataUrl);
      showWorkerNotice(t("photoOfflineQueued"));
    });
  };
  reader.readAsDataURL(file);
}

async function uploadPhotoToBackend(dataUrl) {
  if (!workerToken) {
    throw new Error("missing_worker_token");
  }

  await fetchJson(`${API_BASE}/photo`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${workerToken}`
    },
    body: JSON.stringify({ photoData: dataUrl })
  });

  await loadWorkerData();
}

function isWorkerSessionAuthError(code) {
  return code === "worker_session_expired" || code === "invalid_worker_session";
}

function isWorkerProtectedApiUrl(url) {
  const value = String(url || "");
  return value.includes("/api/worker-app") || (API_BASE && value.startsWith(API_BASE));
}

function stopSiteGeofenceMonitor() {
  if (siteGeofenceWatchTimer) {
    clearInterval(siteGeofenceWatchTimer);
    siteGeofenceWatchTimer = null;
  }
  siteOffSiteStrikeCount = 0;
}

function getCachedWorkerSiteLocation() {
  const cached = readStoredJson(WORKER_CACHED_PAYLOAD_KEY, null);
  return cached?.worker?.siteLocation || null;
}

function storeProximityPin(badgePin) {
  const normalized = normalizeBadgePinInput(badgePin);
  if (!normalized) {
    return;
  }
  try {
    wpSet(WORKER_PROXIMITY_PIN_KEY, normalized);
  } catch {
    // ignore storage failures
  }
}

function clearProximityPin() {
  wpRemove(WORKER_PROXIMITY_PIN_KEY);
  try {
    sessionStorage.removeItem("_wpf");
  } catch {
    // ignore
  }
}

async function fetchProximitySiteHint(badgeId, locationPayload = null) {
  const normalizedBadgeId = normalizeBadgeIdInput(badgeId);
  if (!normalizedBadgeId) {
    return null;
  }
  const cacheKey = locationPayload
    ? `${normalizedBadgeId}:${Math.round(Number(locationPayload.latitude) * 1000)}:${Math.round(Number(locationPayload.longitude) * 1000)}`
    : normalizedBadgeId;
  if (
    proximitySiteHintCache
    && proximitySiteHintCacheBadgeId === cacheKey
    && proximitySiteHintCache.fetchedAt
    && Date.now() - proximitySiteHintCache.fetchedAt < 5 * 60 * 1000
  ) {
    return proximitySiteHintCache;
  }
  try {
    const body = { badgeId: normalizedBadgeId };
    if (locationPayload) {
      body.location = locationPayload;
    }
    const hint = await fetchJson(`${API_BASE}/proximity-site-hint`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    proximitySiteHintCache = { ...hint, fetchedAt: Date.now() };
    proximitySiteHintCacheBadgeId = cacheKey;
    return proximitySiteHintCache;
  } catch {
    return null;
  }
}

function isInsideSiteZones(locationPayload, siteZones, fallbackSiteLocation) {
  const zones = Array.isArray(siteZones) && siteZones.length
    ? siteZones
    : (fallbackSiteLocation ? [fallbackSiteLocation] : []);
  if (!zones.length || !locationPayload) {
    return null;
  }
  for (const zone of zones) {
    if (typeof zone.latitude !== "number" || typeof zone.longitude !== "number") {
      continue;
    }
    const distanceMeters = Math.round(
      calculateDistanceMeters(
        zone.latitude,
        zone.longitude,
        locationPayload.latitude,
        locationPayload.longitude
      )
    );
    const radius = Number(zone.radiusMeters || 20);
    const accuracy = Number(locationPayload.accuracy || locationPayload.accuracyMeters || 0);
    if (accuracy > WORKER_GEO_MAX_ACCURACY_METERS) {
      continue;
    }
    const allowedRadius = radius + (accuracy > 0 ? Math.min(accuracy, WORKER_GEO_ACCURACY_BUFFER_METERS) : 0);
    if (distanceMeters <= allowedRadius) {
      return true;
    }
  }
  return false;
}

function getStoredBadgePinForProximity() {
  try {
    const sessionPin = normalizeBadgePinInput(sessionStorage.getItem("_wpf") || "");
    if (sessionPin) {
      return sessionPin;
    }
  } catch {
    // ignore
  }
  return normalizeBadgePinInput(wpGet(WORKER_PROXIMITY_PIN_KEY) || "");
}

function getAttendanceEligibilityFromHint(hint) {
  const raw = hint?.attendanceEligibility;
  if (!raw || typeof raw !== "object") {
    return { ok: true, reason: "", message: "", dayType: "", shiftStart: "", shiftEnd: "" };
  }
  return {
    ok: raw.ok !== false,
    reason: String(raw.reason || "").trim(),
    message: String(raw.message || "").trim(),
    dayType: String(raw.dayType || "").trim(),
    shiftStart: String(raw.shiftStart || hint.workStartTime || "").trim(),
    shiftEnd: String(raw.shiftEnd || hint.workEndTime || "").trim(),
  };
}

function shouldAllowProximityAutoLogin(hint) {
  if (!hint || hint.siteAutoProximityLogin === false) {
    return false;
  }
  if (String(hint.accessMode || "").toLowerCase() !== "site_app") {
    return false;
  }
  return getAttendanceEligibilityFromHint(hint).ok;
}

function proximityAttendanceBlockedMessage(hint) {
  const attendance = getAttendanceEligibilityFromHint(hint);
  if (attendance.ok) {
    return "";
  }
  if (attendance.message) {
    return attendance.message;
  }
  if (attendance.reason === "outside_work_hours" || attendance.reason === "outside_shift_window") {
    return t("proximityOutsideWorkHours");
  }
  if (attendance.reason === "on_approved_leave") {
    return t("proximityOnLeave");
  }
  return t("proximityNotScheduledToday");
}

function stopProximityLoginWatcher() {
  if (proximityLoginWatchTimer) {
    clearInterval(proximityLoginWatchTimer);
    proximityLoginWatchTimer = null;
  }
  proximityInsideSince = 0;
  proximityLoginInProgress = false;
}

function startProximityLoginWatcher() {
  stopProximityLoginWatcher();
  if (document.body.classList.contains("qr-fast-login")) {
    return;
  }
  if (workerToken || offlineWorkerSessionActive) {
    return;
  }
  const badgeId = normalizeBadgeIdInput(wpGet(WORKER_BADGE_LOGIN_KEY) || "");
  const badgePin = getStoredBadgePinForProximity();
  if (!badgeId || isVisitorBadgeId(badgeId) || !badgePin || !navigator.geolocation) {
    return;
  }
  void pollProximityLoginCandidate();
  proximityLoginWatchTimer = setInterval(() => {
    void pollProximityLoginCandidate();
  }, PROXIMITY_LOGIN_POLL_MS);
}

async function pollProximityLoginCandidate() {
  if (workerToken || proximityLoginInProgress || !navigator.onLine) {
    return;
  }
  const badgeId = normalizeBadgeIdInput(wpGet(WORKER_BADGE_LOGIN_KEY) || "");
  const badgePin = getStoredBadgePinForProximity();
  if (!badgeId || !badgePin) {
    stopProximityLoginWatcher();
    return;
  }

  const siteHintBase = await fetchProximitySiteHint(badgeId);
  const hintCfg = siteAccessCfgFromHint(siteHintBase);
  if (siteHintBase && siteHintBase.siteAutoProximityLogin === false) {
    updateSiteGpsStatusBar({ cfg: hintCfg, preview: siteHintBase.locationPreview });
    stopProximityLoginWatcher();
    return;
  }
  if (siteHintBase && String(siteHintBase.accessMode || "").toLowerCase() !== "site_app") {
    updateSiteGpsStatusBar({ cfg: hintCfg, preview: siteHintBase.locationPreview });
    stopProximityLoginWatcher();
    return;
  }
  if (siteHintBase && !shouldAllowProximityAutoLogin(siteHintBase)) {
    updateSiteGpsStatusBar({
      cfg: hintCfg,
      preview: siteHintBase.locationPreview,
      phase: "attendance-blocked",
      blockedMessage: proximityAttendanceBlockedMessage(siteHintBase),
    });
    stopProximityLoginWatcher();
    return;
  }

  const locationPayload = await resolveSiteLocation({ preferFast: false });
  if (!locationPayload) {
    proximityInsideSince = 0;
    updateSiteGpsStatusBar({ cfg: hintCfg, preview: siteHintBase?.locationPreview });
    return;
  }

  const siteHint = (await fetchProximitySiteHint(badgeId, locationPayload)) || siteHintBase;
  let inside = null;
  const preview = siteHint?.locationPreview;
  if (preview && typeof preview.onSite === "boolean") {
    inside = preview.onSite;
  } else if (preview?.error === "worker_geolocation_inaccurate") {
    inside = null;
  } else {
    inside = isInsideSiteZones(
      locationPayload,
      siteHint?.siteZones,
      siteHint?.siteLocation || getCachedWorkerSiteLocation()
    );
  }
  if (inside === false) {
    proximityInsideSince = 0;
    proximityLoginNoticeShownAt = 0;
    updateSiteGpsStatusBar({ cfg: siteAccessCfgFromHint(siteHint), preview });
    return;
  }
  if (inside === null && preview?.error === "worker_geolocation_inaccurate") {
    updateSiteGpsStatusBar({ cfg: siteAccessCfgFromHint(siteHint), preview });
    showWorkerNotice(t("geolocationInaccurate"));
    return;
  }

  updateSiteGpsStatusBar({
    cfg: siteAccessCfgFromHint(siteHint),
    preview: inside ? { onSite: true, ...(preview || {}) } : preview,
    phase: proximityInsideSince ? "proximity-wait" : undefined,
  });

  const now = Date.now();
  if (!proximityInsideSince) {
    proximityInsideSince = now;
    if (!proximityLoginNoticeShownAt) {
      proximityLoginNoticeShownAt = now;
      showWorkerNotice(t("proximityLoginWaiting"));
    }
    return;
  }
  if (now - proximityInsideSince < PROXIMITY_LOGIN_DWELL_MS) {
    return;
  }

  proximityLoginInProgress = true;
  try {
    const payload = await fetchJson(`${API_BASE}/proximity-login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        badgeId,
        badgePin,
        location: locationPayload,
        dwellSeconds: Math.round((now - proximityInsideSince) / 1000),
      }),
    });
    stopProximityLoginWatcher();
    offlineWorkerSessionActive = false;
    workerToken = payload.token;
    wpSet(WORKER_TOKEN_KEY, workerToken);
    wpSet(WORKER_BADGE_LOGIN_KEY, badgeId);
    storeProximityPin(badgePin);
    wpRemove(WORKER_ACCESS_TOKEN_KEY);
    await loadWorkerData();
    await persistOfflineBadgeProfile(badgeId, badgePin, payload);
    finishWorkerLoginUi();
    showWorkerNotice(payload.autoCheckInLogId ? t("proximityLoginCheckIn") : payload.siteLoginLogId ? t("siteGpsRegistered") : t("proximityLoginSuccess"));
    initializeSessionInactivityProtection();
    void ensureWorkerPushNotifications({ promptIfNeeded: false });
  } catch (error) {
    proximityInsideSince = 0;
    const quietCodes = new Set([
      "not_scheduled_today",
      "on_approved_leave",
      "deployment_declined",
      "outside_shift_window",
      "outside_work_hours",
      "not_a_workday",
      "attendance_not_allowed",
      "worker_geolocation_required",
      "worker_geolocation_inaccurate",
    ]);
    if (!quietCodes.has(error.code)) {
      if (error.code === "proximity_login_disabled" || error.code === "outside_site_radius") {
        showWorkerNotice(error.message || t("proximityLoginFailed"));
      } else if (error.code === "not_scheduled_today" || error.code === "outside_shift_window") {
        showWorkerNotice(error.message || t("proximityNotScheduledToday"));
      } else {
        console.warn("[proximity-login]", error.code || error.message);
      }
    }
  } finally {
    proximityLoginInProgress = false;
  }
}

function getSiteAccessFromPayload(payload = lastWorkerPayload) {
  const company = payload?.company || {};
  const siteAccess = payload?.siteAccess || {};
  const worker = payload?.worker || {};
  const attendanceRaw = siteAccess.attendanceEligibility || {};
  const siteLocation = worker.siteLocation || siteAccess.siteLocation || null;
  const siteZones = Array.isArray(siteAccess.siteZones) && siteAccess.siteZones.length
    ? siteAccess.siteZones
    : (Array.isArray(worker.siteZones) && worker.siteZones.length ? worker.siteZones : []);
  const accessMode = String(company.accessMode || siteAccess.accessMode || "gate").trim().toLowerCase();
  const attendanceShiftStart = String(attendanceRaw.shiftStart || "").trim();
  const attendanceShiftEnd = String(attendanceRaw.shiftEnd || "").trim();
  return {
    accessMode,
    siteApp: accessMode === "site_app",
    autoProximityLogin: company.siteAutoProximityLogin !== false && siteAccess.siteAutoProximityLogin !== false,
    radiusMeters: Number(
      company.siteGeofenceRadiusMeters ||
        siteAccess.siteGeofenceRadiusMeters ||
        siteLocation?.radiusMeters ||
        siteZones[0]?.radiusMeters ||
        80
    ),
    autoLogout: company.siteAutoLogoutOnLeave !== false && siteAccess.siteAutoLogoutOnLeave !== false,
    workStart: attendanceShiftStart || String(company.workStartTime || siteAccess.workStartTime || "").trim(),
    workEnd: attendanceShiftEnd || String(company.workEndTime || siteAccess.workEndTime || "").trim(),
    isWorkdayToday: siteAccess.isWorkdayToday !== false,
    attendanceOk: attendanceRaw.ok !== false,
    attendanceReason: String(attendanceRaw.reason || "").trim(),
    attendanceMessage: String(attendanceRaw.message || "").trim(),
    siteLocation: siteLocation || siteZones[0] || null,
    siteZones,
  };
}

function hasSiteGeofenceConfig(cfg) {
  return Boolean(
    cfg?.siteLocation ||
      (Array.isArray(cfg?.siteZones) && cfg.siteZones.length)
  );
}

function workerApiHostLabel() {
  try {
    return new URL(API_BASE).host;
  } catch {
    return String(API_BASE || "").replace(/^https?:\/\//, "").split("/")[0] || "—";
  }
}

function siteAccessCfgFromHint(hint) {
  if (!hint) return null;
  const attendance = getAttendanceEligibilityFromHint(hint);
  return {
    accessMode: String(hint.accessMode || "gate").toLowerCase(),
    siteApp: String(hint.accessMode || "").toLowerCase() === "site_app",
    siteLocation: hint.siteLocation || null,
    siteZones: Array.isArray(hint.siteZones) ? hint.siteZones : [],
    radiusMeters: Number(hint.siteGeofenceRadiusMeters || 80),
    workStart: attendance.shiftStart || String(hint.workStartTime || "").trim(),
    workEnd: attendance.shiftEnd || String(hint.workEndTime || "").trim(),
    isWorkdayToday: attendance.ok || !["weekend", "free", "leave"].includes(attendance.dayType),
    attendanceOk: attendance.ok,
    attendanceReason: attendance.reason,
    attendanceMessage: attendance.message,
  };
}

function ensureSiteGpsStatusBar() {
  let bar = document.getElementById("workerSiteGpsStatus");
  if (bar) return bar;
  bar = document.createElement("div");
  bar.id = "workerSiteGpsStatus";
  bar.className = "worker-site-gps-status";
  bar.setAttribute("role", "status");
  const banner = document.getElementById("workerWorkHoursBanner");
  if (banner?.parentNode) {
    banner.insertAdjacentElement("afterend", bar);
  } else {
    const anchor = elements.workerHubPanel || document.querySelector(".app-shell");
    anchor?.prepend(bar);
  }
  return bar;
}

function updateSiteGpsStatusBar({ cfg, preview, phase, blockedMessage } = {}) {
  const bar = ensureSiteGpsStatusBar();
  const server = workerApiHostLabel();
  if (!workerToken && document.body.classList.contains("worker-login-shell")) {
    bar.textContent = "";
    bar.classList.add("hidden");
    bar.removeAttribute("data-tone");
    return;
  }
  if (!cfg) {
    bar.textContent = "";
    bar.classList.add("hidden");
    bar.removeAttribute("data-tone");
    return;
  }
  bar.classList.remove("hidden");
  if (!cfg.siteApp) {
    bar.textContent = tf("siteGpsStatusGateMode", { server });
    bar.dataset.tone = "warn";
    return;
  }
  if (!hasSiteGeofenceConfig(cfg)) {
    bar.textContent = tf("siteGpsStatusNoGeofence", { server });
    bar.dataset.tone = "warn";
    return;
  }
  if (preview?.onSite) {
    bar.textContent = tf("siteGpsStatusOnSite", {
      distance: preview.distanceMeters ?? "—",
      allowed: preview.allowedRadiusMeters ?? cfg.radiusMeters ?? 80,
      server,
    });
    bar.dataset.tone = "ok";
    return;
  }
  if (typeof preview?.distanceMeters === "number") {
    bar.textContent = tf("siteGpsStatusOutside", {
      distance: preview.distanceMeters,
      allowed: preview.allowedRadiusMeters ?? cfg.radiusMeters ?? 80,
      server,
    });
    bar.dataset.tone = "warn";
    return;
  }
  if (preview?.error === "worker_geolocation_inaccurate") {
    bar.textContent = `${t("geolocationInaccurate")} · ${server}`;
    bar.dataset.tone = "warn";
    return;
  }
  if (phase === "proximity-wait") {
    bar.textContent = t("proximityLoginWaiting");
    bar.dataset.tone = "pending";
    return;
  }
  if (phase === "attendance-blocked") {
    bar.textContent = blockedMessage || t("proximityNotScheduledToday");
    bar.dataset.tone = "warn";
    return;
  }
  bar.textContent = tf("siteGpsStatusWaiting", { server });
  bar.dataset.tone = "pending";
}

function applySiteAccessUi(payload = lastWorkerPayload) {
  const cfg = getSiteAccessFromPayload(payload);
  lastSiteAccessCfg = cfg;
  document.body.classList.toggle("site-app-mode", cfg.siteApp);

  [elements.gateModeButton, elements.quickGateModeButton].forEach((btn) => {
    if (!btn) return;
    btn.classList.toggle("hidden", cfg.siteApp);
    btn.setAttribute("aria-hidden", cfg.siteApp ? "true" : "false");
  });

  let banner = document.getElementById("workerWorkHoursBanner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "workerWorkHoursBanner";
    banner.className = "worker-work-hours-banner";
    const anchor = elements.workerHubPanel || document.querySelector(".app-shell");
    if (anchor) anchor.prepend(banner);
  }
  if (banner) {
    if (cfg.siteApp) {
      if (cfg.attendanceOk === false && cfg.attendanceMessage) {
        banner.innerHTML = `<span class="worker-work-hours-message">${escapeHtmlBasic(cfg.attendanceMessage)}</span>`;
      } else if (cfg.workStart && cfg.workEnd) {
        const dayHint = cfg.isWorkdayToday
          ? ""
          : `<span class="worker-work-hours-hint">${escapeHtmlBasic(t("notAWorkdayToday"))}</span>`;
        banner.innerHTML = `
          <span class="worker-work-hours-label">${escapeHtmlBasic(t("workHoursToday"))}</span>
          <span class="worker-work-hours-range">${escapeHtmlBasic(cfg.workStart)} – ${escapeHtmlBasic(cfg.workEnd)}</span>
          ${dayHint}
        `.trim();
      } else {
        banner.innerHTML = `<span class="worker-work-hours-message">${escapeHtmlBasic(t("workHoursConfigureInAdmin"))}</span>`;
      }
      banner.classList.remove("hidden");
    } else {
      banner.classList.add("hidden");
    }
  }

  stopSiteGeofenceMonitor();
  lastSitePresenceNoticeKey = "";
  if (cfg.siteApp && workerToken && !offlineWorkerSessionActive && hasSiteGeofenceConfig(cfg) && cfg.attendanceOk !== false) {
    startSiteGeofenceMonitor(cfg);
  } else if (cfg.siteApp && workerToken && !offlineWorkerSessionActive && !hasSiteGeofenceConfig(cfg)) {
    showWorkerNotice(t("siteGpsNotConfigured"));
  } else if (workerToken && !cfg.siteApp && !siteAccessGateModeNoticeShown) {
    siteAccessGateModeNoticeShown = true;
    showWorkerNotice(t("siteAccessGateModeHint"));
  }
  if (cfg.siteApp) {
    siteAccessGateModeNoticeShown = false;
  }
  updateSiteGpsStatusBar({ cfg });
}

async function handleSiteLeaveDetected() {
  if (siteGeofenceLeaveInProgress || !workerToken) return;
  siteGeofenceLeaveInProgress = true;
  stopSiteGeofenceMonitor();
  const tokenForLeave = workerToken;
  const cfg = lastSiteAccessCfg;
  let leavePayload = null;
  try {
    const locationPayload = await resolveSiteLocation({ preferFast: false });
    leavePayload = await fetchJson(`${API_BASE}/site-leave`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${tokenForLeave}`,
      },
      body: JSON.stringify({ location: locationPayload }),
    });
  } catch (error) {
    console.warn("[site-leave]", error);
  }
  if (tokenForLeave === workerToken) {
    const fullLogout = leavePayload?.loggedOut === true;
    if (fullLogout) {
      invalidateWorkerSession({ showNotice: false });
      showWorkerNotice(t("siteLeaveAutoLogout"));
      showWorkerNotice(t("siteReturnProximityHint"));
      lastSitePresenceNoticeKey = "";
      const badgeId = normalizeBadgeIdInput(wpGet(WORKER_BADGE_LOGIN_KEY) || "");
      if (badgeId && getStoredBadgePinForProximity()) {
        try {
          const hint = await fetchProximitySiteHint(badgeId);
          if (shouldAllowProximityAutoLogin(hint)) {
            startProximityLoginWatcher();
          }
          updateSiteGpsStatusBar({ cfg: siteAccessCfgFromHint(hint) || cfg || undefined });
        } catch {
          updateSiteGpsStatusBar({ cfg: cfg || undefined });
        }
      }
    } else {
      showWorkerNotice(t("siteLeaveAttendanceOnly"));
      siteOffSiteStrikeCount = 0;
      if (cfg) {
        startSiteGeofenceMonitor(cfg);
      }
    }
  }
  siteGeofenceLeaveInProgress = false;
}

async function pollSitePresence(cfg) {
  if (!workerToken || offlineWorkerSessionActive || siteGeofenceLeaveInProgress) return;
  lastSiteAccessCfg = cfg;
  let locationPayload = null;
  try {
    locationPayload = await resolveSiteLocation({ preferFast: false });
  } catch {
    return;
  }
  if (!locationPayload) {
    return;
  }
  try {
    const presence = await fetchJson(`${API_BASE}/site-presence`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${workerToken}`,
      },
      body: JSON.stringify({ location: locationPayload }),
    });
    updateSiteGpsStatusBar({
      cfg,
      preview: {
        onSite: presence?.onSite,
        distanceMeters: presence?.distanceMeters,
        allowedRadiusMeters: presence?.allowedRadiusMeters || presence?.radiusMeters,
        error: presence?.error,
      },
    });
    if (presence?.autoCheckInLogId) {
      const noticeKey = `checkin:${presence.autoCheckInLogId}`;
      if (noticeKey !== lastSitePresenceNoticeKey) {
        lastSitePresenceNoticeKey = noticeKey;
        showWorkerNotice(t("siteAutoCheckIn"));
      }
    } else if (presence?.siteLoginLogId) {
      const noticeKey = `login:${presence.siteLoginLogId}`;
      if (noticeKey !== lastSitePresenceNoticeKey) {
        lastSitePresenceNoticeKey = noticeKey;
        showWorkerNotice(t("siteGpsRegistered"));
      }
    } else if (presence?.siteLeaveApplied) {
      const leaveKey = `leave:${presence.checkoutLogId || presence.siteLeaveLogId || "applied"}`;
      if (leaveKey !== lastSitePresenceNoticeKey) {
        lastSitePresenceNoticeKey = leaveKey;
        if (presence.loggedOut) {
          invalidateWorkerSession({ showNotice: false });
          showWorkerNotice(t("siteLeaveAutoLogout"));
          showWorkerNotice(t("siteReturnProximityHint"));
          const badgeId = normalizeBadgeIdInput(wpGet(WORKER_BADGE_LOGIN_KEY) || "");
          if (badgeId && getStoredBadgePinForProximity()) {
            try {
              const hint = await fetchProximitySiteHint(badgeId);
              if (shouldAllowProximityAutoLogin(hint)) {
                startProximityLoginWatcher();
              }
            } catch {
              // ignore
            }
          }
        } else {
          showWorkerNotice(t("siteLeaveAttendanceOnly"));
        }
      }
      siteOffSiteStrikeCount = 0;
      void loadMyTimesheets();
      if (!presence.loggedOut && cfg) {
        startSiteGeofenceMonitor(cfg);
      }
      return;
    } else if (presence?.onSite && presence?.attendanceBlocked?.message) {
      const noticeKey = `blocked:${presence.attendanceBlocked.reason || presence.attendanceBlocked.message}`;
      if (noticeKey !== lastSitePresenceNoticeKey) {
        lastSitePresenceNoticeKey = noticeKey;
        showWorkerNotice(presence.attendanceBlocked.message);
      }
    }
    const offSiteForLeave = presence?.onSiteForLeave === false
      || (presence?.onSiteForLeave === undefined && presence?.onSite === false);
    const registeredOnSite = Boolean(presence?.openCheckInToday || presence?.siteSessionOpen);
    if (offSiteForLeave && typeof presence?.distanceMeters === "number" && registeredOnSite) {
      showWorkerNotice(
        tf("siteOutsideRadius", {
          distance: presence.distanceMeters,
          allowed: presence.allowedRadiusMeters || presence.radiusMeters || cfg?.radiusMeters || 80,
        })
      );
    }
    if (offSiteForLeave && cfg?.autoLogout !== false && registeredOnSite && !presence?.siteLeaveApplied) {
      siteOffSiteStrikeCount += 1;
      if (siteOffSiteStrikeCount >= SITE_OFF_SITE_STRIKES_REQUIRED) {
        await handleSiteLeaveDetected();
      }
    } else {
      siteOffSiteStrikeCount = 0;
    }
  } catch (error) {
    if (isWorkerSessionAuthError(error?.code)) {
      return;
    }
    if (error.code === "worker_geolocation_inaccurate") {
      showWorkerNotice(error.message || t("geolocationInaccurate"));
      return;
    }
    if (error.code === "site_location_unavailable") {
      showWorkerNotice(t("siteGpsNotConfigured"));
      return;
    }
    console.warn("[site-presence]", error);
  }
}

function startSiteGeofenceMonitor(cfg) {
  stopSiteGeofenceMonitor();
  siteOffSiteStrikeCount = 0;
  lastSitePresenceNoticeKey = "";
  void pollSitePresence(cfg);
  siteGeofenceWatchTimer = setInterval(() => {
    void pollSitePresence(cfg);
  }, SITE_GEOFENCE_WATCH_INTERVAL_MS);
}

function invalidateWorkerSession({ showNotice = true } = {}) {
  stopSiteGeofenceMonitor();
  stopProximityLoginWatcher();
  wpRemove(WORKER_TOKEN_KEY);
  wpRemove(WORKER_JWT_KEY);
  wpRemove(WORKER_DEVICE_ID_KEY);
  wpRemove(WORKER_CACHED_PAYLOAD_KEY);
  offlineWorkerSessionActive = false;
  workerToken = "";
  workerBearerToken = "";
  workerChatThreadId = "";
  stopWorkerChatPolling();
  clearWorkerSessionExpiryTimer();
  if (showNotice) {
    showWorkerNotice(t("sessionExpired"));
  }
  showLogin();
  startProximityLoginWatcher();
}

function isWorkerLoginAuthError(code) {
  const normalized = String(code || "").trim();
  return [
    "invalid_badge_id",
    "invalid_badge_pin",
    "badge_pin_not_configured",
    "missing_badge_pin",
    "visitor_visit_expired",
    "worker_app_disabled",
    "invalid_access_token",
    "access_token_expired",
    "access_token_already_used",
  ].includes(normalized);
}

function isWorkerLoginNetworkError(error) {
  if (!error) {
    return false;
  }
  if (error.code === "network_error" || error.code === "offline") {
    return true;
  }
  if (!error.code && (error.name === "TypeError" || error.name === "AbortError")) {
    return true;
  }
  return false;
}

function shouldAttemptOfflineWorkerLogin(error) {
  if (isWorkerLoginAuthError(error?.code)) {
    return false;
  }
  return !navigator.onLine || isWorkerLoginNetworkError(error);
}

function workerLoginErrorMessage(error) {
  if (!error) {
    return t("loginFailed");
  }
  if (error.code === "invalid_badge_id") {
    return t("badgeNotFound");
  }
  if (error.code === "invalid_badge_pin") {
    return t("badgePinWrong");
  }
  if (error.code === "missing_badge_pin") {
    return t("enterPin");
  }
  if (error.code === "rate_limited") {
    return t("loginFailed") + " (bitte kurz warten und erneut versuchen)";
  }
  if (error.code === "badge_pin_not_configured") {
    return t("badgePinNotConfigured");
  }
  if (error.code === "worker_geolocation_required") {
    return t("geolocationRequiredLogin");
  }
  if (error.code === "worker_geolocation_inaccurate") {
    return error.message || t("geolocationInaccurate");
  }
  if (error.code === "outside_site_radius") {
    return error.message || t("outsideSiteRadius");
  }
  if (error.code === "chat_send_failed" || error.code === "message_required") {
    return error.message || t("workerChatSendFailed");
  }
  if (error.code === "not_scheduled_today") {
    return t("proximityNotScheduledToday");
  }
  if (error.code === "on_approved_leave") {
    return t("proximityOnLeave");
  }
  if (error.code === "feature_not_available") {
    return formatWorkerApiError(error);
  }
  if (error.code === "login_server_error" || error.code === "internal_server_error") {
    return t("loginServerError");
  }
  if (isWorkerLoginNetworkError(error)) {
    return t("connError");
  }
  return error.message || t("loginFailed");
}

async function fetchJson(url, options = {}) {
  const requestOptions = { ...(options || {}) };
  if (isWorkerProtectedApiUrl(url) && !isWorkerAnonymousRequest(url) && getWorkerAuthorizationValue()) {
    requestOptions.headers = buildWorkerAuthHeaders(requestOptions.headers || {});
  }
  let response;
  try {
    response = await fetch(url, requestOptions);
  } catch (fetchError) {
    const error = new Error(fetchError?.message || "Network error");
    error.code = "network_error";
    error.cause = fetchError;
    throw error;
  }
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    let code = "";
    let payload = null;
    try {
      payload = await response.json();
      code = payload?.error || "";
      message = payload?.message || payload?.error || message;
    } catch {
      // ignore parse errors
    }
    if (!code && payload?.offline) {
      code = "network_error";
      message = t("connError");
    }
    const error = new Error(message);
    error.code = code;
    error.payload = payload;
    if (isWorkerProtectedApiUrl(url) && isWorkerSessionAuthError(code)) {
      if (!shouldKeepWorkerShellAfterSyncError({ code })) {
        invalidateWorkerSession({ showNotice: true });
      }
    }
    if (isWorkerProtectedApiUrl(url) && code === "device_not_bound") {
      wpRemove(WORKER_DEVICE_ID_KEY);
      if (!shouldKeepWorkerShellAfterSyncError({ code })) {
        showLoginError(t("loginFailed") + " (Gerät nicht freigegeben – bitte erneut anmelden).", { code });
      }
    }
    throw error;
  }
  return response.json();
}

function isAccessLogCheckIn(direction) {
  const value = String(direction || "").trim().toLowerCase();
  return value === "in" || value === "check-in" || value === "check_in" || value === "entry" || value === "app-login";
}

function isAccessLogCheckOut(direction) {
  const value = String(direction || "").trim().toLowerCase();
  return value === "out" || value === "check-out" || value === "check_out" || value === "exit" || value === "app-logout";
}

function minutesBetweenWorkerAccessTimestamps(start, end) {
  const inTime = new Date(String(start || ""));
  const outTime = new Date(String(end || ""));
  if (Number.isNaN(inTime.getTime()) || Number.isNaN(outTime.getTime()) || outTime <= inTime) {
    return null;
  }
  const seconds = Math.floor((outTime - inTime) / 1000);
  if (seconds <= 0) return null;
  return Math.min(Math.max(1, Math.ceil(seconds / 60)), 1439);
}

function pairWorkerPresenceSessions(events) {
  const ordered = [...(events || [])].sort((left, right) =>
    String(left.timestamp || "").localeCompare(String(right.timestamp || ""))
  );
  const sessions = [];
  let pendingIn = null;

  for (const ev of ordered) {
    if (isAccessLogCheckIn(ev.direction)) {
      if (!pendingIn) pendingIn = ev;
      continue;
    }
    if (!isAccessLogCheckOut(ev.direction)) continue;

    if (pendingIn) {
      sessions.push({
        checkIn: pendingIn,
        checkOut: ev,
        durationMinutes: minutesBetweenWorkerAccessTimestamps(pendingIn.timestamp, ev.timestamp),
      });
      pendingIn = null;
    }
  }

  if (pendingIn) {
    sessions.push({
      checkIn: pendingIn,
      checkOut: null,
      durationMinutes: minutesBetweenWorkerAccessTimestamps(pendingIn.timestamp, new Date().toISOString()),
    });
  }

  return sessions;
}

function summarizeWorkerPresenceMinutes(events) {
  return pairWorkerPresenceSessions(events).reduce((sum, session) => {
    const minutes = Number(session.durationMinutes) || 0;
    return sum + (minutes > 0 ? minutes : 0);
  }, 0);
}

function workerPlanAllowsFeature(featureKey, planFeaturesOverride) {
  if (!featureKey) return true;
  const features = planFeaturesOverride ?? lastWorkerPayload?.planFeatures;
  if (!features || typeof features !== "object") return true;
  if (!Object.keys(features).length) return true;
  if (featureKey === "deployment_plan" && features[featureKey] === undefined) return true;
  if (featureKey === "worker_chat") {
    if (features.worker_chat === true || features.worker_app === true) return true;
    if (features.worker_chat === undefined && features.worker_app === undefined) return true;
    if (features.worker_chat === false && features.worker_app !== true) return false;
    return Boolean(features.worker_chat);
  }
  if (features[featureKey] === false) return false;
  return Boolean(features[featureKey]);
}

function applyWorkerDeploymentMenuState(planFeatures = {}) {
  const allowed = planFeatures?.deployment_plan !== false;
  document.querySelectorAll(".worker-menu-btn-deployment, [data-worker-page-target='deploymentPlanCard'], #homeDeploymentTeaser").forEach((btn) => {
    btn.classList.remove("hidden");
    btn.classList.toggle("worker-menu-btn-locked", !allowed);
    btn.toggleAttribute("disabled", !allowed);
    btn.setAttribute("aria-disabled", allowed ? "false" : "true");
    if (!allowed) {
      btn.title = planFeatureBlockedMessage("deployment_plan");
    } else {
      btn.removeAttribute("title");
    }
  });
  const teaser = document.getElementById("homeDeploymentTeaser");
  if (teaser) {
    teaser.classList.toggle("worker-menu-btn-locked", !allowed);
  }
}

function applyWorkerChatMenuState(planFeatures = {}) {
  const allowed = workerPlanAllowsFeature("worker_chat");
  document.querySelectorAll(".worker-menu-btn-chat, [data-worker-page-target='chatCard']").forEach((btn) => {
    btn.classList.toggle("hidden", !allowed);
    btn.classList.toggle("worker-menu-btn-locked", !allowed);
    btn.toggleAttribute("disabled", !allowed);
    btn.setAttribute("aria-disabled", allowed ? "false" : "true");
    if (!allowed) {
      btn.title = planFeatureBlockedMessage("worker_chat");
    } else {
      btn.removeAttribute("title");
    }
  });
  refreshWorkerChatPanel({ skipLoad: !allowed });
}

function refreshWorkerChatPanel(options = {}) {
  const chatCard = ensureWorkerChatDom();
  if (!chatCard) {
    return;
  }
  const onChatTab = currentActiveTab === "chat";
  const allowed = workerPlanAllowsFeature("worker_chat");
  const show = Boolean(workerToken && onChatTab);
  chatCard.classList.toggle("hidden", !show);
  if (!show) {
    chatCard.style.setProperty("display", "none", "important");
    return;
  }
  chatCard.style.removeProperty("display");
  chatCard.classList.remove("hidden");
  setWorkerChatComposeEnabled(allowed);
  if (!allowed) {
    if (elements.workerChatMessages) {
      elements.workerChatMessages.innerHTML = `<p class="muted-info">${escapeHtmlBasic(planFeatureBlockedMessage("worker_chat"))}</p>`;
    }
    return;
  }
  if (!options.skipLoad) {
    startWorkerChatPolling();
    void loadWorkerChat();
  }
  bindWorkerChatComposeEvents();
  applyWorkerChatTabLayout(chatCard);
}

function startWorkerNotificationPolling() {
  if (workerNotificationPollTimer) {
    return;
  }
  workerNotificationPollTimer = setInterval(() => {
    if (!workerToken) {
      return;
    }
    void refreshWorkerNotificationCenter({ silent: true, notifyNew: true });
  }, 30000);
}

function planFeatureBlockedMessage(featureKey) {
  const labels = {
    worker_hours_report: "Arbeitsstunden",
    document_upload: "Dokumente",
    leave_management: "Urlaubsanträge",
    deployment_plan: "Einsatzplan",
    worker_chat: "Chat",
  };
  const label = labels[featureKey] || "Diese Funktion";
  return `${label} ist in Ihrem Paket nicht freigeschaltet. Bitte Ihren Administrator kontaktieren.`;
}

function applyWorkerPlanNavState(planFeatures = {}) {
  Object.entries(WORKER_PLAN_TAB_FEATURES).forEach(([tabName, featureKey]) => {
    const tab = document.querySelector(`.nav-tab[data-tab="${tabName}"]`);
    if (!tab) return;
    const allowed = workerPlanAllowsFeature(featureKey, planFeatures);
    tab.classList.toggle("nav-tab-locked", !allowed);
    tab.setAttribute("aria-disabled", allowed ? "false" : "true");
    if (!allowed) {
      tab.title = planFeatureBlockedMessage(featureKey);
    } else {
      tab.removeAttribute("title");
    }
  });
}

function formatWorkerApiError(error) {
  const code = String(error?.code || error?.payload?.error || "").trim();
  if (code === "feature_not_available") {
    const feature = String(error?.payload?.feature || "").trim();
    const requiredPlan = String(error?.payload?.requiredPlan || "").trim();
    const labels = {
      worker_hours_report: "Arbeitsstunden",
      document_upload: "Dokumente",
      leave_management: "Urlaubsanträge",
      worker_app: "Mitarbeiter-App",
    };
    const label = labels[feature] || "Diese Funktion";
    return requiredPlan
      ? `${label} ist in Ihrem Paket nicht freigeschaltet (benötigt: ${requiredPlan}). Bitte Ihren Administrator kontaktieren.`
      : `${label} ist in Ihrem Paket nicht freigeschaltet. Bitte Ihren Administrator kontaktieren.`;
  }
  if (code === "unauthorized" || code === "session_expired" || code === "invalid_session") {
    return "Sitzung abgelaufen – bitte erneut mit Badge-ID und PIN anmelden.";
  }
  if (isWorkerSessionAuthError(code)) {
    return t("sessionExpired");
  }
  if (code === "plan_not_published") {
    return t("deploymentPlanDeclineErrNotPublished");
  }
  if (code === "no_assignment_for_day") {
    return t("deploymentPlanDeclineErrNoAssignment");
  }
  if (code === "past_day_not_allowed") {
    return t("deploymentPlanDeclineErrPastDay");
  }
  if (code === "decline_save_failed") {
    return t("deploymentPlanDeclineErrSave");
  }
  if (code === "chat_send_failed" || code === "thread_not_found") {
    return t("workerChatSendFailed");
  }
  if (code === "chat_load_failed" || code === "chat_thread_failed") {
    return t("workerChatUnavailable");
  }
  if (code === "attachment_upload_failed" || code === "attachment_payload_required") {
    return t("workerChatDocumentSubmitFailed");
  }
  return String(error?.message || "Daten konnten nicht geladen werden.");
}

function setDeploymentDeclineModalError(message) {
  const el = document.getElementById("deploymentDeclineError");
  if (!el) return;
  const text = String(message || "").trim();
  if (!text) {
    el.textContent = "";
    el.classList.add("hidden");
    return;
  }
  el.textContent = text;
  el.classList.remove("hidden");
}

function renderWorkerListMessage(listEl, message, type = "info") {
  if (!listEl) return;
  const cls = type === "error" ? "worker-panel-error" : "muted-info";
  listEl.innerHTML = `<p class="${cls}">${escapeHtmlBasic(message)}</p>`;
}

function ensureWorkerFeatureHubVisible() {
  workerHubExpanded = true;
  document.body.classList.add("wallet-immersive-sections-open");
  if (elements.workerHubPanel) {
    elements.workerHubPanel.classList.remove("hidden");
    elements.workerHubPanel.style.removeProperty("display");
  }
  if (elements.badgeCard) {
    elements.badgeCard.classList.remove("hidden");
    elements.badgeCard.style.removeProperty("display");
  }
  clearCardEntranceAnimation();
}

function getFeatureTabTitle(tabName) {
  const titles = {
    vacation: t("leaveRequestTitle"),
    timesheet: t("timesheetTitle"),
    documents: t("documentsTitle"),
    chat: t("workerChatTitle"),
  };
  return String(titles[tabName] || "").trim();
}

function updateFeatureTabPageNav(tabName) {
  if (!elements.workerPageNav || !elements.workerPageLabel) return;
  const title = getFeatureTabTitle(tabName);
  if (!title) {
    elements.workerPageNav.classList.add("hidden");
    elements.workerPageLabel.textContent = "";
    return;
  }
  elements.workerPageNav.classList.remove("hidden");
  elements.workerPageLabel.textContent = title;
}

function scrollWorkerFeaturePanelIntoView(panelId) {
  const panel = document.getElementById(panelId);
  if (!panel) return;
  requestAnimationFrame(() => {
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
    const shell = document.querySelector(".app-shell");
    if (shell) {
      shell.scrollTop = 0;
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

function getCurrentMonthKey() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function formatWorkerHoursMinutes(totalMin) {
  const minutes = Math.max(0, Number(totalMin) || 0);
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hours}:${String(mins).padStart(2, "0")}`;
}

function formatMonthLabel(monthKey) {
  const normalized = String(monthKey || "").trim();
  if (!/^\d{4}-\d{2}$/.test(normalized)) {
    return normalized || "-";
  }
  const [year, month] = normalized.split("-").map((part) => Number(part));
  const date = new Date(year, Math.max(0, month - 1), 1);
  return new Intl.DateTimeFormat(getCurrentLocale(), { month: "long", year: "numeric" }).format(date);
}

function normalizeWorkerTimesheetPayload(data) {
  if (Array.isArray(data)) {
    return {
      month: getCurrentMonthKey(),
      monthTotalMinutes: summarizeWorkerPresenceMinutes(data),
      rows: data,
    };
  }
  const rows = Array.isArray(data?.rows) ? data.rows : [];
  return {
    month: String(data?.month || getCurrentMonthKey()).slice(0, 7),
    monthTotalMinutes: Number(data?.monthTotalMinutes) || summarizeWorkerPresenceMinutes(rows),
    rows,
  };
}

function formatDate(value) {
  if (!value) {
    return "-";
  }
  return new Intl.DateTimeFormat(getCurrentLocale(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric"
  }).format(new Date(value));
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return new Intl.DateTimeFormat(getCurrentLocale(), {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(parsed);
}

function renderDayCardValidity(expiresAt) {
  if (!elements.workerDayCardValidity) {
    return;
  }
  if (!expiresAt) {
    elements.workerDayCardValidity.textContent = t("dayCardValidToday");
    return;
  }
  elements.workerDayCardValidity.textContent = tf("dayCardValidUntil", { time: formatDateTime(expiresAt) });
}

function clearWorkerSessionCountdown() {
  if (workerSessionCountdownInterval !== null) {
    window.clearInterval(workerSessionCountdownInterval);
    workerSessionCountdownInterval = null;
  }
}

function renderWorkerSessionCountdown(expiresAt) {
  // Worker cards (Mitarbeiter) don't show countdown timer - only visitors do
  // Mitarbeiter-Karten zeigen keinen Countdown - nur Besucher
  clearWorkerSessionCountdown();
  sessionExpiringSoonNotified = false;
  gateAutoOpenTriggered = false;
  if (!elements.workerSessionCountdown) {
    return;
  }
  // Hide worker session countdown for clean UI
  // Verstecke den Countdown für sauberes UI
  elements.workerSessionCountdown.textContent = "";
  elements.workerSessionCountdown.classList.remove("ok", "warn", "critical");
}

function clearWorkerSessionExpiryTimer() {
  if (workerSessionExpiryTimeout !== null) {
    window.clearTimeout(workerSessionExpiryTimeout);
    workerSessionExpiryTimeout = null;
  }
}

function expireDailyCardInClient() {
  wpRemove(WORKER_TOKEN_KEY);
  workerToken = "";
  clearWorkerSessionExpiryTimer();
  closeGateMode();
  showLogin();
  showWorkerNotice(t("autoEndedAtMidnight"));
}

function scheduleWorkerSessionExpiry(expiresAt) {
  clearWorkerSessionExpiryTimer();
  renderWorkerSessionCountdown(expiresAt);
  if (!expiresAt) {
    return;
  }
  const parsed = new Date(expiresAt);
  if (Number.isNaN(parsed.getTime())) {
    return;
  }
  const msUntilExpiry = parsed.getTime() - Date.now();
  if (msUntilExpiry <= 0) {
    expireDailyCardInClient();
    return;
  }
  workerSessionExpiryTimeout = window.setTimeout(() => {
    expireDailyCardInClient();
  }, msUntilExpiry);
}

function createAvatar(firstName, lastName) {
  const initials = `${firstName?.[0] || ""}${lastName?.[0] || ""}`.toUpperCase();
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="280" height="340" viewBox="0 0 280 340">
      <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#d95d39"/><stop offset="100%" stop-color="#121417"/></linearGradient></defs>
      <rect width="280" height="340" rx="28" fill="url(#g)"/>
      <text x="50%" y="52%" text-anchor="middle" dominant-baseline="middle" font-family="Arial" font-size="84" fill="#fff7ef" font-weight="700">${initials}</text>
    </svg>
  `;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

// ═════════════════════════════════════════════════════════════════════
// ── FEATURE 1: DARK MODE TOGGLE ──
// ═════════════════════════════════════════════════════════════════════

function toggleTheme() {
  const current = wpGet(WORKER_THEME_KEY) || "auto";
  let next = "auto";
  if (current === "auto") next = "light";
  else if (current === "light") next = "dark";
  applyTheme(next);
  wpSet(WORKER_THEME_KEY, next);
}

function applyTheme(theme) {
  if (theme === "auto") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", theme);
  }
}

// ═════════════════════════════════════════════════════════════════════
// ── FEATURE 2: PUSH NOTIFICATIONS (VAPID) ──
// ═════════════════════════════════════════════════════════════════════

async function requestNotificationPermission() {
  await ensureWorkerPushNotifications({ promptIfNeeded: true, showSuccessNotice: true });
}

async function refreshPushSetupBanner() {
  if (!elements.notificationBanner || !workerToken) return;
  try {
    const vapidKeyRes = await fetchJson(`${API_BASE}/push-vapid-key`);
    const hasVapid = Boolean(
      String(vapidKeyRes.vapidPublicKey || vapidKeyRes.publicKey || "").trim(),
    );
    if (!hasVapid && Notification.permission !== "denied") {
      const hint = document.querySelector("#notificationBanner span");
      if (hint) {
        hint.textContent = t("notificationBannerPushNotReady");
      }
      elements.notificationBanner.classList.remove("hidden");
    }
  } catch {
    // ignore
  }
}

async function ensureWorkerPushNotifications({
  promptIfNeeded = false,
  showSuccessNotice = false,
} = {}) {
  if (!workerToken) return;
  if (!("Notification" in window)) {
    if (showSuccessNotice) {
      showWorkerNotice(t("browserPushNotSupported"));
    }
    return;
  }
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    return;
  }

  if (Notification.permission === "denied") {
    if (elements.notificationBanner) {
      elements.notificationBanner.classList.remove("hidden");
    }
    return;
  }

  await refreshPushSetupBanner();

  if (Notification.permission === "default") {
    if (!promptIfNeeded) {
      if (elements.notificationBanner) {
        elements.notificationBanner.classList.remove("hidden");
      }
      return;
    }
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      if (elements.notificationBanner) {
        elements.notificationBanner.classList.remove("hidden");
      }
      return;
    }
  }

  if (Notification.permission === "granted") {
    if (elements.notificationBanner) {
      elements.notificationBanner.classList.add("hidden");
    }
    if (showSuccessNotice) {
      showWorkerNotice(t("notificationsEnabled"));
    }
    await subscribePushNotifications();
  }
}

async function subscribePushNotifications() {
  try {
    if (!workerToken || !("serviceWorker" in navigator) || !("PushManager" in window)) {
      return;
    }

    const registration = await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();

    if (!subscription) {
      const vapidKeyRes = await fetchJson(`${API_BASE}/push-vapid-key`);
      const vapidPublicKey = String(
        vapidKeyRes.vapidPublicKey || vapidKeyRes.publicKey || "",
      ).trim();

      if (!vapidPublicKey) {
        if (!vapidMissingLogged) {
          vapidMissingLogged = true;
          workerDebug("Push notifications skipped: VAPID_PUBLIC_KEY not configured on server.");
        }
        if (elements.notificationBanner) {
          elements.notificationBanner.classList.remove("hidden");
        }
        return;
      }

      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
      });
    }

    await fetchJson(`${API_BASE}/push-subscribe`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${workerToken}`,
      },
      body: JSON.stringify({
        endpoint: subscription.endpoint,
        p256dh: arrayBufferToBase64(subscription.getKey("p256dh")),
        auth: arrayBufferToBase64(subscription.getKey("auth")),
      }),
    });

    workerDebug("Push subscription registered");
  } catch (error) {
    console.error("Push subscription failed:", error);
  }
}

function navigateWorkerAppFromNotification(targetUrl) {
  const raw = String(targetUrl || "").trim();
  if (!raw) return;
  let hash = "";
  try {
    const parsed = new URL(raw, window.location.origin);
    hash = (parsed.hash || "").toLowerCase();
  } catch {
    const hashIndex = raw.indexOf("#");
    hash = hashIndex >= 0 ? raw.slice(hashIndex).toLowerCase() : "";
  }
  if (hash === "#einsatzplan" || hash === "#deployment") {
    void openWorkerDeploymentPlanScreen();
    return;
  }
  if (hash === "#documents" || hash === "#docs") {
    switchToTab("documents");
    return;
  }
  if (hash === "#leave" || hash === "#urlaub") {
    switchToTab("vacation");
    return;
  }
  switchToTab("home");
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/\-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  return new Uint8Array([...rawData].map((char) => char.charCodeAt(0)));
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}

// ═════════════════════════════════════════════════════════════════════
// ── FEATURE 3: LEAVE REQUESTS ──
// ═════════════════════════════════════════════════════════════════════

async function submitLeaveRequest() {
  if (!workerToken || !elements.leaveRequestForm) return;
  if (offlineWorkerSessionActive) {
    showWorkerNotice(t("leaveRequiresOnlineLogin"));
    return;
  }

  const type = elements.leaveRequestType?.value || "urlaub";
  const start = elements.leaveRequestStart?.value || "";
  const end = elements.leaveRequestEnd?.value || "";
  const note = elements.leaveRequestNote?.value || "";
  const recipientEmail = (elements.leaveRequestBossEmail?.value || "").trim();
  
  if (!start || !end) {
    showWorkerNotice(t("enterAccessCode")); // Reuse: please enter dates
    return;
  }
  if (start > end) {
    showWorkerNotice(t("leaveDateRangeInvalid"));
    return;
  }
  if (start > end) {
    showWorkerNotice(t("leaveDateRangeInvalid"));
    return;
  }
  
  try {
    const result = await fetchJson(`${API_BASE}/leave-requests`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${workerToken}`
      },
      body: JSON.stringify({
        type,
        start_date: start,
        end_date: end,
        note,
        recipient_email: recipientEmail
      })
    });
    lastSubmittedLeaveRequestId = String(result?.id || "");
    
    showWorkerNotice(t("leaveRequestSubmitted"));
    if (elements.sendToBossPanel) {
      elements.sendToBossPanel.classList.remove("hidden");
      if (elements.bossEmailInput && elements.leaveRequestBossEmail?.value) {
        elements.bossEmailInput.value = elements.leaveRequestBossEmail.value;
      }
    }
    elements.leaveRequestForm.reset();
    toggleLeaveRequestForm();
    await loadLeaveRequests();
    void loadWorkerData({ quiet: true });
    if (currentActiveTab !== "vacation") {
      switchToTab("vacation");
    }
  } catch (error) {
    if (isWorkerSessionAuthError(error?.code)) {
      return;
    }
    showWorkerNotice(`Fehler: ${formatWorkerApiError(error)}`);
  }
}

function buildStaticLeaveSuggestion(type, start, end) {
  const typeLabel = type === "krank" ? "krankheitsbedingt" : type === "sonstiges" ? "aus persönlichem Grund" : "urlaubsbedingt";
  const dateRange = start && end ? `vom ${start} bis ${end}` : "im gewünschten Zeitraum";
  return `Hiermit beantrage ich ${typeLabel} meine Abwesenheit ${dateRange}. Ich bitte um Genehmigung und danke für die Rückmeldung.`;
}

async function applyAiLeaveSuggestion() {
  const type = elements.leaveRequestType?.value || "urlaub";
  const start = elements.leaveRequestStart?.value || "";
  const end = elements.leaveRequestEnd?.value || "";
  const noteField = elements.leaveRequestNote;
  const btn = elements.leaveRequestAiBtn;
  if (!noteField) return;

  const insertSuggestion = (text, noticeKey) => {
    noteField.value = text;
    showWorkerNotice(t(noticeKey));
  };

  if (!workerToken) {
    insertSuggestion(buildStaticLeaveSuggestion(type, start, end), "aiSuggestionInserted");
    return;
  }
  if (offlineWorkerSessionActive) {
    insertSuggestion(buildStaticLeaveSuggestion(type, start, end), "aiSuggestFallback");
    return;
  }

  const lang = getWorkerLang();
  const dateRange = start && end ? `${start} bis ${end}` : "im gewünschten Zeitraum";
  const typePrompt = type === "krank"
    ? "Krankmeldung"
    : type === "sonstiges"
      ? "Abwesenheitsantrag aus persönlichen Gründen"
      : "Urlaubsantrag";
  const question = [
    `Formuliere einen kurzen, höflichen Antragstext (2–3 Sätze) für einen ${typePrompt}`,
    dateRange !== "im gewünschten Zeitraum" ? `für den Zeitraum ${dateRange}` : "für den gewünschten Zeitraum",
    "Nur den Antragstext, ohne Anrede oder Grußformel.",
    `Sprache: ${lang === "de" ? "Deutsch" : lang}.`,
  ].join(" ");

  const previousLabel = btn?.textContent || "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = t("aiSuggestLoading");
  }

  try {
    const payload = await fetchJson(`${API_BASE}/ai/ask`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${workerToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question, lang }),
    });
    const rawAnswer = String(payload?.answer || payload?.message || "").trim();
    const cleaned = globalThis.BaupassAiUi?.cleanTextForDisplay?.(rawAnswer) || rawAnswer;
    if (cleaned && payload?.configured !== false) {
      insertSuggestion(cleaned, "aiSuggestionInserted");
      return;
    }
    insertSuggestion(buildStaticLeaveSuggestion(type, start, end), payload?.configured === false ? "aiSuggestFallback" : "aiSuggestionInserted");
  } catch {
    insertSuggestion(buildStaticLeaveSuggestion(type, start, end), "aiSuggestFallback");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = previousLabel || t("aiSuggestBtn");
    }
  }
}

async function sendLastLeaveRequestToBoss() {
  if (!workerToken) return;
  if (offlineWorkerSessionActive) {
    showWorkerNotice(t("leaveRequiresOnlineLogin"));
    return;
  }
  if (!lastSubmittedLeaveRequestId) {
    showWorkerNotice(t("submitRequestFirst"));
    return;
  }
  const recipient = (elements.bossEmailInput?.value || "").trim();
  if (!recipient || !recipient.includes("@")) {
    showWorkerNotice(t("enterValidManagerEmail"));
    return;
  }

  try {
    await fetchJson(`${API_BASE}/leave-requests/${encodeURIComponent(lastSubmittedLeaveRequestId)}/send-email`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${workerToken}`
      },
      body: JSON.stringify({ recipient_email: recipient })
    });
    showWorkerNotice(t("sendToBossSuccess"));
  } catch (error) {
    if (isWorkerSessionAuthError(error?.code)) {
      return;
    }
    showWorkerNotice(`${t("sendToBossError")}: ${formatWorkerApiError(error)}`);
  }
}

async function prefillCompanyAdminEmails() {
  if (!workerToken) return;
  try {
    const admins = await fetchJson(`${API_BASE}/company-admins`, {
      headers: { Authorization: `Bearer ${workerToken}` }
    });
    if (!Array.isArray(admins) || admins.length === 0) return;

    const emailList = admins.map(a => a.email).filter(Boolean);
    const firstEmail = emailList[0] || "";

    const populateDatalist = (inputEl, listId) => {
      if (!inputEl) return;
      let dl = document.getElementById(listId);
      if (!dl) {
        dl = document.createElement("datalist");
        dl.id = listId;
        inputEl.parentNode.appendChild(dl);
      }
      dl.innerHTML = emailList.map(e => `<option value="${e}"></option>`).join("");
      inputEl.setAttribute("list", listId);
      if (!inputEl.value && firstEmail) inputEl.value = firstEmail;
    };

    populateDatalist(elements.leaveRequestBossEmail, "bossEmailDatalist1");
    populateDatalist(elements.bossEmailInput, "bossEmailDatalist2");
  } catch (_) {
    // Vorschlag ist optional – Fehler ignorieren
  }
}

function toggleLeaveRequestForm() {
  syncWorkerChatComposeRefs();
  const formWrapper = document.getElementById("leaveRequestFormWrapper");
  const toggleBtn = document.getElementById("leaveRequestToggleBtn");
  if (!formWrapper || !toggleBtn) {
    return;
  }
  elements.leaveRequestFormWrapper = formWrapper;
  elements.leaveRequestToggleBtn = toggleBtn;
  const isHidden = formWrapper.classList.toggle("hidden");
  toggleBtn.textContent = isHidden ? t("leaveRequestNewBtn") : t("leaveRequestHideFormBtn");
}

async function addWorkerPassToWallet(platform) {
  if (!workerToken) {
    showLogin();
    return;
  }
  try {
    showWorkerNotice(t("walletLoading"));
    const payload = await fetchJson(
      `${API_BASE}/wallet/pass?platform=${encodeURIComponent(platform)}`,
      { headers: { Authorization: `Bearer ${workerToken}` } },
    );
    const url = platform === "google"
      ? (payload.add_to_wallet_url || payload.pass_url)
      : payload.pass_url;
    if (!url) {
      showWorkerNotice(t("walletUnavailable"));
      return;
    }
    if (platform === "apple") {
      window.location.assign(url);
    } else {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  } catch (error) {
    if (error?.code === "wallet_not_configured") {
      showWorkerNotice(t("walletNotConfigured"));
      return;
    }
    showWorkerNotice(`${t("walletError")}: ${error.message}`);
  }
}

async function loadIncidents() {
  if (!workerToken || !elements.incidentList) return;
  try {
    const payload = await fetchJson(apiPath("incidents"), {
      headers: { Authorization: `Bearer ${workerToken}` },
    });
    const incidents = Array.isArray(payload?.incidents) ? payload.incidents : [];
    if (!incidents.length) {
      elements.incidentList.innerHTML = `<p class="muted-info">${t("incidentNoReports")}</p>`;
      return;
    }
    elements.incidentList.innerHTML = incidents.map((item) => {
      const status = String(item.status || "open");
      const type = String(item.incident_type || item.type || "-");
      const severity = String(item.severity || "medium");
      const created = formatDateTime(item.created_at);
      const description = String(item.description || "").trim();
      return `<div class="leave-request-item">
        <div class="leave-req-row">
          <strong>${type}</strong>
          <span class="leave-req-badge leave-status-pending">${status} · ${severity}</span>
        </div>
        <div class="leave-req-dates">${created}</div>
        ${description ? `<div class="leave-req-note">${description}</div>` : ""}
      </div>`;
    }).join("");
  } catch (error) {
    workerDebug("Could not load incidents:", error);
    elements.incidentList.innerHTML = `<p class="muted-info">${t("incidentNoReports")}</p>`;
  }
}

async function submitIncidentReport() {
  if (!workerToken || !elements.incidentForm) return;
  const incidentType = String(elements.incidentType?.value || "").trim();
  const severity = String(elements.incidentSeverity?.value || "medium").trim();
  const description = String(elements.incidentDescription?.value || "").trim();
  if (!incidentType || !description) {
    showWorkerNotice(t("incidentSubmitFailed"));
    return;
  }
  try {
    await fetchJson(apiPath("incidents"), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${workerToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ type: incidentType, severity, description }),
    });
    elements.incidentForm.reset();
    if (elements.incidentSeverity) {
      elements.incidentSeverity.value = "medium";
    }
    showWorkerNotice(t("incidentSubmitSuccess"));
    await loadIncidents();
  } catch (error) {
    showWorkerNotice(`${t("incidentSubmitFailed")}: ${error.message}`);
  }
}

async function loadLeaveRequests() {
  if (!workerToken || !elements.leaveRequestList) return;
  
  try {
    const res = await fetchJson(`${API_BASE}/leave-requests`, {
      headers: { Authorization: `Bearer ${workerToken}` }
    });
    
    const requests = Array.isArray(res) ? res : res.requests || [];
    if (requests.length === 0) {
      elements.leaveRequestList.innerHTML = `<p class="muted-info">${t("leaveNoRequests") || "Keine Anträge vorhanden."}</p>`;
    } else {
      const sortedRequests = [...requests].sort((a, b) => {
        const aDate = String(a.start_date || a.created_at || "");
        const bDate = String(b.start_date || b.created_at || "");
        if (aDate === bDate) return 0;
        return aDate < bDate ? 1 : -1;
      });
      const visibleRequests = leaveCompactExpanded ? sortedRequests : sortedRequests.slice(0, 1);
      const hiddenCount = Math.max(0, sortedRequests.length - visibleRequests.length);

      const requestMarkup = visibleRequests.map((req) => {
        const typeMap = { urlaub: "Urlaub", krank: "Krank", sonderurlaub: "Sonderurlaub", unbezahlt: "Unbezahlt" };
        const typeLabel = typeMap[req.type] || req.type || "–";
        const statusCls = req.status === "genehmigt" ? "leave-status-ok" : req.status === "abgelehnt" ? "leave-status-no" : "leave-status-pending";
        const statusTxt = req.status === "genehmigt"
          ? t("leaveStatusApproved")
          : req.status === "abgelehnt"
            ? t("leaveStatusRejected")
            : t("leaveStatusPending");
        return `<div class="leave-request-item ${statusCls}">
          <div class="leave-req-row">
            <strong>${typeLabel}</strong>
            <span class="leave-req-badge ${statusCls}">${statusTxt}</span>
          </div>
          <div class="leave-req-dates">${req.start_date} → ${req.end_date}${req.days_count > 0 ? ` <span class="leave-req-days">${req.days_count} AT</span>` : ""}</div>
          ${req.note ? `<div class="leave-req-note">${req.note}</div>` : ""}
          ${req.review_note ? `<div class="leave-req-review">📋 ${req.review_note}</div>` : ""}
        </div>`;
      }).join("");

      const toggleMarkup = hiddenCount > 0 || leaveCompactExpanded
        ? `<button id="leaveRequestsCompactToggleBtn" class="ghost small-btn compact-list-toggle" type="button">${leaveCompactExpanded ? t("compactShowLess") : `${t("compactShowMore")} (+${hiddenCount})`}</button>`
        : "";

      elements.leaveRequestList.innerHTML = requestMarkup + toggleMarkup;

      const toggleBtn = document.querySelector("#leaveRequestsCompactToggleBtn");
      if (toggleBtn) {
        toggleBtn.addEventListener("click", () => {
          leaveCompactExpanded = !leaveCompactExpanded;
          void loadLeaveRequests();
        });
      }
    }
  } catch (error) {
    renderWorkerListMessage(elements.leaveRequestList, formatWorkerApiError(error), "error");
    console.warn("Could not load leave requests:", error);
  }
}

// ═════════════════════════════════════════════════════════════════════
// ── FEATURE: PROFESSIONAL CARD ENTRANCE ANIMATION ──
// العملية: البطاقة تظهر مباشرة → بعد 15 ثانية تنتقل للأعلى → تظهر المميزات
// ═════════════════════════════════════════════════════════════════════

let cardEntranceTimer = null;

function setWorkerFeaturePanelVisibility(visible) {
  if (!elements.workerHubPanel && !elements.workerMenuCard) {
    return;
  }

  if (visible) {
    if (elements.workerHubPanel) {
      elements.workerHubPanel.style.removeProperty("display");
      elements.workerHubPanel.classList.remove("hidden");
    }
    if (elements.workerMenuCard) {
      elements.workerMenuCard.style.removeProperty("display");
      elements.workerMenuCard.classList.remove("hidden");
    }
    return;
  }

  if (elements.workerHubPanel) {
    elements.workerHubPanel.style.setProperty("display", "none", "important");
  }
  if (elements.workerMenuCard) {
    elements.workerMenuCard.style.setProperty("display", "none", "important");
  }
}

function initializeCardEntranceAnimation() {
  // Clear any previous timer
  if (cardEntranceTimer) clearTimeout(cardEntranceTimer);
  
  if (!elements.badgeCard) return;
  
  // Step 1: Card appears with entrance animation (already visible from renderWorker)
  setWorkerFeaturePanelVisibility(false);
  elements.badgeCard.classList.add("card-entrance-active");
  document.body.classList.add("card-animating");
  
  // Step 2: After 15 seconds (15000ms), smooth transition to top
  cardEntranceTimer = setTimeout(() => {
    if (!elements.badgeCard) return;
    
    // Remove entrance state and add transition-to-top state
    elements.badgeCard.classList.remove("card-entrance-active");
    elements.badgeCard.classList.add("card-transition-top");
    document.body.classList.remove("card-animating");
    document.body.classList.add("card-transitioned");
    
    // Scroll to show the card at top
    setTimeout(() => {
      if (elements.badgeCard) {
        elements.badgeCard.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      // Show feature sections with staggered fade-in
      showFeatureSectionsWithAnimation();
    }, 300);
  }, 15000); // 15 seconds delay
}

function showFeatureSectionsWithAnimation() {
  setWorkerFeaturePanelVisibility(true);

  // Animate in feature sections below the card
  const sections = getWorkerPageSections();
  sections.forEach((section, index) => {
    if (section && !section.classList.contains("hidden")) {
      // Reset animation
      section.classList.remove("feature-fade-in");
      // Trigger reflow to restart animation
      void section.offsetWidth;
      // Apply animation with stagger
      section.style.animationDelay = `${index * 150}ms`;
      section.classList.add("feature-fade-in");
    }
  });
}

function clearCardEntranceAnimation() {
  if (cardEntranceTimer) {
    clearTimeout(cardEntranceTimer);
    cardEntranceTimer = null;
  }
  if (elements.badgeCard) {
    elements.badgeCard.classList.remove("card-entrance-active", "card-transition-top");
  }
  setWorkerFeaturePanelVisibility(true);
  document.body.classList.remove("card-animating", "card-transitioned");
}

// ═════════════════════════════════════════════════════════════════════
// ── FEATURE: TIMESHEETS (Stundennachweise) ──
// ═════════════════════════════════════════════════════════════════════

// ── Zu-spät-Banner ────────────────────────────────────────────────────────
function showLateCheckInBanner(lateInfo, isVisitor) {
  // Remove any existing banner
  const existing = document.getElementById("lateCheckInBanner");
  if (existing) existing.remove();
  if (isVisitor || !lateInfo || !lateInfo.today) return;

  const minutes = lateInfo.minutes || 0;
  const minutesText = minutes > 0 ? ` (${minutes} ${t("lateMinutesUnit") || "Min."})` : "";
  const msg = (t("lateCheckInMessage") || "Du bist heute zu spät eingestempelt").replace("{minutes}", minutesText) + minutesText;

  const banner = document.createElement("div");
  banner.id = "lateCheckInBanner";
  banner.className = "late-checkin-banner";
  banner.setAttribute("role", "alert");
  banner.innerHTML = `
    <span class="late-banner-icon">⚠️</span>
    <span class="late-banner-text">${msg}</span>
    <button class="late-banner-close" aria-label="Schließen" onclick="this.parentElement.remove()">×</button>
  `;

  // Insert after the wallet card or at top of main content
  const walletCard = document.querySelector(".wallet-card");
  if (walletCard && walletCard.parentElement) {
    walletCard.parentElement.insertBefore(banner, walletCard.nextSibling);
  } else {
    const main = document.querySelector("main") || document.querySelector(".worker-main") || document.body;
    main.prepend(banner);
  }
}

function resetDailyInsights() {
  if (elements.dailyCheckinsValue) elements.dailyCheckinsValue.textContent = "0";
  if (elements.dailyCheckoutsValue) elements.dailyCheckoutsValue.textContent = "0";
  if (elements.dailyHoursValue) elements.dailyHoursValue.textContent = "0:00";
  if (elements.dailyBalanceValue) elements.dailyBalanceValue.textContent = t("dailyBalanceOpen");
}

function renderCompanyModeExperience(companyPreset, isVisitor) {
  if (!elements.companyModeCard) {
    return;
  }

  elements.companyModeCard.classList.toggle("hidden", isVisitor);
  if (isVisitor) {
    return;
  }

  const mode = normalizeCompanyBrandingPreset(companyPreset);
  const isIndustry = mode === "industry";
  const isPremium = mode === "premium";
  const leadKey = isIndustry
    ? "companyModeIndustryLead"
    : isPremium
      ? "companyModePremiumLead"
      : "companyModeConstructionLead";
  const itemKeys = isIndustry
    ? ["companyModeIndustryItem1", "companyModeIndustryItem2", "companyModeIndustryItem3"]
    : isPremium
      ? ["companyModePremiumItem1", "companyModePremiumItem2", "companyModePremiumItem3"]
      : ["companyModeConstructionItem1", "companyModeConstructionItem2", "companyModeConstructionItem3"];

  document.body.setAttribute("data-company-mode", mode);
  elements.companyModeCard.dataset.mode = mode;
  if (elements.companyModeTitle) {
    elements.companyModeTitle.textContent = t("companyModeTitle");
  }
  if (elements.companyModeLead) {
    elements.companyModeLead.textContent = t(leadKey);
  }
  if (elements.companyModeFeatureList) {
    elements.companyModeFeatureList.innerHTML = itemKeys.map((key) => `<li>${escapeHtmlBasic(t(key))}</li>`).join("");
  }
}

// ── 10-Second Card Showcase & Bottom Tab Navigation (Global Functions) ──────────────
function startCardShowcase() {
  // Hide everything except featured card
  const appShell = document.querySelector(".app-shell");
  if (appShell) {
    appShell.classList.add("showcase-mode");
  }

  // Hide header and nav
  const topPanel = document.getElementById("topPanel");
  const workerBottomNav = document.getElementById("workerBottomNav");
  if (topPanel) topPanel.classList.add("hidden");
  if (workerBottomNav) workerBottomNav.classList.add("hidden");

  // Show featured card fullscreen
  const dashboardCard = document.querySelector(".dashboard-featured-card");
  if (dashboardCard) {
    dashboardCard.style.display = "block";
  }

  // Clear any previous timeout
  if (showcaseTimeoutId) clearTimeout(showcaseTimeoutId);

  // Start 10-second countdown
  let countdownSeconds = 10;
  showcaseTimeoutId = setInterval(() => {
    countdownSeconds--;
    if (countdownSeconds <= 0) {
      clearInterval(showcaseTimeoutId);
      endCardShowcase();
    }
  }, 1000);
}

function endCardShowcase() {
  const appShell = document.querySelector(".app-shell");
  if (appShell) {
    appShell.classList.remove("showcase-mode");
  }

  // Show header and nav
  const topPanel = document.getElementById("topPanel");
  const workerBottomNav = document.getElementById("workerBottomNav");
  if (topPanel) topPanel.classList.remove("hidden");
  if (workerBottomNav) workerBottomNav.classList.remove("hidden");

  // Mark as loaded
  document.body.classList.add("worker-loaded");

  // Featured card and buttons visible again
  const dashboardCard = document.querySelector(".dashboard-featured-card");
  if (dashboardCard) {
    dashboardCard.style.display = "";
  }

  // Switch to Home tab by default (shows dashboard card + compact info)
  switchToTab("home");
}

function enforceUiVisibilityGuard() {
  const isLoaded = document.body.classList.contains("worker-loaded");
  const loginCard = document.getElementById("loginCard");
  const interiorIds = [
    "workerDashboard",
    "badgeCard",
    "homeCompactInfo",
    "leaveRequestCard",
    "timesheetCard",
    "documentsCard",
    "deploymentPlanCard",
    "workerBottomNav",
    "topPanel",
    "workerMenuCard",
    "sessionInfoCard",
    "actionsPanel",
    "routeCard",
    "companyModeCard",
    "dailyInsightsCard",
    "smartWorkHubCard",
    "workerPageNav",
    "workerHubPanel",
    "visitorCardContainer",
    "quickGateModeButton",
  ];

  if (!isLoaded) {
    document.body.classList.remove("wallet-immersive-sections-open", "card-animating", "card-transitioned");
    document.body.classList.add("worker-login-shell");
    interiorIds.forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.classList.add("hidden");
      el.style.setProperty("display", "none", "important");
    });
    document.querySelectorAll(".worker-hub-toggle-row").forEach((row) => {
      row.classList.add("hidden");
      row.style.setProperty("display", "none", "important");
    });
    if (loginCard) {
      loginCard.classList.remove("hidden");
      loginCard.style.removeProperty("display");
    }
    return;
  }

  document.body.classList.remove("worker-login-shell");

  if (loginCard) {
    loginCard.classList.add("hidden");
    loginCard.style.setProperty("display", "none", "important");
  }
  const topPanel = document.getElementById("topPanel");
  const bottomNav = document.getElementById("workerBottomNav");
  if (topPanel) topPanel.style.removeProperty("display");
  if (bottomNav) bottomNav.style.removeProperty("display");
}

function switchToTab(tabName) {
  // Backward compatibility: older flows still call "pass"
  if (tabName === "pass") tabName = "home";
  if (tabName === "request") tabName = "vacation";

  // Tab mode must win over legacy overview/focus modes.
  document.body.classList.remove("worker-tile-overview");

  // Safety: stale showcase mode can keep all interior panels hidden.
  const appShell = document.querySelector(".app-shell");
  if (appShell) {
    appShell.classList.remove("showcase-mode");
  }

  currentActiveTab = tabName;
  const isFeatureTab = tabName !== "home";
  document.body.classList.toggle("worker-feature-tab-active", isFeatureTab);
  document.body.classList.toggle("wallet-immersive-sections-open", isFeatureTab);
  if (isFeatureTab) {
    document.body.classList.remove("card-animating", "card-transitioned");
    if (cardEntranceTimer) {
      clearTimeout(cardEntranceTimer);
      cardEntranceTimer = null;
    }
    if (elements.badgeCard) {
      elements.badgeCard.classList.remove("card-entrance-active", "card-transition-top");
    }
  }

  const workerHubPanel = elements.workerHubPanel || document.getElementById("workerHubPanel");

  // Never allow tab navigation to reveal interior panels before login completes.
  if (!document.body.classList.contains("worker-loaded")) {
    const loginCard = document.getElementById("loginCard");
    const bottomNav = document.getElementById("workerBottomNav");
    const loginHidden = Boolean(loginCard && loginCard.classList.contains("hidden"));
    const navVisible = Boolean(bottomNav && !bottomNav.classList.contains("hidden"));

    // Recovery path: if the app UI is already visible, restore loaded state
    // so bottom tabs remain functional.
    if (loginHidden || navVisible) {
      document.body.classList.add("worker-loaded");
    } else {
      enforceUiVisibilityGuard();
      return;
    }
  }

  if (!document.body.classList.contains("worker-loaded")) {
    enforceUiVisibilityGuard();
    return;
  }

  // First enforce a strict clean state so legacy sections never leak into view.
  const managedPanels = [
    "routeCard",
    "sessionInfoCard",
    "companyModeCard",
    "dailyInsightsCard",
    "smartWorkHubCard",
    "workerMenuCard",
    "actionsPanel",
    "leaveRequestCard",
    "timesheetCard",
    "documentsCard",
    "deploymentPlanCard",
  ];
  managedPanels.forEach((panelId) => {
    const panel = document.getElementById(panelId);
    if (panel) {
      panel.classList.add("hidden");
      // Hard-stop legacy CSS from forcing hidden panels visible.
      panel.style.setProperty("display", "none", "important");
    }
  });

  // Update button states
  const navTabs = document.querySelectorAll(".nav-tab");
  navTabs.forEach((tab) => {
    const isActive = tab.dataset.tab === tabName;
    tab.classList.toggle("active", isActive);
    tab.setAttribute("aria-selected", isActive);
  });

  updateWorkerShellForTab(tabName);
  document.body.classList.remove("worker-tile-overview");
  activeWorkerPageTarget = "";

  // Show the correct panel based on tab
  if (tabName === "home") {
    if (workerHubPanel) {
      workerHubPanel.classList.add("hidden");
      workerHubPanel.style.setProperty("display", "none", "important");
    }
  } else if (tabName === "chat") {
    ensureWorkerFeatureHubVisible();
    showOnlyWorkerFeaturePanel("chatCard");
    applyWorkerChatTabLayout();
    refreshWorkerChatPanel();
    if (!workerPlanAllowsFeature("worker_chat")) {
      if (elements.workerChatMessages) {
        elements.workerChatMessages.innerHTML = `<p class="muted-info">${escapeHtmlBasic(planFeatureBlockedMessage("worker_chat"))}</p>`;
      }
    } else if (workerToken) {
      void loadWorkerChat();
    } else if (elements.workerChatMessages) {
      elements.workerChatMessages.innerHTML = `<p class="muted-info">${escapeHtmlBasic("Bitte zuerst mit Badge-ID und PIN anmelden.")}</p>`;
    }
  } else if (tabName === "vacation") {
    ensureWorkerFeatureHubVisible();
    showOnlyWorkerFeaturePanel("leaveRequestCard");
    if (!workerPlanAllowsFeature(WORKER_PLAN_TAB_FEATURES.vacation)) {
      renderWorkerListMessage(elements.leaveRequestList, planFeatureBlockedMessage(WORKER_PLAN_TAB_FEATURES.vacation), "error");
    } else if (workerToken) {
      void loadLeaveRequests();
    } else {
      renderWorkerListMessage(elements.leaveRequestList, "Bitte zuerst mit Badge-ID und PIN anmelden.");
    }
    scrollWorkerFeaturePanelIntoView("leaveRequestCard");
  } else if (tabName === "timesheet") {
    ensureWorkerFeatureHubVisible();
    showOnlyWorkerFeaturePanel("timesheetCard");
    if (!workerPlanAllowsFeature(WORKER_PLAN_TAB_FEATURES.timesheet)) {
      renderWorkerListMessage(elements.timesheetList, planFeatureBlockedMessage(WORKER_PLAN_TAB_FEATURES.timesheet), "error");
    } else if (workerToken) {
      void loadMyTimesheets();
    } else {
      renderWorkerListMessage(elements.timesheetList, "Bitte zuerst mit Badge-ID und PIN anmelden.");
    }
    scrollWorkerFeaturePanelIntoView("timesheetCard");
  } else if (tabName === "documents") {
    ensureWorkerFeatureHubVisible();
    showOnlyWorkerFeaturePanel("documentsCard");
    applyWorkerFeaturePanelLayout("documentsCard");
    if (!workerPlanAllowsFeature(WORKER_PLAN_TAB_FEATURES.documents)) {
      renderWorkerListMessage(elements.documentsList, planFeatureBlockedMessage(WORKER_PLAN_TAB_FEATURES.documents), "error");
    } else if (workerToken) {
      void loadMyDocuments();
    } else {
      renderWorkerListMessage(elements.documentsList, "Bitte zuerst mit Badge-ID und PIN anmelden.");
    }
    scrollWorkerFeaturePanelIntoView("documentsCard");
  }

  // Update hash for browser history
  const hashByTab = {
    home: "home",
    vacation: "urlaub",
    timesheet: "stunden",
    documents: "docs",
    chat: "chat",
    actions: "aktionen"
  };
  const nextHash = hashByTab[tabName];
  if (nextHash && window.location.hash !== `#${nextHash}`) {
    history.replaceState(null, "", `#${nextHash}`);
  }

  // Ensure bottom nav and top bar stay visible when switching tabs
  const bottomNav = document.getElementById("workerBottomNav");
  const topBar = document.getElementById("topPanel");
  if (bottomNav && document.body.classList.contains("worker-loaded")) {
    bottomNav.classList.remove("hidden");
    bottomNav.style.removeProperty("display");
  }
  if (topBar && document.body.classList.contains("worker-loaded")) {
    topBar.classList.remove("hidden");
    topBar.style.removeProperty("display");
  }

  // Scroll to top of content
  window.scrollTo(0, 0);

  updateFeatureTabPageNav(tabName);

  const workerFeatureMap = {
    home: "worker-badge",
    vacation: "worker-leave",
    timesheet: "worker-timesheets",
    documents: "worker-documents",
    deployment: "worker-deployment",
    actions: "worker-actions",
    chat: "worker-chat",
  };
  const trackId = workerFeatureMap[tabName] || `worker-${tabName}`;
  if (globalThis.BaupassUsage?.track) {
    globalThis.BaupassUsage.track(trackId, "worker-app");
  }
}

function initBottomTabNavigation() {
  if (bottomTabNavInitialized) return;
  bottomTabNavInitialized = true;

  const navContainer = document.getElementById("workerBottomNav");
  if (navContainer) {
    navContainer.addEventListener("click", (e) => {
      const clicked = e.target instanceof Element ? e.target.closest(".nav-tab") : null;
      if (!clicked) return;
      e.preventDefault();
      if (!document.body.classList.contains("worker-loaded")) {
        const loginCard = document.getElementById("loginCard");
        if (loginCard && loginCard.classList.contains("hidden")) {
          document.body.classList.add("worker-loaded");
        }
      }
      const tabName = clicked.getAttribute("data-tab") || "";
      if (tabName) {
        switchToTab(tabName);
      }
    });
  }

  const hashToTab = {
    "#home": "home",
    "#urlaub": "vacation",
    "#leave": "vacation",
    "#stunden": "timesheet",
    "#docs": "documents",
    "#documents": "documents",
    "#chat": "chat",
    "#einsatzplan": "deployment",
    "#deployment": "deployment",
  };

  const syncFromHash = () => {
    const hash = (window.location.hash || "").toLowerCase();
    if (hash === "#einsatzplan" || hash === "#deployment") {
      switchToTab("home");
      void openWorkerDeploymentPlanScreen();
      return;
    }
    const targetTab = hashToTab[hash] || "home";
    if (targetTab === "deployment") {
      switchToTab("home");
      void openWorkerDeploymentPlanScreen();
      return;
    }
    switchToTab(targetTab);
  };

  window.addEventListener("hashchange", syncFromHash);
}

// Sync worker data to dashboard featured card
function syncWorkerDataToDashboard(payload) {
  if (!payload) return;

  const dashboard = {
    name: document.getElementById("dashboardName"),
    role: document.getElementById("dashboardRole"),
    brandName: document.getElementById("dashboardBrandName"),
    badgeId: document.getElementById("dashboardBadgeId"),
    validUntil: document.getElementById("dashboardValidUntil"),
    companyName: document.getElementById("dashboardCompanyName"),
    subcompany: document.getElementById("dashboardSubcompany"),
    status: document.getElementById("dashboardStatus"),
    photo: document.getElementById("dashboardPhoto"),
    qr: document.getElementById("dashboardQr")
  };

  const worker = {
    name: document.getElementById("workerName"),
    role: document.getElementById("workerRole"),
    brandName: document.getElementById("workerBrandName"),
    badgeId: document.getElementById("workerBadgeId"),
    site: document.getElementById("workerSite"),
    validUntil: document.getElementById("workerValidUntil"),
    companyName: document.getElementById("companyName"),
    subcompany: document.getElementById("workerSubcompany"),
    status: document.getElementById("workerStatus"),
    photo: document.getElementById("workerPhoto"),
    qr: document.getElementById("workerQr")
  };

  // Copy text content
  if (worker.name && dashboard.name) {
    dashboard.name.textContent = worker.name.textContent;
  }
  if (worker.role && dashboard.role) {
    dashboard.role.textContent = worker.role.textContent;
  }
  if (worker.brandName && dashboard.brandName) {
    dashboard.brandName.textContent = worker.brandName.textContent;
  }
  if (worker.badgeId && dashboard.badgeId) {
    dashboard.badgeId.textContent = worker.badgeId.textContent;
  }
  if (worker.validUntil && dashboard.validUntil) {
    dashboard.validUntil.textContent = worker.validUntil.textContent;
  }
  if (worker.companyName && dashboard.companyName) {
    dashboard.companyName.textContent = worker.companyName.textContent;
  }
  if (worker.subcompany && dashboard.subcompany) {
    dashboard.subcompany.textContent = worker.subcompany.textContent;
    dashboard.subcompany.classList.toggle("hidden", worker.subcompany.classList.contains("hidden"));
  }
  if (worker.status && dashboard.status) {
    dashboard.status.textContent = worker.status.textContent;
    const normalizedStatus = worker.status.dataset?.status || "";
    if (normalizedStatus) {
      dashboard.status.dataset.status = normalizedStatus;
    } else {
      delete dashboard.status.dataset.status;
    }
  }

  const homeInfoStatus = document.getElementById("homeInfoStatus");
  const homeInfoSite = document.getElementById("homeInfoSite");
  const homeInfoCompany = document.getElementById("homeInfoCompany");
  const homeInfoValidUntil = document.getElementById("homeInfoValidUntil");
  if (homeInfoStatus && worker.status) {
    homeInfoStatus.textContent = worker.status.textContent || "Aktiv";
  }
  if (homeInfoSite && worker.site) {
    homeInfoSite.textContent = worker.site.textContent || "-";
    if (worker.site instanceof HTMLAnchorElement) {
      homeInfoSite.href = worker.site.getAttribute("href") || "#";
      if (worker.site.getAttribute("aria-disabled") === "true") {
        homeInfoSite.setAttribute("aria-disabled", "true");
      } else {
        homeInfoSite.removeAttribute("aria-disabled");
      }
    }
  }
  if (homeInfoCompany && worker.companyName) {
    homeInfoCompany.textContent = worker.companyName.textContent || t("companyFallback");
  }
  if (homeInfoValidUntil && worker.validUntil) {
    homeInfoValidUntil.textContent = worker.validUntil.textContent || "-";
  }

  // Copy image sources
  if (worker.photo && dashboard.photo && worker.photo.src) {
    dashboard.photo.src = worker.photo.src;
  }
  if (worker.qr && dashboard.qr && worker.qr.src) {
    dashboard.qr.src = worker.qr.src;
  }
}

// Sync QR countdown to dashboard
function syncDashboardQrCountdown() {
  const workerCountdownRing = document.getElementById("dqrCountdownRing");
  const dashboardCountdownRing = document.getElementById("dashboardDqrCountdownRing");
  
  const workerCountdownText = document.getElementById("dqrCountdownText");
  const dashboardCountdownText = document.getElementById("dashboardDqrCountdownText");

  if (workerCountdownRing && dashboardCountdownRing) {
    dashboardCountdownRing.style.strokeDashoffset = workerCountdownRing.style.strokeDashoffset;
  }

  if (workerCountdownText && dashboardCountdownText) {
    dashboardCountdownText.textContent = workerCountdownText.textContent;
  }
}

function updateDailyInsightsFromTimesheets(rows) {
  lastTimesheetRows = Array.isArray(rows) ? rows : [];
  if (!Array.isArray(rows) || rows.length === 0) {
    resetDailyInsights();
    updateSmartWorkHub(lastWorkerPayload, []);
    return;
  }

  const today = getLocalIsoDate();
  const todayRows = rows
    .filter((row) => getLocalIsoDateFromTimestamp(row.timestamp) === today)
    .sort((a, b) => String(a.timestamp || "") > String(b.timestamp || "") ? 1 : -1);

  if (todayRows.length === 0) {
    resetDailyInsights();
    updateSmartWorkHub(lastWorkerPayload, rows);
    return;
  }

  const sessions = pairWorkerPresenceSessions(todayRows);
  const totalMin = summarizeWorkerPresenceMinutes(todayRows);
  const checkins = todayRows.filter((row) => isAccessLogCheckIn(row.direction));
  const checkouts = todayRows.filter((row) => isAccessLogCheckOut(row.direction));
  const isOpen = sessions.some((session) => session.checkIn && !session.checkOut);
  const hours = Math.floor(totalMin / 60);
  const minutes = totalMin % 60;

  if (elements.dailyCheckinsValue) elements.dailyCheckinsValue.textContent = String(checkins.length);
  if (elements.dailyCheckoutsValue) elements.dailyCheckoutsValue.textContent = String(checkouts.length);
  if (elements.dailyHoursValue) elements.dailyHoursValue.textContent = `${hours}:${String(minutes).padStart(2, "0")}`;
  if (elements.dailyBalanceValue) elements.dailyBalanceValue.textContent = isOpen ? t("dailyBalanceOpen") : t("dailyBalanceClosed");
  updateSmartWorkHub(lastWorkerPayload, rows);
}

async function loadMyTimesheets() {
  if (!workerToken || !elements.timesheetList) return;
  elements.timesheetList.innerHTML = `<p class="muted-info">${t("timesheetLoading")}</p>`;
  try {
    const monthKey = getCurrentMonthKey();
    const data = await fetchJson(`${API_BASE}/my-timesheets?month=${encodeURIComponent(monthKey)}`, {
      headers: { Authorization: `Bearer ${workerToken}` }
    });
    const payload = normalizeWorkerTimesheetPayload(data);
    const rows = payload.rows;
    if (!Array.isArray(rows) || rows.length === 0) {
      elements.timesheetList.innerHTML = `
        <div class="timesheet-month-summary">
          <p class="timesheet-month-label">${escapeHtmlBasic(t("timesheetMonthTotalLabel"))}</p>
          <strong class="timesheet-month-value">${escapeHtmlBasic(formatWorkerHoursMinutes(0))} h</strong>
          <p class="timesheet-month-meta">${escapeHtmlBasic(formatMonthLabel(payload.month))}</p>
        </div>
        <p class="muted-info">${t("timesheetEmpty")}</p>`;
      resetDailyInsights();
      lastTimesheetRows = [];
      updateSmartWorkHub(lastWorkerPayload, []);
      return;
    }
    updateDailyInsightsFromTimesheets(rows);
    // Group by date
    const byDate = {};
    for (const row of rows) {
      const date = getLocalIsoDateFromTimestamp(row.timestamp);
      if (!byDate[date]) byDate[date] = [];
      byDate[date].push(row);
    }
    const dayGroups = Object.entries(byDate).sort(([aDate], [bDate]) => {
      if (aDate === bDate) return 0;
      return aDate < bDate ? 1 : -1;
    });
    const visibleDayGroups = timesheetCompactExpanded ? dayGroups : dayGroups.slice(0, 2);
    const daysHiddenCount = Math.max(0, dayGroups.length - visibleDayGroups.length);
    const monthSummaryMarkup = `
      <div class="timesheet-month-summary">
        <p class="timesheet-month-label">${escapeHtmlBasic(t("timesheetMonthTotalLabel"))}</p>
        <strong class="timesheet-month-value">${escapeHtmlBasic(formatWorkerHoursMinutes(payload.monthTotalMinutes))} h</strong>
        <p class="timesheet-month-meta">${escapeHtmlBasic(formatMonthLabel(payload.month))}</p>
      </div>`;

    const dayMarkup = visibleDayGroups.map(([date, entries]) => {
        const sessions = pairWorkerPresenceSessions(entries);
        const totalMin = summarizeWorkerPresenceMinutes(entries);
        const totalLabel = totalMin > 0 ? `${Math.floor(totalMin / 60)}:${String(totalMin % 60).padStart(2, "0")} h` : "";
        const sessionDurationByOut = new Map(
          sessions
            .filter((session) => session.checkOut && session.durationMinutes)
            .map((session) => [String(session.checkOut.timestamp || ""), session.durationMinutes])
        );
        return `<div class="timesheet-day">
        <div class="timesheet-date-row">
          <span class="timesheet-date">${formatDate(date)}</span>
          ${totalLabel ? `<span class="timesheet-total">${totalLabel}</span>` : ""}
        </div>
        ${entries.map((e) => {
          const isIn = isAccessLogCheckIn(e.direction);
          const sessionMinutes = sessionDurationByOut.get(String(e.timestamp || ""));
          const durationLabel = typeof sessionMinutes === "number"
            ? `<span class="entry-duration">${sessionMinutes} Min.</span>`
            : "";
          return `<div class="timesheet-entry ${isIn ? "entry-in" : "entry-out"}">
            <span class="entry-direction">${isIn ? t("timesheetDirectionIn") : t("timesheetDirectionOut")}</span>
            <span class="entry-time">${formatAccessTimeLocal(e.timestamp)}</span>
            ${durationLabel}
            ${e.gate ? `<span class="entry-gate">${e.gate}</span>` : ""}
          </div>`;
        }).join("")}
      </div>`;
      }).join("");

    const toggleMarkup = daysHiddenCount > 0 || timesheetCompactExpanded
      ? `<button id="timesheetCompactToggleBtn" class="ghost small-btn compact-list-toggle" type="button">${timesheetCompactExpanded ? t("compactShowLess") : `${t("compactShowMore")} (+${daysHiddenCount})`}</button>`
      : "";

    elements.timesheetList.innerHTML = monthSummaryMarkup + dayMarkup + toggleMarkup;

    const toggleBtn = document.querySelector("#timesheetCompactToggleBtn");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        timesheetCompactExpanded = !timesheetCompactExpanded;
        void loadMyTimesheets();
      });
    }
  } catch (error) {
    renderWorkerListMessage(elements.timesheetList, formatWorkerApiError(error), "error");
    resetDailyInsights();
    lastTimesheetRows = [];
    updateSmartWorkHub(lastWorkerPayload, []);
    console.warn("Could not load timesheets:", error);
  }
}

// ═════════════════════════════════════════════════════════════════════
// ── FEATURE: DEPLOYMENT PLAN (Einsatzplan / Monatsplan) ──
// ═════════════════════════════════════════════════════════════════════

let deploymentPlanViewYear = null;
let deploymentPlanViewMonth = null;
let deploymentDeclinePendingDate = "";
let deploymentPlanCachedDays = [];
let deploymentPlanPublished = false;
let deploymentPlanCanRespond = false;

function deploymentDayIso(day) {
  return String(day?.date || "").slice(0, 10);
}

function deploymentDayLocationValue(day) {
  return String(day?.location || "").trim();
}

function deploymentDayIsExplicitFreeLocation(location) {
  const normalized = String(location || "").trim().toLowerCase();
  if (!normalized) {
    return true;
  }
  const freeMarkers = new Set([
    "frei",
    "free",
    "off",
    "aus",
    "-",
    "–",
    "—",
    "x",
    "urlaub",
    "free day",
    "kein einsatz",
    "no assignment",
    "off day",
  ]);
  return freeMarkers.has(normalized);
}

function deploymentDayHasAssignment(day) {
  const location = deploymentDayLocationValue(day);
  if (deploymentDayIsExplicitFreeLocation(location)) {
    return false;
  }
  return Boolean(location);
}

function deploymentDayIsDeclinable(day) {
  if (deploymentDayIsFree(day)) {
    return false;
  }
  if (!deploymentPlanCanRespond) return false;
  if (!deploymentDayHasAssignment(day)) return false;
  if (String(day?.workerResponse || "") === "declined") return false;
  const iso = deploymentDayIso(day);
  if (!iso) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(target.getTime())) return false;
  return target >= today;
}

function deploymentDayIsDeclined(day) {
  return String(day?.workerResponse || "") === "declined" || Boolean(day?.isDeclined);
}

async function postDeploymentDayResponse(date, action, reason = "") {
  return fetchJson(`${API_BASE}/deployment-plan/day-response`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${workerToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ date, action, reason }),
  });
}

function openDeploymentDeclineModal(day) {
  const modal = document.getElementById("deploymentDeclineModal");
  const dateEl = document.getElementById("deploymentDeclineModalDate");
  const reasonEl = document.getElementById("deploymentDeclineReason");
  if (!modal || !dateEl) return;
  setDeploymentDeclineModalError("");
  deploymentDeclinePendingDate = deploymentDayIso(day);
  const label = [day.weekday, deploymentDayIso(day)].filter(Boolean).join(" · ");
  dateEl.textContent = label;
  if (reasonEl) {
    reasonEl.value = "";
    reasonEl.placeholder = t("deploymentPlanDeclineReasonPh");
  }
  modal.classList.remove("hidden");
}

function closeDeploymentDeclineModal() {
  deploymentDeclinePendingDate = "";
  setDeploymentDeclineModalError("");
  const confirmBtn = document.getElementById("deploymentDeclineConfirm");
  if (confirmBtn) {
    confirmBtn.disabled = false;
    confirmBtn.removeAttribute("aria-busy");
  }
  document.getElementById("deploymentDeclineModal")?.classList.add("hidden");
}

function formatDeploymentShiftTime(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (raw.includes("T") && raw.length >= 16) return raw.slice(11, 16);
  if (/^\d{1,2}:\d{2}/.test(raw)) return raw.slice(0, 5);
  return raw;
}

function deploymentDayColorStyle(day) {
  const color = String(day?.dayColor || day?.day_color || "").trim();
  if (!/^#[0-9a-f]{6}$/i.test(color)) return "";
  return `--dep-day-color:${color};border-color:${color};background:color-mix(in srgb, ${color} 16%, var(--card, #fff))`;
}

function renderDeploymentPlanCalendar(days) {
  const headers = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
  const first = days[0];
  const pad = first && Number.isFinite(first.weekdayIndex) ? first.weekdayIndex : 0;
  const headHtml = headers.map((label) => `<span class="deployment-plan-calendar-head-cell">${label}</span>`).join("");
  const padHtml = Array.from({ length: pad }, () => `<span class="deployment-plan-calendar-pad" aria-hidden="true"></span>`).join("");
  const cells = days.map((day) => renderDeploymentPlanDayRow(day)).join("");
  return `<div class="deployment-plan-calendar"><div class="deployment-plan-calendar-head">${headHtml}</div><div class="deployment-plan-calendar-grid">${padHtml}${cells}</div></div>`;
}

function deploymentDayIsFree(day) {
  if (deploymentDayIsDeclined(day)) {
    return false;
  }
  if (day?.isFree === true) {
    return true;
  }
  return !deploymentDayHasAssignment(day);
}

function renderDeploymentPlanDayRow(day) {
  const location = deploymentDayLocationValue(day);
  const shiftStart = formatDeploymentShiftTime(day.shiftStart);
  const shiftEnd = formatDeploymentShiftTime(day.shiftEnd);
  const notes = String(day.notes || "").trim();
  const declineReason = String(day.declineReason || "").trim();
  const isFreeDay = deploymentDayIsFree(day);
  const timeText =
    shiftStart && shiftEnd
      ? tf("deploymentPlanTimeRange", { start: shiftStart, end: shiftEnd })
      : shiftStart || shiftEnd || "";
  const dateParts = deploymentDayIso(day).split("-");
  const dayNum = dateParts[2] || day.date;
  const declined = deploymentDayIsDeclined(day);
  const declinable = !isFreeDay && deploymentDayIsDeclinable(day);
  const colorStyle = deploymentDayColorStyle(day);
  const classes = [
    "deployment-plan-day",
    "deployment-plan-calendar-cell",
    isFreeDay ? "is-free" : "",
    day.isWeekend && !isFreeDay ? "is-weekend" : "",
    !isFreeDay && location ? "has-assignment" : "",
    declined ? "is-declined" : "",
  ]
    .filter(Boolean)
    .join(" ");

  let actionsHtml = "";
  if (!isFreeDay && declined) {
    actionsHtml = `
      <div class="deployment-plan-day-actions">
        <button type="button" class="ghost small-btn" data-dep-undo="${escapeHtmlBasic(deploymentDayIso(day))}">${escapeHtmlBasic(t("deploymentPlanUndoDeclineBtn"))}</button>
      </div>`;
  } else if (!isFreeDay && declinable) {
    actionsHtml = `
      <div class="deployment-plan-day-actions">
        <button type="button" class="ghost small-btn" data-dep-decline="${escapeHtmlBasic(deploymentDayIso(day))}">${escapeHtmlBasic(t("deploymentPlanDeclineBtn"))}</button>
      </div>`;
  }

  const statusHtml = declined
    ? `<div class="deployment-plan-day-status">${escapeHtmlBasic(t("deploymentPlanDeclinedBadge"))}${
        declineReason
          ? ` · ${escapeHtmlBasic(tf("deploymentPlanDeclineReasonShow", { reason: declineReason }))}`
          : ""
      }</div>`
    : "";

  const locationLabel = isFreeDay
    ? t("deploymentPlanDayFree")
    : (location || t("deploymentPlanNoLocation"));

  return `
    <article class="${classes}" data-dep-date="${escapeHtmlBasic(deploymentDayIso(day))}"${colorStyle ? ` style="${colorStyle}"` : ""}>
      <div class="deployment-plan-day-head">
        <div class="deployment-plan-day-date">${escapeHtmlBasic(dayNum)}</div>
        <div class="deployment-plan-day-weekday">${escapeHtmlBasic(day.weekday || "")}</div>
      </div>
      <div class="deployment-plan-day-body">
        <div class="deployment-plan-day-location">${escapeHtmlBasic(locationLabel)}</div>
        ${timeText && !isFreeDay ? `<div class="deployment-plan-day-time">${escapeHtmlBasic(timeText)}</div>` : ""}
        ${notes ? `<div class="deployment-plan-day-notes">${escapeHtmlBasic(notes)}</div>` : ""}
        ${statusHtml}
      </div>
      ${actionsHtml}
    </article>
  `;
}

function bindDeploymentPlanInteractions() {
  const list = elements.deploymentPlanList;
  if (!list || bindDeploymentPlanInteractions._done) return;
  bindDeploymentPlanInteractions._done = true;

  list.addEventListener("click", (event) => {
    const declineBtn = event.target.closest("[data-dep-decline]");
    const undoBtn = event.target.closest("[data-dep-undo]");
    if (declineBtn) {
      const iso = declineBtn.getAttribute("data-dep-decline") || "";
      const day =
        deploymentPlanCachedDays.find((entry) => deploymentDayIso(entry) === iso) || {
          date: iso,
          weekday: "",
        };
      openDeploymentDeclineModal(day);
      return;
    }
    if (undoBtn) {
      const iso = undoBtn.getAttribute("data-dep-undo") || "";
      if (!iso) return;
      void (async () => {
        try {
          await postDeploymentDayResponse(iso, "undo");
          showWorkerNotice(t("deploymentPlanUndoDone"));
          await loadDeploymentPlan();
          void refreshHomeDeploymentTeaser().catch(() => {});
        } catch (error) {
          showWorkerNotice(formatWorkerApiError(error));
        }
      })();
    }
  });

  document.getElementById("deploymentDeclineCancel")?.addEventListener("click", closeDeploymentDeclineModal);
  document.getElementById("deploymentDeclineModal")?.addEventListener("click", (event) => {
    if (event.target?.id === "deploymentDeclineModal") closeDeploymentDeclineModal();
  });
  document.getElementById("deploymentDeclineConfirm")?.addEventListener("click", () => {
    const iso = deploymentDeclinePendingDate;
    if (!iso) return;
    const reason = String(document.getElementById("deploymentDeclineReason")?.value || "").trim();
    const confirmBtn = document.getElementById("deploymentDeclineConfirm");
    void (async () => {
      setDeploymentDeclineModalError("");
      if (confirmBtn) {
        confirmBtn.disabled = true;
        confirmBtn.setAttribute("aria-busy", "true");
      }
      try {
        await postDeploymentDayResponse(iso, "decline", reason);
        closeDeploymentDeclineModal();
        showWorkerNotice(t("deploymentPlanDeclineDone"));
        await loadDeploymentPlan();
        void refreshHomeDeploymentTeaser().catch(() => {});
      } catch (error) {
        const message = formatWorkerApiError(error);
        setDeploymentDeclineModalError(message);
        showWorkerNotice(message);
      } finally {
        if (confirmBtn) {
          confirmBtn.disabled = false;
          confirmBtn.removeAttribute("aria-busy");
        }
      }
    })();
  });
}

function monthLabelFromParts(year, month, lang) {
  try {
    return new Date(year, month - 1, 1).toLocaleDateString(lang || getWorkerLang(), {
      month: "long",
      year: "numeric",
    });
  } catch {
    return `${month.toString().padStart(2, "0")}/${year}`;
  }
}

function parseDeploymentMonthValue(value) {
  const raw = String(value || "").trim();
  const match = /^(\d{4})-(\d{2})$/.exec(raw);
  if (!match) return null;
  return { year: Number(match[1]), month: Number(match[2]) };
}

function populateDeploymentMonthSelect(months, selectedYear, selectedMonth) {
  const select = elements.deploymentPlanMonthSelect;
  if (!select) return;
  const lang = getWorkerLang();
  const options = Array.isArray(months) ? months : [];
  if (!options.length) {
    const now = new Date();
    options.push({ year: now.getFullYear(), month: now.getMonth() + 1 });
  }
  select.innerHTML = options
    .map((item) => {
      const year = Number(item.year);
      const month = Number(item.month);
      const value = `${year}-${String(month).padStart(2, "0")}`;
      const label = monthLabelFromParts(year, month, lang);
      const selected = year === selectedYear && month === selectedMonth ? " selected" : "";
      return `<option value="${escapeHtmlBasic(value)}"${selected}>${escapeHtmlBasic(label)}</option>`;
    })
    .join("");
}

async function openWorkerDeploymentPlanScreen(year = null, month = null) {
  if (!workerToken) {
    showWorkerNotice("Bitte zuerst mit Badge-ID und PIN anmelden.");
    return;
  }
  if (!workerPlanAllowsFeature("deployment_plan")) {
    showWorkerNotice(planFeatureBlockedMessage("deployment_plan"));
    return;
  }
  const now = new Date();
  deploymentPlanViewYear = year || deploymentPlanViewYear || now.getFullYear();
  deploymentPlanViewMonth = month || deploymentPlanViewMonth || now.getMonth() + 1;
  document.body.classList.add("worker-feature-tab-active", "worker-page-focus");
  ensureWorkerFeatureHubVisible();
  showOnlyWorkerFeaturePanel("deploymentPlanCard");
  applyWorkerPageView("deploymentPlanCard");
  const card = elements.deploymentPlanCard || document.getElementById("deploymentPlanCard");
  if (card) {
    card.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  if (window.location.hash !== "#einsatzplan") {
    history.replaceState(null, "", "#einsatzplan");
  }
  await loadDeploymentPlan();
}

async function refreshHomeDeploymentTeaser() {
  const teaser = document.getElementById("homeDeploymentTeaser");
  const titleEl = document.getElementById("homeDeploymentTeaserTitle");
  const metaEl = document.getElementById("homeDeploymentTeaserMeta");
  if (!teaser || !titleEl || !metaEl) return;
  if (!workerToken || !workerPlanAllowsFeature("deployment_plan")) {
    teaser.classList.add("hidden");
    return;
  }
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth() + 1;
  const todayIso = `${year}-${String(month).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const lang = getWorkerLang();
  try {
    const data = await fetchJson(
      `${API_BASE}/deployment-plan?year=${encodeURIComponent(year)}&month=${encodeURIComponent(month)}&lang=${encodeURIComponent(lang)}`,
      { headers: { Authorization: `Bearer ${workerToken}` } },
    );
    if (!data?.ok || data?.visible === false) {
      teaser.classList.add("hidden");
      return;
    }
    const days = Array.isArray(data.days) ? data.days : [];
    const today = days.find((day) => String(day.date || "").slice(0, 10) === todayIso);
    if (!data?.published) {
      const location = String(today?.location || "").trim();
      const shiftStart = String(today?.shiftStart || "").trim();
      const shiftEnd = String(today?.shiftEnd || "").trim();
      if (location || shiftStart || shiftEnd) {
        titleEl.textContent = location || t("deploymentPlanNoLocation");
        const timeText =
          shiftStart && shiftEnd
            ? tf("deploymentPlanTimeRange", { start: shiftStart, end: shiftEnd })
            : shiftStart || shiftEnd || "";
        metaEl.textContent = [today?.weekday || "", timeText, t("deploymentPlanDraftShort")]
          .filter(Boolean)
          .join(" · ");
      } else {
        titleEl.textContent = t("deploymentPlanHomeDraft");
        metaEl.textContent = t("deploymentPlanHomeOpen");
      }
      teaser.classList.remove("hidden");
      return;
    }
    const location = deploymentDayLocationValue(today || {});
    const shiftStart = String(today?.shiftStart || "").trim();
    const shiftEnd = String(today?.shiftEnd || "").trim();
    const declinedToday = today && deploymentDayIsDeclined(today);
    const freeToday = today && deploymentDayIsFree(today);
    teaser.classList.toggle("is-declined", Boolean(declinedToday));
    teaser.classList.toggle("is-free", Boolean(freeToday));
    if (declinedToday) {
      titleEl.textContent = t("deploymentPlanHomeDeclined");
      metaEl.textContent = t("deploymentPlanHomeOpen");
    } else if (freeToday) {
      titleEl.textContent = t("deploymentPlanHomeFree");
      metaEl.textContent = [today?.weekday || "", t("deploymentPlanDayFree")].filter(Boolean).join(" · ");
    } else {
      titleEl.textContent = location || t("deploymentPlanNoLocation");
      const timeText =
        shiftStart && shiftEnd
          ? tf("deploymentPlanTimeRange", { start: shiftStart, end: shiftEnd })
          : shiftStart || shiftEnd || "";
      metaEl.textContent = [today?.weekday || "", timeText].filter(Boolean).join(" · ");
    }
    teaser.classList.remove("hidden");
  } catch {
    teaser.classList.add("hidden");
  }
}

async function loadDeploymentPlan() {
  if (!workerToken || !elements.deploymentPlanList) return;
  if (!workerPlanAllowsFeature("deployment_plan")) {
    renderWorkerListMessage(elements.deploymentPlanList, planFeatureBlockedMessage("deployment_plan"), "error");
    return;
  }

  const select = elements.deploymentPlanMonthSelect;
  if (select?.value) {
    const parsed = parseDeploymentMonthValue(select.value);
    if (parsed) {
      deploymentPlanViewYear = parsed.year;
      deploymentPlanViewMonth = parsed.month;
    }
  }
  const year = deploymentPlanViewYear || new Date().getFullYear();
  const month = deploymentPlanViewMonth || new Date().getMonth() + 1;
  const lang = getWorkerLang();

  elements.deploymentPlanList.innerHTML = `<p class="muted-info">${t("deploymentPlanLoading")}</p>`;
  if (elements.deploymentPlanMeta) elements.deploymentPlanMeta.textContent = "";

  try {
    const data = await fetchJson(
      `${API_BASE}/deployment-plan?year=${encodeURIComponent(year)}&month=${encodeURIComponent(month)}&lang=${encodeURIComponent(lang)}`,
      { headers: { Authorization: `Bearer ${workerToken}` } }
    );

    const months = Array.isArray(data?.months) ? data.months : [];
    populateDeploymentMonthSelect(months, year, month);

    deploymentPlanPublished = Boolean(data?.published);
    deploymentPlanCanRespond =
      Boolean(data?.canRespond) ||
      deploymentPlanPublished ||
      (Boolean(data?.visible) && Number(data?.scheduledDayCount || 0) > 0);

    if (!data?.ok || data?.visible === false) {
      const message =
        data?.error === "no_plan" ? t("deploymentPlanEmpty") : t("deploymentPlanEmpty");
      elements.deploymentPlanList.innerHTML = `<p class="muted-info">${escapeHtmlBasic(message)}</p>`;
      if (elements.deploymentPlanMeta) {
        elements.deploymentPlanMeta.textContent = "";
      }
      if (elements.deploymentPlanPdfBtn) elements.deploymentPlanPdfBtn.disabled = true;
      if (elements.deploymentPlanPrintBtn) elements.deploymentPlanPrintBtn.disabled = true;
      return;
    }

    if (elements.deploymentPlanPdfBtn) {
      elements.deploymentPlanPdfBtn.disabled = !deploymentPlanPublished;
    }
    if (elements.deploymentPlanPrintBtn) {
      elements.deploymentPlanPrintBtn.disabled = !deploymentPlanPublished;
    }

    const sentAt = data.sentAt ? formatNotificationTimestamp(data.sentAt) : "";
    const scheduled = Number(data.scheduledDayCount || 0);
    const declined = Number(data.declinedDayCount || 0);
    const metaParts = [
      !deploymentPlanPublished && deploymentPlanCanRespond ? t("deploymentPlanDraftBanner") : "",
      !deploymentPlanPublished && !deploymentPlanCanRespond ? t("deploymentPlanNotPublished") : "",
      tf("deploymentPlanScheduledDays", { count: scheduled }),
      declined > 0 ? tf("deploymentPlanDeclinedDays", { count: declined }) : "",
      sentAt ? tf("deploymentPlanSentAt", { date: sentAt }) : "",
    ].filter(Boolean);
    if (elements.deploymentPlanMeta) {
      elements.deploymentPlanMeta.textContent = metaParts.join(" · ");
    }

    const days = Array.isArray(data.days) ? data.days : [];
    deploymentPlanCachedDays = days;
    elements.deploymentPlanList.innerHTML = days.length
      ? renderDeploymentPlanCalendar(days)
      : `<p class="muted-info">${escapeHtmlBasic(t("deploymentPlanEmpty"))}</p>`;
  } catch (error) {
    renderWorkerListMessage(elements.deploymentPlanList, formatWorkerApiError(error), "error");
    if (elements.deploymentPlanPdfBtn) elements.deploymentPlanPdfBtn.disabled = true;
    if (elements.deploymentPlanPrintBtn) elements.deploymentPlanPrintBtn.disabled = true;
  }
}

async function openDeploymentPlanPdf(shouldPrint = false) {
  if (!workerToken) return;
  const year = deploymentPlanViewYear || new Date().getFullYear();
  const month = deploymentPlanViewMonth || new Date().getMonth() + 1;
  const lang = getWorkerLang();
  try {
    const response = await fetch(
      `${API_BASE}/deployment-plan/pdf?year=${encodeURIComponent(year)}&month=${encodeURIComponent(month)}&lang=${encodeURIComponent(lang)}`,
      { headers: { Authorization: `Bearer ${workerToken}` } }
    );
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    if (shouldPrint) {
      const frame = document.createElement("iframe");
      frame.className = "hidden-control";
      frame.src = url;
      document.body.appendChild(frame);
      frame.onload = () => {
        try {
          frame.contentWindow?.focus();
          frame.contentWindow?.print();
        } catch {
          window.open(url, "_blank", "noopener");
        }
        setTimeout(() => {
          frame.remove();
          URL.revokeObjectURL(url);
        }, 60000);
      };
      return;
    }
    window.open(url, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 120000);
  } catch (error) {
    showWorkerNotice(formatWorkerApiError(error));
  }
}

// ═════════════════════════════════════════════════════════════════════
// ── FEATURE: DOCUMENTS (Meine Dokumente) ──
// ═════════════════════════════════════════════════════════════════════

function workerDocTypeLabel(doc) {
  if (doc?.label) return doc.label;
  const raw = String(doc?.doc_type || "").trim().toLowerCase();
  const key = `docType${raw.charAt(0).toUpperCase()}${raw.slice(1)}`;
  return t(key) || raw.replace(/_/g, " ");
}

async function downloadWorkerDocument(docId, filename) {
  const response = await fetch(`${API_BASE}/my-documents/${encodeURIComponent(docId)}/download`, {
    headers: { Authorization: `Bearer ${workerToken}` },
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename || "dokument.pdf";
  anchor.click();
  URL.revokeObjectURL(url);
}

async function ensureWorkerChatThread(forceRefresh = false) {
  if (!workerToken) {
    return "";
  }
  if (workerChatThreadId && !forceRefresh) {
    return workerChatThreadId;
  }
  const authHeaders = buildWorkerAuthHeaders();
  try {
    const threadsPayload = await fetchJson(`${API_BASE}/chat/threads`, {
      headers: authHeaders,
    });
    const threads = Array.isArray(threadsPayload?.threads) ? threadsPayload.threads : [];
    if (threads.length) {
      const sorted = [...threads].sort((left, right) =>
        String(right.last_message_at || right.updated_at || "").localeCompare(
          String(left.last_message_at || left.updated_at || "")
        )
      );
      const existing = sorted.find((row) => String(row.subject || "general") === "general") || sorted[0];
      workerChatThreadId = String(existing?.id || existing?.threadId || "");
      if (workerChatThreadId) {
        return workerChatThreadId;
      }
    }
  } catch {
    // fall back to creating a thread
  }
  try {
    const created = await fetchJson(`${API_BASE}/chat/threads`, {
      method: "POST",
      headers: buildWorkerAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ subject: "general" }),
    });
    workerChatThreadId = String(created?.threadId || "");
    if (workerChatThreadId) {
      return workerChatThreadId;
    }
  } catch {
    // ignore create errors
  }
  return workerChatThreadId;
}

function renderWorkerChatAttachmentHtml(attachments) {
  if (!Array.isArray(attachments) || !attachments.length) {
    return "";
  }
  return `<div class="worker-chat-attachments">${attachments
    .map((attachment) => {
      const id = escapeHtmlBasic(String(attachment.id || ""));
      const name = escapeHtmlBasic(String(attachment.filename || t("workerChatDownload")));
      return `<button type="button" class="worker-chat-attachment-btn" data-attachment-id="${id}" data-filename="${name}">⬇ ${escapeHtmlBasic(t("workerChatDownload"))}: ${name}</button>`;
    })
    .join("")}</div>`;
}

function renderWorkerChatMessages(messages) {
  if (!elements.workerChatMessages) {
    return;
  }
  if (!Array.isArray(messages) || !messages.length) {
    elements.workerChatMessages.innerHTML = `<p class="muted-info">${t("workerChatEmpty")}</p>`;
    return;
  }
  elements.workerChatMessages.innerHTML = messages
    .map((msg) => {
      const side = workerChatSenderSide(msg);
      const senderLabel = side === "mine" ? t("workerChatFromYou") : getWorkerBrandTitle();
      const body = escapeHtmlBasic(String(msg.body || ""));
      const attachHtml = renderWorkerChatAttachmentHtml(msg.attachments);
      const bodyHtml = body ? `<div class="worker-chat-body">${body}</div>` : "";
      const time = formatChatTimestamp(msg.createdAt || msg.created_at);
      const readLabel = workerChatReadLabel(msg, side);
      const read = msg.readByRecipient === true || msg.read_by_recipient === true;
      const messageId = String(msg.id || "");
      const deleteHtml = side === "mine" && messageId && !read
        ? `<button type="button" class="worker-chat-delete-btn" data-chat-delete-id="${escapeHtmlBasic(messageId)}" aria-label="${escapeHtmlBasic(t("workerChatDelete"))}">🗑</button>`
        : "";
      const readHtml = readLabel
        ? `<span class="worker-chat-read${read ? " is-read" : ""}">${escapeHtmlBasic(readLabel)}</span>`
        : "";
      return `
        <div class="worker-chat-row is-${side}">
          <span class="worker-chat-sender">${escapeHtmlBasic(senderLabel)}</span>
          <div class="worker-chat-bubble is-${side}">
            ${bodyHtml}
            ${attachHtml}
            <div class="worker-chat-meta">
              ${time ? `<span class="worker-chat-time">${escapeHtmlBasic(time)}</span>` : ""}
              ${readHtml}
              ${deleteHtml}
            </div>
          </div>
        </div>
      `;
    })
    .join("");
  bindWorkerChatMessageActions();
  elements.workerChatMessages.scrollTop = elements.workerChatMessages.scrollHeight;
}

async function downloadWorkerChatAttachment(attachmentId, filename) {
  if (!workerToken || !attachmentId) {
    return;
  }
  try {
    const response = await fetch(`${API_BASE}/chat/attachments/${encodeURIComponent(attachmentId)}/download`, {
      headers: buildWorkerAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename || "download";
    anchor.rel = "noopener";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    showWorkerNotice(formatWorkerApiError(error));
  }
}

async function uploadWorkerChatAttachment(threadId, messageId, file) {
  const form = new FormData();
  form.append("message_id", messageId);
  form.append("file", file);
  form.append("doc_type", "sonstiges");
  const response = await fetch(`${API_BASE}/chat/threads/${encodeURIComponent(threadId)}/attachments`, {
    method: "POST",
    headers: buildWorkerAuthHeaders(),
    body: form,
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const error = new Error(payload?.message || payload?.error || `HTTP ${response.status}`);
    error.code = payload?.error || "";
    error.payload = payload;
    throw error;
  }
  return payload;
}

async function loadWorkerChat(options = {}) {
  const quiet = Boolean(options.quiet);
  syncWorkerChatComposeRefs();
  if (!getWorkerAuthorizationValue() || !elements.workerChatMessages) {
    return;
  }
  if (!quiet) {
    elements.workerChatMessages.innerHTML = `<p class="muted-info">${t("workerChatLoading")}</p>`;
  }
  try {
    const threadId = await ensureWorkerChatThread();
    if (!threadId) {
      if (!quiet) {
        elements.workerChatMessages.innerHTML = `<p class="muted-info">${t("workerChatUnavailable")}</p>`;
      }
      return;
    }
    const payload = await fetchJson(`${API_BASE}/chat/threads/${encodeURIComponent(threadId)}/messages`, {
      headers: buildWorkerAuthHeaders(),
    });
    renderWorkerChatMessages(payload?.messages || []);
  } catch (error) {
    if (error?.code === "thread_not_found") {
      workerChatThreadId = "";
    }
    if (!quiet) {
      elements.workerChatMessages.innerHTML = `<p class="muted-info">${escapeHtmlBasic(formatWorkerApiError(error))}</p>`;
    }
  }
}

function stopWorkerChatPolling() {
  if (workerChatPollTimer) {
    clearInterval(workerChatPollTimer);
    workerChatPollTimer = null;
  }
}

function startWorkerChatPolling() {
  stopWorkerChatPolling();
  if (!workerToken || !workerPlanAllowsFeature("worker_chat")) {
    return;
  }
  workerChatPollTimer = setInterval(() => {
    if (!workerToken) {
      return;
    }
    void loadWorkerChat({ quiet: true });
  }, 5000);
}

async function sendWorkerChatMessage() {
  syncWorkerChatComposeRefs();
  if (!getWorkerAuthorizationValue()) {
    showWorkerNotice(t("enterBadgeId"));
    return;
  }
  const input = elements.workerChatInput || document.getElementById("workerChatInput");
  if (!input) {
    showWorkerNotice(t("workerChatUnavailable"));
    return;
  }
  elements.workerChatInput = input;
  const fileInput = elements.workerChatFileInput || document.getElementById("workerChatFileInput");
  const file = fileInput?.files?.[0] || null;
  let body = String(input.value || "").trim();
  if (!body && file) {
    body = t("workerChatAttachmentOnly");
  }
  if (!body && !file) {
    return;
  }
  const postMessage = async (threadId) => fetchJson(`${API_BASE}/chat/threads/${encodeURIComponent(threadId)}/messages`, {
    method: "POST",
    headers: buildWorkerAuthHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ body }),
  });
  const allowed = workerPlanAllowsFeature("worker_chat");
  try {
    let threadId = await ensureWorkerChatThread();
    if (!threadId) {
      showWorkerNotice(t("workerChatUnavailable"));
      return;
    }
    setWorkerChatComposeEnabled(false);
    let messageId = "";
    try {
      const sent = await postMessage(threadId);
      messageId = String(sent?.message?.id || "");
    } catch (error) {
      if (error?.code === "thread_not_found" || error?.code === "chat_send_failed") {
        workerChatThreadId = "";
        threadId = await ensureWorkerChatThread(true);
        if (!threadId) {
          throw error;
        }
        const sent = await postMessage(threadId);
        messageId = String(sent?.message?.id || "");
      } else {
        throw error;
      }
    }
    if (file && messageId) {
      await uploadWorkerChatAttachment(threadId, messageId, file);
    }
    input.value = "";
    if (fileInput) {
      fileInput.value = "";
      updateWorkerChatFileHint();
    }
    await loadWorkerChat();
    showWorkerNotice(file ? t("workerChatDocumentSubmitted") : t("workerChatSent"));
  } catch (error) {
    const message = formatWorkerApiError(error);
    showWorkerNotice(message);
    if (elements.workerChatMessages) {
      elements.workerChatMessages.innerHTML = `<p class="muted-info worker-chat-error">${escapeHtmlBasic(message)}</p>`;
    }
  } finally {
    setWorkerChatComposeEnabled(allowed);
  }
}

async function openWorkerChatScreen() {
  if (!workerToken) {
    showWorkerNotice(t("enterBadgeId"));
    return;
  }
  if (!workerPlanAllowsFeature("worker_chat")) {
    showWorkerNotice(planFeatureBlockedMessage("worker_chat"));
    return;
  }
  switchToTab("chat");
  if (elements.workerChatInput) {
    elements.workerChatInput.focus();
  }
}

async function loadMyDocuments() {
  if (!workerToken || !elements.documentsList) return;
  elements.documentsList.innerHTML = `<p class="muted-info">${t("documentsLoading")}</p>`;
  try {
    const lang = getWorkerLang();
    const rows = await fetchJson(`${API_BASE}/my-documents?lang=${encodeURIComponent(lang)}`, {
      headers: { Authorization: `Bearer ${workerToken}` }
    });
    lastDocumentRows = Array.isArray(rows) ? rows : [];
    if (!Array.isArray(rows) || rows.length === 0) {
      elements.documentsList.innerHTML = `<p class="muted-info">${t("documentsEmpty")}</p>`;
      updateSmartWorkHub(lastWorkerPayload, lastTimesheetRows);
      return;
    }
    const today = getLocalIsoDate();
    const soon = new Date(); soon.setDate(soon.getDate() + 30);
    const soonStr = getLocalIsoDate(soon);

    // Ablauf-Warnung Banner
    const expiringSoon = rows.filter(d => d.expiry_date && d.expiry_date > today && d.expiry_date <= soonStr);
    const expired = rows.filter(d => d.expiry_date && d.expiry_date <= today);
    let warningBanner = "";
    if (expired.length > 0) {
      warningBanner += `<div class="doc-warning-banner doc-warning-expired">⚠️ ${expired.length} Dokument${expired.length > 1 ? "e" : ""} abgelaufen</div>`;
    }
    if (expiringSoon.length > 0) {
      warningBanner += `<div class="doc-warning-banner doc-warning-soon">🕐 ${expiringSoon.length} Dokument${expiringSoon.length > 1 ? "e laufen" : " läuft"} bald ab</div>`;
    }

    const sortedRows = [...rows].sort((a, b) => {
      const aExpiry = String(a.expiry_date || "");
      const bExpiry = String(b.expiry_date || "");
      const aExpired = Boolean(aExpiry && aExpiry <= today);
      const bExpired = Boolean(bExpiry && bExpiry <= today);
      const aSoon = Boolean(aExpiry && aExpiry > today && aExpiry <= soonStr);
      const bSoon = Boolean(bExpiry && bExpiry > today && bExpiry <= soonStr);

      const aPriority = aExpired ? 0 : aSoon ? 1 : 2;
      const bPriority = bExpired ? 0 : bSoon ? 1 : 2;
      if (aPriority !== bPriority) return aPriority - bPriority;

      if (aExpiry && bExpiry && aExpiry !== bExpiry) {
        return aExpiry < bExpiry ? -1 : 1;
      }
      const aType = String(a.doc_type || "").toLowerCase();
      const bType = String(b.doc_type || "").toLowerCase();
      if (aType === bType) return 0;
      return aType < bType ? -1 : 1;
    });

    const payrollRows = sortedRows.filter((doc) => doc.isPayroll || doc.category === "payroll");
    const otherRows = sortedRows.filter((doc) => !payrollRows.includes(doc));
    const listSource = [...payrollRows, ...otherRows];
    const visibleRows = documentsCompactExpanded ? listSource : listSource.slice(0, 4);
    const docsHiddenCount = Math.max(0, listSource.length - visibleRows.length);

    let payrollBanner = "";
    if (payrollRows.length > 0) {
      payrollBanner = `<div class="doc-payroll-banner">
        <strong>${t("documentsPayrollTitle")}</strong>
        <span>${payrollRows.length} · ${t("documentsPayrollNew")}</span>
      </div>`;
    }

    const docsMarkup = visibleRows.map((doc) => {
      const isPayroll = Boolean(doc.isPayroll || doc.category === "payroll");
      const isExpired = doc.expiry_date && doc.expiry_date < today;
      const expiryTs = doc.expiry_date ? new Date(`${doc.expiry_date}T23:59:59`).getTime() : Number.NaN;
      const dayDiff = Number.isNaN(expiryTs) ? null : Math.ceil((expiryTs - Date.now()) / 86400000);
      const statusLabel = doc.expiry_date
        ? (isExpired ? t("documentsStatusExpired") : t("documentsStatusOk"))
        : t("documentsStatusNoExpiry");
      const expiryDeltaLabel = dayDiff === null
        ? ""
        : dayDiff < 0
          ? `T+${Math.abs(dayDiff)}d`
          : `T-${dayDiff}d`;
      const statusClass = doc.expiry_date
        ? (isExpired ? "doc-expired" : "doc-ok")
        : "doc-no-expiry";
      const received = (doc.created_at || "").slice(0, 10);
      const docType = String(doc.doc_type || "").trim().toLowerCase();
      const isEinsatzplan = docType === "einsatzplan";
      const openPlanBtn = isEinsatzplan
        ? `<button type="button" class="doc-open-plan-btn ghost small-btn" data-open-einsatzplan="1">${t("deploymentPlanOpenInApp")}</button>`
        : "";
      const downloadBtn = doc.id && doc.canDownload !== false
        ? `<button type="button" class="doc-download-btn" data-doc-id="${escapeHtmlBasic(doc.id)}" data-doc-name="${escapeHtmlBasic(doc.filename || "dokument.pdf")}">⬇ ${t("documentsDownload")}</button>`
        : "";
      return `<div class="document-item ${statusClass}${isPayroll ? " doc-payroll-item" : ""}">
        <div class="doc-type-row">
          <div class="doc-type">${escapeHtmlBasic(workerDocTypeLabel(doc))}</div>
          ${isPayroll ? `<span class="doc-payroll-pill">${t("documentsPayrollTitle")}</span>` : ""}
        </div>
        <div class="doc-meta">
          ${received ? `<span>${t("documentsReceived")}: ${formatDate(received)}</span>` : ""}
          ${doc.expiry_date ? `<span>${t("documentsExpiry")}: ${formatDate(doc.expiry_date)}</span>` : ""}
          <span class="doc-status-badge ${statusClass}">${statusLabel}${expiryDeltaLabel ? ` · ${expiryDeltaLabel}` : ""}</span>
        </div>
        <div class="doc-actions-row">${openPlanBtn}${downloadBtn}</div>
      </div>`;
    }).join("");

    const toggleMarkup = docsHiddenCount > 0 || documentsCompactExpanded
      ? `<button id="documentsCompactToggleBtn" class="ghost small-btn compact-list-toggle" type="button">${documentsCompactExpanded ? t("compactShowLess") : `${t("compactShowMore")} (+${docsHiddenCount})`}</button>`
      : "";

    elements.documentsList.innerHTML = payrollBanner + warningBanner + docsMarkup + toggleMarkup;

    elements.documentsList.querySelectorAll("[data-open-einsatzplan]").forEach((btn) => {
      btn.addEventListener("click", () => {
        void openWorkerDeploymentPlanScreen();
      });
    });

    elements.documentsList.querySelectorAll(".doc-download-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const docId = btn.getAttribute("data-doc-id");
        const docName = btn.getAttribute("data-doc-name") || "dokument.pdf";
        btn.disabled = true;
        try {
          await downloadWorkerDocument(docId, docName);
        } catch (error) {
          showWorkerNotice(formatWorkerApiError(error));
        } finally {
          btn.disabled = false;
        }
      });
    });

    const toggleBtn = document.querySelector("#documentsCompactToggleBtn");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        documentsCompactExpanded = !documentsCompactExpanded;
        void loadMyDocuments();
      });
    }
    updateSmartWorkHub(lastWorkerPayload, lastTimesheetRows);
  } catch (error) {
    lastDocumentRows = [];
    renderWorkerListMessage(elements.documentsList, formatWorkerApiError(error), "error");
    updateSmartWorkHub(lastWorkerPayload, lastTimesheetRows);
    console.warn("Could not load documents:", error);
  }
}

function escapeHtmlBasic(str) {
  return String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Zählt Arbeitstage (Mo–Fr) zwischen start und end (inkl.) */
function countWorkingDays(startStr, endStr) {
  const start = new Date(startStr);
  const end = new Date(endStr);
  let count = 0;
  const cur = new Date(start);
  while (cur <= end) {
    const dow = cur.getDay();
    if (dow !== 0 && dow !== 6) count++;
    cur.setDate(cur.getDate() + 1);
  }
  return count;
}

// ═════════════════════════════════════════════════════════════════════
// ── FEATURE 4: VOICE COMMANDS (Web Speech API) ──
// ═════════════════════════════════════════════════════════════════════

let voiceRecognition = null;
let isListening = false;

function initVoiceCommands() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition || !window.isSecureContext) {
    const fallbackInput = window.prompt(t("voiceFallbackPrompt"), "");
    if (!fallbackInput) {
      showWorkerNotice(t("voiceFallbackCancelled"));
      return;
    }
    processVoiceCommand(fallbackInput);
    return;
  }
  
  if (!voiceRecognition) {
    voiceRecognition = new SpeechRecognition();
    const langMap = {
      de: "de-DE",
      en: "en-GB",
      tr: "tr-TR",
      ar: "ar-SA",
      fr: "fr-FR",
      es: "es-ES",
      it: "it-IT",
      pl: "pl-PL"
    };
    voiceRecognition.lang = langMap[currentLang] || "de-DE";
    voiceRecognition.continuous = false;
    voiceRecognition.interimResults = false;
    
    voiceRecognition.onstart = () => {
      isListening = true;
      if (elements.voiceCommandBtn) {
        elements.voiceCommandBtn.classList.add("listening");
      }
      showWorkerNotice(t("voiceListening"));
    };
    
    voiceRecognition.onend = () => {
      isListening = false;
      if (elements.voiceCommandBtn) {
        elements.voiceCommandBtn.classList.remove("listening");
      }
    };
    
    voiceRecognition.onerror = (event) => {
      const code = String(event.error || "");
      if (code === "not-allowed" || code === "service-not-allowed") {
        showWorkerNotice(t("microphoneAccessBlocked"));
        return;
      }
      if (code === "no-speech") {
        showWorkerNotice(t("noSpeechDetected"));
        return;
      }
      showWorkerNotice(`Fehler: ${code || "unknown"}`);
    };
    
    voiceRecognition.onresult = (event) => {
      let interimTranscript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          processVoiceCommand(transcript);
        } else {
          interimTranscript += transcript;
        }
      }
      if (interimTranscript) {
        showWorkerNotice(`Hört: "${interimTranscript}"`);
      }
    };
  }
  
  if (isListening) {
    voiceRecognition.stop();
  } else {
    voiceRecognition.start();
  }
}

function getWorkerLang() {
  return String(wpGet(WORKER_LANG_KEY) || "de").slice(0, 2);
}

function formatWorkerAiAnswerHtml(text) {
  const safe = escapeHtmlBasic(String(text || ""));
  return safe.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\n/g, "<br>");
}

function appendWorkerAiLog(role, text, actions = []) {
  if (!elements.workerAiLog || !text) return;
  const row = document.createElement("div");
  row.className = role === "user" ? "worker-ai-msg-user" : "worker-ai-msg-bot";
  if (role === "bot") {
    row.innerHTML = formatWorkerAiAnswerHtml(text);
  } else {
    row.textContent = text;
  }
  elements.workerAiLog.appendChild(row);
  if (role === "bot" && actions?.length && globalThis.BaupassAiUi?.renderActionButtons) {
    const actionHost = document.createElement("div");
    actionHost.className = "worker-ai-action-host";
    globalThis.BaupassAiUi.renderActionButtons(actionHost, actions, getWorkerLang());
    actionHost.querySelectorAll(".ai-action-btn").forEach((btn) => {
      btn.classList.add("worker-ai-action-btn");
    });
    elements.workerAiLog.appendChild(actionHost);
  }
  elements.workerAiLog.scrollTop = elements.workerAiLog.scrollHeight;
}

async function submitWorkerAiQuestion() {
  const input = elements.workerAiQuestion;
  let question = (input?.value || "").trim();
  if (!question) return;
  globalThis.BaupassAiUi?.stopSpeaking?.();
  globalThis.BaupassAiUi?.stopVoiceCapture?.("workerAiQuestion");
  if (!workerToken) {
    showWorkerNotice(t("sessionExpired"));
    return;
  }
  const spoken = globalThis.BaupassAiUi?.consumeVoiceInputFlag?.(input) || false;
  question = globalThis.BaupassAiUi?.cleanQuestionText?.(question) || question;
  appendWorkerAiLog("user", question);
  if (input) {
    input.value = "";
  }
  try {
    const payload = await fetchJson(`${API_BASE}/ai/ask`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${workerToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question, lang: getWorkerLang(), spoken }),
    });
    const rawAnswer = payload?.answer || payload?.message || t("workerAiNoAnswer");
    const answer = spoken
      ? (globalThis.BaupassAiUi?.cleanTextForDisplay?.(rawAnswer) || rawAnswer)
      : rawAnswer;
    const actions = payload?.actions || payload?.suggestedActions || [];
    appendWorkerAiLog("bot", answer, actions);
    await globalThis.BaupassAiUi?.speakReply?.(answer, getWorkerLang(), {
      spoken,
      speakUrl: `${API_BASE}/ai/speak`,
      authHeaders: { Authorization: `Bearer ${workerToken}` },
    });
  } catch (error) {
    appendWorkerAiLog("bot", formatWorkerApiError(error));
  }
}

function isWorkerAiQuestion(text) {
  const cmd = text.toLowerCase().trim();
  if (!cmd) return false;
  if (/(kontakt|contact|hilfe|help|admin|chef|support|mail|email|dokument|document|stunden|zeiten|urlaub|leave|ki\b|ai\b|frage|question|مساعدة|اتصل)/i.test(cmd)) {
    return true;
  }
  return cmd.length > 28;
}

function processVoiceCommand(text) {
  const cmd = text.toLowerCase().trim();
  showWorkerNotice(`Befehl: "${text}"`);

  if (cmd.includes("ausbuchen") || cmd.includes("checkout")) {
    openGateMode();
    return;
  }
  if (cmd.includes("antrag") || cmd.includes("urlaub")) {
    applyWorkerPageView("leaveRequestCard");
    toggleLeaveRequestForm();
    return;
  }
  if (cmd.includes("thema") || cmd.includes("theme")) {
    toggleTheme();
    return;
  }
  if (cmd.includes("beenden") || cmd.includes("exit")) {
    if (!elements.gateScannerOverlay?.classList.contains("hidden")) {
      closeGateMode();
    }
    return;
  }
  if (isWorkerAiQuestion(text)) {
    applyWorkerPageView("workerAiCard");
    if (elements.workerAiQuestion) {
      elements.workerAiQuestion.value = text.trim();
    }
    void submitWorkerAiQuestion();
    return;
  }
  showWorkerNotice(`"${text}" nicht erkannt. Versuchen Sie: Ausbuchen, Antrag, Kontakt, Dokumente`);
}

// ═════════════════════════════════════════════════════════════════════
// ── FEATURE 5: OFFLINE QUEUE + IndexedDB ──
// ═════════════════════════════════════════════════════════════════════

async function initOfflineStorage() {
  // Already handled by existing offline queue in localStorage
  // IndexedDB can be added here for larger data persistence
  if (!("indexedDB" in window)) {
    console.warn("IndexedDB not supported");
    return;
  }
  
  try {
    const db = indexedDB.open("workpass-offline", 1);
    db.onupgradeneeded = (event) => {
      const idb = event.target.result;
      if (!idb.objectStoreNames.contains("events")) {
        idb.createObjectStore("events", { keyPath: "id", autoIncrement: true });
      }
    };
  } catch (error) {
    console.warn("Could not init IndexedDB:", error);
  }
}

// ═════════════════════════════════════════════════════════════════════
// ── INITIALIZATION ──
// ═════════════════════════════════════════════════════════════════════

// Apply stored theme on load
const storedTheme = wpGet(WORKER_THEME_KEY) || "auto";
applyTheme(storedTheme);

// Initialize offline storage
void initOfflineStorage();

// Show notification permission banner if not yet granted
if ("Notification" in window && Notification.permission === "default" && elements.notificationBanner) {
  elements.notificationBanner.classList.remove("hidden");
}

// Load leave requests on login
if (workerToken) {
  void loadLeaveRequests();
}

// ─────────────────────────────────────────────────────────────────────
// STARTUP: Force immediate card render if worker data exists
// ─────────────────────────────────────────────────────────────────────

workerDebug("[worker-app init] workerToken:", workerToken ? "present" : "missing");

const __workerBootParamsForHydrate = new URLSearchParams(window.location.search);
if (workerToken && !isQrBootstrapEntry(__workerBootParamsForHydrate)) {
  const cachedPayloadRaw = wpGet(WORKER_CACHED_PAYLOAD_KEY);
  if (cachedPayloadRaw) {
    try {
      const cachedPayload = JSON.parse(cachedPayloadRaw);
      workerDebug("[worker-app init] Found cached payload, rendering immediately...");
      renderWorker(cachedPayload);
      focusWorkerPassOnLoad();
    } catch (err) {
      console.error("[worker-app init] Cache parse failed:", err);
    }
  }
} else if (!window.__workerAppInitDone) {
  workerDebug("[worker-app init] No token, login handled by init()");
}

// ════════════════════════════════════════════════════════════════
// VISITOR COUNTDOWN TIMER – Premium Timer Management
// ════════════════════════════════════════════════════════════════

var visitorCountdownInterval = null;
var visitorTimerRing = null;
var visitorTimeRemaining = null;

function startVisitorCountdownTimer(visitEndAt) {
  stopVisitorCountdownTimer(); // Clear any existing timer
  
  if (!visitEndAt) return;
  
  const timerRing = document.getElementById("visitorTimerRing");
  const timeDisplay = document.getElementById("visitorTimeRemaining");
  
  if (!timerRing || !timeDisplay) return;
  
    const MAX_DASH_OFFSET = 81.68; // Circumference of r=13 chip ring (2π×13)
  const updateTimer = () => {
    const now = new Date();
    const endTime = new Date(visitEndAt);
    const diffMs = endTime - now;
    
    if (diffMs <= 0) {
      // Timer expired
      timeDisplay.textContent = "00:00";
      timerRing.style.strokeDashoffset = MAX_DASH_OFFSET;
      stopVisitorCountdownTimer();
      showWorkerNotice("Besuchszeit abgelaufen");
      return;
    }
    
    const totalSeconds = Math.floor(diffMs / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    
    // Format time display
    if (hours > 0) {
      timeDisplay.textContent = `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
    } else {
      timeDisplay.textContent = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }
    
    // Calculate total duration (initial endTime - now when started)
    const startMs = visitEndAt - (Math.floor((endTime - now) / 1000) * 1000); // Rough estimate
    const totalDurationMs = endTime - startMs;
    const progressRatio = diffMs / totalDurationMs;
    const dashOffset = MAX_DASH_OFFSET * progressRatio;
    
    timerRing.style.strokeDashoffset = Math.max(0, dashOffset);
    
    // Warning colors as time runs out
    const timerChip = document.getElementById("visitorTimerChip");
    if (timerChip) {
      if (diffMs < 5 * 60 * 1000) { // Less than 5 minutes
        timerChip.classList.remove("timer-warning");
        timerChip.classList.add("timer-critical");
      } else if (diffMs < 15 * 60 * 1000) { // Less than 15 minutes
        timerChip.classList.remove("timer-critical");
        timerChip.classList.add("timer-warning");
      } else {
        timerChip.classList.remove("timer-warning", "timer-critical");
      }
    }
  };
  
  updateTimer(); // Initial update
  visitorCountdownInterval = window.setInterval(updateTimer, 1000);
}

function stopVisitorCountdownTimer() {
  if (visitorCountdownInterval) {
    window.clearInterval(visitorCountdownInterval);
    visitorCountdownInterval = null;
  }
  
    const timerChip = document.getElementById("visitorTimerChip");
    if (timerChip) {
      timerChip.classList.remove("timer-warning", "timer-critical");
  }
}

// Initialize bottom tab navigation on page load and also when script runs
// after DOMContentLoaded (webview/service-worker cache edge cases).
function initWorkerAppShell() {
  ensureWorkerChatShellStyles();
  ensureWorkerChatNavDom();
  ensureWorkerChatDom();
  ensureWorkerChatComposeBar();
  refreshTopBarElements();
  bindTopBarActions();
  enforceUiVisibilityGuard();
  bindWorkerFeatureTabActions();
  initBottomTabNavigation();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initWorkerAppShell, { once: true });
} else {
  initWorkerAppShell();
}

