/**
 * SUPPIX admin chat thread preferences — pin & mute (localStorage per company).
 */
(function initSuppixChatThreadPrefs(global) {
  const KEY = "suppix-admin-chat-thread-prefs";

  function readAll() {
    try {
      const raw = global.localStorage?.getItem(KEY);
      const parsed = raw ? JSON.parse(raw) : {};
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      return {};
    }
  }

  function writeAll(data) {
    try {
      global.localStorage?.setItem(KEY, JSON.stringify(data));
    } catch {
      /* ignore quota */
    }
  }

  function companyBucket(companyId) {
    const cid = String(companyId || "default").trim() || "default";
    const all = readAll();
    if (!all[cid] || typeof all[cid] !== "object") {
      all[cid] = { pins: {}, muted: {} };
    }
    return all[cid];
  }

  function saveCompany(companyId, bucket) {
    const cid = String(companyId || "default").trim() || "default";
    const all = readAll();
    all[cid] = bucket;
    writeAll(all);
  }

  function workerKey(workerId) {
    return String(workerId || "").trim();
  }

  function isPinned(companyId, workerId) {
    const key = workerKey(workerId);
    if (!key) return false;
    return Boolean(companyBucket(companyId).pins?.[key]);
  }

  function isMuted(companyId, workerId) {
    const key = workerKey(workerId);
    if (!key) return false;
    return Boolean(companyBucket(companyId).muted?.[key]);
  }

  function togglePin(companyId, workerId) {
    const key = workerKey(workerId);
    if (!key) return false;
    const bucket = companyBucket(companyId);
    if (bucket.pins[key]) {
      delete bucket.pins[key];
      saveCompany(companyId, bucket);
      return false;
    }
    bucket.pins[key] = Date.now();
    saveCompany(companyId, bucket);
    return true;
  }

  function toggleMute(companyId, workerId) {
    const key = workerKey(workerId);
    if (!key) return false;
    const bucket = companyBucket(companyId);
    if (bucket.muted[key]) {
      delete bucket.muted[key];
      saveCompany(companyId, bucket);
      return false;
    }
    bucket.muted[key] = true;
    saveCompany(companyId, bucket);
    return true;
  }

  function pinSortValue(companyId, workerId) {
    const key = workerKey(workerId);
    const ts = Number(companyBucket(companyId).pins?.[key] || 0);
    return ts;
  }

  global.SUPPIXChatThreadPrefs = {
    isPinned,
    isMuted,
    togglePin,
    toggleMute,
    pinSortValue,
  };
})(typeof window !== "undefined" ? window : globalThis);
