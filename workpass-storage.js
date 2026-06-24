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

  function legacyFor(canonicalKey) {
    return LEGACY_BY_CANONICAL[canonicalKey] || "";
  }

  function getItem(canonicalKey) {
    if (!canonicalKey) return null;
    try {
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
      global.localStorage.setItem(canonicalKey, value);
      const legacyKey = legacyFor(canonicalKey);
      if (legacyKey) global.localStorage.removeItem(legacyKey);
    } catch {
      // ignore quota / private mode
    }
  }

  function removeItem(canonicalKey) {
    if (!canonicalKey) return;
    try {
      global.localStorage.removeItem(canonicalKey);
      const legacyKey = legacyFor(canonicalKey);
      if (legacyKey) global.localStorage.removeItem(legacyKey);
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
    SESSION_TOKEN_KEYS.forEach((key) => removeItem(key));
    removeItem(KEYS.ADMIN_USER);
    removeItem(KEYS.ADMIN_SESSION);
  }

  global.WorkPassStorage = {
    KEYS,
    LEGACY_BY_CANONICAL,
    getItem,
    setItem,
    removeItem,
    migrateOnce,
    readSessionToken,
    persistSessionToken,
    readStoredCompanyId,
    persistCompanyId,
    clearSessionTokens,
    SESSION_TOKEN_KEYS,
    COMPANY_STORAGE_KEYS,
  };

  migrateOnce();
})(typeof window !== "undefined" ? window : globalThis);
