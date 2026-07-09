import { applyI18n, featureLabel, formatForecastSummary, getLang, moduleAlertMessage, resolvePlanLabel, setLang, setSectorTermOverrides, t, widgetDetail, widgetLabel, widgetValue } from "./i18n.js";
import { mountGeofenceMapWhenReady, refreshGeofenceMap, useGeofenceCurrentLocation } from "./geofence-map.js";
import { INTEGRATION_WIZARD, buildConnectPayload, renderWizardForm } from "./integrations-wizard.js";

const WP = window.WorkPassStorage;
const TOKEN_KEY = WP?.KEYS?.ADMIN_TOKEN || "workpass-admin-token";
const USER_KEY = WP?.KEYS?.ADMIN_USER || "workpass-admin-user";
const COMPANY_KEY = WP?.KEYS?.ADMIN_COMPANY || "workpass-admin-company";
const CONTROL_TOKEN_KEY = WP?.KEYS?.SESSION_TOKEN || "workpass-session-token";

function wpGet(key) {
  return WP ? WP.getItem(key) : localStorage.getItem(key);
}
function wpSet(key, value) {
  if (WP) WP.setItem(key, value);
  else localStorage.setItem(key, value);
}
function wpRemove(key) {
  if (WP) WP.removeItem(key);
  else localStorage.removeItem(key);
}

const DEFAULT_RENDER_API_BASE = "https://baupass-production.up.railway.app";

function isLocalHostName(hostname) {
  const host = String(hostname || "").toLowerCase();
  return (
    host === "localhost"
    || host === "127.0.0.1"
    || host === "::1"
    || host === "0.0.0.0"
    || host.endsWith(".local")
  );
}

function isEmbedMode() {
  return new URLSearchParams(location.search).get("embed") === "1";
}

if (isEmbedMode()) {
  document.documentElement.classList.add("embed-document");
  document.body.classList.add("embed-mode", "admin-v2-embed");
}

async function tryEmbedSessionFromControlPass() {
  if (!isEmbedMode()) {
    return false;
  }
  if (tryEmbedSessionFromControlPass._cooldownUntil && Date.now() < tryEmbedSessionFromControlPass._cooldownUntil) {
    return false;
  }
  document.documentElement.classList.add("embed-document");
  document.body.classList.add("embed-mode", "admin-v2-embed");
  const parentToken = (wpGet(CONTROL_TOKEN_KEY) || "").trim();
  if (!parentToken) {
    return false;
  }
  try {
    const res = await fetch(`${apiBase()}/api/v2/auth/session`, {
      headers: { Authorization: `Bearer ${parentToken}`, Accept: "application/json" },
      cache: "no-store",
    });
    if (!res.ok) {
      if (res.status >= 500) {
        tryEmbedSessionFromControlPass._cooldownUntil = Date.now() + 30000;
      }
      return false;
    }
    const data = await res.json();
    wpSet(TOKEN_KEY, parentToken);
    wpSet(USER_KEY, JSON.stringify(data.user || {}));
    const qsCid = new URLSearchParams(location.search).get("company_id") || "";
    if (qsCid) {
      wpSet(COMPANY_KEY, qsCid);
    } else if (data.user?.preview_company_id && String(data.user?.role || "") === "superadmin") {
      wpSet(COMPANY_KEY, data.user.preview_company_id);
    } else if (data.user?.company_id) {
      wpSet(COMPANY_KEY, data.user.company_id);
    }
    return true;
  } catch {
    return false;
  }
}

function applyEmbedStartupTab() {
  applyStartupTab();
}

function applyStartupTab() {
  const params = new URLSearchParams(location.search);
  const hashTab = String(location.hash || "").replace(/^#/, "").trim();
  let tab = params.get("tab") || hashTab;
  if (tab === "analytics" && !canAccessAnalyticsTab()) {
    tab = "overview";
  }
  if (tab && document.querySelector(`.tab[data-tab="${tab}"]`)) {
    switchToTab(tab);
  }
  if (params.get("einsatzplan") === "1" || params.get("focus") === "deployment") {
    switchToTab("workers");
  }
}

async function applyStartupTabAfterLoad() {
  applyStartupTab();
  const params = new URLSearchParams(location.search);
  if (params.get("einsatzplan") === "1" || params.get("focus") === "deployment") {
    try {
      await refreshActiveTab();
      await focusDeploymentSection();
    } catch (err) {
      notifyTabError(err);
    }
  }
}

async function focusDeploymentSection() {
  const bar = $("deploymentMonthBar");
  if (!bar) return;
  if (bar.classList.contains("hidden")) {
    showActionToast(t("common.selectCompany"), true);
    return;
  }
  bar.classList.remove("hidden");
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  const scrollHost = document.querySelector(".app-content");
  if (scrollHost) {
    const hostRect = scrollHost.getBoundingClientRect();
    const barRect = bar.getBoundingClientRect();
    const delta = barRect.top - hostRect.top + scrollHost.scrollTop - 16;
    scrollHost.scrollTo({ top: Math.max(0, delta), behavior: "smooth" });
  } else {
    bar.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  bar.classList.add("deployment-highlight");
  setTimeout(() => bar.classList.remove("deployment-highlight"), 2600);
}

async function activateCommandItem(item) {
  if (!item) return;
  closeCommandPalette();
  if (item.tab === "enterprise" && requestEnterpriseHubInShell()) {
    return;
  }
  if (item.href) {
    if (item.href.includes("enterprise-hub.html")) {
      if (requestEnterpriseHubInShell()) {
        return;
      }
      switchToTab("enterprise");
      syncEnterpriseFrame();
      return;
    }
    if (isEmbedMode()) {
      window.open(item.href, "_blank", "noopener");
    } else {
      window.location.href = item.href;
    }
    return;
  }
  const tab = item.tab;
  if (!tab) return;
  switchToTab(tab);
  try {
    if (item.focusDeployment) {
      await loadWorkers();
      await focusDeploymentSection();
      return;
    }
    await refreshActiveTab();
  } catch (err) {
    notifyTabError(err);
  }
}

function ensureEmbedQuickNav() {
  if (!isEmbedMode()) return;
  /* Parent SUPPIX sidebar owns navigation — no duplicate quick bar in embed */
  return;
  const main = document.querySelector(".app-main");
  if (!main || document.getElementById("embedQuickNav")) return;
  const nav = document.createElement("nav");
  nav.id = "embedQuickNav";
  nav.className = "embed-quick-nav";
  nav.setAttribute("aria-label", "Schnellzugriff Embed");
  const items = [
    { tab: "workers", label: t("deployment.planBtn"), primary: true, deployment: true },
    { tab: "workers", label: t("tab.workers") },
    { tab: "access", label: t("tab.access") },
    { tab: "inbox", label: t("tab.inbox") },
    { tab: "overview", label: t("tab.overview") },
  ];
  nav.innerHTML = items
    .map(
      (item) =>
        `<button type="button" class="embed-quick-nav-btn${item.primary ? " primary" : ""}" data-embed-tab="${item.tab}"${item.deployment ? ' data-embed-deployment="1"' : ""}>${item.label}</button>`,
    )
    .join("");
  const content = document.querySelector(".app-content");
  if (content) {
    main.insertBefore(nav, content);
  } else {
    main.prepend(nav);
  }
  nav.querySelectorAll("[data-embed-tab]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      switchToTab(btn.getAttribute("data-embed-tab"));
      try {
        if (btn.getAttribute("data-embed-deployment") === "1") {
          await loadWorkers();
          await focusDeploymentSection();
        } else {
          await refreshActiveTab();
        }
      } catch (err) {
        notifyTabError(err);
      }
    });
  });
}

function isAuthError(err) {
  const code = String(err?.data?.error || err?.message || "").toLowerCase();
  return (
    err?.status === 401 ||
    err?.auth === true ||
    ["invalid_session", "session_expired", "unauthorized"].includes(code)
  );
}

function hideAllSessionViews() {
  $("sessionBootView")?.classList.add("hidden");
  $("embedAuthView")?.classList.add("hidden");
  $("loginView")?.classList.add("hidden");
  $("dashboardView")?.classList.add("hidden");
}

function showSessionBoot() {
  hideAllSessionViews();
  $("sessionBootView")?.classList.remove("hidden");
}

function showEmbedAuthRequired(message) {
  hideAllSessionViews();
  $("embedAuthView")?.classList.remove("hidden");
  const msgEl = $("embedAuthView")?.querySelector("[data-i18n='login.embedRequired']");
  if (msgEl && message) {
    msgEl.textContent = message;
  }
}

function clearSessionAndShowLogin(message) {
  wpRemove(TOKEN_KEY);
  wpRemove(USER_KEY);
  if (isEmbedMode()) {
    showEmbedAuthRequired(message || t("login.embedRequired"));
    return;
  }
  showLogin();
  const errEl = $("loginError");
  if (errEl && message) {
    errEl.textContent = message;
    errEl.classList.remove("hidden");
  }
}

async function probeSessionToken(token) {
  if (!token) return false;
  try {
    const res = await fetch(`${apiBase()}/api/v2/auth/session`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
    });
    return res.ok;
  } catch {
    return false;
  }
}

async function adoptControlPassTokenIfValid() {
  const controlToken = (wpGet(CONTROL_TOKEN_KEY) || "").trim();
  if (!controlToken) return false;
  if (!(await probeSessionToken(controlToken))) return false;
  wpSet(TOKEN_KEY, controlToken);
  return true;
}

function notifyTabError(err) {
  if (isAuthError(err)) return;
  showActionToast(err?.message || String(err), true);
}

async function applyTenantBrandingFromApi() {
  const user = getUser();
  let cid = String(user?.company_id || "").trim();
  if (user?.role === "superadmin") {
    cid = String(wpGet(COMPANY_KEY) || "").trim();
  }
  try {
    if (window.BaupassAuth?.resolveTenantBranding) {
      await window.BaupassAuth.resolveTenantBranding({ companyId: cid || undefined });
    } else if (window.BaupassAuth?.loadTenantBranding) {
      await window.BaupassAuth.loadTenantBranding(cid || undefined);
    } else {
      const q = cid ? `?company_id=${encodeURIComponent(cid)}` : "";
      const branding = await api(`/api/companies/current/branding${q}`);
      window.BaupassAuth?.applyTenantBranding?.(branding);
    }
  } catch {
    // optional white-label
  }
  await loadSectorTerminologyForAdmin();
}

function resolveAdminCompanyId() {
  const user = getUser();
  let cid = String(user?.company_id || "").trim();
  if (user?.role === "superadmin") {
    cid = String(wpGet(COMPANY_KEY) || "").trim();
  }
  return cid;
}

async function loadSectorTerminologyForAdmin() {
  const cid = resolveAdminCompanyId();
  const lang = getLang();
  try {
    let url = `/api/platform/sector-config?lang=${encodeURIComponent(lang)}`;
    if (cid) url += `&company_id=${encodeURIComponent(cid)}`;
    const data = await api(url);
    setSectorTermOverrides(data?.terms || {});
    window.__adminV2Sector = data?.sector || "construction";
    applyI18n();
  } catch {
    setSectorTermOverrides({});
  }
}

function applyParentCompanyId(companyId) {
  const cid = String(companyId || "").trim();
  if (!cid) return;
  wpSet(COMPANY_KEY, cid);
  const select = $("companyPicker");
  if (select && select.options.length) {
    const has = Array.from(select.options).some((o) => o.value === cid);
    if (has) select.value = cid;
  }
  void applyTenantBrandingFromApi();
}

window.addEventListener("message", (event) => {
  if (!event?.data || event.origin !== window.location.origin) return;
  if (event.data.type === "baupass-open-command-palette") {
    if (!$("dashboardView")?.classList.contains("hidden")) {
      applyParentCompanyId(event.data.companyId);
      openCommandPalette();
    }
    return;
  }
  if (event.data.type === "baupass-focus-einsatzplan") {
    applyParentCompanyId(event.data.companyId);
    pendingEinsatzplanFocus = true;
    pendingDeploymentWorkerId = String(event.data.workerId || "").trim() || null;
    pendingDeploymentWorkerName = String(event.data.workerName || "").trim() || null;
    pendingDeploymentWorkDate = String(event.data.workDate || "").trim().slice(0, 10) || null;
    if (!tryFocusEinsatzplanFromParent()) {
      bootSession().catch(() => {});
    }
    return;
  }
  if (event.data.type === "baupass-sync-lang") {
    const lang = String(event.data.lang || "").trim().slice(0, 2);
    if (lang) {
      setLang(lang);
      document.querySelectorAll("[data-lang-select]").forEach((sel) => {
        if (sel.value !== lang) sel.value = lang;
      });
    }
    return;
  }
  if (event.data.type === "baupass-navigate") {
    if (window.self !== window.top) {
      try {
        window.parent.postMessage(event.data, window.location.origin);
      } catch {
        // ignore
      }
      return;
    }
    handleHubNavigateFromEmbed(event.data);
    return;
  }
  if (event.data.type !== "baupass-sync-token") return;
  const langFromParent = String(event.data.lang || "").trim().slice(0, 2);
  if (langFromParent) {
    setLang(langFromParent);
    document.querySelectorAll("[data-lang-select]").forEach((sel) => {
      if (sel.value !== langFromParent) sel.value = langFromParent;
    });
  }
  const token = String(event.data.token || "").trim();
  if (!token) return;
  wpSet(TOKEN_KEY, token);
  wpSet(CONTROL_TOKEN_KEY, token);
  if (event.data.companyId) {
    applyParentCompanyId(event.data.companyId);
  }
  if ($("dashboardView")?.classList.contains("hidden")) {
    showSessionBoot();
    bootSession().catch(() => {});
    return;
  }
  const activeTab = document.querySelector(".tab.active")?.dataset?.tab;
  if (activeTab) {
    refreshActiveTab().catch(() => {});
  }
});
let pendingIntegrationProvider = null;
let pendingEinsatzplanFocus = false;
let pendingDeploymentWorkerId = null;
let pendingDeploymentWorkerName = null;
let pendingDeploymentWorkDate = null;
let pendingOpsEmbedPage = null;

function handleHubNavigateFromEmbed(data) {
  const view = String(data?.view || "").trim();
  if (data?.companyId) {
    applyParentCompanyId(data.companyId);
  }
  if (view === "deployment-plan" || data?.focusEinsatzplan || (view === "admin-v2" && data?.focusEinsatzplan)) {
    pendingEinsatzplanFocus = true;
    switchToTab("workers");
    tryFocusEinsatzplanFromParent();
    return;
  }
  if (view === "ops-center") {
    if (postShellNavigate({ view: "ops-center", companyId: data?.companyId || activeCompanyId() })) {
      return;
    }
    navigateToOpsEmbed("/ops-command-center.html");
    return;
  }
  if (view === "ai-assistant") {
    if (postShellNavigate({ view: "ai-assistant", companyId: data?.companyId || activeCompanyId() })) {
      return;
    }
    navigateToOpsEmbed("/ai-command-center.html");
    return;
  }
  if (view === "enterprise-hub") {
    if (requestEnterpriseHubInShell()) {
      return;
    }
  }
  const tabByView = {
    dashboard: "overview",
    workers: "workers",
    access: "access",
    documents: "inbox",
    "ai-assistant": "copilot",
    "enterprise-hub": "enterprise",
    "admin-v2": "workers",
  };
  const tab = tabByView[view];
  if (tab) {
    switchToTab(tab);
    return;
  }
  if (data?.url && typeof data.url === "string") {
    try {
      window.location.href = data.url;
    } catch {
      // ignore
    }
  }
}

function navigateToOpsEmbed(page) {
  pendingOpsEmbedPage = String(page || "").trim();
  switchToTab("operations");
  refreshActiveTab().catch(notifyTabError);
}

/** When embedded in SUPPIX shell, open Enterprise Hub in parent (local tab is hidden). */
function postShellNavigate(payload) {
  if (!isEmbedMode() || window.self === window.top) {
    return false;
  }
  try {
    window.parent.postMessage(
      {
        type: "baupass-navigate",
        companyId: activeCompanyId() || getUser()?.company_id || "",
        ...payload,
      },
      window.location.origin,
    );
    return true;
  } catch {
    return false;
  }
}

function requestEnterpriseHubInShell() {
  return postShellNavigate({ view: "enterprise-hub" });
}

function tryFocusEinsatzplanFromParent() {
  if ($("dashboardView")?.classList.contains("hidden")) {
    return false;
  }
  pendingEinsatzplanFocus = false;
  const workerId = pendingDeploymentWorkerId;
  const workerName = pendingDeploymentWorkerName;
  const workDate = pendingDeploymentWorkDate;
  pendingDeploymentWorkerId = null;
  pendingDeploymentWorkerName = null;
  pendingDeploymentWorkDate = null;
  activateCommandItem({
    tab: "workers",
    focusDeployment: true,
  })
    .then(async () => {
      if (!workerId) return;
      const list = Array.isArray(window.__adminV2WorkersCache) ? window.__adminV2WorkersCache : [];
      const w = list.find((entry) => String(entry.id || entry.workerId || "") === String(workerId));
      const name =
        workerName ||
        `${w?.firstName || w?.first_name || ""} ${w?.lastName || w?.last_name || ""}`.trim() ||
        workerId;
      await openDeploymentModal(workerId, name, workDate);
    })
    .catch(notifyTabError);
  return true;
}

function getUser() {
  try {
    return JSON.parse(wpGet(USER_KEY) || "{}");
  } catch {
    return {};
  }
}

function isSuperadminUser() {
  return String(getUser()?.role || "").toLowerCase() === "superadmin";
}

function canAccessAnalyticsTab() {
  return isSuperadminUser();
}

function applyRoleNavigation() {
  const showAnalytics = canAccessAnalyticsTab();
  const showPlatform = isSuperadminUser();
  document.querySelectorAll('.tab[data-tab="analytics"]').forEach((el) => {
    el.classList.toggle("hidden", !showAnalytics);
  });
  document.querySelectorAll('.tab[data-tab="platform"]').forEach((el) => {
    el.classList.toggle("hidden", !showPlatform);
  });
  $("enterpriseAnalyticsShortcut")?.classList.toggle("hidden", !showAnalytics);
  if (!showAnalytics && document.querySelector('.tab.active[data-tab="analytics"]')) {
    switchToTab("overview");
  }
  if (!showPlatform && document.querySelector('.tab.active[data-tab="platform"]')) {
    switchToTab("overview");
  }
}

function companyQuery() {
  const user = getUser();
  if (user.role !== "superadmin") {
    return "";
  }
  const cid = wpGet(COMPANY_KEY) || "";
  return cid ? `?company_id=${encodeURIComponent(cid)}` : "";
}

function apiBase() {
  const params = new URL(window.location.href).searchParams;
  const queryValue = String(params.get("apiBase") || "").trim().replace(/\/+$/, "");
  const host = String(window.location.hostname || "").toLowerCase();
  const localHost = isLocalHostName(host);
  const staticHost = host.endsWith("github.io") || host.endsWith(".pages.dev") || host.endsWith(".web.app");

  if (localHost) {
    return "";
  }

  if (staticHost) {
    if (queryValue) {
      try {
        const parsed = new URL(queryValue);
        const queryHost = parsed.hostname.toLowerCase();
        if (!isLocalHostName(queryHost)) {
          return queryValue;
        }
      } catch {
        // ignore malformed overrides on static hosts
      }
    }
    return DEFAULT_RENDER_API_BASE;
  }

  if (queryValue) {
    try {
      const parsed = new URL(queryValue);
      const queryHost = parsed.hostname.toLowerCase();
      if (!isLocalHostName(queryHost)) {
        return queryValue;
      }
    } catch {
      // ignore malformed overrides
    }
  }

  return "";
}

