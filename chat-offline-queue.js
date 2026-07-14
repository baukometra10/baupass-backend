/**
 * SUPPIX chat offline queue — retry pending messages on reconnect.
 */
(function initSuppixChatOfflineQueue(global) {
  const STORAGE_KEY = "suppix-chat-offline-queue";
  const MAX_QUEUE = 40;

  function readQueue() {
    try {
      const raw = global.localStorage?.getItem(STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function writeQueue(rows) {
    try {
      global.localStorage?.setItem(STORAGE_KEY, JSON.stringify(rows.slice(-MAX_QUEUE)));
    } catch {
      /* ignore quota */
    }
  }

  function enqueue(item) {
    const rows = readQueue();
    rows.push({
      id: `q-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      createdAt: new Date().toISOString(),
      retries: 0,
      ...item,
    });
    writeQueue(rows);
    return rows.length;
  }

  function isOnline() {
    return global.navigator?.onLine !== false;
  }

  async function flushQueue({ sendItem, onProgress } = {}) {
    if (!isOnline() || typeof sendItem !== "function") return { sent: 0, failed: 0 };
    let rows = readQueue();
    if (!rows.length) return { sent: 0, failed: 0 };
    let sent = 0;
    let failed = 0;
    const remaining = [];
    for (const item of rows) {
      try {
        await sendItem(item);
        sent += 1;
        onProgress?.({ type: "sent", item });
      } catch (error) {
        const retries = Number(item.retries || 0) + 1;
        if (retries < 5) {
          remaining.push({ ...item, retries });
        } else {
          failed += 1;
          onProgress?.({ type: "dropped", item, error });
        }
      }
    }
    writeQueue(remaining);
    return { sent, failed, pending: remaining.length };
  }

  function bindAutoFlush({ sendItem, onProgress } = {}) {
    const run = () => { void flushQueue({ sendItem, onProgress }); };
    global.addEventListener("online", run);
    global.addEventListener("visibilitychange", () => {
      if (global.document?.visibilityState === "visible") run();
    });
    if ("serviceWorker" in global.navigator) {
      global.navigator.serviceWorker.addEventListener("message", (event) => {
        if (event?.data?.type === "SW_FLUSH_OFFLINE_QUEUE") run();
      });
    }
    run();
    return () => {
      global.removeEventListener("online", run);
    };
  }

  async function sendWithOfflineFallback({
    payload,
    sendNow,
    onQueued,
  } = {}) {
    if (isOnline()) {
      try {
        return await sendNow(payload);
      } catch (error) {
        if (error?.code !== "network_error" && error?.name !== "TypeError") throw error;
      }
    }
    enqueue(payload);
    onQueued?.(payload);
    return { queued: true };
  }

  global.SUPPIXChatOfflineQueue = {
    STORAGE_KEY,
    readQueue,
    enqueue,
    flushQueue,
    bindAutoFlush,
    sendWithOfflineFallback,
    isOnline,
    pendingCount() {
      return readQueue().length;
    },
  };
})(typeof window !== "undefined" ? window : globalThis);
