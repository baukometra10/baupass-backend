/**
 * SUPPIX admin chat thread preferences — pin & mute (local + optional server sync).
 */
(function initSuppixChatThreadPrefs(global) {
  const KEY = "suppix-admin-chat-thread-prefs";
  let syncApi = null;
  let syncCompanyId = "";

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
    if (!all[cid].pins || typeof all[cid].pins !== "object") all[cid].pins = {};
    if (!all[cid].muted || typeof all[cid].muted !== "object") all[cid].muted = {};
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

  function pushPref(companyId, workerId, patch) {
    if (!syncApi || String(companyId) !== String(syncCompanyId)) return;
    const wid = workerKey(workerId);
    if (!wid) return;
    void syncApi(`/api/chat/thread-prefs/${encodeURIComponent(wid)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_id: companyId, ...patch }),
    }).catch(() => {});
  }

  function togglePin(companyId, workerId) {
    const key = workerKey(workerId);
    if (!key) return false;
    const bucket = companyBucket(companyId);
    if (bucket.pins[key]) {
      delete bucket.pins[key];
      saveCompany(companyId, bucket);
      pushPref(companyId, workerId, { pinned: false });
      return false;
    }
    bucket.pins[key] = Date.now();
    saveCompany(companyId, bucket);
    pushPref(companyId, workerId, { pinned: true });
    return true;
  }

  function toggleMute(companyId, workerId) {
    const key = workerKey(workerId);
    if (!key) return false;
    const bucket = companyBucket(companyId);
    if (bucket.muted[key]) {
      delete bucket.muted[key];
      saveCompany(companyId, bucket);
      pushPref(companyId, workerId, { muted: false });
      return false;
    }
    bucket.muted[key] = true;
    saveCompany(companyId, bucket);
    pushPref(companyId, workerId, { muted: true });
    return true;
  }

  function pinSortValue(companyId, workerId) {
    const key = workerKey(workerId);
    const ts = Number(companyBucket(companyId).pins?.[key] || 0);
    return ts;
  }

  async function hydrateFromServer({ api, companyId } = {}) {
    syncApi = typeof api === "function" ? api : null;
    syncCompanyId = String(companyId || "").trim();
    if (!syncApi || !syncCompanyId) return;
    try {
      const data = await syncApi(`/api/chat/thread-prefs?company_id=${encodeURIComponent(syncCompanyId)}`);
      const prefs = data?.prefs && typeof data.prefs === "object" ? data.prefs : {};
      const bucket = companyBucket(syncCompanyId);
      Object.entries(prefs).forEach(([wid, pref]) => {
        const key = workerKey(wid);
        if (!key || !pref || typeof pref !== "object") return;
        if (pref.pinnedAt) bucket.pins[key] = Date.parse(pref.pinnedAt) || Date.now();
        else delete bucket.pins[key];
        if (pref.muted) bucket.muted[key] = true;
        else delete bucket.muted[key];
      });
      saveCompany(syncCompanyId, bucket);
    } catch {
      /* local prefs remain */
    }
  }

  global.SUPPIXChatThreadPrefs = {
    isPinned,
    isMuted,
    togglePin,
    toggleMute,
    pinSortValue,
    hydrateFromServer,
  };
})(typeof window !== "undefined" ? window : globalThis);