async function api(path, options = {}) {
  const token = wpGet(TOKEN_KEY);
  const headers = {
    Accept: "application/json",
    ...(options.headers || {}),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const res = await (window.BaupassGuardian?.fetchWithGuardianRetry
    ? window.BaupassGuardian.fetchWithGuardianRetry(`${apiBase()}${path}`, { ...options, headers })
    : fetch(`${apiBase()}${path}`, { ...options, headers }));
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    const snippet = text.replace(/\s+/g, " ").trim().slice(0, 100);
    const pathHint = String(path || "").split("?")[0];
    data = {
      error: "invalid_json",
      message:
        res.status === 404 || res.status === 405
          ? `API nicht erreichbar (${pathHint}, HTTP ${res.status}). Bitte Seite neu laden — ggf. läuft noch ein Server-Update.`
          : `Unerwartete Server-Antwort (${pathHint}, HTTP ${res.status}).`,
      detail: snippet,
    };
  }
  if (!res.ok) {
    const code = String(data.error || "").toLowerCase();
    if (
      res.status === 401 &&
      ["invalid_session", "session_expired", "unauthorized"].includes(code)
    ) {
      clearSessionAndShowLogin(t("login.sessionExpired"));
      const err = new Error(t("login.sessionExpired"));
      err.status = 401;
      err.auth = true;
      err.data = data;
      throw err;
    }
    const err = new Error(data.message || data.error || res.statusText);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

function $(id) {
  return document.getElementById(id);
}

async function apiMultipart(path, { fields = {}, fileField = "file", file } = {}) {
  const token = wpGet(TOKEN_KEY);
  const form = new FormData();
  Object.entries(fields).forEach(([key, value]) => {
    if (value != null && String(value).trim() !== "") form.append(key, String(value));
  });
  if (file) {
    form.append(fileField, file);
  }
  const headers = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${apiBase()}${path}`, {
    method: "POST",
    headers,
    body: form,
  });
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = {};
  }
  if (!res.ok) {
    const err = new Error(data.message || data.error || res.statusText);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

function showLogin() {
  hideAllSessionViews();
  $("loginView").classList.remove("hidden");
  if (window.BaupassAuth?.loadPublicTenantBranding) {
    void window.BaupassAuth.loadPublicTenantBranding();
  }
}

function showDashboard() {
  hideAllSessionViews();
  $("dashboardView").classList.remove("hidden");
  const user = getUser();
  const line = `${user.username || ""} · ${user.role || ""}`;
  $("userLine").textContent = line;
  const sideLine = $("sidebarUserLine");
  if (sideLine) sideLine.textContent = line;
  setupCompanyPicker(user);
  applyRoleNavigation();
  bindTabNavigation();
  initCommandPalette();
  bindDeploymentModalOnce();
  bindDeploymentMonthBarOnce();
  ensureEmbedQuickNav();
}

function setupCompanyPicker(user) {
  const wrap = $("companyPickerWrap");
  const select = $("companyPicker");
  if (user.role !== "superadmin") {
    wrap.classList.add("hidden");
    return;
  }
  wrap.classList.remove("hidden");
  select.onchange = () => {
    if (!select.value) {
      return;
    }
    wpSet(COMPANY_KEY, select.value);
    void applyTenantBrandingFromApi();
    syncEnterpriseFrame();
    startAdminRealtime().catch(() => {});
    refreshActiveTab().catch(notifyTabError);
    if (document.querySelector(".tab.active")?.dataset?.tab === "platform") {
      loadCompanyWorkTimesForm(select.value).catch(() => {});
    }
  };
}

async function loadCompanies() {
  const user = getUser();
  if (user.role !== "superadmin") {
    return;
  }
  const select = $("companyPicker");
  if (!select) {
    return;
  }
  select.innerHTML = `<option value="" disabled selected>${t("common.loading")}</option>`;
  const companies = await api("/api/companies");
  const rows = Array.isArray(companies) ? companies.filter((c) => c && !c.deleted_at) : [];
  if (!rows.length) {
    select.innerHTML = `<option value="" disabled selected>${t("common.selectCompany")}</option>`;
    return;
  }
  const saved = wpGet(COMPANY_KEY) || "";
  select.innerHTML = rows
    .map((c) => `<option value="${c.id}">${c.name || c.id}</option>`)
    .join("");
  if (saved && rows.some((c) => c.id === saved)) {
    select.value = saved;
  } else {
    select.value = rows[0].id;
    wpSet(COMPANY_KEY, rows[0].id);
  }
}

function yn(v) {
  return v ? t("common.yes") : t("common.no");
}

function getOpsLayerOrder() {
  return [
    ["1_digital_twin", t("ops.layer.digitalTwin"), "🗺"],
    ["2_ai_security", t("ops.layer.aiSecurity"), "🛡"],
    ["3_site_intelligence", t("ops.layer.siteIntel"), "📊"],
    ["4_reputation", t("ops.layer.reputation"), "⭐"],
    ["5_emergency", t("ops.layer.emergency"), "🚨"],
    ["6_camera_ai", t("ops.layer.cameraAi"), "📷"],
    ["7_iot", t("ops.layer.iot"), "📡"],
    ["8_command_center", t("ops.layer.commandCenter"), "🎛"],
    ["9_autonomous", t("ops.layer.autonomous"), "⚙"],
    ["10_workforce_graph", t("ops.layer.workforceGraph"), "🔗"],
    ["11_identity", t("ops.layer.identity"), "🪪"],
    ["12_copilot", t("ops.layer.copilot"), "🤖"],
  ];
}

function statusBadge(ok) {
  return ok
    ? `<span class="badge badge-ok">${t("badge.ready")}</span>`
    : `<span class="badge badge-warn">${t("badge.needsSetup")}</span>`;
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatPushDelivery(res) {
  const d = res?.pushDelivery || res;
  if (!d) return "";
  if (d.delivered || (d.pushSent ?? 0) > 0) {
    const ch = (d.channels || []).join(" + ") || "push";
    return `Push: ${d.pushSent} (${ch})`;
  }
  return d.hint || t("push.none");
}

function showActionToast(message, isError) {
  const el =
    document.getElementById("globalToast") ||
    document.getElementById("inboxToast");
  if (!el) {
    alert(message);
    return;
  }
  const baseClass = el.id === "globalToast" ? "global-toast" : "inbox-toast";
  el.textContent = message;
  el.className = isError ? `${baseClass} err` : `${baseClass} ok`;
  el.classList.remove("hidden");
  clearTimeout(showActionToast._t);
  showActionToast._t = setTimeout(() => el.classList.add("hidden"), 4500);
}

function activeCompanyId() {
  const user = getUser();
  const stored = wpGet(COMPANY_KEY) || "";
  if (user.role === "superadmin") {
    return stored;
  }
  return stored || user.company_id || "";
}

let adminRealtimeStop = null;

function companyIdFromQuery() {
  const q = companyQuery();
  return q ? q.replace(/^\?company_id=/, "") : "";
}

function shouldRefreshOnEvent(evt) {
  const t = String(evt?.type || evt?.event_type || "");
  return /inbox|security|leave|access|push|emergency|alert|document|site_checkin|site_leave|proximity|worker_app|check_in|check_out|app_login|app_logout/i.test(
    t,
  );
}

function formatAccessDirection(direction) {
  const d = String(direction || "").trim().toLowerCase();
  if (d === "app-login") return t("access.appLogin");
  if (d === "app-logout") return t("access.appLogout");
  if (d === "check-in") return t("access.checkIn");
  if (d === "check-out") return t("access.checkOut");
  return direction || "-";
}

function paintInboxBadge(el, open, critical) {
  if (!el) return;
  const n = Number(open) || 0;
  const crit = Number(critical) || 0;
  if (n <= 0) {
    el.classList.add("hidden");
    el.classList.remove("critical");
    el.textContent = "";
    return;
  }
  el.classList.remove("hidden");
  const wasCritical = el.classList.contains("critical");
  el.classList.toggle("critical", crit > 0);
  el.textContent = crit > 0 ? `${n}!` : String(n);
  if (crit > 0 && !wasCritical) {
    el.classList.remove("badge-pulse-once");
    void el.offsetWidth;
    el.classList.add("badge-pulse-once");
  }
}

function updateInboxTabBadge(open, critical) {
  paintInboxBadge($("inboxTabBadge"), open, critical);
  paintInboxBadge($("inboxMobileBadge"), open, critical);
}

async function refreshInboxBadgeOnly() {
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    updateInboxTabBadge(0, 0);
    return;
  }
  try {
    const data = await api(`/api/inbox/counts${q}`);
    const c = data.counts || {};
    updateInboxTabBadge(c.open, c.critical);
  } catch {
    /* ignore */
  }
}

function scheduleInboxReload() {
  clearTimeout(scheduleInboxReload._t);
  scheduleInboxReload._t = setTimeout(() => {
    const tab = document.querySelector(".tab.active")?.dataset?.tab;
    if (tab === "inbox") loadInbox().catch(() => {});
    else refreshInboxBadgeOnly();
  }, 500);
}

async function startAdminRealtime() {
  if (!window.SUPPIXOpsRealtime) return;
  if (adminRealtimeStop) {
    adminRealtimeStop();
    adminRealtimeStop = null;
  }
  const cid = companyIdFromQuery();
  if (!cid && getUser().role === "superadmin") return;
  adminRealtimeStop = await window.SUPPIXOpsRealtime.start({
    companyId: cid,
    feedEl: null,
    onEvent: (evt) => {
      if (!shouldRefreshOnEvent(evt)) return;
      if (evt?.type === "inbox.changed") {
        scheduleInboxReload();
        return;
      }
      refreshInboxBadgeOnly();
      const tab = document.querySelector(".tab.active")?.dataset?.tab || "overview";
      if (tab === "inbox") scheduleInboxReload();
      else if (tab === "overview") {
        clearTimeout(scheduleInboxReload._overviewT);
        scheduleInboxReload._overviewT = setTimeout(() => loadOverview().catch(() => {}), 800);
      } else if (tab === "operations") {
        clearTimeout(scheduleInboxReload._opsT);
        scheduleInboxReload._opsT = setTimeout(() => loadOperations().catch(() => {}), 1200);
      }
    },
  });
}

function syncEnterpriseFrame() {
  const frame = $("enterpriseFrame");
  if (!frame) return;
  const q = companyQuery();
  const cid = q ? q.replace(/^\?company_id=/, "") : "";
  const lang = getLang();
  const base = `/enterprise-hub.html?embed=1&lang=${encodeURIComponent(lang)}&v=20260705b`;
  frame.src = cid ? `${base}&company_id=${encodeURIComponent(cid)}` : base;
  try {
    if (window.BaupassEmbed?.postMessageToIframe) {
      window.BaupassEmbed.postMessageToIframe(frame, { type: "baupass-sync-lang", lang });
    } else if (frame.contentWindow && frame.src && frame.src !== "about:blank") {
      frame.contentWindow.postMessage({ type: "baupass-sync-lang", lang }, window.location.origin);
    }
  } catch {
    // iframe not ready
  }
}

function broadcastLangToEnterpriseFrame(lang) {
  const frame = $("enterpriseFrame");
  if (!frame) return;
  try {
    if (window.BaupassEmbed?.postMessageToIframe) {
      window.BaupassEmbed.postMessageToIframe(frame, { type: "baupass-sync-lang", lang });
    } else if (frame.contentWindow && frame.src && frame.src !== "about:blank") {
      frame.contentWindow.postMessage({ type: "baupass-sync-lang", lang }, window.location.origin);
    }
  } catch {
    // iframe not ready
  }
}

const TAB_TITLE_KEYS = {
  overview: "tab.overview",
  analytics: "tab.analytics",
  inbox: "tab.inbox",
  copilot: "tab.copilot",
  enterprise: "tab.enterprise",
  workers: "tab.workers",
  access: "tab.access",
  mobile: "tab.mobile",
  operations: "tab.operations",
  tools: "tab.tools",
  platform: "tab.platform",
};

const COMMAND_NAV = [
  { tab: "overview", titleKey: "tab.overview", groupKey: "nav.group.start" },
  { tab: "analytics", titleKey: "tab.analytics", groupKey: "nav.group.start" },
  { tab: "inbox", titleKey: "tab.inbox", groupKey: "nav.group.start" },
  { tab: "copilot", titleKey: "tab.copilot", groupKey: "nav.group.start" },
  { tab: "workers", titleKey: "tab.workers", groupKey: "nav.group.people" },
  {
    tab: "workers",
    titleKey: "deployment.planBtn",
    groupKey: "nav.group.people",
    searchTerms: "einsatzplan monatsplan deployment plan pdf monat",
    focusDeployment: true,
  },
  { tab: "access", titleKey: "tab.access", groupKey: "nav.group.people" },
  { tab: "mobile", titleKey: "tab.mobile", groupKey: "nav.group.people" },
  { tab: "operations", titleKey: "tab.operations", groupKey: "nav.group.ops" },
  {
    href: "/admin-v2/chat.html",
    titleKey: "chat.title",
    groupKey: "nav.group.ops",
    searchTerms: "chat mitarbeiter nachricht nachrichten firma unterhaltung message messages",
  },
  {
    href: "/admin-v2/contracts.html",
    titleKey: "contracts.title",
    groupKey: "nav.group.ops",
    searchTerms: "arbeitsvertrag vertrag contract ai pdf employment agreement",
  },
  { tab: "tools", titleKey: "tab.tools", groupKey: "nav.group.ops" },
  { tab: "platform", titleKey: "tab.platform", groupKey: "nav.group.ops" },
  { tab: "enterprise", titleKey: "tab.enterprise", groupKey: "nav.group.enterprise" },
  { tab: "enterprise", titleKey: "common.enterpriseHub", groupKey: "nav.group.enterprise", searchTerms: "enterprise hub funktionen 16 ebenen layers katalog" },
  { href: "/index.html", titleKey: "common.legacyDashboard", groupKey: "nav.group.ops" },
];

let commandPaletteIndex = 0;
let commandPaletteFiltered = [];

function bindTabNavigation() {
  document.querySelectorAll(".tab[data-tab]").forEach((btn) => {
    if (btn.dataset.tabNavBound === "1") return;
    btn.dataset.tabNavBound = "1";
    btn.addEventListener("click", () => {
      switchToTab(btn.dataset.tab);
      refreshActiveTab().catch(notifyTabError);
    });
  });
  const gotoAnalytics = $("gotoAnalyticsBtn");
  if (gotoAnalytics && gotoAnalytics.dataset.bound !== "1") {
    gotoAnalytics.dataset.bound = "1";
    gotoAnalytics.addEventListener("click", () => {
      switchToTab("analytics");
      refreshActiveTab().catch(notifyTabError);
    });
  }
}

function switchToTab(tabId) {
  if (tabId === "analytics" && !canAccessAnalyticsTab()) {
    tabId = "overview";
  }
  if (tabId === "enterprise") {
    if (requestEnterpriseHubInShell()) {
      closeCommandPalette();
      return;
    }
  }
  document.querySelectorAll(".tab[data-tab]").forEach((btn) => {
    const on = btn.dataset.tab === tabId;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-current", on ? "page" : "false");
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("hidden", panel.id !== `tab-${tabId}`);
  });
  const titleKey = TAB_TITLE_KEYS[tabId] || "app.title";
  const titleEl = $("brandTitle");
  if (titleEl) {
    titleEl.textContent = t(titleKey);
    titleEl.setAttribute("data-i18n", titleKey);
  }
  $("overviewQuickBar")?.classList.toggle("hidden", tabId !== "overview");
  const content = document.querySelector(".app-content");
  if (content) content.scrollTop = 0;
  window.scrollTo(0, 0);
  trackFeatureUsage(tabId);
  if (tabId === "enterprise") syncEnterpriseFrame();
  if (tabId === "tools") {
    requestAnimationFrame(() => {
      refreshGeofenceMap();
      setTimeout(refreshGeofenceMap, 350);
    });
  }
}

function renderOverviewQuickBar() {
  const bar = $("overviewQuickBar");
  if (!bar) return;
  const items = [
    { tab: "inbox", label: t("overview.quick.inbox"), icon: "📥" },
    { tab: "workers", label: t("overview.quick.workers"), icon: "👷" },
    { tab: "workers", label: t("deployment.planBtn"), icon: "📋", highlight: "deployment" },
    { tab: "access", label: t("overview.quick.access"), icon: "✓" },
    { tab: "copilot", label: t("overview.quick.copilot"), icon: "✦" },
  ];
  bar.innerHTML = items
    .map(
      (item) =>
        `<button type="button" class="quick-bar-btn" data-goto-tab="${item.tab}"${item.highlight ? ` data-highlight="${item.highlight}"` : ""}><span class="quick-bar-icon" aria-hidden="true">${item.icon}</span><span>${item.label}</span></button>`,
    )
    .join("");
  bar.querySelectorAll("[data-goto-tab]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      switchToTab(btn.getAttribute("data-goto-tab"));
      try {
        await refreshActiveTab();
        if (btn.getAttribute("data-highlight") === "deployment") {
          await focusDeploymentSection();
        }
      } catch (err) {
        notifyTabError(err);
      }
    });
  });
}

function openCommandPalette() {
  const pal = $("commandPalette");
  if (!pal) return;
  pal.classList.remove("hidden");
  pal.setAttribute("aria-hidden", "false");
  document.body.classList.add("command-palette-open");
  commandPaletteIndex = 0;
  renderCommandPaletteList(($("commandPaletteInput")?.value || "").trim());
  const input = $("commandPaletteInput");
  if (input) {
    input.value = "";
    setTimeout(() => input.focus(), 0);
  }
}

function closeCommandPalette() {
  const pal = $("commandPalette");
  if (!pal) return;
  pal.classList.add("hidden");
  pal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("command-palette-open");
}

function renderCommandPaletteList(query) {
  const list = $("commandPaletteList");
  if (!list) return;
  const q = query.toLowerCase();
  commandPaletteFiltered = COMMAND_NAV.filter((item) => {
    if (isEmbedMode() && item.tab === "enterprise" && item.titleKey === "tab.enterprise") {
      return false;
    }
    if (item.tab === "analytics" && !canAccessAnalyticsTab()) {
      return false;
    }
    const title = t(item.titleKey).toLowerCase();
    const group = t(item.groupKey || "").toLowerCase();
    const extra = String(item.searchTerms || "").toLowerCase();
    if (!q) return true;
    return title.includes(q) || group.includes(q) || extra.includes(q) || (item.tab || "").includes(q);
  });
  if (commandPaletteIndex >= commandPaletteFiltered.length) {
    commandPaletteIndex = Math.max(0, commandPaletteFiltered.length - 1);
  }
  list.innerHTML = commandPaletteFiltered
    .map((item, i) => {
      const title = t(item.titleKey);
      const group = t(item.groupKey || "");
      const active = i === commandPaletteIndex ? " command-item-active" : "";
      if (item.href) {
        return `<li><a class="command-item${active}" href="${item.href}" data-cmd-idx="${i}"><span>${title}</span><span class="muted small">${group}</span></a></li>`;
      }
      return `<li><button type="button" class="command-item${active}" data-cmd-tab="${item.tab}" data-cmd-idx="${i}"><span>${title}</span><span class="muted small">${group}</span></button></li>`;
    })
    .join("");
  list.querySelectorAll("[data-cmd-idx]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      const idx = parseInt(el.getAttribute("data-cmd-idx"), 10);
      activateCommandItem(commandPaletteFiltered[idx]).catch(notifyTabError);
    });
  });
}

function initCommandPalette() {
  if (initCommandPalette._done) return;
  initCommandPalette._done = true;
  $("openCommandPaletteBtn")?.addEventListener("click", openCommandPalette);
  $("openCommandPaletteBtnTop")?.addEventListener("click", openCommandPalette);
  $("commandPalette")?.querySelectorAll("[data-cmd-close]").forEach((el) => {
    el.addEventListener("click", closeCommandPalette);
  });
  $("commandPaletteInput")?.addEventListener("input", (e) => {
    commandPaletteIndex = 0;
    renderCommandPaletteList(e.target.value.trim());
  });
  $("commandPaletteInput")?.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "ArrowDown") {
      e.preventDefault();
      commandPaletteIndex = Math.min(commandPaletteIndex + 1, commandPaletteFiltered.length - 1);
      renderCommandPaletteList(e.target.value.trim());
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      commandPaletteIndex = Math.max(commandPaletteIndex - 1, 0);
      renderCommandPaletteList(e.target.value.trim());
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = commandPaletteFiltered[commandPaletteIndex];
      activateCommandItem(item).catch(notifyTabError);
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeCommandPalette();
    }
  });
  document.addEventListener(
    "keydown",
    (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        e.stopPropagation();
        if ($("dashboardView")?.classList.contains("hidden")) return;
        openCommandPalette();
      } else if (e.key === "Escape" && !$("commandPalette")?.classList.contains("hidden")) {
        e.preventDefault();
        e.stopPropagation();
        closeCommandPalette();
      }
    },
    true,
  );
}

function renderQuickLinks() {
  const items = [
    { tab: "enterprise", title: t("quick.enterprise.title"), desc: t("quick.enterprise.desc") },
    { tab: "workers", title: t("quick.workers.title"), desc: t("quick.workers.desc") },
    { tab: "access", title: t("quick.access.title"), desc: t("quick.access.desc") },
    { tab: "mobile", title: t("quick.mobile.title"), desc: t("quick.mobile.desc") },
    { tab: "inbox", title: t("tab.inbox"), desc: t("section.inbox.desc") },
    { tab: "copilot", title: t("section.copilot.title"), desc: t("section.copilot.desc") },
    { tab: "operations", title: t("quick.operations.title"), desc: t("quick.operations.desc") },
    { tab: "tools", title: t("quick.tools.title"), desc: t("quick.tools.desc") },
    { tab: "platform", title: t("quick.platform.title"), desc: t("quick.platform.desc") },
    { tab: null, title: t("quick.legacy.title"), desc: t("quick.legacy.desc"), href: "/index.html" },
  ];
  $("quickLinks").innerHTML = items
    .map((item) => {
      if (item.href) {
        return `<a class="feature-card" href="${item.href}"><h3>${item.title}</h3><p class="muted small">${item.desc}</p></a>`;
      }
      return `<button type="button" class="feature-card" data-goto-tab="${item.tab}"><h3>${item.title}</h3><p class="muted small">${item.desc}</p></button>`;
    })
    .join("");
  $("quickLinks").querySelectorAll("[data-goto-tab]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      switchToTab(btn.getAttribute("data-goto-tab"));
      await refreshActiveTab();
    });
  });
}

async function loadPlatformBanner() {
  const el = $("platformBanner");
  try {
    const [caps, ready] = await Promise.all([
      api("/api/platform/capabilities").catch(() => null),
      fetch("/api/health/ready").then((r) => r.json()).catch(() => null),
    ]);
    if (!caps && !ready) {
      el.classList.add("hidden");
      return;
    }
    const score = caps?.maturityScore ?? "—";
    const level = caps?.maturityLevel ?? "";
    const dbOk = ready?.checks?.database?.ok;
    const runtime = caps?.dataLayer?.runtime || ready?.checks?.database?.backend || "—";
    el.innerHTML = `
      <div>
        <span class="muted small">${t("platform.banner.maturity")}</span>
        <strong>${score}/100</strong>
        <span class="muted small">${level}</span>
      </div>
      <div>${t("platform.banner.database")}: <strong>${runtime}</strong> ${statusBadge(dbOk)}</div>
      <a href="/enterprise-hub.html?v=20260527e" class="btn-link platform-banner-enterprise-link" style="color:#fbbf24;font-weight:700">${t("platform.banner.enterpriseLink")}</a>
      <button type="button" class="btn-link" data-goto-tab="platform">${t("platform.banner.details")}</button>
    `;
    el.classList.remove("hidden");
    el.querySelector(".platform-banner-enterprise-link")?.addEventListener("click", (ev) => {
      if (requestEnterpriseHubInShell()) {
        ev.preventDefault();
      }
    });
    el.querySelector("[data-goto-tab]")?.addEventListener("click", async () => {
      switchToTab("platform");
      await loadPlatform();
    });
  } catch {
    el.classList.add("hidden");
  }
}

function bindWorkTimesPanelOnce(host) {
  if (!host || host.dataset.workTimesBound === "1") {
    return;
  }
  host.dataset.workTimesBound = "1";
  host.addEventListener("submit", async (ev) => {
    const form = ev.target;
    if (!form || form.id !== "workTimesForm") {
      return;
    }
    ev.preventDefault();
    const companyId = host.dataset.companyId || "";
    const cfg = host._workTimesCfg || {};
    const feedback = host.querySelector("#workTimesFeedback");
    const submitBtn = form.querySelector('button[type="submit"]');
    if (!companyId) {
      if (feedback) {
        feedback.textContent = t("workTimes.pickCompany");
        feedback.className = "work-times-feedback err";
      }
      showActionToast(t("workTimes.pickCompany"), true);
      return;
    }
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = t("common.sending");
    }
    if (feedback) {
      feedback.textContent = "";
      feedback.className = "work-times-feedback hidden";
    }
    const fd = new FormData(form);
    const accessMode = String(fd.get("accessMode") || cfg.accessMode || "gate");
    const siteApp = accessMode === "site_app";
    try {
      const saved = await api(`/api/companies/${encodeURIComponent(companyId)}/work-times`, {
        method: "PUT",
        body: JSON.stringify({
          workStartTime: "",
          workEndTime: "",
          accessMode,
          siteGeofenceRadiusMeters: Number(fd.get("siteGeofenceRadiusMeters") || cfg.siteGeofenceRadiusMeters || 80),
          siteAutoCheckin: siteApp ? fd.get("siteAutoCheckin") === "on" : cfg.siteAutoCheckin !== false,
          siteAutoLogoutOnLeave: siteApp ? fd.get("siteAutoLogoutOnLeave") === "on" : cfg.siteAutoLogoutOnLeave !== false,
          siteAutoProximityLogin: siteApp ? fd.get("siteAutoProximityLogin") === "on" : cfg.siteAutoProximityLogin !== false,
        }),
      });
      host._workTimesCfg = { ...cfg, ...saved };
      const msg = t("workTimes.saved");
      if (feedback) {
        feedback.textContent = msg;
        feedback.className = "work-times-feedback ok";
      }
      showActionToast(msg, false);
      await loadCompanyWorkTimesForm(companyId);
    } catch (e) {
      const errMsg = e.message || t("common.error");
      if (feedback) {
        feedback.textContent = errMsg;
        feedback.className = "work-times-feedback err";
      }
      showActionToast(errMsg, true);
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = t("workTimes.save");
      }
    }
  });
}

async function loadCompanyWorkTimesForm(companyId) {
  const host = $("workTimesPanel");
  if (!host) return;
  bindWorkTimesPanelOnce(host);
  if (!companyId) {
    host.dataset.companyId = "";
    host._workTimesCfg = {};
    host.innerHTML = `<p class="muted small">${t("workTimes.pickCompany")}</p>`;
    return;
  }
  host.dataset.companyId = companyId;
  try {
    const cfg = await api(`/api/companies/${encodeURIComponent(companyId)}/work-times`);
    host._workTimesCfg = cfg;
    const accessMode = String(cfg.accessMode || "gate").toLowerCase() === "site_app" ? "site_app" : "gate";
    const siteRadius = Number(cfg.siteGeofenceRadiusMeters || 80);
    const siteFieldsHidden = accessMode !== "site_app";
    host.innerHTML = `
      <h3>${t("workTimes.title")}</h3>
      <p class="muted small">${t("workTimes.hint")}</p>
      <p id="workTimesFeedback" class="work-times-feedback hidden" role="status"></p>
      <form id="workTimesForm" class="tool-form access-settings-form">
        <label>${t("workTimes.accessMode")}
          <select name="accessMode" id="workTimesAccessMode">
            <option value="gate"${accessMode === "gate" ? " selected" : ""}>${t("workTimes.accessGate")}</option>
            <option value="site_app"${accessMode === "site_app" ? " selected" : ""}>${t("workTimes.accessSiteApp")}</option>
          </select>
        </label>
        <fieldset id="workTimesSiteFieldset" class="access-settings-fieldset${siteFieldsHidden ? " hidden" : ""}">
          <legend>${t("workTimes.siteAccessLegend")}</legend>
          <label>${t("workTimes.siteRadius")}
            <input name="siteGeofenceRadiusMeters" type="number" min="20" max="500" step="5" value="${siteRadius}" />
          </label>
          <label class="checkbox-row"><input name="siteAutoProximityLogin" type="checkbox"${cfg.siteAutoProximityLogin !== false ? " checked" : ""} /> ${t("workTimes.siteAutoProximity")}</label>
          <label class="checkbox-row"><input name="siteAutoCheckin" type="checkbox"${cfg.siteAutoCheckin !== false ? " checked" : ""} /> ${t("workTimes.siteAutoCheckin")}</label>
          <label class="checkbox-row"><input name="siteAutoLogoutOnLeave" type="checkbox"${cfg.siteAutoLogoutOnLeave !== false ? " checked" : ""} /> ${t("workTimes.siteAutoLogout")}</label>
          <p class="muted small">${t("workTimes.siteAccessHint")}</p>
        </fieldset>
        <button type="submit">${t("workTimes.save")}</button>
      </form>`;
    const accessModeEl = host.querySelector("#workTimesAccessMode");
    const siteFieldset = host.querySelector("#workTimesSiteFieldset");
    const syncSiteAccessFields = () => {
      const siteApp = accessModeEl?.value === "site_app";
      siteFieldset?.classList.toggle("hidden", !siteApp);
    };
    accessModeEl?.addEventListener("change", syncSiteAccessFields);
  } catch (e) {
    host.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

const AUTOPILOT_KEYS = [
  "autoAckInfoAlerts",
  "autoNotifyDocExpiry",
  "autoDailySecurityScan",
  "autoSeedAutomationRules",
  "autoEnsureScheduledReport",
  "autoInboxBulkDocPush",
  "autoInboxAckLowSecurity",
];

const AUTOPILOT_LABEL_KEYS = {
  autoAckInfoAlerts: "autopilot.ackInfo",
  autoNotifyDocExpiry: "autopilot.docPush",
  autoDailySecurityScan: "autopilot.security",
  autoSeedAutomationRules: "autopilot.rules",
  autoEnsureScheduledReport: "autopilot.report",
  autoInboxBulkDocPush: "autopilot.inboxDoc",
  autoInboxAckLowSecurity: "autopilot.inboxSec",
  autoPrepareNextMonthDeployment: "autopilot.prepareNext",
};

let deploymentModalWorkerId = null;
let deploymentMonthState = null;
let deploymentModalDays = [];

function deploymentMonthParts() {
  const raw = $("deploymentMonth")?.value || "";
  const [y, m] = raw.split("-").map((x) => parseInt(x, 10));
  if (!y || !m) {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() + 1 };
  }
  return { year: y, month: m };
}

function isoToTimeInput(iso) {
  const s = String(iso || "").trim();
  if (!s) return "";
  if (s.length >= 16 && s.includes("T")) return s.slice(11, 16);
  if (/^\d{1,2}:\d{2}/.test(s)) return s.slice(0, 5);
  return "";
}

function timeInputToIso(dateStr, hhmm) {
  const date = String(dateStr || "").trim().slice(0, 10);
  const t = String(hhmm || "").trim();
  if (!date || !t) return "";
  const parts = t.split(":");
  const h = parseInt(parts[0], 10);
  const m = parseInt(parts[1], 10);
  if (Number.isNaN(h) || Number.isNaN(m)) return "";
  return `${date}T${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:00`;
}

function escapeAttr(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}

function readDeploymentDaysFromForm() {
  const host = $("deploymentDaysList");
  if (!host) return;
  host.querySelectorAll(".deployment-day-row[data-dep-idx]").forEach((row) => {
    const i = parseInt(row.getAttribute("data-dep-idx"), 10);
    const d = deploymentModalDays[i];
    if (!d) return;
    d.location = row.querySelector('[data-dep-field="location"]')?.value.trim() || "";
    d.shiftStart = timeInputToIso(d.date, row.querySelector('[data-dep-field="start"]')?.value);
    d.shiftEnd = timeInputToIso(d.date, row.querySelector('[data-dep-field="end"]')?.value);
    d.notes = row.querySelector('[data-dep-field="notes"]')?.value.trim() || "";
    d.dayColor = row.querySelector('[data-dep-field="color"]')?.value || "";
  });
}

function wireDeploymentDayRowActions() {
  const host = $("deploymentDaysList");
  if (!host) return;
  host.querySelectorAll("[data-dep-clear]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const i = parseInt(btn.getAttribute("data-dep-clear"), 10);
      const d = deploymentModalDays[i];
      if (!d) return;
      d.location = "Frei";
      d.shiftStart = "";
      d.shiftEnd = "";
      d.notes = "";
      d.dayType = "free";
      renderDeploymentDaysList();
    });
  });
  host.querySelectorAll("[data-dep-free]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const i = parseInt(btn.getAttribute("data-dep-free"), 10);
      const d = deploymentModalDays[i];
      if (!d) return;
      d.location = "Frei";
      d.shiftStart = "";
      d.shiftEnd = "";
      d.dayType = "free";
      if (!d.dayColor) d.dayColor = "#10b981";
      renderDeploymentDaysList();
    });
  });
  host.querySelectorAll('[data-dep-field="color"]').forEach((input) => {
    input.addEventListener("input", () => {
      const row = input.closest(".deployment-day-row");
      if (!row) return;
      const value = String(input.value || "").trim();
      if (value) {
        row.style.setProperty("--dep-row-color", value);
      } else {
        row.style.removeProperty("--dep-row-color");
      }
    });
  });
}

function renderDeploymentDaysList() {
  const host = $("deploymentDaysList");
  if (!host) return;
  const header = `
    <div class="deployment-days-header" role="row">
      <span>${t("deployment.colDay")}</span>
      <span>${t("deployment.colLocation")}</span>
      <span>${t("deployment.colStart")}</span>
      <span>${t("deployment.colEnd")}</span>
      <span>${t("deployment.colNotes")}</span>
      <span>${t("deployment.colColor")}</span>
      <span></span>
    </div>`;
  const rows = deploymentModalDays
    .map((d, i) => {
      const loc = escapeAttr(d.location || "");
      const notes = escapeAttr(d.notes || "");
      const start = escapeAttr(isoToTimeInput(d.shiftStart));
      const end = escapeAttr(isoToTimeInput(d.shiftEnd));
      const color = escapeAttr(d.dayColor || d.day_color || "#1f6feb");
      const isFree = !loc || /^(frei|free|off|aus|urlaub)$/i.test(loc.trim());
      const declined =
        String(d.workerResponse || "") === "declined" || Boolean(d.isDeclined);
      const reasonText = String(d.declineReason || "").trim();
      const declineHint = declined
        ? `<span class="deployment-day-declined">${escapeAttr(t("deployment.workerDeclined"))}</span>`
        : "";
      const declineReasonBlock =
        declined && reasonText
          ? `<p class="deployment-decline-reason"><strong>${escapeAttr(t("deployment.declineReasonLabel"))}:</strong> ${escapeAttr(reasonText)}</p>`
          : declined
            ? `<p class="deployment-decline-reason muted small">${escapeAttr(t("deployment.workerDeclined"))} — ${escapeAttr(t("deployment.noDeclineReason"))}</p>`
            : "";
      const rowColor = escapeAttr(d.dayColor || d.day_color || "");
      return `
      <div class="deployment-day-row${d.isWeekend ? " weekend" : ""}${declined ? " worker-declined" : ""}${isFree ? " is-free-day" : ""}" data-dep-idx="${i}" role="row"${rowColor ? ` style="--dep-row-color:${rowColor}"` : ""}>
        <span class="deployment-day-meta">${d.date.slice(8, 10)}.${d.date.slice(5, 7)}.<br /><span class="deployment-weekday">${d.weekday}</span>${declineHint}${declineReasonBlock}</span>
        <input type="text" data-dep-field="location" value="${loc}" placeholder="${escapeAttr(t("deployment.locationPh"))}" aria-label="${escapeAttr(t("deployment.colLocation"))} ${d.date}" />
        <input type="time" data-dep-field="start" value="${start}" aria-label="${escapeAttr(t("deployment.colStart"))} ${d.date}" />
        <input type="time" data-dep-field="end" value="${end}" aria-label="${escapeAttr(t("deployment.colEnd"))} ${d.date}" />
        <input type="text" data-dep-field="notes" value="${notes}" placeholder="${escapeAttr(t("deployment.notesPh"))}" aria-label="${escapeAttr(t("deployment.colNotes"))} ${d.date}" />
        <input type="color" class="deployment-day-color" data-dep-field="color" value="${color}" title="${escapeAttr(t("deployment.colColor"))}" aria-label="${escapeAttr(t("deployment.colColor"))} ${d.date}" />
        <div class="deployment-day-actions-inline">
          <button type="button" class="ghost deployment-day-free" data-dep-free="${i}">${escapeAttr(t("deployment.markFree"))}</button>
          <button type="button" class="ghost deployment-day-clear" data-dep-clear="${i}">${escapeAttr(t("deployment.clearDay"))}</button>
        </div>
      </div>`;
    })
    .join("");
  host.innerHTML = header + rows;
  wireDeploymentDayRowActions();
}

async function openDeploymentModal(workerId, workerName, focusWorkDate) {
  deploymentModalWorkerId = workerId;
  $("deploymentModalWorker").textContent = workerName;
  const now = new Date();
  $("deploymentMonth").value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  $("deploymentModal").classList.remove("hidden");
  const scrollHost = $("deploymentModalScroll");
  if (scrollHost) {
    scrollHost.scrollTop = 0;
    window.setTimeout(() => scrollHost.focus({ preventScroll: true }), 50);
  }
  await reloadDeploymentPlan();
  if (focusWorkDate) {
    window.setTimeout(() => scrollDeploymentModalToDate(focusWorkDate), 80);
  } else if (scrollHost) {
    scrollHost.scrollTop = 0;
  }
}

function scrollDeploymentModalToDate(workDate) {
  const iso = String(workDate || "").slice(0, 10);
  if (!iso) return;
  const host = $("deploymentDaysList");
  const scrollHost = $("deploymentModalScroll");
  const idx = deploymentModalDays.findIndex((d) => String(d.date || "").slice(0, 10) === iso);
  if (idx < 0 || !host) return;
  const row = host.querySelector(`[data-dep-idx="${idx}"]`);
  if (!row) return;
  row.classList.add("deployment-day-highlight");
  window.setTimeout(() => row.classList.remove("deployment-day-highlight"), 3200);
  if (scrollHost) {
    const top = row.offsetTop - Math.max(0, (scrollHost.clientHeight - row.clientHeight) / 2);
    scrollHost.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  } else {
    row.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}

async function acknowledgeDeploymentDecline(item) {
  const q = companyQuery();
  await api(`/api/workforce/deployment-decline/acknowledge${q}`, {
    method: "POST",
    body: JSON.stringify({
      workerId: item.workerId,
      workDate: String(item.workDate || "").slice(0, 10),
    }),
  });
}

async function handleDeploymentDeclineClick(item) {
  await acknowledgeDeploymentDecline(item);
  const wname = String(item.workerName || item.workerId || "").trim();
  const workDate = String(item.workDate || "").slice(0, 10);
  await openDeploymentModal(item.workerId, wname, workDate);
  await loadDeploymentMonthBar();
}

async function reloadDeploymentPlan() {
  const q = companyQuery();
  const { year, month } = deploymentMonthParts();
  if (!deploymentModalWorkerId) return;
  try {
    const data = await api(
      `/api/workforce/deployment-plan${q}${q ? "&" : "?"}worker_id=${encodeURIComponent(deploymentModalWorkerId)}&year=${year}&month=${month}&lang=${getLang().slice(0, 2)}`,
    );
    deploymentModalDays = data.days || [];
    const declined = Number(data.declinedDayCount || 0);
    const metaEl = document.getElementById("deploymentModalDeclinedMeta");
    if (metaEl) {
      if (declined > 0) {
        metaEl.textContent = t("deployment.modalDeclinedDays", { count: declined });
        metaEl.classList.remove("hidden");
      } else {
        metaEl.textContent = "";
        metaEl.classList.add("hidden");
      }
    }
    if (!data.capabilities?.pdf) {
      $("deploymentPdfBtn")?.setAttribute("title", t("deployment.needPro"));
    }
    const mb = data.monthBatch || {};
    const sendHint =
      mb.status === "sent" && !mb.awaitingConfirm
        ? ` (${t("deployment.statusSent")})`
        : ` (${t("deployment.statusAwaiting")})`;
    $("deploymentSendBtn")?.setAttribute("title", t("deployment.monthHint") + sendHint);
    renderDeploymentDaysList();
  } catch (e) {
    deploymentModalDays = [];
    renderDeploymentDaysList();
    showActionToast(e.message, true);
  }
}

async function saveDeploymentPlan() {
  const q = companyQuery();
  const { year, month } = deploymentMonthParts();
  readDeploymentDaysFromForm();
  const days = deploymentModalDays.map((d) => ({
    date: d.date,
    location: d.location,
    notes: d.notes || "",
    shiftStart: d.shiftStart,
    shiftEnd: d.shiftEnd,
    dayColor: d.dayColor || d.day_color || "",
    dayType: d.dayType || (/^(frei|free)$/i.test(String(d.location || "").trim()) ? "free" : ""),
  }));
  await api(`/api/workforce/deployment-plan${q}`, {
    method: "PUT",
    body: JSON.stringify({ workerId: deploymentModalWorkerId, year, month, days }),
  });
  showActionToast(t("deployment.saved"), false);
  await loadDeploymentMonthBar().catch(() => {});
}

let deploymentPdfPreviewObjectUrl = "";
let deploymentBrandingPdfPreviewUrl = "";

async function fetchDeploymentBrandingPdfBlob() {
  const q = companyQuery();
  const token = wpGet(TOKEN_KEY);
  const res = await fetch(`/api/workforce/deployment-plan/pdf/branding-preview${q}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ lang: getLang().slice(0, 2) }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || err.error || res.statusText);
  }
  return res.blob();
}

