/**
 * WorkPass browser storage — canonical workpass-* keys with baupass-* legacy migration.
 * Load before app.js, worker-app.js, admin-v2/app.js, and inline storage scripts.
 */
(function workpassStorageModule(global) {
  "use strict";

  const MIGRATION_FLAG = "workpass-storage-migrated-v2";

  /** @type {Record<string, string>} canonical → legacy localStorage key */
  const LEGACY_BY_CANONICAL = {
    "workpass-api-base": "baupass-api-base",
    "workpass-session-token": "baupass-control-token",
    "workpass-support-login-context": "baupass-support-login-context",
    "workpass-support-phone": "baupass-support-phone",
    "workpass-ui-lang": "baupass-ui-lang",
    "workpass-invoice-filters-v1": "baupass-invoice-filters-v1",
    "workpass-system-theme": "baupass-system-theme",
    "workpass-system-theme-color": "baupass-system-theme-color",
    "workpass-worker-form-defaults-v1": "baupass-worker-form-defaults-v1",
    "workpass-greeting-date": "baupass-greeting-date",
    "workpass-preview-company-id": "baupass-preview-company-id",
    "workpass-build-tag": "baupass-control-build",
    "workpass-admin-company": "baupass-admin-v2-company",
    "workpass-admin-token": "baupass-admin-v2-token",
    "workpass-admin-user": "baupass-admin-v2-user",
    "workpass-admin-lang": "baupass-admin-v2-lang",
    "workpass-worker-token": "baupass-worker-token",
    "workpass-worker-access-token": "baupass-worker-access-token",
    "workpass-worker-badge-login": "baupass-worker-badge-login",
    "workpass-last-local-photo": "baupass-last-local-photo",
    "workpass-offline-photo-queue": "baupass-offline-photo-queue",
    "workpass-offline-event-queue": "baupass-offline-event-queue",
    "workpass-worker-offline-login-profile": "baupass-worker-offline-login-profile",
    "workpass-qr-high-contrast": "baupass-qr-high-contrast",
    "workpass-auto-open-scanner": "baupass-auto-open-scanner",
    "workpass-worker-cached-payload": "baupass-worker-cached-payload",
    "workpass-worker-lang": "baupass-worker-lang",
    "workpass-worker-theme": "baupass-worker-theme",
    "workpass-worker-day-planner": "baupass-worker-day-planner",
    "workpass-smart-hub-notify": "baupass-smart-hub-notify",
    "workpass-notification-history": "baupass-notification-history",
    "workpass-sync-conflicts": "baupass-sync-conflicts",
    "workpass-worker-last-build-tag": "baupass-worker-last-build-tag",
    "workpass-ai-voice-reply": "baupass-ai-voice-reply",
    "workpass-signotec-stpad-lib-v1": "baupass-signotec-stpad-lib-v1",
    "workpass-support-assist-watch": "baupass-support-assist-watch",
    "workpass-pending-access-token": "baupass-pending-access-token",
    "workpass-token": "baupass-token",
    "workpass-admin-session": "baupass_admin_session",
  };

  const KEYS = Object.freeze({
    API_BASE: "workpass-api-base",
    SESSION_TOKEN: "workpass-session-token",
    SUPPORT_LOGIN_CONTEXT: "workpass-support-login-context",
    SUPPORT_PHONE: "workpass-support-phone",
    UI_LANG: "workpass-ui-lang",
    INVOICE_FILTERS: "workpass-invoice-filters-v1",
    SYSTEM_THEME: "workpass-system-theme",
    SYSTEM_THEME_COLOR: "workpass-system-theme-color",
    WORKER_FORM_DEFAULTS: "workpass-worker-form-defaults-v1",
    GREETING_DATE: "workpass-greeting-date",
    PREVIEW_COMPANY_ID: "workpass-preview-company-id",
    BUILD_TAG: "workpass-build-tag",
    ADMIN_COMPANY: "workpass-admin-company",
    ADMIN_TOKEN: "workpass-admin-token",
    ADMIN_USER: "workpass-admin-user",
    ADMIN_LANG: "workpass-admin-lang",
    WORKER_TOKEN: "workpass-worker-token",
    WORKER_ACCESS_TOKEN: "workpass-worker-access-token",
    WORKER_BADGE_LOGIN: "workpass-worker-badge-login",
    LOCAL_LAST_PHOTO: "workpass-last-local-photo",
    OFFLINE_PHOTO_QUEUE: "workpass-offline-photo-queue",
    OFFLINE_EVENT_QUEUE: "workpass-offline-event-queue",
    WORKER_OFFLINE_LOGIN_PROFILE: "workpass-worker-offline-login-profile",
    QR_CACHE_PREFIX: "workpass-worker-qr-cache",
    QR_HIGH_CONTRAST: "workpass-qr-high-contrast",
    AUTO_OPEN_SCANNER: "workpass-auto-open-scanner",
    WORKER_CACHED_PAYLOAD: "workpass-worker-cached-payload",
    WORKER_LANG: "workpass-worker-lang",
    WORKER_THEME: "workpass-worker-theme",
    WORKER_DAY_PLANNER: "workpass-worker-day-planner",
    SMART_HUB_NOTIFY: "workpass-smart-hub-notify",
    NOTIFICATION_HISTORY: "workpass-notification-history",
    SYNC_CONFLICTS: "workpass-sync-conflicts",
    WORKER_LAST_BUILD_TAG: "workpass-worker-last-build-tag",
    AI_VOICE_REPLY: "workpass-ai-voice-reply",
    SIGNOTEC_LIB_CACHE: "workpass-signotec-stpad-lib-v1",
    SUPPORT_ASSIST_WATCH: "workpass-support-assist-watch",
    PENDING_ACCESS_TOKEN: "workpass-pending-access-token",
    GENERIC_TOKEN: "workpass-token",
    ADMIN_SESSION: "workpass-admin-session",
  });

  const SESSION_TOKEN_KEYS = [KEYS.SESSION_TOKEN, KEYS.ADMIN_TOKEN];
  const COMPANY_STORAGE_KEYS = [KEYS.PREVIEW_COMPANY_ID, KEYS.ADMIN_COMPANY];
  const TAB_SCOPED_KEYS = new Set([
    KEYS.SESSION_TOKEN,
    KEYS.ADMIN_TOKEN,
    KEYS.ADMIN_USER,
    KEYS.ADMIN_SESSION,
    KEYS.SUPPORT_LOGIN_CONTEXT,
  ]);

  function legacyFor(canonicalKey) {
    return LEGACY_BY_CANONICAL[canonicalKey] || "";
  }

  function isTabScopedKey(canonicalKey) {
    return TAB_SCOPED_KEYS.has(canonicalKey);
  }

  function getSessionItem(canonicalKey) {
    if (!canonicalKey || !isTabScopedKey(canonicalKey)) return null;
    try {
      return global.sessionStorage.getItem(canonicalKey);
    } catch {
      return null;
    }
  }

  function parentStorageApi() {
    try {
      if (global.self === global.top) return null;
      return global.top?.WorkPassStorage || null;
    } catch {
      return null;
    }
  }

  /** Support tab is active — do not leak main-tab credentials from localStorage. */
  function hasActiveSupportTabScope() {
    try {
      const parentApi = parentStorageApi();
      if (parentApi?.hasActiveSupportTabScope?.() === true) return true;
      const ctxRaw = global.sessionStorage.getItem(KEYS.SUPPORT_LOGIN_CONTEXT);
      if (ctxRaw) {
        const ctx = JSON.parse(ctxRaw);
        if (ctx?.companyId) return true;
      }
      const userRaw = global.sessionStorage.getItem(KEYS.ADMIN_USER);
      if (userRaw) {
        const user = JSON.parse(userRaw);
        if (user?.support_read_only) return true;
      }
      const tabToken =
        global.sessionStorage.getItem(KEYS.SESSION_TOKEN)
        || global.sessionStorage.getItem(KEYS.ADMIN_TOKEN);
      if (tabToken) return true;
      const watchRaw = global.sessionStorage.getItem("baupass-support-assist-watch");
      if (watchRaw) {
        const watch = JSON.parse(watchRaw);
        // Agent tab only. Spectator watch must never hide the customer's localStorage session.
        if (watch?.agent && watch?.watchToken) return true;
      }
    } catch {
      // ignore parse errors
    }
    return false;
  }

  function isSupportAssistQuietMode() {
    try {
      const parentApi = parentStorageApi();
      if (parentApi?.isSupportAssistQuietMode?.() === true) return true;
      if (hasActiveSupportTabScope()) return true;
      if (global.document?.body?.classList?.contains("support-assist-spectator-active")) return true;
      const watchRaw =
        global.sessionStorage.getItem("baupass-support-assist-watch")
        || global.sessionStorage.getItem(KEYS.SUPPORT_ASSIST_WATCH);
      if (watchRaw) {
        const watch = JSON.parse(watchRaw);
        if (watch?.watchToken) return true;
      }
      const userRaw = getItem(KEYS.ADMIN_USER);
      if (userRaw) {
        const user = JSON.parse(userRaw);
        if (user?.support_read_only) return true;
      }
    } catch {
      // ignore
    }
    return false;
  }

  function getItem(canonicalKey) {
    if (!canonicalKey) return null;
    try {
      if (isTabScopedKey(canonicalKey)) {
        const sessionValue = global.sessionStorage.getItem(canonicalKey);
        if (sessionValue !== null && sessionValue !== "") return sessionValue;
        if (hasActiveSupportTabScope()) return sessionValue;
      }
      const current = global.localStorage.getItem(canonicalKey);
      if (current !== null && current !== "") return current;
      const legacyKey = legacyFor(canonicalKey);
      if (!legacyKey) return current;
      const legacyVal = global.localStorage.getItem(legacyKey);
      if (legacyVal !== null && legacyVal !== "") {
        global.localStorage.setItem(canonicalKey, legacyVal);
        return legacyVal;
      }
      return current;
    } catch {
      return null;
    }
  }

  function setItem(canonicalKey, value) {
    if (!canonicalKey) return;
    try {
      if (isTabScopedKey(canonicalKey) && hasActiveSupportTabScope()) {
        setSessionItem(canonicalKey, value);
        return;
      }
      global.localStorage.setItem(canonicalKey, value);
      const legacyKey = legacyFor(canonicalKey);
      if (legacyKey) global.localStorage.removeItem(legacyKey);
    } catch {
      // ignore quota / private mode
    }
  }

  function setSessionItem(canonicalKey, value) {
    if (!canonicalKey || !isTabScopedKey(canonicalKey)) return;
    try {
      global.sessionStorage.setItem(canonicalKey, value);
    } catch {
      // ignore quota / private mode
    }
  }

  function removeItem(canonicalKey) {
    if (!canonicalKey) return;
    try {
      if (isTabScopedKey(canonicalKey) && hasActiveSupportTabScope()) {
        removeSessionItem(canonicalKey);
        return;
      }
      global.localStorage.removeItem(canonicalKey);
      const legacyKey = legacyFor(canonicalKey);
      if (legacyKey) global.localStorage.removeItem(legacyKey);
    } catch {
      // ignore
    }
  }

  function removeSessionItem(canonicalKey) {
    if (!canonicalKey || !isTabScopedKey(canonicalKey)) return;
    try {
      global.sessionStorage.removeItem(canonicalKey);
    } catch {
      // ignore
    }
  }

  function migratePrefix(oldPrefix, newPrefix) {
    if (!oldPrefix || !newPrefix || oldPrefix === newPrefix) return;
    try {
      const keys = [];
      for (let i = 0; i < global.localStorage.length; i += 1) {
        const key = global.localStorage.key(i);
        if (key && key.startsWith(oldPrefix)) keys.push(key);
      }
      keys.forEach((oldKey) => {
        const suffix = oldKey.slice(oldPrefix.length);
        const newKey = newPrefix + suffix;
        if (global.localStorage.getItem(newKey)) return;
        const val = global.localStorage.getItem(oldKey);
        if (val !== null) global.localStorage.setItem(newKey, val);
      });
    } catch {
      // ignore
    }
  }

  function migrateDynamicPrefixes() {
    migratePrefix("baupass-day-close-alert-", "workpass-day-close-alert-");
    migratePrefix("baupass-worker-qr-cache", "workpass-worker-qr-cache");
    migratePrefix("baupass-worker-", "workpass-worker-");
  }

  function migrateOnce() {
    try {
      if (global.localStorage.getItem(MIGRATION_FLAG) === "1") return;
      Object.entries(LEGACY_BY_CANONICAL).forEach(([canonical, legacy]) => {
        if (global.localStorage.getItem(canonical)) return;
        const legacyVal = global.localStorage.getItem(legacy);
        if (legacyVal !== null && legacyVal !== "") {
          global.localStorage.setItem(canonical, legacyVal);
        }
      });
      migrateDynamicPrefixes();
      global.localStorage.setItem(MIGRATION_FLAG, "1");
    } catch {
      // ignore
    }
  }

  function readSessionToken() {
    if (hasActiveSupportTabScope()) {
      for (const key of SESSION_TOKEN_KEYS) {
        const val = String(getSessionItem(key) || "").trim();
        if (val) return val;
      }
      return "";
    }
    for (const key of SESSION_TOKEN_KEYS) {
      const val = String(getItem(key) || "").trim();
      if (val) return val;
    }
    const legacyControl = String(global.localStorage.getItem("baupass-control-token") || "").trim();
    if (legacyControl) {
      setItem(KEYS.SESSION_TOKEN, legacyControl);
      return legacyControl;
    }
    return "";
  }

  function persistSessionToken(token) {
    const val = String(token || "").trim();
    if (!val) return;
    clearAuthUnusable();
    clearSharedAuthSessionProbe();
    if (hasActiveSupportTabScope()) {
      // Never leave an invalidated localStorage Bearer that can win over the cookie.
      purgeSharedLocalSessionTokens();
      SESSION_TOKEN_KEYS.forEach((key) => setSessionItem(key, val));
      return;
    }
    SESSION_TOKEN_KEYS.forEach((key) => setItem(key, val));
  }

  function readStoredCompanyId() {
    for (const key of COMPANY_STORAGE_KEYS) {
      const val = String(getItem(key) || "").trim();
      if (val) return val;
    }
    return "";
  }

  function persistCompanyId(companyId) {
    const cid = String(companyId || "").trim();
    if (!cid) return;
    setItem(KEYS.PREVIEW_COMPANY_ID, cid);
  }

  function clearSessionTokens() {
    if (hasActiveSupportTabScope()) {
      SESSION_TOKEN_KEYS.forEach((key) => removeSessionItem(key));
      removeSessionItem(KEYS.ADMIN_USER);
      removeSessionItem(KEYS.ADMIN_SESSION);
      return;
    }
    SESSION_TOKEN_KEYS.forEach((key) => removeItem(key));
    SESSION_TOKEN_KEYS.forEach((key) => removeSessionItem(key));
    removeItem(KEYS.ADMIN_USER);
    removeSessionItem(KEYS.ADMIN_USER);
    removeItem(KEYS.ADMIN_SESSION);
    removeSessionItem(KEYS.ADMIN_SESSION);
  }

  const SUPPORT_FETCH_BLOCK = [
    "/api/ai/speak",
    "/api/ai/transcribe",
    "/api/ai/insights",
    "/api/ai/operator/",
    "/api/ai/briefing",
    "/api/ai/status",
    "/api/v2/usage/event",
    "/api/v2/admin/usage-stats",
    "/api/chat/calls/incoming",
    "/api/e2e/identity",
    "/api/guardian/remediate",
    "/api/platform/sector-config",
    "/api/companies/current/branding",
    "/api/platform/enterprise-catalog",
  ];

  const SUPPORT_SPECTATOR_FETCH_BLOCK = [
    "/api/payroll/accounting/",
    "/api/payroll/statements/",
    "/api/dashboard/role",
  ];

  /** Background polls that must not hit the network without a confirmed support session. */
  const SUPPORT_POLL_BLOCK = [
    "/api/dashboard/role",
    "/api/ai/agents",
    "/api/leave-requests",
    "/api/ops-os/live-map",
    "/api/ops-os/summary",
    "/api/operations/snapshot",
    "/api/v1/events/recent",
    "/api/inbox/counts",
    "/api/inbox",
    "/api/payroll/accounting/messages",
  ];

  const SHARED_SUPPORT_COOLDOWN_KEY = "baupass-support-fetch-cooldown";

  const SUPPORT_WRITE_BLOCK = [
    "/review-open",
    "/payroll/statements/",
    "/payroll/accounting/messages/",
  ];

  const AUTH_UNUSABLE_KEY = "workpass-auth-unusable";
  const TTS_UNUSABLE_KEY = "workpass-tts-unavailable";
  const AUTH_UNUSABLE_TTL_MS = 120000;
  const SUPPORT_FETCH_COOLDOWN_MS = 60000;
  const supportFetchCooldownUntil = new Map();
  const AUTH_DEAD_ALLOW = [
    "/api/login",
    "/api/logout",
    "/api/support-assist/",
    "/api/public/",
    "/api/health",
  ];

  function isAuthUnusable() {
    try {
      const at = Number(global.sessionStorage.getItem(AUTH_UNUSABLE_KEY) || 0);
      return at > 0 && (Date.now() - at) < AUTH_UNUSABLE_TTL_MS;
    } catch {
      return false;
    }
  }

  function markAuthUnusable() {
    try {
      global.sessionStorage.setItem(AUTH_UNUSABLE_KEY, String(Date.now()));
    } catch {
      // ignore
    }
  }

  function getSharedRoot() {
    try {
      if (global.top && global.top !== global && global.top.sessionStorage) {
        return global.top;
      }
    } catch {
      // cross-origin iframe
    }
    return global;
  }

  function clearSharedAuthSessionProbe() {
    try {
      getSharedRoot().__wpAuthSessionProbe = null;
    } catch {
      // ignore
    }
  }

  function clearAuthUnusable() {
    try {
      global.sessionStorage.removeItem(AUTH_UNUSABLE_KEY);
      clearSupportFetchCooldowns();
    } catch {
      // ignore
    }
    clearSharedAuthSessionProbe();
  }

  function isTtsUnusable() {
    try {
      return global.sessionStorage.getItem(TTS_UNUSABLE_KEY) === "1";
    } catch {
      return false;
    }
  }

  function markTtsUnusable() {
    try {
      global.sessionStorage.setItem(TTS_UNUSABLE_KEY, "1");
    } catch {
      // ignore
    }
  }

  function isApiUrl(url) {
    return String(url || "").toLowerCase().includes("/api/");
  }

  function readSharedSupportCooldowns() {
    try {
      const root = getSharedRoot();
      const raw = root.sessionStorage.getItem(SHARED_SUPPORT_COOLDOWN_KEY);
      const map = raw ? JSON.parse(raw) : {};
      return map && typeof map === "object" ? map : {};
    } catch {
      return {};
    }
  }

  function writeSharedSupportCooldown(key, until) {
    try {
      const root = getSharedRoot();
      const map = readSharedSupportCooldowns();
      map[key] = until;
      root.sessionStorage.setItem(SHARED_SUPPORT_COOLDOWN_KEY, JSON.stringify(map));
    } catch {
      // ignore
    }
  }

  function supportFetchKey(url) {
    return String(url || "").toLowerCase().split("?")[0];
  }

  function isSupportFetchCoolingDown(url) {
    if (!isSupportAssistQuietMode() && !hasActiveSupportTabScope()) return false;
    const key = supportFetchKey(url);
    const sharedUntil = Number(readSharedSupportCooldowns()[key] || 0);
    const localUntil = supportFetchCooldownUntil.get(key) || 0;
    const until = Math.max(sharedUntil, localUntil);
    return Date.now() < until;
  }

  function markSupportFetchCooldown(url, status) {
    if (status !== 401 && status !== 403) return;
    if (!isSupportAssistQuietMode() && !hasActiveSupportTabScope()) return;
    const key = supportFetchKey(url);
    const until = Date.now() + SUPPORT_FETCH_COOLDOWN_MS;
    supportFetchCooldownUntil.set(key, until);
    writeSharedSupportCooldown(key, until);
  }

  function clearSupportFetchCooldowns() {
    supportFetchCooldownUntil.clear();
    try {
      getSharedRoot().sessionStorage.removeItem(SHARED_SUPPORT_COOLDOWN_KEY);
    } catch {
      // ignore
    }
  }

  function isAuthDeadAllowed(url) {
    const raw = String(url || "").toLowerCase();
    return AUTH_DEAD_ALLOW.some((part) => raw.includes(part));
  }

  function noteAuthFailure(res, url) {
    if (!res || res.status !== 401 || !isApiUrl(url) || isAuthDeadAllowed(url)) return;
    const raw = String(url || "").toLowerCase();
    // Support login gap / spectator polls: never poison the shared session from bare 401s.
    if (isSupportAssistQuietMode() || hasActiveSupportTabScope()) {
      if (!readSessionToken()) return;
      if (isSpectatorWatchOnly()) return;
    }
    if (raw.includes("/api/session/bootstrap") && !readSessionToken()) return;
    if (raw.includes("/api/v2/auth/session") && (!readSessionToken() || isSupportAssistQuietMode())) return;
    markAuthUnusable();
  }

  function purgeSharedLocalSessionTokens() {
    try {
      SESSION_TOKEN_KEYS.forEach((key) => {
        global.localStorage.removeItem(key);
        const legacy = legacyFor(key);
        if (legacy) global.localStorage.removeItem(legacy);
      });
      global.localStorage.removeItem(KEYS.ADMIN_USER);
      global.localStorage.removeItem(KEYS.ADMIN_SESSION);
      const legacyUser = legacyFor(KEYS.ADMIN_USER);
      if (legacyUser) global.localStorage.removeItem(legacyUser);
    } catch {
      // ignore
    }
  }

  function isAuthSessionProbeUrl(url) {
    return String(url || "").toLowerCase().includes("/api/v2/auth/session");
  }

  function shareAuthSessionProbe(run) {
    const root = getSharedRoot();
    if (root.__wpAuthSessionProbe) {
      return replayAuthSessionProbe(root.__wpAuthSessionProbe);
    }
    const p = run().then(async (res) => {
      let body = "{}";
      try {
        body = await res.clone().text();
      } catch {
        body = "{}";
      }
      if (res && res.status === 401 && !isSupportAssistQuietMode() && readSessionToken()) {
        markAuthUnusable();
      }
      return { status: res.status, body, ok: Boolean(res.ok) };
    });
    root.__wpAuthSessionProbe = p;
    p.finally(() => {
      setTimeout(() => {
        if (root.__wpAuthSessionProbe === p) root.__wpAuthSessionProbe = null;
      }, 2000);
    });
    return replayAuthSessionProbe(p);
  }

  function replayAuthSessionProbe(p) {
    return p.then((shared) => new Response(shared.body, {
      status: shared.status,
      statusText: shared.ok ? "OK" : "Unauthorized",
      headers: { "Content-Type": "application/json" },
    }));
  }

  function requestMethod(input, init) {
    if (init && init.method) return String(init.method).toUpperCase();
    if (input && typeof input !== "string" && input.method) return String(input.method).toUpperCase();
    return "GET";
  }

  function shouldBlockSupportFetch(url) {
    const raw = String(url || "").toLowerCase();
    return SUPPORT_FETCH_BLOCK.some((part) => raw.includes(part));
  }

  function shouldBlockSupportPoll(url) {
    const raw = String(url || "").toLowerCase();
    return SUPPORT_POLL_BLOCK.some((part) => raw.includes(part));
  }

  function isEmbedWithoutSessionToken() {
    try {
      if (global.self === global.top) return false;
      const params = new URLSearchParams(String(global.location.search || ""));
      if (params.get("embed") !== "1") return false;
      return !readSessionToken();
    } catch {
      return false;
    }
  }

  function shouldDeferSupportPoll() {
    if (isAuthUnusable()) return true;
    if (isEmbedWithoutSessionToken()) return true;
    return !readSessionToken();
  }

  function shouldBlockSpectatorFetch(url) {
    if (hasActiveSupportTabScope()) return false;
    const raw = String(url || "").toLowerCase();
    return SUPPORT_SPECTATOR_FETCH_BLOCK.some((part) => raw.includes(part));
  }

  function shouldBlockSupportWrite(url, input, init) {
    const method = requestMethod(input, init);
    if (!["POST", "PUT", "PATCH", "DELETE"].includes(method)) return false;
    const raw = String(url || "").toLowerCase();
    return SUPPORT_WRITE_BLOCK.some((part) => raw.includes(part));
  }

  function syntheticReadOnlyResponse() {
    return new Response(JSON.stringify({ error: "support_session_read_only" }), {
      status: 403,
      statusText: "Forbidden",
      headers: { "Content-Type": "application/json" },
    });
  }

  function syntheticAuthDeadResponse() {
    return new Response(JSON.stringify({ error: "unauthorized" }), {
      status: 401,
      statusText: "Unauthorized",
      headers: { "Content-Type": "application/json" },
    });
  }

  function isSpectatorWatchOnly() {
    try {
      const watchRaw =
        global.sessionStorage.getItem("baupass-support-assist-watch")
        || global.sessionStorage.getItem(KEYS.SUPPORT_ASSIST_WATCH);
      const watch = watchRaw ? JSON.parse(watchRaw) : null;
      return Boolean(watch?.watchToken && watch?.companyId && !watch?.agent);
    } catch {
      return false;
    }
  }

  function syntheticSupportResponse(url) {
    const raw = String(url || "").toLowerCase();
    if (raw.includes("/api/platform/sector-config")) {
      return new Response(JSON.stringify({
        sector: "construction",
        terms: {},
        label: "",
      }), {
        status: 200,
        statusText: "OK",
        headers: { "Content-Type": "application/json" },
      });
    }
    if (raw.includes("/api/payroll/statements/pending")) {
      return new Response(JSON.stringify({ ok: true, batches: [], count: 0, inbox: "open" }), {
        status: 200,
        statusText: "OK",
        headers: { "Content-Type": "application/json" },
      });
    }
    if (raw.includes("/api/payroll/accounting/messages")) {
      return new Response(JSON.stringify({
        ok: true,
        messages: [],
        notifications: [],
        count: 0,
        notificationCount: 0,
      }), {
        status: 200,
        statusText: "OK",
        headers: { "Content-Type": "application/json" },
      });
    }
    if (raw.includes("/api/payroll/accounting/data-alerts")) {
      return new Response(JSON.stringify({ ok: true, alerts: [] }), {
        status: 200,
        statusText: "OK",
        headers: { "Content-Type": "application/json" },
      });
    }
    if (raw.includes("/api/payroll/accounting/period-requests")) {
      return new Response(JSON.stringify({ ok: true, requests: [] }), {
        status: 200,
        statusText: "OK",
        headers: { "Content-Type": "application/json" },
      });
    }
    if (raw.includes("/api/dashboard/role")) {
      return new Response(JSON.stringify({ widgets: [] }), {
        status: 200,
        statusText: "OK",
        headers: { "Content-Type": "application/json" },
      });
    }
    if (raw.includes("/api/ai/agents")) {
      return new Response(JSON.stringify({ agents: [] }), {
        status: 200,
        statusText: "OK",
        headers: { "Content-Type": "application/json" },
      });
    }
    if (raw.includes("/api/leave-requests")) {
      return new Response(JSON.stringify([]), {
        status: 200,
        statusText: "OK",
        headers: { "Content-Type": "application/json" },
      });
    }
    if (raw.includes("/api/ops-os/live-map")) {
      return new Response(JSON.stringify({ workersOnSite: [], geofences: [], cameras: [], gates: [] }), {
        status: 200,
        statusText: "OK",
        headers: { "Content-Type": "application/json" },
      });
    }
    if (raw.includes("/api/support-assist/pulse") || raw.includes("/api/support-assist/end")) {
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        statusText: "OK",
        headers: { "Content-Type": "application/json" },
      });
    }
    if (raw.includes("/api/v1/events/recent") || raw.includes("/api/v1/realtime/")) {
      return new Response(JSON.stringify({ events: [], socketio: false, websocket: { enabled: false } }), {
        status: 200,
        statusText: "OK",
        headers: { "Content-Type": "application/json" },
      });
    }
    if (raw.includes("/socket.io")) {
      return new Response("0", {
        status: 200,
        statusText: "OK",
        headers: { "Content-Type": "text/plain" },
      });
    }
    return new Response("{}", {
      status: 204,
      statusText: "No Content",
      headers: { "Content-Type": "application/json" },
    });
  }

  function withSupportAuth(input, init) {
    const token = readSessionToken();
    const headers = new Headers(
      (init && init.headers)
      || (input && typeof input !== "string" && input.headers)
      || undefined,
    );
    const scoped = hasActiveSupportTabScope() || isSupportAssistQuietMode();
    if (scoped) {
      if (isSpectatorWatchOnly()) {
        // Spectator must use watch headers + customer cookie, never a stale Bearer.
        headers.delete("Authorization");
      } else if (token) {
        headers.set("Authorization", `Bearer ${token}`);
      } else {
        // Agent support tab without token yet: strip any stale Bearer so cookie can win,
        // and let the fetch guard short-circuit polls (see installSupportFetchGuard).
        headers.delete("Authorization");
      }
    } else if (token && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    try {
      const watchRaw =
        global.sessionStorage.getItem("baupass-support-assist-watch")
        || global.sessionStorage.getItem(KEYS.SUPPORT_ASSIST_WATCH);
      const watch = watchRaw ? JSON.parse(watchRaw) : null;
      if (watch?.watchToken && watch?.companyId && !watch?.agent) {
        if (!headers.has("X-Support-Watch-Token")) {
          headers.set("X-Support-Watch-Token", String(watch.watchToken));
        }
        if (!headers.has("X-Support-Company-Id")) {
          headers.set("X-Support-Company-Id", String(watch.companyId));
        }
      }
    } catch {
      // ignore
    }
    if (scoped || token || headers.has("X-Support-Watch-Token")) {
      return [input, { ...(init || {}), headers }];
    }
    return [input, init];
  }

  function installSupportFetchGuard() {
    if (global.__baupassSupportFetchGuard || typeof global.fetch !== "function") return;
    global.__baupassSupportFetchGuard = true;
    const originalFetch = global.fetch.bind(global);
    global.fetch = function baupassSupportFetch(input, init) {
      const url = typeof input === "string" ? input : (input && input.url) || "";
      if (isAuthUnusable() && isApiUrl(url) && !isAuthDeadAllowed(url)) {
        return Promise.resolve(syntheticSupportResponse(url));
      }
      if (
        isEmbedWithoutSessionToken()
        && isApiUrl(url)
        && !isAuthDeadAllowed(url)
      ) {
        return Promise.resolve(syntheticSupportResponse(url));
      }
      if ((isSupportAssistQuietMode() || isTtsUnusable()) && String(url || "").toLowerCase().includes("/api/ai/speak")) {
        return Promise.resolve(syntheticSupportResponse(url));
      }
      if (isSupportAssistQuietMode() && shouldBlockSupportWrite(url, input, init)) {
        return Promise.resolve(syntheticReadOnlyResponse());
      }
      if (String(url || "").toLowerCase().includes("/api/v2/usage/event") && (isSupportAssistQuietMode() || isAuthUnusable())) {
        return Promise.resolve(syntheticSupportResponse(url));
      }
      if (isSupportAssistQuietMode() && shouldBlockSpectatorFetch(url)) {
        return Promise.resolve(syntheticSupportResponse(url));
      }
      if (isSupportAssistQuietMode() && shouldBlockSupportFetch(url)) {
        return Promise.resolve(syntheticSupportResponse(url));
      }
      if (
        (isSupportAssistQuietMode() || hasActiveSupportTabScope())
        && shouldBlockSupportPoll(url)
        && (shouldDeferSupportPoll() || isSupportFetchCoolingDown(url))
      ) {
        return Promise.resolve(syntheticSupportResponse(url));
      }
      // Agent support tab waiting for Server-Admin login: do not hammer APIs with bare 401s.
      if (
        hasActiveSupportTabScope()
        && !isSpectatorWatchOnly()
        && !readSessionToken()
        && isApiUrl(url)
        && !isAuthDeadAllowed(url)
      ) {
        return Promise.resolve(syntheticSupportResponse(url));
      }
      if (
        String(url || "").toLowerCase().includes("/api/support-assist/pulse")
        && (isSupportFetchCoolingDown(url) || (!readSessionToken() && !parentStorageApi()?.readSessionToken?.()))
      ) {
        return Promise.resolve(syntheticSupportResponse(url));
      }
      if (isSupportFetchCoolingDown(url)) {
        return Promise.resolve(syntheticSupportResponse(url));
      }
      const run = (nextInput, nextInit) => originalFetch(nextInput, nextInit).then((res) => {
        noteAuthFailure(res, url);
        markSupportFetchCooldown(url, res?.status);
        if (res && !res.ok && String(url || "").toLowerCase().includes("/api/ai/speak")) {
          markTtsUnusable();
        }
        return res;
      });
      const scoped = hasActiveSupportTabScope() || isSupportAssistQuietMode();
      const exec = () => {
        if (scoped) {
          const next = withSupportAuth(input, init);
          return run(next[0], next[1]);
        }
        return run(input, init);
      };
      if (isAuthSessionProbeUrl(url)) {
        return shareAuthSessionProbe(exec);
      }
      return exec();
    };
  }

  global.WorkPassStorage = {
    KEYS,
    LEGACY_BY_CANONICAL,
    getItem,
    getSessionItem,
    setItem,
    setSessionItem,
    removeItem,
    removeSessionItem,
    migrateOnce,
    readSessionToken,
    persistSessionToken,
    readStoredCompanyId,
    persistCompanyId,
    clearSessionTokens,
    SESSION_TOKEN_KEYS,
    COMPANY_STORAGE_KEYS,
    hasActiveSupportTabScope,
    isSupportAssistQuietMode,
    isAuthUnusable,
    markAuthUnusable,
    clearAuthUnusable,
    purgeSharedLocalSessionTokens,
  };

  migrateOnce();
  installSupportFetchGuard();
})(typeof window !== "undefined" ? window : globalThis);
