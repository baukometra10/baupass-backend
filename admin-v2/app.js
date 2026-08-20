import { applyI18n, featureLabel, formatForecastSummary, getLang, moduleAlertMessage, resolvePlanLabel, setLang, setSectorTermOverrides, t, widgetDetail, widgetLabel, widgetValue } from "./i18n.js?v=20260817sector1";
import { ensureLeafletLoaded, mountGeofenceMapWhenReady, refreshGeofenceMap, searchGeofencePlace, useGeofenceCurrentLocation } from "./geofence-map.js";
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
  if (WP?.isAuthUnusable?.()) {
    return false;
  }
  document.documentElement.classList.add("embed-document");
  document.body.classList.add("embed-mode", "admin-v2-embed");
  const parentToken = WP?.hasActiveSupportTabScope?.()
    ? String(WP.readSessionToken?.() || "").trim()
    : (wpGet(CONTROL_TOKEN_KEY) || "").trim();
  if (!parentToken) {
    return false;
  }
  try {
    const res = await fetch(`${apiBase()}/api/v2/auth/session`, {
      headers: { Authorization: `Bearer ${parentToken}`, Accept: "application/json" },
      cache: "no-store",
    });
    if (!res.ok) {
      if (res.status === 401 || res.status === 403) {
        const quiet = WP?.isSupportAssistQuietMode?.() || WP?.hasActiveSupportTabScope?.();
        tryEmbedSessionFromControlPass._cooldownUntil = Date.now() + (quiet ? 2500 : 60000);
      } else if (res.status >= 500) {
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
  const source = String(params.get("source") || "").trim().toLowerCase();
  if (source && ["security", "attendance", "chat", "leave", "document", "system"].includes(source)) {
    inboxSourceFilter = source;
  }
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
  if (item.openLohn) {
    await openLohnSystem();
    return;
  }
  if (item.tab === "enterprise" && requestEnterpriseHubInShell()) {
    return;
  }
  if (item.legacyView) {
    openLegacyDashboard(item.legacyView);
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
    if (item.href.includes("/index.html")) {
      openLegacyDashboard("auto");
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
  if (isEmbedMode()) {
    showEmbedAuthRequired(message || t("login.embedRequired"));
    return;
  }
  wpRemove(TOKEN_KEY);
  wpRemove(USER_KEY);
  showLogin();
  const errEl = $("loginError");
  if (errEl && message) {
    errEl.textContent = message;
    errEl.classList.remove("hidden");
  }
}

async function probeSessionToken(token) {
  if (!token) return false;
  if (window.WorkPassStorage?.isAuthUnusable?.()) return false;
  if (isSupportReadOnlySession() && probeSessionToken._ok) return true;
  if (isSupportSpectatorEmbed()) return Boolean(token);
  if (probeSessionToken._cooldownUntil && Date.now() < probeSessionToken._cooldownUntil) {
    return Boolean(probeSessionToken._lastOk);
  }
  try {
    const res = await fetch(`${apiBase()}/api/v2/auth/session`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      credentials: "include",
      cache: "no-store",
    });
    if (res.ok) {
      probeSessionToken._ok = true;
      probeSessionToken._lastOk = true;
      probeSessionToken._cooldownUntil = 0;
      return true;
    }
    if (res.status === 401 || res.status === 403) {
      // Support login rotates tokens — keep cooldown short so embeds recover quickly.
      const quiet = window.WorkPassStorage?.isSupportAssistQuietMode?.()
        || window.WorkPassStorage?.hasActiveSupportTabScope?.();
      probeSessionToken._cooldownUntil = Date.now() + (quiet ? 2500 : 60000);
      probeSessionToken._lastOk = false;
    }
    return false;
  } catch {
    return false;
  }
}

async function adoptControlPassTokenIfValid() {
  if (WP?.hasActiveSupportTabScope?.()) return false;
  const controlToken = (wpGet(CONTROL_TOKEN_KEY) || "").trim();
  if (!controlToken) return false;
  if (!(await probeSessionToken(controlToken))) return false;
  wpSet(TOKEN_KEY, controlToken);
  return true;
}

function notifyTabError(err) {
  if (isAuthError(err)) return;
  showActionToast(humanizeUserError(err), true);
}

function humanizeUserError(err) {
  if (err == null) return t("common.error");
  const data = err?.data && typeof err.data === "object" ? err.data : {};
  const code = String(data.error || data.code || err?.code || "")
    .trim()
    .toLowerCase();
  const msgCandidate =
    typeof err?.message === "string"
      ? err.message
      : typeof err === "string"
        ? err
        : typeof data.message === "string"
          ? data.message
          : typeof data.error === "string"
            ? data.error
            : "";
  const raw = String(msgCandidate || "").trim();
  const rawLower = raw.toLowerCase();
  const status = Number(err?.status || data.status || 0) || 0;

  const known = {
    export_failed: "error.exportFailed",
    login_failed: "error.loginFailed",
    invalid_json: "error.serverUnexpected",
    network_error: "error.network",
    failed_to_fetch: "error.network",
    timeout: "error.timeout",
    company_required: "common.selectCompany",
    company_id_required: "common.selectCompany",
    forbidden: "error.forbidden",
    forbidden_company: "error.forbidden",
    not_found: "error.notFound",
    unauthorized: "login.sessionExpired",
    invalid_session: "login.sessionExpired",
    session_expired: "login.sessionExpired",
    openai_quota_exceeded: "error.aiUnavailable",
    feature_not_available: "error.featureUnavailable",
    database_not_ready: "error.dbNotReady",
    missing_fields: "error.missingFields",
    feature_not_available: "error.featureUnavailable",
    push_failed: "inbox.pushNotDelivered",
    push_not_delivered: "inbox.pushNotDelivered",
    worker_not_found: "error.notFound",
    worker_id_and_body_required: "error.missingFields",
  };
  if (code && known[code]) {
    const label = t(known[code]);
    if (label && label !== known[code]) return label;
  }
  for (const [needle, key] of Object.entries(known)) {
    if (rawLower === needle || rawLower.includes(needle)) {
      const label = t(key);
      if (label && label !== key) return label;
    }
  }
  if (/api nicht erreichbar|unerwartete server-antwort|invalid_json/i.test(raw)) {
    return t("error.serverUnexpected");
  }
  if (status === 404 || status === 405) return t("error.notFound");
  if (status === 403) return t("error.forbidden");
  if (status === 401) return t("login.sessionExpired");
  if (status >= 500) return t("error.serverUnexpected");
  // Hide snake_case / http_### codes from end users
  if (/^[a-z][a-z0-9_.-]*$/i.test(raw) || /^http_\d{3}$/i.test(raw)) {
    return t("common.error");
  }
  if (raw === "[object Object]") return t("common.error");
  if (raw.length > 180) return `${raw.slice(0, 160)}…`;
  return raw || t("common.error");
}

function summarizeIntegrationResult(res) {
  if (!res || typeof res !== "object") return t("common.done");
  if (res.ok === false) return humanizeUserError({ message: res.message || res.error, data: res });
  const synced = res.synced ?? res.imported ?? res.updated ?? res.count;
  const skipped = res.skipped ?? res.skippedCount;
  const parts = [];
  if (synced != null) parts.push(t("tools.resultSynced", { n: synced }));
  if (skipped != null) parts.push(t("tools.resultSkipped", { n: skipped }));
  if (res.dryRun) parts.push(t("tools.resultDryRun"));
  if (parts.length) return parts.join(" · ");
  if (res.message && !/^[a-z][a-z0-9_.-]*$/i.test(String(res.message))) return String(res.message);
  return t("common.done");
}

async function applyTenantBrandingFromApi() {
  if (isSupportReadOnlySession()) {
    await loadSectorTerminologyForAdmin();
    return;
  }
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
  if (isSupportReadOnlySession()) {
    setSectorTermOverrides({});
    window.__adminV2Sector = "construction";
    window.__adminV2SectorLabel = "";
    window.__adminV2SectorTerms = {};
    document.body.dataset.operatingSector = "construction";
    $("sectorChip")?.classList.add("hidden");
    applyI18n();
    return;
  }
  const cid = resolveAdminCompanyId();
  const lang = getLang();
  try {
    let url = `/api/platform/sector-config?lang=${encodeURIComponent(lang)}`;
    if (cid) url += `&company_id=${encodeURIComponent(cid)}`;
    const data = await api(url);
    setSectorTermOverrides(data?.terms || {});
    window.__adminV2Sector = data?.sector || "construction";
    window.__adminV2SectorLabel = data?.label || "";
    window.__adminV2SectorTerms = data?.terms || {};
    document.body.dataset.operatingSector = data?.sector || "construction";
    const chip = $("sectorChip");
    if (chip) {
      const label = String(data?.label || "").trim();
      const banner = String(data?.terms?.sectorBanner || "").trim();
      if (label) {
        chip.textContent = label;
        chip.title = banner || label;
        chip.classList.remove("hidden");
      } else {
        chip.classList.add("hidden");
      }
    }
    applyI18n();
  } catch {
    setSectorTermOverrides({});
    $("sectorChip")?.classList.add("hidden");
  }
}

function applyParentCompanyId(companyId) {
  const cid = String(companyId || "").trim();
  if (!cid) return;
  const prev = String(wpGet(COMPANY_KEY) || "").trim();
  wpSet(COMPANY_KEY, cid);
  const select = $("companyPicker");
  if (select && select.options.length) {
    const has = Array.from(select.options).some((o) => o.value === cid);
    if (has) select.value = cid;
  }
  if (prev === cid) return;
  if (isSupportReadOnlySession() || window.WorkPassStorage?.isSupportAssistQuietMode?.()) {
    void loadSectorTerminologyForAdmin();
    return;
  }
  void applyTenantBrandingFromApi();
  void loadSectorTerminologyForAdmin();
}

function replyEmbedTokenRequest(event) {
  // Prefer tab-scoped support token; never forward a stale control-pass Bearer into nested embeds.
  const tok = String(WP?.readSessionToken?.() || wpGet(TOKEN_KEY) || "").trim();
  if (tok) {
    try {
      event.source?.postMessage(
        {
          type: "baupass-sync-token",
          token: tok,
          companyId: activeCompanyId() || "",
          lang: getLang(),
          user: getUser(),
        },
        window.location.origin,
      );
    } catch {
      // iframe not ready
    }
    const opsFrame = document.querySelector("#opsEmbedFrame");
    if (opsFrame) {
      syncTokenToOpsEmbedFrame(opsFrame, activeCompanyId());
    }
    return true;
  }
  if (window.parent && window.parent !== window) {
    try {
      window.parent.postMessage({ type: "baupass-request-token" }, window.location.origin);
    } catch {
      // ignore
    }
  }
  return false;
}

window.addEventListener("message", (event) => {
  if (!event?.data || event.origin !== window.location.origin) return;
  if (event.data.type === "baupass-request-token") {
    replyEmbedTokenRequest(event);
    return;
  }
  if (event.data.type === "baupass-open-command-palette") {
    if (!$("dashboardView")?.classList.contains("hidden")) {
      applyParentCompanyId(event.data.companyId);
      openCommandPalette();
    }
    return;
  }
  if (event.data.type === "baupass-open-lohn") {
    applyParentCompanyId(event.data.companyId);
    openLohnSystem().catch(() => {});
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
    if (lang && lang !== getLang()) {
      setLang(lang);
      document.querySelectorAll("[data-lang-select]").forEach((sel) => {
        if (sel.value !== lang) sel.value = lang;
      });
    }
    return;
  }
  if (event.data.type === "baupass-support-mirror-tab") {
    if (event.data.companyId) {
      applyParentCompanyId(event.data.companyId);
    }
    const tab = String(event.data.tab || "").trim();
    const opsPage = String(event.data.opsEmbedPage || "").trim();
    if (opsPage) {
      pendingOpsEmbedPage = opsPage;
    }
    if (tab && document.querySelector(`.tab[data-tab="${tab}"]`)) {
      switchToTab(tab, { silent: true });
      if (!shouldSkipSupportBackgroundLoads()) {
        refreshActiveTab().catch(notifyTabError);
      }
      return;
    }
    if (opsPage) {
      const activeTab = document.querySelector(".tab.active")?.dataset?.tab || "";
      if (activeTab === "operations") {
        if (!shouldSkipSupportBackgroundLoads()) {
          refreshActiveTab().catch(notifyTabError);
        }
      } else if (document.querySelector(`.tab[data-tab="operations"]`)) {
        switchToTab("operations", { silent: true });
        if (!shouldSkipSupportBackgroundLoads()) {
          refreshActiveTab().catch(notifyTabError);
        }
      }
    }
    return;
  }
  if (event.data.type === "baupass-navigate") {
    const handled = handleHubNavigateFromEmbed(event.data);
    if (!handled && window.self !== window.top) {
      try {
        window.parent.postMessage(event.data, window.location.origin);
      } catch {
        // ignore
      }
    }
    return;
  }
  if (event.data.type !== "baupass-sync-token") return;
  const langFromParent = String(event.data.lang || "").trim().slice(0, 2);
  if (langFromParent && langFromParent !== getLang()) {
    setLang(langFromParent);
    document.querySelectorAll("[data-lang-select]").forEach((sel) => {
      if (sel.value !== langFromParent) sel.value = langFromParent;
    });
  }
  const token = String(event.data.token || "").trim();
  if (!token) return;
  const userFromParent = event.data.user;
  if (userFromParent && typeof userFromParent === "object" && userFromParent.id) {
    wpSet(USER_KEY, JSON.stringify(userFromParent));
  }
  const prevToken = String(WP?.readSessionToken?.() || wpGet(TOKEN_KEY) || "").trim();
  const nextCid = String(event.data.companyId || "").trim();
  const prevCid = String(activeCompanyId() || "").trim();
  const tokenChanged = token !== prevToken;
  const companyChanged = Boolean(nextCid) && nextCid !== prevCid;
  WP?.clearAuthUnusable?.();
  WP?.purgeSharedLocalSessionTokens?.();
  probeSessionToken._ok = true;
  probeSessionToken._lastOk = true;
  probeSessionToken._cooldownUntil = 0;
  tryEmbedSessionFromControlPass._cooldownUntil = 0;
  if (WP?.persistSessionToken) {
    WP.persistSessionToken(token);
  }
  wpSet(TOKEN_KEY, token);
  wpSet(CONTROL_TOKEN_KEY, token);
  if (nextCid) {
    applyParentCompanyId(nextCid);
  }
  const opsFrame = document.querySelector("#opsEmbedFrame");
  if (opsFrame) {
    syncTokenToOpsEmbedFrame(opsFrame, nextCid || activeCompanyId());
  }
  if ($("dashboardView")?.classList.contains("hidden")) {
    showSessionBoot();
    bootSession().catch(() => {});
    return;
  }
  // Parent re-posts the same session often — do not remount Platform/Ops forms every time.
  if (!tokenChanged && !companyChanged) return;
  const activeTab = document.querySelector(".tab.active")?.dataset?.tab;
  if (!activeTab) return;
  clearTimeout(window.__adminSyncTokenRefreshT);
  window.__adminSyncTokenRefreshT = setTimeout(() => {
    refreshActiveTab().catch(() => {});
  }, 400);
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
  if (data?.url && typeof data.url === "string") {
    try {
      const u = new URL(data.url, window.location.origin);
      const tabFromUrl = String(u.searchParams.get("tab") || (u.hash || "").replace(/^#/, "") || "").trim();
      if (tabFromUrl && document.querySelector(`.tab[data-tab="${tabFromUrl}"]`)) {
        if (u.searchParams.get("einsatzplan") === "1" || data?.focusEinsatzplan) {
          pendingEinsatzplanFocus = true;
        }
        switchToTab(tabFromUrl);
        if (pendingEinsatzplanFocus) tryFocusEinsatzplanFromParent();
        return true;
      }
      const path = u.pathname.toLowerCase();
      if (path.includes("ai-command-center")) {
        navigateToOpsEmbed("/ai-command-center.html");
        return true;
      }
      if (path.includes("ops-command-center") || path.includes("ops-live-map")) {
        navigateToOpsEmbed(u.pathname + u.search);
        return true;
      }
    } catch {
      // ignore bad urls
    }
  }
  if (view === "deployment-plan" || data?.focusEinsatzplan || (view === "admin-v2" && data?.focusEinsatzplan)) {
    pendingEinsatzplanFocus = true;
    switchToTab("workers");
    tryFocusEinsatzplanFromParent();
    return true;
  }
  if (view === "ops-center") {
    if (postShellNavigate({ view: "ops-center", companyId: data?.companyId || activeCompanyId() })) {
      return true;
    }
    navigateToOpsEmbed("/ops-command-center.html");
    return true;
  }
  if (view === "ai-assistant") {
    if (postShellNavigate({ view: "ai-assistant", companyId: data?.companyId || activeCompanyId() })) {
      return true;
    }
    navigateToOpsEmbed("/ai-command-center.html");
    return true;
  }
  if (view === "enterprise-hub") {
    if (requestEnterpriseHubInShell()) {
      return true;
    }
  }
  const tabByView = {
    dashboard: "overview",
    overview: "overview",
    workers: "workers",
    access: "access",
    documents: "inbox",
    inbox: "inbox",
    operations: "operations",
    copilot: "copilot",
    "ai-assistant": "copilot",
    "enterprise-hub": "enterprise",
    enterprise: "enterprise",
    "admin-v2": "workers",
  };
  const tab = tabByView[view];
  if (tab && document.querySelector(`.tab[data-tab="${tab}"]`)) {
    switchToTab(tab);
    return true;
  }
  if (data?.url && typeof data.url === "string" && window.self === window.top) {
    try {
      window.location.href = data.url;
      return true;
    } catch {
      // ignore
    }
  }
  return false;
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

function isSupportReadOnlySession() {
  try {
    // Only the support agent's read-only session. Customer's spectator tab must keep
    // full read access so mirrored Betrieb/KI/Hub show the same details.
    return Boolean(getUser()?.support_read_only);
  } catch {
    return false;
  }
}

function isSupportSpectatorEmbed() {
  if (!isEmbedMode()) return false;
  try {
    if (global.document?.body?.classList?.contains("support-assist-spectator-active")) return true;
    const watchRaw = global.sessionStorage?.getItem("baupass-support-assist-watch");
    const watch = watchRaw ? JSON.parse(watchRaw) : null;
    return Boolean(watch?.watchToken && watch?.companyId && !watch?.agent);
  } catch {
    return false;
  }
}

function shouldSkipSupportBackgroundLoads() {
  if (window.WorkPassStorage?.isAuthUnusable?.()) return true;
  const tok = String(WP?.readSessionToken?.() || wpGet(TOKEN_KEY) || "").trim();
  // Spectator embeds keep the customer's session — allow data loads so mirrored Betrieb
  // shows the same details as the support agent. Only skip when auth is missing.
  if (!tok && (window.WorkPassStorage?.hasActiveSupportTabScope?.() || window.WorkPassStorage?.isSupportAssistQuietMode?.())) {
    return true;
  }
  return false;
}

function isSuperadminUser() {
  return String(getUser()?.role || "").toLowerCase() === "superadmin";
}

function isOfficeUser() {
  return String(getUser()?.role || "").toLowerCase() === "office";
}

function canAccessOwnerFinance() {
  const role = String(getUser()?.role || "").toLowerCase();
  return role === "superadmin" || role === "company-admin";
}

function canAccessWorkpassLohnUi() {
  // Owner-only: office operators must not see Lohn button, drawer, or accounting toasts.
  return canAccessOwnerFinance();
}

/** Legacy SUPPIX dashboard (index.html) — invoices, devices, platform settings. */
function resolveLegacyDashboardView(preset) {
  const requested = String(preset || "").trim().toLowerCase();
  if (requested && requested !== "auto") {
    return requested;
  }
  const role = String(getUser()?.role || "").toLowerCase();
  if (role === "superadmin") {
    return "admin";
  }
  if (role === "company-admin") {
    return "invoices";
  }
  if (role === "office") {
    return "workers";
  }
  return "dashboard";
}

function buildLegacyDashboardUrl(view = "auto") {
  const targetView = resolveLegacyDashboardView(view);
  const params = new URLSearchParams();
  params.set("view", targetView);
  const cid = activeCompanyId();
  if (cid) {
    params.set("company_id", cid);
  }
  return `/index.html?${params.toString()}#${targetView}`;
}

function openLegacyDashboard(view = "auto") {
  const targetView = resolveLegacyDashboardView(view);
  if (isEmbedMode() && window.parent && window.parent !== window) {
    try {
      window.parent.postMessage(
        {
          type: "baupass-navigate",
          view: targetView,
          companyId: activeCompanyId() || undefined,
        },
        window.location.origin,
      );
      return;
    } catch {
      // fall through to top navigation
    }
  }
  const url = buildLegacyDashboardUrl(view);
  const topWin = window.top && window.top !== window ? window.top : window;
  topWin.location.href = url;
}

function bindLegacyDashboardLinks(root = document) {
  root.querySelectorAll("[data-legacy-dashboard]").forEach((el) => {
    if (el.dataset.legacyBound === "1") {
      return;
    }
    el.dataset.legacyBound = "1";
    el.addEventListener("click", (event) => {
      event.preventDefault();
      openLegacyDashboard(el.getAttribute("data-legacy-dashboard") || "auto");
    });
  });
}

function canAccessAnalyticsTab() {
  return isSuperadminUser();
}

function applyRoleNavigation() {
  const showAnalytics = canAccessAnalyticsTab();
  const showPlatform = isSuperadminUser();
  const showLegacy = isSuperadminUser();
  const showOwnerFinance = canAccessOwnerFinance();
  document.querySelectorAll('.tab[data-tab="analytics"]').forEach((el) => {
    el.classList.toggle("hidden", !showAnalytics);
  });
  document.querySelectorAll('.tab[data-tab="platform"]').forEach((el) => {
    el.classList.toggle("hidden", !showPlatform);
  });
  document.querySelectorAll('.tab[data-tab="billing"], .tab[data-tab="audit"]').forEach((el) => {
    el.classList.toggle("hidden", !showOwnerFinance);
  });
  document.querySelectorAll(".nav-item-lohn, #openLohnSystemBtn").forEach((el) => {
    if (!canAccessWorkpassLohnUi()) {
      el.classList.add("hidden");
      if ("hidden" in el) el.hidden = true;
    }
    // Visibility for enabled companies is owned by syncLohnOpenButton() — do not
    // hide here based on finance tabs (that caused the Buchhaltung button flicker).
  });
  document.querySelectorAll("#opsStripLohnLink, .ops-strip-lohn-btn").forEach((el) => {
    el.classList.toggle("hidden", !canAccessWorkpassLohnUi());
  });
  if (!canAccessWorkpassLohnUi()) {
    try {
      closeLohnDrawer();
    } catch {
      /* drawer helpers may not be ready yet */
    }
    updateLohnNavBadge(0);
  }
  document.querySelectorAll(".legacy-dashboard-link, .sidebar-legacy-link").forEach((el) => {
    el.classList.toggle("hidden", !showLegacy);
  });
  $("enterpriseAnalyticsShortcut")?.classList.toggle("hidden", !showAnalytics);
  if (!showAnalytics && document.querySelector('.tab.active[data-tab="analytics"]')) {
    switchToTab("overview");
  }
  if (!showPlatform && document.querySelector('.tab.active[data-tab="platform"]')) {
    switchToTab("overview");
  }
  if (!showOwnerFinance && document.querySelector('.tab.active[data-tab="billing"], .tab.active[data-tab="audit"]')) {
    switchToTab("overview");
  }
}

function companyQuery() {
  const cid = String(activeCompanyId() || "").trim();
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
  const token = String(WP?.readSessionToken?.() || wpGet(TOKEN_KEY) || "").trim();
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
  const fetchOpts = { ...options, headers, credentials: "include", cache: "no-store" };
  const res = await (window.BaupassGuardian?.fetchWithGuardianRetry
    ? window.BaupassGuardian.fetchWithGuardianRetry(`${apiBase()}${path}`, fetchOpts)
    : fetch(`${apiBase()}${path}`, fetchOpts));
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = {
      error: "invalid_json",
      message: t("error.serverUnexpected"),
    };
  }
  if (!res.ok) {
    const code = String(data.error || "").toLowerCase();
    if (
      res.status === 401 &&
      ["invalid_session", "session_expired", "unauthorized"].includes(code)
    ) {
      if (isSupportReadOnlySession() || window.WorkPassStorage?.isSupportAssistQuietMode?.()) {
        const err = new Error(t("login.sessionExpired"));
        err.status = 401;
        err.auth = true;
        err.data = data;
        throw err;
      }
      clearSessionAndShowLogin(t("login.sessionExpired"));
      const err = new Error(t("login.sessionExpired"));
      err.status = 401;
      err.auth = true;
      err.data = data;
      throw err;
    }
    const err = new Error(
      humanizeUserError({
        message: data.message || data.error || res.statusText,
        status: res.status,
        data,
      }),
    );
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

/** Soft API call: never block the UI longer than timeoutMs (slow SQLite / cold endpoints). */
function withTimeout(promise, timeoutMs, fallback) {
  let timer;
  const timed = new Promise((resolve) => {
    timer = setTimeout(() => resolve(fallback), Math.max(500, Number(timeoutMs) || 8000));
  });
  return Promise.race([
    Promise.resolve(promise).finally(() => clearTimeout(timer)),
    timed,
  ]);
}

function apiSoft(path, fallback = null, timeoutMs = 8000, options = {}) {
  return withTimeout(api(path, options).catch(() => fallback), timeoutMs, fallback);
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
  try {
    window.dispatchEvent(new CustomEvent("baupass-ai-operator-hide"));
    window.BaupassAiOperator?.hide?.();
  } catch {
    /* optional FAB */
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
  bindLegacyDashboardLinks();
  try {
    window.dispatchEvent(new CustomEvent("baupass-ai-operator-ready"));
    window.BaupassAiOperator?.show?.();
  } catch {
    /* optional FAB */
  }
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
  window.__baupassCompanies = rows;
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
  let text;
  if (isError) {
    if (message && typeof message === "object") {
      text = humanizeUserError(message);
    } else {
      text = humanizeUserError({ message: message == null ? "" : String(message) });
    }
  } else if (message && typeof message === "object") {
    text = humanizeUserError(message);
  } else {
    text = String(message ?? "");
  }
  if (!text || text === "[object Object]") text = t("common.error");
  if (!el) {
    // Never use blocking alert() — it stacks and re-triggers send clicks.
    console.warn("[toast]", isError ? "err" : "ok", text);
    return;
  }
  const baseClass = el.id === "globalToast" ? "global-toast" : "inbox-toast";
  el.textContent = text;
  el.className = isError ? `${baseClass} err` : `${baseClass} ok`;
  el.classList.remove("hidden");
  el.setAttribute("aria-live", isError ? "assertive" : "polite");
  // Clicks on the toast must not bubble into studio action handlers.
  if (!el.dataset.payslipToastBound) {
    el.dataset.payslipToastBound = "1";
    el.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      el.classList.add("hidden");
    });
  }
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
  return /inbox|security|leave|access|push|emergency|alert|document|site_checkin|site_leave|proximity|worker_app|check_in|check_out|app_login|app_logout|camera|iot|biometric|autopilot/i.test(
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

function formatAccessTimestamp(value) {
  const raw = String(value || "").trim();
  if (!raw) return "-";
  const hasOffset = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw);
  if (!hasOffset) {
    return raw.slice(0, 19).replace("T", " ");
  }
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) {
    return raw.slice(0, 19).replace("T", " ");
  }
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Europe/Berlin",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(parsed);
}

function paintInboxBadge(el, open, critical) {
  if (!el) return;
  const n = Number(open) || 0;
  const crit = Number(critical) || 0;
  if (n <= 0) {
    el.classList.add("hidden");
    el.classList.remove("critical");
    el.textContent = "";
    el.removeAttribute("title");
    return;
  }
  el.classList.remove("hidden");
  const wasCritical = el.classList.contains("critical");
  el.classList.toggle("critical", crit > 0);
  el.textContent = crit > 0 ? `${n}!` : String(n);
  el.title = t("inbox.badgeTooltip", { open: n, critical: crit });
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

function paintLohnBadge(el, count) {
  if (!el) return;
  const n = Number(count) || 0;
  if (n <= 0) {
    el.classList.add("hidden");
    el.textContent = "";
    el.removeAttribute("title");
    return;
  }
  el.classList.remove("hidden");
  el.textContent = String(n);
  el.title = t("lohn.badgeTooltip", { n });
}

function updateLohnNavBadge(count) {
  paintLohnBadge($("lohnOpsBadge"), count);
  paintLohnBadge($("lohnOpsMobileBadge"), count);
}

let lohnOpenEnabled = false;
const lohnEnabledByCompany = Object.create(null);
let lohnOpenSyncSeq = 0;

async function syncLohnOpenButton() {
  const btn = $("openLohnSystemBtn");
  const cid = activeCompanyId();
  const seq = ++lohnOpenSyncSeq;
  if (!cid || !canAccessWorkpassLohnUi()) {
    lohnOpenEnabled = false;
    if (btn) {
      btn.hidden = true;
      btn.classList.add("hidden");
    }
    return;
  }
  // Keep last known good state while a slow/failed poll is in flight.
  if (lohnEnabledByCompany[cid] === true && btn) {
    lohnOpenEnabled = true;
    btn.hidden = false;
    btn.classList.remove("hidden");
  }
  try {
    const settings = await apiSoft(
      `/api/payroll/accounting/company-settings?company_id=${encodeURIComponent(cid)}`,
      null,
      4000,
    );
    if (seq !== lohnOpenSyncSeq || activeCompanyId() !== cid) return;
    if (!settings || typeof settings !== "object") {
      // Timeout / network — do not flip an enabled button off.
      const cached = lohnEnabledByCompany[cid];
      if (cached != null && btn) {
        lohnOpenEnabled = !!cached;
        btn.hidden = !cached;
        btn.classList.toggle("hidden", !cached);
      }
      return;
    }
    lohnOpenEnabled = !!settings.workpassLohnEnabled;
    lohnEnabledByCompany[cid] = lohnOpenEnabled;
    if (btn) {
      btn.hidden = !lohnOpenEnabled;
      btn.classList.toggle("hidden", !lohnOpenEnabled);
    }
  } catch {
    if (seq !== lohnOpenSyncSeq || activeCompanyId() !== cid) return;
    const cached = lohnEnabledByCompany[cid];
    if (cached != null) {
      lohnOpenEnabled = !!cached;
      if (btn) {
        btn.hidden = !cached;
        btn.classList.toggle("hidden", !cached);
      }
      return;
    }
    lohnOpenEnabled = false;
    if (btn) {
      btn.hidden = true;
      btn.classList.add("hidden");
    }
  }
}

async function openLohnSystem() {
  if (!canAccessWorkpassLohnUi()) {
    showActionToast(t("common.forbidden") || "Keine Berechtigung", true);
    return;
  }
  const cid = activeCompanyId();
  if (!cid) {
    showActionToast(t("common.selectCompany") || "Bitte Firma wählen", true);
    return;
  }
  try {
    const res = await api(`/api/payroll/accounting/launch?company_id=${encodeURIComponent(cid)}`);
    if (!res?.ok || !res.url) {
      showActionToast(res?.message || t("lohn.openFailed") || "Buchhaltung nicht erreichbar", true);
      return;
    }
    const url = String(res.url);
    // Prefer a new tab so a brief platform restart (railway up) cannot
    // wipe the admin UI with "Verbindung abgelehnt".
    // Do NOT pass "noopener" — Chromium drops hash fragments used by SSO.
    const win = window.open(url, "_blank");
    if (!win) {
      window.location.assign(url);
      return;
    }
    if (res.sso || res.mode === "sso_bridge" || url.includes("sso-enter")) {
      showActionToast(t("lohn.ssoOpening") || "Buchhaltung — SSO-Anmeldung…");
    }
  } catch (e) {
    showActionToast(e?.message || t("lohn.openFailed") || "Buchhaltung nicht erreichbar", true);
  }
}

async function refreshLohnBadgeOnly() {
  if (!canAccessWorkpassLohnUi()) {
    updateLohnNavBadge(0);
    paintLohnBadge($("opsStripLohnBadge"), 0);
    void syncLohnOpenButton();
    return;
  }
  if (shouldSkipSupportBackgroundLoads()) {
    updateLohnNavBadge(0);
    paintLohnBadge($("opsStripLohnBadge"), 0);
    void syncLohnOpenButton();
    return;
  }
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    updateLohnNavBadge(0);
    void syncLohnOpenButton();
    return;
  }
  try {
    // sync=0: badge poll must not pull Lohn on every tick (that caused UI thrash).
    const sep = q ? "&" : "?";
    const data = await api(`/api/payroll/accounting/messages/counts${q}${sep}sync=0`);
    updateLohnNavBadge(data.count ?? data.unread ?? 0);
  } catch {
    try {
      const sep = q ? "&" : "?";
      const data = await api(`/api/payroll/accounting/messages${q}${sep}sync=0`);
      updateLohnNavBadge(data.count ?? (data.messages || []).length);
    } catch {
      /* Lohn optional per company */
    }
  }
  void syncLohnOpenButton();
}

function broadcastLohnInboxChanged() {
  try {
    localStorage.setItem("workpass-lohn-inbox-bump", String(Date.now()));
  } catch {
    /* ignore */
  }
  try {
    window.dispatchEvent(new CustomEvent("workpass-lohn-inbox-changed"));
  } catch {
    /* ignore */
  }
}

function closeLohnDrawer() {
  $("lohnDrawer")?.classList.add("hidden");
  $("lohnDrawer")?.setAttribute("aria-hidden", "true");
  document.body.classList.remove("lohn-drawer-open");
}

const payslipStudioState = {
  batches: [],
  activeBatchId: "",
  activeStmtId: "",
  pdfObjectUrl: "",
  previewKind: "sheet",
  sheetHtml: "",
  sheetWindow: null,
  viewerBlobUrl: "",
  workersByCompany: {},
  inbox: "open",
  inboxSeq: 0,
  previewFitReady: false,
  previewObserver: null,
  archiveQuery: "",
  archiveStatus: "all",
  archivePeriod: "",
  releaseInFlight: false,
  downloadInFlight: false,
  captureCache: null,
  libsWarm: false,
  prepSeq: 0,
  capturePromise: null,
  syncPromise: null,
};

const PAYSLIP_A4_PX_W = 794;
const PAYSLIP_A4_PX_H = 1123;

function lockPayslipIframeChrome(iframe) {
  try {
    const doc = iframe?.contentDocument;
    if (!doc) return;
    const html = doc.documentElement;
    const body = doc.body;
    if (html) {
      html.style.overflow = "hidden";
      html.style.margin = "0";
      html.style.padding = "0";
    }
    if (body) {
      body.style.overflow = "hidden";
      body.style.margin = "0";
      body.style.padding = "0";
      body.style.minHeight = "0";
      body.style.height = "max-content";
      body.style.width = "max-content";
    }
    iframe.setAttribute("scrolling", "no");
  } catch {
    /* ignore */
  }
}

function resetPayslipInnerScale(doc) {
  try {
    const html = doc?.documentElement;
    const body = doc?.body;
    if (html) {
      html.style.zoom = "1";
      html.style.transform = "none";
    }
    if (body) {
      body.style.zoom = "1";
      body.style.transform = "none";
    }
    const sheet = doc?.querySelector?.("#datevSheetA4") || doc?.querySelector?.(".datev-sheet-a4");
    if (sheet) {
      sheet.style.zoom = "1";
      sheet.style.transform = "none";
    }
  } catch {
    /* ignore */
  }
}

function setPayslipPreviewKind(kind) {
  const next = kind === "pdf" ? "pdf" : "sheet";
  payslipStudioState.previewKind = next;
  const wrap = $("payslipStudioPdf")?.closest?.(".payslip-studio-pdf-wrap");
  wrap?.classList.toggle("is-pdf-doc", next === "pdf");
  wrap?.classList.toggle("is-sheet-doc", next !== "pdf");
}

function fitPayslipPreview() {
  const iframe = $("payslipStudioPdf");
  const stage = $("payslipSheetStage") || iframe?.closest?.(".payslip-sheet-stage");
  const wrap = iframe?.closest?.(".payslip-studio-pdf-wrap");
  if (!iframe || !stage || !wrap) return;
  const wrapW = wrap.clientWidth || 0;
  const wrapH = wrap.clientHeight || 0;
  if (wrapW < 40 || wrapH < 40) return;

  // Original Lohn PDFs (Vordienst, Steuer, …): fill the pane — do not A4-scale/clip the browser PDF viewer.
  if (payslipStudioState.previewKind === "pdf" || wrap.classList.contains("is-pdf-doc")) {
    stage.style.width = "100%";
    stage.style.height = "100%";
    stage.style.maxWidth = "100%";
    stage.style.maxHeight = "100%";
    stage.style.aspectRatio = "auto";
    stage.style.pointerEvents = "auto";
    iframe.style.position = "absolute";
    iframe.style.inset = "0";
    iframe.style.width = "100%";
    iframe.style.height = "100%";
    iframe.style.minHeight = "100%";
    iframe.style.maxHeight = "none";
    iframe.style.transform = "none";
    iframe.style.overflow = "auto";
    iframe.style.pointerEvents = "auto";
    iframe.style.background = "#fff";
    return;
  }

  lockPayslipIframeChrome(iframe);
  const pad = 8;
  const availW = Math.max(80, wrapW - pad);
  const availH = Math.max(80, wrapH - pad);
  const boxScale = Math.min(availW / PAYSLIP_A4_PX_W, availH / PAYSLIP_A4_PX_H);
  const stageW = Math.max(1, Math.floor(PAYSLIP_A4_PX_W * boxScale));
  const stageH = Math.max(1, Math.floor(PAYSLIP_A4_PX_H * boxScale));
  stage.style.width = `${stageW}px`;
  stage.style.height = `${stageH}px`;
  stage.style.aspectRatio = "auto";
  iframe.style.width = `${stageW}px`;
  iframe.style.height = `${stageH}px`;
  iframe.style.minHeight = `${stageH}px`;
  iframe.style.maxHeight = `${stageH}px`;
  iframe.style.transform = "none";
  iframe.style.overflow = "hidden";
  iframe.style.pointerEvents = "none";
  try {
    const doc = iframe.contentDocument;
    if (!doc) return;
    resetPayslipInnerScale(doc);
    const sheet =
      doc.querySelector("#datevSheetA4") ||
      doc.querySelector(".datev-sheet-a4") ||
      doc.body;
    const nw = Math.max(1, sheet.offsetWidth || PAYSLIP_A4_PX_W);
    const nh = Math.max(1, sheet.offsetHeight || PAYSLIP_A4_PX_H);
    const inner = Math.min(stageW / nw, stageH / nh);
    sheet.style.transformOrigin = "top left";
    sheet.style.transform = `scale(${inner})`;
  } catch {
    /* iframe not ready */
  }
}

function schedulePayslipPreviewFit() {
  ensurePayslipPreviewFit();
  requestAnimationFrame(() => {
    fitPayslipPreview();
    requestAnimationFrame(fitPayslipPreview);
  });
}

function ensurePayslipPreviewFit() {
  if (payslipStudioState.previewFitReady) return;
  const wrap = $("payslipStudioPdf")?.closest?.(".payslip-studio-pdf-wrap");
  if (!wrap) return;
  payslipStudioState.previewFitReady = true;
  window.addEventListener("resize", fitPayslipPreview);
  if (typeof ResizeObserver !== "undefined") {
    payslipStudioState.previewObserver = new ResizeObserver(() => fitPayslipPreview());
    payslipStudioState.previewObserver.observe(wrap);
  }
}

function toast(message, kind = "ok") {
  const text = String(message || "").trim();
  if (!text) return;
  try {
    if (typeof showActionToast === "function") {
      showActionToast(text, kind === "error" || kind === "err");
      return;
    }
  } catch {
    /* fall through */
  }
  try {
    // Avoid stacking modal alerts during payslip retries.
    console.warn("[payslip]", kind, text);
  } catch {
    /* ignore */
  }
}

async function pullPayslipsFromLohn() {
  const cid = activeCompanyId();
  if (!cid) {
    showActionToast(t("common.selectCompany") || "Bitte Firma wählen", true);
    return;
  }
  try {
    showActionToast(t("lohn.pullPayslips") || "Abrechnungen werden geholt…");
    const res = await api(`/api/payroll/statements/pull-from-lohn`, {
      method: "POST",
      body: JSON.stringify({ companyId: cid, redeliver: true }),
    });
    if (!res?.ok) {
      showActionToast(res?.message || res?.error || t("lohn.pullPayslipsFailed") || "Abruf fehlgeschlagen", true);
      return;
    }
    const n = Number(res.createdCount || 0);
    if (n > 0) {
      showActionToast((t("lohn.pullPayslipsOk") || "Abrechnungen übernommen") + ` (${n})`);
      broadcastLohnInboxChanged();
      openPayslipReviewStudio().catch(() => {});
    } else {
      showActionToast(res.message || t("lohn.pullPayslipsEmpty") || "Keine neuen Abrechnungen");
    }
    refreshLohnBadgeOnly().catch(() => {});
  } catch (e) {
    showActionToast(e?.message || t("lohn.pullPayslipsFailed") || "Abruf fehlgeschlagen", true);
  }
}

function closePayslipReviewStudio() {
  const el = $("payslipReviewStudio");
  el?.classList.add("hidden");
  el?.classList.remove("is-sheet-focus");
  el?.setAttribute("aria-hidden", "true");
  document.body.classList.remove("payslip-studio-open", "payslip-sheet-focus");
  closePayslipSheetOverlay();
  try {
    if (document.fullscreenElement) {
      (document.exitFullscreen || document.webkitExitFullscreen)?.call(document);
    }
  } catch {
    /* ignore */
  }
  if (payslipStudioState.pdfObjectUrl) {
    try {
      URL.revokeObjectURL(payslipStudioState.pdfObjectUrl);
    } catch {
      /* ignore */
    }
    payslipStudioState.pdfObjectUrl = "";
  }
  revokePayslipViewerBlobUrl();
  const iframe = $("payslipStudioPdf");
  if (iframe) iframe.src = "about:blank";
}

function payslipStatusLabel(status) {
  const s = String(status || "").toLowerCase();
  if (s === "released") return t("lohn.statusReleased") || "Gesendet";
  if (s === "rejected") return t("lohn.statusRejected") || "Abgelehnt";
  if (s === "pending") return t("lohn.statusOpen") || "Offen";
  return s || "";
}

function isPayslipLocked(stmt) {
  const s = String(stmt?.status || "").toLowerCase();
  return s === "released" || s === "rejected" || Boolean(stmt?.deliveryLocked);
}

function payslipMatchLabel(status) {
  if (status === "unmatched") return t("lohn.matchUnmatched") || "Nicht zugeordnet";
  if (status === "ambiguous") return t("lohn.matchAmbiguous") || "Bitte prüfen";
  return t("lohn.matchMatched") || "Mitarbeiter erkannt";
}

function formatPayslipMoney(amount, currency) {
  const n = Number(amount);
  if (!Number.isFinite(n)) return "—";
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: currency || "EUR",
    }).format(n);
  } catch {
    return `${n.toFixed(2)} ${currency || "EUR"}`;
  }
}

function loadExternalScriptOnce(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-payslip-lib="${src}"]`);
    if (existing) {
      if (existing.dataset.ready === "1") return resolve();
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error(`script ${src}`)), { once: true });
      return;
    }
    const s = document.createElement("script");
    s.src = src;
    s.async = true;
    s.dataset.payslipLib = src;
    s.onload = () => {
      s.dataset.ready = "1";
      resolve();
    };
    s.onerror = () => reject(new Error(`script ${src}`));
    document.head.appendChild(s);
  });
}

async function ensurePayslipCaptureLibs() {
  const needCanvas = !window.html2canvas;
  const needPdf = !(window.jspdf?.jsPDF || window.jsPDF);
  if (needCanvas || needPdf) {
    const jobs = [];
    if (needCanvas) {
      jobs.push(
        loadExternalScriptOnce(
          "https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js",
        ),
      );
    }
    if (needPdf) {
      jobs.push(
        loadExternalScriptOnce(
          "https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js",
        ),
      );
    }
    await Promise.all(jobs);
  }
  if (!window.html2canvas) {
    throw new Error("html2canvas konnte nicht geladen werden (CSP)");
  }
  if (!(window.jspdf?.jsPDF || window.jsPDF)) {
    throw new Error("jsPDF konnte nicht geladen werden (CSP)");
  }
  payslipStudioState.libsWarm = true;
}

function warmPayslipCaptureLibs() {
  if (payslipStudioState.libsWarm && window.html2canvas && (window.jspdf?.jsPDF || window.jsPDF)) {
    return;
  }
  ensurePayslipCaptureLibs().catch(() => {});
}

function payslipCaptureCacheKey(batchId, statementId) {
  return `${batchId}::${statementId}::${String(payslipStudioState.sheetHtml || "").length}`;
}

function revokePayslipCaptureBlobUrl() {
  const url = payslipStudioState.captureCache?.blobUrl;
  if (!url) return;
  try {
    URL.revokeObjectURL(url);
  } catch {
    /* ignore */
  }
}

function invalidatePayslipCaptureCache() {
  payslipStudioState.prepSeq += 1;
  payslipStudioState.capturePromise = null;
  payslipStudioState.syncPromise = null;
  revokePayslipCaptureBlobUrl();
  payslipStudioState.captureCache = null;
}

function getFreshPayslipCapture(batchId, statementId) {
  const key = payslipCaptureCacheKey(batchId, statementId);
  const cached = payslipStudioState.captureCache;
  if (
    cached
    && cached.key === key
    && Date.now() - Number(cached.at || 0) < 180000
  ) {
    return cached;
  }
  return null;
}

async function waitForPayslipSheetReady({ timeoutMs = 8000 } = {}) {
  const iframe0 = $("payslipStudioPdf");
  const doc0 = iframe0?.contentDocument || iframe0?.contentWindow?.document;
  const sheet0 =
    doc0?.querySelector?.(".datev-sheet-a4")
    || doc0?.querySelector?.("#datevSheetA4")
    || doc0?.querySelector?.("[class*='datev-sheet']");
  if (sheet0 && String(payslipStudioState.sheetHtml || "").length > 200) {
    return { iframe: iframe0, doc: doc0, sheet: sheet0 };
  }
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const iframe = $("payslipStudioPdf");
    const doc = iframe?.contentDocument || iframe?.contentWindow?.document;
    const sheet =
      doc?.querySelector?.(".datev-sheet-a4")
      || doc?.querySelector?.("#datevSheetA4")
      || doc?.querySelector?.("[class*='datev-sheet']");
    if (sheet && String(payslipStudioState.sheetHtml || "").length > 200) {
      return { iframe, doc, sheet };
    }
    await new Promise((r) => setTimeout(r, 50));
  }
  throw new Error(t("lohn.sheetNotReady") || "Abrechnung noch nicht geladen — kurz warten und erneut versuchen");
}

async function capturePayslipSheetLikeLohn() {
  await ensurePayslipCaptureLibs();
  const { sheet } = await waitForPayslipSheetReady();
  if (!window.html2canvas) {
    throw new Error("PDF nicht verfügbar");
  }
  const JsPDF = window.jspdf?.jsPDF || window.jsPDF;
  if (!JsPDF) throw new Error("PDF-Bibliothek fehlt");

  const A4_W = 794;
  const A4_H = 1123;
  const prev = {
    transform: sheet.style.transform,
    origin: sheet.style.transformOrigin,
    width: sheet.style.width,
    height: sheet.style.height,
    minHeight: sheet.style.minHeight,
    maxHeight: sheet.style.maxHeight,
  };
  // Capture at true A4 CSS pixels — preview scale would otherwise squash the sheet.
  sheet.style.transform = "none";
  sheet.style.transformOrigin = "top left";
  sheet.style.width = `${A4_W}px`;
  sheet.style.height = `${A4_H}px`;
  sheet.style.minHeight = `${A4_H}px`;
  sheet.style.maxHeight = "none";
  try {
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    const canvas = await window.html2canvas(sheet, {
      // 1.35 + JPEG keeps text sharp enough and is much faster than PNG@2x.
      scale: 1.35,
      useCORS: true,
      allowTaint: true,
      backgroundColor: "#ffffff",
      logging: false,
      width: A4_W,
      height: A4_H,
      windowWidth: A4_W,
      windowHeight: A4_H,
      scrollX: 0,
      scrollY: 0,
      onclone: (_doc, cloned) => {
        const root = cloned?.querySelector?.(".datev-sheet-a4") || cloned;
        if (!root) return;
        root.style.transform = "none";
        root.style.width = `${A4_W}px`;
        root.style.height = `${A4_H}px`;
        root.style.minHeight = `${A4_H}px`;
        // html2canvas often drops CSS gradients → blue Auszahlungsbetrag becomes white.
        root.querySelectorAll?.(".ds-pay").forEach((el) => {
          el.style.setProperty("background", "#152a45", "important");
          el.style.setProperty("background-image", "none", "important");
          el.style.setProperty("background-color", "#152a45", "important");
          el.style.setProperty("color", "#ffffff", "important");
          el.style.setProperty("-webkit-print-color-adjust", "exact", "important");
          el.style.setProperty("print-color-adjust", "exact", "important");
        });
        root.querySelectorAll?.(".ds-pay span, .ds-pay strong").forEach((el) => {
          el.style.setProperty("color", "#ffffff", "important");
          el.style.setProperty("opacity", "1", "important");
        });
        const style = _doc.createElement("style");
        style.textContent = `
          .ds-pay {
            background: #152a45 !important;
            background-image: none !important;
            color: #fff !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }
          .ds-pay span, .ds-pay strong { color: #fff !important; opacity: 1 !important; }
        `;
        (_doc.head || _doc.documentElement)?.appendChild(style);
      },
    });
    const pdf = new JsPDF({ orientation: "portrait", unit: "mm", format: "a4", compress: true });
    const img = canvas.toDataURL("image/jpeg", 0.92);
    pdf.addImage(img, "JPEG", 0, 0, 210, 297, undefined, "FAST");
    const blob = pdf.output("blob");
    const pdfBase64 = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || "").split(",")[1] || "");
      reader.onerror = () => reject(new Error("PDF-Encode fehlgeschlagen"));
      reader.readAsDataURL(blob);
    });
    return { pdfBase64, blob };
  } finally {
    sheet.style.transform = prev.transform;
    sheet.style.transformOrigin = prev.origin;
    sheet.style.width = prev.width;
    sheet.style.height = prev.height;
    sheet.style.minHeight = prev.minHeight;
    sheet.style.maxHeight = prev.maxHeight;
    try {
      schedulePayslipPreviewFit?.();
    } catch {
      /* ignore */
    }
  }
}

async function uploadPayslipPdfBase64(batchId, statementId, pdfBase64) {
  return api(
    `/api/payroll/statements/${encodeURIComponent(batchId)}/${encodeURIComponent(statementId)}/pdf`,
    {
      method: "POST",
      body: JSON.stringify({
        pdfBase64,
        pdfSource: "lohn_html2canvas",
        repair: true,
      }),
    },
  );
}

async function ensurePayslipLocalPdf(batchId, statementId, { force = false } = {}) {
  const key = payslipCaptureCacheKey(batchId, statementId);
  const seq = payslipStudioState.prepSeq;
  const hit = getFreshPayslipCapture(batchId, statementId);
  if (!force && hit?.blobUrl && hit?.pdfBase64) return hit;

  if (
    !force
    && payslipStudioState.capturePromise
    && payslipStudioState.capturePromise.key === key
  ) {
    return payslipStudioState.capturePromise.promise;
  }

  const run = (async () => {
    const captured = await capturePayslipSheetLikeLohn();
    if (seq !== payslipStudioState.prepSeq) return null;
    if (!captured?.pdfBase64 || captured.pdfBase64.length < 100 || !captured.blob) {
      throw new Error("PDF-Erfassung fehlgeschlagen");
    }
    revokePayslipCaptureBlobUrl();
    const local = {
      key,
      at: Date.now(),
      synced: false,
      pdfBase64: captured.pdfBase64,
      blob: captured.blob,
      blobUrl: URL.createObjectURL(captured.blob),
    };
    payslipStudioState.captureCache = local;
    return local;
  })();

  payslipStudioState.capturePromise = { key, promise: run };
  try {
    return await run;
  } finally {
    if (payslipStudioState.capturePromise?.promise === run) {
      payslipStudioState.capturePromise = null;
    }
  }
}

async function ensurePayslipSyncedPdf(batchId, statementId, { force = false } = {}) {
  const key = payslipCaptureCacheKey(batchId, statementId);
  const seq = payslipStudioState.prepSeq;
  const local = await ensurePayslipLocalPdf(batchId, statementId, { force });
  if (!local) return { ok: false, cancelled: true };
  if (local.synced && !force) {
    return { ok: true, cached: true, pdfSource: "lohn_html2canvas", blobUrl: local.blobUrl, synced: true };
  }

  if (
    !force
    && payslipStudioState.syncPromise
    && payslipStudioState.syncPromise.key === key
  ) {
    return payslipStudioState.syncPromise.promise;
  }

  const run = (async () => {
    const res = await uploadPayslipPdfBase64(batchId, statementId, local.pdfBase64);
    if (seq !== payslipStudioState.prepSeq) return { ok: false, cancelled: true };
    if (!res?.ok) {
      throw new Error(res?.error || res?.message || "PDF-Upload fehlgeschlagen");
    }
    const cur = getFreshPayslipCapture(batchId, statementId) || local;
    cur.synced = true;
    cur.at = Date.now();
    payslipStudioState.captureCache = cur;
    return { ok: true, cached: false, pdfSource: "lohn_html2canvas", blobUrl: cur.blobUrl, synced: true };
  })();

  payslipStudioState.syncPromise = { key, promise: run };
  try {
    return await run;
  } finally {
    if (payslipStudioState.syncPromise?.promise === run) {
      payslipStudioState.syncPromise = null;
    }
  }
}

async function preparePayslipPdf(batchId, statementId, { force = false, needSync = true } = {}) {
  if (!needSync) {
    const local = await ensurePayslipLocalPdf(batchId, statementId, { force });
    if (!local) return { ok: false, cancelled: true };
    return {
      ok: true,
      cached: Boolean(local.synced),
      pdfSource: "lohn_html2canvas",
      blobUrl: local.blobUrl,
      synced: Boolean(local.synced),
    };
  }
  return ensurePayslipSyncedPdf(batchId, statementId, { force });
}

function schedulePayslipPdfPrep(batchId, statementId) {
  if (isSupportReadOnlySession()) return;
  if (!batchId || !statementId) return;
  const key = payslipCaptureCacheKey(batchId, statementId);
  const cached = getFreshPayslipCapture(batchId, statementId);
  if (cached?.blobUrl && cached.synced) return;
  if (payslipStudioState.syncPromise?.key === key) return;
  if (payslipStudioState.capturePromise?.key === key) return;
  // Capture + upload while the user reviews — clicks then feel instant.
  const kick = () => {
    preparePayslipPdf(batchId, statementId, { needSync: true }).catch(() => {});
  };
  if (typeof requestIdleCallback === "function") {
    requestIdleCallback(kick, { timeout: 400 });
  } else {
    setTimeout(kick, 60);
  }
}

async function fetchPayslipPdfBlobUrl(batchId, statementId) {
  if (!isSupportReadOnlySession()) {
    const ready = getFreshPayslipCapture(batchId, statementId);
    if (ready?.blobUrl) {
      if (!ready.synced) {
        ensurePayslipSyncedPdf(batchId, statementId).catch(() => {});
      }
      return ready.blobUrl;
    }
    const prepared = await preparePayslipPdf(batchId, statementId, { needSync: false });
    if (prepared?.blobUrl) {
      if (!prepared.synced) {
        ensurePayslipSyncedPdf(batchId, statementId).catch(() => {});
      }
      return prepared.blobUrl;
    }
    await preparePayslipPdf(batchId, statementId, { needSync: true });
  }
  const token = String(WP?.readSessionToken?.() || wpGet(TOKEN_KEY) || "").trim();
  const headers = { Accept: "application/pdf" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(
    `/api/payroll/statements/${encodeURIComponent(batchId)}/${encodeURIComponent(statementId)}/pdf`,
    { headers },
  );
  if (!res.ok) {
    let msg = `PDF ${res.status}`;
    try {
      const j = await res.json();
      msg = j.error || msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

async function syncPayslipStudioPdfFromHtml(batchId, statementId, { force = false } = {}) {
  if (isSupportReadOnlySession()) {
    return { ok: true, skipped: true };
  }
  // Exact studio capture only — never fall back to a remade Chromium/Weasy PDF.
  const res = await preparePayslipPdf(batchId, statementId, { force, needSync: true });
  if (res?.cancelled) {
    throw new Error(t("lohn.sheetNotReady") || "Abrechnung noch nicht geladen — kurz warten und erneut versuchen");
  }
  if (!res?.ok) {
    throw new Error("PDF-Erfassung fehlgeschlagen");
  }
  return res;
}

async function loadPayslipWorkers(companyId) {
  const cid = String(companyId || "").trim();
  if (!cid) return [];
  if (Array.isArray(payslipStudioState.workersByCompany[cid])) {
    return payslipStudioState.workersByCompany[cid];
  }
  const data = await apiSoft(
    `/api/payroll/accounting/employees?company_id=${encodeURIComponent(cid)}`,
    { employees: [] },
    8000,
  );
  const list = Array.isArray(data?.employees) ? data.employees : [];
  payslipStudioState.workersByCompany[cid] = list;
  return list;
}

function formatPayslipShortDate(iso) {
  const s = String(iso || "").slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return "";
  return `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}`;
}

function payslipArchiveHaystack(stmt) {
  return [
    stmt?.displayName,
    stmt?.badgeId,
    stmt?.workerId,
    stmt?.documentPeriod || stmt?.period,
    stmt?.status,
    formatPayslipMoney(stmt?.netAmount ?? stmt?.grossAmount, stmt?.currency),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function filterPayslipArchiveStatements(stmts) {
  const q = String(payslipStudioState.archiveQuery || "").trim().toLowerCase();
  const st = String(payslipStudioState.archiveStatus || "all");
  const period = String(payslipStudioState.archivePeriod || "");
  return (stmts || []).filter((s) => {
    const status = String(s.status || "");
    if (st !== "all" && status !== st) return false;
    const p = String(s.documentPeriod || s.period || "");
    if (period && p !== period) return false;
    if (q && !payslipArchiveHaystack(s).includes(q)) return false;
    return true;
  });
}

function payslipArchiveCounts(batches) {
  let released = 0;
  let rejected = 0;
  const periods = new Set();
  for (const batch of batches || []) {
    for (const s of batch.statements || []) {
      if (String(s.status) === "released") released += 1;
      if (String(s.status) === "rejected") rejected += 1;
      const p = String(s.documentPeriod || s.period || "").trim();
      if (p) periods.add(p);
    }
  }
  return { released, rejected, periods: [...periods].sort().reverse() };
}

function renderPayslipInboxChrome() {
  const inbox = payslipStudioState.inbox === "archive" ? "archive" : "open";
  $("payslipInboxTabs")?.querySelectorAll("[data-payslip-inbox]").forEach((btn) => {
    btn.classList.toggle("is-active", btn.getAttribute("data-payslip-inbox") === inbox);
  });
  const tools = $("payslipArchiveTools");
  if (!tools) return;
  tools.classList.toggle("hidden", inbox !== "archive");
  if (inbox !== "archive") return;
  const batches = payslipStudioState.batches || [];
  const counts = payslipArchiveCounts(batches);
  const stats = $("payslipArchiveStats");
  if (stats) {
    stats.textContent = `${counts.released} ${t("lohn.statusReleased") || "Gesendet"} · ${counts.rejected} ${t("lohn.statusRejected") || "Abgelehnt"}`;
  }
  const search = $("payslipArchiveSearch");
  if (search) {
    search.placeholder = t("lohn.archiveSearch") || "Name, Badge, Periode…";
    if (search.value !== payslipStudioState.archiveQuery) {
      search.value = payslipStudioState.archiveQuery;
    }
  }
  const filters = $("payslipArchiveFilters");
  if (filters) {
    const cur = payslipStudioState.archiveStatus || "all";
    filters.innerHTML = [
      ["all", t("lohn.archiveFilterAll") || "Alle"],
      ["released", t("lohn.statusReleased") || "Gesendet"],
      ["rejected", t("lohn.statusRejected") || "Abgelehnt"],
    ]
      .map(
        ([id, label]) =>
          `<button type="button" class="${cur === id ? "is-active" : ""}" data-payslip-archive-status="${id}">${escapeHtml(label)}</button>`,
      )
      .join("");
  }
  const periodSel = $("payslipArchivePeriod");
  if (periodSel) {
    const cur = payslipStudioState.archivePeriod || "";
    const opts = [`<option value="">${escapeHtml(t("lohn.archiveAllPeriods") || "Alle Perioden")}</option>`]
      .concat(
        counts.periods.map(
          (p) =>
            `<option value="${escapeAttr(p)}"${p === cur ? " selected" : ""}>${escapeHtml(p)}</option>`,
        ),
      );
    periodSel.innerHTML = opts.join("");
  }
}

function renderPayslipStudioList() {
  const host = $("payslipStudioList");
  if (!host) return;
  renderPayslipInboxChrome();
  const inbox = payslipStudioState.inbox === "archive" ? "archive" : "open";
  const archived = inbox === "archive";
  const batches = (payslipStudioState.batches || [])
    .map((batch) => {
      const stmts = Array.isArray(batch.statements) ? batch.statements : [];
      return {
        ...batch,
        statements: archived ? filterPayslipArchiveStatements(stmts) : stmts,
      };
    })
    .filter((batch) => (batch.statements || []).length);
  if (!batches.length) {
    const empty = archived
      ? payslipStudioState.batches?.length
        ? t("lohn.archiveNoHits") || "Keine Treffer im Archiv."
        : t("lohn.payslipArchiveNone") || "Kein Archiv für diese Firma."
      : t("lohn.payslipNone") || "Keine offenen Lohnabrechnungen.";
    host.innerHTML = `<div class="payslip-studio-empty">${escapeHtml(empty)}</div>`;
    return;
  }
  host.innerHTML = batches
    .map((batch) => {
      const bid = String(batch.id || "");
      const stmts = Array.isArray(batch.statements) ? batch.statements : [];
      const releasable = Number(batch.releasableCount || 0);
      const items = stmts
        .map((s) => {
          const sid = String(s.statementId || s.id || "");
          const active =
            bid === payslipStudioState.activeBatchId && sid === payslipStudioState.activeStmtId
              ? " is-active"
              : "";
          const match = String(s.matchStatus || "matched");
          const st = String(s.status || "pending");
          const badges = [
            `<span class="payslip-match is-${escapeAttr(match)}">${escapeHtml(payslipMatchLabel(match))}</span>`,
          ];
          if (st === "released" || st === "rejected") {
            badges.push(
              `<span class="payslip-match is-${escapeAttr(st)}">${escapeHtml(payslipStatusLabel(st))}</span>`,
            );
          } else if (s.reviewed) {
            badges.push(
              `<span class="payslip-match is-reviewed">${escapeHtml(t("lohn.reviewed") || "Geprüft")}</span>`,
            );
          }
          if (s.locked || s.deliveryLocked) {
            badges.push(`<span class="payslip-match is-locked">${escapeHtml(t("lohn.locked") || "Gesperrt")}</span>`);
          }
          const sentOn = archived ? formatPayslipShortDate(s.releasedAt || s.reviewedAt) : "";
          const docTitle = String(s.title || s.docTypeLabel || s.documentType || s.docType || "").trim();
          const metaParts = [
            docTitle,
            s.badgeId,
            s.documentPeriod || s.period,
            formatPayslipMoney(s.netAmount ?? s.grossAmount, s.currency),
            sentOn ? `${t("lohn.archiveSentOn") || "am"} ${sentOn}` : "",
          ].filter(Boolean);
          return `<button type="button" class="payslip-stmt-item${active}" data-payslip-select="${escapeAttr(bid)}::${escapeAttr(sid)}">
            <div class="name">${escapeHtml(s.displayName || s.workerId || "—")}</div>
            <div class="meta">${escapeHtml(metaParts.join(" · "))}</div>
            ${badges.join(" ")}
          </button>`;
        })
        .join("");
      const batchActions = archived
        ? ""
        : `<div class="payslip-batch-actions">
            <button type="button" class="primary" data-payslip-batch="release-reviewed" data-batch-id="${escapeAttr(bid)}" ${releasable ? "" : "disabled"}>${escapeHtml(t("lohn.releaseReviewed") || "Alle geprüften senden")}</button>
            <button type="button" data-payslip-batch="reject" data-batch-id="${escapeAttr(bid)}">${escapeHtml(t("lohn.rejectBatch") || "Stapel ablehnen")}</button>
          </div>`;
      return `<div class="payslip-batch-group" data-batch="${escapeAttr(bid)}">
        <div class="payslip-batch-head">
          <strong>${escapeHtml(batch.companyName || batch.companyId || "—")} · ${escapeHtml(batch.period || "")}</strong>
          <span>${escapeHtml(String(stmts.length))}${archived ? "" : ` · ${escapeHtml(String(releasable))} ${escapeHtml(t("lohn.ready") || "bereit")}`}</span>
          ${batchActions}
        </div>
        ${items}
      </div>`;
    })
    .join("");
}

function currentPayslipStatement() {
  const batch = (payslipStudioState.batches || []).find(
    (b) => String(b.id) === String(payslipStudioState.activeBatchId),
  );
  if (!batch) return null;
  return (batch.statements || []).find(
    (s) => String(s.statementId || s.id) === String(payslipStudioState.activeStmtId),
  );
}

async function renderPayslipIdentity(stmt) {
  const card = $("payslipIdentityCard");
  const actions = $("payslipStudioActions");
  if (!card || !actions || !stmt) return;
  const match = String(stmt.matchStatus || "matched");
  const locked = isPayslipLocked(stmt) || payslipStudioState.inbox === "archive";
  const warnings = Array.isArray(stmt.stammdatenWarnings) ? stmt.stammdatenWarnings : [];
  const warnHtml = warnings.length
    ? `<ul class="payslip-warn">${warnings.map((w) => `<li>${escapeHtml(String(w))}</li>`).join("")}</ul>`
    : "";
  const lockNote = locked
    ? `<p class="muted small" style="margin:0.45rem 0 0">${escapeHtml(t("lohn.lockedHint") || "Nach dem Versand sind Stammdaten dieser Abrechnung gesperrt.")}</p>`
    : "";
  card.innerHTML = `
    <h3>${escapeHtml(stmt.displayName || "—")}</h3>
    <span class="payslip-match is-${escapeAttr(match)}">${escapeHtml(payslipMatchLabel(match))}</span>
    ${locked ? `<span class="payslip-match is-${escapeAttr(stmt.status || "released")}">${escapeHtml(payslipStatusLabel(stmt.status))}</span>` : ""}
    <p class="muted small" style="margin:0.55rem 0 0">${escapeHtml(stmt.documentPeriod || stmt.period || "")} · ${escapeHtml(formatPayslipMoney(stmt.netAmount, stmt.currency))}</p>
    <p class="muted small" style="margin:0.25rem 0 0">${escapeHtml(stmt.badgeId || stmt.workerId || "")}</p>
    ${lockNote}${warnHtml}`;

  const viewBtns = `
    <button type="button" class="primary" data-payslip-action="open-window">${escapeHtml(t("lohn.openSheetWindow") || "Vollbild prüfen")}</button>
    <button type="button" data-payslip-action="focus-sheet">${escapeHtml(t("lohn.focusSheet") || "Nur Abrechnung anzeigen")}</button>
    <button type="button" data-payslip-action="download-pdf">${escapeHtml(t("lohn.downloadPdf") || "PDF herunterladen")}</button>`;
  if (locked) {
    actions.innerHTML = viewBtns;
    return;
  }

  let workerOptions = "";
  try {
    const workers = await loadPayslipWorkers(stmt.companyId);
    workerOptions = workers
      .map((w) => {
        const id = String(w.employeeId || w.workerId || w.id || "");
        const label = `${w.firstName || ""} ${w.lastName || ""}`.trim() || id;
        const selected = id && id === String(stmt.workerId || "") ? " selected" : "";
        return `<option value="${escapeAttr(id)}"${selected}>${escapeHtml(label)}${w.badgeId ? ` (${escapeHtml(w.badgeId)})` : ""}</option>`;
      })
      .join("");
  } catch {
    workerOptions = "";
  }

  const canSend = !!stmt.canRelease;
  const sendTitle = canSend
    ? ""
    : escapeAttr(
        !stmt.reviewed
          ? (t("lohn.reviewRequired") || "Zuerst Abrechnung öffnen/prüfen")
          : !stmt.workerId
            ? (t("lohn.pickWorker") || "Mitarbeiter zuweisen")
            : (t("lohn.sendBlocked") || "Senden nicht möglich"),
      );
  actions.innerHTML = `
    ${viewBtns}
    <select id="payslipAssignSelect" aria-label="${escapeAttr(t("lohn.assignWorker") || "Mitarbeiter")}">
      <option value="">${escapeHtml(t("lohn.pickWorker") || "— Mitarbeiter —")}</option>
      ${workerOptions}
    </select>
    <button type="button" data-payslip-action="assign">${escapeHtml(t("lohn.applyAssign") || "Zuordnung speichern")}</button>
    <button type="button" class="primary${canSend ? "" : " is-blocked"}" data-payslip-action="release" aria-disabled="${canSend ? "false" : "true"}" title="${sendTitle}">${escapeHtml(t("lohn.sendToWorker") || "An Mitarbeiter senden")}</button>
    <button type="button" data-payslip-action="reject">${escapeHtml(t("lohn.rejectStatement") || "Ablehnen")}</button>
  `;
}

function currentUiTheme() {
  return document.body?.classList?.contains("theme-black") ? "dark" : "light";
}

function wrapPayslipViewerHtml(sheetHtml) {
  const theme = currentUiTheme();
  const bg = theme === "dark" ? "#0b1220" : "#e8edf2";
  const barBg = theme === "dark" ? "#0d1628" : "#ffffff";
  const barBorder = theme === "dark" ? "rgba(120,156,255,0.18)" : "#d8dee6";
  const fg = theme === "dark" ? "#e2e8f0" : "#0f172a";
  const muted = theme === "dark" ? "#94a3b8" : "#64748b";
  const closeLabel = t("common.close") || "Schließen";
  const title = t("lohn.payslipReviewTitle") || "Lohnabrechnung";
  // Extract body content if a full document was returned.
  let inner = String(sheetHtml || "");
  const bodyMatch = inner.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
  if (bodyMatch) inner = bodyMatch[1];
  const styleMatch = String(sheetHtml || "").match(/<style[^>]*>([\s\S]*?)<\/style>/i);
  const sheetCss = styleMatch ? styleMatch[1] : "";
  return `<!DOCTYPE html>
<html lang="de"><head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>${title}</title>
<style>
${sheetCss}
html, body { margin:0; height:100%; background:${bg}; color:${fg}; }
.payslip-viewer-bar {
  position: sticky; top: 0; z-index: 20;
  display: flex; align-items: center; justify-content: space-between; gap: 1rem;
  padding: 0.7rem 1rem; background: ${barBg}; border-bottom: 1px solid ${barBorder};
  box-shadow: 0 8px 24px rgba(0,0,0,0.18);
}
.payslip-viewer-bar strong { font-size: 0.95rem; }
.payslip-viewer-bar span { font-size: 0.78rem; color: ${muted}; }
.payslip-viewer-bar button {
  border: 1px solid ${barBorder}; background: #ef4444; color: #fff;
  border-radius: 8px; padding: 0.45rem 0.9rem; font-weight: 600; cursor: pointer;
}
.payslip-viewer-stage {
  min-height: calc(100vh - 54px); box-sizing: border-box;
  display: flex; justify-content: center; align-items: flex-start;
  padding: 18px 12px 28px; overflow: auto; background: ${bg};
}
.payslip-viewer-stage .datev-sheet-a4 { margin: 0 auto; box-shadow: 0 12px 36px rgba(0,0,0,0.28); }
body.sheet-chrome { min-height: auto !important; padding: 0 !important; background: transparent !important; display: block !important; }
</style>
</head>
<body>
  <header class="payslip-viewer-bar">
    <div>
      <strong>${title}</strong>
      <div><span>WorkPass Lohn · DatevSheet</span></div>
    </div>
    <button type="button" id="payslipViewerClose">${closeLabel}</button>
  </header>
  <main class="payslip-viewer-stage">${inner}</main>
  <script>
    (function () {
      var btn = document.getElementById("payslipViewerClose");
      function closeWin() {
        try { window.close(); } catch (e) {}
        try { parent.postMessage({ type: "workpass-payslip-close" }, "*"); } catch (e) {}
      }
      if (btn) btn.addEventListener("click", closeWin);
      document.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape") closeWin();
      });
      try { window.focus(); } catch (e) {}
    })();
  </script>
</body></html>`;
}

function revokePayslipViewerBlobUrl() {
  const url = payslipStudioState.viewerBlobUrl;
  if (!url) return;
  payslipStudioState.viewerBlobUrl = "";
  try {
    URL.revokeObjectURL(url);
  } catch {
    /* ignore */
  }
}

function closePayslipSheetOverlay() {
  const overlay = $("payslipSheetOverlay");
  if (!overlay) return;
  overlay.classList.add("hidden");
  overlay.setAttribute("aria-hidden", "true");
  const frame = overlay.querySelector("iframe");
  if (frame) {
    frame.srcdoc = "";
    frame.removeAttribute("src");
  }
  document.body.classList.remove("payslip-overlay-open");
  try {
    if (document.fullscreenElement === overlay) {
      (document.exitFullscreen || document.webkitExitFullscreen)?.call(document);
    }
  } catch {
    /* ignore */
  }
}

function ensurePayslipSheetOverlay() {
  let overlay = $("payslipSheetOverlay");
  if (overlay) return overlay;
  overlay = document.createElement("div");
  overlay.id = "payslipSheetOverlay";
  overlay.className = "payslip-sheet-overlay hidden";
  overlay.setAttribute("aria-hidden", "true");
  overlay.innerHTML = `
    <div class="payslip-sheet-overlay-bar">
      <strong>${escapeHtml(t("lohn.payslipReviewTitle") || "Lohnabrechnung")}</strong>
      <button type="button" id="payslipSheetOverlayClose">${escapeHtml(t("common.close") || "Schließen")}</button>
    </div>
    <iframe class="payslip-sheet-overlay-frame" title="Lohnabrechnung"></iframe>`;
  document.body.appendChild(overlay);
  overlay.querySelector("#payslipSheetOverlayClose")?.addEventListener("click", () => closePayslipSheetOverlay());
  overlay.addEventListener("click", (ev) => {
    if (ev.target === overlay) closePayslipSheetOverlay();
  });
  return overlay;
}

function openPayslipSheetOverlay(viewerHtml) {
  const overlay = ensurePayslipSheetOverlay();
  const frame = overlay.querySelector("iframe");
  if (frame) frame.srcdoc = String(viewerHtml || "");
  overlay.classList.remove("hidden");
  overlay.setAttribute("aria-hidden", "false");
  document.body.classList.add("payslip-overlay-open");
  const req = overlay.requestFullscreen || overlay.webkitRequestFullscreen;
  try {
    req?.call(overlay);
  } catch {
    /* fullscreen optional */
  }
  showActionToast(t("lohn.overlayOpened") || "Abrechnung im Vollbild geöffnet");
}

function openPayslipSheetWindow(html) {
  const docHtml = String(html || payslipStudioState.sheetHtml || "").trim();
  if (!docHtml) {
    showActionToast(t("lohn.sheetMissing") || "Keine Abrechnung geladen", true);
    return;
  }
  const viewerHtml = wrapPayslipViewerHtml(docHtml);
  try {
    if (payslipStudioState.sheetWindow && !payslipStudioState.sheetWindow.closed) {
      payslipStudioState.sheetWindow.close();
    }
  } catch {
    /* ignore */
  }
  revokePayslipViewerBlobUrl();
  let win = null;
  try {
    const blob = new Blob([viewerHtml], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    payslipStudioState.viewerBlobUrl = url;
    win = window.open(url, "workpass-lohn-payslip");
    if (win) {
      payslipStudioState.sheetWindow = win;
      try {
        win.focus();
      } catch {
        /* ignore */
      }
      const watch = window.setInterval(() => {
        let closed = false;
        try {
          closed = !win || win.closed;
        } catch {
          closed = true;
        }
        if (!closed) return;
        window.clearInterval(watch);
        revokePayslipViewerBlobUrl();
      }, 1200);
      return;
    }
  } catch {
    win = null;
  }
  revokePayslipViewerBlobUrl();
  openPayslipSheetOverlay(viewerHtml);
}

function statementPrefersPdfPreview(stmt) {
  if (!stmt) return false;
  // Hard rule: everything from WorkPass Lohn with a PDF opens unchanged.
  if (stmt.hasPdf || stmt.pdfImmutable || stmt.lohnPassthrough || Number(stmt.fileSize || 0) > 20) {
    return true;
  }
  if (stmt.pdfSuspectRemake) return true;
  const src = String(stmt.pdfSource || "").toLowerCase();
  if (
    src === "lohn_original"
    || src === "lohn_html2canvas"
    || src === "lohn_sheet_capture"
  ) {
    return true;
  }
  const origin = String(stmt.source || stmt.origin || "").toLowerCase();
  if (origin === "lohn_delivery" || origin === "workpass_lohn" || origin === "lohn") return true;
  const mode = String(stmt.previewMode || "").toLowerCase();
  if (mode === "pdf") return true;
  const docType = String(stmt.docType || stmt.documentType || "").toLowerCase();
  const sheetTypes = new Set(["lohnabrechnung", "gehaltsabrechnung", ""]);
  if (docType && !sheetTypes.has(docType)) return true;
  const title = String(stmt.title || stmt.docTypeLabel || stmt.filename || "").toLowerCase();
  if (/vordienst|lohnsteuer|lstb|verdienst|jahresabrechnung|steuerbescheinigung|bescheinigung|شهادة|سنوي/.test(title)) {
    return true;
  }
  return false;
}

async function loadPayslipStudioOriginalPdf(batchId, statementId, iframe) {
  const token = String(WP?.readSessionToken?.() || wpGet(TOKEN_KEY) || "").trim();
  const headers = { Accept: "application/pdf" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(
    `/api/payroll/statements/${encodeURIComponent(batchId)}/${encodeURIComponent(statementId)}/pdf`,
    { headers },
  );
  if (!res.ok) {
    let msg = `PDF ${res.status}`;
    try {
      const j = await res.json();
      msg = j.error || j.hint || msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  const raw = await res.blob();
  if (!raw || raw.size < 40) {
    throw new Error(t("lohn.pdfMissing") || "PDF fehlt oder ist leer");
  }
  const head = new Uint8Array(await raw.slice(0, 5).arrayBuffer());
  const magic = String.fromCharCode(...head);
  if (!magic.startsWith("%PDF")) {
    throw new Error(t("lohn.pdfInvalid") || "Datei ist kein PDF");
  }
  const blob = raw.type === "application/pdf" ? raw : new Blob([raw], { type: "application/pdf" });
  if (payslipStudioState.pdfObjectUrl) {
    try {
      URL.revokeObjectURL(payslipStudioState.pdfObjectUrl);
    } catch {
      /* ignore */
    }
  }
  const url = URL.createObjectURL(blob);
  payslipStudioState.pdfObjectUrl = url;
  payslipStudioState.sheetHtml = "";
  setPayslipPreviewKind("pdf");
  invalidatePayslipCaptureCache();
  if (iframe) {
    iframe.removeAttribute("srcdoc");
    iframe.setAttribute("scrolling", "auto");
    iframe.onload = () => {
      try {
        schedulePayslipPreviewFit();
        const wrap = iframe.closest(".payslip-studio-pdf-wrap");
        if (wrap) wrap.scrollTop = 0;
      } catch {
        /* ignore */
      }
    };
    // FitH so content is visible; allow toolbar for zoom/scroll on non-payslip docs.
    iframe.src = `${url}#toolbar=1&navpanes=0&scrollbar=1&view=FitH`;
    schedulePayslipPreviewFit();
  }
  return url;
}

async function selectPayslipStatement(batchId, statementId) {
  payslipStudioState.activeBatchId = String(batchId || "");
  payslipStudioState.activeStmtId = String(statementId || "");
  renderPayslipStudioList();
  const empty = $("payslipStudioEmpty");
  const work = $("payslipStudioWork");
  const stmt = currentPayslipStatement();
  if (!stmt) {
    empty?.classList.remove("hidden");
    work?.classList.add("hidden");
    return;
  }
  empty?.classList.add("hidden");
  work?.classList.remove("hidden");
  await renderPayslipIdentity(stmt);

  if (stmt.pdfSuspectRemake) {
    showActionToast(
      t("lohn.pdfRemakeHint")
        || "Dieses Dokument wurde als Datev-Blatt neu erzeugt — bitte Original erneut aus WorkPass Lohn senden.",
      true,
    );
  }

  if (payslipStudioState.pdfObjectUrl) {
    try {
      URL.revokeObjectURL(payslipStudioState.pdfObjectUrl);
    } catch {
      /* ignore */
    }
    payslipStudioState.pdfObjectUrl = "";
  }
  const iframe = $("payslipStudioPdf");
  try {
    const docType = String(stmt.docType || stmt.documentType || "").toLowerCase();
    const src = String(stmt.pdfSource || "").toLowerCase();
    const origin = String(stmt.source || stmt.origin || "").toLowerCase();
    const allowSheetFallback =
      ["lohnabrechnung", "gehaltsabrechnung"].includes(docType)
      && !stmt.pdfImmutable
      && !stmt.lohnPassthrough
      && !stmt.hasPdf
      && Number(stmt.fileSize || 0) <= 20
      && src !== "lohn_original"
      && src !== "lohn_html2canvas"
      && src !== "lohn_sheet_capture"
      && origin !== "lohn_delivery"
      && origin !== "workpass_lohn"
      && origin !== "lohn";
    // Always try the unchanged Lohn PDF first. Datev sheet only if no original exists.
    let usedPdf = false;
    try {
      await loadPayslipStudioOriginalPdf(batchId, statementId, iframe);
      usedPdf = true;
    } catch (pdfErr) {
      if (!allowSheetFallback) {
        throw pdfErr;
      }
    }
    if (!usedPdf) {
      setPayslipPreviewKind("sheet");
      const token = wpGet(TOKEN_KEY);
      const headers = { Accept: "text/html" };
      if (token) headers.Authorization = `Bearer ${token}`;
      const sheetRes = await fetch(
        `/api/payroll/statements/${encodeURIComponent(batchId)}/${encodeURIComponent(statementId)}/sheet?theme=${encodeURIComponent(currentUiTheme())}&embed=1`,
        { headers },
      );
      if (!sheetRes.ok) throw new Error(`Abrechnung ${sheetRes.status}`);
      const sheetHtml = await sheetRes.text();
      payslipStudioState.sheetHtml = sheetHtml;
      invalidatePayslipCaptureCache();
      warmPayslipCaptureLibs();
      if (iframe) {
        iframe.removeAttribute("src");
        iframe.setAttribute("scrolling", "no");
        iframe.srcdoc = sheetHtml;
        iframe.onload = () => {
          try {
            lockPayslipIframeChrome(iframe);
            schedulePayslipPreviewFit();
            setTimeout(schedulePayslipPreviewFit, 120);
            warmPayslipCaptureLibs();
            schedulePayslipPdfPrep(batchId, statementId);
            const wrap = iframe.closest(".payslip-studio-pdf-wrap");
            if (wrap) wrap.scrollTop = 0;
            try {
              iframe.contentWindow?.scrollTo?.(0, 0);
            } catch {
              /* ignore */
            }
          } catch {
            /* cross-origin / not ready */
          }
        };
        schedulePayslipPreviewFit();
      }
    }
    if (!isPayslipLocked(stmt) && payslipStudioState.inbox !== "archive" && !isSupportReadOnlySession()) {
      await api(
        `/api/payroll/statements/${encodeURIComponent(batchId)}/${encodeURIComponent(statementId)}/review-open`,
        { method: "POST", body: "{}" },
      );
      await refreshPayslipStudio({ keepSelection: true });
    }
  } catch (err) {
    if (iframe) {
      iframe.srcdoc = "";
      iframe.src = "about:blank";
    }
    setPayslipPreviewKind("sheet");
    const msg = humanizeUserError?.(err) || err?.message || "Abrechnung fehlgeschlagen";
    showActionToast(msg, true);
  }
}

async function refreshPayslipStudio({ keepSelection = false } = {}) {
  if (shouldSkipSupportBackgroundLoads()) return;
  const cid = activeCompanyId();
  const inbox = payslipStudioState.inbox === "archive" ? "archive" : "open";
  const params = new URLSearchParams();
  if (cid) params.set("company_id", cid);
  params.set("inbox", inbox);
  const data = await api(`/api/payroll/statements/pending?${params.toString()}`);
  payslipStudioState.batches = Array.isArray(data?.batches) ? data.batches : [];
  renderPayslipStudioList();
  if (keepSelection && payslipStudioState.activeBatchId && payslipStudioState.activeStmtId) {
    const still = currentPayslipStatement();
    if (still) {
      await renderPayslipIdentity(still);
      return;
    }
  }
  const firstBatch = payslipStudioState.batches[0];
  const firstStmt = firstBatch?.statements?.[0];
  if (firstBatch && firstStmt) {
    await selectPayslipStatement(firstBatch.id, firstStmt.statementId || firstStmt.id);
  } else {
    payslipStudioState.activeBatchId = "";
    payslipStudioState.activeStmtId = "";
    $("payslipStudioEmpty")?.classList.remove("hidden");
    $("payslipStudioWork")?.classList.add("hidden");
  }
}

async function openPayslipReviewStudio(opts = {}) {
  closeLohnDrawer();
  const el = $("payslipReviewStudio");
  if (!el) return;
  el.classList.remove("hidden");
  el.setAttribute("aria-hidden", "false");
  document.body.classList.add("payslip-studio-open");
  warmPayslipCaptureLibs();
  schedulePayslipPreviewFit();
  $("payslipStudioList").innerHTML = `<div class="payslip-studio-empty">${escapeHtml(t("common.loading") || "…")}</div>`;
  try {
    await refreshPayslipStudio({ keepSelection: false });
    if (opts.batchId && opts.statementId) {
      await selectPayslipStatement(opts.batchId, opts.statementId);
    } else if (opts.batchId) {
      const batch = payslipStudioState.batches.find((b) => String(b.id) === String(opts.batchId));
      const stmt = batch?.statements?.[0];
      if (stmt) await selectPayslipStatement(batch.id, stmt.statementId || stmt.id);
    }
  } catch (err) {
    toast(err?.message || "load_failed", "error");
  }
}

function selectNextPayslipStatement() {
  const flat = [];
  for (const b of payslipStudioState.batches || []) {
    for (const s of b.statements || []) {
      flat.push({ batchId: b.id, statementId: s.statementId || s.id });
    }
  }
  const idx = flat.findIndex(
    (x) =>
      String(x.batchId) === String(payslipStudioState.activeBatchId) &&
      String(x.statementId) === String(payslipStudioState.activeStmtId),
  );
  const next = flat[idx + 1] || flat[0];
  if (next) return selectPayslipStatement(next.batchId, next.statementId);
}

async function switchPayslipInbox(next) {
  const inbox = next === "archive" ? "archive" : "open";
  if (payslipStudioState.inbox === inbox) return;
  const seq = ++payslipStudioState.inboxSeq;
  payslipStudioState.inbox = inbox;
  payslipStudioState.activeBatchId = "";
  payslipStudioState.activeStmtId = "";
  renderPayslipInboxChrome();
  const host = $("payslipStudioList");
  if (host) {
    host.innerHTML = `<div class="payslip-studio-empty">${escapeHtml(t("common.loading") || "…")}</div>`;
  }
  $("payslipStudioWork")?.classList.add("hidden");
  $("payslipStudioEmpty")?.classList.remove("hidden");
  await refreshPayslipStudio({ keepSelection: false });
  if (seq !== payslipStudioState.inboxSeq) return;
}

async function handlePayslipStudioClick(ev) {
  const inboxBtn = ev.target?.closest?.("[data-payslip-inbox]");
  if (inboxBtn) {
    await switchPayslipInbox(inboxBtn.getAttribute("data-payslip-inbox"));
    return;
  }
  const archiveStatus = ev.target?.closest?.("[data-payslip-archive-status]");
  if (archiveStatus) {
    payslipStudioState.archiveStatus = archiveStatus.getAttribute("data-payslip-archive-status") || "all";
    renderPayslipStudioList();
    return;
  }
  const selectBtn = ev.target?.closest?.("[data-payslip-select]");
  if (selectBtn) {
    const [batchId, statementId] = String(selectBtn.getAttribute("data-payslip-select") || "").split("::");
    if (batchId && statementId) await selectPayslipStatement(batchId, statementId);
    return;
  }
  const batchAct = ev.target?.closest?.("[data-payslip-batch]");
  if (batchAct) {
    const action = batchAct.getAttribute("data-payslip-batch");
    const batchId = batchAct.getAttribute("data-batch-id");
    if (!batchId) return;
    if (action === "release-reviewed") {
      if (!window.confirm(t("lohn.confirmReleaseReviewed") || "Alle geprüften Abrechnungen an die Mitarbeiter-App senden?")) {
        return;
      }
      const res = await api(`/api/payroll/statements/${encodeURIComponent(batchId)}/release-reviewed`, {
        method: "POST",
        body: "{}",
      });
      toast(res.message || `${res.released || 0} gesendet`, "ok");
      await refreshPayslipStudio({ keepSelection: true });
      broadcastLohnInboxChanged();
      return;
    }
    if (action === "reject") {
      const reason = window.prompt(t("lohn.rejectReason") || "Grund (optional)", "") || "";
      if (!window.confirm(t("lohn.confirmRejectBatch") || "Gesamten Stapel ablehnen?")) return;
      await api(`/api/payroll/statements/${encodeURIComponent(batchId)}/reject`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      toast(t("lohn.batchRejected") || "Stapel abgelehnt", "ok");
      await refreshPayslipStudio({ keepSelection: false });
      broadcastLohnInboxChanged();
    }
    return;
  }
  const act = ev.target?.closest?.("[data-payslip-action]");
  if (!act) return;
  const action = act.getAttribute("data-payslip-action");
  const batchId = payslipStudioState.activeBatchId;
  const statementId = payslipStudioState.activeStmtId;
  if (!batchId || !statementId) return;
  if (action === "next") {
    await selectNextPayslipStatement();
    return;
  }
  if (action === "open-window") {
    const stmt = currentPayslipStatement();
    if (payslipStudioState.pdfObjectUrl && statementPrefersPdfPreview(stmt)) {
      window.open(payslipStudioState.pdfObjectUrl, "_blank", "noopener");
      return;
    }
    if (!String(payslipStudioState.sheetHtml || "").trim()) {
      toast(t("lohn.sheetMissing") || "Keine Abrechnung geladen — Eintrag erneut wählen", "error");
      return;
    }
    openPayslipSheetWindow(payslipStudioState.sheetHtml);
    return;
  }
  if (action === "focus-sheet") {
    const studio = $("payslipReviewStudio");
    const on = studio?.classList.toggle("is-sheet-focus");
    document.body.classList.toggle("payslip-sheet-focus", Boolean(on));
    const iframe = $("payslipStudioPdf");
    const wrap = iframe?.closest?.(".payslip-studio-pdf-wrap");
    let exitBtn = $("payslipFocusExitBtn");
    if (on) {
      if (!exitBtn) {
        exitBtn = document.createElement("button");
        exitBtn.id = "payslipFocusExitBtn";
        exitBtn.type = "button";
        exitBtn.className = "payslip-focus-exit primary";
        exitBtn.setAttribute("data-payslip-action", "focus-sheet");
        exitBtn.textContent = t("lohn.exitFocus") || "Zurück zur Freigabe";
        studio?.appendChild(exitBtn);
      }
      exitBtn.classList.remove("hidden");
      if (iframe) iframe.style.pointerEvents = "auto";
      const host = wrap || studio;
      const req = host?.requestFullscreen || host?.webkitRequestFullscreen;
      try {
        req?.call(host);
      } catch {
        /* fullscreen optional — CSS focus still applies */
      }
    } else if (exitBtn) {
      exitBtn.classList.add("hidden");
      if (iframe) iframe.style.pointerEvents = "none";
      try {
        if (document.fullscreenElement) {
          (document.exitFullscreen || document.webkitExitFullscreen)?.call(document);
        }
      } catch {
        /* ignore */
      }
    }
    schedulePayslipPreviewFit();
    return;
  }
  if (action === "download-pdf") {
    if (payslipStudioState.downloadInFlight) {
      showActionToast(t("lohn.preparingPdf") || "PDF wird erstellt…");
      return;
    }
    payslipStudioState.downloadInFlight = true;
    if (act) act.setAttribute("disabled", "disabled");
    const stmtDl = currentPayslipStatement();
    const useOriginal = statementPrefersPdfPreview(stmtDl) || Boolean(payslipStudioState.pdfObjectUrl);
    const hadReady = useOriginal
      ? Boolean(payslipStudioState.pdfObjectUrl)
      : Boolean(getFreshPayslipCapture(batchId, statementId)?.blobUrl);
    try {
      if (!hadReady) showActionToast(t("lohn.preparingPdf") || "PDF wird erstellt…");
      let url = "";
      if (useOriginal) {
        url = payslipStudioState.pdfObjectUrl || (await loadPayslipStudioOriginalPdf(batchId, statementId, null));
      } else {
        url = await fetchPayslipPdfBlobUrl(batchId, statementId);
      }
      const a = document.createElement("a");
      a.href = url;
      a.download = stmtDl?.filename || stmtDl?.title || "Lohnabrechnung.pdf";
      if (!String(a.download).toLowerCase().endsWith(".pdf")) a.download = `${a.download}.pdf`;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
      if (!hadReady) showActionToast(t("lohn.pdfReady") || "PDF bereit");
    } catch (err) {
      toast(err?.message || "PDF", "error");
    } finally {
      payslipStudioState.downloadInFlight = false;
      if (act) act.removeAttribute("disabled");
    }
    return;
  }
  const stmtNow = currentPayslipStatement();
  if (isPayslipLocked(stmtNow) && (action === "assign" || action === "release" || action === "reject")) {
    toast(t("lohn.lockedHint") || "Abrechnung ist gesperrt", "error");
    return;
  }
  if (action === "assign") {
    const workerId = String($("payslipAssignSelect")?.value || "").trim();
    if (!workerId) {
      toast(t("lohn.pickWorker") || "Mitarbeiter wählen", "error");
      return;
    }
    try {
      showActionToast(t("lohn.saving") || "Speichern…");
      await api(
        `/api/payroll/statements/${encodeURIComponent(batchId)}/${encodeURIComponent(statementId)}/assign`,
        { method: "POST", body: JSON.stringify({ workerId }) },
      );
      toast(t("lohn.assignSaved") || "Zuordnung gespeichert", "ok");
      await refreshPayslipStudio({ keepSelection: true });
    } catch (err) {
      showActionToast(humanizeUserError?.(err) || err?.message || "error", true);
    }
    return;
  }
  if (action === "release") {
    if (act?.getAttribute("aria-disabled") === "true" || (stmtNow && !stmtNow.canRelease)) {
      const why = !stmtNow?.reviewed
        ? (t("lohn.reviewRequired") || "Zuerst Abrechnung öffnen/prüfen")
        : !stmtNow?.workerId
          ? (t("lohn.pickWorker") || "Mitarbeiter zuweisen")
          : (t("lohn.sendBlocked") || "Senden nicht möglich");
      showActionToast(why, true);
      return;
    }
    if (payslipStudioState.releaseInFlight) {
      showActionToast(t("lohn.sending") || "Wird gesendet…");
      return;
    }
    const warns = Array.isArray(stmtNow?.stammdatenWarnings) ? stmtNow.stammdatenWarnings : [];
    const extra = warns.length ? `\n\n${warns.join("\n")}` : "";
    if (!window.confirm((t("lohn.confirmSendWorker") || "Diese Lohnabrechnung an die Mitarbeiter-App senden?") + extra)) {
      return;
    }
    payslipStudioState.releaseInFlight = true;
    const releaseBtn = act;
    if (releaseBtn) releaseBtn.setAttribute("disabled", "disabled");
    const preferOriginalPdf =
      statementPrefersPdfPreview(stmtNow)
      || Boolean(stmtNow?.pdfImmutable)
      || Boolean(payslipStudioState.pdfObjectUrl);
    const alreadyReady = preferOriginalPdf
      ? Boolean(payslipStudioState.pdfObjectUrl || stmtNow?.hasPdf)
      : Boolean(getFreshPayslipCapture(batchId, statementId)?.synced);
    try {
      showActionToast(
        alreadyReady
          ? (t("lohn.sending") || "Wird gesendet…")
          : (t("lohn.preparingPdf") || "PDF wird erstellt…"),
      );
      if (!preferOriginalPdf) {
        const captured = await syncPayslipStudioPdfFromHtml(batchId, statementId);
        if (!alreadyReady) showActionToast(t("lohn.sending") || "Wird gesendet…");
        if (!captured?.ok) {
          throw new Error(
            t("lohn.captureRequired")
              || "PDF-Erfassung fehlgeschlagen — Abrechnung erneut öffnen und senden",
          );
        }
      } else if (!alreadyReady) {
        showActionToast(t("lohn.sending") || "Wird gesendet…");
      }
      const res = await api(
        `/api/payroll/statements/${encodeURIComponent(batchId)}/${encodeURIComponent(statementId)}/release`,
        { method: "POST", body: "{}" },
      );
      if (!res?.ok) {
        throw new Error(res?.message || res?.error || t("lohn.sendFailed") || "Senden fehlgeschlagen");
      }
      if (!res.workerDocumentId) {
        throw new Error(
          t("lohn.sendNoDocument")
            || "Senden ohne Dokument — bitte erneut versuchen",
        );
      }
      toast(
        res.message
          || (res.repaired
            ? (t("lohn.repairedSend") || "Nachgeliefert an Mitarbeiter-App")
            : (t("lohn.sentToArchive") || t("lohn.sentToWorker") || "Gesendet")),
        "ok",
      );
      await refreshPayslipStudio({ keepSelection: false });
      broadcastLohnInboxChanged();
    } catch (err) {
      const msg = humanizeUserError?.(err) || err?.message || t("lohn.sendFailed") || "Senden fehlgeschlagen";
      showActionToast(msg, true);
    } finally {
      payslipStudioState.releaseInFlight = false;
      if (releaseBtn) {
        releaseBtn.removeAttribute("disabled");
        if (currentPayslipStatement()?.canRelease) {
          releaseBtn.setAttribute("aria-disabled", "false");
          releaseBtn.classList.remove("is-blocked");
        }
      }
    }
    return;
  }
  if (action === "reject") {
    const reason = window.prompt(t("lohn.rejectReason") || "Grund (optional)", "") || "";
    await api(
      `/api/payroll/statements/${encodeURIComponent(batchId)}/${encodeURIComponent(statementId)}/reject`,
      { method: "POST", body: JSON.stringify({ reason }) },
    );
    toast(t("lohn.statementRejected") || "Abgelehnt", "ok");
    await refreshPayslipStudio({ keepSelection: false });
    broadcastLohnInboxChanged();
  }
}

function lohnContractsUrl(companyId, workerId, fields, hint) {
  const cid = String(companyId || activeCompanyId() || "").trim();
  const wid = String(workerId || "").trim();
  const u = new URL("/admin-v2/contracts.html", location.origin);
  if (cid) u.searchParams.set("company_id", cid);
  if (wid) u.searchParams.set("worker_id", wid);
  u.searchParams.set("focus", "payroll");
  const fieldList = Array.isArray(fields) ? fields.filter(Boolean) : [];
  if (fieldList.length) u.searchParams.set("fields", fieldList.join(","));
  if (hint) u.searchParams.set("hint", String(hint).slice(0, 120));
  return u.pathname + u.search;
}

function renderLohnDrawerChips(fields) {
  const list = Array.isArray(fields) ? fields.filter(Boolean) : [];
  if (!list.length) return "";
  return `<div class="lohn-drawer-chips">${list
    .slice(0, 6)
    .map((f) => `<span class="lohn-drawer-chip">${escapeHtml(String(f))}</span>`)
    .join("")}</div>`;
}

async function openLohnDrawer() {
  if (!canAccessWorkpassLohnUi()) {
    closeLohnDrawer();
    return;
  }
  if (shouldSkipSupportBackgroundLoads()) return;
  const drawer = $("lohnDrawer");
  const body = $("lohnDrawerBody");
  if (!drawer || !body) return;
  drawer.classList.remove("hidden");
  document.body.classList.add("lohn-drawer-open");
  body.innerHTML = `<div class="lohn-drawer-empty">${escapeHtml(t("common.loading") || "Wird geladen…")}</div>`;
  drawer.setAttribute("aria-hidden", "false");

  const q = companyQuery();
  const cid = activeCompanyId() || q.replace("?company_id=", "");
  const opsLink = $("lohnDrawerOpsLink");
  if (opsLink) {
    opsLink.href = `/ops-command-center.html${cid ? `?company_id=${encodeURIComponent(cid)}` : ""}#lohnHub`;
  }
  if (getUser().role === "superadmin" && !cid) {
    body.innerHTML = `<div class="lohn-drawer-empty">${escapeHtml(t("common.selectCompany") || "Bitte Firma wählen")}</div>`;
    return;
  }

  const cq = cid ? `?company_id=${encodeURIComponent(cid)}` : "";
  const sync = isSupportReadOnlySession() ? "0" : "1";
  const msgUrl = `/api/payroll/accounting/messages?sync=${sync}${cid ? `&company_id=${encodeURIComponent(cid)}` : ""}`;
  let messages = [];
  let alerts = [];
  let periodRequests = [];
  let payslipBatches = [];
  try {
    const [msgRes, alertRes, periodRes, payslipRes] = await Promise.all([
      apiSoft(msgUrl, { messages: [] }, 8000),
      apiSoft(`/api/payroll/accounting/data-alerts${cq}`, { alerts: [] }, 4000),
      apiSoft(
        `/api/payroll/accounting/period-requests?status=pending_confirmation${cid ? `&company_id=${encodeURIComponent(cid)}` : ""}`,
        { requests: [] },
        4000,
      ),
      apiSoft(`/api/payroll/statements/pending${cq}`, { batches: [] }, 5000),
    ]);
    messages = Array.isArray(msgRes?.messages) ? msgRes.messages : [];
    alerts = Array.isArray(alertRes?.alerts) ? alertRes.alerts : [];
    periodRequests = Array.isArray(periodRes?.requests) ? periodRes.requests : [];
    payslipBatches = Array.isArray(payslipRes?.batches) ? payslipRes.batches : [];
  } catch (e) {
    body.innerHTML = `<div class="lohn-drawer-empty">${escapeHtml(e.message || "load_failed")}</div>`;
    return;
  }

  const payslipCount = payslipBatches.reduce(
    (n, b) => n + (Array.isArray(b.statements) ? b.statements.length : Number(b.statement_count || 0)),
    0,
  );
  updateLohnNavBadge(messages.length + payslipCount);
  paintLohnBadge($("opsStripLohnBadge"), messages.length + payslipCount);

  if (!messages.length && !alerts.length && !periodRequests.length && !payslipBatches.length) {
    body.innerHTML = `<div class="lohn-drawer-empty"><strong>${escapeHtml(t("lohn.drawerEmptyTitle") || "Alles erledigt")}</strong>${escapeHtml(t("lohn.drawerEmptyBody") || "Keine offenen Anfragen von WorkPass Lohn.")}</div>`;
    return;
  }

  const parts = [];

  if (payslipBatches.length) {
    parts.push(`
      <article class="lohn-drawer-item is-alert">
        <div class="lohn-drawer-item-title">${escapeHtml(t("lohn.payslipPendingTitle") || "Lohnabrechnungen zur Prüfung")}</div>
        <div class="lohn-drawer-item-body">${escapeHtml(t("lohn.payslipPendingBody", { n: String(payslipCount) }) || `${payslipCount} PDF(s) warten auf Prüfung und Versand an die Mitarbeiter-App.`)}</div>
        <div class="lohn-drawer-actions">
          <button type="button" class="primary" data-lohn-drawer="open-payslips">${escapeHtml(t("lohn.openPayslipReview") || "Jetzt prüfen & senden")}</button>
        </div>
      </article>`);
  }

  for (const req of periodRequests.slice(0, 8)) {
    const id = String(req.id || "");
    const period = String(req.period || "—");
    parts.push(`
      <article class="lohn-drawer-item is-alert" data-lohn-period="${escapeAttr(id)}">
        <div class="lohn-drawer-item-title">${escapeHtml(t("lohn.periodRequestTitle") || "Perioden-Übergabe")}</div>
        <div class="lohn-drawer-item-body">${escapeHtml(t("lohn.periodRequestBody", { period }) || `Buchhaltung bittet um Daten für ${period}.`)}</div>
        <div class="lohn-drawer-item-meta">${escapeHtml(period)}</div>
        <div class="lohn-drawer-actions">
          <button type="button" class="primary" data-lohn-drawer="period-confirm" data-id="${escapeAttr(id)}">${escapeHtml(t("lohn.periodConfirm") || "Freigeben")}</button>
          <button type="button" data-lohn-drawer="period-reject" data-id="${escapeAttr(id)}">${escapeHtml(t("lohn.periodReject") || "Ablehnen")}</button>
        </div>
      </article>`);
  }

  for (const a of alerts.slice(0, 12)) {
    const id = String(a.id || "");
    const wid = String(a.workerId || a.employeeId || "").trim();
    const fields = a.missingFields || a.missing_fields || [];
    const name = String(a.workerDisplayName || "").trim()
      || [a.workerFirstName, a.workerLastName].filter(Boolean).join(" ").trim()
      || a.workerName || wid || "—";
    const href = lohnContractsUrl(a.companyId || cid, wid, fields, a.message || "");
    parts.push(`
      <article class="lohn-drawer-item is-alert" data-lohn-alert="${escapeAttr(id)}">
        <div class="lohn-drawer-item-title"><strong>${escapeHtml(name)}</strong>${wid && name !== wid ? ` <span class="muted">(${escapeHtml(wid)})</span>` : ""}</div>
        <div class="lohn-drawer-item-body">${escapeHtml(a.message || (t("lohn.missingData") || "Fehlende Stammdaten"))}</div>
        ${renderLohnDrawerChips(fields)}
        <div class="lohn-drawer-actions">
          <a class="primary" href="${escapeAttr(href)}" target="_blank" rel="noopener" data-lohn-drawer="open-stammdaten" data-alert-id="${escapeAttr(id)}" data-worker-id="${escapeAttr(wid)}">${escapeHtml(t("lohn.openStammdaten") || "Stammdaten öffnen")}</a>
          <button type="button" data-lohn-drawer="dismiss-alert" data-id="${escapeAttr(id)}">${escapeHtml(t("lohn.dismiss") || "Erledigt")}</button>
        </div>
      </article>`);
  }

  for (const m of messages.slice(0, 20)) {
    const id = String(m.id || "");
    const fields = m.missingFields || m.missing_fields || [];
    const subject = m.subject || m.kind || "WorkPass Lohn";
    const bodyText = String(m.body || "").trim();
    const wid = String(m.workerId || "").trim();
    const name = String(m.workerDisplayName || "").trim()
      || [m.workerFirstName, m.workerLastName].filter(Boolean).join(" ").trim();
    const workerLine = name && wid
      ? `${name} · ID ${wid}`
      : (name || (wid ? `ID ${wid}` : ""));
    const href = lohnContractsUrl(m.companyId || cid, m.workerId, fields, `${subject} ${bodyText}`);
    parts.push(`
      <article class="lohn-drawer-item" data-lohn-msg="${escapeAttr(id)}">
        <div class="lohn-drawer-item-title">${escapeHtml(subject)}</div>
        ${workerLine ? `<div class="lohn-drawer-item-worker"><strong>${escapeHtml(name || "—")}</strong>${wid ? ` <span class="muted">(${escapeHtml(wid)})</span>` : ""}</div>` : ""}
        ${bodyText ? `<div class="lohn-drawer-item-body">${escapeHtml(bodyText.slice(0, 220))}</div>` : ""}
        ${renderLohnDrawerChips(fields)}
        <div class="lohn-drawer-item-meta">${escapeHtml([m.period, workerLine].filter(Boolean).join(" · ") || "—")}</div>
        <div class="lohn-drawer-actions">
          <a class="primary" href="${escapeAttr(href)}" target="_blank" rel="noopener" data-lohn-drawer="open-msg-stammdaten" data-id="${escapeAttr(id)}">${escapeHtml(t("lohn.openStammdaten") || "Bearbeiten")}</a>
          <button type="button" data-lohn-drawer="ack-msg" data-id="${escapeAttr(id)}">${escapeHtml(t("lohn.markDone") || "Erledigt")}</button>
        </div>
      </article>`);
  }

  body.innerHTML = parts.join("");
}

async function handleLohnDrawerAction(ev) {
  const el = ev.target?.closest?.("[data-lohn-drawer]");
  if (!el) return;
  const action = el.getAttribute("data-lohn-drawer");
  const id = String(el.getAttribute("data-id") || el.getAttribute("data-alert-id") || "").trim();

  const removeRow = (sel) => document.querySelector(sel)?.remove();

  if (action === "open-payslips") {
    openPayslipReviewStudio().catch((err) => toast(err?.message || "error", "error"));
    return;
  }

  if (action === "open-msg-stammdaten" && id) {
    // Ack in background so the request leaves the inbox after opening contracts
    ev.preventDefault();
    const href = el.getAttribute("href");
    removeRow(`.lohn-drawer-item[data-lohn-msg="${CSS.escape(id)}"]`);
    try {
      await api(`/api/payroll/accounting/messages/${encodeURIComponent(id)}/open`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
    } catch {
      /* still open contracts */
    }
    broadcastLohnInboxChanged();
    refreshLohnBadgeOnly().catch(() => {});
    if (href) window.open(href, "_blank", "noopener");
    if (!$("lohnDrawerBody")?.querySelector(".lohn-drawer-item")) {
      openLohnDrawer().catch(() => {});
    }
    return;
  }

  if (action === "ack-msg" && id) {
    el.disabled = true;
    removeRow(`.lohn-drawer-item[data-lohn-msg="${CSS.escape(id)}"]`);
    try {
      await api(`/api/payroll/accounting/messages/${encodeURIComponent(id)}/open`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
    } catch (e) {
      /* still open contracts */
    }
    broadcastLohnInboxChanged();
    refreshLohnBadgeOnly().catch(() => {});
    if (!$("lohnDrawerBody")?.querySelector(".lohn-drawer-item")) {
      openLohnDrawer().catch(() => {});
    }
    return;
  }

  if (action === "dismiss-alert" && id) {
    el.disabled = true;
    removeRow(`.lohn-drawer-item[data-lohn-alert="${CSS.escape(id)}"]`);
    try {
      await api(`/api/payroll/accounting/data-alerts/${encodeURIComponent(id)}/dismiss`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
    } catch {
      /* ignore */
    }
    broadcastLohnInboxChanged();
    return;
  }

  if (action === "open-stammdaten") {
    // Keep alert until contract save pushes resolved data; just open.
    return;
  }

  if ((action === "period-confirm" || action === "period-reject") && id) {
    el.disabled = true;
    const path =
      action === "period-confirm"
        ? `/api/payroll/accounting/period-requests/${encodeURIComponent(id)}/confirm`
        : `/api/payroll/accounting/period-requests/${encodeURIComponent(id)}/reject`;
    removeRow(`.lohn-drawer-item[data-lohn-period="${CSS.escape(id)}"]`);
    try {
      await api(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: action === "period-reject" ? JSON.stringify({ reason: "" }) : "{}",
      });
    } catch (e) {
      /* ignore period error — drawer will refresh */
      openLohnDrawer().catch(() => {});
      return;
    }
    broadcastLohnInboxChanged();
    if (!$("lohnDrawerBody")?.querySelector(".lohn-drawer-item")) {
      openLohnDrawer().catch(() => {});
    }
  }
}

function wireLohnDrawer() {
  $("lohnDrawerClose")?.addEventListener("click", closeLohnDrawer);
  $("lohnDrawerBackdrop")?.addEventListener("click", closeLohnDrawer);
  $("lohnDrawerRefresh")?.addEventListener("click", () => openLohnDrawer().catch(() => {}));
  $("lohnDrawerPayslips")?.addEventListener("click", () => openPayslipReviewStudio().catch(() => {}));
  $("lohnDrawerPullPayslips")?.addEventListener("click", () => pullPayslipsFromLohn().catch(() => {}));
  $("payslipStudioClose")?.addEventListener("click", () => closePayslipReviewStudio());
  $("payslipStudioBackdrop")?.addEventListener("click", () => closePayslipReviewStudio());
  $("payslipInboxTabs")?.addEventListener("pointerdown", (ev) => {
    const btn = ev.target?.closest?.("[data-payslip-inbox]");
    if (!btn) return;
    ev.preventDefault();
    ev.stopPropagation();
    switchPayslipInbox(btn.getAttribute("data-payslip-inbox")).catch((err) => toast(err?.message || "error", "error"));
  });
  $("payslipReviewStudio")?.addEventListener("click", (ev) => {
    handlePayslipStudioClick(ev).catch((err) => toast(err?.message || "error", "error"));
  });
  $("payslipReviewStudio")?.addEventListener("input", (ev) => {
    const q = ev.target?.closest?.("[data-payslip-archive-q]");
    if (!q) return;
    payslipStudioState.archiveQuery = String(q.value || "");
    renderPayslipStudioList();
  });
  $("payslipReviewStudio")?.addEventListener("change", (ev) => {
    const period = ev.target?.closest?.("[data-payslip-archive-period]");
    if (!period) return;
    payslipStudioState.archivePeriod = String(period.value || "");
    renderPayslipStudioList();
  });
  // Deep-link: ?payslipReview=1&batch_id=…
  try {
    const params = new URLSearchParams(location.search);
    if (params.get("payslipReview") === "1" || params.get("payslip_review") === "1") {
      openPayslipReviewStudio({
        batchId: params.get("batch_id") || params.get("batchId") || "",
        statementId: params.get("statement_id") || params.get("statementId") || "",
      }).catch(() => {});
    }
  } catch {
    /* ignore */
  }
  $("openLohnSystemBtn")?.addEventListener("click", () => {
    openLohnSystem().catch(() => {});
  });
  $("lohnDrawerBody")?.addEventListener("click", (ev) => {
    handleLohnDrawerAction(ev).catch(() => {});
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !$("lohnDrawer")?.classList.contains("hidden")) {
      closeLohnDrawer();
      return;
    }
    if (ev.key === "Escape" && !$("payslipSheetOverlay")?.classList.contains("hidden")) {
      closePayslipSheetOverlay();
      return;
    }
    if (ev.key === "Escape" && $("payslipReviewStudio")?.classList.contains("is-sheet-focus")) {
      $("payslipFocusExitBtn")?.click();
    }
  });
  window.addEventListener("message", (ev) => {
    if (ev.origin && ev.origin !== window.location.origin) return;
    if (ev.data?.type === "workpass-payslip-close") closePayslipSheetOverlay();
  });
  window.addEventListener("storage", (ev) => {
    if (ev.key === "workpass-lohn-inbox-bump") refreshLohnBadgeOnly().catch(() => {});
  });
  window.addEventListener("workpass-lohn-inbox-changed", () => {
    refreshLohnBadgeOnly().catch(() => {});
  });
  // Badge on Betrieb tab also opens the fast drawer
  $("lohnOpsBadge")?.closest("button")?.addEventListener("click", (ev) => {
    if (Number($("lohnOpsBadge")?.textContent || 0) > 0 && ev.detail === 1) {
      // After tab switch settles, open drawer when badge shows mail
      setTimeout(() => {
        if (Number($("lohnOpsBadge")?.textContent || 0) > 0) {
          openLohnDrawer().catch(() => {});
        }
      }, 120);
    }
  });
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
  refreshLohnBadgeOnly().catch(() => {});
}

function scheduleOverviewReload() {
  clearTimeout(scheduleOverviewReload._t);
  scheduleOverviewReload._t = setTimeout(() => loadOverview().catch(() => {}), 800);
}

function scheduleInboxReload() {
  clearTimeout(scheduleInboxReload._t);
  // Skip briefly after a local ack so a realtime echo cannot resurrect the row.
  if (Date.now() < (scheduleInboxReload._suppressUntil || 0)) return;
  scheduleInboxReload._t = setTimeout(() => {
    if (Date.now() < (scheduleInboxReload._suppressUntil || 0)) return;
    const tab = document.querySelector(".tab.active")?.dataset?.tab;
    if (tab === "inbox") loadInbox().catch(() => {});
    else refreshInboxBadgeOnly();
  }, 500);
}

function suppressInboxReload(ms = 2500) {
  scheduleInboxReload._suppressUntil = Date.now() + Math.max(500, ms);
  clearTimeout(scheduleInboxReload._t);
}

async function startAdminRealtime() {
  if (!window.SUPPIXOpsRealtime) return;
  if (adminRealtimeStop) {
    adminRealtimeStop();
    adminRealtimeStop = null;
  }
  const cid = companyIdFromQuery();
  if (!cid && getUser().role === "superadmin") return;
  window.__adminRealtimeLive = false;
  adminRealtimeStop = await window.SUPPIXOpsRealtime.start({
    companyId: cid,
    feedEl: null,
    onEvent: (evt) => {
      if (!shouldRefreshOnEvent(evt)) return;
      window.__adminRealtimeLive = true;
      const tab = document.querySelector(".tab.active")?.dataset?.tab || "overview";
      if (evt?.type === "inbox.changed") {
        scheduleInboxReload();
        // Keep Live-Lage inbox KPI fresh while on overview.
        if (tab === "overview") scheduleOverviewReload();
        return;
      }
      refreshInboxBadgeOnly();
      if (tab === "inbox") scheduleInboxReload();
      else if (tab === "overview") scheduleOverviewReload();
      else if (tab === "access") {
        clearTimeout(scheduleInboxReload._accessT);
        scheduleInboxReload._accessT = setTimeout(() => loadAccess().catch(() => {}), 800);
      } else if (tab === "operations") {
        clearTimeout(scheduleInboxReload._opsT);
        scheduleInboxReload._opsT = setTimeout(() => loadOperations().catch(() => {}), 1200);
      }
    },
  });
  window.__adminRealtimeLive = Boolean(adminRealtimeStop);
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
  audit: "tab.audit",
  copilot: "tab.copilot",
  enterprise: "tab.enterprise",
  workers: "tab.workers",
  access: "tab.access",
  mobile: "tab.mobile",
  operations: "tab.operations",
  billing: "tab.billing",
  tools: "tab.tools",
  platform: "tab.platform",
};

const COMMAND_NAV = [
  { tab: "overview", titleKey: "tab.overview", groupKey: "nav.group.start" },
  { tab: "analytics", titleKey: "tab.analytics", groupKey: "nav.group.start" },
  { tab: "inbox", titleKey: "tab.inbox", groupKey: "nav.group.start" },
  { tab: "audit", titleKey: "tab.audit", groupKey: "nav.group.start" },
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
    openLohn: true,
    titleKey: "lohn.opsLink",
    groupKey: "nav.group.ops",
    searchTerms: "lohn buchhaltung accounting workpass payroll abrechnung firma.de sso",
  },
  { tab: "billing", titleKey: "tab.billing", groupKey: "nav.group.ops", searchTerms: "rechnung invoice billing stripe zahlung abo" },
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
  {
    href: "/admin-v2/docs.html",
    titleKey: "docs.title",
    groupKey: "nav.group.ops",
    searchTerms: "dokument editor word tip tap text rich docs brief schreiben",
  },
  { tab: "tools", titleKey: "tab.tools", groupKey: "nav.group.ops" },
  { tab: "platform", titleKey: "tab.platform", groupKey: "nav.group.ops" },
  { tab: "enterprise", titleKey: "tab.enterprise", groupKey: "nav.group.enterprise" },
  { tab: "enterprise", titleKey: "common.enterpriseHub", groupKey: "nav.group.enterprise", searchTerms: "enterprise hub funktionen 16 ebenen layers katalog" },
  { legacyView: "auto", titleKey: "common.legacyDashboard", groupKey: "nav.group.ops" },
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

function notifyParentEmbedTab(tabId, extra) {
  if (!isEmbedMode() || window.self === window.top) {
    return;
  }
  try {
    window.parent.postMessage(
      {
        type: "baupass-embed-tab-change",
        tab: String(tabId || "").trim(),
        opsEmbedPage: String(extra?.opsEmbedPage || pendingOpsEmbedPage || "").trim(),
        companyId: activeCompanyId() || getUser()?.company_id || "",
      },
      window.location.origin,
    );
  } catch {
    // ignore
  }
}

function switchToTab(tabId, options) {
  const opts = options || {};
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
  try {
    const nextHash = `#${tabId}`;
    if (location.hash !== nextHash) {
      history.replaceState(null, "", `${location.pathname}${location.search}${nextHash}`);
    }
  } catch {
    /* ignore history failures */
  }
  if (tabId === "enterprise") syncEnterpriseFrame();
  if (tabId === "tools") {
    requestAnimationFrame(() => {
      refreshGeofenceMap();
      setTimeout(refreshGeofenceMap, 350);
    });
  }
  if (!opts.silent) {
    notifyParentEmbedTab(tabId);
  }
}

/** AI Operator FAB → navigate tabs / focus Einsatzplan without leaving admin-v2. */
if (!window.__baupassAiNavigateBound) {
  window.__baupassAiNavigateBound = true;
  window.addEventListener("baupass-ai-navigate", (ev) => {
    const detail = ev?.detail || {};
    const tab = String(detail.tab || "").trim();
    const goEinsatz =
      Boolean(detail.einsatzplan)
      || detail.focus === "deployment"
      || /einsatzplan|deployment/i.test(String(detail.url || ""));
    try {
      if (tab && document.querySelector(`.tab[data-tab="${tab}"]`)) {
        switchToTab(tab);
        refreshActiveTab().catch(notifyTabError);
      }
      if (goEinsatz) {
        pendingEinsatzplanFocus = true;
        if (!tryFocusEinsatzplanFromParent()) {
          switchToTab("workers");
          refreshActiveTab()
            .then(() => tryFocusEinsatzplanFromParent())
            .catch(notifyTabError);
        }
      }
    } catch (err) {
      console.warn("baupass-ai-navigate", err);
    }
  });

  // Allowlisted UI pilot: click real tab buttons when present.
  window.addEventListener("baupass-ai-ui-pilot", (ev) => {
    const detail = ev?.detail || {};
    if (detail.clicked) return;
    const tab = String(detail.tab || "").trim();
    const selector = String(detail.selector || "").trim();
    try {
      if (selector) {
        const el = document.querySelector(selector);
        if (el && typeof el.click === "function") {
          el.click();
          return;
        }
      }
      if (tab && document.querySelector(`.tab[data-tab="${tab}"]`)) {
        switchToTab(tab);
        refreshActiveTab().catch(notifyTabError);
      }
    } catch (err) {
      console.warn("baupass-ai-ui-pilot", err);
    }
  });
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
  // Refresh Lohn visibility so Schnellnavigation shows Buchhaltung when enabled.
  syncLohnOpenButton()
    .then(() => {
      if ($("commandPalette")?.classList.contains("hidden")) return;
      renderCommandPaletteList(($("commandPaletteInput")?.value || "").trim());
    })
    .catch(() => {});
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
    if (item.openLohn && !lohnOpenEnabled) {
      return false;
    }
    if (item.tab === "analytics" && !canAccessAnalyticsTab()) {
      return false;
    }
    if (item.legacyView && !isSuperadminUser()) {
      return false;
    }
    // Pförtner / office: no Arbeitsverträge — Docs-Editor bleibt nutzbar.
    if (
      (String(getUser()?.role || "").toLowerCase() === "turnstile" || isOfficeUser()) &&
      String(item.href || "").includes("contracts.html")
    ) {
      return false;
    }
    if (isOfficeUser() && (item.openLohn || item.tab === "billing" || item.tab === "audit")) {
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
      if (item.legacyView) {
        return `<li><button type="button" class="command-item${active}" data-cmd-idx="${i}"><span>${title}</span><span class="muted small">${group}</span></button></li>`;
      }
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
  const primary = [
    { tab: "enterprise", title: t("quick.enterprise.title"), desc: t("quick.enterprise.desc") },
    { tab: "workers", title: t("quick.workers.title"), desc: t("quick.workers.desc") },
    { tab: "access", title: t("quick.access.title"), desc: t("quick.access.desc") },
    { tab: "mobile", title: t("quick.mobile.title"), desc: t("quick.mobile.desc") },
    { tab: "inbox", title: t("tab.inbox"), desc: t("section.inbox.desc") },
    { tab: "billing", title: t("tab.billing"), desc: t("section.billing.desc") },
    { tab: "platform", title: t("quick.platform.title"), desc: t("quick.platform.desc") },
  ];
  const legacy = isSuperadminUser()
    ? [
        { legacy: "devices", title: t("feature.devices"), desc: t("quick.legacy.devicesDesc") },
        { legacy: "admin", title: t("feature.settings"), desc: t("quick.legacy.settingsDesc") },
      ]
    : [];
  const renderCard = (item) => {
    if (item.legacy) {
      return `<button type="button" class="feature-card" data-legacy-dashboard="${item.legacy}"><h3>${item.title}</h3><p class="muted small">${item.desc}</p></button>`;
    }
    return `<button type="button" class="feature-card" data-goto-tab="${item.tab}"><h3>${item.title}</h3><p class="muted small">${item.desc}</p></button>`;
  };
  $("quickLinks").innerHTML = `
    <div class="quick-links-primary">${primary.map(renderCard).join("")}</div>
    ${legacy.length ? `<details class="quick-links-more muted small">
      <summary>${t("quick.moreTools") || "Weitere Tools"}</summary>
      <div class="quick-links-grid">${legacy.map(renderCard).join("")}</div>
    </details>` : ""}`;
  bindLegacyDashboardLinks($("quickLinks"));
  $("quickLinks").querySelectorAll("[data-goto-tab]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      switchToTab(btn.getAttribute("data-goto-tab"));
      await refreshActiveTab();
    });
  });
}

const DEFAULT_LOHN_UI_URL = "https://workpass-lohn.up.railway.app";

function resolveLohnUiUrl(uiUrl, baseUrl) {
  const ui = String(uiUrl || "").trim();
  if (ui) return ui.replace(/\/$/, "");
  const base = String(baseUrl || "").trim().replace(/\/$/, "");
  if (base) return base;
  return DEFAULT_LOHN_UI_URL;
}

function readLohnPlatformLinkForm(form) {
  const fd = new FormData(form);
  const baseUrl = String(fd.get("baseUrl") || "").trim();
  let uiBaseUrl = String(fd.get("uiBaseUrl") || "").trim();
  if (!uiBaseUrl) {
    uiBaseUrl = resolveLohnUiUrl("", baseUrl);
    const uiInput = form.querySelector('[name="uiBaseUrl"]');
    if (uiInput) uiInput.value = uiBaseUrl;
  }
  const body = {
    enabled: String(fd.get("enabled") || "0") === "1",
    autoProvision: String(fd.get("autoProvision") || "0") === "1",
    baseUrl,
    uiBaseUrl,
    platformPublicUrl: String(fd.get("platformPublicUrl") || "").trim(),
    companyUpsertPath: String(fd.get("companyUpsertPath") || "").trim() || "/v1/company/upsert",
    hoursWebhookPath: String(fd.get("hoursWebhookPath") || "").trim() || "/hooks/suppix-hours",
    runDay: Number(fd.get("runDay") || 1) || 1,
  };
  const master = String(fd.get("masterApiKey") || "").trim();
  if (master) body.masterApiKey = master;
  return body;
}

function paintLohnWebhookStatus(host, data = {}) {
  const box = host?.querySelector("#lohnWebhookStatus");
  if (!box) return;
  const ok = data.ok === true;
  const pending = data.pending === true;
  const pillClass = pending ? "is-wait" : ok ? "is-on" : "is-off";
  const pillLabel = pending
    ? (t("lohnLink.webhookChecking") || "Prüfe…")
    : ok
      ? (t("lohnLink.webhookOk") || "Webhook OK")
      : (t("lohnLink.webhookFail") || "Webhook prüfen");
  const url = escapeHtml(String(data.url || box.dataset.webhookUrl || ""));
  const detail = escapeHtml(String(data.message || data.error || data.hint || ""));
  const lohnLast = data.lohnLastWebhook || null;
  const lohnLine = lohnLast
    ? `<p class="muted small">${t("lohnLink.lohnLastWebhook") || "Letzter Lohn-Webhook"}: ${escapeHtml(String(lohnLast.status ?? "—"))} · ${escapeHtml(String(lohnLast.at || "").slice(0, 19))} · ${escapeHtml(String(lohnLast.event || ""))}</p>`
    : "";
  box.innerHTML = `
    <div class="lohn-webhook-status-head">
      <strong>${t("lohnLink.webhookTitle") || "Webhook-Status"}</strong>
      <span class="platform-status-pill ${pillClass}">${pillLabel}</span>
    </div>
    <p class="mono small lohn-webhook-url">${url || "—"}</p>
    ${detail ? `<p class="muted small">${detail}</p>` : ""}
    ${lohnLine}
  `;
}

async function refreshLohnWebhookStatus(host, { probe = false } = {}) {
  if (!host) return;
  const form = host.querySelector("#lohnPlatformLinkForm");
  const baseUrl = String(form?.querySelector('[name="baseUrl"]')?.value || host.dataset.lohnBase || "").trim().replace(/\/$/, "");
  const webhookUrl = String(host.dataset.webhookUrl || "").trim();
  paintLohnWebhookStatus(host, { pending: true, url: webhookUrl });
  let lohnLastWebhook = null;
  if (baseUrl) {
    try {
      const health = await withTimeout(
        fetch(`${baseUrl}/health`, { cache: "no-store" }).then((r) => r.json()),
        5000,
        null,
      );
      lohnLastWebhook = health?.lastWebhook || null;
    } catch {
      /* optional */
    }
  }
  if (!probe) {
    const lastOk = lohnLastWebhook?.ok === true;
    paintLohnWebhookStatus(host, {
      ok: lastOk,
      url: webhookUrl,
      message: lastOk
        ? (t("lohnLink.webhookFromLohnOk") || "Lohn meldet letzten Webhook als erfolgreich.")
        : (t("lohnLink.webhookFromLohnHint") || "Zum Prüfen «Webhook prüfen» verwenden."),
      lohnLastWebhook,
    });
    return;
  }
  try {
    const result = await api("/api/payroll/accounting/platform-link/webhook-probe", {
      method: "POST",
      body: "{}",
    });
    paintLohnWebhookStatus(host, {
      ok: true,
      url: result.url || webhookUrl,
      message: result.message || (t("lohnLink.webhookOk") || "Webhook OK"),
      lohnLastWebhook,
    });
  } catch (e) {
    paintLohnWebhookStatus(host, {
      ok: false,
      url: e?.data?.url || webhookUrl,
      message: e?.data?.message || e.message || "webhook_probe_failed",
      error: e?.data?.error,
      lohnLastWebhook,
    });
  }
}

function bindLohnPlatformLinkPanel(host) {
  if (!host || host.dataset.bound === "1") return;
  host.dataset.bound = "1";
  const form = host.querySelector("#lohnPlatformLinkForm");
  const msg = host.querySelector("#lohnLinkMsg");
  const baseInput = form?.querySelector('[name="baseUrl"]');
  const uiInput = form?.querySelector('[name="uiBaseUrl"]');
  const syncUiFromBase = () => {
    if (!uiInput || !baseInput) return;
    const currentUi = String(uiInput.value || "").trim();
    if (currentUi && currentUi !== DEFAULT_LOHN_UI_URL) return;
    const next = resolveLohnUiUrl("", baseInput.value);
    if (next) uiInput.value = next;
  };
  baseInput?.addEventListener("change", syncUiFromBase);
  baseInput?.addEventListener("blur", syncUiFromBase);
  form?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = readLohnPlatformLinkForm(form);
    try {
      await api("/api/payroll/accounting/platform-link", { method: "POST", body: JSON.stringify(body) });
      if (msg) msg.textContent = t("lohnLink.saved") || "Gespeichert";
      showActionToast(t("lohnLink.saved") || "Gespeichert");
      await loadPlatform();
    } catch (e) {
      if (msg) msg.textContent = e.message || "error";
      showActionToast(e.message || "error", true);
    }
  });
  host.querySelector("#lohnLinkTestBtn")?.addEventListener("click", async () => {
    try {
      const body = readLohnPlatformLinkForm(form);
      if (!body.baseUrl) throw new Error("WorkPass Lohn Basis-URL fehlt.");
      if (/suppix-ai-workpass\.com/i.test(body.baseUrl)) {
        throw new Error("Basis-URL muss die Lohn-App sein — nicht die Plattform.");
      }
      await api("/api/payroll/accounting/platform-link", { method: "POST", body: JSON.stringify(body) });
      const result = await api("/api/payroll/accounting/platform-link/test", {
        method: "POST",
        body: "{}",
      });
      const text = `${t("lohnLink.testOk") || "OK"} · ${result.status || ""} · ${result.url || result.baseUrl || ""}`;
      if (msg) msg.textContent = text;
      showActionToast(text);
      await refreshLohnWebhookStatus(host, { probe: false });
    } catch (e) {
      const detail = e?.data?.message || e.message || "error";
      if (msg) msg.textContent = detail;
      showActionToast(detail, true);
    }
  });
  host.querySelector("#lohnWebhookProbeBtn")?.addEventListener("click", () => {
    refreshLohnWebhookStatus(host, { probe: true }).catch(() => {});
  });
  refreshLohnWebhookStatus(host, { probe: false }).catch(() => {});
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
      <a href="/enterprise-hub.html?v=20260527e" class="btn-link platform-banner-enterprise-link">${t("platform.banner.enterpriseLink")}</a>
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
          workStartTime: String(fd.get("workStartTime") || "").trim().slice(0, 5),
          workEndTime: String(fd.get("workEndTime") || "").trim().slice(0, 5),
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
    const startVal = String(cfg.workStartTime || "").trim().slice(0, 5);
    const endVal = String(cfg.workEndTime || "").trim().slice(0, 5);
    host.innerHTML = `
      <h3>${t("workTimes.title")}</h3>
      <p class="muted small">${t("workTimes.hint")}</p>
      <p id="workTimesFeedback" class="work-times-feedback hidden" role="status"></p>
      <form id="workTimesForm" class="tool-form access-settings-form">
        <fieldset class="access-settings-fieldset">
          <legend>${t("workTimes.hoursLegend")}</legend>
          <p class="muted small">${t("workTimes.hoursHint")}</p>
          <label>${t("workTimes.start")}
            <input name="workStartTime" type="time" value="${escapeAttr(startVal)}" />
          </label>
          <label>${t("workTimes.end")}
            <input name="workEndTime" type="time" value="${escapeAttr(endVal)}" />
          </label>
        </fieldset>
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
  "autoSuggestPendingLeave",
  "autoSuggestDocsReview",
  "autoSuggestMissingExpected",
  "autoSuggestOpenSecurity",
  "autoDailyOpsDigest",
  "autoWorkerMorningPush",
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
  autoSuggestPendingLeave: "autopilot.suggestLeave",
  autoSuggestDocsReview: "autopilot.suggestDocsReview",
  autoSuggestMissingExpected: "autopilot.suggestMissing",
  autoSuggestOpenSecurity: "autopilot.suggestSecurityOpen",
  autoDailyOpsDigest: "autopilot.dailyDigest",
  autoWorkerMorningPush: "autopilot.workerMorningPush",
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
  $("deploymentCompanyHours")?.addEventListener("click", async () => {
    const q = companyQuery();
    const { year, month } = deploymentMonthParts();
    try {
      const res = await api(`/api/workforce/deployment-plan/apply-company-hours${q}`, {
        method: "POST",
        body: JSON.stringify({
          workerId: deploymentModalWorkerId,
          year,
          month,
          onlyEmpty: true,
        }),
      });
      await reloadDeploymentPlan();
      const n = Number(res.appliedDays ?? res.saved ?? 0);
      showActionToast(t("deployment.companyHoursOk", { n }), false);
    } catch (e) {
      const msg = String(e.message || "");
      showActionToast(
        msg.includes("company_work_window_unset") ? t("deployment.companyHoursUnset") : msg || t("common.error"),
        true,
      );
    }
  });
  $("deploymentRotation")?.addEventListener("click", async () => {
    const raw = prompt(
      "Orte (kommagetrennt), z.B.\nBerlin Mitte, Alexanderplatz, Potsdam",
      "Berlin Mitte, Alexanderplatz, Potsdam",
    );
    if (!raw) return;
    const locations = raw.split(",").map((s) => s.trim()).filter(Boolean);
    const useHours = confirm(t("deployment.rotationUseHours"));
    const q = companyQuery();
    const { year, month } = deploymentMonthParts();
    await api(`/api/workforce/deployment-plan/rotation${q}`, {
      method: "POST",
      body: JSON.stringify({
        workerId: deploymentModalWorkerId,
        year,
        month,
        locations,
        skipWeekends: true,
        useCompanyHours: useHours,
      }),
    });
    await reloadDeploymentPlan();
    showActionToast(t("deployment.rotation") + " ✓", false);
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
      await api(`/api/platform/autopilot/run${q}`, { method: "POST", body: "{}" });
      showActionToast(t("autopilot.ran"), false);
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
  const gen = (loadPlatform._gen = (loadPlatform._gen || 0) + 1);
  const hasContent = Boolean(panel?.querySelector("#lohnPlatformLinkPanel, .platform-studio, .platform-panel-grid"));
  // Avoid wiping the WorkPass Lohn form on every parent sync / lang no-op remount.
  if (!hasContent) {
    panel.innerHTML = `
    <p class="muted">${t("common.loading")}</p>
    <div class="platform-panel-grid platform-loading-skel" aria-hidden="true">
      <div class="panel-block platform-skel-card"><span class="skel-bar"></span><span class="skel-bar short"></span></div>
      <div class="panel-block platform-skel-card"><span class="skel-bar"></span><span class="skel-bar short"></span></div>
      <div class="panel-block platform-skel-card"><span class="skel-bar"></span><span class="skel-bar short"></span></div>
    </div>`;
  }
  const cid = activeCompanyId();
  try {
    const [caps, ready, health, setup] = await Promise.all([
      apiSoft("/api/platform/capabilities", {}, 5000),
      withTimeout(fetch("/api/health/ready").then((r) => r.json()).catch(() => ({ ready: false })), 4000, { ready: false }),
      withTimeout(fetch("/api/health").then((r) => r.json()).catch(() => ({})), 4000, {}),
      apiSoft("/api/platform/setup-status", null, 5000),
    ]);
    if (gen !== loadPlatform._gen) return;
    const dbEarly = setup?.database || {};
    const bgEarly = setup?.backgroundJobs || health.checks?.backgroundJobs || {};
    if (!hasContent) {
    panel.innerHTML = `
      <p class="admin-superadmin-banner">${t("platform.superadminOnly")}</p>
      <div class="platform-setup-banner ${dbEarly.loginReady === false ? "warn" : "ok"}">
        <strong>${t("platform.dbHealth")}</strong>
        <p class="muted small">${dbEarly.loginReady === false ? t("platform.dbNotReady") : (dbEarly.loginReady === true ? t("platform.dbReady") : (t("platform.dbStatusUnknown") || "Status wird geladen…"))}
        · ${t("platform.globalMaturity")}: <strong>${caps.maturityScore ?? "—"}/100</strong>
        · ${t("platform.readiness")}: ${statusBadge(ready.ready)}</p>
      </div>
      <div class="platform-panel-grid">
        <div class="panel-block">
          <h3>${t("platform.infrastructure")}</h3>
          <p>${t("platform.runtime")}: <strong>${caps.dataLayer?.runtime || "—"}</strong>
            · Redis: ${statusBadge(caps.dataLayer?.redisConfigured)}
            · ${t("platform.rqWorkers")}: <strong>${bgEarly.workers?.active ?? health.checks?.workers?.active ?? "—"}</strong></p>
        </div>
        <div class="panel-block platform-skel-card"><p class="muted small">${t("common.loading")}</p><span class="skel-bar"></span></div>
        <div class="panel-block platform-skel-card"><p class="muted small">${t("common.loading")}</p><span class="skel-bar"></span></div>
      </div>`;
    }

    // Cap each call — one slow SQLite/wallet/billing probe used to freeze this panel 1–2 min.
    const softMs = 7000;
    const [ent, aiSt, wallet, pushSt, mobileDist, autopilot, backups, billingOv, revenue, lohnLinkPayload] = await Promise.all([
      apiSoft("/api/platform/entitlements", null, softMs),
      apiSoft("/api/ai/status", { configured: false }, softMs),
      apiSoft("/api/admin/wallet/runtime-status", null, softMs),
      apiSoft("/api/platform/push/status", null, softMs),
      apiSoft("/api/v2/mobile/distribution", null, softMs),
      cid
        ? apiSoft(`/api/platform/autopilot/settings${companyQuery()}`, { settings: {} }, softMs)
        : Promise.resolve({ settings: {} }),
      apiSoft("/api/admin/database/backups", { items: [] }, softMs),
      cid ? withTimeout(fetchBillingOverviewCached(cid), softMs, null) : Promise.resolve(null),
      apiSoft("/api/v2/billing/revenue-metrics", null, softMs),
      apiSoft("/api/payroll/accounting/platform-link", null, softMs),
    ]);
    if (gen !== loadPlatform._gen) return;
    const lohnLink = lohnLinkPayload?.link || {};
    const lohnEnabled = Boolean(lohnLink.enabled || lohnLink.configured);
    const lohnBase = String(lohnLink.baseUrl || lohnLink.base_url || "").trim();
    const lohnUi = String(lohnLink.uiBaseUrl || lohnLink.ui_base_url || "").trim();
    const lohnAuto = lohnLink.autoProvision ?? lohnLink.auto_provision;
    const lohnAutoOn = lohnAuto === true || Number(lohnAuto) === 1 || lohnAuto == null;
    const lohnUiResolved = resolveLohnUiUrl(lohnUi, lohnBase);
    const lohnStatusClass = lohnEnabled && lohnBase ? "is-on" : "is-off";
    const lohnStatusLabel = lohnEnabled && lohnBase
      ? (t("lohnLink.connected") || "Verbunden")
      : (t("lohnLink.off") || "Nicht verbunden");
    const webhookUrl = String(
      lohnLink.platformWebhookUrl
      || lohnLinkPayload?.link?.platformWebhookUrl
      || `${String(lohnLink.platformPublicUrl || lohnLink.platform_public_url || "https://suppix-ai-workpass.com").replace(/\/$/, "")}/api/workpass/webhooks/accounting`,
    ).trim();
    const lohnPanel = `<section class="platform-section platform-section--lohn" id="lohnPlatformLinkPanel" data-lohn-base="${escapeAttr(lohnBase || DEFAULT_LOHN_UI_URL)}" data-webhook-url="${escapeAttr(webhookUrl)}">
        <header class="platform-section-head">
          <div>
            <p class="platform-section-kicker">${t("lohnLink.kicker") || "Buchhaltung"}</p>
            <h3>${t("lohnLink.title") || "WorkPass Lohn — Plattform-Link"}</h3>
            <p class="muted small">${t("lohnLink.hint") || "Einmalige Verbindung zur Buchhaltungs-App. Firmen danach einzeln in Einstellungen aktivieren."}</p>
          </div>
          <span class="platform-status-pill ${lohnStatusClass}">${lohnStatusLabel}</span>
        </header>
        ${lohnEnabled && lohnBase ? `<p class="lohn-link-endpoint mono">✓ ${escapeHtml(lohnBase)}</p>` : ""}
        <div id="lohnWebhookStatus" class="lohn-webhook-status" data-webhook-url="${escapeAttr(webhookUrl)}"></div>
        <form id="lohnPlatformLinkForm" class="lohn-link-form">
          <div class="lohn-link-grid lohn-link-grid--toggles">
            <label class="lohn-field">
              <span>${t("lohnLink.enabled") || "Aktiv"}</span>
              <select name="enabled"><option value="1" ${lohnEnabled ? "selected" : ""}>Ja</option><option value="0" ${!lohnEnabled ? "selected" : ""}>Nein</option></select>
            </label>
            <label class="lohn-field">
              <span>${t("lohnLink.auto") || "Auto-Provision"}</span>
              <select name="autoProvision"><option value="1" ${lohnAutoOn ? "selected" : ""}>Ja</option><option value="0" ${!lohnAutoOn ? "selected" : ""}>Nein</option></select>
            </label>
            <label class="lohn-field">
              <span>${t("lohnLink.runDay") || "Export-Tag"}</span>
              <input name="runDay" type="number" min="1" max="28" value="${escapeAttr(String(lohnLink.runDay || lohnLink.default_run_day || 1))}" />
            </label>
          </div>
          <div class="lohn-link-grid">
            <label class="lohn-field lohn-field--full">
              <span>${t("lohnLink.baseUrl") || "API-Basis-URL"}</span>
              <input name="baseUrl" type="url" value="${escapeAttr(lohnBase || DEFAULT_LOHN_UI_URL)}" placeholder="${escapeAttr(DEFAULT_LOHN_UI_URL)}" />
            </label>
            <label class="lohn-field lohn-field--full">
              <span>${t("lohnLink.uiBaseUrl") || "UI-URL (Browser)"}</span>
              <input name="uiBaseUrl" type="url" value="${escapeAttr(lohnUiResolved)}" placeholder="${escapeAttr(DEFAULT_LOHN_UI_URL)}" />
            </label>
            <p class="muted small lohn-field--full">${t("lohnLink.uiHint") || "API-URL oft nicht im Browser öffenbar (X-WorkPass-Key). Hier die Web-App-URL für «Buchhaltung öffnen»."}</p>
            <label class="lohn-field lohn-field--full">
              <span>${t("lohnLink.masterKey") || "Master-API-Key"}</span>
              <input name="masterApiKey" type="password" placeholder="${lohnLink.masterApiKeySet ? escapeAttr(lohnLink.masterApiKeyPreview || "***") : ""}" autocomplete="new-password" />
            </label>
          </div>
          <details class="lohn-advanced">
            <summary>${t("lohnLink.advanced") || "Erweiterte Einstellungen"}</summary>
            <div class="lohn-link-grid">
              <label class="lohn-field lohn-field--full">
                <span>${t("lohnLink.platformUrl") || "Plattform-URL"}</span>
                <input name="platformPublicUrl" type="url" value="${escapeAttr(String(lohnLink.platformPublicUrl || lohnLink.platform_public_url || "https://suppix-ai-workpass.com"))}" />
              </label>
              <label class="lohn-field">
                <span>${t("lohnLink.upsertPath") || "Upsert-Pfad"}</span>
                <input name="companyUpsertPath" value="${escapeAttr(String(lohnLink.companyUpsertPath || lohnLink.company_upsert_path || "/v1/company/upsert"))}" />
              </label>
              <label class="lohn-field">
                <span>${t("lohnLink.webhookPath") || "Webhook-Pfad (Lohn)"}</span>
                <input name="hoursWebhookPath" value="${escapeAttr(String(lohnLink.hoursWebhookPath || lohnLink.hours_webhook_path || "/hooks/suppix-hours"))}" />
              </label>
              <p class="muted small lohn-field--full">${t("lohnLink.advancedHint") || "Technische Pfade nur ändern, wenn die Lohn-API andere Endpunkte nutzt."}</p>
            </div>
          </details>
          <div class="lohn-link-actions">
            <button type="submit">${t("lohnLink.save") || "Speichern"}</button>
            <button type="button" class="ghost" id="lohnLinkTestBtn">${t("lohnLink.test") || "Verbindung testen"}</button>
            <button type="button" class="ghost" id="lohnWebhookProbeBtn">${t("lohnLink.webhookProbe") || "Webhook prüfen"}</button>
            <p id="lohnLinkMsg" class="muted small lohn-link-msg"></p>
          </div>
        </form>
      </section>`;
    const ap = autopilot?.settings || {};
    const autopilotToggles = AUTOPILOT_KEYS.map(
      (key) => `
        <label class="autopilot-toggle">
          <input type="checkbox" data-autopilot-key="${key}" ${ap[key] !== false ? "checked" : ""} />
          <span>${t(AUTOPILOT_LABEL_KEYS[key])}</span>
        </label>`,
    ).join("");
    const db = setup?.database || {};
    const dbKnown = typeof db.loginReady === "boolean";
    const dbBannerClass = db.loginReady === false ? "warn" : (dbKnown ? "ok" : "info");
    const dbReadyLabel = db.loginReady === false
      ? t("platform.dbNotReady")
      : (db.loginReady === true ? t("platform.dbReady") : (t("platform.dbStatusUnknown") || "Status unbekannt — Setup-API prüfen"));
    const dbFileLabel = !dbKnown
      ? (t("platform.dbStatusUnknown") || "Status unbekannt")
      : (db.sqliteFileExists ? t("platform.dbFileOk") : t("platform.dbFileMissing"));
    const dbPersistLabel = !dbKnown
      ? ""
      : (db.persistent ? t("platform.dbPersistent") : t("platform.dbEphemeral"));
    const maturityScore = caps.maturityScore ?? "—";
    const maturityLevel = caps.maturityLevel || "";
    const runtimeLabel = caps.dataLayer?.runtime || ready.checks?.database?.backend || "—";
    const redisOk = !!(caps.dataLayer?.redisConfigured || ready.checks?.redis?.ok);
    const readyOk = !!ready.ready;
    const workersActive = bgEarly.workers?.active ?? health.checks?.workers?.active ?? ready.checks?.queues?.stats?.default?.started ?? "—";
    const setupLines = (setup?.readyScore?.missing || [])
      .map((m) => `<li class="miss">○ ${escapeHtml(m)}</li>`)
      .join("");
    const setupOk = setup
      ? `<div class="panel-block">
          <h3>${t("platform.setupTitle") || "Setup"}</h3>
          <p>${t("platform.setup.railway")}: <strong>${setup.readyScore?.percent ?? 0}%</strong></p>
          <ul class="setup-checklist">${setupLines || `<li class="ok">${t("platform.setup.allOk")}</li>`}</ul>
        </div>`
      : "";
    const steps = (caps.nextSteps || [])
      .map((s) => `<li>${s}</li>`)
      .join("");
    const attendance = caps.attendance || {};
    const attRows = Object.entries(attendance)
      .map(([k, v]) => `<tr><td>${k}</td><td>${statusBadge(!!v)}</td></tr>`)
      .join("");
    const bgJobs = setup?.backgroundJobs || health.checks?.backgroundJobs || {};
    const bgJobRows = Object.entries(bgJobs.jobs || {})
      .map(([name, snap]) => {
        const ok = snap?.ok === true || snap?.status === "ok";
        const fails = Number(snap?.consecutiveFailures || 0);
        const last = snap?.lastRunAt ? String(snap.lastRunAt).slice(0, 19) : "—";
        return `<tr><td>${escapeHtml(name)}</td><td>${last}</td><td>${statusBadge(ok)}${fails >= 3 ? ` <span class="badge badge-warn">${fails}×</span>` : ""}</td></tr>`;
      })
      .join("");
    const bgDegraded = (bgJobs.degraded || []).length
      ? `<p class="muted small warn">${escapeHtml((bgJobs.degraded || []).join(", "))}</p>`
      : "";
    const backupRows = (backups?.items || [])
      .slice(0, 8)
      .map((b) => {
        const sha = String(b.sha256 || "").slice(0, 10);
        const integ = b.integrityCheck === "ok" ? "✓" : escapeHtml(String(b.integrityCheck || "—"));
        const off = b.offsiteUploaded ? "☁" : "—";
        const sizeKb = Math.round(Number(b.sizeBytes || 0) / 1024);
        return `<tr>
          <td class="mono small">${escapeHtml(b.filename || "")}</td>
          <td>${escapeHtml(String(b.createdAt || "").slice(0, 19))}</td>
          <td>${sizeKb} KB</td>
          <td class="mono small">${escapeHtml(sha)}</td>
          <td>${integ}</td>
          <td>${off}</td>
          <td>
            <button type="button" class="ghost small" data-backup-verify="${escapeHtml(b.filename || "")}">Verify</button>
            <a class="ghost small" href="/api/admin/database/backups/download?filename=${encodeURIComponent(b.filename || "")}">Download</a>
          </td>
        </tr>`;
      })
      .join("");
    const channels = Array.isArray(setup?.channels) ? setup.channels : [];
    const channelsHtml = channels.length
      ? `<div class="panel-block">
        <h3>${t("platform.channelsTitle")}</h3>
        <p class="muted small">${t("platform.channelsHint")}</p>
        <div class="billing-summary-grid">
          ${channels
            .map((ch) => {
              const ok = !!ch.ok;
              const pill = ok ? "is-ok" : ch.severity === "warn" ? "is-warn" : "is-off";
              return `<div class="metric"><span>${escapeHtml(ch.label || ch.id || "")}</span>
                <strong><span class="integration-status-pill ${pill}">${ok ? t("badge.ready") : t("badge.needsSetup")}</span></strong>
                ${ch.hint && !ok ? `<small class="muted">${escapeHtml(ch.hint)}</small>` : ""}</div>`;
            })
            .join("")}
        </div>
      </div>`
      : "";
    panel.innerHTML = `
      <div class="platform-studio">
        <header class="platform-studio-hero">
          <div>
            <p class="platform-section-kicker">${t("tab.platform") || "Plattform"}</p>
            <h2 class="platform-studio-title">${t("section.platform.hint") || "Globale Plattform-Bereitschaft"}</h2>
            <p class="admin-superadmin-banner platform-studio-note">${t("platform.superadminOnly")}</p>
          </div>
          <div class="platform-kpi-strip">
            <div class="platform-kpi">
              <span>${t("platform.globalMaturity")}</span>
              <strong>${maturityScore}<small>/100</small></strong>
              <em>${escapeHtml(maturityLevel)}</em>
            </div>
            <div class="platform-kpi">
              <span>${t("platform.dbHealth")}</span>
              <strong>${escapeHtml(runtimeLabel)}</strong>
              <em>${escapeHtml(dbReadyLabel)}</em>
            </div>
            <div class="platform-kpi">
              <span>${t("platform.readiness")}</span>
              <strong>${readyOk ? t("badge.ready") : t("badge.needsSetup")}</strong>
              <em>Redis ${redisOk ? "OK" : (readyOk ? "OK*" : "—")} · RQ ${escapeHtml(String(workersActive))}</em>
            </div>
          </div>
        </header>

        <div class="platform-setup-banner ${dbBannerClass}">
          <strong>${t("platform.dbHealth")}</strong>
          <p class="muted small">${escapeHtml(dbReadyLabel)}
          · ${escapeHtml(dbFileLabel)}
          ${dbPersistLabel ? ` · ${escapeHtml(dbPersistLabel)}` : ""}
          ${db.sqliteSizeBytes ? ` · ${Math.round(Number(db.sqliteSizeBytes) / 1024)} KB` : ""}
          ${readyOk && !dbKnown ? ` · health/ready: OK (${escapeHtml(String(ready.checks?.database?.path || ""))})` : ""}</p>
          ${(db.railwayHints || []).map((h) => `<p class="muted small">${escapeHtml(h)}</p>`).join("")}
          ${!setup ? `<p class="muted small">${t("platform.setupStatusFailed") || "Setup-Status API nicht geladen — /api/health/ready ist maßgeblich."}</p>` : ""}
        </div>

        ${lohnPanel}

        <section class="platform-section">
          <header class="platform-section-head">
            <div>
              <p class="platform-section-kicker">${t("platform.secOps") || "Betrieb"}</p>
              <h3>${t("platform.secOpsTitle") || "Automatisierung & Abrechnung"}</h3>
            </div>
          </header>
          <div class="platform-panel-grid">
            ${channelsHtml}
            ${
              revenue
                ? `<div class="panel-block">
              <h3>${t("billing.revenueTitle")}</h3>
              <p class="muted small">${t("billing.revenueHint")}</p>
              <div class="billing-summary-grid">
                <div class="metric"><span>${t("billing.paidInvoices")}</span><strong>${revenue.paidInvoices?.count ?? 0} · ${formatEur(revenue.paidInvoices?.totalEur)}</strong></div>
                <div class="metric"><span>${t("billing.openInvoices")}</span><strong>${revenue.openInvoices?.count ?? 0} · ${formatEur(revenue.openInvoices?.totalEur)}</strong></div>
                <div class="metric"><span>${t("billing.mrrEstimate")}</span><strong>${formatEur(revenue.estimatedMrrNetEur)}</strong></div>
              </div>
              <button type="button" class="ghost" data-goto-tab="billing">${t("billing.openInvoicesUi")}</button>
            </div>`
                : ""
            }
            ${cid && billingOv ? renderBillingSummaryHtml(billingOv) : ""}
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
            ${setupOk}
          </div>
        </section>

        <section class="platform-section">
          <header class="platform-section-head">
            <div>
              <p class="platform-section-kicker">${t("platform.secInfra") || "Infrastruktur"}</p>
              <h3>${t("platform.infrastructure")}</h3>
            </div>
          </header>
          <div class="platform-panel-grid">
            <div class="panel-block">
              <h3>${t("platform.globalMaturity")} <span class="badge badge-ok">${maturityScore}/100</span></h3>
              <p class="muted">${escapeHtml(maturityLevel)}</p>
              ${steps ? `<ul class="muted small">${steps}</ul>` : ""}
            </div>
            <div class="panel-block">
              <h3>${t("platform.infrastructure")}</h3>
              <p>${t("platform.runtime")}: <strong>${escapeHtml(runtimeLabel)}</strong> · Redis: ${statusBadge(redisOk)} · Queues: ${statusBadge(caps.dataLayer?.taskQueuesReady)}</p>
              <p>${t("platform.readiness")}: ${statusBadge(readyOk)} · Redis: ${health.checks?.redis?.status || health.redis?.status || ready.checks?.redis?.status || "—"} · ${t("platform.rqWorkers")}: <strong>${escapeHtml(String(workersActive))}</strong></p>
              ${
                bgJobRows
                  ? `<h4 class="muted small">${t("platform.backgroundJobs")}</h4><div class="table-wrap"><table><thead><tr><th>Job</th><th>${t("common.lastRun") || "Last run"}</th><th>${t("common.status") || "Status"}</th></tr></thead><tbody>${bgJobRows}</tbody></table></div>${bgDegraded}`
                  : ""
              }
              <details class="platform-tech-details muted small">
                <summary>${t("platform.techDetails") || "Technische Details"}</summary>
                <p>DB: ${db.sqliteFileExists ? t("platform.dbFileOk") : t("platform.dbFileMissing")} · ${db.persistent ? t("platform.dbPersistent") : t("platform.dbEphemeral")}</p>
                <p class="mono">${escapeHtml(caps.dataLayer?.sqlitePath || ready.checks?.database?.path || "—")}</p>
              </details>
            </div>
            <div class="panel-block" id="backupPanel">
              <h3>${t("platform.backupsTitle") || "Database backups"}</h3>
              <p class="muted small">Retention: ${escapeHtml(String(backups?.retentionDays ?? "—"))} days · Dir: <span class="mono">${escapeHtml(String(backups?.backupDir || ""))}</span></p>
              <div class="autopilot-actions" style="margin-bottom:0.75rem">
                <button type="button" id="backupNowBtn">Backup now</button>
                <button type="button" class="ghost" id="backupVerifyLatestBtn">Verify latest</button>
              </div>
              <div class="table-wrap"><table>
                <thead><tr><th>File</th><th>Created</th><th>Size</th><th>SHA</th><th>Integrity</th><th>Offsite</th><th></th></tr></thead>
                <tbody>${backupRows || `<tr><td colspan="7" class="muted">No backups yet</td></tr>`}</tbody>
              </table></div>
              <pre id="backupActionLog" class="ai-answer muted small"></pre>
            </div>
            <div class="panel-block">
              <h3>${t("platform.attendanceCaps")}</h3>
              <div class="table-wrap"><table><tbody>${attRows}</tbody></table></div>
            </div>
          </div>
        </section>

        <section class="platform-section">
          <header class="platform-section-head">
            <div>
              <p class="platform-section-kicker">${t("platform.secServices") || "Dienste"}</p>
              <h3>${t("platform.secServicesTitle") || "Plan, KI, App & Wallet"}</h3>
            </div>
          </header>
          <div class="platform-panel-grid">
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
              <p class="muted small">${wallet?.ok || wallet?.wallet?.ok ? statusBadge(true) : statusBadge(false)}
                Apple: ${wallet?.wallet?.runtime?.apple?.ok ? statusBadge(true) : statusBadge(false)}
                · Google: ${wallet?.wallet?.runtime?.google?.ok ? statusBadge(true) : statusBadge(false)}
              </p>
              ${
                wallet?.wallet?.runtime?.apple?.error
                  ? `<p class="muted small">${escapeHtml(String(wallet.wallet.runtime.apple.error).slice(0, 160))}</p>`
                  : ""
              }
              ${
                wallet?.wallet?.runtime?.google?.error
                  ? `<p class="muted small">${escapeHtml(String(wallet.wallet.runtime.google.error).slice(0, 160))}</p>`
                  : ""
              }
            </div>
          </div>
        </section>

        <div class="link-row platform-studio-links">
          <a href="/api/health/ready" target="_blank" rel="noopener">health/ready</a>
          <a href="/enterprise-hub.html?v=20260528a">${t("common.enterpriseHub")}</a>
          <a href="/index.html" class="legacy-dashboard-link" data-legacy-dashboard="auto">${t("common.legacyDashboard")}</a>
        </div>
      </div>
    `;
    await loadCompanyWorkTimesForm(cid);
    bindAutopilotPanel($("autopilotPanel"), ap);
    bindLegacyDashboardLinks(panel);
    bindLohnPlatformLinkPanel($("lohnPlatformLinkPanel"));
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

    const backupLog = $("backupActionLog");
    const setBackupLog = (msg) => {
      if (backupLog) backupLog.textContent = msg;
    };
    $("backupNowBtn")?.addEventListener("click", async () => {
      setBackupLog(t("common.loading"));
      try {
        const res = await api("/api/admin/database/backup", { method: "POST", body: "{}" });
        setBackupLog(
          `OK ${res.backupPath || res.path || ""} · sha=${String(res.sha256 || "").slice(0, 12)} · offsite=${res.offsite?.uploaded ? "yes" : "no"}`,
        );
        await loadPlatform();
      } catch (e) {
        setBackupLog(e.message || "backup_failed");
      }
    });
    $("backupVerifyLatestBtn")?.addEventListener("click", async () => {
      setBackupLog(t("common.loading"));
      try {
        const res = await api("/api/admin/database/backups/verify", { method: "POST", body: "{}" });
        setBackupLog(`verify ok=${res.ok} integrity=${res.integrityCheck || "—"}`);
      } catch (e) {
        setBackupLog(e.message || "verify_failed");
      }
    });
    panel.querySelectorAll("[data-backup-verify]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const filename = btn.getAttribute("data-backup-verify");
        setBackupLog(t("common.loading"));
        try {
          const res = await api("/api/admin/database/backups/verify", {
            method: "POST",
            body: JSON.stringify({ filename }),
          });
          setBackupLog(`${filename}: ok=${res.ok} integrity=${res.integrityCheck || "—"}`);
        } catch (e) {
          setBackupLog(e.message || "verify_failed");
        }
      });
    });
    bindLegacyDashboardLinks(panel);
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
      stat = t("ops.stat.openAlerts", {
        n: v.openAlertCount ?? (v.openAlerts || []).length,
      });
      lines.push(
        t("ops.stat.newFindings", { n: v.newFindings ?? 0 }),
        t("ops.stat.analysisActive"),
      );
      tone = (v.openAlertCount ?? (v.openAlerts || []).length) > 0 ? "warn" : "ok";
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
        lines.push(t("ops.stat.inside", { n: v.insideCount ?? "—" }));
      }
      break;
    case "6_camera_ai":
      stat = t("ops.stat.events24h", { n: v.events24h ?? 0 });
      lines.push(
        t("ops.stat.camerasOnline", {
          n: v.camerasOnline ?? 0,
          total: v.camerasTotal ?? 0,
        }),
      );
      break;
    case "7_iot":
      stat = t("ops.stat.devices", { n: (v.devices || []).length || Number(v.deviceCount || 0) });
      lines.push(t("ops.stat.registryReady"));
      break;
    case "8_command_center":
      stat = t("ops.stat.totalWorkers", { n: v.totalOnSite ?? v.workersOnSite ?? 0 });
      lines.push(
        t("ops.stat.emergencies", { n: v.openEmergencies ?? v.activeEmergencies ?? 0 }),
        t("ops.stat.securityOpenCount", { n: v.openSecurity ?? 0 }),
      );
      break;
    case "9_autonomous":
      stat = t("ops.stat.rules", { n: v.enabledRules ?? v.ruleCount ?? 0 });
      lines.push(t("ops.stat.automationHint"));
      break;
    case "10_workforce_graph":
      stat = t("ops.stat.nodes", { n: (v.nodes || v.workers || []).length });
      lines.push(t("ops.stat.edges", { n: (v.edges || []).length }));
      break;
    case "11_identity":
      stat = t("ops.stat.identityHub");
      lines.push(t("ops.stat.identityHint"));
      break;
    case "12_copilot":
      stat = v.configured ? t("ops.stat.aiReady") : t("ops.stat.notConfigured");
      lines.push(v.configured ? t("ops.stat.copilotReadyHint") : t("ops.stat.copilotSetupHint"));
      tone = v.configured ? "ok" : "warn";
      break;
    default:
      stat = t("ops.stat.active");
      break;
  }
  return { stat, lines: lines.filter(Boolean).slice(0, 3), tone };
}

function renderOpsLayerCard(key, title, icon, val) {
  const sum = summarizeOpsLayer(key, val);
  const num = String(key).replace(/\D/g, "").padStart(2, "0") || "—";
  const meta = sum.lines.map((l) => `<li>${escapeHtml(l)}</li>`).join("");
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

function formatOpsLayerDetailRows(val, layerKey = "") {
  const rows = [];
  const push = (label, value) => {
    if (value === undefined || value === null || value === "") return;
    rows.push(
      `<tr><th scope="row">${escapeHtml(label)}</th><td>${escapeHtml(String(value))}</td></tr>`,
    );
  };
  const v = val && typeof val === "object" ? val : {};
  const sum = v.summary && typeof v.summary === "object" ? v.summary : {};

  // Curated human fields only — never dump raw keys / API paths for end users.
  push(t("ops.detail.status"), v.status && !/^[a-z0-9_]+$/i.test(String(v.status)) ? v.status : null);
  push(t("ops.detail.date"), v.date);
  if (sum.workersOnSite != null) push(t("ops.detail.onSite"), sum.workersOnSite);
  if (sum.gatesActive != null) push(t("ops.detail.gatesActive"), sum.gatesActive);
  if (sum.hazardZones != null) push(t("ops.detail.hazardZones"), sum.hazardZones);
  if (v.openAlertCount != null || Array.isArray(v.openAlerts)) {
    push(t("ops.detail.openSecurity"), v.openAlertCount ?? v.openAlerts.length);
  }
  if (v.newFindings != null) push(t("ops.detail.newFindings"), v.newFindings);
  if (v.averageScore != null) push(t("ops.detail.reputationAvg"), Number(v.averageScore).toFixed(1));
  if (Array.isArray(v.leaderboard) || Array.isArray(v.workers)) {
    push(t("ops.detail.rankedWorkers"), (v.leaderboard || v.workers || []).length);
  }
  if (v.active != null) push(t("ops.detail.emergencyActive"), yn(v.active));
  if (v.insideCount != null) push(t("ops.detail.insideCount"), v.insideCount);
  if (v.events24h != null || v.totalEvents24h != null) {
    push(t("ops.detail.cameraEvents"), v.events24h ?? v.totalEvents24h);
  }
  if (v.camerasTotal != null) {
    push(t("ops.detail.cameras"), `${v.camerasOnline ?? 0} / ${v.camerasTotal}`);
  }
  if (v.totalOnSite != null) push(t("ops.detail.onSite"), v.totalOnSite);
  if (v.openEmergencies != null) push(t("ops.detail.openEmergencies"), v.openEmergencies);
  if (v.openSecurity != null) push(t("ops.detail.openSecurityShort"), v.openSecurity);
  if (v.enabledRules != null || v.ruleCount != null) {
    push(t("ops.detail.automationRules"), v.enabledRules ?? v.ruleCount);
  }
  if (Array.isArray(v.devices) || v.deviceCount != null) {
    push(t("ops.detail.iotDevices"), Array.isArray(v.devices) ? v.devices.length : v.deviceCount);
  }
  if (Array.isArray(v.busiestGates)) {
    push(t("ops.detail.topGates"), v.busiestGates.length);
    v.busiestGates.slice(0, 3).forEach((g, i) => {
      const name = typeof g === "string" ? g : g.name || g.gate || g.id;
      if (name && !/^[a-z0-9_-]+$/i.test(String(name))) {
        push(`${t("ops.detail.gate")} ${i + 1}`, name);
      } else if (name) {
        push(`${t("ops.detail.gate")} ${i + 1}`, name);
      }
    });
  }
  if (Array.isArray(v.nodes)) push(t("ops.detail.graphNodes"), v.nodes.length);
  if (Array.isArray(v.edges)) push(t("ops.detail.graphEdges"), v.edges.length);
  if (v.configured != null) {
    push(t("ops.detail.copilot"), v.configured ? t("ops.stat.aiReady") : t("ops.stat.notConfigured"));
  }
  if (layerKey === "13_daily_brief" || v.headlines || v.priorities) {
    const headlines = v.headlines || v.priorities || [];
    if (Array.isArray(headlines) && headlines.length) {
      push(t("ops.detail.briefItems"), headlines.length);
    }
  }

  if (isSuperadminUser() && (v.endpoint || v.api)) {
    push(t("ops.detail.api"), v.endpoint || v.api);
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
  $("opsLayerModalBody").innerHTML = formatOpsLayerDetailRows(val, layerKey);
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
  if (isSupportReadOnlySession() || window.WorkPassStorage?.isSupportAssistQuietMode?.()) {
    const tok = String(WP?.readSessionToken?.() || wpGet(TOKEN_KEY) || "").trim();
    if (!tok) return;
  }
  const token = String(WP?.readSessionToken?.() || wpGet(TOKEN_KEY) || "").trim();
  if (!token) return;
  const send = () => {
    try {
      frame.contentWindow?.postMessage(
        {
          type: "baupass-sync-token",
          token,
          companyId: companyId || activeCompanyId() || "",
          lang: getLang(),
          user: getUser(),
        },
        window.location.origin,
      );
    } catch {
      // iframe not ready
    }
  };
  if (frame.dataset.opsTokenSyncBound !== "1") {
    frame.dataset.opsTokenSyncBound = "1";
    frame.addEventListener("load", send);
  }
  send();
  window.setTimeout(send, 350);
  window.setTimeout(send, 1200);
  window.setTimeout(send, 2800);
}

function initOpsEmbedTabs(panel, companyId) {
  const frame = panel?.querySelector("#opsEmbedFrame");
  if (!frame) return;
  if (panel.dataset.opsEmbedTabsBound === "1" && frame.dataset.opsCid === String(companyId || "")) {
    syncTokenToOpsEmbedFrame(frame, companyId);
    return;
  }
  panel.dataset.opsEmbedTabsBound = "1";
  frame.dataset.opsCid = String(companyId || "");
  const ensureFrameSrc = (page) => {
    const target = page || frame.getAttribute("data-ops-page") || "/ops-live-map.html";
    const nextSrc = buildOpsEmbedUrl(target, companyId);
    frame.setAttribute("data-ops-page", target);
    // Avoid reload loop when soft-updating the ops shell.
    if (frame.getAttribute("src") !== nextSrc) {
      frame.src = nextSrc;
    }
    syncTokenToOpsEmbedFrame(frame, companyId);
  };
  panel.querySelectorAll(".ops-embed-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const page = btn.getAttribute("data-ops-page");
      if (!page || btn.disabled) return;
      panel.querySelectorAll(".ops-embed-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      frame.title = btn.textContent || "";
      ensureFrameSrc(page);
      notifyParentEmbedTab("operations", { opsEmbedPage: page });
    });
  });
  // Lazy: load first embed after idle / click — saves bandwidth on slow links.
  const lazyLoad = () => {
    if (frame.getAttribute("data-loaded") === "1") return;
    frame.setAttribute("data-loaded", "1");
    const active = panel.querySelector(".ops-embed-tab.active");
    ensureFrameSrc(active?.getAttribute("data-ops-page") || "/ops-live-map.html");
  };
  if (pendingOpsEmbedPage) {
    lazyLoad();
  } else if (typeof requestIdleCallback === "function") {
    requestIdleCallback(() => lazyLoad(), { timeout: 2500 });
  } else {
    setTimeout(lazyLoad, 1200);
  }
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

  /* Vertical wheel scrolls the page; horizontal (or Shift+wheel) moves the card row */
  track.addEventListener(
    "wheel",
    (e) => {
      const dx = Math.abs(e.deltaX);
      const dy = Math.abs(e.deltaY);
      const scroller = document.querySelector(".app-content");
      if (dx <= dy && !e.shiftKey) {
        if (scroller) {
          scroller.scrollTop += e.deltaY;
          e.preventDefault();
          e.stopPropagation();
        }
        return;
      }
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

let _legacyFeaturesCache = { companyId: "", at: 0, value: null };

async function loadLegacyFeatures(companyId) {
  if (getUser().role === "superadmin" && !String(companyId || "").trim()) return null;
  const cid = String(companyId || "").trim();
  const now = Date.now();
  if (_legacyFeaturesCache.companyId === cid && now - _legacyFeaturesCache.at < 45_000) {
    return _legacyFeaturesCache.value;
  }
  const q = cid ? `?company_id=${encodeURIComponent(cid)}` : "";
  const ent = await api(`/api/platform/entitlements${q}`).catch(() => null);
  if (ent?.plan) window.__baupassActivePlan = normalizePlanUi(ent.plan);
  const value = ent?.legacyFeatures || {};
  _legacyFeaturesCache = { companyId: cid, at: now, value };
  return value;
}

function aiCommandCenterHref(extraParams = {}) {
  const params = new URLSearchParams();
  const cid = (companyQuery() || "").replace("?company_id=", "");
  if (cid) params.set("company_id", cid);
  Object.entries(extraParams || {}).forEach(([k, v]) => {
    if (v != null && String(v) !== "") params.set(k, String(v));
  });
  const qs = params.toString();
  return `/ai-command-center.html${qs ? `?${qs}` : ""}`;
}

function openAiCommandCenterWithPrompt(prompt, agent = "decision") {
  const text = String(prompt || "").trim();
  try {
    if (text) {
      sessionStorage.setItem("baupass_ai_autoprompt", text);
      sessionStorage.setItem("baupass_ai_agent", String(agent || "decision"));
    }
  } catch {
    /* ignore */
  }
  const href = text
    ? aiCommandCenterHref({ agent: agent || "decision" })
    : aiCommandCenterHref();
  window.location.href = href;
}

function legacyFeatureEnabled(features, key) {
  if (features === null) return true;
  return Boolean(features[key]);
}

const PLAN_RANK_UI = { tageskarte: 0, starter: 1, professional: 2, enterprise: 3 };

function normalizePlanUi(planValue) {
  const raw = String(planValue || "").trim().toLowerCase();
  const aliases = {
    start: "starter",
    startpreis: "starter",
    starterpaket: "starter",
    pro: "professional",
    professionell: "professional",
    "enterprise packet": "enterprise",
    enterprisepacket: "enterprise",
    "enterprise paket": "enterprise",
    unternehmenspaket: "enterprise",
  };
  const plan = aliases[raw] || raw;
  if (plan in PLAN_RANK_UI) return plan;
  if (plan.includes("enterprise")) return "enterprise";
  if (plan.includes("profession") || plan === "pro") return "professional";
  if (plan.includes("start")) return "starter";
  return "starter";
}

function activeCompanyPlan() {
  if (window.__baupassActivePlan) return normalizePlanUi(window.__baupassActivePlan);
  const cid = String(activeCompanyId() || "").trim();
  if (!cid) return getUser().role === "superadmin" ? "enterprise" : "starter";
  const companies = Array.isArray(window.__baupassCompanies) ? window.__baupassCompanies : [];
  const hit = companies.find((c) => String(c?.id || "") === cid);
  return normalizePlanUi(hit?.plan || "starter");
}

function meetsMinPlan(minPlan) {
  if (getUser().role === "superadmin" && !activeCompanyId()) return true;
  const need = PLAN_RANK_UI[minPlan] ?? PLAN_RANK_UI.enterprise;
  return (PLAN_RANK_UI[activeCompanyPlan()] || 0) >= need;
}

/** Operational surfaces shown per company package. Enterprise includes all. */
const OPS_SURFACE_MIN_PLAN = {
  liveMap: "professional",
  cameras: "professional",
  security: "professional",
  physicalOs: "professional",
  foreman: "professional",
  commandCenter: "enterprise",
  aiCenter: "enterprise",
};

const OPS_SURFACE_FEATURE = {
  liveMap: "live_tracking",
  cameras: "physical_operations_os",
  security: "physical_operations_os",
  physicalOs: "physical_operations_os",
  foreman: "foreman_dashboard",
  commandCenter: "ops_command_center",
  aiCenter: "ai_assistant",
};

function opsSurfaceEnabled(key, features = null) {
  const minPlan = OPS_SURFACE_MIN_PLAN[key];
  if (!minPlan) return true;
  const featureKey = OPS_SURFACE_FEATURE[key];
  if (featureKey && features && legacyFeatureEnabled(features, featureKey)) return true;
  return meetsMinPlan(minPlan);
}

async function loadEntitlementFlags(companyId) {
  const features = await loadLegacyFeatures(companyId);
  if (features === null) {
    // Superadmin without forced company: all on. With company: use entitlements.
    if (!companyId) return { all: true, features: {} };
  }
  return { all: false, features: features || {} };
}

function entitlementOn(flags, key, minPlanFallback = "enterprise") {
  if (flags?.all) return true;
  if (flags?.features && Object.prototype.hasOwnProperty.call(flags.features, key)) {
    return Boolean(flags.features[key]);
  }
  return meetsMinPlan(minPlanFallback);
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
  const isTurnstile = String(getUser()?.role || "").toLowerCase() === "turnstile";
  const hideContracts = isTurnstile || isOfficeUser();
  host.innerHTML = [
    !hideContracts &&
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
      href: `/admin-v2/docs.html${q}`,
      icon: "✍️",
      title: t("docs.title"),
      desc: t("docs.desc"),
      cta: t("docs.open"),
      locked: false,
      upgradeLabel: "",
    }),
    !isTurnstile &&
      renderBetriebActionCard({
        href: `/admin-v2/camera-watch.html${q}`,
        icon: "📹",
        title: t("cameraWatch.title"),
        desc: t("cameraWatch.desc"),
        cta: t("cameraWatch.open"),
        locked: false,
        upgradeLabel: "",
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
  ]
    .filter(Boolean)
    .join("");
}

let _opsOverviewCache = { cid: "", at: 0, data: null };
let _inboxCountsCache = { key: "", at: 0, data: null };
let _billingOverviewCache = { key: "", at: 0, data: null };

function formatEur(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  try {
    return new Intl.NumberFormat(getLang() || "de", {
      style: "currency",
      currency: "EUR",
      maximumFractionDigits: 2,
    }).format(n);
  } catch {
    return `${n.toFixed(2)} €`;
  }
}

async function fetchInboxCountsCached(q) {
  const key = q || "_";
  if (_inboxCountsCache.key === key && Date.now() - _inboxCountsCache.at < 20_000) {
    return _inboxCountsCache.data;
  }
  // Prefer lightweight counts endpoint; fall back to full inbox only if needed.
  const data = await apiSoft(`/api/inbox/counts${q}`, null, 2500)
    .then(async (countsPayload) => {
      if (countsPayload?.counts) return countsPayload;
      return apiSoft(`/api/inbox${q}`, { counts: {} }, 3500);
    })
    .catch(() => ({ counts: {} }));
  _inboxCountsCache = { key, at: Date.now(), data };
  return data;
}

async function fetchBillingOverviewCached(cid) {
  const resolved = String(cid || activeCompanyId() || "").trim();
  if (!resolved && getUser().role === "superadmin") return null;
  const key = resolved || "_self";
  if (_billingOverviewCache.key === key && Date.now() - _billingOverviewCache.at < 60_000) {
    return _billingOverviewCache.data;
  }
  const qs = resolved && getUser().role === "superadmin"
    ? `?company_id=${encodeURIComponent(resolved)}`
    : "";
  const data = await api(`/api/v2/billing/overview${qs}`).catch(() => null);
  if (data) _billingOverviewCache = { key, at: Date.now(), data };
  return data;
}

function renderBillingSummaryHtml(overview, usage) {
  if (!overview) return "";
  const workers = overview.workers || {};
  const openInv = overview.openInvoices || {};
  const stripe = overview.stripe || {};
  const trial = overview.trial || {};
  const planLabel = resolvePlanLabel(null, overview.plan) || String(overview.plan || "—");
  const subStatus = String(stripe.subscriptionStatus || overview.status || "").trim() || "—";
  const stripeOk = !!stripe.configured;
  const openCount = Number(openInv.count || 0);
  const activeWorkers = Number(workers.active ?? workers.workerCount ?? 0);
  const totalNet = Number(workers.totalNetEur);
  const perWorker =
    Number.isFinite(totalNet) && activeWorkers > 0 ? formatEur(totalNet / activeWorkers) : "—";
  const usageBlock = usage
    ? `<p class="muted small" style="margin:0.25rem 0 0.65rem">${t("billing.usageLine", {
        activeUsers: usage.activeUsers ?? usage.active_users ?? 0,
        checkIns: usage.attendanceCheckIns ?? usage.attendance ?? 0,
        period: usage.period === "week" ? t("billing.usageWeek") : t("billing.usageDay"),
      })} · <button type="button" class="btn-link" data-goto-tab="analytics">${t("billing.openUsage")}</button></p>`
    : `<p class="muted small" style="margin:0.25rem 0 0.65rem"><button type="button" class="btn-link" data-goto-tab="analytics">${t("billing.openUsage")}</button></p>`;
  return `
    <div class="panel-block">
      <h3>${t("billing.title")}</h3>
      <p class="muted small">${t("billing.hint")}</p>
      <div class="billing-summary-grid">
        <div class="metric"><span>${t("billing.plan")}</span><strong>${escapeHtml(planLabel)}</strong></div>
        <div class="metric"><span>${t("billing.monthlyNet")}</span><strong>${formatEur(workers.totalNetEur)}</strong></div>
        <div class="metric"><span>${t("billing.workers")}</span><strong>${activeWorkers}</strong></div>
        <div class="metric"><span>${t("billing.perWorker")}</span><strong>${perWorker}</strong></div>
        <div class="metric"><span>${t("billing.openInvoices")}</span><strong style="color:${openCount > 0 ? "var(--warn-accent,#fbbf24)" : "inherit"}">${openCount} · ${formatEur(openInv.totalEur)}</strong></div>
      </div>
      <p class="muted small" style="margin:0.35rem 0 0">
        ${t("billing.status")}: <strong>${escapeHtml(subStatus)}</strong>
        · Stripe: ${stripeOk ? `<span class="integration-status-pill is-ok">${t("billing.stripeOn")}</span>` : `<span class="integration-status-pill is-off">${t("billing.stripeOff")}</span>`}
        ${trial.isTrialing ? ` · <span class="integration-status-pill is-warn">${t("billing.trialing")}</span>` : ""}
      </p>
      ${usageBlock}
      <div id="billingInvoicesTable" class="table-wrap billing-invoices-table"></div>
      <button type="button" class="ghost" data-goto-tab="billing">${t("billing.openInvoicesUi")}</button>
    </div>`;
}

function renderRecentInvoicesHtml(rows) {
  const list = Array.isArray(rows) ? rows.slice(0, 8) : [];
  if (!list.length) {
    return emptyStateHtml(t("billing.recentInvoices"), t("billing.noInvoices"));
  }
  const body = list
    .map((inv) => {
      const num = escapeHtml(inv.invoice_number || inv.invoiceNumber || inv.id || "—");
      const status = escapeHtml(inv.status || "—");
      const total = formatEur(inv.total_amount ?? inv.totalAmount);
      const paid = inv.paid_at || inv.paidAt;
      const created = escapeHtml(String(inv.created_at || inv.createdAt || "").slice(0, 10));
      const payUrl = inv.stripe_payment_link_url || inv.stripePaymentLinkUrl || "";
      const invId = encodeURIComponent(inv.id || "");
      const payCell = payUrl && !paid
        ? `<a href="${escapeHtml(payUrl)}" target="_blank" rel="noopener">${t("billing.payLink")}</a>`
        : paid
          ? `<span class="integration-status-pill is-ok">${t("billing.paid")}</span>`
          : "—";
      const pdfCell = invId
        ? `<button type="button" class="btn-link" data-invoice-pdf="${invId}">${t("billing.pdf")}</button>`
        : "—";
      return `<tr><td>${num}</td><td>${created}</td><td>${status}</td><td>${total}</td><td>${payCell}</td><td>${pdfCell}</td></tr>`;
    })
    .join("");
  return `<table><thead><tr>
    <th>${t("billing.colNumber")}</th><th>${t("billing.colDate")}</th>
    <th>${t("billing.colStatus")}</th><th>${t("billing.colTotal")}</th><th></th><th></th>
  </tr></thead><tbody>${body}</tbody></table>`;
}

async function downloadInvoicePdf(invoiceId) {
  const token = wpGet(TOKEN_KEY) || "";
  const res = await fetch(`${apiBase()}/api/invoices/${encodeURIComponent(invoiceId)}/document.pdf`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.message || err.error || `PDF ${res.status}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 120_000);
}

async function loadBillingSummaryPanel(cid) {
  const panel = $("billingSummaryPanel");
  if (!panel) return;
  if (!cid && getUser().role === "superadmin") {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }
  panel.classList.remove("hidden");
  panel.innerHTML = `<div class="panel-block"><p class="muted small">${t("common.loading")}</p></div>`;
  const qs = cid && getUser().role === "superadmin" ? `?company_id=${encodeURIComponent(cid)}` : "";
  const usageQs = qs ? `${qs}&period=day` : "?period=day";
  const [overview, usage] = await Promise.all([
    fetchBillingOverviewCached(cid),
    (isSupportReadOnlySession() || window.WorkPassStorage?.isSupportAssistQuietMode?.())
      ? Promise.resolve(null)
      : api(`/api/v2/admin/usage-stats${usageQs}`).catch(() => null),
  ]);
  if (!overview) {
    panel.innerHTML = `<div class="panel-block">${emptyStateHtml(t("billing.title"), t("billing.loadError"))}</div>`;
    return;
  }
  panel.innerHTML = renderBillingSummaryHtml(overview, usage);
  bindLegacyDashboardLinks(panel);
  panel.querySelectorAll("[data-goto-tab]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      switchToTab(btn.getAttribute("data-goto-tab"));
      await refreshActiveTab().catch(notifyTabError);
    });
  });
  const invoices = await api(`/api/invoices${qs}`).catch(() => []);
  const tableHost = panel.querySelector("#billingInvoicesTable");
  if (tableHost) {
    tableHost.innerHTML = renderRecentInvoicesHtml(invoices);
    tableHost.querySelectorAll("[data-invoice-pdf]").forEach((btn) => {
      btn.addEventListener("click", () => {
        downloadInvoicePdf(btn.getAttribute("data-invoice-pdf")).catch((e) =>
          showActionToast(e.message || String(e), true),
        );
      });
    });
  }
}

let _billingTabInvoices = [];
let _billingTabSelectedId = "";

function invoiceStatusNorm(inv) {
  return String(inv?.status || "").toLowerCase();
}

function invoiceIsPaid(inv) {
  return !!(inv?.paid_at || inv?.paidAt) || invoiceStatusNorm(inv) === "bezahlt";
}

function invoiceMatchesFilter(inv, q, statusFilter) {
  const hay = `${inv.invoice_number || ""} ${inv.company_name || ""} ${inv.recipient_email || ""} ${inv.status || ""}`.toLowerCase();
  if (q && !hay.includes(q)) return false;
  if (!statusFilter) return true;
  const st = invoiceStatusNorm(inv);
  const paid = invoiceIsPaid(inv);
  if (statusFilter === "bezahlt") return paid || st === "bezahlt";
  if (statusFilter === "offen") return !paid && !["storniert", "cancelled", "bezahlt"].includes(st);
  if (statusFilter === "überfällig") return !paid && (st.includes("überfäll") || st.includes("overdue") || st === "ueberfaellig");
  if (statusFilter === "storniert") return st.includes("storn") || st === "cancelled";
  return st.includes(statusFilter);
}

function renderBillingInvoicesTable(rows) {
  if (!rows.length) {
    return emptyStateHtml(t("section.billing.title"), t("section.billing.empty"));
  }
  const showCompany = getUser().role === "superadmin";
  const head = `<tr>
    <th>${t("billing.colNumber")}</th>
    ${showCompany ? `<th>${t("section.billing.colCompany")}</th>` : ""}
    <th>${t("billing.colDate")}</th>
    <th>${t("billing.colStatus")}</th>
    <th>${t("billing.colTotal")}</th>
    <th>${t("section.billing.actions")}</th>
  </tr>`;
  const body = rows
    .map((inv) => {
      const id = escapeHtml(inv.id || "");
      const num = escapeHtml(inv.invoice_number || inv.invoiceNumber || inv.id || "—");
      const created = escapeHtml(String(inv.created_at || inv.createdAt || "").slice(0, 10));
      const status = escapeHtml(inv.status || "—");
      const total = formatEur(inv.total_amount ?? inv.totalAmount);
      const company = escapeHtml(inv.company_name || inv.companyName || "—");
      const active = inv.id === _billingTabSelectedId ? " active" : "";
      return `<tr class="billing-inv-row${active}" data-invoice-id="${id}" tabindex="0">
        <td>${num}</td>
        ${showCompany ? `<td>${company}</td>` : ""}
        <td>${created}</td>
        <td>${status}</td>
        <td>${total}</td>
        <td><button type="button" class="btn-link" data-invoice-pdf="${id}">${t("billing.pdf")}</button></td>
      </tr>`;
    })
    .join("");
  return `<table class="data-table"><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

function renderBillingInvoiceDetail(inv) {
  if (!inv) {
    return `<p class="muted small">${t("section.billing.selectHint")}</p>`;
  }
  const paid = invoiceIsPaid(inv);
  const payUrl = inv.stripe_payment_link_url || inv.stripePaymentLinkUrl || "";
  const isSa = getUser().role === "superadmin";
  const st = invoiceStatusNorm(inv);
  const actions = [
    `<button type="button" class="ghost" data-inv-action="pdf">${t("billing.pdf")}</button>`,
    payUrl
      ? `<a class="ghost" href="${escapeHtml(payUrl)}" target="_blank" rel="noopener">${t("section.billing.payLinkOpen")}</a>`
      : `<button type="button" class="ghost" data-inv-action="paylink">${t("section.billing.payLinkCreate")}</button>`,
  ];
  if (isSa && !paid) {
    actions.push(`<button type="button" class="primary" data-inv-action="markpaid">${t("section.billing.markPaid")}</button>`);
  }
  if (isSa && st === "send_failed") {
    actions.push(`<button type="button" class="ghost" data-inv-action="retry">${t("section.billing.retrySend")}</button>`);
  }
  return `
    <h3>${t("section.billing.detailTitle")}</h3>
    <dl class="billing-detail-dl">
      <dt>${t("billing.colNumber")}</dt><dd>${escapeHtml(inv.invoice_number || inv.id || "—")}</dd>
      <dt>${t("section.billing.colCompany")}</dt><dd>${escapeHtml(inv.company_name || "—")}</dd>
      <dt>${t("section.billing.colEmail")}</dt><dd>${escapeHtml(inv.recipient_email || "—")}</dd>
      <dt>${t("billing.colStatus")}</dt><dd>${escapeHtml(inv.status || "—")}</dd>
      <dt>${t("billing.colTotal")}</dt><dd>${formatEur(inv.total_amount ?? inv.totalAmount)}</dd>
      <dt>${t("billing.colDate")}</dt><dd>${escapeHtml(String(inv.invoice_date || inv.created_at || "").slice(0, 10))}</dd>
      <dt>${t("section.billing.dueDate")}</dt><dd>${escapeHtml(String(inv.due_date || "").slice(0, 10) || "—")}</dd>
    </dl>
    <p class="muted small">${escapeHtml(inv.description || "")}</p>
    <div class="billing-detail-actions">${actions.join("")}</div>
  `;
}

async function loadBillingTab() {
  const cid = (wpGet(COMPANY_KEY) || "").trim();
  const summaryHost = $("billingTabSummary");
  const listHost = $("billingInvoicesList");
  const detailHost = $("billingInvoiceDetail");
  const createPanel = $("billingCreatePanel");
  if (!listHost) return;

  if (createPanel) {
    createPanel.classList.toggle("hidden", getUser().role !== "superadmin" || !cid);
  }

  if (summaryHost) {
    summaryHost.innerHTML = `<p class="muted small">${t("common.loading")}</p>`;
    const usageQs =
      cid && getUser().role === "superadmin"
        ? `?company_id=${encodeURIComponent(cid)}&period=day`
        : "?period=day";
    const [overview, usage] = await Promise.all([
      fetchBillingOverviewCached(cid).catch(() => null),
      (isSupportReadOnlySession() || window.WorkPassStorage?.isSupportAssistQuietMode?.())
        ? Promise.resolve(null)
        : api(`/api/v2/admin/usage-stats${usageQs}`).catch(() => null),
    ]);
    if (!overview) {
      summaryHost.innerHTML = emptyStateHtml(t("billing.title"), t("billing.loadError"));
    } else {
      summaryHost.innerHTML = renderBillingSummaryHtml(overview, usage);
      // Inside the billing tab, drop the nested "open invoices" CTA / legacy links.
      summaryHost
        .querySelectorAll("[data-goto-tab='billing'], [data-legacy-dashboard], #billingInvoicesTable")
        .forEach((el) => el.remove());
      summaryHost.querySelectorAll("[data-goto-tab]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          switchToTab(btn.getAttribute("data-goto-tab"));
          await refreshActiveTab().catch(notifyTabError);
        });
      });
    }
  }

  listHost.innerHTML = `<p class="muted small">${t("common.loading")}</p>`;
  const qs = new URLSearchParams();
  if (cid && getUser().role === "superadmin") qs.set("company_id", cid);
  const q = ($("billingInvoiceQ")?.value || "").trim();
  if (q) qs.set("q", q);
  const path = `/api/invoices${qs.toString() ? `?${qs}` : ""}`;
  const invoices = await api(path).catch((e) => {
    showActionToast(e.message || t("billing.loadError"), true);
    return [];
  });
  _billingTabInvoices = Array.isArray(invoices) ? invoices : [];
  const statusFilter = ($("billingInvoiceStatus")?.value || "").trim();
  const filtered = _billingTabInvoices.filter((inv) => invoiceMatchesFilter(inv, q.toLowerCase(), statusFilter));
  if (_billingTabSelectedId && !filtered.some((r) => r.id === _billingTabSelectedId)) {
    _billingTabSelectedId = filtered[0]?.id || "";
  }
  listHost.innerHTML = renderBillingInvoicesTable(filtered);
  listHost.querySelectorAll("[data-invoice-pdf]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      downloadInvoicePdf(btn.getAttribute("data-invoice-pdf")).catch((e) =>
        showActionToast(e.message || String(e), true),
      );
    });
  });
  listHost.querySelectorAll("[data-invoice-id]").forEach((row) => {
    const open = () => {
      _billingTabSelectedId = row.getAttribute("data-invoice-id") || "";
      const inv = _billingTabInvoices.find((r) => r.id === _billingTabSelectedId);
      if (detailHost) {
        detailHost.classList.remove("hidden");
        detailHost.innerHTML = renderBillingInvoiceDetail(inv);
        bindBillingDetailActions(detailHost, inv);
      }
      listHost.querySelectorAll(".billing-inv-row").forEach((r) => {
        r.classList.toggle("active", r.getAttribute("data-invoice-id") === _billingTabSelectedId);
      });
    };
    row.addEventListener("click", open);
    row.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        open();
      }
    });
  });
  if (detailHost) {
    const inv = _billingTabInvoices.find((r) => r.id === _billingTabSelectedId) || null;
    detailHost.classList.toggle("hidden", !inv);
    detailHost.innerHTML = renderBillingInvoiceDetail(inv);
    if (inv) bindBillingDetailActions(detailHost, inv);
  }
  bindBillingTabFormsOnce();
}

function bindBillingDetailActions(host, inv) {
  if (!host || !inv) return;
  host.querySelectorAll("[data-inv-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const action = btn.getAttribute("data-inv-action");
      try {
        if (action === "pdf") {
          await downloadInvoicePdf(inv.id);
        } else if (action === "paylink") {
          const res = await api(`/api/v2/billing/invoices/${encodeURIComponent(inv.id)}/payment-link`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: "{}",
          });
          const url = res.url || res.paymentUrl || res.stripe_payment_link_url || "";
          if (url) window.open(url, "_blank", "noopener");
          showActionToast(t("section.billing.linkCreated"));
          await loadBillingTab();
        } else if (action === "markpaid") {
          await api(`/api/invoices/${encodeURIComponent(inv.id)}/pay`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
          });
          showActionToast(t("section.billing.markedPaid"));
          await loadBillingTab();
        } else if (action === "retry") {
          await api(`/api/invoices/${encodeURIComponent(inv.id)}/retry-send`, { method: "POST" });
          showActionToast(t("section.billing.createOk"));
          await loadBillingTab();
        }
      } catch (e) {
        showActionToast(e.message || e.data?.message || e.data?.error || String(e), true);
      }
    });
  });
}

function bindBillingTabFormsOnce() {
  const filter = $("billingInvoiceFilterForm");
  if (filter && filter.dataset.bound !== "1") {
    filter.dataset.bound = "1";
    filter.addEventListener("submit", (ev) => {
      ev.preventDefault();
      loadBillingTab().catch(notifyTabError);
    });
  }
  const createForm = $("billingCreateForm");
  if (createForm && createForm.dataset.bound !== "1") {
    createForm.dataset.bound = "1";
    createForm.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const cid = (wpGet(COMPANY_KEY) || "").trim();
      const msg = $("billingCreateMsg");
      if (!cid) {
        showActionToast(t("common.selectCompany"), true);
        return;
      }
      const email = ($("billingCreateEmail")?.value || "").trim();
      const number = ($("billingCreateNumber")?.value || "").trim();
      const net = Number($("billingCreateNet")?.value || 0);
      const desc = ($("billingCreateDesc")?.value || "").trim() || "SUPPIX Abo";
      const due = ($("billingCreateDue")?.value || "").trim();
      const period = new Date().toISOString().slice(0, 7);
      const renderedHtml = `<html><body><h1>Rechnung</h1><p>${escapeHtml(desc)}</p><p>Netto: ${net.toFixed(2)} EUR</p></body></html>`;
      try {
        if (msg) msg.textContent = t("common.loading");
        await api("/api/invoices/send", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            companyId: cid,
            recipientEmail: email,
            invoiceNumber: number || undefined,
            netAmount: net,
            vatRate: 19,
            description: desc,
            invoicePeriod: period,
            dueDate: due || undefined,
            renderedHtml,
          }),
        });
        if (msg) msg.textContent = t("section.billing.createOk");
        showActionToast(t("section.billing.createOk"));
        createForm.reset();
        _billingOverviewCache = { key: "", at: 0, data: null };
        await loadBillingTab();
      } catch (e) {
        const err = e.message || e.data?.message || e.data?.error || t("section.billing.createFail");
        if (msg) msg.textContent = err;
        showActionToast(err, true);
      }
    });
  }
}



function renderOperationsShell(panel, { cid, q, layers, rtLabel, chatThreads, features, mapEager }) {
  // Soft update: keep Ops iframe alive (full remount was killing Ops-Zentrale mid-load).
  const existingFrame = panel?.querySelector("#opsEmbedFrame");
  if (existingFrame && panel.dataset.opsCid === String(cid) && panel.querySelector(".ops-panel")) {
    window.__opsLayersCache = layers;
    const track = panel.querySelector(".ops-carousel-track");
    if (track) {
      track.innerHTML = getOpsLayerOrder()
        .map(([key, title, icon]) => renderOpsLayerCard(key, title, icon, layers[key]))
        .join("") || `<p class="muted small">${t("common.loading")}</p>`;
      initOpsCarousel($("opsCarousel"));
      initOpsLayerCards($("opsCarousel"));
    }
    const head = panel.querySelector(".ops-panel-head h3");
    if (head) {
      head.innerHTML = `${t("ops.physicalOs")} <span class="badge badge-ok">${t("ops.layersBadge")}</span> ${rtLabel || ""}`;
    }
    syncTokenToOpsEmbedFrame(existingFrame, cid);
    return;
  }
  panel.dataset.opsEmbedTabsBound = "";

  const cards = getOpsLayerOrder()
    .map(([key, title, icon]) => renderOpsLayerCard(key, title, icon, layers[key]))
    .join("");
  const isTurnstile = String(getUser()?.role || "").toLowerCase() === "turnstile";
  const contractsCard = isTurnstile || isOfficeUser()
    ? ""
    : renderBetriebActionCard({
        href: `/admin-v2/contracts.html${q}`,
        icon: "📄",
        title: t("contracts.open"),
        desc: t("contracts.desc"),
        cta: t("contracts.open"),
        locked: !legacyFeatureEnabled(features, "employment_contracts"),
        upgradeLabel: t("contracts.upgrade"),
      });
  const docsCard = renderBetriebActionCard({
    href: `/admin-v2/docs.html${q}`,
    icon: "✍️",
    title: t("docs.open"),
    desc: t("docs.desc"),
    cta: t("docs.open"),
    locked: false,
    upgradeLabel: "",
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
  const canLiveMap = opsSurfaceEnabled("liveMap", features);
  const canCmdCenter = opsSurfaceEnabled("commandCenter", features);
  const canAi = opsSurfaceEnabled("aiCenter", features);
  const canPhysicalOs = opsSurfaceEnabled("physicalOs", features);
  const defaultOpsPage = canLiveMap
    ? "/ops-live-map.html"
    : canCmdCenter
      ? "/ops-command-center.html"
      : canAi
        ? "/ai-command-center.html"
        : "/enterprise-hub.html";
  const mapSrc = mapEager && canLiveMap && !isSupportReadOnlySession() && !window.WorkPassStorage?.isSupportAssistQuietMode?.()
    ? `/ops-live-map.html${q ? `${q}&embed=1` : `?company_id=${encodeURIComponent(cid)}&embed=1`}`
    : mapEager && canCmdCenter && !isSupportReadOnlySession() && !window.WorkPassStorage?.isSupportAssistQuietMode?.()
      ? `/ops-command-center.html${q ? `${q}&embed=1` : `?company_id=${encodeURIComponent(cid)}&embed=1`}`
      : "about:blank";
  panel.dataset.opsCid = String(cid || "");
  const upgradeHint = (need) =>
    `<span class="muted small"> · ${escapeHtml(t("platform.upgradeRequired", { plan: need }) || `Upgrade: ${need}`)}</span>`;
  panel.innerHTML = `
      <div class="panel-block ops-panel">
        <div class="ops-panel-head">
          <h3>${t("ops.physicalOs")} <span class="badge badge-ok">${t("ops.layersBadge")}</span> ${rtLabel || ""}</h3>
          <p class="muted small">${t("ops.company", { id: cid })}${canPhysicalOs ? "" : upgradeHint("professional")}</p>
        </div>
        <div class="ops-carousel-shell" id="opsCarousel">
          <div class="ops-carousel-wrap">
            <button type="button" class="ops-carousel-btn ops-carousel-prev" aria-label="${t("ops.prevLayer")}">‹</button>
            <div class="ops-carousel-track">${canPhysicalOs ? (cards || `<p class="muted small">${t("common.loading")}</p>`) : `<p class="muted small">${escapeHtml(t("platform.upgradeRequired", { plan: "professional" }) || "Professional erforderlich")}</p>`}</div>
            <button type="button" class="ops-carousel-btn ops-carousel-next" aria-label="${t("ops.nextLayer")}">›</button>
          </div>
        </div>
        <p class="ops-carousel-hint muted small"></p>
      </div>
      <div class="link-row ops-embed-tabs" role="tablist">
        <button type="button" class="btn-link ops-embed-tab ${defaultOpsPage.includes("live-map") ? "active" : ""}" data-ops-page="/ops-live-map.html" ${canLiveMap ? "" : "disabled"}>${t("ops.liveMap")}${canLiveMap ? "" : " 🔒"}</button>
        <button type="button" class="btn-link ops-embed-tab ${defaultOpsPage.includes("ops-command") ? "active" : ""}" data-ops-page="/ops-command-center.html" ${canCmdCenter ? "" : "disabled"}>${t("ops.commandCenter")}${canCmdCenter ? "" : " 🔒"}</button>
        <button type="button" class="btn-link ops-embed-tab ${defaultOpsPage.includes("ai-command") ? "active" : ""}" data-ops-page="/ai-command-center.html" ${canAi ? "" : "disabled"}>${t("ops.aiCenter")}${canAi ? "" : " 🔒"}</button>
        <button type="button" class="btn-link ops-embed-tab" data-ops-page="/enterprise-hub.html">${t("common.enterpriseHub")}</button>
        <a href="${defaultOpsPage}${q ? `${q}&embed=1` : `?company_id=${encodeURIComponent(cid)}&embed=1`}" target="_blank" rel="noopener" class="muted small">${t("ops.openNewTab")}</a>
      </div>
      <iframe id="opsEmbedFrame" src="${mapSrc}" title="${t("ops.liveMap")}" class="ops-map-frame" loading="lazy"></iframe>
      <div class="panel-block">
        <h3>${t("contracts.title")}</h3>
        <p class="muted small">${t("contracts.desc")}</p>
        <div style="max-width:420px;">${contractsCard}</div>
      </div>
      <div class="panel-block">
        <h3>${t("docs.title")}</h3>
        <p class="muted small">${t("docs.desc")}</p>
        <div style="max-width:420px;">${docsCard}</div>
      </div>
      <div class="panel-block">
        <h3>${t("chat.title")}</h3>
        <p class="muted small">${t("chat.inboxHint", { count: chatThreads.length })}</p>
        <div style="max-width:420px;">${chatCard}</div>
      </div>
      <div class="panel-block" id="aiOperatorSettingsPanel">
        <h3>${t("aiOperator.title")}</h3>
        <p class="muted small">${t("aiOperator.desc")}</p>
        <label class="autopilot-toggle" style="display:flex;gap:0.6rem;align-items:center;margin:0.75rem 0">
          <input type="checkbox" id="aiOperatorEnabledToggle" checked />
          <span>${t("aiOperator.enabled")}</span>
        </label>
        <label class="autopilot-toggle" style="display:flex;gap:0.6rem;align-items:center;margin:0.5rem 0">
          <input type="checkbox" id="aiOperatorVoiceToggle" checked />
          <span>${t("aiOperator.voiceEnabled")}</span>
        </label>
        <label class="autopilot-toggle" style="display:flex;gap:0.6rem;align-items:center;margin:0.5rem 0">
          <input type="checkbox" id="aiOperatorWelcomeToggle" checked />
          <span>${t("aiOperator.welcomeEnabled")}</span>
        </label>
        <hr style="border:none;border-top:1px solid var(--border, #334155);margin:1rem 0" />
        <label class="autopilot-toggle" style="display:flex;gap:0.6rem;align-items:center;margin:0.5rem 0">
          <input type="checkbox" id="aiOperatorBriefingToggle" checked />
          <span>${t("aiOperator.briefingEnabled")}</span>
        </label>
        <label class="muted small" style="display:block;margin:0.5rem 0 0.25rem">${t("aiOperator.briefingHours")}</label>
        <input type="text" id="aiOperatorBriefingHours" placeholder="auto" style="max-width:220px;width:100%" />
        <p class="muted small" id="aiOperatorBriefingHoursHint">${t("aiOperator.briefingHoursHint")}</p>
        <label class="muted small" style="display:block;margin:0.5rem 0 0.25rem">${t("aiOperator.briefingTz")}</label>
        <input type="text" id="aiOperatorBriefingTz" placeholder="auto" style="max-width:220px;width:100%" />
        <label class="muted small" style="display:block;margin:0.5rem 0 0.25rem">${t("aiOperator.briefingEmail")}</label>
        <input type="text" id="aiOperatorBriefingEmail" placeholder="auto" style="max-width:320px;width:100%" />
        <p class="muted small" id="aiOperatorBriefingEmailHint">${t("aiOperator.briefingEmailHint")}</p>
        <p class="muted small" id="aiOperatorSettingsHint">${t("aiOperator.hint")}</p>
        <p class="muted small" id="aiOperatorLiveStatus" style="margin-top:0.75rem"></p>
        <div class="autopilot-actions">
          <button type="button" id="aiOperatorSaveBtn">${t("common.save")}</button>
          <button type="button" id="aiOperatorPulsePreviewBtn" class="ghost">${t("aiOperator.pulsePreview")}</button>
          <button type="button" id="aiOperatorStatusBtn" class="ghost">${t("aiOperator.statusCheck")}</button>
        </div>
        <hr style="border:none;border-top:1px solid var(--border, #334155);margin:1rem 0" />
        <h4 style="margin:0 0 0.35rem;font-size:0.95rem">${t("aiOperator.auditTitle")}</h4>
        <p class="muted small">${t("aiOperator.auditHint")}</p>
        <div id="aiOperatorAuditList" class="muted small" style="max-height:220px;overflow:auto;margin-top:0.5rem"></div>
        <button type="button" id="aiOperatorAuditRefreshBtn" class="ghost" style="margin-top:0.5rem">${t("aiOperator.auditRefresh")}</button>
      </div>
    `;
  window.__opsLayersCache = layers;
  initOpsCarousel($("opsCarousel"));
  initOpsLayerCards($("opsCarousel"));
  initOpsEmbedTabs(panel, cid);
  void bindAiOperatorSettingsPanel(cid);
  if (pendingOpsEmbedPage) {
    const page = pendingOpsEmbedPage;
    pendingOpsEmbedPage = null;
    const embedBtn = panel.querySelector(`.ops-embed-tab[data-ops-page="${page}"]`);
    embedBtn?.click();
  }
}

async function bindAiOperatorSettingsPanel(cid) {
  const host = $("aiOperatorSettingsPanel");
  if (!host || !cid) return;
  const toggle = host.querySelector("#aiOperatorEnabledToggle");
  const voiceToggle = host.querySelector("#aiOperatorVoiceToggle");
  const welcomeToggle = host.querySelector("#aiOperatorWelcomeToggle");
  const briefingToggle = host.querySelector("#aiOperatorBriefingToggle");
  const hoursInput = host.querySelector("#aiOperatorBriefingHours");
  const hoursHint = host.querySelector("#aiOperatorBriefingHoursHint");
  const tzInput = host.querySelector("#aiOperatorBriefingTz");
  const emailInput = host.querySelector("#aiOperatorBriefingEmail");
  const emailHint = host.querySelector("#aiOperatorBriefingEmailHint");
  const saveBtn = host.querySelector("#aiOperatorSaveBtn");
  const pulseBtn = host.querySelector("#aiOperatorPulsePreviewBtn");
  const statusBtn = host.querySelector("#aiOperatorStatusBtn");
  const auditBtn = host.querySelector("#aiOperatorAuditRefreshBtn");
  const liveStatus = host.querySelector("#aiOperatorLiveStatus");
  const auditList = host.querySelector("#aiOperatorAuditList");
  const hint = host.querySelector("#aiOperatorSettingsHint");
  let planAllowed = true;

  async function loadAiOperatorStatus() {
    if (!liveStatus || !planAllowed) return;
    try {
      const st = await api(`/api/ai/operator/status?company_id=${encodeURIComponent(cid)}`);
      const tts = st?.tts || {};
      const br = st?.briefing || {};
      const bits = [
        tts.configured
          ? t("aiOperator.statusTtsOk", { provider: tts.provider || "?" })
          : t("aiOperator.statusTtsMissing"),
        br.cronEnabled ? t("aiOperator.statusCronOn") : t("aiOperator.statusCronOff"),
        br.smtpConfigured ? t("aiOperator.statusSmtpOk") : t("aiOperator.statusSmtpMissing"),
        br.emailResolved
          ? t("aiOperator.statusEmail", { email: br.emailResolved })
          : t("aiOperator.statusEmailMissing"),
      ];
      liveStatus.textContent = bits.join(" · ");
    } catch {
      liveStatus.textContent = t("aiOperator.statusError");
    }
  }

  async function loadAiOperatorAudit() {
    if (!auditList || !planAllowed) return;
    auditList.textContent = t("common.loading") || "…";
    try {
      const data = await api(`/api/ai/operator/audit?company_id=${encodeURIComponent(cid)}&limit=20`);
      const events = Array.isArray(data?.events) ? data.events : [];
      if (!events.length) {
        auditList.textContent = t("aiOperator.auditEmpty");
        return;
      }
      auditList.innerHTML = events
        .map((ev) => {
          const when = String(ev.createdAt || "").replace("T", " ").slice(0, 16);
          const actor = escapeHtml(String(ev.actor || "—"));
          const msg = escapeHtml(String(ev.message || ev.eventType || ""));
          const typ = escapeHtml(String(ev.eventType || "").replace("ai.action.", ""));
          return `<div style="padding:0.35rem 0;border-bottom:1px solid var(--border,#33415533)"><strong>${typ}</strong> · ${when}<br>${msg}<br><span class="muted">${actor}</span></div>`;
        })
        .join("");
    } catch {
      auditList.textContent = t("aiOperator.auditError");
    }
  }
  try {
    const data = await api(`/api/ai/operator/settings?company_id=${encodeURIComponent(cid)}`);
    planAllowed = data?.planAllowed !== false;
    const settings = data?.settings || {};
    const companyOn = data?.companyEnabled != null
      ? Boolean(data.companyEnabled)
      : settings.enabled !== false;
    if (toggle) {
      toggle.checked = companyOn && planAllowed;
      toggle.disabled = !planAllowed;
    }
    if (voiceToggle) {
      voiceToggle.checked = settings.voiceEnabled !== false;
      voiceToggle.disabled = !planAllowed;
    }
    if (welcomeToggle) {
      welcomeToggle.checked = settings.welcomeEnabled !== false;
      welcomeToggle.disabled = !planAllowed;
    }
    if (briefingToggle) {
      briefingToggle.checked = settings.briefingEnabled !== false;
      briefingToggle.disabled = !planAllowed;
    }
    if (hoursInput) {
      const mode = String(settings.briefingHoursMode || "auto").toLowerCase();
      const hours = Array.isArray(settings.briefingHours) ? settings.briefingHours : [];
      hoursInput.value = mode === "manual" && hours.length ? hours.join(",") : "auto";
      hoursInput.disabled = !planAllowed;
      const resolved = Array.isArray(settings.briefingHoursResolved)
        ? settings.briefingHoursResolved
        : [];
      if (hoursHint) {
        hoursHint.textContent = resolved.length
          ? t("aiOperator.briefingHoursHintAuto", { hours: resolved.join(",") })
          : t("aiOperator.briefingHoursHint");
      }
    }
    if (tzInput) {
      const tz = String(settings.briefingTz || "").trim();
      tzInput.value = tz || "auto";
      tzInput.placeholder = String(settings.briefingTzResolved || "Europe/Berlin");
      tzInput.disabled = !planAllowed;
    }
    if (emailInput) {
      const emailOverride = String(settings.briefingEmail || "").trim();
      emailInput.value = emailOverride || "auto";
      emailInput.disabled = !planAllowed;
      const resolvedEmail = String(settings.briefingEmailResolved || "").trim();
      if (emailHint) {
        emailHint.textContent = resolvedEmail
          ? t("aiOperator.briefingEmailHintAuto", { email: resolvedEmail })
          : t("aiOperator.briefingEmailHint");
      }
    }
    if (saveBtn) saveBtn.disabled = !planAllowed;
    if (pulseBtn) pulseBtn.disabled = !planAllowed;
    if (statusBtn) statusBtn.disabled = !planAllowed;
    if (auditBtn) auditBtn.disabled = !planAllowed;
    if (hint) {
      hint.textContent = planAllowed
        ? t("aiOperator.hint")
        : t("aiOperator.planLocked");
    }
    if (planAllowed) {
      void loadAiOperatorStatus();
      void loadAiOperatorAudit();
    }
  } catch {
    /* keep default checked */
  }
  statusBtn?.addEventListener("click", () => {
    if (!planAllowed) return;
    void loadAiOperatorStatus();
  });
  auditBtn?.addEventListener("click", () => {
    if (!planAllowed) return;
    void loadAiOperatorAudit();
  });
  pulseBtn?.addEventListener("click", async () => {
    if (!planAllowed) return;
    pulseBtn.disabled = true;
    try {
      const data = await api(`/api/ai/operator/pulse/dispatch`, {
        method: "POST",
        body: JSON.stringify({ company_id: cid, dry_run: true, include_llm: false }),
      });
      const body = String(data?.body || "").trim();
      const urgency = data?.urgency ?? 0;
      const preview = data?.preview || {};
      const hours = Array.isArray(preview.hours) ? preview.hours.join(",") : "";
      const site = preview.sectorTerms?.termSite || "";
      const meta = [
        preview.email ? `→ ${preview.email}` : "",
        preview.lang ? `lang=${preview.lang}` : "",
        hours ? `${hours}h` : "",
        preview.tz || "",
        site ? `sector=${site}` : "",
      ].filter(Boolean).join(" · ");
      showActionToast(
        body
          ? t("aiOperator.pulsePreviewOk", { urgency })
          : t("aiOperator.pulsePreviewEmpty"),
        false
      );
      if (hint) {
        const snippet = body ? body.split("\n").slice(0, 4).join(" · ").slice(0, 160) : "";
        hint.textContent = [meta, snippet].filter(Boolean).join(" | ").slice(0, 280)
          || t("aiOperator.pulsePreviewEmpty");
      }
    } catch (err) {
      showActionToast(err?.message || t("common.error"), true);
    } finally {
      pulseBtn.disabled = !planAllowed;
    }
  });
  saveBtn?.addEventListener("click", async () => {
    if (!toggle || !planAllowed) return;
    saveBtn.disabled = true;
    try {
      const enabled = Boolean(toggle.checked);
      const voiceEnabled = voiceToggle ? Boolean(voiceToggle.checked) : true;
      const welcomeEnabled = welcomeToggle ? Boolean(welcomeToggle.checked) : true;
      const briefingEnabled = briefingToggle ? Boolean(briefingToggle.checked) : true;
      const hoursRaw = String(hoursInput?.value || "auto").trim();
      const briefingHours = !hoursRaw || /^auto/i.test(hoursRaw) ? "auto" : hoursRaw;
      const tzRaw = String(tzInput?.value || "").trim();
      const briefingTz = !tzRaw || /^auto$/i.test(tzRaw) ? "" : tzRaw;
      const emailRaw = String(emailInput?.value || "").trim();
      const briefingEmail = !emailRaw || /^auto$/i.test(emailRaw) ? "" : emailRaw;
      const data = await api(`/api/ai/operator/settings`, {
        method: "POST",
        body: JSON.stringify({
          company_id: cid,
          enabled,
          voiceEnabled,
          welcomeEnabled,
          briefingEnabled,
          briefingHours,
          briefingTz,
          briefingEmail,
        }),
      });
      const effective = data?.enabled !== false && enabled;
      try {
        localStorage.setItem(`baupass-aio-company-enabled:${cid}`, effective ? "1" : "0");
      } catch {
        /* ignore */
      }
      try {
        if (typeof BroadcastChannel !== "undefined") {
          new BroadcastChannel("baupass-aio-visibility").postMessage({
            enabled: effective,
            companyId: cid,
            voiceEnabled,
            welcomeEnabled,
          });
        }
      } catch {
        /* ignore */
      }
      window.dispatchEvent(new CustomEvent(effective ? "baupass-ai-operator-ready" : "baupass-ai-operator-hide"));
      if (window.BaupassAiOperator?.refresh) window.BaupassAiOperator.refresh();
      if (hint) hint.textContent = effective ? t("aiOperator.savedOn") : t("aiOperator.savedOff");
      showActionToast(effective ? t("aiOperator.savedOn") : t("aiOperator.savedOff"), false);
    } catch (err) {
      showActionToast(err?.message || t("common.error"), true);
    } finally {
      saveBtn.disabled = !planAllowed;
    }
  });
}

async function loadOperations() {
  const panel = $("operationsPanel");
  const cid = String(activeCompanyId() || "").trim();
  const q = cid ? `?company_id=${encodeURIComponent(cid)}` : "";
  // Hub must not block first paint of the main panel.
  void renderBetriebActionHub(cid);
  if (getUser().role === "superadmin" && !cid) {
    panel.innerHTML = `<p class="muted">${t("common.selectCompany")}</p>`;
    return;
  }

  const cacheHit =
    _opsOverviewCache.cid === cid && Date.now() - _opsOverviewCache.at < 45_000
      ? _opsOverviewCache.data
      : null;
  const featuresP = loadLegacyFeatures(cid);
  const featuresWarm = await Promise.race([
    featuresP,
    new Promise((resolve) => setTimeout(() => resolve({}), 80)),
  ]);

  if (cacheHit?.layers) {
    renderOperationsShell(panel, {
      cid,
      q,
      layers: cacheHit.layers,
      rtLabel: "",
      chatThreads: [],
      features: featuresWarm,
      mapEager: false,
    });
  } else {
    panel.innerHTML = `<p class="muted">${t("common.loading")}</p>`;
  }

  try {
    const summaryP = apiSoft(
      `/api/ops-os/summary?company_id=${encodeURIComponent(cid)}`,
      null,
      6000,
    );
    // Full overview builds many layers on SQLite — soft-timeout so UI stays usable.
    const overviewP = apiSoft(
      `/api/ops-os/overview?company_id=${encodeURIComponent(cid)}`,
      null,
      12000,
    );
    const rtP = apiSoft("/api/v1/realtime/status", null, 5000);
    const chatP = apiSoft(`/api/chat/threads${q ? q : ""}`, { threads: [] }, 5000);

    // First paint from summary (or cache), then upgrade with full overview.
    if (!cacheHit?.layers) {
      const summary = await summaryP;
      const features = await featuresP;
      if (summary?.layers) {
        renderOperationsShell(panel, {
          cid,
          q,
          layers: summary.layers,
          rtLabel: "",
          chatThreads: [],
          features,
          mapEager: false,
        });
      }
    }

    const [data, rt, chatResp, features] = await Promise.all([overviewP, rtP, chatP, featuresP]);
    if (data?.layers) {
      _opsOverviewCache = { cid, at: Date.now(), data };
    }
    const layers = data?.layers || cacheHit?.layers || (await summaryP)?.layers || {};
    const rtLabel = rt?.websocket?.enabled
      ? `<span class="badge badge-ok">${t("ops.websocketLive")}</span>`
      : rt
        ? `<span class="badge badge-warn">${t("ops.sseFallback")}</span>`
        : "";
    renderOperationsShell(panel, {
      cid,
      q,
      layers,
      rtLabel,
      chatThreads: chatResp?.threads || [],
      features,
      mapEager: false,
    });
  } catch (e) {
    if (!panel.querySelector(".ops-panel")) {
      panel.innerHTML = `<p class="error">${e.message || t("ops.loadError")}</p>`;
    }
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
  const gen = (loadTools._gen = (loadTools._gen || 0) + 1);
  const keepUi = Boolean(panel.querySelector("#geofenceMap"));
  if (!keepUi) {
    panel.innerHTML = `<p class="muted">${t("common.loading")}</p>`;
  }
  try {
    const [geofences, rules, integrations, setupLite, lockSt] = await Promise.all([
      apiSoft(`/api/geofences/admin${q}`, { geofences: [] }, 3500),
      apiSoft(`/api/automation/rules${q}`, { rules: [] }, 3500),
      apiSoft(`/api/integrations${q}`, { integrations: [] }, 3500),
      isSuperadminUser() ? apiSoft("/api/platform/setup-status", null, 3000) : Promise.resolve(null),
      apiSoft(`/api/contracts/lock-status${q}`, null, 3000),
      ensureLeafletLoaded(4500),
    ]);
    if (gen !== loadTools._gen) return;
    const features = await loadLegacyFeatures(activeCompanyId()).catch(() => ({}));
    const canZones = legacyFeatureEnabled(features, "zones") || meetsMinPlan("professional");
    const canAutomation = legacyFeatureEnabled(features, "automation_suite") || meetsMinPlan("professional");
    const gfRows = canZones ? (geofences?.geofences || []) : [];
    const ruleRows = canAutomation ? (rules?.rules || []) : [];
    const intRows = integrations?.integrations || [];
    const zonesLockedBanner = canZones
      ? ""
      : `<p class="muted small" style="margin:0.5rem 0 1rem;padding:0.65rem 0.8rem;border:1px solid var(--border,#334155);border-radius:8px;">🔒 ${escapeHtml(t("platform.upgradeRequired", { plan: "professional" }) || "Professional erforderlich für Geofencing.")}</p>`;
    const automationLockedBanner = canAutomation
      ? ""
      : `<p class="muted small" style="margin:0.5rem 0 1rem;padding:0.65rem 0.8rem;border:1px solid var(--border,#334155);border-radius:8px;">🔒 ${escapeHtml(t("platform.upgradeRequired", { plan: "professional" }) || "Professional erforderlich für Automation.")}</p>`;
    const zonesSig = gfRows
      .map((z) => `${z.id || z.site_name}|${z.latitude}|${z.longitude}|${z.radius_meters}|${z.zone_kind || ""}`)
      .join(";");
    const mapAlive = Boolean(panel.querySelector("#geofenceMap")?._baupassLeafletMap);
    if (keepUi && mapAlive && panel.dataset.toolsZonesSig === zonesSig && panel.querySelector("#geofenceTable")) {
      const zoneKindLabel = (value) => {
        const kind = String(value || "site").trim().toLowerCase();
        if (kind === "production") return t("tools.zoneKindProduction") || "Production";
        if (kind === "warehouse") return t("tools.zoneKindWarehouse") || "Warehouse";
        if (kind === "admin") return t("tools.zoneKindAdmin") || "Administration";
        if (kind === "maintenance") return t("tools.zoneKindMaintenance") || "Maintenance";
        if (kind === "lab") return t("tools.zoneKindLab") || "Laboratory";
        if (kind === "other") return t("tools.zoneKindOther") || "Other";
        return t("tools.zoneKindSite") || "Site";
      };
      renderTable($("geofenceTable"), gfRows, [
        { label: t("table.site"), render: (r) => r.site_name || "-" },
        { label: t("table.coords"), render: (r) => `${r.latitude}, ${r.longitude}` },
        { label: t("table.radius"), render: (r) => `${r.radius_meters}m` },
        { label: t("tools.zoneKind") || "Typ", render: (r) => zoneKindLabel(r.zone_kind || r.zoneKind || "site") },
        { label: t("table.active"), render: (r) => yn(r.active) },
      ]);
      if ($("automationTable")) {
        renderTable($("automationTable"), ruleRows, [
          { label: t("table.name"), render: (r) => r.name || "-" },
          { label: t("table.trigger"), render: (r) => r.trigger_event || "-" },
          { label: t("table.enabled"), render: (r) => yn(r.enabled) },
        ]);
      }
      return;
    }
    panel.dataset.toolsZonesSig = zonesSig;
    const channelPills = [];
    if (setupLite?.channels) {
      for (const ch of setupLite.channels) {
        channelPills.push({
          label: ch.label || ch.id,
          ok: !!ch.ok,
          warn: !ch.ok,
        });
      }
    } else {
      channelPills.push(
        { label: "SMS", ok: !!lockSt?.smsConfigured, warn: !lockSt?.smsConfigured },
        { label: "Stripe", ok: true, warn: false },
      );
    }
    const channelsBar = channelPills.length
      ? `<div class="panel-block"><h3>${t("tools.channelsTitle")}</h3>
          <div class="billing-summary-grid">${channelPills
            .map(
              (c) =>
                `<div class="metric"><span>${escapeHtml(c.label)}</span><strong><span class="integration-status-pill ${
                  c.ok ? "is-ok" : "is-warn"
                }">${c.ok ? t("badge.ready") : t("badge.needsSetup")}</span></strong></div>`,
            )
            .join("")}</div></div>`
      : "";
    const providers = [
      { id: "sap", label: "SAP" },
      { id: "oracle", label: "Oracle" },
      { id: "microsoft365", label: "Microsoft 365" },
      { id: "google_workspace", label: "Google Workspace" },
      { id: "payroll", label: "Payroll" },
      { id: "security_webhook", label: t("tools.securityWebhook") || "Security-Webhook" },
    ];
    panel.innerHTML = `
      ${channelsBar}
      <div class="panel-block">
        <h3>${t("tools.geofence")}</h3>
        ${zonesLockedBanner}
        <p class="muted small">${t("tools.mapHint")}</p>
        <div class="geofence-search-row">
          <input id="geofenceSearchInput" type="text" placeholder="${t("tools.searchPlacePlaceholder")}" autocomplete="street-address" />
          <button type="button" id="geofenceSearchBtn" class="btn-link">🔎 ${t("tools.searchPlaceBtn")}</button>
        </div>
        <div id="geofenceSearchResults" class="geofence-search-results" hidden></div>
        <span id="geofenceSearchStatus" class="muted small"></span>
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
          <select name="zone_kind" title="${t("tools.zoneKind") || "Zonentyp"}">
            <option value="site">${t("tools.zoneKindSite") || "Standort"}</option>
            <option value="production">${t("tools.zoneKindProduction") || "Produktion"}</option>
            <option value="warehouse">${t("tools.zoneKindWarehouse") || "Lager"}</option>
            <option value="admin">${t("tools.zoneKindAdmin") || "Verwaltung"}</option>
            <option value="maintenance">${t("tools.zoneKindMaintenance") || "Wartung"}</option>
            <option value="lab">${t("tools.zoneKindLab") || "Labor"}</option>
            <option value="other">${t("tools.zoneKindOther") || "Sonstiges"}</option>
          </select>
          <button type="submit">${t("tools.addZone")}</button>
        </form>
        <div class="table-wrap" id="geofenceTable"></div>
      </div>
      <div class="panel-block">
        <h3>${t("tools.automation")}</h3>
        ${automationLockedBanner}
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
    const zoneKindLabel = (value) => {
      const kind = String(value || "site").trim().toLowerCase();
      if (kind === "production") return t("tools.zoneKindProduction") || "Production";
      if (kind === "warehouse") return t("tools.zoneKindWarehouse") || "Warehouse";
      if (kind === "admin") return t("tools.zoneKindAdmin") || "Administration";
      if (kind === "maintenance") return t("tools.zoneKindMaintenance") || "Maintenance";
      if (kind === "lab") return t("tools.zoneKindLab") || "Laboratory";
      if (kind === "other") return t("tools.zoneKindOther") || "Other";
      return t("tools.zoneKindSite") || "Site";
    };
    renderTable($("geofenceTable"), gfRows, [
      { label: t("table.site"), render: (r) => r.site_name || "-" },
      { label: t("table.coords"), render: (r) => `${r.latitude}, ${r.longitude}` },
      { label: t("table.radius"), render: (r) => `${r.radius_meters}m` },
      { label: t("tools.zoneKind") || "Typ", render: (r) => zoneKindLabel(r.zone_kind || r.zoneKind || "site") },
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
        const raw = String(conn?.status || "").toLowerCase();
        const connected = Boolean(conn) && !["disconnected", "error", "failed", ""].includes(raw);
        const errored = ["error", "failed"].includes(raw);
        const pillClass = errored ? "is-warn" : connected ? "is-ok" : "is-off";
        const stLabel = conn
          ? (errored ? (conn.status || t("common.error")) : (conn.status || t("tools.connected") || "connected"))
          : t("tools.notConnected");
        const erpBtns = erpProviders.has(p.id)
          ? `<button type="button" class="btn-link" data-export-preview="${p.id}">${t("tools.exportPreview")}</button>
             <button type="button" class="btn-link" data-export-push="${p.id}">${t("tools.exportPush")}</button>
             <button type="button" class="btn-link" data-export-dry="${p.id}">${t("tools.exportDryRun")}</button>`
          : "";
        return `<div class="layer-pill" data-provider="${p.id}">
          <strong>${p.label}</strong>
          <div><span class="integration-status-pill ${pillClass}">${escapeHtml(stLabel)}</span></div>
          <button type="button" class="btn-link" data-connect="${p.id}">${t("tools.connect")}</button>
          <button type="button" class="btn-link" data-sync="${p.id}">${t("tools.sync")}</button>
          ${erpBtns}
        </div>`;
      })
      .join("") || `<div class="empty-state"><strong>${t("tools.integrations")}</strong>${t("common.noData")}</div>`;
    const gfForm = $("geofenceForm");
    const latIn = gfForm.querySelector('[name="latitude"]');
    const lngIn = gfForm.querySelector('[name="longitude"]');
    mountGeofenceMapWhenReady($("geofenceMap"), latIn, lngIn, gfRows).then(() => {
      refreshGeofenceMap();
    });
    const geofenceSearchInput = $("geofenceSearchInput");
    const geofenceSearchStatus = $("geofenceSearchStatus");
    const geofenceSearchResults = $("geofenceSearchResults");
    const mapEl = $("geofenceMap");
    const setGeofenceSearchResults = (items = []) => {
      if (!geofenceSearchResults) return;
      const rows = Array.isArray(items) ? items.filter((r) => Number.isFinite(Number(r?.lat)) && Number.isFinite(Number(r?.lng))) : [];
      if (!rows.length) {
        geofenceSearchResults.hidden = true;
        geofenceSearchResults.innerHTML = "";
        return;
      }
      geofenceSearchResults.hidden = false;
      geofenceSearchResults.innerHTML = rows
        .map((row, idx) => {
          const label = escapeHtml(String(row.label || "").trim() || `#${idx + 1}`);
          const lat = Number(row.lat);
          const lng = Number(row.lng);
          return `<button type="button" class="geofence-search-item" data-lat="${lat}" data-lng="${lng}" title="${label}">${label}</button>`;
        })
        .join("");
    };
    geofenceSearchResults?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button.geofence-search-item");
      if (!btn) return;
      const lat = Number(btn.getAttribute("data-lat"));
      const lng = Number(btn.getAttribute("data-lng"));
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
      if (mapEl?._baupassLeafletMap?._baupassApplyCoords) {
        mapEl._baupassLeafletMap._baupassApplyCoords(lat, lng, { center: true });
      } else {
        latIn.value = lat.toFixed(6);
        lngIn.value = lng.toFixed(6);
      }
      if (geofenceSearchStatus) {
        geofenceSearchStatus.textContent = t("tools.searchMoved").replace("{place}", btn.textContent || "");
      }
      const siteInput = gfForm.querySelector('[name="site_name"]');
      if (siteInput && !String(siteInput.value || "").trim()) {
        const firstPart = String(btn.textContent || "").split(",")[0]?.trim();
        if (firstPart) siteInput.value = firstPart;
      }
    });
    const runGeofenceSearch = async () => {
      const raw = String(geofenceSearchInput?.value || "").trim();
      const result = await searchGeofencePlace(raw, mapEl, latIn, lngIn, {
        language: getLang(),
        onStatus: (state, details = {}) => {
          if (!geofenceSearchStatus) return;
          if (state === "loading") {
            geofenceSearchStatus.textContent = t("tools.searching");
            setGeofenceSearchResults([]);
          } else if (state === "empty") {
            geofenceSearchStatus.textContent = t("tools.searchEmpty");
            setGeofenceSearchResults([]);
          } else if (state === "notFound") {
            geofenceSearchStatus.textContent = t("tools.searchNoResult");
            setGeofenceSearchResults([]);
          } else if (state === "failed") {
            geofenceSearchStatus.textContent = t("tools.searchFailed");
            setGeofenceSearchResults([]);
          }
          else if (state === "ok") geofenceSearchStatus.textContent = t("tools.searchMoved").replace("{place}", details.label || raw);
        },
      });
      if (!result) return;
      setGeofenceSearchResults(result.results || []);
      if (Array.isArray(result.results) && result.results.length > 1 && geofenceSearchStatus) {
        geofenceSearchStatus.textContent = t("tools.searchChooseResult").replace("{count}", String(result.results.length));
      }
      const siteInput = gfForm.querySelector('[name="site_name"]');
      if (siteInput && !String(siteInput.value || "").trim()) {
        const firstPart = String(result.label || "").split(",")[0]?.trim();
        if (firstPart) siteInput.value = firstPart;
      }
    };
    $("geofenceSearchBtn")?.addEventListener("click", () => {
      runGeofenceSearch();
    });
    geofenceSearchInput?.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter") return;
      ev.preventDefault();
      runGeofenceSearch();
    });
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
            zone_kind: String(fd.get("zone_kind") || "site"),
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
        if (spec.cameraWatchDeepLink) {
          const href = `/admin-v2/camera-watch.html${q}#settings`;
          window.open(href, "_blank", "noopener");
          showActionToast(t("tools.securityWebhookHint") || spec.hint || "");
          return;
        }
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
          showActionToast(summarizeIntegrationResult(res), false);
        } catch (e) {
          showActionToast(humanizeUserError(e), true);
        }
      });
    });
    panel.querySelectorAll("[data-export-preview]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const provider = btn.getAttribute("data-export-preview");
        try {
          const res = await api(`/api/integrations/${provider}/export-preview${q}`);
          showActionToast(summarizeIntegrationResult(res), false);
        } catch (e) {
          showActionToast(humanizeUserError(e), true);
        }
      });
    });
    async function runErpExport(provider, dryRun) {
      const res = await api(`/api/integrations/${provider}/export${q}`, {
        method: "POST",
        body: JSON.stringify({ dryRun: Boolean(dryRun) }),
      });
      showActionToast(summarizeIntegrationResult(res), false);
    }
    panel.querySelectorAll("[data-export-push]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const provider = btn.getAttribute("data-export-push");
        if (!window.confirm(`${provider.toUpperCase()}: ${t("tools.exportPush")}?`)) return;
        try {
          await runErpExport(provider, false);
        } catch (e) {
          showActionToast(humanizeUserError(e), true);
        }
      });
    });
    panel.querySelectorAll("[data-export-dry]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const provider = btn.getAttribute("data-export-dry");
        try {
          await runErpExport(provider, true);
        } catch (e) {
          showActionToast(humanizeUserError(e), true);
        }
      });
    });
  } catch (e) {
    panel.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

function emptyStateHtml(title, detail = "") {
  return `<div class="empty-state"><strong>${escapeHtml(title || t("common.noData"))}</strong>${
    detail ? `<p class="muted small" style="margin:0">${escapeHtml(detail)}</p>` : ""
  }</div>`;
}

function renderTable(container, rows, columns) {
  if (!rows.length) {
    container.innerHTML = emptyStateHtml(t("common.noData"), t("common.noDataHint") || "");
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
    { id: "attendance", label: `${t("inbox.filterAttendance")} (${bySource.attendance ?? 0})` },
    { id: "chat", label: `${t("inbox.filterChat")} (${bySource.chat ?? 0})` },
    { id: "leave", label: `${t("inbox.filterLeave")} (${bySource.leave ?? 0})` },
    { id: "deployment", label: `${t("inbox.filterDeployment")} (${bySource.deployment ?? 0})` },
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

function inboxSeverityLabel(severity) {
  const s = String(severity || "").trim().toLowerCase();
  if (!s) return "—";
  const key = `inbox.severity.${s}`;
  const label = t(key);
  return label && label !== key ? label : s;
}

function employerCleanText(value) {
  const s = String(value ?? "").trim();
  if (!s) return "";
  // Hide raw technical ids / snake_case codes from employers.
  if (/^[a-z][a-z0-9_.-]{2,}$/i.test(s) && (s.includes("_") || s.includes("."))) return "";
  if (/^[0-9a-f]{8,}$/i.test(s)) return "";
  return s;
}

function lageToneForCount(value, { warnAt = 1, alertAt = 3, invert = false } = {}) {
  const n = Number(value) || 0;
  if (invert) {
    if (n <= 0) return "muted";
    if (n < warnAt) return "warn";
    return "ok";
  }
  if (n <= 0) return "ok";
  if (n >= alertAt) return "alert";
  if (n >= warnAt) return "warn";
  return "ok";
}

function renderLageKpi({ id, label, value, tone = "ok", hint = "", inboxSource = null, gotoTab = null, href = null }) {
  const toneCls = ["ok", "warn", "alert", "info", "muted"].includes(tone) ? tone : "ok";
  const attrs = [`data-lage-kpi="${escapeAttr(id)}"`];
  if (inboxSource != null) {
    attrs.push(`data-goto-tab="inbox"`, `data-inbox-source="${escapeAttr(inboxSource)}"`);
  } else if (gotoTab) {
    attrs.push(`data-goto-tab="${escapeAttr(gotoTab)}"`);
  } else if (href) {
    attrs.push(`data-href="${escapeAttr(href)}"`);
  }
  return `<button type="button" class="lage-kpi is-${toneCls}" ${attrs.join(" ")} title="${escapeAttr(hint || label)}">
    <span class="lage-kpi-label">${escapeHtml(label)}</span>
    <strong class="lage-kpi-value">${escapeHtml(String(value ?? "—"))}</strong>
    <span class="lage-kpi-hint">${escapeHtml(hint || t("lage.tapOpenInbox"))}</span>
  </button>`;
}

function renderLagePersonRows(items, emptyKey) {
  const rows = (items || []).filter(Boolean);
  if (!rows.length) {
    return `<p class="lage-empty">${escapeHtml(t(emptyKey))}</p>`;
  }
  return `<ul class="lage-alert-list">${rows.join("")}</ul>`;
}

function inboxSourceLabel(source) {
  const s = String(source || "").trim().toLowerCase();
  const map = {
    security: "inbox.filterSecurity",
    attendance: "inbox.filterAttendance",
    chat: "inbox.filterChat",
    leave: "inbox.filterLeave",
    document: "inbox.filterDocument",
    system: "inbox.filterSystem",
    deployment: "inbox.filterDeployment",
  };
  const key = map[s];
  if (key) {
    const label = t(key);
    if (label && label !== key) return label;
  }
  return s || "—";
}

function inboxActionLabel(a) {
  const action = a || {};
  const type = String(action.type || "").trim().toLowerCase();
  const rawLabel = String(action.label || "").trim();
  // Technical ids look like snake_case / dotted codes — plain words stay human labels.
  const isTechnical =
    /^[a-z][a-z0-9_.-]*$/i.test(rawLabel) && (/[_.-]/.test(rawLabel) || rawLabel.length < 3);
  const humanLabel = rawLabel && !isTechnical ? rawLabel : "";
  if (type === "resolve" || type === "ack") return humanLabel || t("inbox.done");
  if (type === "prompt") return humanLabel || t("inbox.aiAnalyze");
  if (type === "open") return humanLabel || t("inbox.openAction");
  if (type === "execute") {
    const act = String(action.action || "").trim();
    const key = `inbox.exec.${act}`;
    const localized = t(key);
    if (localized && localized !== key) return localized;
    if (humanLabel) return humanLabel;
    if (act === "notify_worker") return t("inbox.exec.notify_worker");
    return act ? act.replace(/_/g, " ") : t("common.open");
  }
  if (type === "navigate") {
    const url = String(action.url || "");
    const tab = String(action.tab || "").trim();
    if (tab === "audit" || /tab=audit/i.test(url)) return t("inbox.nav.audit");
    if (tab === "access" || /tab=access/i.test(url)) return t("inbox.nav.attendance");
    if (tab === "workers" || /tab=workers/i.test(url)) return t("tab.workers");
    if (/chat\.html/i.test(url)) return humanLabel || t("lage.openChat");
    if (/docs\.html/i.test(url)) return t("inbox.nav.docs");
    if (/camera-watch/i.test(url)) return t("cameraWatch.open");
    if (/source=leave/i.test(url)) return t("inbox.nav.leave");
    if (/source=document/i.test(url)) return t("inbox.nav.docs");
    if (/source=attendance/i.test(url)) return t("inbox.nav.attendance");
    if (/source=security/i.test(url)) return t("inbox.nav.security");
    if (/ai-command-center/i.test(url)) return t("inbox.aiAnalyze");
    if (/deployment|einsatzplan/i.test(url)) return t("inbox.nav.deployment");
    if (humanLabel) return humanLabel;
    return t("common.open");
  }
  if (humanLabel) return humanLabel;
  return t("common.open");
}

function inboxJoinUrl(url, companyQ) {
  const raw = String(url || "").trim();
  if (!raw) return raw;
  const q = String(companyQ || "").replace(/^\?/, "");
  if (!q) return raw;
  try {
    const u = new URL(raw, window.location.origin);
    const extra = new URLSearchParams(q);
    extra.forEach((value, key) => {
      if (!u.searchParams.has(key)) u.searchParams.set(key, value);
    });
    return u.pathname + u.search + u.hash;
  } catch (_e) {
    if (raw.includes("?")) return raw;
    return `${raw}?${q}`;
  }
}

async function runInboxNavigateAction(a, { companyQ = "", workerId = "", workerName = "" } = {}) {
  const action = a || {};
  const url = String(action.url || "").trim();
  const tabTarget =
    String(action.tab || "").trim() ||
    (() => {
      try {
        return new URL(url, window.location.origin).searchParams.get("tab") || "";
      } catch (_e) {
        return "";
      }
    })();

  if (tabTarget && document.querySelector(`.tab[data-tab="${tabTarget}"]`)) {
    switchToTab(tabTarget);
    await refreshActiveTab();
    return;
  }

  const isDeployment =
    /deployment-plan|einsatzplan/i.test(url) || String(action.label || "").toLowerCase().includes("einsatz");
  if (isDeployment && workerId) {
    switchToTab("workers");
    await loadWorkers();
    await openDeploymentModal(workerId, workerName || workerId);
    return;
  }

  if (/chat\.html/i.test(url)) {
    const href = inboxJoinUrl(url, companyQ);
    window.open(href, "_blank", "noopener");
    return;
  }

  if (url) {
    const href = inboxJoinUrl(url, companyQ);
    if (window.parent !== window && href.startsWith("/")) {
      try {
        const u = new URL(href, window.location.origin);
        window.parent.postMessage(
          {
            type: "baupass-navigate",
            view: u.searchParams.get("view") || "",
            focusEinsatzplan: u.searchParams.get("einsatzplan") === "1",
            url: u.pathname + u.search + u.hash,
          },
          window.location.origin,
        );
        return;
      } catch (_e) {
        /* fall through */
      }
    }
    if (/^https?:\/\//i.test(href) || href.startsWith("/")) {
      window.location.href = href;
      return;
    }
  }
  showActionToast(t("common.error"), true);
}

async function runInboxResolveAction(itemId, companyQ, extraBody = {}) {
  const res = await api(`/api/inbox/${encodeURIComponent(itemId)}/resolve${companyQ}`, {
    method: "POST",
    body: JSON.stringify(extraBody),
  });
  const ok = res?.ok !== false;
  showActionToast(
    ok ? t("common.done") : humanizeUserError({ message: res?.message || res?.error, data: res }),
    !ok,
  );
  if (ok) {
    await loadInbox();
    // Keep Live-Lage KPIs in sync (Fehlt heute, Offene Aufgaben, …).
    scheduleOverviewReload();
  }
  return res;
}

async function runInboxExecAction(btn, companyQ) {
  const id = btn.dataset.id || "";
  const action = btn.dataset.action || "";
  if (id.startsWith("leave:") && (action === "approve_leave_request" || action === "reject_leave_request")) {
    const decision = action === "approve_leave_request" ? "approve" : "reject";
    const res = await api(`/api/inbox/${encodeURIComponent(id)}/resolve${companyQ}`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    });
    const ok = res?.ok !== false;
    const msg = ok
      ? `${decision === "approve" ? t("inbox.approved") : t("inbox.rejected")}. ${formatPushDelivery(res)}`
      : humanizeUserError({ message: res?.message || res?.error, data: res });
    showActionToast(msg, !ok);
    if (ok) {
      await loadInbox();
      scheduleOverviewReload();
    }
    return;
  }
  let params = {};
  try {
    params = JSON.parse(decodeURIComponent(btn.dataset.params || "%7B%7D"));
  } catch (_e) {
    params = {};
  }
  const cid = String(companyQ || "").replace(/^\?company_id=/, "");
  // Prefer inbox execute (no AI-plan gate). Fall back to AI execute for legacy actions.
  let res;
  try {
    res = await api(`/api/inbox/${encodeURIComponent(id || "action")}/execute${companyQ}`, {
      method: "POST",
      body: JSON.stringify({ action, params, company_id: cid || undefined }),
    });
  } catch (firstErr) {
    // Older backends / unexpected 404 → try AI path once.
    const status = Number(firstErr?.status || 0);
    if (status === 404 || status === 405) {
      res = await api("/api/ai/actions/execute", {
        method: "POST",
        body: JSON.stringify({ action, params, company_id: cid || undefined }),
      });
    } else {
      throw firstErr;
    }
  }
  const sent = Number(res?.pushSent ?? res?.pushDelivery?.pushSent ?? 0) || 0;
  const channels = res?.pushDelivery?.channels || [];
  const pushMsg = formatPushDelivery(res);
  const soft = Boolean(res?.softFail) || (action === "notify_worker" && sent <= 0);
  if (action === "notify_worker") {
    if (sent > 0) {
      showActionToast(`${t("inbox.exec.notify_worker")} ✓ — ${pushMsg || t("common.done")}`, false);
    } else if (channels.includes("inbox") || channels.includes("email") || res?.ok) {
      showActionToast(
        t("inbox.pushSoftOk") ||
          `Mitteilung gespeichert${pushMsg ? ` — ${pushMsg}` : ""}. Push-Gerät fehlt ggf. beim Mitarbeiter.`,
        false,
      );
    } else {
      showActionToast(
        pushMsg ||
          t("inbox.pushNotDelivered") ||
          "Push nicht zugestellt — Mitarbeiter hat kein aktives Gerät. Bitte Chat nutzen.",
        true,
      );
    }
    return;
  }
  const ok = res?.ok !== false;
  showActionToast(
    ok
      ? `${inboxActionLabel({ type: "execute", action, label: btn.textContent }) || action} ✓${pushMsg ? ` — ${pushMsg}` : ""}`
      : humanizeUserError({ message: res?.message || res?.error, data: res, status: res?.status }),
    !ok,
  );
  if (ok && !soft) await loadInbox();
}

function inboxTitleForCode(code, fallback) {
  const c = String(code || "").trim();
  const keyMap = {
    outside_hours_checkin_attempt: "inbox.alert.outsideHours.title",
    repeated_late_checkin: "inbox.alert.repeatedLate.title",
    tomorrow_attendance_forecast: "inbox.alert.tomorrowForecast.title",
    deployment_worker_declined: "inbox.alert.deploymentDeclined.title",
    shift_swap_accepted: "inbox.alert.shiftSwap.title",
    "docs.review": "inbox.alert.docsReview.title",
    "docs.review.stale": "inbox.alert.docsReviewStale.title",
    "docs.published": "inbox.alert.docsPublished.title",
    "autopilot.leave_queue": "inbox.alert.autopilotLeave.title",
    "autopilot.docs_review": "inbox.alert.autopilotDocs.title",
    "autopilot.missing_expected": "inbox.alert.autopilotMissing.title",
    "autopilot.security_open": "inbox.alert.autopilotSecurity.title",
    "autopilot.ops_digest": "inbox.alert.autopilotDigest.title",
  };
  if (c.startsWith("sensitive_attempt")) {
    const k = "inbox.alert.sensitive.title";
    const label = t(k);
    return label && label !== k ? label : fallback || c;
  }
  const key = keyMap[c];
  if (key) {
    const label = t(key);
    if (label && label !== key) return label;
  }
  const fb = String(fallback || "").trim();
  // Never show raw snake_case codes as titles
  if (fb && !/^[a-z][a-z0-9_.-]*$/i.test(fb)) return fb;
  return t("inbox.alert.generic.title");
}

function splitInboxReason(message, details = {}) {
  const fromDetails = String(details.reasonSummary || details.reason || details.note || "").trim();
  let body = String(message || "").trim();
  let reason = fromDetails;
  if (!reason) {
    const m = body.match(/^(.*?)(?:\s*[·•|]\s*)?(?:Grund|Reason|Why|السبب|سبب)\s*:\s*(.+)$/is);
    if (m) {
      body = m[1].trim();
      reason = m[2].trim();
    }
  } else if (body) {
    body = body.replace(/(?:\s*[·•|]\s*)?(?:Grund|Reason|Why|السبب|سبب)\s*:\s*.+$/is, "").trim();
  }
  return { body, reason };
}

function inboxFromName(it) {
  const details = it?.details && typeof it.details === "object" ? it.details : {};
  const named = String(details.workerName || details.fromName || "").trim();
  if (named) return named;
  const msg = String(it?.message || "").trim();
  const before = msg.split(/[·:]/)[0]?.trim() || "";
  if (before && before.length > 1 && before.length < 80 && !/^[a-z0-9_.-]+$/i.test(before)) {
    return before;
  }
  return inboxSourceLabel(it?.source);
}

function localizeInboxItem(it) {
  const item = it || {};
  const code = String(item.code || "").trim();
  const details = item.details && typeof item.details === "object" ? { ...item.details } : {};
  const id = String(item.id || "");

  if (code === "outside_hours_checkin_attempt" || details.i18nKey === "outside_hours_checkin_attempt") {
    const channelKey = String(details.channel || "gps").trim().toLowerCase() || "gps";
    const channel = t(`inbox.alert.outsideHours.channel.${channelKey}`);
    const channelLabel = channel && !channel.startsWith("inbox.alert.") ? channel : channelKey.toUpperCase();
    const gateRaw = String(details.gate || "").trim();
    const gateHuman = gateRaw && /[a-zA-Z\u0600-\u06FF]{2,}/.test(gateRaw) && !/^[a-z0-9_]+$/i.test(gateRaw)
      ? ` (${gateRaw})`
      : "";
    const start = String(details.shiftStart || "").trim().slice(0, 5);
    const end = String(details.shiftEnd || "").trim().slice(0, 5);
    const windowBit = start && end ? t("inbox.alert.outsideHours.window", { start, end }) : "";
    const name = String(details.workerName || "").trim() || "—";
    return {
      ...item,
      title: t("inbox.alert.outsideHours.title"),
      message: t("inbox.alert.outsideHours.body", {
        name,
        channel: channelLabel,
        gate: gateHuman,
        window: windowBit,
      }),
      details: { ...details, workerName: name },
      fromName: name,
    };
  }
  if (code === "repeated_late_checkin" || details.i18nKey === "repeated_late_checkin") {
    const name = String(details.workerName || "").trim() || "—";
    const streak = Number(details.streak || 0) || 0;
    const reasonText = String(details.reasonSummary || details.reason || "").trim();
    return {
      ...item,
      title: t("inbox.alert.repeatedLate.title"),
      message: t("inbox.alert.repeatedLate.body", { name, streak }),
      details: { ...details, workerName: name, reasonSummary: reasonText },
      fromName: name,
    };
  }
  if (code === "tomorrow_attendance_forecast" || details.i18nKey === "tomorrow_attendance_forecast") {
    const names = Array.isArray(details.names) ? details.names.filter(Boolean).slice(0, 5).join(", ") : "";
    return {
      ...item,
      title: t("inbox.alert.tomorrowForecast.title"),
      message: t("inbox.alert.tomorrowForecast.body", {
        date: details.date || "",
        onSite: details.expectedOnSite ?? "—",
        absent: details.expectedAbsent ?? "—",
        names: names ? ` ${names}` : "",
      }),
    };
  }
  if (code === "deployment_worker_declined" || id.startsWith("depdecl:")) {
    const { body, reason } = splitInboxReason(item.message, details);
    const name = String(details.workerName || "").trim() || body.split("·")[0]?.trim() || "—";
    const date = String(details.workDate || "").trim();
    const loc = String(details.location || "").trim();
    const msg = t("inbox.alert.deploymentDeclined.body", {
      name,
      date: date || "—",
      location: loc || "—",
    });
    return {
      ...item,
      title: t("inbox.alert.deploymentDeclined.title"),
      message: msg,
      details: { ...details, workerName: name, reasonSummary: reason || details.reasonSummary || "" },
      fromName: name,
    };
  }
  if (code === "leave_request_pending" || id.startsWith("leave:") || item.source === "leave") {
    const { body, reason } = splitInboxReason(item.message, details);
    const name = String(details.workerName || "").trim() || body.split(":")[0]?.trim() || "—";
    const leaveType = String(details.leaveType || "").trim() || "—";
    const start = String(details.startDate || "").trim() || "—";
    const end = String(details.endDate || "").trim() || "—";
    return {
      ...item,
      title: t("inbox.alert.leave.title"),
      message: t("inbox.alert.leave.body", { name, type: leaveType, start, end }),
      details: {
        ...details,
        workerName: name,
        reasonSummary: reason || details.reasonSummary || details.note || "",
      },
      fromName: name,
    };
  }
  if (code === "missing_checkin" || id.startsWith("miss:")) {
    const name = String(details.workerName || "").trim() || "—";
    const loc = employerCleanText(details.location) || "";
    const startRaw = String(details.shiftStart || "").trim();
    const endRaw = String(details.shiftEnd || "").trim();
    const start = /^\d{1,2}:\d{2}/.test(startRaw) ? startRaw.slice(0, 5) : "";
    const end = /^\d{1,2}:\d{2}/.test(endRaw) ? endRaw.slice(0, 5) : "";
    const shift = start && end ? `${start}–${end}` : start || "";
    return {
      ...item,
      title: t("inbox.alert.missingCheckin.title", { name }),
      message: t("inbox.alert.missingCheckin.body", {
        name,
        location: loc ? ` · ${loc}` : "",
        shift: shift ? ` (${shift})` : "",
      }),
      details: { ...details, workerName: name, shiftStart: start, shiftEnd: end },
      fromName: name,
    };
  }
  if (code === "shift_swap_accepted") {
    return { ...item, title: t("inbox.alert.shiftSwap.title") };
  }
  const title = inboxTitleForCode(code, item.title);
  const split = splitInboxReason(item.message, details);
  let message = split.body;
  if (!message || /^[a-z][a-z0-9_.-]*$/i.test(message)) {
    message = t("inbox.detail.noMessage");
  }
  return {
    ...item,
    title,
    message,
    details: { ...details, reasonSummary: split.reason || details.reasonSummary || "" },
    fromName: inboxFromName({ ...item, details, message }),
  };
}

async function loadInbox() {
  const el = $("inboxList");
  const countsEl = $("inboxCounts");
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    el.innerHTML = emptyStateHtml(t("common.selectCompany"));
    countsEl.innerHTML = "";
    $("inboxFilters")?.classList.add("hidden");
    $("complianceAutopilotCard")?.classList.add("hidden");
    return;
  }
  el.innerHTML = `<p class="muted">${t("common.loading")}</p>`;
  const iq = inboxApiQuery(q);
  // Render inbox first; push status is non-blocking for perceived speed.
  const data = await api(`/api/inbox${iq || q}`);
  _inboxCountsCache = { key: q || "_", at: Date.now(), data };
  api("/api/platform/push/status")
    .then((pushSt) => {
      const pushEl = $("inboxPushStatus");
      if (!pushEl || !pushSt) return;
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
    })
    .catch(() => {
      const pushEl = $("inboxPushStatus");
      if (pushEl) pushEl.classList.add("hidden");
    });
  const liveHint = $("inboxLiveHint");
  if (liveHint) liveHint.classList.remove("hidden");
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

  const complianceCard = $("complianceAutopilotCard");
  if (complianceCard) {
    const docItems = (data.items || []).filter((it) => String(it.id || "").startsWith("doc:"));
    const expiring = docItems.length;
    complianceCard.classList.remove("hidden");
    complianceCard.innerHTML = `
      <h3>${t("compliance.autopilotTitle")}</h3>
      <p class="muted small" style="margin:0">${t("compliance.autopilotDesc")}</p>
      <p style="margin:0.55rem 0 0"><strong>${expiring}</strong> <span class="muted">${t("compliance.expiring")}</span></p>
      <div class="compliance-autopilot-actions">
        <button type="button" id="compliancePushNowBtn">${t("compliance.pushNow")}</button>
        <button type="button" class="ghost" id="complianceRunAutopilotBtn">${t("compliance.runAutopilot")}</button>
        <button type="button" class="ghost" data-goto-tab="platform">${t("quick.platform.title")}</button>
      </div>
    `;
    complianceCard.querySelector("#compliancePushNowBtn")?.addEventListener("click", () => {
      runInboxBulk("push_document_reminders").catch((e) => showActionToast(e.message, true));
    });
    complianceCard.querySelector("#complianceRunAutopilotBtn")?.addEventListener("click", async () => {
      try {
        await api(`/api/platform/autopilot/run${q}`, { method: "POST", body: "{}" });
        showActionToast(t("autopilot.ran"), false);
        await loadInbox();
      } catch (e) {
        showActionToast(e.message || String(e), true);
      }
    });
    complianceCard.querySelector("[data-goto-tab]")?.addEventListener("click", () => {
      switchToTab("platform");
      refreshActiveTab();
    });
  }

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
    const filterHint =
      inboxSourceFilter === "attendance"
        ? t("inbox.emptyAttendance")
        : t("inbox.emptyHint") || "";
    el.innerHTML = `<div class="empty-state inbox-empty-state"><strong>${t("inbox.empty")}</strong><p class="muted small" style="margin:0.4rem 0 0">${escapeHtml(filterHint)}</p>
      ${inboxSourceFilter === "attendance" ? `<p style="margin:0.75rem 0 0"><button type="button" class="ghost" data-goto-tab="access">${escapeHtml(t("lage.openAccess"))}</button></p>` : ""}
    </div>`;
    el.querySelector("[data-goto-tab=\"access\"]")?.addEventListener("click", async () => {
      switchToTab("access");
      await loadAccess();
    });
    return;
  }
  el.innerHTML = `<div class="inbox-mail-list">${items
    .map((raw) => {
      const it = localizeInboxItem(raw);
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
              : "";
      const when = String(it.createdAt || "")
        .slice(0, 16)
        .replace("T", " ");
      const from = it.fromName || inboxFromName(it);
      const preview = String(it.details?.reasonSummary || it.message || "").trim();
      const sev = String(it.severity || "").toLowerCase();
      const sevBadge =
        sev === "critical" || sev === "high"
          ? "badge-warn"
          : sev === "info" || sev === "low"
            ? "badge-ok"
            : "badge-warn";
      return `<article class="inbox-mail-row${sev === "critical" ? " is-critical" : ""} inbox-row" data-inbox-id="${escapeAttr(it.id)}" tabindex="0" role="button">
        <label class="inbox-mail-check" onclick="event.stopPropagation()">
          <input type="checkbox" class="inbox-pick" data-id="${it.id}"${checked} aria-label="${t("inbox.selectAria")}" />
        </label>
        <div class="inbox-mail-main">
          <div class="inbox-mail-top">
            <strong class="inbox-mail-from">${escapeHtml(from)}</strong>
            <span class="inbox-mail-meta">
              <span class="badge ${sevBadge}">${escapeHtml(inboxSeverityLabel(it.severity))}</span>
              <span class="inbox-mail-source">${escapeHtml(inboxSourceLabel(it.source))}</span>
              ${when ? `<time datetime="${escapeAttr(String(it.createdAt || ""))}">${escapeHtml(when)}</time>` : ""}
            </span>
          </div>
          <div class="inbox-mail-subject">${escapeHtml(it.title || t("inbox.alert.generic.title"))}</div>
          <div class="inbox-mail-preview muted small">${escapeHtml(preview.slice(0, 160))}${preview.length > 160 ? "…" : ""}</div>
          ${slaLabel ? `<div class="inbox-mail-sla ${slaCls}">${escapeHtml(slaLabel)}</div>` : ""}
        </div>
      </article>`;
    })
    .join("")}</div>`;
  const itemById = Object.fromEntries(items.map((it) => [it.id, it]));
  async function openInboxItem(itemId) {
    const raw = itemById[itemId];
    if (!raw) return;
    const it = localizeInboxItem(raw);
    const panel = $("inboxDetailPanel");
    const details = it.details || {};
    const events = Array.isArray(details.lateEvents) ? details.lateEvents : [];
    const eventHtml = events.length
      ? `<div class="inbox-late-events">
          <p class="muted small"><strong>${escapeHtml(t("inbox.detail.lateHistory"))}</strong></p>
          <ul class="muted small">${events
            .map((ev) => {
              const day = escapeHtml(ev.day || ev.date || "");
              const time = escapeHtml(String(ev.time || ev.at || "").slice(0, 5));
              const gateRaw = String(ev.gate || "").trim();
              const gate =
                gateRaw && !/^[a-z0-9_]+$/i.test(gateRaw) ? escapeHtml(gateRaw) : "";
              const note = ev.note ? escapeHtml(ev.note) : "";
              const bits = [day, time, gate, note].filter(Boolean);
              return `<li>${bits.join(" · ") || "—"}</li>`;
            })
            .join("")}</ul>
        </div>`
      : "";
    const reason = String(details.reasonSummary || details.reason || details.note || "").trim();
    const shouldAutoAck =
      Boolean(it.autoAckOnOpen) && String(it.id || "").startsWith("sys:") && it.status !== "resolved";

    // Ack as soon as the employer opens/reads the alert — before UI paint so it cannot stick.
    if (shouldAutoAck) {
      try {
        suppressInboxReload(3000);
        await api(`/api/inbox/${encodeURIComponent(it.id)}/resolve${q}`, {
          method: "POST",
          body: "{}",
        });
        it.status = "resolved";
        raw.status = "resolved";
        showActionToast(t("inbox.ackedOnOpen"), false);
        await refreshInboxBadgeOnly();
        scheduleOverviewReload();
      } catch (e) {
        showActionToast(humanizeUserError(e), true);
      }
    }

    if (panel) {
      const code = String(it.code || details.i18nKey || "").trim();
      const facts = [];
      const pushFact = (label, value) => {
        if (value === undefined || value === null || value === "") return;
        facts.push(
          `<tr><th scope="row">${escapeHtml(label)}</th><td>${escapeHtml(String(value))}</td></tr>`,
        );
      };
      if (code === "outside_hours_checkin_attempt") {
        pushFact(t("inbox.detail.worker"), details.workerName);
        const chKey = String(details.channel || "").trim().toLowerCase();
        const chLabel = chKey ? t(`inbox.alert.outsideHours.channel.${chKey}`) : "";
        pushFact(
          t("inbox.detail.channel"),
          chLabel && !chLabel.startsWith("inbox.alert.") ? chLabel : details.channel,
        );
        const gate = String(details.gate || details.gateName || details.siteName || "").trim();
        if (gate && !/^[a-z0-9_]+$/i.test(gate)) pushFact(t("inbox.detail.gate"), gate);
        else if (details.siteName) pushFact(t("inbox.detail.site"), details.siteName);
        const start = String(details.shiftStart || details.workStart || "").trim().slice(0, 5);
        const end = String(details.shiftEnd || details.workEnd || "").trim().slice(0, 5);
        if (start && end) pushFact(t("inbox.detail.shiftWindow"), `${start}–${end}`);
        if (details.attemptedAt || details.at || details.timestamp || it.createdAt) {
          pushFact(
            t("inbox.detail.when"),
            String(details.attemptedAt || details.at || details.timestamp || it.createdAt || "")
              .slice(0, 19)
              .replace("T", " "),
          );
        }
        if (details.minutesOutside != null || details.deltaMinutes != null) {
          pushFact(
            t("inbox.detail.minutesOutside"),
            details.minutesOutside ?? details.deltaMinutes,
          );
        }
        const lat = details.lat ?? details.latitude;
        const lng = details.lng ?? details.longitude;
        if (lat != null && lng != null) {
          pushFact(t("inbox.detail.location"), `${Number(lat).toFixed(5)}, ${Number(lng).toFixed(5)}`);
        }
        if (details.distanceMeters != null || details.distance_m != null) {
          pushFact(
            t("inbox.detail.distance"),
            `${Math.round(Number(details.distanceMeters ?? details.distance_m))} m`,
          );
        }
      }
      if (code === "repeated_late_checkin") {
        pushFact(t("inbox.detail.worker"), details.workerName);
        if (details.streak != null) pushFact(t("inbox.detail.streak"), details.streak);
        if (details.windowDays != null) {
          pushFact(t("inbox.detail.windowDays"), details.windowDays);
        }
        if (it.createdAt) {
          pushFact(
            t("inbox.detail.when"),
            String(it.createdAt).slice(0, 19).replace("T", " "),
          );
        }
      }
      if (code === "leave_request_pending" || String(it.id || "").startsWith("leave:")) {
        pushFact(t("inbox.detail.worker"), details.workerName);
        if (details.leaveType) pushFact(t("inbox.detail.leaveType"), details.leaveType);
        if (details.startDate || details.endDate) {
          pushFact(
            t("inbox.detail.leavePeriod"),
            `${details.startDate || "—"} – ${details.endDate || "—"}`,
          );
        }
      }
      if (code === "deployment_worker_declined" || String(it.id || "").startsWith("depdecl:")) {
        pushFact(t("inbox.detail.worker"), details.workerName);
        if (details.workDate) pushFact(t("inbox.detail.when"), details.workDate);
        if (details.location) pushFact(t("inbox.detail.site"), details.location);
      }
      pushFact(t("inbox.colSource"), inboxSourceLabel(it.source));
      pushFact(t("inbox.colSeverity"), inboxSeverityLabel(it.severity));
      const factsHtml = facts.length
        ? `<table class="inbox-detail-facts"><tbody>${facts.join("")}</tbody></table>`
        : "";
      const from = it.fromName || inboxFromName(it);
      const when = String(it.createdAt || "")
        .slice(0, 19)
        .replace("T", " ");
      const bodyParas = String(it.message || t("inbox.detail.noMessage"))
        .split(/\n+/)
        .map((p) => p.trim())
        .filter(Boolean)
        .map((p) => `<p>${escapeHtml(p)}</p>`)
        .join("");
      const actionBtns = (it.actions || [])
        .map((a, idx) => {
          const label = inboxActionLabel(a);
          if (a.type === "resolve" || a.type === "ack")
            return `<button type="button" class="ghost inbox-action-btn inbox-resolve" data-id="${escapeAttr(it.id)}">${escapeHtml(label)}</button>`;
          if (a.type === "execute" && a.action)
            return `<button type="button" class="ghost inbox-action-btn inbox-exec" data-id="${escapeAttr(it.id)}" data-action="${escapeAttr(a.action)}" data-params="${encodeURIComponent(JSON.stringify(a.params || {}))}">${escapeHtml(label)}</button>`;
          if (a.type === "navigate") {
            const url = String(a.url || "");
            if (/ai-command-center\.html/i.test(url)) {
              const prompt =
                a.prompt ||
                t("inbox.aiPromptDefault", {
                  title: it.title || "",
                  message: it.message || "",
                });
              return `<button type="button" class="ghost inbox-action-btn inbox-ai-analyze" data-id="${escapeAttr(it.id)}" data-prompt="${encodeURIComponent(prompt)}" data-agent="${escapeAttr(a.agent || "decision")}">${escapeHtml(label)}</button>`;
            }
            return `<button type="button" class="ghost inbox-action-btn inbox-nav" data-action-idx="${idx}" data-worker-id="${escapeAttr(String(it.workerId || ""))}" data-worker-name="${escapeAttr(String(from || ""))}">${escapeHtml(label)}</button>`;
          }
          if (a.type === "prompt")
            return `<button type="button" class="ghost inbox-action-btn inbox-ai-analyze" data-id="${escapeAttr(it.id)}" data-prompt="${encodeURIComponent(a.prompt || "")}" data-agent="${escapeAttr(a.agent || "decision")}">${escapeHtml(label)}</button>`;
          if (a.type === "open")
            return ""; // Already open in the letter view — no redundant button
          return "";
        })
        .filter(Boolean)
        .join("");
      panel.classList.remove("hidden");
      panel.innerHTML = `
      <article class="inbox-letter">
        <div class="inbox-detail-head">
          <div>
            <p class="inbox-detail-kicker">${escapeHtml(inboxSourceLabel(it.source))} · ${escapeHtml(inboxSeverityLabel(it.severity))}</p>
            <h3>${escapeHtml(it.title || t("inbox.alert.generic.title"))}</h3>
          </div>
          <button type="button" class="ghost small" id="inboxDetailClose">${t("common.close") || "Schließen"}</button>
        </div>
        <div class="inbox-letter-meta">
          <div><span>${escapeHtml(t("inbox.mail.from"))}</span><strong>${escapeHtml(from)}</strong></div>
          <div><span>${escapeHtml(t("inbox.mail.when"))}</span><strong>${escapeHtml(when || "—")}</strong></div>
        </div>
        <div class="inbox-letter-body">
          ${bodyParas}
          ${reason ? `<blockquote class="inbox-detail-reason"><strong>${escapeHtml(t("inbox.reasonLabel"))}</strong><br>${escapeHtml(reason)}</blockquote>` : ""}
        </div>
        ${factsHtml}
        ${eventHtml}
        <div class="inbox-detail-actions">${actionBtns}</div>
      </article>
    `;
      panel.querySelector("#inboxDetailClose")?.addEventListener("click", () => {
        panel.classList.add("hidden");
        panel.innerHTML = "";
      });
      panel.querySelectorAll(".inbox-ai-analyze").forEach((btn) => {
        btn.addEventListener("click", () => runInboxAiAnalyze(btn).catch((e) => showActionToast(humanizeUserError(e), true)));
      });
      panel.querySelectorAll(".inbox-resolve").forEach((btn) => {
        btn.addEventListener("click", () =>
          runInboxResolveAction(btn.dataset.id, q).catch((e) => showActionToast(humanizeUserError(e), true)),
        );
      });
      panel.querySelectorAll(".inbox-exec").forEach((btn) => {
        btn.addEventListener("click", () =>
          runInboxExecAction(btn, q).catch((e) => showActionToast(humanizeUserError(e), true)),
        );
      });
      panel.querySelectorAll(".inbox-nav").forEach((btn) => {
        btn.addEventListener("click", () => {
          const idx = Number(btn.dataset.actionIdx);
          const navAction = (it.actions || [])[idx];
          if (!navAction) return;
          runInboxNavigateAction(navAction, {
            companyQ: q,
            workerId: btn.dataset.workerId || it.workerId || "",
            workerName: btn.dataset.workerName || from || "",
          }).catch((e) => showActionToast(humanizeUserError(e), true));
        });
      });
    }

    if (shouldAutoAck) {
      // Keep the letter open after list refresh; re-bind close only (actions already used).
      const detailHtml = panel?.innerHTML || "";
      const detailOpen = panel && !panel.classList.contains("hidden");
      await loadInbox();
      if (detailOpen && panel && detailHtml) {
        panel.classList.remove("hidden");
        panel.innerHTML = detailHtml;
        panel.querySelector("#inboxDetailClose")?.addEventListener("click", () => {
          panel.classList.add("hidden");
          panel.innerHTML = "";
        });
      }
    }
  }
  async function runInboxAiAnalyze(btn) {
    const prompt = decodeURIComponent(btn.dataset.prompt || "");
    const agent = btn.dataset.agent || "decision";
    const alertId = String(btn.dataset.id || "").trim();
    const aiPanel = $("inboxAiPanel");
    if (!prompt) return;
    // Reading via AI analysis also dismisses employer auto-ack alerts.
    if (alertId.startsWith("sys:")) {
      const raw = itemById[alertId];
      if (raw && raw.autoAckOnOpen && raw.status !== "resolved") {
        try {
          suppressInboxReload(3000);
          await api(`/api/inbox/${encodeURIComponent(alertId)}/resolve${q}`, {
            method: "POST",
            body: "{}",
          });
          raw.status = "resolved";
          showActionToast(t("inbox.ackedOnOpen"), false);
        } catch (_) {
          /* keep analyzing even if ack fails */
        }
      }
    }
    if (aiPanel) {
      aiPanel.classList.remove("hidden");
      aiPanel.innerHTML = `<p class="muted">${t("inbox.aiAnalyzing")}</p>`;
      aiPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    const cid = (companyQuery() || "").replace("?company_id=", "");
    if (!cid) {
      const msg = t("common.selectCompany");
      if (aiPanel) aiPanel.innerHTML = `<p class="error">${escapeHtml(msg)}</p>`;
      else showActionToast(msg, true);
      return;
    }

    const isTechnicalDecisionText = (value) => {
      const s = String(value || "").trim();
      if (!s) return true;
      if (/^(review_ops|retry|escalate|monitor)$/i.test(s)) return true;
      if (/structured decision block missing/i.test(s)) return true;
      return false;
    };

    const formatInboxAiHtml = (raw) => {
      let s = String(raw || "").trim();
      if (s.includes("DECISION_JSON")) s = s.split("DECISION_JSON")[0].trim();
      s = s.replace(/\n{3,}/g, "\n\n");
      const escape = (v) =>
        String(v)
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");
      const inline = (line) =>
        escape(line)
          .replace(/`([^`]+)`/g, "<code>$1</code>")
          .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      return s
        .split(/\n{2,}/)
        .map((block) => `<p>${block.split(/\n/).map(inline).join("<br>")}</p>`)
        .join("");
    };

    const renderInboxAiResult = (text, { promptText = prompt, agentId = agent } = {}) => {
      if (!aiPanel) {
        showActionToast(String(text).slice(0, 160), false);
        return;
      }
      aiPanel.innerHTML = `
        <div class="inbox-ai-head">
          <h3>${t("inbox.aiAnalyze")}</h3>
        </div>
        <div class="inbox-ai-body">${formatInboxAiHtml(text)}</div>
        <button type="button" class="ghost small" id="inboxAiOpenFull">${t("inbox.aiOpenFull")}</button>
      `;
      aiPanel.querySelector("#inboxAiOpenFull")?.addEventListener("click", () => {
        openAiCommandCenterWithPrompt(promptText, agentId);
      });
    };

    const pickAnswer = (res) => {
      const decision = res?.decision && typeof res.decision === "object" ? res.decision : {};
      const errCode = String(res?.error || "").trim();
      if (
        errCode === "openai_quota_exceeded" ||
        /insufficient_quota|exceeded your current quota|chatgpt plus/i.test(String(res?.hint || ""))
      ) {
        return (
          t("inbox.aiQuota") ||
          "OpenAI-API-Guthaben leer. Bitte unter platform.openai.com/settings/billing aufladen (ChatGPT Plus ≠ API)."
        );
      }
      if (errCode === "ai_not_configured" || errCode === "openai_not_configured") {
        return t("inbox.aiNotConfigured") || "KI ist noch nicht konfiguriert (OPENAI_API_KEY).";
      }
      const candidates = [
        res?.answer,
        decision.summary,
        decision.rationale,
        res?.message,
      ];
      for (const c of candidates) {
        const s = String(c || "").trim();
        if (s && !isTechnicalDecisionText(s)) return s;
      }
      const hint = String(res?.hint || "").trim();
      if (hint && !isTechnicalDecisionText(hint) && !/openai|quota|api key/i.test(hint)) return hint;
      if (hint) {
        return (
          t("inbox.aiQuota") ||
          "OpenAI-API-Guthaben leer. Bitte unter platform.openai.com/settings/billing aufladen (ChatGPT Plus ≠ API)."
        );
      }
      return "";
    };

    try {
      let res = await api("/api/ai/decision", {
        method: "POST",
        body: JSON.stringify({
          question: prompt,
          agent,
          company_id: cid,
          autoStage: false,
          lang: getLang?.() || "de",
        }),
      });
      let text = pickAnswer(res);
      if (!text) {
        res = await api("/api/ai/query", {
          method: "POST",
          body: JSON.stringify({
            question: prompt,
            company_id: cid,
            use_agent: true,
            agent_id: agent || "operations",
            lang: getLang?.() || "de",
          }),
        });
        text = pickAnswer(res);
      }
      if (!text) {
        text = t("inbox.aiEmpty") || "Keine aussagekräftige Analyse erhalten. Bitte erneut versuchen.";
      }
      renderInboxAiResult(text);
    } catch (e) {
      try {
        const res = await api("/api/ai/query", {
          method: "POST",
          body: JSON.stringify({
            question: prompt,
            company_id: cid,
            use_agent: true,
            agent_id: "operations",
            lang: getLang?.() || "de",
          }),
        });
        const text = pickAnswer(res) || e.message || "error";
        renderInboxAiResult(text, { agentId: "operations" });
      } catch (e2) {
        if (aiPanel) {
          aiPanel.innerHTML = `<p class="error">${escapeHtml(e2.message || e.message || "error")}</p>`;
        }
        throw e2;
      }
    }
  }
  el.querySelectorAll(".inbox-row").forEach((tr) => {
    tr.addEventListener("click", (ev) => {
      if (ev.target.closest("a, button, input, label, .inbox-pick, .inbox-resolve, .inbox-exec, .inbox-ai-analyze, .inbox-nav-deployment, .inbox-nav-parent, .inbox-nav-tab")) {
        return;
      }
      ev.preventDefault();
      const id = tr.getAttribute("data-inbox-id");
      if (id) openInboxItem(id).catch((e) => showActionToast(e.message, true));
    });
    tr.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      if (ev.target !== tr) return;
      ev.preventDefault();
      const id = tr.getAttribute("data-inbox-id");
      if (id) openInboxItem(id).catch((e) => showActionToast(e.message, true));
    });
  });
  el.querySelectorAll(".inbox-open").forEach((node) => {
    node.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const id = node.dataset.id || node.closest("tr[data-inbox-id]")?.getAttribute("data-inbox-id");
      if (id) openInboxItem(id).catch((e) => showActionToast(e.message, true));
    });
  });
  el.querySelectorAll(".inbox-ai-analyze").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      runInboxAiAnalyze(btn).catch((e) => showActionToast(e.message, true));
    });
  });
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
  el.querySelectorAll(".inbox-nav-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = String(btn.dataset.tab || "").trim();
      if (!tab) return;
      switchToTab(tab);
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
    if (res.ok) scheduleOverviewReload();
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
    btn.addEventListener("click", () =>
      runInboxExecAction(btn, q).catch((e) => showActionToast(humanizeUserError(e), true)),
    );
  });
}

let analyticsPeriod = "day";

function trackFeatureUsage(featureId) {
  const fid = String(featureId || "").trim();
  if (!fid || superadminNeedsCompany()) return;
  if (isSupportReadOnlySession() || window.WorkPassStorage?.isAuthUnusable?.()) return;
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

async function renderAttendanceInsightPanel(q) {
  const el = $("attendanceInsightPanel");
  if (!el) return;
  if (!q && getUser().role === "superadmin") {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = `<p class="muted">${t("common.loading")}</p>`;
  const [punctuality, behavior, overview] = await Promise.all([
    api(`/api/analytics/punctuality-report${q || ""}`).catch(() => null),
    api(`/api/analytics/behavior-patterns${q ? `${q}&` : "?"}days=14`).catch(() => null),
    api(`/api/v2/admin/overview${q || ""}`).catch(() => null),
  ]);
  const lateToday = punctuality?.lateWorkers || punctuality?.late_workers || [];
  const lateCount = Number(punctuality?.lateCount ?? punctuality?.late_count ?? lateToday.length ?? 0);
  const lateRate = behavior?.lateCheckinRate ?? behavior?.late_checkin_rate;
  const riskScore = behavior?.riskScore ?? behavior?.risk_score;
  const insights = behavior?.insights || [];
  const repeated = overview?.repeatedLateWorkers || [];
  const drivers = overview?.tomorrowForecast?.drivers || [];
  const driverItems = [];
  for (const d of drivers) {
    for (const item of d.items || []) {
      const nm = String(item.name || "").trim();
      if (nm && !driverItems.includes(nm)) driverItems.push(nm);
      if (driverItems.length >= 8) break;
    }
    if (driverItems.length >= 8) break;
  }
  el.innerHTML = `
    <div class="analytics-feature-grid">
      <div class="card">
        <h3 class="section-title">${t("analytics.punctualityTitle")}</h3>
        <p><strong>${lateCount}</strong> <span class="muted">${t("analytics.lateToday")}</span></p>
        ${
          lateToday.length
            ? `<ul class="analytics-list">${lateToday
                .slice(0, 8)
                .map(
                  (w) =>
                    `<li><strong>${escapeHtml(w.name || "")}</strong>
                    <span class="muted"> — ${escapeHtml(String(w.checkinTime || w.checkin_time || ""))}
                    ${w.minutesLate != null ? ` (+${w.minutesLate} ${t("analytics.minutes")})` : ""}</span></li>`,
                )
                .join("")}</ul>`
            : `<p class="muted">${t("analytics.noLateToday")}</p>`
        }
        <button type="button" class="btn-link" data-goto-tab="inbox">${t("overview.openInbox")}</button>
      </div>
      <div class="card">
        <h3 class="section-title">${t("analytics.behaviorTitle")}</h3>
        <p><strong>${lateRate != null ? `${Math.round(Number(lateRate) * 100)}%` : "—"}</strong>
          <span class="muted">${t("analytics.lateRate14d")}</span>
          ${riskScore != null ? ` · ${t("analytics.riskScore")}: <strong>${riskScore}</strong>` : ""}</p>
        ${
          insights.length
            ? `<ul class="analytics-list">${insights
                .slice(0, 6)
                .map((line) => `<li>${escapeHtml(String(line))}</li>`)
                .join("")}</ul>`
            : `<p class="muted">${t("analytics.noBehaviorRisk")}</p>`
        }
      </div>
      <div class="card">
        <h3 class="section-title">${t("overview.repeatedLateTitle")}</h3>
        ${
          repeated.length
            ? `<ul class="analytics-list">${repeated
                .map(
                  (w) =>
                    `<li><button type="button" class="btn-link attendance-open-worker" data-worker-id="${escapeAttr(String(w.workerId || ""))}">${escapeHtml(w.name || "")}</button>
                    <span class="muted"> — ${t("overview.repeatedLateStreak", { n: w.streak ?? 0 })}</span></li>`,
                )
                .join("")}</ul>`
            : `<p class="muted">${t("analytics.noRepeatedLate")}</p>`
        }
        ${
          driverItems.length
            ? `<p class="muted small" style="margin-top:0.6rem">${t("analytics.forecastAtRisk")}</p>
               <ul class="analytics-list">${driverItems.map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul>`
            : ""
        }
      </div>
    </div>`;
  el.querySelectorAll("[data-goto-tab=\"inbox\"]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      switchToTab("inbox");
      await loadInbox();
    });
  });
  el.querySelectorAll(".attendance-open-worker").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const workerId = String(btn.dataset.workerId || "").trim();
      switchToTab("workers");
      await loadWorkers();
      if (workerId) {
        try {
          await openDeploymentModal(workerId, btn.textContent || workerId);
        } catch (_) {
          /* ignore */
        }
      }
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
    (isSupportReadOnlySession() || window.WorkPassStorage?.isSupportAssistQuietMode?.())
      ? Promise.resolve({})
      : api(`/api/v2/admin/usage-stats${periodQs}`).catch(() => ({})),
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

  await renderAttendanceInsightPanel(q);

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
  if (shouldSkipSupportBackgroundLoads()) {
    $("statCards").innerHTML = `<p class="muted">${escapeHtml(t("common.loading") || "Live-Ansicht…")}</p>`;
    return;
  }
  if (getUser().role === "superadmin" && !q) {
    $("statCards").innerHTML = emptyStateHtml(t("common.selectCompany"));
    const bp = $("billingSummaryPanel");
    if (bp) {
      bp.classList.add("hidden");
      bp.innerHTML = "";
    }
    return;
  }
  const cid = activeCompanyId() || q.replace("?company_id=", "");
  const cacheKey = `${cid || "-"}:${q}`;
  const cached =
    loadOverview._cache?.key === cacheKey && Date.now() - (loadOverview._cache?.at || 0) < 20000
      ? loadOverview._cache.data
      : null;
  if (cached?.workforce) {
    const wf = cached.workforce || {};
    $("statCards").innerHTML = `
    <div class="card card-metric"><span class="muted">${t("overview.onSite")}</span><strong>${wf.onSite ?? 0}</strong></div>
    <div class="card card-metric"><span class="muted">${t("overview.activeWorkers")}</span><strong>${wf.totalActive ?? 0}</strong></div>
    <div class="card card-metric"><span class="muted">${t("overview.geofenceZones")}</span><strong>${cached.zonesCount ?? 0}</strong></div>`;
  } else {
    $("statCards").innerHTML = `
    <div class="card card-skeleton"><span class="muted">${t("overview.onSite")}</span><strong>…</strong></div>
    <div class="card card-skeleton"><span class="muted">${t("overview.activeWorkers")}</span><strong>…</strong></div>
    <div class="card card-skeleton"><span class="muted">${t("overview.geofenceZones")}</span><strong>…</strong></div>`;
  }
  const overviewP = apiSoft(`/api/v2/admin/overview${q}`, cached || null, 5000);
  const billingP = withTimeout(loadBillingSummaryPanel(cid), 4000, null);
  const secondaryP = Promise.all([
    withTimeout(fetchInboxCountsCached(q), 3500, { counts: {} }),
    apiSoft(`/api/dashboard/role${q}`, null, 3500),
    cid
      ? apiSoft(`/api/ops-os/summary?company_id=${encodeURIComponent(cid)}`, null, 3500)
      : Promise.resolve(null),
    apiSoft(`/api/operations/snapshot${q}`, null, 3500),
    apiSoft(`/api/integrations/cameras${q}`, { cameras: [] }, 3500),
    cid
      ? apiSoft(`/api/ops-os/daily-brief?company_id=${encodeURIComponent(cid)}`, null, 4000)
      : Promise.resolve(null),
    cid ? loadLegacyFeatures(cid) : Promise.resolve({}),
  ]);
  const overview = (await overviewP) || cached || {};
  loadOverview._cache = { key: cacheKey, at: Date.now(), data: overview };
  const wfEarly = overview.workforce || {};
  $("statCards").innerHTML = `
    <div class="card card-metric"><span class="muted">${t("overview.onSite")}</span><strong>${wfEarly.onSite ?? 0}</strong></div>
    <div class="card card-metric"><span class="muted">${t("overview.activeWorkers")}</span><strong>${wfEarly.totalActive ?? 0}</strong></div>
    <div class="card card-metric"><span class="muted">${t("overview.geofenceZones")}</span><strong>${overview.zonesCount ?? 0}</strong></div>
    <button type="button" class="card card-metric" data-goto-tab="inbox" style="cursor:pointer;text-align:start;border:1px solid var(--border)">
      <span class="muted">${t("overview.inbox")}</span><strong>…</strong>
      <small class="muted">${t("overview.inboxHint")}</small>
    </button>`;
  const [inbox, roleDash, opsBrief, opsSnap, cameras, dailyBrief, opsFeatures] = await secondaryP;
  const wf = overview.workforce || {};
  const openInbox = inbox?.counts?.open ?? 0;
  const dashWidgets = (roleDash?.widgets || []).filter((w) => w.id !== "on_site");
  const extraCards = dashWidgets
    .map(
      (w) =>
        `<div class="card card-metric"><span class="muted">${escapeHtml(widgetLabel(w))}</span><strong>${widgetValue(w)}</strong>${widgetDetail(w) ? `<small class="muted">${escapeHtml(widgetDetail(w))}</small>` : ""}</div>`,
    )
    .join("");
  $("statCards").innerHTML = `
    <div class="card card-metric"><span class="muted">${t("overview.onSite")}</span><strong>${wf.onSite ?? 0}</strong></div>
    <div class="card card-metric"><span class="muted">${t("overview.activeWorkers")}</span><strong>${wf.totalActive ?? 0}</strong></div>
    <div class="card card-metric"><span class="muted">${t("overview.geofenceZones")}</span><strong>${overview.zonesCount ?? 0}</strong></div>
    <button type="button" class="card card-metric" data-goto-tab="inbox" style="cursor:pointer;text-align:start;border:1px solid var(--border)">
      <span class="muted">${t("overview.inbox")}</span><strong style="color:${openInbox > 0 ? "var(--warn-accent,#fbbf24)" : "inherit"}">${openInbox}</strong>
      <small class="muted">${t("overview.inboxHint")}</small>
    </button>
    ${extraCards}
  `;
  $("statCards").querySelector('[data-goto-tab="inbox"]')?.addEventListener("click", async () => {
    switchToTab("inbox");
    await loadInbox();
  });
  await billingP;
  const fc = overview.tomorrowForecast || {};
  const repeatedLate = Array.isArray(overview.repeatedLateWorkers) ? overview.repeatedLateWorkers : [];
  const fp = $("forecastPanel");
  if (fp && (fc.date || repeatedLate.length)) {
    fp.classList.remove("hidden");
    const driverNames = [];
    for (const d of fc.drivers || []) {
      for (const item of d.items || []) {
        const nm = String(item.name || "").trim();
        if (nm && !driverNames.includes(nm)) driverNames.push(nm);
        if (driverNames.length >= 6) break;
      }
      if (driverNames.length >= 6) break;
    }
    const driversHtml = driverNames.length
      ? `<ul class="muted small" style="margin:0.4rem 0 0;padding-left:1.1rem">${driverNames
          .map((n) => `<li>${escapeHtml(n)}</li>`)
          .join("")}</ul>`
      : "";
    const lateHtml = repeatedLate.length
      ? `<div class="card forecast-card" style="margin-top:0.75rem;border-color:var(--warn-border,#b45309)">
          <div class="forecast-head">
            <span class="muted">${t("overview.repeatedLateTitle")}</span>
            <span class="badge">${repeatedLate.length}</span>
          </div>
          <p class="muted small" style="margin:0.35rem 0 0">${t("overview.repeatedLateHint")}</p>
          <p class="muted small" style="margin:0.5rem 0 0">
            <button type="button" class="btn-link" data-goto-tab="inbox" data-inbox-source="attendance">${t("overview.openInbox")}</button>
          </p>
        </div>`
      : "";
    fp.innerHTML = `
      ${
        fc.date
          ? `<div class="card forecast-card">
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
        ${driversHtml}
        <p class="muted small"><a href="/ai-command-center.html${q}">${t("ops.aiCenter")}</a> · <a href="/ops-command-center.html${q}">${t("ops.commandCenter")}</a></p>
      </div>`
          : ""
      }
      ${lateHtml}`;
    fp.querySelector("[data-goto-tab=\"inbox\"]")?.addEventListener("click", async () => {
      switchToTab("inbox");
      inboxSourceFilter = fp.querySelector("[data-goto-tab=\"inbox\"]")?.getAttribute("data-inbox-source") || "";
      await loadInbox();
    });
  } else if (fp) {
    fp.classList.add("hidden");
    fp.innerHTML = "";
  }
  const strip = $("opsCommandStrip");
  if (strip && cid) {
    strip.classList.remove("hidden");
    const twin = opsBrief?.layers?.["1_digital_twin"]?.summary || {};
    const sec = opsBrief?.layers?.["2_ai_security"] || {};
    const emg = opsBrief?.layers?.["5_emergency"] || {};
    const canCmd = opsSurfaceEnabled("commandCenter", opsFeatures);
    const canMap = opsSurfaceEnabled("liveMap", opsFeatures);
    const canAi = opsSurfaceEnabled("aiCenter", opsFeatures);
    const canForeman = opsSurfaceEnabled("foreman", opsFeatures);
    const canLayers = opsSurfaceEnabled("physicalOs", opsFeatures);
    const qs = q || `?company_id=${encodeURIComponent(cid)}`;
    strip.innerHTML = `
      <span class="ops-strip-kpi"><strong>${twin.workersOnSite ?? wf.onSite ?? 0}</strong> ${t("overview.onSiteKpi")}</span>
      ${opsSurfaceEnabled("security", opsFeatures) ? `<span class="ops-strip-kpi"><strong>${(sec.openAlerts || []).length}</strong> ${t("inbox.filterSecurity")}</span>` : ""}
      <span class="ops-strip-kpi">${emg.active ? t("overview.emergency") : t("overview.calm")}</span>
      ${canAccessWorkpassLohnUi() ? `<button type="button" class="ops-strip-lohn-btn" id="opsStripLohnLink">${t("lohn.opsLink")}<span id="opsStripLohnBadge" class="tab-badge hidden"></span></button>` : ""}
      ${canCmd ? `<a href="/ops-command-center.html${qs}" target="_blank" rel="noopener">${t("ops.commandCenter")}</a>` : ""}
      ${canMap ? `<a href="/ops-live-map.html${qs}" target="_blank" rel="noopener">${t("ops.liveMap")}</a>` : ""}
      ${canAi ? `<a href="/ai-command-center.html${qs}" target="_blank" rel="noopener">${t("ops.aiCenter")}</a>` : ""}
      ${canForeman ? `<a href="/foreman.html${qs}" target="_blank" rel="noopener">${t("overview.foreman")}</a>` : ""}
      ${canLayers ? `<button type="button" class="ghost ops-strip-tab" data-goto-tab="operations">${t("overview.layers12")}</button>` : ""}
    `;
    strip.querySelector(".ops-strip-tab")?.addEventListener("click", async () => {
      switchToTab("operations");
      await loadOperations();
    });
    strip.querySelector("#opsStripLohnLink")?.addEventListener("click", () => {
      if (!canAccessWorkpassLohnUi()) return;
      openLohnDrawer().catch(() => {});
    });
    if (canAccessWorkpassLohnUi()) {
      refreshLohnBadgeOnly()
        .then(() => {
          const n = Number($("lohnOpsBadge")?.textContent || 0);
          paintLohnBadge($("opsStripLohnBadge"), n);
        })
        .catch(() => {});
    } else {
      updateLohnNavBadge(0);
      paintLohnBadge($("opsStripLohnBadge"), 0);
    }
  } else if (strip) {
    strip.classList.add("hidden");
  }

  const lage = $("lagePanel");
  if (lage && cid) {
    const twin = opsBrief?.layers?.["1_digital_twin"]?.summary || {};
    const sec = opsBrief?.layers?.["2_ai_security"] || {};
    const camList = Array.isArray(cameras?.cameras) ? cameras.cameras : [];
    const camsOnline = camList.filter((c) => c.online).length;
    const watch = cameras?.watch || cameras?.summary || {};
    const watchActive = !!watch.watchModeActive;
    const watchEnabled = watch.enabled !== false && watch.watchEnabled !== false;
    const camLayer = opsBrief?.layers?.["6_camera_ai"] || {};
    const att = dailyBrief?.attendance || {};
    const secBrief = dailyBrief?.security || {};
    const chatBrief = dailyBrief?.chat || {};
    const hrBrief = dailyBrief?.hr || {};
    const openEsc = Number(secBrief.openCameraEscalations ?? camLayer.openEscalations ?? 0);
    const chatOpen = Number(chatBrief.totalOpen || 0);
    const missedCallsOpen = Number(chatBrief.missedCallsOpen || 0);
    const callbackOpen = Number(chatBrief.callbackRequestsOpen || 0);
    const hrOpen = Number(hrBrief.totalOpen || 0);
    const pendingLeave = Number(hrBrief.pendingLeave || 0);
    const expiringDocs = Number(hrBrief.expiringDocuments || 0);
    const inReviewDocs = Number(hrBrief.inReviewDocuments || 0);
    const onSite = att.onSite ?? opsSnap?.workersOnSite ?? twin.workersOnSite ?? wf.onSite ?? 0;
    const checkIns = att.checkInsToday ?? opsSnap?.checkInsToday ?? opsSnap?.checkinsToday ?? 0;
    const lateToday = Number(att.lateToday || 0);
    const outsideToday = Number(att.outsideHoursAttemptsToday || 0);
    const missingToday = Number(att.missingExpected || 0);
    const expectedToday = Number(att.expectedToday || 0);
    const workWin = att.workWindow || {};
    const workWinLabel = workWin.configured
      ? `${workWin.start || "—"}–${workWin.end || "—"}`
      : t("lage.workWindowFlexible");
    const securityOpen = Number(
      secBrief.totalOpen ?? (sec.openAlerts || []).length + openEsc,
    );
    const aiPrompt = encodeURIComponent(
      "Fasse die aktuelle Lage zusammen: Anwesenheit (fehlt/spät/außerhalb), Security, Chat/Anrufe, Urlaub, ablaufende Dokumente und offene Aufgaben.",
    );
    lage.classList.remove("hidden");
    const liveBadge = window.__adminRealtimeLive
      ? `<span class="badge badge-ok">${t("lage.live")}</span>`
      : `<span class="badge">${t("lage.poll")}</span>`;
    const watchBadge = watchActive
      ? `<span class="badge badge-warn">${t("lage.watchActive")}</span>`
      : watchEnabled
        ? `<span class="badge">${t("lage.watchStandby")}</span>`
        : `<span class="badge">${t("lage.watchOff")}</span>`;
    const openInboxFromLage = async (source = "") => {
      switchToTab("inbox");
      inboxSourceFilter = source || "";
      await loadInbox();
    };

    lage.innerHTML = `
      <div class="lage-panel-head">
        <div>
          <h3>${t("lage.title")}</h3>
          <p class="muted small" style="margin:0.2rem 0 0">${t("lage.subtitle")}</p>
        </div>
        <div style="display:flex;gap:0.35rem;align-items:center;flex-wrap:wrap">${liveBadge}${watchBadge}</div>
      </div>
      <p class="muted small lage-inbox-hint">${escapeHtml(t("lage.inboxHint", { window: workWinLabel }))}</p>
      <div class="lage-grid">
        ${renderLageKpi({ id: "onSite", label: t("lage.onSite"), value: onSite, tone: lageToneForCount(onSite, { invert: true, warnAt: 1 }), gotoTab: "access", hint: t("lage.openAccess") })}
        ${renderLageKpi({ id: "checkIns", label: t("lage.checkIns"), value: checkIns, tone: "info", gotoTab: "access", hint: t("lage.openAccess") })}
        ${renderLageKpi({ id: "expected", label: t("lage.expectedToday"), value: expectedToday, tone: "info", gotoTab: "access", hint: t("lage.openAccess") })}
        ${renderLageKpi({ id: "missing", label: t("lage.missingToday"), value: missingToday, tone: lageToneForCount(missingToday), inboxSource: "attendance" })}
        ${renderLageKpi({ id: "late", label: t("lage.lateToday"), value: lateToday, tone: lageToneForCount(lateToday), inboxSource: "attendance" })}
        ${renderLageKpi({ id: "outside", label: t("lage.outsideHours"), value: outsideToday, tone: lageToneForCount(outsideToday), inboxSource: "attendance" })}
        ${opsSurfaceEnabled("cameras", opsFeatures) ? renderLageKpi({ id: "cameras", label: t("lage.camerasOnline"), value: `${camsOnline}/${camList.length}`, tone: camsOnline < camList.length ? "warn" : "ok", href: `/admin-v2/camera-watch.html${q}` }) : ""}
        ${opsSurfaceEnabled("security", opsFeatures) ? renderLageKpi({ id: "security", label: t("lage.security"), value: securityOpen, tone: lageToneForCount(securityOpen), inboxSource: "security" }) : ""}
        ${renderLageKpi({ id: "chat", label: t("lage.chatOpen"), value: chatOpen, tone: lageToneForCount(chatOpen), inboxSource: "chat" })}
        ${renderLageKpi({ id: "hr", label: t("lage.hrOpen"), value: hrOpen, tone: lageToneForCount(hrOpen), inboxSource: "leave" })}
        ${renderLageKpi({ id: "inbox", label: t("lage.inbox"), value: openInbox, tone: lageToneForCount(openInbox), inboxSource: "" })}
      </div>
      <div class="lage-actions">
        <button type="button" class="ghost" data-goto-tab="inbox">${t("overview.openInbox")}</button>
        <a href="/admin-v2/chat.html${q}" target="_blank" rel="noopener">${t("lage.openChat")}</a>
        ${opsSurfaceEnabled("cameras", opsFeatures) ? `<a href="/admin-v2/camera-watch.html${q}">${t("cameraWatch.open")}</a>` : ""}
        <button type="button" class="ghost" data-goto-tab="access">${t("lage.openAccess")}</button>
        ${opsSurfaceEnabled("liveMap", opsFeatures) ? `<a href="/ops-live-map.html${q}" target="_blank" rel="noopener">${t("lage.openMap")}</a>` : ""}
        ${opsSurfaceEnabled("aiCenter", opsFeatures) ? `<a href="/ai-command-center.html${q}${q ? "&" : "?"}autoprompt=${aiPrompt}" target="_blank" rel="noopener">${t("lage.aiAsk")}</a>` : ""}
      </div>
      ${
        opsSurfaceEnabled("liveMap", opsFeatures) && !isSupportReadOnlySession()
          ? `<div class="lage-map-embed" id="lageMapEmbed" title="${escapeAttr(t("lage.mapScrollHint") || "Klicken zum Interagieren · Scrollen bewegt die Seite")}">
        <p class="lage-map-embed-hint">${escapeHtml(t("lage.mapScrollHint") || "Klicken für Karte · Mausrad scrollt die Seite")}</p>
        <iframe
          title="${escapeAttr(t("lage.openMap"))}"
          loading="lazy"
          referrerpolicy="same-origin"
          src="/ops-live-map.html${q ? `${q}&embed=1` : `?embed=1`}"
        ></iframe>
      </div>`
          : ""
      }
    `;

    const mapEmbed = lage.querySelector("#lageMapEmbed");
    if (mapEmbed) {
      mapEmbed.addEventListener("click", () => {
        mapEmbed.classList.add("is-interactive");
      });
      mapEmbed.addEventListener("mouseleave", () => {
        mapEmbed.classList.remove("is-interactive");
      });
    }
    lage.querySelectorAll("[data-goto-tab]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const tab = btn.getAttribute("data-goto-tab");
        if (tab === "inbox") {
          await openInboxFromLage(btn.getAttribute("data-inbox-source") || "");
          return;
        }
        switchToTab(tab);
        if (tab === "access") await loadAccess();
      });
    });
    lage.querySelectorAll("[data-href]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const href = btn.getAttribute("data-href");
        if (href) window.location.href = href;
      });
    });
  } else if (lage) {
    lage.classList.add("hidden");
    lage.innerHTML = "";
  }

  renderTable($("recentAccess"), overview.recentAccess || [], [
    { label: t("table.worker"), render: (r) => `${r.first_name || ""} ${r.last_name || ""}`.trim() },
    { label: t("workers.colBadge"), render: (r) => r.badge_id || "-" },
    {
      label: t("table.direction"),
      render: (r) => formatAccessDirection(r.direction),
    },
    { label: t("table.gate"), render: (r) => r.gate || "-" },
    { label: t("table.time"), render: (r) => formatAccessTimestamp(r.timestamp) },
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
    $("workersTable").innerHTML = emptyStateHtml(t("common.selectCompany"));
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
      container.innerHTML = emptyStateHtml(t("common.noWorkers"), t("common.noDataHint") || "");
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
            <button type="button" class="worker-action-btn worker-action-btn-ghost" data-worker-write="${id}" data-worker-name="${name.replace(/"/g, "&quot;")}">${t("workers.writeDoc")}</button>
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
      const url = new URL("/admin-v2/contracts.html", location.origin);
      const cid = (wpGet(COMPANY_KEY) || "").trim();
      if (cid) url.searchParams.set("company_id", cid);
      if (wid) url.searchParams.set("worker_id", wid);
      location.href = `${url.pathname}${url.search}`;
    });
  });
  container.querySelectorAll("[data-worker-write]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const wid = btn.getAttribute("data-worker-write");
      const wname = btn.getAttribute("data-worker-name") || "";
      const url = new URL("/admin-v2/docs.html", location.origin);
      const cid = (wpGet(COMPANY_KEY) || "").trim();
      if (cid) url.searchParams.set("company_id", cid);
      if (wid) url.searchParams.set("worker_id", wid);
      if (wname) url.searchParams.set("title", `Schreiben · ${wname}`);
      location.href = `${url.pathname}${url.search}`;
    });
  });
  } catch (error) {
    $("workersTable").innerHTML = `<p class="muted" style="padding:1rem">${error?.message || "Mitarbeiter konnten nicht geladen werden."}</p>`;
  }
}

async function loadAccess() {
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    $("accessTable").innerHTML = emptyStateHtml(t("common.selectCompany"));
    $("accessSummary").innerHTML = "";
    return;
  }
  try {
    const summary = await api(`/api/access-logs/summary${q}`);
    const open = Array.isArray(summary.openEntries) ? summary.openEntries.length : 0;
    const hourly = Array.isArray(summary.hourly) ? summary.hourly : [];
    // Prefer explicit today KPIs from API (hourly is today-scoped since fix).
    const sumHourly = (key) => hourly.reduce((n, h) => n + (Number(h[key]) || 0), 0);
    const checkIns = Number(summary.checkInsToday ?? sumHourly("checkIn"));
    const checkOuts = Number(summary.checkOutsToday ?? sumHourly("checkOut"));
    const appLogins = Number(summary.appLoginsToday ?? sumHourly("appLogin"));
    const appLogouts = Number(summary.appLogoutsToday ?? sumHourly("appLogout"));
    const lateToday = Number(summary.lateCheckInsToday || 0);
    const hasToday = summary.hasActivityToday === true || checkIns + checkOuts + appLogins + appLogouts > 0;
    const lastCheckIn = summary.lastCheckInAt || summary.lastActivityAt || "";
    const lastLabel = lastCheckIn ? formatAccessTimestamp(lastCheckIn) : "";
    const todayLabel = summary.today || "";
    const quietHint = !hasToday
      ? `<p class="access-today-hint muted small">${
          lastLabel
            ? t("access.noActivityTodayLast", { last: lastLabel, today: todayLabel })
            : t("access.noActivityToday")
        }</p>`
      : todayLabel
        ? `<p class="access-today-hint muted small">${t("access.todayScope", { today: todayLabel })}</p>`
        : "";
    const card = (label, value, isQuiet) =>
      `<div class="card${isQuiet && Number(value) === 0 ? " card-quiet" : ""}"><span class="muted">${label}</span><strong>${value}</strong></div>`;
    $("accessSummary").innerHTML = `
      ${quietHint}
      ${card(t("access.checkIns"), checkIns, !hasToday)}
      ${card(t("access.checkOuts"), checkOuts, !hasToday)}
      ${card(t("access.appLoginsToday"), appLogins, !hasToday)}
      ${card(t("access.appLogoutsToday"), appLogouts, !hasToday)}
      ${card(t("access.openSessions"), open, false)}
      ${card(t("access.lateCheckIns"), lateToday, !hasToday)}
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
        .catch((err) => alert(humanizeUserError(err)));
    };
  }
  const data = await api(`/api/v2/access/live${q}`);
  const logs = data.access_logs || [];
  const tableHost = $("accessTable");
  renderTable(tableHost, logs, [
    { label: t("table.worker"), render: (r) => `${r.first_name || ""} ${r.last_name || ""}`.trim() },
    { label: t("table.direction"), render: (r) => formatAccessDirection(r.direction) },
    { label: t("table.gate"), render: (r) => r.gate || "-" },
    { label: t("table.time"), render: (r) => formatAccessTimestamp(r.timestamp) },
    {
      label: t("access.late"),
      render: (r) =>
        r.direction === "check-in" && Number(r.checked_in_late || 0) === 1
          ? `<span class="badge badge-warn">${t("access.lateYes")}</span>`
          : "—",
    },
  ]);
  if (tableHost && logs.length) {
    const caption = document.createElement("p");
    caption.className = "muted small access-table-caption";
    caption.textContent = t("access.recentBookings");
    tableHost.prepend(caption);
  }
}

async function loadAudit() {
  const list = $("auditList");
  const summaryHost = $("auditSummaryCards");
  const detail = $("auditDetail");
  if (!list) return;
  list.innerHTML = `<p class="muted">${t("common.loading")}</p>`;
  if (detail) {
    detail.classList.add("hidden");
    detail.textContent = "";
  }
  closeAuditDetailModal();
  const params = new URLSearchParams();
  const q = ($("auditQ")?.value || "").trim();
  const eventType = ($("auditEventType")?.value || "").trim();
  const actorRole = ($("auditActorRole")?.value || "").trim();
  const from = ($("auditFrom")?.value || "").trim();
  const to = ($("auditTo")?.value || "").trim();
  if (q) params.set("q", q);
  if (eventType) params.set("eventType", eventType);
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  params.set("limit", "150");
  const companySel = $("auditCompanyFilter");
  const actorRoleSel = $("auditActorRole");
  let companyNameById = {};
  if (isSuperadminUser()) {
    if (actorRoleSel) actorRoleSel.classList.remove("hidden");
    if (actorRole) params.set("actorRole", actorRole);
    if (companySel) {
      companySel.classList.remove("hidden");
      if (!companySel.dataset.ready) {
        try {
          const companies = await api("/api/companies").catch(() => []);
          const items = Array.isArray(companies) ? companies : companies.items || [];
          companyNameById = Object.fromEntries(items.map((c) => [c.id, c.name || c.id]));
          companySel.innerHTML =
            `<option value="">${t("section.audit.allCompanies")}</option>` +
            items
              .map((c) => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.name || c.id)}</option>`)
              .join("");
          companySel.dataset.ready = "1";
          companySel._nameById = companyNameById;
        } catch {
          companySel.innerHTML = `<option value="">${t("section.audit.allCompanies")}</option>`;
        }
      } else {
        companyNameById = companySel._nameById || {};
      }
      const cid = companySel.value || "";
      if (cid) params.set("companyId", cid);
    }
  } else {
    if (actorRoleSel) actorRoleSel.classList.add("hidden");
    const cid = activeCompanyId();
    if (cid) params.set("companyId", cid);
  }
  try {
    const qs = params.toString();
    const summaryQs = new URLSearchParams();
    const summaryCid = params.get("companyId");
    if (summaryCid) summaryQs.set("companyId", summaryCid);
    summaryQs.set("days", "7");
    const [data, summary] = await Promise.all([
      api(`/api/audit-events?${qs}`),
      api(`/api/audit-events/summary?${summaryQs.toString()}`).catch(() => null),
    ]);
    if (summaryHost && summary) {
      const topTypes = (summary.byEventType || [])
        .slice(0, 4)
        .map((x) => `<li>${escapeHtml(x.eventType)} · <strong>${x.count}</strong></li>`)
        .join("");
      const topActors = (summary.byActor || [])
        .slice(0, 4)
        .map((x) => `<li>${escapeHtml(x.actor)} · <strong>${x.count}</strong></li>`)
        .join("");
      const companyBlock =
        isSuperadminUser() && (summary.byCompany || []).length
          ? `<div class="card"><h3>${t("section.audit.byCompany")}</h3><ul class="muted small">${(summary.byCompany || [])
              .slice(0, 5)
              .map((c) => {
                const label = c.companyName || companyNameById[c.companyId] || c.companyId || "—";
                return `<li>${escapeHtml(label)} · <strong>${c.count}</strong></li>`;
              })
              .join("")}</ul></div>`
          : "";
      summaryHost.innerHTML = `
        <div class="card"><h3>${t("section.audit.total7d")}</h3><p class="stat">${summary.total ?? 0}</p></div>
        <div class="card"><h3>${t("section.audit.topEvents")}</h3><ul class="muted small">${topTypes || "<li>—</li>"}</ul></div>
        <div class="card"><h3>${t("section.audit.topActors")}</h3><ul class="muted small">${topActors || "<li>—</li>"}</ul></div>
        ${companyBlock}
      `;
    }
    const events = data.events || data.logs || [];
    const cols = [
      {
        label: t("section.audit.when"),
        render: (r) => escapeHtml(String(r.createdAt || r.created_at || "").slice(0, 19)),
      },
      {
        label: t("section.audit.who"),
        render: (r) =>
          escapeHtml(r.actorName || r.actor_name || r.actorUserId || r.actor_user_id || r.actorRole || r.actor_role || "—"),
      },
      {
        label: t("section.audit.what"),
        render: (r) => escapeHtml(humanizeAuditEventType(r.eventType || r.event_type || "")),
      },
      {
        label: t("section.audit.message"),
        render: (r) => escapeHtml(String(r.message || "").slice(0, 120)),
      },
      {
        label: t("section.audit.why"),
        render: (r) => escapeHtml(String(r.reason || "—").slice(0, 80)),
      },
    ];
    if (isSuperadminUser()) {
      cols.splice(1, 0, {
        label: t("section.audit.company"),
        render: (r) => {
          const cid = r.companyId || r.company_id || "";
          return escapeHtml(companyNameById[cid] || cid || "—");
        },
      });
    }
    cols.push({
      label: "",
      render: (r) => {
        const idx = events.indexOf(r);
        return `<button type="button" class="ghost small" data-audit-id="${escapeHtml(String(r.id ?? ""))}" data-audit-idx="${idx >= 0 ? idx : 0}">${t("section.audit.details")}</button>`;
      },
    });
    renderTable(list, events, cols);
    list.querySelectorAll("[data-audit-id]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const id = String(btn.getAttribute("data-audit-id") || "");
        const idx = Number(btn.getAttribute("data-audit-idx"));
        const row =
          events.find((e) => String(e.id) === id) ||
          (Number.isFinite(idx) ? events[idx] : null);
        if (!row) {
          showActionToast(t("section.audit.detailsMissing") || "Eintrag nicht gefunden", true);
          return;
        }
        openAuditDetailModal(row);
      });
    });
    const exportLink = $("auditExportLink");
    if (exportLink) {
      exportLink.href = `/api/audit-logs/export.csv?${qs}`;
      exportLink.onclick = (e) => {
        e.preventDefault();
        const token = (wpGet(TOKEN_KEY) || "").trim();
        fetch(exportLink.href, { headers: { Authorization: `Bearer ${token}` } })
          .then((r) => r.blob())
          .then((blob) => {
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "audit-events.csv";
            a.click();
            URL.revokeObjectURL(url);
          })
          .catch((err) => alert(humanizeUserError(err)));
      };
    }
  } catch (e) {
    list.innerHTML = `<p class="error">${escapeHtml(e.message || "error")}</p>`;
  }
}

$("auditFilterForm")?.addEventListener("submit", (e) => {
  e.preventDefault();
  loadAudit().catch((err) => showActionToast(err.message, true));
});
$("auditCompanyFilter")?.addEventListener("change", () => {
  loadAudit().catch((err) => showActionToast(err.message, true));
});

function closeAuditDetailModal() {
  document.getElementById("auditDetailModal")?.remove();
}

function humanizeAuditEventType(eventType) {
  const raw = String(eventType || "").trim();
  if (!raw) return "—";
  const key = `section.audit.event.${raw}`;
  const localized = t(key);
  if (localized && localized !== key) return localized;
  // contract.create → Contract create
  return raw
    .replace(/[._]+/g, " ")
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function openAuditDetailModal(row) {
  closeAuditDetailModal();
  const when = String(row.createdAt || row.created_at || "").slice(0, 19).replace("T", " ");
  const whoName =
    row.actorName || row.actor_name || row.actorUserId || row.actor_user_id || "—";
  const whoRole = row.actorRole || row.actor_role || "";
  const eventType = row.eventType || row.event_type || "";
  const companyId = row.companyId || row.company_id || "";
  const nameById = $("auditCompanyFilter")?._nameById || {};
  const companyLabel = nameById[companyId] || companyId || "";
  const targetType = row.targetType || row.target_type || "";
  const targetId = row.targetId || row.target_id || "";
  const message = String(row.message || "").trim();
  const reason = String(row.reason || "").trim();
  const detailsObj =
    row.details && typeof row.details === "object"
      ? row.details
      : (() => {
          try {
            const parsed = JSON.parse(row.details || "{}");
            return typeof parsed === "object" && parsed ? parsed : {};
          } catch {
            return {};
          }
        })();

  const rows = [];
  const push = (label, value) => {
    if (value === undefined || value === null || value === "") return;
    rows.push(
      `<tr><th scope="row">${escapeHtml(label)}</th><td>${escapeHtml(String(value))}</td></tr>`,
    );
  };
  push(t("section.audit.when"), when);
  push(t("section.audit.who"), whoRole ? `${whoName} (${whoRole})` : whoName);
  push(t("section.audit.what"), humanizeAuditEventType(eventType));
  if (companyLabel && isSuperadminUser()) push(t("section.audit.company"), companyLabel);
  push(t("section.audit.message"), message);
  push(t("section.audit.why"), reason);
  if (targetType || targetId) {
    push(
      t("section.audit.target"),
      [targetType, targetId].filter(Boolean).join(" · "),
    );
  }
  // A few common detail fields in plain language (skip nested objects / ids)
  for (const [k, v] of Object.entries(detailsObj)) {
    if (v == null || typeof v === "object") continue;
    if (/^(id|userId|workerId|companyId|token|password|key)$/i.test(k)) continue;
    if (String(v).length > 160) continue;
    const label = k.replace(/[._]+/g, " ").replace(/\b\w/g, (ch) => ch.toUpperCase());
    push(label, v);
    if (rows.length >= 12) break;
  }

  const payload = {
    id: row.id,
    eventType,
    when: row.createdAt || row.created_at,
    who: {
      id: row.actorUserId || row.actor_user_id,
      name: row.actorName || row.actor_name,
      role: whoRole,
      ip: row.ipAddress || row.ip_address,
    },
    companyId,
    target: { type: targetType, id: targetId },
    message,
    reason,
    details: detailsObj,
  };
  const pretty = JSON.stringify(payload, null, 2);
  const showTech = isSuperadminUser();
  const inline = $("auditDetail");
  if (inline) {
    inline.classList.add("hidden");
    inline.textContent = "";
  }
  const modal = document.createElement("div");
  modal.id = "auditDetailModal";
  modal.className = "audit-detail-modal";
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  modal.innerHTML = `
    <div class="audit-detail-modal-card">
      <div class="audit-detail-modal-head">
        <h3>${escapeHtml(t("section.audit.details") || "Details")}</h3>
        <button type="button" class="ghost small" data-audit-close aria-label="${escapeAttr(t("common.close") || "Schließen")}">×</button>
      </div>
      <p class="muted small">${escapeHtml(humanizeAuditEventType(eventType))} · ${escapeHtml(when || "—")}</p>
      <table class="audit-detail-facts"><tbody>${rows.join("") || `<tr><td class="muted">${escapeHtml(t("ops.noDetailData"))}</td></tr>`}</tbody></table>
      ${
        showTech
          ? `<details class="audit-tech-details">
        <summary>${escapeHtml(t("section.audit.techDetails"))}</summary>
        <pre class="audit-detail-pre">${escapeHtml(pretty)}</pre>
      </details>`
          : ""
      }
      <div class="audit-detail-modal-actions">
        ${showTech ? `<button type="button" class="ghost" data-audit-copy>${escapeHtml(t("section.audit.copy") || "Kopieren")}</button>` : ""}
        <button type="button" data-audit-close>${escapeHtml(t("common.close") || "Schließen")}</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  const close = () => closeAuditDetailModal();
  modal.addEventListener("click", (e) => {
    if (e.target === modal) close();
  });
  modal.querySelectorAll("[data-audit-close]").forEach((btn) => btn.addEventListener("click", close));
  modal.querySelector("[data-audit-copy]")?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(pretty);
      showActionToast(t("section.audit.copied") || "Kopiert");
    } catch {
      showActionToast(t("section.audit.copyFailed") || "Kopieren fehlgeschlagen", true);
    }
  });
  document.addEventListener(
    "keydown",
    function onEsc(e) {
      if (e.key === "Escape") {
        close();
        document.removeEventListener("keydown", onEsc);
      }
    },
    { once: true },
  );
}

async function loadCopilot() {
  const answerEl = $("copilotAnswer");
  if (!answerEl) return;
  answerEl.textContent = t("section.copilot.idle");
  const host = $("copilotQuickActions");
  if (!host) return;
  const actions = [
    { id: "lage", label: t("copilot.actionLage"), q: t("copilot.promptLage") },
    { id: "late", label: t("copilot.actionLate"), q: t("copilot.promptLate") },
    { id: "security", label: t("copilot.actionSecurity"), q: t("copilot.promptSecurity") },
    { id: "camera", label: t("copilot.actionCamera"), q: t("copilot.promptCamera") },
    { id: "chat", label: t("copilot.actionChat"), q: t("copilot.promptChat") },
    { id: "hr", label: t("copilot.actionHr"), q: t("copilot.promptHr") },
  ];
  host.innerHTML = actions
    .map(
      (a) =>
        `<button type="button" class="inbox-filter-chip" data-copilot-q="${escapeAttr(a.q)}">${escapeHtml(a.label)}</button>`,
    )
    .join("");
  host.querySelectorAll("[data-copilot-q]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const ta = $("copilotQuestion");
      if (ta) ta.value = btn.getAttribute("data-copilot-q") || "";
      $("copilotForm")?.requestSubmit?.();
    });
  });
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
    if (answerEl) {
      const text = lines.filter(Boolean).join("\n\n").trim();
      if (!text || text === "—" || text === "{}") {
        answerEl.textContent = t("section.copilot.emptyAnswer");
      } else {
        answerEl.textContent = text;
      }
    }
  } catch (err) {
    const msg = String(err?.message || err || "");
    const low = msg.toLowerCase();
    if (answerEl) {
      if (low.includes("quota") || low.includes("openai_quota") || low.includes("guthaben")) {
        answerEl.textContent = t("section.copilot.quotaHint");
      } else {
        answerEl.textContent = msg || t("section.copilot.emptyAnswer");
      }
    }
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
  if (shouldSkipSupportBackgroundLoads()) {
    return;
  }
  const active = document.querySelector(".tab.active");
  const tab = active?.dataset?.tab || "overview";
  if (tab === "inbox") {
    await loadInbox();
    await startAdminRealtime();
  }
  else if (tab === "audit") await loadAudit();
  else if (tab === "copilot") await loadCopilot();
  else if (tab === "workers") await loadWorkers();
  else if (tab === "access") await loadAccess();
  else if (tab === "mobile") await loadMobile();
  else if (tab === "operations") await loadOperations();
  else if (tab === "billing") await loadBillingTab();
  else if (tab === "platform") await loadPlatform();
  else if (tab === "tools") await loadTools();
  else if (tab === "analytics") await loadAnalytics();
  else if (tab === "enterprise") syncEnterpriseFrame();
  else await loadOverview();
}

function waitForEmbedParentToken(timeoutMs) {
  const existing = String(wpGet(TOKEN_KEY) || WP?.readSessionToken?.() || "").trim();
  if (existing) return Promise.resolve(existing);
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => {
      window.removeEventListener("message", onMsg);
      resolve(String(wpGet(TOKEN_KEY) || WP?.readSessionToken?.() || "").trim());
    }, Math.max(200, Number(timeoutMs) || 1500));
    function onMsg(event) {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type !== "baupass-sync-token" || !event.data.token) return;
      window.clearTimeout(timer);
      window.removeEventListener("message", onMsg);
      resolve(String(event.data.token || "").trim());
    }
    window.addEventListener("message", onMsg);
  });
}

async function bootSession() {
  showSessionBoot();
  const forceLoginForm = new URLSearchParams(location.search).get("login") === "1";
  let embedSessionOk = false;
  if (isEmbedMode()) {
    embedSessionOk = await tryEmbedSessionFromControlPass();
  }
  let token = String(WP?.readSessionToken?.() || wpGet(TOKEN_KEY) || "").trim();
  if (forceLoginForm && !isEmbedMode()) {
    showLogin();
    return;
  }
  if (isEmbedMode() && window.WorkPassStorage?.isAuthUnusable?.()) {
    showEmbedAuthRequired(t("login.embedRequired"));
    return;
  }
  if (
    !token
    && isEmbedMode()
    && (window.WorkPassStorage?.hasActiveSupportTabScope?.() || window.WorkPassStorage?.isSupportAssistQuietMode?.())
  ) {
    token = await waitForEmbedParentToken(4500);
    if (token) {
      WP?.clearAuthUnusable?.();
      if (WP?.persistSessionToken) WP.persistSessionToken(token);
      wpSet(TOKEN_KEY, token);
      wpSet(CONTROL_TOKEN_KEY, token);
    }
  }
  if (!embedSessionOk && (!token || !(await probeSessionToken(token)))) {
    const adopted = await adoptControlPassTokenIfValid();
    if (adopted) {
      token = wpGet(TOKEN_KEY);
    }
  }
  if (!embedSessionOk && (!token || !(await probeSessionToken(token)))) {
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
    if (!embedSessionOk) {
      const data = await api("/api/v2/auth/session");
      if (data.user) {
        wpSet(USER_KEY, JSON.stringify(data.user));
        if (data.user.company_id && !wpGet(COMPANY_KEY)) {
          wpSet(COMPANY_KEY, data.user.company_id);
        }
      }
    }
    await loadCompanies();
    const qsCid = new URLSearchParams(location.search).get("company_id") || "";
    if (qsCid) {
      applyParentCompanyId(qsCid);
    }
    showDashboard();
    await Promise.all([
      applyTenantBrandingFromApi().catch(() => {}),
      loadPlatformBanner().catch(() => {}),
    ]);
    await applyStartupTabAfterLoad();
    if (pendingEinsatzplanFocus) {
      tryFocusEinsatzplanFromParent();
    }
    const params = new URLSearchParams(location.search);
    if (params.get("einsatzplan") !== "1" && params.get("focus") !== "deployment") {
      refreshActiveTab().catch(notifyTabError);
    }
    if (!isSupportReadOnlySession() && !window.WorkPassStorage?.isSupportAssistQuietMode?.()) {
      startAdminRealtime().catch(() => {});
      refreshInboxBadgeOnly().catch(() => {});
      maybePromptSatisfactionSurvey().catch(() => {});
      if (!window.__lohnBadgePoll) {
        window.__lohnBadgePoll = setInterval(() => {
          refreshLohnBadgeOnly().catch(() => {});
        }, 45000);
      }
    }
    wireLohnDrawer();
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
    wireLohnDrawer();
    if (!window.__lohnBadgePoll) {
      window.__lohnBadgePoll = setInterval(() => {
        refreshLohnBadgeOnly().catch(() => {});
      }, 45000);
    }
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
  // Debounce: language events must not hammer Platform-Link / Ops remounts.
  clearTimeout(window.__adminLangRefreshT);
  window.__adminLangRefreshT = setTimeout(() => {
    refreshActiveTab().catch(() => {});
  }, 350);
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
bindLegacyDashboardLinks();
if (window.BaupassAuth?.loadPublicTenantBranding) {
  void window.BaupassAuth.loadPublicTenantBranding();
}
bindSurveyInvitePanelActions();