function closeDeploymentBrandingPdfPreview() {
  const modal = $("deploymentBrandingPdfModal");
  const frame = $("deploymentBrandingPdfFrame");
  if (modal) modal.classList.add("hidden");
  if (frame) frame.removeAttribute("src");
  if (deploymentBrandingPdfPreviewUrl) {
    URL.revokeObjectURL(deploymentBrandingPdfPreviewUrl);
    deploymentBrandingPdfPreviewUrl = "";
  }
}

async function previewDeploymentBrandingPdf() {
  const modal = $("deploymentBrandingPdfModal");
  const frame = $("deploymentBrandingPdfFrame");
  if (!modal || !frame) return;
  const blob = await fetchDeploymentBrandingPdfBlob();
  if (deploymentBrandingPdfPreviewUrl) {
    URL.revokeObjectURL(deploymentBrandingPdfPreviewUrl);
  }
  deploymentBrandingPdfPreviewUrl = URL.createObjectURL(blob);
  frame.src = deploymentBrandingPdfPreviewUrl;
  modal.classList.remove("hidden");
}

async function fetchDeploymentPdfBlob() {
  const q = companyQuery();
  const { year, month } = deploymentMonthParts();
  await saveDeploymentPlan();
  const token = wpGet(TOKEN_KEY);
  const res = await fetch(`/api/workforce/deployment-plan/pdf${q}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      workerId: deploymentModalWorkerId,
      year,
      month,
      lang: getLang().slice(0, 2),
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || err.error || res.statusText);
  }
  return res.blob();
}

function closeDeploymentPdfPreview() {
  const modal = $("deploymentPdfPreviewModal");
  const frame = $("deploymentPdfPreviewFrame");
  if (modal) modal.classList.add("hidden");
  if (frame) frame.removeAttribute("src");
  if (deploymentPdfPreviewObjectUrl) {
    URL.revokeObjectURL(deploymentPdfPreviewObjectUrl);
    deploymentPdfPreviewObjectUrl = "";
  }
}

async function previewCompanyBrandingPdf() {
  const cid = activeCompanyId();
  if (!cid) {
    showActionToast(t("common.selectCompany"), true);
    return;
  }
  const modal = $("deploymentPdfPreviewModal");
  const frame = $("deploymentPdfPreviewFrame");
  if (!modal || !frame) {
    showActionToast(t("common.error"), true);
    return;
  }
  const token = wpGet(TOKEN_KEY);
  const res = await fetch(
    `/api/workforce/deployment-plan/pdf/branding-preview?company_id=${encodeURIComponent(cid)}`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ lang: getLang().slice(0, 2) }),
    },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || err.error || res.statusText);
  }
  const blob = await res.blob();
  if (deploymentPdfPreviewObjectUrl) {
    URL.revokeObjectURL(deploymentPdfPreviewObjectUrl);
  }
  deploymentPdfPreviewObjectUrl = URL.createObjectURL(blob);
  frame.src = deploymentPdfPreviewObjectUrl;
  modal.classList.remove("hidden");
}

async function previewDeploymentPdf() {
  const modal = $("deploymentPdfPreviewModal");
  const frame = $("deploymentPdfPreviewFrame");
  if (!modal || !frame) {
    return downloadDeploymentPdf();
  }
  const blob = await fetchDeploymentPdfBlob();
  if (deploymentPdfPreviewObjectUrl) {
    URL.revokeObjectURL(deploymentPdfPreviewObjectUrl);
  }
  deploymentPdfPreviewObjectUrl = URL.createObjectURL(blob);
  frame.src = deploymentPdfPreviewObjectUrl;
  modal.classList.remove("hidden");
}

async function downloadDeploymentPdf() {
  const { year, month } = deploymentMonthParts();
  const blob = await fetchDeploymentPdfBlob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `einsatzplan-${deploymentModalWorkerId}-${year}-${month}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

function bindDeploymentModalOnce() {
  if (bindDeploymentModalOnce._done) return;
  bindDeploymentModalOnce._done = true;
  $("deploymentMonth")?.addEventListener("change", () => reloadDeploymentPlan().catch((e) => showActionToast(e.message, true)));
  $("deploymentCloseBtn")?.addEventListener("click", () => $("deploymentModal").classList.add("hidden"));
  $("deploymentModal")?.addEventListener("click", (e) => {
    if (e.target?.id === "deploymentModal") $("deploymentModal").classList.add("hidden");
  });
  $("deploymentSaveBtn")?.addEventListener("click", () => saveDeploymentPlan().catch((e) => showActionToast(e.message, true)));
  $("deploymentPdfPreviewBtn")?.addEventListener("click", () =>
    previewDeploymentPdf().catch((e) => showActionToast(e.message, true)),
  );
  $("deploymentPdfBtn")?.addEventListener("click", () => downloadDeploymentPdf().catch((e) => showActionToast(e.message, true)));
  $("deploymentPdfPreviewCloseBtn")?.addEventListener("click", closeDeploymentPdfPreview);
  $("deploymentPdfPreviewModal")?.addEventListener("click", (e) => {
    if (e.target?.id === "deploymentPdfPreviewModal") closeDeploymentPdfPreview();
  });
  $("deploymentPdfPreviewDownloadBtn")?.addEventListener("click", () =>
    downloadDeploymentPdf().catch((e) => showActionToast(e.message, true)),
  );
  $("deploymentPdfPreviewPrintBtn")?.addEventListener("click", () => {
    const frame = $("deploymentPdfPreviewFrame");
    try {
      frame?.contentWindow?.focus();
      frame?.contentWindow?.print();
    } catch {
      showActionToast(t("common.error"), true);
    }
  });
  $("deploymentSendBtn")?.addEventListener("click", async () => {
    const q = companyQuery();
    const { year, month } = deploymentMonthParts();
    await saveDeploymentPlan();
    const res = await api(`/api/workforce/deployment-plan/distribute${q}`, {
      method: "POST",
      body: JSON.stringify({ workerId: deploymentModalWorkerId, year, month, lang: getLang().slice(0, 2) }),
    });
    showActionToast(res.ok ? t("deployment.send") + " ✓" : res.emailError || t("common.error"), !res.ok);
    if (res.ok) {
      await reloadDeploymentPlan();
      await loadDeploymentMonthBar();
    }
  });
  $("deploymentFromShifts")?.addEventListener("click", async () => {
    const q = companyQuery();
    const { year, month } = deploymentMonthParts();
    await api(`/api/workforce/deployment-plan/from-shifts${q}`, {
      method: "POST",
      body: JSON.stringify({ workerId: deploymentModalWorkerId, year, month }),
    });
    await reloadDeploymentPlan();
    showActionToast(t("deployment.fromShifts") + " ✓", false);
  });
  $("deploymentBulkWeekdays")?.addEventListener("click", () => {
    readDeploymentDaysFromForm();
    const loc = $("deploymentBulkLocation")?.value.trim() || "";
    const start = $("deploymentBulkStart")?.value || "";
    const end = $("deploymentBulkEnd")?.value || "";
    deploymentModalDays.forEach((d) => {
      if (d.isWeekend) return;
      if (loc) d.location = loc;
      if (start) d.shiftStart = timeInputToIso(d.date, start);
      if (end) d.shiftEnd = timeInputToIso(d.date, end);
    });
    renderDeploymentDaysList();
    showActionToast(t("deployment.bulkApplied"), false);
  });
  $("deploymentBulkClearWeekends")?.addEventListener("click", () => {
    readDeploymentDaysFromForm();
    deploymentModalDays.forEach((d) => {
      if (!d.isWeekend) return;
      d.location = "";
      d.shiftStart = "";
      d.shiftEnd = "";
      d.notes = "";
    });
    renderDeploymentDaysList();
  });
  $("deploymentRotation")?.addEventListener("click", async () => {
    const raw = prompt(
      "Orte (kommagetrennt), z.B.\nBerlin Mitte, Alexanderplatz, Potsdam",
      "Berlin Mitte, Alexanderplatz, Potsdam",
    );
    if (!raw) return;
    const locations = raw.split(",").map((s) => s.trim()).filter(Boolean);
    const q = companyQuery();
    const { year, month } = deploymentMonthParts();
    await api(`/api/workforce/deployment-plan/rotation${q}`, {
      method: "POST",
      body: JSON.stringify({ workerId: deploymentModalWorkerId, year, month, locations, skipWeekends: true }),
    });
    await reloadDeploymentPlan();
    showActionToast(t("deployment.rotation") + " ✓", false);
  });
}

function bindAutopilotPanel(host, settings) {
  if (!host) return;
  AUTOPILOT_KEYS.forEach((key) => {
    const el = host.querySelector(`[data-autopilot-key="${key}"]`);
    if (el) el.checked = !!settings[key];
  });
  host.querySelector("#autopilotSaveBtn")?.addEventListener("click", async () => {
    const q = companyQuery();
    const patch = {};
    AUTOPILOT_KEYS.forEach((key) => {
      const el = host.querySelector(`[data-autopilot-key="${key}"]`);
      if (el) patch[key] = !!el.checked;
    });
    try {
      await api(`/api/platform/autopilot/settings${q}`, {
        method: "PATCH",
        body: JSON.stringify({ settings: patch }),
      });
      showActionToast(t("autopilot.saved"), false);
    } catch (e) {
      showActionToast(e.message, true);
    }
  });
  host.querySelector("#autopilotRunBtn")?.addEventListener("click", async () => {
    const q = companyQuery();
    try {
      const res = await api(`/api/platform/autopilot/run${q}`, { method: "POST", body: "{}" });
      const tot = res.totals || res;
      const msg = `${t("autopilot.ran")} ${JSON.stringify(tot).slice(0, 120)}`;
      showActionToast(msg, false);
    } catch (e) {
      showActionToast(e.message, true);
    }
  });
}

async function loadPlatform() {
  if (!isSuperadminUser()) {
    switchToTab("overview");
    return;
  }
  const panel = $("platformPanel");
  panel.innerHTML = `<p class="muted">${t("common.loading")}</p>`;
  const cid = activeCompanyId();
  try {
    const [caps, ready, health, ent, aiSt, wallet, setup, pushSt, mobileDist, autopilot] = await Promise.all([
      api("/api/platform/capabilities"),
      fetch("/api/health/ready").then((r) => r.json()),
      fetch("/api/health").then((r) => r.json()).catch(() => ({})),
      api("/api/platform/entitlements").catch(() => null),
      api("/api/ai/status").catch(() => ({ configured: false })),
      api("/api/admin/wallet/runtime-status").catch(() => null),
      fetch("/api/platform/setup-status").then((r) => r.json()).catch(() => null),
      api("/api/platform/push/status").catch(() => null),
      api("/api/v2/mobile/distribution").catch(() => null),
      cid
        ? api(`/api/platform/autopilot/settings${companyQuery()}`).catch(() => ({ settings: {} }))
        : Promise.resolve({ settings: {} }),
    ]);
    const ap = autopilot?.settings || {};
    const autopilotToggles = AUTOPILOT_KEYS.map(
      (key) => `
        <label class="autopilot-toggle">
          <input type="checkbox" data-autopilot-key="${key}" ${ap[key] !== false ? "checked" : ""} />
          <span>${t(AUTOPILOT_LABEL_KEYS[key])}</span>
        </label>`,
    ).join("");
    const db = setup?.database || {};
    const dbBannerClass = db.loginReady === false ? "warn" : "ok";
    const dbBanner = setup
      ? `<div class="platform-setup-banner ${dbBannerClass}">
        <strong>${t("platform.dbHealth")}</strong>
        <p class="muted small">${db.loginReady ? t("platform.dbReady") : t("platform.dbNotReady")}
        · ${db.sqliteFileExists ? t("platform.dbFileOk") : t("platform.dbFileMissing")}
        · ${db.persistent ? t("platform.dbPersistent") : t("platform.dbEphemeral")}
        ${db.sqliteSizeBytes ? ` · ${Math.round(Number(db.sqliteSizeBytes) / 1024)} KB` : ""}</p>
        ${(db.railwayHints || []).map((h) => `<p class="muted small">${escapeHtml(h)}</p>`).join("")}
      </div>`
      : "";
    const setupLines = (setup?.readyScore?.missing || [])
      .map((m) => `<li class="miss">○ ${escapeHtml(m)}</li>`)
      .join("");
    const setupOk = setup
      ? `<p>${t("platform.setup.railway")}: <strong>${setup.readyScore?.percent ?? 0}%</strong></p><ul class="setup-checklist">${setupLines || `<li class="ok">${t("platform.setup.allOk")}</li>`}</ul>`
      : "";
    const steps = (caps.nextSteps || [])
      .map((s) => `<li>${s}</li>`)
      .join("");
    const attendance = caps.attendance || {};
    const attRows = Object.entries(attendance)
      .map(([k, v]) => `<tr><td>${k}</td><td>${statusBadge(!!v)}</td></tr>`)
      .join("");
    panel.innerHTML = `
      <p class="admin-superadmin-banner">${t("platform.superadminOnly")}</p>
      ${dbBanner}
      <div class="platform-panel-grid">
      <div class="panel-block" id="workTimesPanel"></div>
      ${
        cid
          ? `<div class="panel-block autopilot-panel" id="autopilotPanel">
        <h3>${t("autopilot.title")}</h3>
        <p class="muted small">${t("autopilot.desc")}</p>
        <div class="autopilot-toggles">${autopilotToggles}</div>
        <div class="autopilot-actions">
          <button type="button" id="autopilotSaveBtn">${t("common.save")}</button>
          <button type="button" class="ghost" id="autopilotRunBtn">${t("autopilot.runNow")}</button>
        </div>
      </div>`
          : `<p class="muted small panel-block">${t("common.selectCompany")}</p>`
      }
      <div class="panel-block">${setupOk}</div>
      <div class="panel-block">
        <h3>${t("platform.globalMaturity")} <span class="badge badge-ok">${caps.maturityScore}/100</span></h3>
        <p class="muted">${caps.maturityLevel || ""}</p>
        ${steps ? `<ul class="muted small">${steps}</ul>` : ""}
      </div>
      <div class="panel-block">
        <h3>${t("platform.infrastructure")}</h3>
        <p>${t("platform.runtime")}: <strong>${caps.dataLayer?.runtime || "—"}</strong> · Redis: ${statusBadge(caps.dataLayer?.redisConfigured)} · Queues: ${statusBadge(caps.dataLayer?.taskQueuesReady)}</p>
        <p class="muted small">Path: ${caps.dataLayer?.sqlitePath || ready.checks?.database?.path || "—"}</p>
        <p>${t("platform.readiness")}: ${statusBadge(ready.ready)} · Redis: ${health.checks?.redis?.status || health.redis?.status || ready.checks?.redis?.status || "—"}</p>
      </div>
      <div class="panel-block">
        <h3>${t("platform.attendanceCaps")}</h3>
        <div class="table-wrap"><table><tbody>${attRows}</tbody></table></div>
      </div>
      ${
        ent
          ? `<div class="panel-block">
        <h3>${t("platform.yourPlan")}: ${resolvePlanLabel(ent.planMeta, ent.plan)}</h3>
        <p>${t("platform.planSummary", {
          enabled: ent.entitlements?.enabledCount || 0,
          locked: ent.entitlements?.lockedCount || 0,
          pct: ent.entitlements?.coveragePercent || 0,
        })}</p>
        <div class="platform-plan-actions">
          <button type="button" class="feature-card" id="platformOpenEnterpriseBtn">${t("platform.openEnterprise")}</button>
          <button type="button" class="feature-card" id="platformOpenAiBtn">${t("platform.openAiCenter")}</button>
        </div>
      </div>`
          : ""
      }
      ${
        cid
          ? `<div class="panel-block">
        <h3>${t("platform.brandingPdfTitle")}</h3>
        <p class="muted small">${t("platform.brandingPdfHint")}</p>
        <button type="button" class="ghost" id="platformBrandingPdfBtn">${t("platform.brandingPdfBtn")}</button>
      </div>`
          : ""
      }
      <div class="panel-block">
        <h3>${t("platform.aiAssistant")} ${aiSt?.configured ? statusBadge(true) : statusBadge(false)}</h3>
        <p class="muted small">${t("platform.aiRequires")}</p>
        <form id="aiQuickForm" class="tool-form">
          <input name="question" placeholder="${t("platform.aiPlaceholder")}" required />
          <button type="submit">${t("common.send")}</button>
        </form>
        <pre id="aiQuickAnswer" class="ai-answer muted small"></pre>
      </div>
      <div class="panel-block">
        <h3>${t("platform.hybridApp")}</h3>
        <p>${pushSt?.fcmConfigured ? statusBadge(true) : statusBadge(false)} FCM · ${t("platform.hybridWorkers", { workers: pushSt?.workersWithPush ?? 0, devices: pushSt?.registeredDevices ?? 0 })}</p>
        <p class="muted small">${t("platform.hybridChannel")}: ${pushSt?.primaryChannel || "fcm"} · ${pushSt?.workerAppKind || "hybrid_native"}</p>
        ${
          mobileDist?.install
            ? `<p class="muted small">APK: ${mobileDist.install.apkUrl ? `<a href="${mobileDist.install.apkUrl}" target="_blank" rel="noopener">${t("common.download")}</a>` : t("platform.apkSet")}</p>`
            : ""
        }
        <button type="button" class="feature-card" data-goto-tab="mobile">${t("platform.mobileTab")}</button>
      </div>
      <div class="panel-block">
        <h3>${t("platform.wallet")}</h3>
        <p class="muted small">${wallet ? JSON.stringify(wallet, null, 2) : t("platform.walletLoading")}</p>
      </div>
      </div>
      <div class="link-row">
        <a href="/api/health/ready" target="_blank" rel="noopener">health/ready</a>
        <a href="/enterprise-hub.html?v=20260528a">${t("common.enterpriseHub")}</a>
        <a href="/index.html">${t("common.legacyDashboard")}</a>
      </div>
    `;
    await loadCompanyWorkTimesForm(cid);
    bindAutopilotPanel($("autopilotPanel"), ap);
    panel.querySelectorAll("[data-goto-tab]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        switchToTab(btn.getAttribute("data-goto-tab"));
        await refreshActiveTab();
      });
    });
    panel.querySelector("#platformOpenEnterpriseBtn")?.addEventListener("click", () => {
      if (requestEnterpriseHubInShell()) {
        return;
      }
      switchToTab("enterprise");
      syncEnterpriseFrame();
    });
    panel.querySelector("#platformOpenAiBtn")?.addEventListener("click", () => {
      navigateToOpsEmbed("/ai-command-center.html");
    });
    panel.querySelector("#platformBrandingPdfBtn")?.addEventListener("click", () =>
      previewCompanyBrandingPdf().catch((e) => showActionToast(e.message, true)),
    );
    $("aiQuickForm")?.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const q = ev.target.question.value.trim();
      const out = $("aiQuickAnswer");
      out.textContent = t("common.sending");
      try {
        const aiBody = { question: q, use_agent: true, agent_id: "operations", lang: getLang().slice(0, 2) };
        const user = getUser();
        const cid =
          wpGet(COMPANY_KEY) ||
          user.preview_company_id ||
          user.company_id ||
          "";
        if (cid) aiBody.company_id = cid;
        const res = await api("/api/ai/query", {
          method: "POST",
          body: JSON.stringify(aiBody),
        });
        out.textContent = res.answer || res.hint || res.error || JSON.stringify(res, null, 2);
      } catch (e) {
        out.textContent = e.data?.error === "feature_not_available"
          ? t("platform.upgradeRequired", { plan: e.data.requiredPlan })
          : e.message;
      }
    });
  } catch (e) {
    panel.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

function renderMobileChannelCard({ icon, title, desc, href, ready }) {
  if (href && ready) {
    return `
      <a href="${escapeHtml(href)}" target="_blank" rel="noopener" class="mobile-channel-card">
        <span class="mobile-channel-icon" aria-hidden="true">${icon}</span>
        <strong>${escapeHtml(title)}</strong>
        <span class="muted small">${escapeHtml(desc)}</span>
        ${statusBadge(true)}
        <span class="mobile-channel-cta">${t("mobile.channel.open")} →</span>
      </a>`;
  }
  return `
    <div class="mobile-channel-card mobile-channel-card--pending">
      <span class="mobile-channel-icon" aria-hidden="true">${icon}</span>
      <strong>${escapeHtml(title)}</strong>
      <span class="muted small">${escapeHtml(desc)}</span>
      ${statusBadge(false)}
      <span class="mobile-channel-hint muted small">${t("mobile.channel.setupHint")}</span>
    </div>`;
}

function resolveMobileModeLabel(mode) {
  const id = String(mode?.id || "").trim();
  const key = {
    app_qr_badge: "mobile.mode.qrBadge",
    gate_reader_nfc_rfid: "mobile.mode.nfcGate",
    hce_phone_card: "mobile.mode.hce",
  }[id];
  return key ? t(key) : mode?.label || id;
}

async function loadMobile() {
  const panel = $("mobilePanel");
  panel.innerHTML = `<p class="muted">${t("common.loading")}</p>`;
  try {
    const data = await api("/api/v2/mobile/distribution");
    const install = data.install || {};
    const native = data.nativeInstall || {};
    const pwaLegacy = data.pwaInstall || {};
    const joinUrl = install.joinPage || "/join.html";
    const channels = [
      {
        icon: "🤖",
        title: t("mobile.channel.android"),
        desc: t("mobile.channel.androidDesc"),
        href: install.apkUrl,
        ready: Boolean(install.apkUrl),
      },
      {
        icon: "🍎",
        title: t("mobile.channel.testflight"),
        desc: t("mobile.channel.testflightDesc"),
        href: install.testFlightUrl,
        ready: Boolean(install.testFlightUrl),
      },
      {
        icon: "▶️",
        title: t("mobile.channel.playStore"),
        desc: t("mobile.channel.playStoreDesc"),
        href: install.playStoreUrl,
        ready: Boolean(install.playStoreUrl),
      },
      {
        icon: "📲",
        title: t("mobile.channel.appStore"),
        desc: t("mobile.channel.appStoreDesc"),
        href: install.appStoreUrl,
        ready: Boolean(install.appStoreUrl),
      },
    ];
    const modeIcons = { app_qr_badge: "📱", gate_reader_nfc_rfid: "💳", hce_phone_card: "📡" };
    const modes = (data.hybridModes || [])
      .map(
        (m) => `
        <article class="mobile-mode-card">
          <span class="mobile-mode-icon" aria-hidden="true">${modeIcons[m.id] || "✓"}</span>
          <div>
            <strong>${escapeHtml(resolveMobileModeLabel(m))}</strong>
            <p class="muted small">${escapeHtml(m.note || m.api || "")}</p>
          </div>
        </article>`,
      )
      .join("");
    panel.innerHTML = `
      <div class="mobile-hero panel-block">
        <div class="mobile-hero-main">
          <div class="mobile-hero-brand">
            <img src="/branding/suppix-ai-mark.svg" alt="SUPPIX" class="mobile-hero-logo" width="44" height="44" />
            <div>
              <p class="mobile-hero-eyebrow">${t("mobile.kicker")}</p>
              <h2 class="mobile-hero-title">${t("mobile.title")}</h2>
            </div>
          </div>
          <p class="muted mobile-hero-sub">${t("mobile.subtitle")}</p>
        </div>
        <div class="mobile-hero-actions">
          <a href="${escapeHtml(joinUrl)}" target="_blank" rel="noopener" class="primary-button mobile-hero-btn">${t("mobile.qrOpen")}</a>
          <button type="button" class="ghost mobile-hero-btn" data-goto-tab="workers">${t("mobile.goWorkers")}</button>
        </div>
      </div>
      <div class="panel-block">
        <h3>${t("mobile.distributionTitle")}</h3>
        <p class="muted small">${t("mobile.distributionHint")}</p>
        <div class="mobile-channel-grid">${channels.map((c) => renderMobileChannelCard(c)).join("")}</div>
      </div>
      <div class="panel-block mobile-tech-strip">
        <div class="mobile-tech-item">
          <strong>${t("mobile.pushTitle")}</strong>
          <p class="muted small">${t("mobile.pushHint")}</p>
        </div>
        <div class="mobile-tech-item">
          <strong>API</strong>
          <p class="muted small"><code>${escapeHtml(native.apiPrefix || "/api/worker-app")}</code> · FCM</p>
        </div>
      </div>
      <div class="panel-block mobile-legacy-block">
        <h3>${t("mobile.legacyTitle")}</h3>
        <p class="muted small">${escapeHtml(pwaLegacy.label || t("mobile.legacyDesc"))}</p>
        <p class="mobile-legacy-row">${pwaLegacy.deprecated ? statusBadge(false) : ""}<a href="${escapeHtml(install.pwaEntry || pwaLegacy.entry || "#")}" target="_blank" rel="noopener">${t("mobile.legacyOpen")}</a></p>
      </div>
      <div class="panel-block">
        <h3>${t("mobile.attendanceModes")}</h3>
        <p class="muted small">${t("mobile.attendanceModesHint")}</p>
        <div class="mobile-mode-grid">${modes}</div>
      </div>
      <p class="muted small mobile-footnote">${t("mobile.workersHint")}</p>
    `;
    panel.querySelector("[data-goto-tab='workers']")?.addEventListener("click", () => {
      switchToTab("workers");
      refreshActiveTab().catch(notifyTabError);
    });
  } catch (e) {
    panel.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

function summarizeOpsLayer(key, val) {
  const v = val && typeof val === "object" ? val : {};
  const lines = [];
  let stat = "—";
  let tone = "ok";
  switch (key) {
    case "1_digital_twin":
      stat = t("ops.stat.workersOnSite", { n: v.summary?.workersOnSite ?? 0 });
      lines.push(
        t("ops.stat.gatesActive", { n: v.summary?.gatesActive ?? 0 }),
        t("ops.stat.hazardZones", { n: v.summary?.hazardZones ?? 0 }),
      );
      break;
    case "2_ai_security":
      stat = t("ops.stat.openAlerts", { n: (v.openAlerts || []).length });
      lines.push(
        t("ops.stat.newFindings", { n: v.newFindings ?? 0 }),
        (v.capabilities || []).slice(0, 2).join(", ") || t("ops.stat.analysisActive"),
      );
      tone = (v.openAlerts || []).length > 0 ? "warn" : "ok";
      break;
    case "3_site_intelligence":
      stat = t("ops.stat.topGates", { n: (v.busiestGates || []).length });
      lines.push(
        t("ops.stat.date", { date: v.date || "—" }),
        t("ops.stat.events24h", { n: v.totalEvents24h ?? v.events24h ?? "—" }),
      );
      break;
    case "4_reputation":
      stat = t("ops.stat.avgScore", { n: Number(v.averageScore ?? 0).toFixed(1) });
      lines.push(t("ops.stat.ranking", { n: (v.leaderboard || v.workers || []).length }));
      break;
    case "5_emergency":
      stat = v.active ? t("ops.stat.emergencyActive") : t("ops.stat.noEmergency");
      tone = v.active ? "danger" : "ok";
      if (v.active) {
        lines.push(`ID ${v.emergencyId || v.id || "—"}`, t("ops.stat.inside", { n: v.insideCount ?? "—" }));
      }
      break;
    case "6_camera_ai":
      stat = t("ops.stat.events24h", { n: v.events24h ?? 0 });
      break;
    case "7_iot":
      stat = t("ops.stat.devices", { n: (v.devices || []).length });
      lines.push(v.status || "Registry");
      break;
    case "8_command_center":
      stat = t("ops.stat.totalWorkers", { n: v.totalOnSite ?? v.workersOnSite ?? 0 });
      lines.push(
        t("ops.stat.emergencies", { n: v.openEmergencies ?? v.activeEmergencies ?? 0 }),
        `${v.openSecurity ?? 0} Security`,
      );
      break;
    case "9_autonomous":
      stat = t("ops.stat.rules", { n: v.enabledRules ?? v.ruleCount ?? 0 });
      lines.push(v.api || "/api/automation/rules");
      break;
    case "10_workforce_graph":
      stat = t("ops.stat.nodes", { n: (v.nodes || v.workers || []).length });
      lines.push(t("ops.stat.edges", { n: (v.edges || []).length }));
      break;
    case "11_identity":
      stat = t("ops.stat.identityHub");
      lines.push((v.apis?.gates || "Gates API").toString().slice(0, 40));
      break;
    case "12_copilot":
      stat = v.configured ? t("ops.stat.aiReady") : t("ops.stat.notConfigured");
      lines.push(v.endpoint || "POST /api/ops-os/copilot");
      tone = v.configured ? "ok" : "warn";
      break;
    default:
      stat = v.status || v.layer || t("ops.stat.active");
      break;
  }
  return { stat, lines: lines.filter(Boolean).slice(0, 3), tone };
}

function renderOpsLayerCard(key, title, icon, val) {
  const sum = summarizeOpsLayer(key, val);
  const num = String(key).replace(/\D/g, "").padStart(2, "0") || "—";
  const meta = sum.lines.map((l) => `<li>${l}</li>`).join("");
  return `
    <article class="ops-layer-card ops-tone-${sum.tone}" data-layer="${key}" role="button" tabindex="0" title="${t("ops.showDetails")}">
      <div class="ops-layer-head">
        <span class="ops-layer-num">${num}</span>
        <span class="ops-layer-icon" aria-hidden="true">${icon}</span>
      </div>
      <h4 class="ops-layer-title">${title}</h4>
      <p class="ops-layer-stat">${escapeHtml(sum.stat)}</p>
      ${meta ? `<ul class="ops-layer-meta">${meta}</ul>` : ""}
      <span class="ops-layer-more muted small">${t("ops.details")}</span>
    </article>
  `;
}

function formatOpsLayerDetailRows(val) {
  const rows = [];
  const push = (label, value) => {
    if (value === undefined || value === null || value === "") return;
    rows.push(`<tr><td>${escapeHtml(label)}</td><td>${escapeHtml(value)}</td></tr>`);
  };
  const v = val && typeof val === "object" ? val : {};
  if (v.layer) push(t("ops.detail.layer"), v.layer);
  if (v.status) push(t("ops.detail.status"), v.status);
  if (v.date) push(t("ops.detail.date"), v.date);
  if (v.company_id || v.companyId) push(t("ops.detail.company"), v.company_id || v.companyId);
  if (v.summary && typeof v.summary === "object") {
    for (const [sk, sv] of Object.entries(v.summary)) push(sk, sv);
  }
  if (Array.isArray(v.openAlerts)) push(t("ops.detail.openSecurity"), v.openAlerts.length);
  if (v.newFindings != null) push(t("ops.detail.newFindings"), v.newFindings);
  if (v.averageScore != null) push(t("ops.detail.reputationAvg"), Number(v.averageScore).toFixed(1));
  if (v.active != null) push(t("ops.detail.emergencyActive"), yn(v.active));
  if (v.events24h != null) push(t("ops.detail.cameraEvents"), v.events24h);
  if (v.totalOnSite != null) push(t("ops.detail.onSite"), v.totalOnSite);
  if (v.openEmergencies != null) push(t("ops.detail.openEmergencies"), v.openEmergencies);
  if (v.openSecurity != null) push(t("ops.detail.openSecurityShort"), v.openSecurity);
  if (v.enabledRules != null) push(t("ops.detail.automationRules"), v.enabledRules);
  if (Array.isArray(v.devices)) push(t("ops.detail.iotDevices"), v.devices.length);
  if (Array.isArray(v.busiestGates)) push(t("ops.detail.topGates"), v.busiestGates.length);
  if (v.configured != null) push(t("ops.detail.copilot"), v.configured ? t("ops.stat.aiReady") : t("ops.stat.notConfigured"));
  if (v.endpoint) push(t("ops.detail.api"), v.endpoint);
  if (rows.length < 4) {
    for (const [k, raw] of Object.entries(v)) {
      if (["entities", "liveMovement", "findings", "leaderboard", "workers"].includes(k)) {
        push(k, Array.isArray(raw) ? t("ops.detail.entries", { n: raw.length }) : t("ops.detail.object"));
        continue;
      }
      if (typeof raw === "object" && raw !== null) continue;
      push(k, raw);
      if (rows.length >= 14) break;
    }
  }
  return rows.join("") || `<tr><td colspan="2" class="muted">${t("ops.noDetailData")}</td></tr>`;
}

function openOpsLayerModal(layerKey) {
  const layers = window.__opsLayersCache || {};
  const meta = getOpsLayerOrder().find(([k]) => k === layerKey);
  const title = meta ? meta[1] : layerKey;
  const val = layers[layerKey];
  const sum = summarizeOpsLayer(layerKey, val);
  $("opsLayerModalTitle").textContent = title;
  $("opsLayerModalStat").textContent = sum.stat;
  $("opsLayerModalBody").innerHTML = formatOpsLayerDetailRows(val);
  $("opsLayerModal").classList.remove("hidden");
}

function initOpsLayerCards(root) {
  if (!root) return;
  root.querySelectorAll(".ops-layer-card").forEach((card) => {
    const open = () => openOpsLayerModal(card.dataset.layer || "");
    card.addEventListener("click", open);
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        open();
      }
    });
  });
}

