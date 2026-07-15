/**
 * SUPPIX chat message preferences — pin & star (local + optional server sync).
 * Admin: /api/chat/message-prefs
 * Worker: /api/worker-app/chat/message-prefs
 */
(function initSuppixChatMessagePrefs(global) {
  const KEY = "suppix-chat-message-prefs";
  let syncApi = null;
  let syncCompanyId = "";
  let syncBasePath = "/api/chat/message-prefs";

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

  function threadBucket(threadId) {
    const tid = String(threadId || "").trim();
    if (!tid) return { pins: {}, stars: {} };
    const all = readAll();
    if (!all[tid] || typeof all[tid] !== "object") {
      all[tid] = { pins: {}, stars: {} };
    }
    if (!all[tid].pins || typeof all[tid].pins !== "object") all[tid].pins = {};
    if (!all[tid].stars || typeof all[tid].stars !== "object") all[tid].stars = {};
    return all[tid];
  }

  function saveThread(threadId, bucket) {
    const tid = String(threadId || "").trim();
    if (!tid) return;
    const all = readAll();
    all[tid] = bucket;
    writeAll(all);
  }

  function messageKey(messageId) {
    return String(messageId || "").trim();
  }

  function pushPref(threadId, messageId, patch) {
    if (!syncApi) return;
    const mid = messageKey(messageId);
    const tid = String(threadId || "").trim();
    if (!mid || !tid) return;
    const body = { thread_id: tid, ...patch };
    if (syncCompanyId) body.company_id = syncCompanyId;
    void syncApi(`${syncBasePath}/${encodeURIComponent(mid)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch(() => {});
  }

  function isPinned(threadId, messageId) {
    const key = messageKey(messageId);
    if (!key) return false;
    return Boolean(threadBucket(threadId).pins[key]);
  }

  function isStarred(threadId, messageId) {
    const key = messageKey(messageId);
    if (!key) return false;
    return Boolean(threadBucket(threadId).stars[key]);
  }

  function togglePin(threadId, messageId) {
    const tid = String(threadId || "").trim();
    const key = messageKey(messageId);
    if (!tid || !key) return false;
    const bucket = threadBucket(tid);
    if (bucket.pins[key]) {
      delete bucket.pins[key];
      saveThread(tid, bucket);
      pushPref(tid, key, { pinned: false });
      return false;
    }
    bucket.pins[key] = Date.now();
    saveThread(tid, bucket);
    pushPref(tid, key, { pinned: true });
    return true;
  }

  function toggleStar(threadId, messageId) {
    const tid = String(threadId || "").trim();
    const key = messageKey(messageId);
    if (!tid || !key) return false;
    const bucket = threadBucket(tid);
    if (bucket.stars[key]) {
      delete bucket.stars[key];
      saveThread(tid, bucket);
      pushPref(tid, key, { starred: false });
      return false;
    }
    bucket.stars[key] = true;
    saveThread(tid, bucket);
    pushPref(tid, key, { starred: true });
    return true;
  }

  function getPinnedIds(threadId) {
    const tid = String(threadId || "").trim();
    if (!tid) return [];
    const pins = threadBucket(tid).pins || {};
    return Object.entries(pins)
      .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
      .map(([id]) => id);
  }

  async function hydrateFromServer({ api, companyId, threadId, role } = {}) {
    syncApi = typeof api === "function" ? api : null;
    syncCompanyId = String(companyId || "").trim();
    syncBasePath = String(role || "").toLowerCase() === "worker"
      ? "/api/worker-app/chat/message-prefs"
      : "/api/chat/message-prefs";
    const tid = String(threadId || "").trim();
    if (!syncApi || !tid) return;
    if (syncBasePath.indexOf("worker-app") < 0 && !syncCompanyId) return;
    try {
      const qs = new URLSearchParams({ thread_id: tid });
      if (syncCompanyId) qs.set("company_id", syncCompanyId);
      const data = await syncApi(`${syncBasePath}?${qs.toString()}`);
      const prefs = data?.prefs && typeof data.prefs === "object" ? data.prefs : {};
      const bucket = threadBucket(tid);
      Object.entries(prefs).forEach(([mid, pref]) => {
        const key = messageKey(mid);
        if (!key || !pref || typeof pref !== "object") return;
        if (pref.pinnedAt) bucket.pins[key] = Date.parse(pref.pinnedAt) || Date.now();
        else delete bucket.pins[key];
        if (pref.starred) bucket.stars[key] = true;
        else delete bucket.stars[key];
      });
      saveThread(tid, bucket);
    } catch {
      /* local prefs remain */
    }
  }

  global.SUPPIXChatMessagePrefs = {
    isPinned,
    isStarred,
    togglePin,
    toggleStar,
    getPinnedIds,
    hydrateFromServer,
  };
})(typeof window !== "undefined" ? window : globalThis);
