/**
 * SUPPIX chat message preferences — pin & star (localStorage per thread).
 */
(function initSuppixChatMessagePrefs(global) {
  const KEY = "suppix-chat-message-prefs";

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
      return false;
    }
    bucket.pins[key] = Date.now();
    saveThread(tid, bucket);
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
      return false;
    }
    bucket.stars[key] = true;
    saveThread(tid, bucket);
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

  global.SUPPIXChatMessagePrefs = {
    isPinned,
    isStarred,
    togglePin,
    toggleStar,
    getPinnedIds,
  };
})(typeof window !== "undefined" ? window : globalThis);