function buildOpsEmbedUrl(pagePath, companyId) {
  const u = new URL(pagePath, location.origin);
  u.searchParams.set("embed", "1");
  if (companyId) {
    u.searchParams.set("company_id", companyId);
  }
  return u.pathname + u.search;
}

function syncTokenToOpsEmbedFrame(frame, companyId) {
  if (!frame) return;
  const token = (wpGet(CONTROL_TOKEN_KEY) || wpGet(TOKEN_KEY) || "").trim();
  if (!token) return;
  const send = () => {
    try {
      frame.contentWindow?.postMessage(
        {
          type: "baupass-sync-token",
          token,
          companyId: companyId || activeCompanyId() || "",
          lang: getLang(),
        },
        window.location.origin,
      );
    } catch {
      // iframe not ready
    }
  };
  frame.addEventListener("load", send, { once: false });
  send();
}

function initOpsEmbedTabs(panel, companyId) {
  const frame = panel?.querySelector("#opsEmbedFrame");
  if (!frame) return;
  panel.querySelectorAll(".ops-embed-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const page = btn.getAttribute("data-ops-page");
      if (!page) return;
      panel.querySelectorAll(".ops-embed-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      frame.src = buildOpsEmbedUrl(page, companyId);
      frame.title = btn.textContent || "";
      syncTokenToOpsEmbedFrame(frame, companyId);
    });
  });
  syncTokenToOpsEmbedFrame(frame, companyId);
}

function initOpsCarousel(root) {
  const track = root?.querySelector(".ops-carousel-track");
  const prev = root?.querySelector(".ops-carousel-prev");
  const next = root?.querySelector(".ops-carousel-next");
  const hint = root?.querySelector(".ops-carousel-hint");
  if (!track) return;

  const step = () => {
    const card = track.querySelector(".ops-layer-card");
    const gap = 14;
    return (card?.offsetWidth || 280) + gap;
  };

  if (hint) {
    hint.textContent = t("ops.scrollHint");
  }

  prev?.addEventListener("click", (e) => {
    e.stopPropagation();
    track.scrollBy({ left: -step(), behavior: "smooth" });
  });
  next?.addEventListener("click", (e) => {
    e.stopPropagation();
    track.scrollBy({ left: step(), behavior: "smooth" });
  });

  /* Scroll-Chaining zur Seite verhindern — nur die Kartenzeile bewegt sich */
  track.addEventListener(
    "wheel",
    (e) => {
      const dx = Math.abs(e.deltaX);
      const dy = Math.abs(e.deltaY);
      if (dx <= dy && !e.shiftKey) return;
      e.preventDefault();
      e.stopPropagation();
      track.scrollLeft += dx > dy ? e.deltaX : e.deltaY;
    },
    { passive: false }
  );

  track.addEventListener(
    "touchmove",
    (e) => {
      e.stopPropagation();
    },
    { passive: true }
  );
}

async function loadLegacyFeatures(companyId) {
  if (getUser().role === "superadmin") return null;
  const q = companyId ? `?company_id=${encodeURIComponent(companyId)}` : "";
  const ent = await api(`/api/platform/entitlements${q}`).catch(() => null);
  return ent?.legacyFeatures || {};
}

function legacyFeatureEnabled(features, key) {
  if (features === null) return true;
  return Boolean(features[key]);
}

function renderBetriebActionCard({ href, icon, title, desc, cta, locked, upgradeLabel }) {
  if (locked) {
    return `
      <div class="betrieb-action-card betrieb-action-locked" aria-disabled="true">
        <span class="betrieb-action-icon" aria-hidden="true">${icon}</span>
        <strong>${title}</strong>
        <span class="muted small">${desc}</span>
        <span class="betrieb-action-cta">${upgradeLabel}</span>
      </div>`;
  }
  return `
    <a href="${href}" class="betrieb-action-card">
      <span class="betrieb-action-icon" aria-hidden="true">${icon}</span>
      <strong>${title}</strong>
      <span class="muted small">${desc}</span>
      <span class="betrieb-action-cta">${cta} →</span>
    </a>`;
}

async function renderBetriebActionHub(companyId) {
  const host = $("operationsActionHub");
  if (!host) return;
  const q = companyId ? `?company_id=${encodeURIComponent(companyId)}` : "";
  if (getUser().role === "superadmin" && !companyId) {
    host.innerHTML = `<p class="muted small">${t("common.selectCompany")}</p>`;
    return;
  }
  const features = await loadLegacyFeatures(companyId);
  host.innerHTML = [
    renderBetriebActionCard({
      href: `/admin-v2/contracts.html${q}`,
      icon: "📄",
      title: t("contracts.title"),
      desc: t("contracts.desc"),
      cta: t("contracts.open"),
      locked: !legacyFeatureEnabled(features, "employment_contracts"),
      upgradeLabel: t("contracts.upgrade"),
    }),
    renderBetriebActionCard({
      href: `/admin-v2/chat.html${q}`,
      icon: "💬",
      title: t("chat.title"),
      desc: t("chat.desc"),
      cta: t("chat.open"),
      locked: !legacyFeatureEnabled(features, "worker_chat"),
      upgradeLabel: t("chat.upgrade"),
    }),
  ].join("");
}

async function loadOperations() {
  const panel = $("operationsPanel");
  const q = companyQuery();
  const cid = q.replace("?company_id=", "");
  await renderBetriebActionHub(cid);
  if (getUser().role === "superadmin" && !q) {
    panel.innerHTML = `<p class="muted">${t("common.selectCompany")}</p>`;
    return;
  }
  panel.innerHTML = `<p class="muted">${t("common.loading")}</p>`;
  try {
    const cid = q.replace("?company_id=", "");
    const data = await api(`/api/ops-os/overview?company_id=${encodeURIComponent(cid)}`);
    const layers = data.layers || {};
    const cards = getOpsLayerOrder()
      .map(([key, title, icon]) => renderOpsLayerCard(key, title, icon, layers[key]))
      .join("");
    let rtLabel = "";
    try {
      const rt = await api("/api/v1/realtime/status");
      rtLabel = rt?.websocket?.enabled
        ? `<span class="badge badge-ok">${t("ops.websocketLive")}</span>`
        : `<span class="badge badge-warn">${t("ops.sseFallback")}</span>`;
    } catch {
      rtLabel = "";
    }
    const chatResp = await api(`/api/chat/threads${q ? q : ""}`).catch(() => ({ threads: [] }));
    const chatThreads = chatResp.threads || [];
    const features = await loadLegacyFeatures(cid);
    const contractsCard = renderBetriebActionCard({
      href: `/admin-v2/contracts.html${q}`,
      icon: "📄",
      title: t("contracts.open"),
      desc: t("contracts.desc"),
      cta: t("contracts.open"),
      locked: !legacyFeatureEnabled(features, "employment_contracts"),
      upgradeLabel: t("contracts.upgrade"),
    });
    const chatCard = renderBetriebActionCard({
      href: `/admin-v2/chat.html${q}`,
      icon: "💬",
      title: t("chat.open"),
      desc: chatThreads.length ? t("chat.threadCount", { count: chatThreads.length }) : t("chat.empty"),
      cta: t("chat.open"),
      locked: !legacyFeatureEnabled(features, "worker_chat"),
      upgradeLabel: t("chat.upgrade"),
    });
    panel.innerHTML = `
      <div class="panel-block ops-panel">
        <div class="ops-panel-head">
          <h3>${t("ops.physicalOs")} <span class="badge badge-ok">${t("ops.layersBadge")}</span> ${rtLabel}</h3>
          <p class="muted small">${t("ops.company", { id: data.companyId || cid })}</p>
        </div>
        <div class="ops-carousel-shell" id="opsCarousel">
          <div class="ops-carousel-wrap">
            <button type="button" class="ops-carousel-btn ops-carousel-prev" aria-label="${t("ops.prevLayer")}">‹</button>
            <div class="ops-carousel-track">${cards}</div>
            <button type="button" class="ops-carousel-btn ops-carousel-next" aria-label="${t("ops.nextLayer")}">›</button>
          </div>
        </div>
        <p class="ops-carousel-hint muted small"></p>
      </div>
      <div class="link-row ops-embed-tabs" role="tablist">
        <button type="button" class="btn-link ops-embed-tab active" data-ops-page="/ops-live-map.html">${t("ops.liveMap")}</button>
        <button type="button" class="btn-link ops-embed-tab" data-ops-page="/ops-command-center.html">${t("ops.commandCenter")}</button>
        <button type="button" class="btn-link ops-embed-tab" data-ops-page="/ai-command-center.html">${t("ops.aiCenter")}</button>
        <button type="button" class="btn-link ops-embed-tab" data-ops-page="/enterprise-hub.html">${t("common.enterpriseHub")}</button>
        <a href="/ops-live-map.html${q ? `${q}&embed=1` : `?company_id=${encodeURIComponent(cid)}&embed=1`}" target="_blank" rel="noopener" class="muted small">${t("ops.openNewTab")}</a>
      </div>
      <iframe id="opsEmbedFrame" src="/ops-live-map.html${q ? `${q}&embed=1` : `?company_id=${encodeURIComponent(cid)}&embed=1`}" title="${t("ops.liveMap")}" class="ops-map-frame"></iframe>
      <div class="panel-block">
        <h3>${t("contracts.title")}</h3>
        <p class="muted small">${t("contracts.desc")}</p>
        <div style="max-width:420px;">${contractsCard}</div>
      </div>
      <div class="panel-block">
        <h3>${t("chat.title")}</h3>
        <p class="muted small">${t("chat.inboxHint", { count: chatThreads.length })}</p>
        <div style="max-width:420px;">${chatCard}</div>
      </div>
    `;
    window.__opsLayersCache = layers;
    initOpsCarousel($("opsCarousel"));
    initOpsLayerCards($("opsCarousel"));
    initOpsEmbedTabs(panel, cid);
    if (pendingOpsEmbedPage) {
      const page = pendingOpsEmbedPage;
      pendingOpsEmbedPage = null;
      const embedBtn = panel.querySelector(`.ops-embed-tab[data-ops-page="${page}"]`);
      embedBtn?.click();
    }
  } catch (e) {
    panel.innerHTML = `<p class="error">${e.message || t("ops.loadError")}</p>`;
  }
}

function requireCompany(panel) {
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    panel.innerHTML = `<p class="muted">${t("common.selectCompany")}</p>`;
    return null;
  }
  return q;
}

async function loadTools() {
  const panel = $("toolsPanel");
  const q = requireCompany(panel);
  if (q === null) return;
  panel.innerHTML = `<p class="muted">${t("common.loading")}</p>`;
  try {
    const [geofences, rules, integrations] = await Promise.all([
      api(`/api/geofences/admin${q}`),
      api(`/api/automation/rules${q}`),
      api(`/api/integrations${q}`),
    ]);
    const gfRows = geofences.geofences || [];
    const ruleRows = rules.rules || [];
    const intRows = integrations.integrations || [];
    const providers = [
      { id: "sap", label: "SAP" },
      { id: "oracle", label: "Oracle" },
      { id: "microsoft365", label: "Microsoft 365" },
      { id: "google_workspace", label: "Google Workspace" },
      { id: "payroll", label: "Payroll" },
    ];
    panel.innerHTML = `
      <div class="panel-block">
        <h3>${t("tools.geofence")}</h3>
        <p class="muted small">${t("tools.mapHint")}</p>
        <div id="geofenceMap"></div>
        <form id="geofenceForm" class="tool-form">
          <input name="site_name" placeholder="${t("tools.sitePlaceholder")}" required />
          <div class="geofence-coords-row">
            <input name="latitude" type="number" step="any" placeholder="${t("tools.lat")}" required />
            <input name="longitude" type="number" step="any" placeholder="${t("tools.lng")}" required />
            <button type="button" id="geofenceGpsBtn" class="btn-link" title="${t("tools.useGps")}">📍 ${t("tools.useGps")}</button>
          </div>
          <span id="geofenceGpsStatus" class="muted small"></span>
          <input name="radius_meters" type="number" value="100" min="20" max="500" placeholder="${t("tools.radius")}" />
          <button type="submit">${t("tools.addZone")}</button>
        </form>
        <div class="table-wrap" id="geofenceTable"></div>
      </div>
      <div class="panel-block">
        <h3>${t("tools.automation")}</h3>
        <form id="automationForm" class="tool-form">
          <input name="name" placeholder="${t("tools.ruleName")}" required />
          <select name="trigger_event">
            <option value="worker.checkin">${t("tools.checkin")}</option>
            <option value="worker.checkout">${t("tools.checkout")}</option>
            <option value="*">${t("tools.anyEvent")}</option>
          </select>
          <button type="submit">${t("tools.createRule")}</button>
        </form>
        <div class="table-wrap" id="automationTable"></div>
      </div>
      <div class="panel-block">
        <h3>${t("tools.integrations")}</h3>
        <div class="layer-grid" id="integrationCards"></div>
      </div>`;
    renderTable($("geofenceTable"), gfRows, [
      { label: t("table.site"), render: (r) => r.site_name || "-" },
      { label: t("table.coords"), render: (r) => `${r.latitude}, ${r.longitude}` },
      { label: t("table.radius"), render: (r) => `${r.radius_meters}m` },
      { label: t("table.active"), render: (r) => yn(r.active) },
    ]);
    renderTable($("automationTable"), ruleRows, [
      { label: t("table.name"), render: (r) => r.name || "-" },
      { label: t("table.trigger"), render: (r) => r.trigger_event || "-" },
      { label: t("table.enabled"), render: (r) => yn(r.enabled) },
    ]);
    const intByProvider = Object.fromEntries(intRows.map((r) => [r.provider, r]));
    const erpProviders = new Set(["sap", "oracle"]);
    $("integrationCards").innerHTML = providers
      .map((p) => {
        const conn = intByProvider[p.id];
        const st = conn ? conn.status : t("tools.notConnected");
        const erpBtns = erpProviders.has(p.id)
          ? `<button type="button" class="btn-link" data-export-preview="${p.id}">${t("tools.exportPreview")}</button>
             <button type="button" class="btn-link" data-export-push="${p.id}">${t("tools.exportPush")}</button>
             <button type="button" class="btn-link" data-export-dry="${p.id}">${t("tools.exportDryRun")}</button>`
          : "";
        return `<div class="layer-pill" data-provider="${p.id}">
          <strong>${p.label}</strong><br><span class="muted small">${st}</span>
          <button type="button" class="btn-link" data-connect="${p.id}">${t("tools.connect")}</button>
          <button type="button" class="btn-link" data-sync="${p.id}">${t("tools.sync")}</button>
          ${erpBtns}
        </div>`;
      })
      .join("");
    const gfForm = $("geofenceForm");
    const latIn = gfForm.querySelector('[name="latitude"]');
    const lngIn = gfForm.querySelector('[name="longitude"]');
    mountGeofenceMapWhenReady($("geofenceMap"), latIn, lngIn, gfRows);
    const gpsStatus = $("geofenceGpsStatus");
    $("geofenceGpsBtn")?.addEventListener("click", () => {
      useGeofenceCurrentLocation(latIn, lngIn, $("geofenceMap"), {
        onStatus: (state, details = {}) => {
          if (!gpsStatus) return;
          if (state === "loading") gpsStatus.textContent = t("tools.gpsLoading");
          else if (state === "ok") {
            const meters = Math.round(Number(details.accuracyMeters) || 0);
            gpsStatus.textContent =
              meters > 0
                ? t("tools.gpsOkMeters").replace("{meters}", String(meters))
                : t("tools.gpsOk");
          } else if (state === "inaccurate") {
            const meters = Math.round(Number(details.accuracyMeters) || 0);
            gpsStatus.textContent = t("tools.gpsInaccurate").replace("{meters}", String(meters || "?"));
          } else if (state === "denied") gpsStatus.textContent = t("tools.gpsDenied");
          else if (state === "timeout") gpsStatus.textContent = t("tools.gpsTimeout");
          else if (state === "failed") gpsStatus.textContent = t("tools.gpsFailed");
          else if (state === "unsupported") gpsStatus.textContent = t("tools.gpsUnsupported");
        },
      });
    });
    $("geofenceForm").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const fd = new FormData(ev.target);
      let latitude = Number(fd.get("latitude"));
      let longitude = Number(fd.get("longitude"));
      const map = $("geofenceMap")?._baupassLeafletMap;
      if ((!Number.isFinite(latitude) || !Number.isFinite(longitude)) && map?._baupassMarker) {
        const point = map._baupassMarker.getLatLng();
        latitude = point.lat;
        longitude = point.lng;
      }
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
        alert(t("tools.coordsRequired"));
        return;
      }
      try {
        await api(`/api/geofences/admin${q}`, {
          method: "POST",
          body: JSON.stringify({
            site_name: fd.get("site_name"),
            latitude,
            longitude,
            radius_meters: parseInt(fd.get("radius_meters") || "100", 10),
          }),
        });
        ev.target.reset();
        await loadTools();
      } catch (error) {
        alert(error?.message || t("tools.coordsRequired"));
      }
    });
    $("automationForm").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const fd = new FormData(ev.target);
      await api(`/api/automation/rules${q}`, {
        method: "POST",
        body: JSON.stringify({
          name: fd.get("name"),
          trigger_event: fd.get("trigger_event"),
          conditions: [],
          actions: [{ type: "log", message: "automation_triggered" }],
          enabled: true,
        }),
      });
      ev.target.reset();
      await loadTools();
    });
    panel.querySelectorAll("[data-connect]").forEach((btn) => {
      btn.addEventListener("click", () => {
        pendingIntegrationProvider = btn.getAttribute("data-connect");
        const spec = INTEGRATION_WIZARD[pendingIntegrationProvider];
        if (!spec) return;
        $("integrationModalTitle").textContent = spec.title;
        renderWizardForm(pendingIntegrationProvider, $("integrationWizardForm"));
        $("integrationModal").classList.remove("hidden");
      });
    });
    panel.querySelectorAll("[data-sync]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const provider = btn.getAttribute("data-sync");
        try {
          const res = await api(`/api/integrations/${provider}/sync${q}`, { method: "POST", body: "{}" });
          alert(JSON.stringify(res, null, 2).slice(0, 800));
        } catch (e) {
          alert(e.message);
        }
      });
    });
    panel.querySelectorAll("[data-export-preview]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const provider = btn.getAttribute("data-export-preview");
        try {
          const res = await api(`/api/integrations/${provider}/export-preview${q}`);
          alert(JSON.stringify(res, null, 2).slice(0, 1200));
        } catch (e) {
          alert(e.message);
        }
      });
    });
    async function runErpExport(provider, dryRun) {
      const res = await api(`/api/integrations/${provider}/export${q}`, {
        method: "POST",
        body: JSON.stringify({ dryRun: Boolean(dryRun) }),
      });
      alert(JSON.stringify(res, null, 2).slice(0, 1200));
    }
    panel.querySelectorAll("[data-export-push]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const provider = btn.getAttribute("data-export-push");
        if (!window.confirm(`${provider.toUpperCase()}: ${t("tools.exportPush")}?`)) return;
        try {
          await runErpExport(provider, false);
        } catch (e) {
          alert(e.message);
        }
      });
    });
    panel.querySelectorAll("[data-export-dry]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const provider = btn.getAttribute("data-export-dry");
        try {
          await runErpExport(provider, true);
        } catch (e) {
          alert(e.message);
        }
      });
    });
  } catch (e) {
    panel.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

function renderTable(container, rows, columns) {
  if (!rows.length) {
    container.innerHTML = `<p class="muted" style="padding:1rem">${t("common.noData")}</p>`;
    return;
  }
  const head = columns.map((c) => `<th>${c.label}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = columns.map((c) => `<td>${c.render(row)}</td>`).join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  container.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

let inboxSourceFilter = "";
const inboxSelectedIds = new Set();

function inboxApiQuery(baseQ) {
  const params = new URLSearchParams((baseQ || "").replace(/^\?/, ""));
  if (inboxSourceFilter) params.set("source", inboxSourceFilter);
  const s = params.toString();
  return s ? `?${s}` : "";
}

function renderInboxFilters(bySource = {}) {
  const bar = $("inboxFilters");
  if (!bar) return;
  const chips = [
    { id: "", label: t("inbox.filterAll") },
    { id: "security", label: `${t("inbox.filterSecurity")} (${bySource.security ?? 0})` },
    { id: "leave", label: `${t("inbox.filterLeave")} (${bySource.leave ?? 0})` },
    { id: "document", label: `${t("inbox.filterDocument")} (${bySource.document ?? 0})` },
    { id: "system", label: `${t("inbox.filterSystem")} (${bySource.system ?? 0})` },
  ];
  bar.classList.remove("hidden");
  bar.innerHTML = chips
    .map(
      (c) =>
        `<button type="button" class="inbox-filter-chip${inboxSourceFilter === c.id ? " active" : ""}" data-source="${c.id}">${c.label}</button>`,
    )
    .join("");
  bar.querySelectorAll(".inbox-filter-chip").forEach((btn) => {
    btn.addEventListener("click", async () => {
      inboxSourceFilter = btn.dataset.source || "";
      await loadInbox();
    });
  });
}

async function loadInbox() {
  const el = $("inboxList");
  const countsEl = $("inboxCounts");
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    el.innerHTML = `<p class="muted">${t("common.selectCompany")}</p>`;
    countsEl.innerHTML = "";
    $("inboxFilters")?.classList.add("hidden");
    return;
  }
  el.innerHTML = `<p class="muted">${t("common.loading")}</p>`;
  const iq = inboxApiQuery(q);
  const [data, pushSt] = await Promise.all([
    api(`/api/inbox${iq || q}`),
    api("/api/platform/push/status").catch(() => null),
  ]);
  const liveHint = $("inboxLiveHint");
  if (liveHint) liveHint.classList.remove("hidden");
  const pushEl = $("inboxPushStatus");
  if (pushEl && pushSt) {
    const ready = pushSt.anyChannelReady;
    pushEl.classList.remove("hidden");
    const mode = pushSt.fcmMode === "http_v1" ? "FCM v1" : pushSt.fcmMode === "legacy" ? "FCM legacy" : "";
    const v1only = pushSt.fcmV1Only ? " · v1-only" : "";
    const extra = `${mode ? ` · ${mode}${v1only}` : ""}${pushSt.webPushSubscriptions ? ` · ${pushSt.webPushSubscriptions} PWA` : ""}`;
    pushEl.innerHTML = ready
      ? t("inbox.pushHybrid", {
          workers: pushSt.workersWithPush ?? 0,
          devices: pushSt.registeredDevices ?? 0,
          extra,
        })
      : t("inbox.pushNotConfigured");
  } else if (pushEl) {
    pushEl.classList.add("hidden");
  }
  const c = data.counts || {};
  renderInboxFilters(c.bySource || {});
  updateInboxTabBadge(c.open, c.critical);
  countsEl.innerHTML = `
    <div class="card"><span class="muted">${t("inbox.open")}</span><strong>${c.open ?? 0}</strong></div>
    <div class="card"><span class="muted">${t("inbox.critical")}</span><strong style="color:#f87171">${c.critical ?? 0}</strong></div>
    <div class="card"><span class="muted">${t("inbox.total")}</span><strong>${c.total ?? 0}</strong></div>
    <button type="button" class="feature-card" data-goto-tab="operations">${t("inbox.opsCenter")}</button>
  `;
  countsEl.querySelector("[data-goto-tab]")?.addEventListener("click", () => {
    switchToTab("operations");
    refreshActiveTab();
  });
  const items = data.items || [];
  for (const id of [...inboxSelectedIds]) {
    if (!items.some((it) => it.id === id)) inboxSelectedIds.delete(id);
  }
  const selectedItems = items.filter((it) => inboxSelectedIds.has(it.id));
  const scope = selectedItems.length ? selectedItems : items;
  const bulkBar = $("inboxBulkBar");
  const docCount = scope.filter((it) => String(it.id || "").startsWith("doc:")).length;
  const leaveCount = scope.filter((it) => String(it.id || "").startsWith("leave:")).length;
  const sysCount = scope.filter((it) => String(it.id || "").startsWith("sys:")).length;
  const selHint =
    selectedItems.length > 0
      ? `<span class="muted small">${t("inbox.selected", { n: selectedItems.length })}</span>`
      : `<span class="muted small">${t("inbox.allItems", { n: items.length })}</span>`;
  if (bulkBar) {
    if (!items.length) {
      bulkBar.classList.add("hidden");
      bulkBar.innerHTML = "";
    } else {
      bulkBar.classList.remove("hidden");
      bulkBar.innerHTML = `
        ${selHint}
        <button type="button" class="ghost" id="inboxSelectAll">${t("inbox.selectAll")}</button>
        <button type="button" class="ghost" id="inboxSelectNone">${t("inbox.selectNone")}</button>
        ${docCount ? `<button type="button" class="ghost" id="inboxBulkDocPush">${t("inbox.bulkDocPush", { n: docCount })}</button>` : ""}
        ${leaveCount ? `<button type="button" class="ghost" id="inboxBulkLeaveOk">${t("inbox.bulkLeaveApprove", { n: leaveCount })}</button>` : ""}
        ${leaveCount ? `<button type="button" class="ghost" id="inboxBulkLeaveNo">${t("inbox.bulkLeaveReject", { n: leaveCount })}</button>` : ""}
        ${sysCount ? `<button type="button" class="ghost" id="inboxBulkSysAck">${t("inbox.bulkSysAck", { n: sysCount })}</button>` : ""}
      `;
    }
  }
  if (!items.length) {
    el.innerHTML = `<p class="muted">${t("inbox.empty")}</p>`;
    return;
  }
  el.innerHTML = `<table><thead><tr><th></th><th>${t("inbox.colTitle")}</th><th>${t("inbox.colSla")}</th><th>${t("inbox.colSource")}</th><th>${t("inbox.colActions")}</th></tr></thead><tbody>${items
    .map((it) => {
      const checked = inboxSelectedIds.has(it.id) ? " checked" : "";
      const slaCls =
        it.slaStatus === "overdue" ? "sla-overdue" : it.slaStatus === "due_soon" ? "sla-due-soon" : "";
      const slaLabel =
        it.slaStatus === "overdue"
          ? t("inbox.slaOverdue")
          : it.slaStatus === "due_soon"
            ? t("inbox.slaDueSoon")
            : it.slaDueAt
              ? t("inbox.slaUntil", { date: (it.slaDueAt || "").slice(0, 16).replace("T", " ") })
              : "—";
      const acts = (it.actions || [])
        .map((a) => {
          if (a.type === "resolve" || a.type === "ack")
            return `<button type="button" class="btn-link inbox-resolve" data-id="${it.id}">${t("inbox.done")}</button>`;
          if (a.type === "execute" && a.action)
            return `<button type="button" class="btn-link inbox-exec" data-id="${it.id}" data-action="${a.action}" data-params="${encodeURIComponent(JSON.stringify(a.params || {}))}">${a.label || a.action}</button>`;
          if (a.type === "navigate") {
            const label = a.label || t("inbox.openAction");
            const isDeployment =
              String(it.id || "").startsWith("depdecl:") ||
              String(a.url || "").includes("deployment-plan") ||
              String(a.url || "").includes("einsatzplan");
            if (isDeployment && it.workerId) {
              const workerName = String(it.message || "")
                .split("·")[0]
                .trim();
              return `<button type="button" class="btn-link inbox-nav-deployment" data-worker-id="${escapeAttr(String(it.workerId))}" data-worker-name="${escapeAttr(workerName)}">${escapeAttr(label)}</button>`;
            }
            if (window.parent !== window && String(a.url || "").startsWith("/")) {
              return `<button type="button" class="btn-link inbox-nav-parent" data-nav-url="${escapeAttr(String(a.url))}">${escapeAttr(label)}</button>`;
            }
            return `<a class="btn-link" href="${a.url}${q}">${label}</a>`;
          }
          if (a.type === "prompt")
            return `<a class="btn-link" href="/ai-command-center.html${q}&autoprompt=${encodeURIComponent(a.prompt || "")}">KI</a>`;
          return "";
        })
        .join(" · ");
      return `<tr class="${it.severity === "critical" ? "row-critical" : ""}">
        <td><input type="checkbox" class="inbox-pick" data-id="${it.id}"${checked} aria-label="${t("inbox.selectAria")}" /> <span class="badge badge-warn">${it.severity || ""}</span></td>
        <td><strong>${it.title || ""}</strong><br><span class="muted small">${it.message || ""}</span></td>
        <td class="${slaCls}">${slaLabel}</td>
        <td>${it.source || ""}</td>
        <td>${acts}</td></tr>`;
    })
    .join("")}</tbody></table>`;
  el.querySelectorAll(".inbox-nav-deployment").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const workerId = String(btn.dataset.workerId || "").trim();
      const workerName = String(btn.dataset.workerName || "").trim();
      if (!workerId) return;
      try {
        switchToTab("workers");
        await loadWorkers();
        await openDeploymentModal(workerId, workerName || workerId);
      } catch (e) {
        showActionToast(e.message, true);
      }
    });
  });
  el.querySelectorAll(".inbox-nav-parent").forEach((btn) => {
    btn.addEventListener("click", () => {
      const raw = String(btn.dataset.navUrl || "").trim();
      if (!raw) return;
      try {
        const u = new URL(raw, window.location.origin);
        const view = u.searchParams.get("view") || "";
        window.parent.postMessage(
          {
            type: "baupass-navigate",
            view,
            focusEinsatzplan: u.searchParams.get("einsatzplan") === "1",
            url: u.pathname + u.search + u.hash,
          },
          window.location.origin,
        );
      } catch (e) {
        showActionToast(e.message, true);
      }
    });
  });
  el.querySelectorAll(".inbox-resolve").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        const res = await api(`/api/inbox/${encodeURIComponent(btn.dataset.id)}/resolve${q}`, {
          method: "POST",
          body: "{}",
        });
        showActionToast(res.ok ? t("common.done") : res.error || t("common.error"), !res.ok);
        await loadInbox();
      } catch (e) {
        showActionToast(e.message, true);
      }
    });
  });
  el.querySelectorAll(".inbox-pick").forEach((cb) => {
    cb.addEventListener("change", () => {
      const id = cb.dataset.id || "";
      if (!id) return;
      if (cb.checked) inboxSelectedIds.add(id);
      else inboxSelectedIds.delete(id);
      loadInbox().catch(() => {});
    });
  });
  $("inboxSelectAll")?.addEventListener("click", () => {
    items.forEach((it) => {
      if (it.id) inboxSelectedIds.add(it.id);
    });
    loadInbox().catch(() => {});
  });
  $("inboxSelectNone")?.addEventListener("click", () => {
    inboxSelectedIds.clear();
    loadInbox().catch(() => {});
  });

  async function runInboxBulk(action, extra = {}) {
    const cid = q.replace("?company_id=", "");
    const itemIds = selectedItems.length
      ? selectedItems.map((it) => it.id).filter(Boolean)
      : undefined;
    const res = await api(`/api/inbox/bulk${iq || q}`, {
      method: "POST",
      body: JSON.stringify({ action, company_id: cid || undefined, item_ids: itemIds, ...extra }),
    });
    const msg =
      action === "push_document_reminders"
        ? t("inbox.bulkResultDoc", { sent: res.pushSent ?? 0, total: res.processed ?? 0 })
        : action === "approve_pending_leave"
          ? t("inbox.bulkResultLeave", { n: res.approvedOrRejected ?? 0, push: res.pushSent ?? 0 })
          : t("inbox.bulkResultSys", { n: res.acknowledged ?? 0 });
    showActionToast(res.ok ? msg : res.error || t("common.error"), !res.ok);
    await loadInbox();
  }

  $("inboxBulkDocPush")?.addEventListener("click", () => {
    if (!confirm(t("inbox.confirmDocPush"))) return;
    runInboxBulk("push_document_reminders").catch((e) => showActionToast(e.message, true));
  });
  $("inboxBulkLeaveOk")?.addEventListener("click", () => {
    if (!confirm(t("inbox.confirmLeaveApprove"))) return;
    runInboxBulk("approve_pending_leave", { decision: "approve" }).catch((e) =>
      showActionToast(e.message, true),
    );
  });
  $("inboxBulkLeaveNo")?.addEventListener("click", () => {
    if (!confirm(t("inbox.confirmLeaveReject"))) return;
    runInboxBulk("approve_pending_leave", { decision: "reject" }).catch((e) =>
      showActionToast(e.message, true),
    );
  });
  $("inboxBulkSysAck")?.addEventListener("click", () => {
    runInboxBulk("ack_system_alerts").catch((e) => showActionToast(e.message, true));
  });

  el.querySelectorAll(".inbox-exec").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.id || "";
      const action = btn.dataset.action || "";
      if (id.startsWith("leave:") && (action === "approve_leave_request" || action === "reject_leave_request")) {
        const decision = action === "approve_leave_request" ? "approve" : "reject";
        try {
          const res = await api(`/api/inbox/${encodeURIComponent(id)}/resolve${q}`, {
            method: "POST",
            body: JSON.stringify({ decision }),
          });
          const msg = res.ok
            ? `${decision === "approve" ? t("inbox.approved") : t("inbox.rejected")}. ${formatPushDelivery(res)}`
            : res.error || t("common.error");
          showActionToast(msg, !res.ok);
          await loadInbox();
          return;
        } catch (e) {
          showActionToast(e.message, true);
          return;
        }
      }
      try {
        const params = JSON.parse(decodeURIComponent(btn.dataset.params || "%7B%7D"));
        const cid = q.replace("?company_id=", "");
        const res = await api("/api/ai/actions/execute", {
          method: "POST",
          body: JSON.stringify({ action, params, company_id: cid || undefined }),
        });
        const pushMsg = formatPushDelivery(res);
        showActionToast(
          res.ok ? `${action} ✓${pushMsg ? ` — ${pushMsg}` : ""}` : res.error || t("common.error"),
          !res.ok,
        );
        await loadInbox();
      } catch (e) {
        showActionToast(e.message, true);
      }
    });
  });
}

let analyticsPeriod = "day";

function trackFeatureUsage(featureId) {
  const fid = String(featureId || "").trim();
  if (!fid || superadminNeedsCompany()) return;
  if (globalThis.BaupassUsage?.track) {
    globalThis.BaupassUsage.track(fid, "admin-v2");
    return;
  }
  api("/api/v2/usage/event", {
    method: "POST",
    body: JSON.stringify({ feature_id: fid, source: "admin-v2" }),
  }).catch(() => {});
}

function bindAnalyticsPeriodButtons() {
  document.querySelectorAll("[data-analytics-period]").forEach((btn) => {
    if (btn.dataset.bound) return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", async () => {
      analyticsPeriod = btn.getAttribute("data-analytics-period") || "day";
      document.querySelectorAll("[data-analytics-period]").forEach((b) => {
        b.classList.toggle("active", b === btn);
      });
      await loadAnalytics();
    });
  });
}

async function loadAnalytics() {
  if (!canAccessAnalyticsTab()) {
    switchToTab("overview");
    return;
  }
  bindAnalyticsPeriodButtons();
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    const surveys = await api("/api/v2/admin/satisfaction-surveys");
    const sum = surveys.summary || {};
    $("usageStatCards").innerHTML = `<p class="muted">${t("common.selectCompany")}</p>`;
    $("satisfactionSummaryCards").innerHTML = `
    <div class="card"><span class="muted">${t("analytics.avgScore")}</span><strong>${sum.avgSatisfactionScore ?? "—"}</strong></div>
    <div class="card"><span class="muted">${t("analytics.recommendRate")}</span><strong>${sum.recommendRate != null ? `${Math.round(sum.recommendRate * 100)}%` : "—"}</strong></div>
    <div class="card"><span class="muted">${t("analytics.avgTimeSaved")}</span><strong>${sum.avgTimeSavedHours ?? "—"}</strong></div>
    <div class="card"><span class="muted">${t("analytics.avgCostSaved")}</span><strong>${sum.avgCostSavedEstimate != null ? `€${sum.avgCostSavedEstimate}` : "—"}</strong></div>
  `;
    const rows = surveys.surveys || [];
    $("satisfactionSurveysList").innerHTML = rows.length
      ? `<table class="data-table"><thead><tr>
        <th>${t("table.time")}</th><th>${t("login.user")}</th><th>Score</th><th>✓</th><th>Feature</th><th>ROI</th>
      </tr></thead><tbody>${rows
        .map((r) => {
          const roi = [
            r.time_saved_hours != null ? `${r.time_saved_hours}h` : "",
            r.cost_saved_estimate != null ? `€${r.cost_saved_estimate}` : "",
          ]
            .filter(Boolean)
            .join(" · ");
          return `<tr>
            <td>${escapeHtml((r.created_at || "").slice(0, 16))}</td>
            <td>${escapeHtml(r.actor_username || "—")}</td>
            <td>${r.satisfaction_score ?? "—"}</td>
            <td>${r.would_recommend ? "✓" : "—"}</td>
            <td>${escapeHtml(r.best_feature || "—")}</td>
            <td>${escapeHtml(roi || "—")}</td>
          </tr>`;
        })
        .join("")}</tbody></table>`
      : `<p class="muted">${t("analytics.noSurveys")}</p>`;
    $("usageTrendsPanel").innerHTML = "";
    $("moduleAlertsPanel").innerHTML = "";
    $("featureUsagePanel").innerHTML = `<p class="muted">${t("common.selectCompany")}</p>`;
    await loadSurveyInvitePanel(q);
    return;
  }
  const periodQs = `${q}${q ? "&" : "?"}period=${encodeURIComponent(analyticsPeriod)}`;
  const featDays = analyticsPeriod === "week" ? 14 : 7;
  const featQs = `${q}${q ? "&" : "?"}days=${featDays}`;
  const [usage, features, surveys, trends] = await Promise.all([
    api(`/api/v2/admin/usage-stats${periodQs}`),
    api(`/api/v2/admin/feature-usage${featQs}`),
    api(`/api/v2/admin/satisfaction-surveys${q}`),
    api(`/api/v2/admin/usage-trends${q}${q ? "&" : "?"}days=${featDays}`),
  ]);
  const cards = [
    ["analytics.activeUsers", usage.activeUsers],
    ["analytics.logins", usage.logins],
    ["analytics.attendance", usage.attendanceCheckIns],
    ["analytics.lateCheckIns", usage.lateCheckIns],
    ["analytics.contracts", usage.contractsCreated],
    ["analytics.documents", usage.documentsCreated],
    ["analytics.messages", usage.internalMessagesSent],
  ];
  $("usageStatCards").innerHTML = cards
    .map(
      ([key, val]) =>
        `<div class="card"><span class="muted">${t(key)}</span><strong>${val ?? 0}</strong></div>`,
    )
    .join("");

  renderUsageTrends(trends);
  renderModuleAlerts(features.unusedModuleAlerts || []);
  await loadSurveyInvitePanel(q);

  const sum = surveys.summary || {};
  $("satisfactionSummaryCards").innerHTML = `
    <div class="card"><span class="muted">${t("analytics.avgScore")}</span><strong>${sum.avgSatisfactionScore ?? "—"}</strong></div>
    <div class="card"><span class="muted">${t("analytics.recommendRate")}</span><strong>${sum.recommendRate != null ? `${Math.round(sum.recommendRate * 100)}%` : "—"}</strong></div>
    <div class="card"><span class="muted">${t("analytics.avgTimeSaved")}</span><strong>${sum.avgTimeSavedHours ?? "—"}</strong></div>
    <div class="card"><span class="muted">${t("analytics.avgCostSaved")}</span><strong>${sum.avgCostSavedEstimate != null ? `€${sum.avgCostSavedEstimate}` : "—"}</strong></div>
  `;

  const rows = surveys.surveys || [];
  $("satisfactionSurveysList").innerHTML = rows.length
    ? `<table class="data-table"><thead><tr>
        <th>${t("table.time")}</th><th>${t("login.user")}</th><th>Score</th><th>✓</th><th>Feature</th><th>ROI</th>
      </tr></thead><tbody>${rows
        .map((r) => {
          const roi = [
            r.time_saved_hours != null ? `${r.time_saved_hours}h` : "",
            r.cost_saved_estimate != null ? `€${r.cost_saved_estimate}` : "",
          ]
            .filter(Boolean)
            .join(" · ");
          return `<tr>
            <td>${escapeHtml((r.created_at || "").slice(0, 16))}</td>
            <td>${escapeHtml(r.actor_username || "—")}</td>
            <td>${r.satisfaction_score ?? "—"}</td>
            <td>${r.would_recommend ? "✓" : "—"}</td>
            <td>${escapeHtml(r.best_feature || "—")}</td>
            <td>${escapeHtml(roi || "—")}</td>
          </tr>`;
        })
        .join("")}</tbody></table>`
    : `<p class="muted">${t("analytics.noSurveys")}</p>`;

  const daily = features.dailyUsed || [];
  const unused = features.unusedModules || [];
  const freq = features.frequentRequests || [];
  const confusion = features.confusionReports || [];
  $("featureUsagePanel").innerHTML = `
    <div class="analytics-feature-grid">
      <div class="card">
        <h3 class="section-title">${t("analytics.dailyUsed")}</h3>
        ${daily.length ? `<ul class="analytics-list">${daily.map((m) => `<li><strong>${escapeHtml(featureLabel(m.featureId, m.label))}</strong> — ${m.hits} hits / ${m.activeDays}d</li>`).join("")}</ul>` : `<p class="muted">${t("analytics.noFeatures")}</p>`}
      </div>
      <div class="card">
        <h3 class="section-title">${t("analytics.unused")}</h3>
        ${unused.length ? `<ul class="analytics-list">${unused.map((m) => `<li>${escapeHtml(featureLabel(m.featureId, m.label))}</li>`).join("")}</ul>` : `<p class="muted">—</p>`}
      </div>
      <div class="card">
        <h3 class="section-title">${t("analytics.frequentRequests")}</h3>
        ${freq.length ? `<ul class="analytics-list">${freq.map((m) => `<li>${escapeHtml(m.text)} <span class="muted">(${m.count})</span></li>`).join("")}</ul>` : `<p class="muted">—</p>`}
      </div>
      <div class="card">
        <h3 class="section-title">${t("analytics.confusion")}</h3>
        ${confusion.length ? `<ul class="analytics-list">${confusion.map((m) => `<li>${escapeHtml(m.confusion_note)} <span class="muted">(${m.satisfaction_score})</span></li>`).join("")}</ul>` : `<p class="muted">—</p>`}
      </div>
    </div>`;
}

async function loadSurveyInvitePanel(q) {
  const panel = $("surveyInvitePanel");
  if (!panel) return;
  const user = getUser();
  if (user.role === "superadmin" && !q) {
    panel.innerHTML = `
      <div class="card survey-invite-card">
        <h3 class="section-title">${t("section.analytics.satisfaction")} — E-Mail</h3>
        <p class="survey-mail-banner survey-mail-pending">${t("survey.selectCompanyFirst")}</p>
      </div>`;
    return;
  }
  try {
    const data = await api(`/api/v2/admin/satisfaction-survey/invite-candidates${q}`);
    const mail = data.mail || {};
    const candidates = data.candidates || [];
    const mailReady = Boolean(mail.configured);
    const imapOnly = Boolean(mail.imapConfigured && !mail.configured);
    const withEmail = candidates.filter((c) => String(c.email || "").trim());
    const mailBanner = mailReady
      ? `<p class="survey-mail-banner survey-mail-ok">${t("survey.mailReady", { provider: (mail.providers || []).join(", ") || "—" })}</p>`
      : imapOnly
        ? `<p class="survey-mail-banner survey-mail-pending">${escapeHtml(mail.hint || "IMAP aktiv — ausgehende E-Mails (SMTP/Resend) fehlen noch.")}</p>`
        : `<p class="survey-mail-banner survey-mail-pending">${t("survey.mailPending")}</p>`;

    const reasonLabel = (c) => {
      if (c.eligible) return t("survey.eligible");
      if (c.ineligibleReason === "missing_email") return t("survey.missingEmail");
      if (c.ineligibleReason === "usage_too_short") {
        const need = Math.max(0, (data.usageDaysRequired || 30) - (c.usageDays || 0));
        return t("survey.waitUsage", { days: need });
      }
      if (c.ineligibleReason === "recent_invite") return t("survey.recentInvite");
      if (c.ineligibleReason === "recent_submission") return t("survey.recentSubmission");
      return "—";
    };

    const rows = candidates.length
      ? candidates
          .map(
            (c) => `<tr>
              <td>${escapeHtml(c.name || c.username || "—")}${c.surveyPromptEnabled ? ` <span class="badge badge-ok">${t("survey.promptOn")}</span>` : ""}</td>
              <td>${escapeHtml(c.email || "—")}${c.emailSource && c.emailSource !== "user" ? ` <span class="muted small">(${escapeHtml(c.emailSource)})</span>` : ""}</td>
              <td>${c.usageDays ?? 0}d</td>
              <td class="muted small">${escapeHtml(reasonLabel(c))}</td>
              <td>
                <button type="button" class="ghost small survey-send-btn" data-user-id="${escapeHtml(c.id)}"
                  ${!mailReady || !String(c.email || "").trim() ? "disabled" : ""}>${t("survey.sendOne")}</button>
              </td>
            </tr>`,
          )
          .join("")
      : "";

    panel.innerHTML = `
      <div class="card survey-invite-card">
        <h3 class="section-title">${t("section.analytics.satisfaction")} — E-Mail</h3>
        ${mailBanner}
        <p class="muted small">${t("survey.mailHint")}: <a href="${escapeHtml(mail.surveyUrl || "/satisfaction-survey.html")}" target="_blank" rel="noopener">${escapeHtml(mail.surveyUrl || "/satisfaction-survey.html")}</a></p>
        <div id="surveyInviteFeedback" class="survey-invite-feedback hidden" role="status" aria-live="polite"></div>
        <div class="survey-invite-actions">
          <button type="button" id="surveySendAllBtn" class="primary survey-send-all-btn">${t("survey.sendAll")}</button>
          <span class="muted small survey-invite-hint">${withEmail.length ? t("survey.sendAllHint", { count: withEmail.length }) : t("survey.noEmailUsers")}</span>
        </div>
        ${rows
          ? `<div class="table-wrap"><table class="data-table"><thead><tr>
              <th>${t("table.name")}</th><th>E-Mail</th><th>${t("analytics.periodDay")}</th><th>Status</th><th></th>
            </tr></thead><tbody>${rows}</tbody></table></div>`
          : `<p class="muted">${t("survey.noCandidates")}</p>`}
      </div>`;
  } catch (err) {
    panel.innerHTML = `<p class="muted">${escapeHtml(err.message || String(err))}</p>`;
  }
}

function showSurveyInviteFeedback(message, isError) {
  const el = document.getElementById("surveyInviteFeedback");
  if (el) {
    el.textContent = message;
    el.className = `survey-invite-feedback ${isError ? "err" : "ok"}`;
    el.classList.remove("hidden");
    el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  showActionToast(message, isError);
}

function setSurveyInviteBusy(busy) {
  const btn = document.getElementById("surveySendAllBtn");
  if (!btn) return;
  btn.disabled = Boolean(busy);
  btn.setAttribute("aria-busy", busy ? "true" : "false");
  if (busy) {
    btn.dataset.prevLabel = btn.textContent || "";
    btn.textContent = t("survey.sending");
  } else if (btn.dataset.prevLabel) {
    btn.textContent = btn.dataset.prevLabel;
    delete btn.dataset.prevLabel;
  }
}

function bindSurveyInvitePanelActions() {
  const panel = $("surveyInvitePanel");
  if (!panel || panel.dataset.surveyInviteBound === "1") return;
  panel.dataset.surveyInviteBound = "1";
  panel.addEventListener("click", (event) => {
    const allBtn = event.target.closest("#surveySendAllBtn, .survey-send-all-btn");
    if (allBtn) {
      event.preventDefault();
      sendSurveyInvite({ send_all: true }).catch(notifyTabError);
      return;
    }
    const oneBtn = event.target.closest(".survey-send-btn");
    if (oneBtn) {
      event.preventDefault();
      const uid = oneBtn.getAttribute("data-user-id");
      if (uid) sendSurveyInvite({ user_id: uid }).catch(notifyTabError);
    }
  });
}

function surveyInviteResultMessage(result) {
  const sent = Number(result?.sent) || 0;
  const skipped = Number(result?.skipped) || 0;
  if (sent > 0 && skipped > 0) {
    return { message: t("survey.sentBatch", { sent, skipped }), isError: false };
  }
  if (sent > 0) {
    return { message: t("survey.sentOk", { email: `${sent}` }), isError: false };
  }
  if (result?.error === "mail_not_configured") {
    return { message: result.hint || t("survey.mailPending"), isError: true };
  }
  if (result?.error === "no_recipients") {
    return { message: t("survey.noEmailUsers"), isError: true };
  }
  if (result?.error === "all_skipped") {
    return { message: t("survey.allSkipped", { skipped }), isError: true };
  }
  const detail = result?.errors?.[0]?.error || result?.error || "—";
  return { message: t("survey.sentFail", { error: detail }), isError: true };
}

async function sendSurveyInvite(body) {
  const q = companyQuery();
  const user = getUser();
  if (user.role === "superadmin" && !companyIdFromQuery()) {
    showSurveyInviteFeedback(t("survey.selectCompanyFirst"), true);
    return;
  }
  setSurveyInviteBusy(true);
  try {
    const result = await api(`/api/v2/admin/satisfaction-survey/invite${q}`, {
      method: "POST",
      body: JSON.stringify(body || {}),
    });
    const toast = surveyInviteResultMessage(result);
    showSurveyInviteFeedback(toast.message, toast.isError);
    await loadSurveyInvitePanel(q);
  } catch (err) {
    const data = err.data || {};
    const toast = surveyInviteResultMessage(data);
    if (toast.message) {
      showSurveyInviteFeedback(toast.message, toast.isError);
    } else if (data.error === "mail_not_configured" || err.status === 503) {
      showSurveyInviteFeedback(data.hint || t("survey.mailPending"), true);
    } else {
      showSurveyInviteFeedback(t("survey.sentFail", { error: err.message || "—" }), true);
    }
    await loadSurveyInvitePanel(q);
  } finally {
    setSurveyInviteBusy(false);
  }
}

function renderUsageTrends(trends) {
  const panel = $("usageTrendsPanel");
  if (!panel) return;
  const daily = trends?.dailyActiveUsers || [];
  const weekly = trends?.weeklySatisfaction || [];
  const peak = Math.max(1, Number(trends?.peakActiveUsers || 1));

  const dauBars = daily
    .map((d) => {
      const h = Math.max(6, Math.round((Number(d.activeUsers || 0) / peak) * 100));
      return `<div class="trend-bar-wrap" title="${escapeHtml(d.date)}: ${d.activeUsers}">
        <div class="trend-bar" style="height:${h}%"></div>
        <span class="trend-bar-label">${escapeHtml((d.date || "").slice(5))}</span>
      </div>`;
    })
    .join("");

  const satBars = weekly
    .map((w) => {
      const score = Number(w.avgSatisfactionScore || 0);
      const h = score ? Math.max(8, Math.round(((6 - score) / 5) * 100)) : 6;
      return `<div class="trend-bar-wrap" title="${escapeHtml(w.week)}: ${score || "—"}">
        <div class="trend-bar trend-bar-sat" style="height:${h}%"></div>
        <span class="trend-bar-label">${escapeHtml((w.week || "").replace("W", ""))}</span>
      </div>`;
    })
    .join("");

  panel.innerHTML = `
    <div class="analytics-trends-grid">
      <div class="card">
        <h3 class="section-title">${t("analytics.trendDau")}</h3>
        <div class="trend-chart" role="img" aria-label="${t("analytics.trendDau")}">${dauBars || `<p class="muted">—</p>`}</div>
      </div>
      <div class="card">
        <h3 class="section-title">${t("analytics.trendSatisfaction")}</h3>
        <div class="trend-chart" role="img" aria-label="${t("analytics.trendSatisfaction")}">${satBars || `<p class="muted">—</p>`}</div>
        <p class="muted small">${t("analytics.avgScore")}</p>
      </div>
    </div>`;
}

function renderModuleAlerts(alerts) {
  const panel = $("moduleAlertsPanel");
  if (!panel) return;
  if (!alerts.length) {
    panel.innerHTML = "";
    return;
  }
  panel.innerHTML = `
    <h2 class="section-title">${t("analytics.moduleAlerts")}</h2>
    <div class="analytics-alerts-list">
      ${alerts
        .map(
          (a) => `<div class="analytics-alert analytics-alert-${escapeHtml(a.severity || "info")}">
            <strong>${escapeHtml(featureLabel(a.featureId, a.label))}</strong>
            <span class="muted small">${escapeHtml(moduleAlertMessage(a))}</span>
          </div>`,
        )
        .join("")}
    </div>`;
}

async function maybePromptSatisfactionSurvey() {
  try {
    const dismissUntil = Number(wpGet("wp-survey-dismiss-until") || 0);
    if (dismissUntil > Date.now()) return;
    const pending = await api("/api/v2/satisfaction-survey/pending");
    if (!pending?.pending) return;
    const modal = $("satisfactionSurveyModal");
    const intro = $("satisfactionSurveyIntro");
    if (intro) {
      if (pending.invitedRecently) {
        intro.textContent = t("survey.modalInvited");
      } else if (pending.surveyPromptEnabled) {
        intro.textContent = t("survey.modalPromptEnabled");
      } else {
        intro.textContent = t("survey.modalDefault");
      }
    }
    if (modal) modal.classList.remove("hidden");
  } catch {
    // no-op
  }
}

async function loadOverview() {
  renderOverviewQuickBar();
  $("overviewQuickBar")?.classList.remove("hidden");
  renderQuickLinks();
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    $("statCards").innerHTML = `<p class="muted">${t("common.selectCompany")}</p>`;
    return;
  }
  const cid = q.replace("?company_id=", "");
  const [overview, inbox, roleDash, opsBrief] = await Promise.all([
    api(`/api/v2/admin/overview${q}`),
    api(`/api/inbox${q}`).catch(() => ({ counts: {} })),
    api(`/api/dashboard/role${q}`).catch(() => null),
    cid
      ? api(`/api/ops-os/overview?company_id=${encodeURIComponent(cid)}`).catch(() => null)
      : Promise.resolve(null),
  ]);
  const wf = overview.workforce || {};
  const openInbox = inbox?.counts?.open ?? 0;
  const dashWidgets = (roleDash?.widgets || []).filter((w) => w.id !== "on_site");
  const extraCards = dashWidgets
    .map(
      (w) =>
        `<div class="card"><span class="muted">${escapeHtml(widgetLabel(w))}</span><strong>${widgetValue(w)}</strong>${widgetDetail(w) ? `<small class="muted">${escapeHtml(widgetDetail(w))}</small>` : ""}</div>`,
    )
    .join("");
  $("statCards").innerHTML = `
    <div class="card"><span class="muted">${t("overview.onSite")}</span><strong>${wf.onSite ?? 0}</strong></div>
    <div class="card"><span class="muted">${t("overview.activeWorkers")}</span><strong>${wf.totalActive ?? 0}</strong></div>
    <div class="card"><span class="muted">${t("overview.geofenceZones")}</span><strong>${overview.zonesCount ?? 0}</strong></div>
    <button type="button" class="card" data-goto-tab="inbox" style="cursor:pointer;text-align:start;border:1px solid var(--border)">
      <span class="muted">${t("overview.inbox")}</span><strong style="color:${openInbox > 0 ? "#fbbf24" : "inherit"}">${openInbox}</strong>
    </button>
    ${extraCards}
  `;
  $("statCards").querySelector('[data-goto-tab="inbox"]')?.addEventListener("click", async () => {
    switchToTab("inbox");
    await loadInbox();
  });
  const fc = overview.tomorrowForecast || {};
  const fp = $("forecastPanel");
  if (fp && fc.date) {
    fp.classList.remove("hidden");
    fp.innerHTML = `
      <div class="card forecast-card">
        <div class="forecast-head">
          <span class="muted">${t("overview.forecastTomorrow", { day: typeof fc.weekday === "number" ? t(`weekday.${fc.weekday}`) : (fc.weekdayLabel || ""), date: fc.date })}</span>
          <span class="badge">${fc.confidence === "high" ? t("overview.confidenceHigh") : t("overview.confidenceMed")}</span>
        </div>
        <p class="forecast-summary">${formatForecastSummary(fc)}</p>
        <div class="cards forecast-stats">
          <div><span class="muted">${t("overview.expectedOnSite")}</span><strong>${fc.expectedOnSite ?? "—"}</strong></div>
          <div><span class="muted">${t("overview.absentRisk")}</span><strong>${fc.expectedAbsent ?? "—"}</strong></div>
          <div><span class="muted">${t("overview.totalActive")}</span><strong>${fc.totalActive ?? "—"}</strong></div>
        </div>
        <p class="muted small"><a href="/ai-command-center.html${q}">${t("ops.aiCenter")}</a> · <a href="/ops-command-center.html${q}">${t("ops.commandCenter")}</a></p>
      </div>`;
  } else if (fp) {
    fp.classList.add("hidden");
    fp.innerHTML = "";
  }
  const strip = $("opsCommandStrip");
  if (strip && q) {
    strip.classList.remove("hidden");
    const twin = opsBrief?.layers?.["1_digital_twin"]?.summary || {};
    const sec = opsBrief?.layers?.["2_ai_security"] || {};
    const emg = opsBrief?.layers?.["5_emergency"] || {};
    strip.innerHTML = `
      <span class="ops-strip-kpi"><strong>${twin.workersOnSite ?? wf.onSite ?? 0}</strong> ${t("overview.onSiteKpi")}</span>
      <span class="ops-strip-kpi"><strong>${(sec.openAlerts || []).length}</strong> ${t("inbox.filterSecurity")}</span>
      <span class="ops-strip-kpi">${emg.active ? t("overview.emergency") : t("overview.calm")}</span>
      <a href="/ops-command-center.html${q}" target="_blank" rel="noopener">${t("ops.commandCenter")}</a>
      <a href="/ops-live-map.html${q}" target="_blank" rel="noopener">${t("ops.liveMap")}</a>
      <a href="/ai-command-center.html${q}" target="_blank" rel="noopener">${t("ops.aiCenter")}</a>
      <a href="/foreman.html" target="_blank" rel="noopener">${t("overview.foreman")}</a>
      <button type="button" class="ghost ops-strip-tab" data-goto-tab="operations">${t("overview.layers12")}</button>
    `;
    strip.querySelector(".ops-strip-tab")?.addEventListener("click", async () => {
      switchToTab("operations");
      await loadOperations();
    });
  } else if (strip) {
    strip.classList.add("hidden");
  }
  renderTable($("recentAccess"), overview.recentAccess || [], [
    { label: t("table.worker"), render: (r) => `${r.first_name || ""} ${r.last_name || ""}`.trim() },
    { label: t("workers.colBadge"), render: (r) => r.badge_id || "-" },
    {
      label: t("table.direction"),
      render: (r) => formatAccessDirection(r.direction),
    },
    { label: t("table.gate"), render: (r) => r.gate || "-" },
    { label: t("table.time"), render: (r) => (r.timestamp || "").slice(0, 19) },
  ]);
}

async function loadQrImage(link) {
  const token = wpGet(TOKEN_KEY);
  const res = await fetch(`/api/qr.png?data=${encodeURIComponent(link)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    throw new Error("qr_failed");
  }
  return URL.createObjectURL(await res.blob());
}

function closeJoinModal() {
  const modal = $("joinModal");
  modal.classList.add("hidden");
  const img = $("joinQrImg");
  if (img.dataset.blobUrl) {
    URL.revokeObjectURL(img.dataset.blobUrl);
    delete img.dataset.blobUrl;
  }
  img.removeAttribute("src");
}

async function showWorkerJoin(workerId, workerName) {
  const payload = await api(`/api/workers/${encodeURIComponent(workerId)}/app-access`, {
    method: "POST",
  });
  const link = payload.link || payload.joinLink || "";
  if (!link) {
    alert(t("join.noLink"));
    return;
  }
  $("joinModalName").textContent = workerName;
  $("joinLinkInput").value = link;
  const exp = payload.accessExpiresAt ? String(payload.accessExpiresAt).slice(0, 19) : "";
  $("joinExpires").textContent = exp ? t("join.expires", { exp }) : t("join.once");
  const blobUrl = await loadQrImage(link);
  const img = $("joinQrImg");
  img.src = blobUrl;
  img.dataset.blobUrl = blobUrl;
  $("joinModal").classList.remove("hidden");
}

$("joinCloseBtn").addEventListener("click", closeJoinModal);
$("joinModal").addEventListener("click", (e) => {
  if (e.target === $("joinModal")) closeJoinModal();
});
$("joinCopyBtn").addEventListener("click", async () => {
  const link = $("joinLinkInput").value;
  try {
    await navigator.clipboard.writeText(link);
    alert(t("common.copyDone"));
  } catch {
    $("joinLinkInput").select();
    document.execCommand("copy");
    alert(t("common.copyDone"));
  }
});

async function assignNfc(workerId, inputEl) {
  const uid = (inputEl.value || "").trim();
  if (!uid) {
    alert(t("workers.nfcPrompt"));
    return;
  }
  await api(`/api/v2/workers/${encodeURIComponent(workerId)}/physical-card${companyQuery()}`, {
    method: "PATCH",
    body: JSON.stringify({ physicalCardId: uid }),
  });
  alert(t("workers.nfcSaved"));
  await loadWorkers();
}

function companyDeploymentMonthParts() {
  const raw = $("deploymentCompanyMonth")?.value || "";
  const [y, m] = raw.split("-").map((x) => parseInt(x, 10));
  if (!y || !m) {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() + 1 };
  }
  return { year: y, month: m };
}

function renderDeploymentMonthStatus(batch) {
  const el = $("deploymentMonthStatus");
  if (!el) return;
  const st = batch?.status || "draft";
  const awaiting = batch?.awaitingConfirm;
  let label = t("deployment.statusDraft");
  let cls = "deployment-status-badge draft";
  if (st === "sent" && !awaiting) {
    label = t("deployment.statusSent");
    cls = "deployment-status-badge sent";
  } else if (awaiting || st === "draft") {
    label = t("deployment.statusAwaiting");
    cls = "deployment-status-badge awaiting";
  }
  el.textContent = label;
  el.className = cls;
  $("deploymentReopenMonthBtn")?.classList.toggle("hidden", st !== "sent" || awaiting);
  $("deploymentConfirmSendBtn")?.classList.toggle("hidden", st === "sent" && !awaiting);
}

function renderDeploymentDeclinesBanner(state) {
  const bar = $("deploymentMonthBar");
  if (!bar) return;
  let banner = document.getElementById("deploymentDeclinesBanner");
  const count = Number(state?.declinedDayCount || 0);
  if (!count) {
    banner?.remove();
    return;
  }
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "deploymentDeclinesBanner";
    banner.className = "deployment-declines-banner";
    banner.setAttribute("role", "alert");
    bar.insertAdjacentElement("afterend", banner);
  }
  const declines = (state.recentDeclines || []).slice(0, 8);
  const items = declines
    .map((item) => {
      const name = escapeAttr(item.workerName || item.workerId || "—");
      const date = escapeAttr(String(item.workDate || "").slice(0, 10));
      const loc = escapeAttr(item.location || "—");
      const reason = escapeAttr(item.reason || "");
      const reasonPart = reason ? ` — ${reason}` : "";
      return `<li class="deployment-decline-clickable" role="button" tabindex="0"><strong>${name}</strong> · ${date} · ${loc}${reasonPart}</li>`;
    })
    .join("");
  banner.innerHTML = `
    <div class="deployment-declines-banner-inner">
      <p class="deployment-declines-banner-title">${escapeAttr(t("deployment.declinesBannerTitle"))}</p>
      <p class="muted small">${escapeAttr(t("deployment.declinesBannerHint"))}</p>
      <ul class="deployment-declines-list">${items}</ul>
    </div>`;
  banner.querySelectorAll(".deployment-decline-clickable").forEach((li, idx) => {
    const item = declines[idx];
    if (!item?.workerId) return;
    const openDecline = () => {
      void handleDeploymentDeclineClick(item).catch((e) => showActionToast(e.message, true));
    };
    li.addEventListener("click", openDecline);
    li.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openDecline();
      }
    });
  });
}

async function loadDeploymentMonthBar() {
  const bar = $("deploymentMonthBar");
  const q = companyQuery();
  if (!bar) return;
  if (getUser().role === "superadmin" && !q) {
    bar.classList.add("hidden");
    return;
  }
  bar.classList.remove("hidden");
  const now = new Date();
  if (!$("deploymentCompanyMonth").value) {
    $("deploymentCompanyMonth").value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  }
  const { year, month } = companyDeploymentMonthParts();
  try {
    deploymentMonthState = await api(
      `/api/workforce/deployment-month${q}${q ? "&" : "?"}year=${year}&month=${month}`,
    );
    renderDeploymentMonthStatus(deploymentMonthState.batch);
    const ready = deploymentMonthState.readyCount ?? 0;
    const total = deploymentMonthState.totalWorkers ?? 0;
    let statsText = t("deployment.monthStats", { ready, total });
    const declined = Number(deploymentMonthState.declinedDayCount || 0);
    if (declined > 0 && t("deployment.monthStatsDeclines")) {
      statsText += t("deployment.monthStatsDeclines", { count: declined });
    }
    $("deploymentMonthStats").textContent = statsText;
    renderDeploymentDeclinesBanner(deploymentMonthState);
  } catch (e) {
    deploymentMonthState = null;
    $("deploymentMonthStats").textContent = e.message;
  }
}

function bindDeploymentMonthBarOnce() {
  if (bindDeploymentMonthBarOnce._done) return;
  bindDeploymentMonthBarOnce._done = true;
  $("deploymentCompanyMonth")?.addEventListener("change", () =>
    loadDeploymentMonthBar().catch((e) => showActionToast(e.message, true)),
  );
  $("deploymentPrepareNextBtn")?.addEventListener("click", async () => {
    const q = companyQuery();
    const res = await api(`/api/workforce/deployment-month/prepare-next${q}`, {
      method: "POST",
      body: JSON.stringify({ useAutopilotLogic: true }),
    });
    showActionToast(t("deployment.preparedOk"), false);
    await loadDeploymentMonthBar();
    if (res.year && res.month) {
      $("deploymentCompanyMonth").value = `${res.year}-${String(res.month).padStart(2, "0")}`;
      await loadDeploymentMonthBar();
    }
  });
  $("deploymentReopenMonthBtn")?.addEventListener("click", async () => {
    const q = companyQuery();
    const { year, month } = companyDeploymentMonthParts();
    await api(`/api/workforce/deployment-month/reopen${q}`, {
      method: "POST",
      body: JSON.stringify({ year, month }),
    });
    await loadDeploymentMonthBar();
    showActionToast(t("deployment.reopenEdit") + " ✓", false);
  });
  $("deploymentConfirmSendBtn")?.addEventListener("click", () => {
    const ready = deploymentMonthState?.readyCount ?? 0;
    $("deploymentConfirmStats").textContent = `${ready} ${t("deployment.confirmSendNow")}`;
    $("deploymentConfirmCheckbox").checked = false;
    $("deploymentConfirmModal").classList.remove("hidden");
  });
  $("deploymentConfirmCancelBtn")?.addEventListener("click", () =>
    $("deploymentConfirmModal").classList.add("hidden"),
  );
  $("deploymentConfirmModal")?.addEventListener("click", (e) => {
    if (e.target?.id === "deploymentConfirmModal") $("deploymentConfirmModal").classList.add("hidden");
  });
  $("deploymentBrandingPdfBtn")?.addEventListener("click", () =>
    previewDeploymentBrandingPdf().catch((e) => showActionToast(e.message, true)),
  );
  $("deploymentBrandingPdfCloseBtn")?.addEventListener("click", closeDeploymentBrandingPdfPreview);
  $("deploymentBrandingPdfModal")?.addEventListener("click", (e) => {
    if (e.target?.id === "deploymentBrandingPdfModal") closeDeploymentBrandingPdfPreview();
  });
  $("deploymentBrandingPdfPrintBtn")?.addEventListener("click", () => {
    const frame = $("deploymentBrandingPdfFrame");
    try {
      frame?.contentWindow?.focus();
      frame?.contentWindow?.print();
    } catch {
      showActionToast(t("common.error"), true);
    }
  });
  $("deploymentConfirmSubmitBtn")?.addEventListener("click", async () => {
    if (!$("deploymentConfirmCheckbox").checked) {
      showActionToast(t("deployment.confirmCheck"), true);
      return;
    }
    const q = companyQuery();
    const { year, month } = companyDeploymentMonthParts();
    const res = await api(`/api/workforce/deployment-month/confirm-send${q}`, {
      method: "POST",
      body: JSON.stringify({
        year,
        month,
        confirmSend: true,
        lang: getLang().slice(0, 2),
      }),
    });
    $("deploymentConfirmModal").classList.add("hidden");
    if (!res.ok) {
      showActionToast(res.error || t("common.error"), true);
      return;
    }
    showActionToast(`${t("deployment.sentOk")} (${res.sent})`, false);
    await loadDeploymentMonthBar();
  });
}

async function loadWorkers() {
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    $("workersTable").innerHTML = `<p class="muted" style="padding:1rem">${t("common.selectCompany")}</p>`;
    $("deploymentMonthBar")?.classList.add("hidden");
    return;
  }
  await loadDeploymentMonthBar();
  try {
    const data = await api(`/api/v2/workers${q}`);
    const rows = data.workers || [];
    window.__adminV2WorkersCache = rows;
    const container = $("workersTable");
    if (!rows.length) {
      container.innerHTML = `<p class="muted" style="padding:1rem">${t("common.noWorkers")}</p>`;
      return;
    }
  const head = `
    <tr>
      <th>${t("workers.colName")}</th>
      <th>${t("workers.colBadge")}</th>
      <th>${t("workers.colNfc")}</th>
      <th>${t("workers.colAssign")}</th>
      <th>${t("workers.colActions")}</th>
    </tr>`;
  const body = rows
    .map((r) => {
      const id = r.id;
      const name = `${r.first_name || ""} ${r.last_name || ""}`.trim();
      const current = r.physical_card_id || "";
      return `<tr>
        <td>${name}</td>
        <td>${r.badge_id || "-"}</td>
        <td><code>${current || "—"}</code></td>
        <td>
          <input class="nfc-input" type="text" placeholder="UID" value="${current}" data-worker-id="${id}" />
          <button type="button" class="btn-link" data-save-nfc="${id}">${t("common.save")}</button>
        </td>
        <td class="worker-action-cell">
          <div class="worker-action-group">
            <button type="button" class="worker-action-btn worker-action-btn-primary" data-deployment-plan="${id}" data-worker-name="${name.replace(/"/g, "&quot;")}">${t("deployment.planBtn")}</button>
            <button type="button" class="worker-action-btn worker-action-btn-ghost" data-worker-contracts="${id}" data-worker-name="${name.replace(/"/g, "&quot;")}">${t("workers.contracts")}</button>
            <button type="button" class="worker-action-btn worker-action-btn-ghost" data-join-app="${id}" data-worker-name="${name.replace(/"/g, "&quot;")}">${t("workers.joinQr")}</button>
          </div>
        </td>
      </tr>`;
    })
    .join("");
  container.innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
  container.querySelectorAll("[data-save-nfc]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const wid = btn.getAttribute("data-save-nfc");
      const input = container.querySelector(`input[data-worker-id="${wid}"]`);
      assignNfc(wid, input).catch((e) => alert(e.message));
    });
  });
  container.querySelectorAll("[data-join-app]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const wid = btn.getAttribute("data-join-app");
      const wname = btn.getAttribute("data-worker-name") || wid;
      showWorkerJoin(wid, wname).catch((e) => alert(e.message || e));
    });
  });
  container.querySelectorAll("[data-deployment-plan]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const wid = btn.getAttribute("data-deployment-plan");
      const wname = btn.getAttribute("data-worker-name") || wid;
      openDeploymentModal(wid, wname).catch((e) => showActionToast(e.message, true));
    });
  });
  container.querySelectorAll("[data-worker-contracts]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const wid = btn.getAttribute("data-worker-contracts");
      const q = companyQuery();
      location.href = `/admin-v2/contracts.html${q}&worker_id=${encodeURIComponent(wid)}`;
    });
  });
  } catch (error) {
    $("workersTable").innerHTML = `<p class="muted" style="padding:1rem">${error?.message || "Mitarbeiter konnten nicht geladen werden."}</p>`;
  }
}

async function loadAccess() {
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    $("accessTable").innerHTML = `<p class="muted" style="padding:1rem">${t("common.selectCompany")}</p>`;
    $("accessSummary").innerHTML = "";
    return;
  }
  try {
    const summary = await api(`/api/access-logs/summary${q}`);
    const open = Array.isArray(summary.openEntries) ? summary.openEntries.length : 0;
    const hourly = Array.isArray(summary.hourly) ? summary.hourly : [];
    const checkIns = hourly.reduce((n, h) => n + (h.checkIn || 0), 0);
    const checkOuts = hourly.reduce((n, h) => n + (h.checkOut || 0), 0);
    const lateToday = Number(summary.lateCheckInsToday || 0);
    $("accessSummary").innerHTML = `
      <div class="card"><span class="muted">${t("access.checkIns")}</span><strong>${checkIns}</strong></div>
      <div class="card"><span class="muted">${t("access.checkOuts")}</span><strong>${checkOuts}</strong></div>
      <div class="card"><span class="muted">${t("access.openSessions")}</span><strong>${open}</strong></div>
      <div class="card"><span class="muted">${t("access.lateCheckIns")}</span><strong>${lateToday}</strong></div>
    `;
  } catch {
    $("accessSummary").innerHTML = "";
  }
  const exportLink = $("exportCsvLink");
  if (exportLink) {
    const csvQuery = q ? `${q}&format=csv` : "?format=csv";
    exportLink.href = `/api/access-logs/export.csv${csvQuery}`;
    exportLink.onclick = (e) => {
      const token = wpGet(TOKEN_KEY);
      if (!token) return;
      e.preventDefault();
      fetch(exportLink.href, { headers: { Authorization: `Bearer ${token}` } })
        .then((r) => r.blob())
        .then((blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "access-logs.csv";
          a.click();
          URL.revokeObjectURL(url);
        })
        .catch((err) => alert(err.message || "export_failed"));
    };
  }
  const data = await api(`/api/v2/access/live${q}`);
  renderTable($("accessTable"), data.access_logs || [], [
    { label: t("table.worker"), render: (r) => `${r.first_name || ""} ${r.last_name || ""}`.trim() },
    { label: t("table.direction"), render: (r) => formatAccessDirection(r.direction) },
    { label: t("table.gate"), render: (r) => r.gate || "-" },
    { label: t("table.time"), render: (r) => (r.timestamp || "").slice(0, 19) },
    {
      label: t("access.late"),
      render: (r) =>
        r.direction === "check-in" && Number(r.checked_in_late || 0) === 1
          ? `<span class="badge badge-warn">${t("access.lateYes")}</span>`
          : "—",
    },
  ]);
}

async function loadCopilot() {
  const answerEl = $("copilotAnswer");
  if (!answerEl) return;
  answerEl.textContent = t("section.copilot.idle");
}

$("copilotForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = ($("copilotQuestion")?.value || "").trim();
  if (!q) return;
  const answerEl = $("copilotAnswer");
  const btn = $("copilotSubmit");
  if (answerEl) answerEl.textContent = t("section.copilot.thinking");
  if (btn) btn.disabled = true;
  try {
    const cid = companyQuery().replace("?company_id=", "") || undefined;
    const res = await api("/api/ops-os/copilot", {
      method: "POST",
      body: JSON.stringify({ question: q, company_id: cid }),
    });
    const lines = [];
    if (res.answer) lines.push(String(res.answer));
    if (res.response) lines.push(String(res.response));
    if (res.deterministicAnswers?.answer) lines.push(String(res.deterministicAnswers.answer));
    if (res.hint) lines.push(`${t("section.copilot.hintPrefix")}: ${res.hint}`);
    if (res.contextSummary) {
      lines.push(
        `\n${t("section.copilot.context", {
          onSite: res.contextSummary.workersOnSite ?? 0,
          security: res.contextSummary.openSecurityFindings ?? 0,
        })}`,
      );
    }
    if (answerEl) answerEl.textContent = lines.filter(Boolean).join("\n\n") || JSON.stringify(res, null, 2);
  } catch (err) {
    if (answerEl) answerEl.textContent = err.message || String(err);
  } finally {
    if (btn) btn.disabled = false;
  }
});

function superadminNeedsCompany() {
  const user = getUser();
  return user.role === "superadmin" && !(wpGet(COMPANY_KEY) || "").trim();
}

async function refreshActiveTab() {
  if (superadminNeedsCompany()) {
    showActionToast(t("common.selectCompany"), true);
    return;
  }
  const active = document.querySelector(".tab.active");
  const tab = active?.dataset?.tab || "overview";
  if (tab === "inbox") {
    await loadInbox();
    await startAdminRealtime();
  }
  else if (tab === "copilot") await loadCopilot();
  else if (tab === "workers") await loadWorkers();
  else if (tab === "access") await loadAccess();
  else if (tab === "mobile") await loadMobile();
  else if (tab === "operations") await loadOperations();
  else if (tab === "platform") await loadPlatform();
  else if (tab === "tools") await loadTools();
  else if (tab === "analytics") await loadAnalytics();
  else if (tab === "enterprise") syncEnterpriseFrame();
  else await loadOverview();
}

async function bootSession() {
  showSessionBoot();
  const forceLoginForm = new URLSearchParams(location.search).get("login") === "1";
  if (isEmbedMode()) {
    await tryEmbedSessionFromControlPass();
  }
  let token = (wpGet(TOKEN_KEY) || "").trim();
  if (forceLoginForm && !isEmbedMode()) {
    showLogin();
    return;
  }
  if (!token || !(await probeSessionToken(token))) {
    const adopted = await adoptControlPassTokenIfValid();
    if (adopted) {
      token = wpGet(TOKEN_KEY);
    }
  }
  if (!token || !(await probeSessionToken(token))) {
    if (isEmbedMode()) {
      showEmbedAuthRequired(
        token ? t("login.sessionExpired") : t("login.embedRequired"),
      );
    } else {
      clearSessionAndShowLogin(token ? t("login.sessionExpired") : "");
    }
    return;
  }
  try {
    const data = await api("/api/v2/auth/session");
    if (data.user) {
      wpSet(USER_KEY, JSON.stringify(data.user));
      if (data.user.company_id && !wpGet(COMPANY_KEY)) {
        wpSet(COMPANY_KEY, data.user.company_id);
      }
    }
    await loadCompanies();
    const qsCid = new URLSearchParams(location.search).get("company_id") || "";
    if (qsCid) {
      applyParentCompanyId(qsCid);
    }
    showDashboard();
    await applyTenantBrandingFromApi();
    await applyStartupTabAfterLoad();
    if (pendingEinsatzplanFocus) {
      tryFocusEinsatzplanFromParent();
    }
    await loadPlatformBanner();
    const params = new URLSearchParams(location.search);
    if (params.get("einsatzplan") !== "1" && params.get("focus") !== "deployment") {
      await refreshActiveTab();
    }
    startAdminRealtime().catch(() => {});
    refreshInboxBadgeOnly().catch(() => {});
    maybePromptSatisfactionSurvey().catch(() => {});
  } catch (e) {
    if (isAuthError(e)) return;
    clearSessionAndShowLogin(t("login.sessionExpired"));
  }
}

$("loginBtn").addEventListener("click", async () => {
  $("loginError").classList.add("hidden");
  try {
    const payload = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({
        username: $("username").value.trim(),
        password: $("password").value,
        loginScope: "auto",
      }),
    });
    if (!payload.ok || !payload.token) {
      throw new Error(payload.error || "login_failed");
    }
    wpSet(TOKEN_KEY, payload.token);
    wpSet(USER_KEY, JSON.stringify(payload.user || {}));
    if (payload.user?.company_id) {
      wpSet(COMPANY_KEY, payload.user.company_id);
    }
    await loadCompanies();
    showDashboard();
    await applyTenantBrandingFromApi();
    await applyStartupTabAfterLoad();
    await loadPlatformBanner();
    const params = new URLSearchParams(location.search);
    if (params.get("einsatzplan") !== "1" && params.get("focus") !== "deployment") {
      await refreshActiveTab();
    }
    startAdminRealtime().catch(() => {});
    refreshInboxBadgeOnly().catch(() => {});
    maybePromptSatisfactionSurvey().catch(() => {});
  } catch (e) {
    $("loginError").textContent = e.message || t("login.fail");
    $("loginError").classList.remove("hidden");
  }
});

$("logoutBtn").addEventListener("click", async () => {
  try {
    await api("/api/v2/auth/revoke", { method: "POST" });
  } catch {
    // ignore
  }
  wpRemove(TOKEN_KEY);
  wpRemove(USER_KEY);
  showLogin();
});

$("refreshBtn").addEventListener("click", () => refreshActiveTab().catch(notifyTabError));

bindTabNavigation();

$("integrationWizardForm")?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  if (!pendingIntegrationProvider) return;
  const q = companyQuery();
  try {
    const fd = new FormData(ev.target);
    const body = buildConnectPayload(pendingIntegrationProvider, fd);
    await api(`/api/integrations/${pendingIntegrationProvider}/connect${q}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    $("integrationModal").classList.add("hidden");
    pendingIntegrationProvider = null;
    alert(t("common.ok"));
    if (document.querySelector(".tab.active")?.dataset?.tab === "tools") await loadTools();
  } catch (e) {
    alert(e.message);
  }
});

$("integrationModalClose")?.addEventListener("click", () => {
  $("integrationModal").classList.add("hidden");
  pendingIntegrationProvider = null;
});

$("opsLayerModalClose")?.addEventListener("click", () => {
  $("opsLayerModal")?.classList.add("hidden");
});

$("opsLayerModal")?.addEventListener("click", (e) => {
  if (e.target?.id === "opsLayerModal") $("opsLayerModal").classList.add("hidden");
});

function bindLangSelect(sel) {
  if (!sel) return;
  sel.value = getLang();
  sel.addEventListener("change", () => {
    setLang(sel.value);
    document.querySelectorAll("[data-lang-select]").forEach((other) => {
      if (other !== sel) other.value = getLang();
    });
  });
}
bindLangSelect($("langSelect"));
bindLangSelect($("langSelectDash"));
window.addEventListener("baupass-admin-lang", (event) => {
  const lang = event?.detail?.lang || getLang();
  broadcastLangToEnterpriseFrame(lang);
  const activeTab = document.querySelector(".tab.active")?.dataset?.tab;
  if (activeTab === "enterprise") syncEnterpriseFrame();
  loadSectorTerminologyForAdmin().catch(() => {});
  if ($("dashboardView").classList.contains("hidden")) return;
  const tab = document.querySelector(".tab.active")?.dataset?.tab;
  if (tab && TAB_TITLE_KEYS[tab]) {
    const titleEl = $("brandTitle");
    if (titleEl) {
      titleEl.textContent = t(TAB_TITLE_KEYS[tab]);
      titleEl.setAttribute("data-i18n", TAB_TITLE_KEYS[tab]);
    }
  }
  if (tab === "overview") {
    renderOverviewQuickBar();
    $("overviewQuickBar")?.classList.remove("hidden");
  } else {
    $("overviewQuickBar")?.classList.add("hidden");
  }
  refreshActiveTab().catch(() => {});
});
applyI18n();

$("satisfactionSurveyLater")?.addEventListener("click", () => {
  wpSet("wp-survey-dismiss-until", String(Date.now() + 7 * 24 * 60 * 60 * 1000));
  $("satisfactionSurveyModal")?.classList.add("hidden");
});

$("satisfactionSurveyForm")?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const errEl = $("satisfactionSurveyError");
  errEl?.classList.add("hidden");
  const score = Number($("satisfactionScore")?.value || 0);
  if (score < 1 || score > 5) {
    if (errEl) {
      errEl.textContent = "Bitte Zufriedenheit 1–5 wählen.";
      errEl.classList.remove("hidden");
    }
    return;
  }
  const btn = $("satisfactionSurveySubmit");
  if (btn) btn.disabled = true;
  try {
    await api("/api/v2/satisfaction-survey", {
      method: "POST",
      body: JSON.stringify({
        satisfaction_score: score,
        would_recommend: Boolean($("satisfactionRecommend")?.checked),
        best_feature: $("satisfactionBestFeature")?.value?.trim() || "",
        frequent_request: $("satisfactionFrequentRequest")?.value?.trim() || "",
        confusion_note: $("satisfactionConfusion")?.value?.trim() || "",
        time_saved_hours: $("satisfactionTimeSaved")?.value || null,
        cost_saved_estimate: $("satisfactionCostSaved")?.value || null,
      }),
    });
    $("satisfactionSurveyModal")?.classList.add("hidden");
    showActionToast("Danke für Ihre Bewertung!");
    if (document.querySelector(".tab.active")?.dataset?.tab === "analytics") {
      await loadAnalytics();
    }
  } catch (e) {
    if (errEl) {
      errEl.textContent = e.message || "Fehler";
      errEl.classList.remove("hidden");
    }
  } finally {
    if (btn) btn.disabled = false;
  }
});

bootSession();
if (window.BaupassAuth?.loadPublicTenantBranding) {
  void window.BaupassAuth.loadPublicTenantBranding();
}
bindSurveyInvitePanelActions();
