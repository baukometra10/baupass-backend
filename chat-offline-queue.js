/**
 * SUPPIX chat offline queue — text + attachments (IndexedDB blobs), auto-retry on reconnect.
 */
(function initSuppixChatOfflineQueue(global) {
  const META_KEY = "suppix-chat-offline-queue";
  const DB_NAME = "suppix-chat-offline";
  const DB_VERSION = 1;
  const MAX_QUEUE = 40;
  let dbPromise = null;

  function readMetaQueue() {
    try {
      const raw = global.localStorage?.getItem(META_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function writeMetaQueue(rows) {
    try {
      global.localStorage?.setItem(META_KEY, JSON.stringify(rows.slice(-MAX_QUEUE)));
    } catch {
      /* ignore quota */
    }
  }

  function isOnline() {
    return global.navigator?.onLine !== false;
  }

  function getIndexedDB() {
    try {
      return global.indexedDB || global.webkitIndexedDB || null;
    } catch {
      return null;
    }
  }

  function openDb() {
    const idb = getIndexedDB();
    if (!idb) return Promise.resolve(null);
    if (!dbPromise) {
      dbPromise = new Promise((resolve, reject) => {
        const req = idb.open(DB_NAME, DB_VERSION);
        req.onupgradeneeded = (event) => {
          const db = event.target.result;
          if (!db.objectStoreNames.contains("blobs")) {
            db.createObjectStore("blobs");
          }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      }).catch(() => null);
    }
    return dbPromise;
  }

  async function storeBlob(blobKey, file) {
    const db = await openDb();
    if (!db || !file) return false;
    const buffer = await file.arrayBuffer();
    const payload = {
      buffer,
      filename: String(file.name || "upload.bin"),
      contentType: String(file.type || "application/octet-stream"),
      durationSec: Number(file.durationSec || 0),
      viewOnce: Boolean(file.viewOnce),
    };
    return new Promise((resolve) => {
      const tx = db.transaction("blobs", "readwrite");
      tx.objectStore("blobs").put(payload, blobKey);
      tx.oncomplete = () => resolve(true);
      tx.onerror = () => resolve(false);
    });
  }

  async function readBlob(blobKey) {
    const db = await openDb();
    if (!db || !blobKey) return null;
    const payload = await new Promise((resolve) => {
      const tx = db.transaction("blobs", "readonly");
      const req = tx.objectStore("blobs").get(blobKey);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => resolve(null);
    });
    if (!payload?.buffer) return null;
    const blob = new Blob([payload.buffer], { type: payload.contentType || "application/octet-stream" });
    const file = new File([blob], payload.filename || "upload.bin", { type: payload.contentType || "application/octet-stream" });
    if (payload.durationSec) file.durationSec = payload.durationSec;
    if (payload.viewOnce) file.viewOnce = true;
    return file;
  }

  async function deleteBlob(blobKey) {
    const db = await openDb();
    if (!db || !blobKey) return;
    await new Promise((resolve) => {
      const tx = db.transaction("blobs", "readwrite");
      tx.objectStore("blobs").delete(blobKey);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  }

  async function enqueue(item, file = null) {
    const entry = {
      id: `q-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      createdAt: new Date().toISOString(),
      retries: 0,
      ...item,
    };
    if (file) {
      const blobKey = `blob-${entry.id}`;
      const stored = await storeBlob(blobKey, file);
      if (stored) {
        entry.attachment = {
          blobKey,
          filename: String(file.name || "upload.bin"),
          contentType: String(file.type || "application/octet-stream"),
          durationSec: Number(file.durationSec || 0),
          e2eFields: item.attachmentE2eFields || null,
        };
      }
    }
    const rows = readMetaQueue();
    rows.push(entry);
    writeMetaQueue(rows);
    return entry;
  }

  async function flushQueue({ sendItem, onProgress } = {}) {
    if (!isOnline() || typeof sendItem !== "function") return { sent: 0, failed: 0, pending: readMetaQueue().length };
    let rows = readMetaQueue();
    if (!rows.length) return { sent: 0, failed: 0, pending: 0 };
    let sent = 0;
    let failed = 0;
    const remaining = [];
    for (const item of rows) {
      let attachmentFile = null;
      if (item.attachment?.blobKey) {
        attachmentFile = await readBlob(item.attachment.blobKey);
      }
      try {
        await sendItem(item, attachmentFile);
        if (item.attachment?.blobKey) await deleteBlob(item.attachment.blobKey);
        sent += 1;
        onProgress?.({ type: "sent", item });
      } catch (error) {
        const retries = Number(item.retries || 0) + 1;
        if (retries < 5) {
          remaining.push({ ...item, retries });
        } else {
          if (item.attachment?.blobKey) await deleteBlob(item.attachment.blobKey);
          failed += 1;
          onProgress?.({ type: "dropped", item, error });
        }
      }
    }
    writeMetaQueue(remaining);
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

  async function sendWithOfflineFallback({ payload, file, sendNow, onQueued } = {}) {
    if (isOnline()) {
      try {
        return await sendNow(payload, file);
      } catch (error) {
        if (error?.code !== "network_error" && error?.name !== "TypeError") throw error;
      }
    }
    await enqueue(payload, file || null);
    onQueued?.(payload);
    return { queued: true };
  }

  global.SUPPIXChatOfflineQueue = {
    STORAGE_KEY: META_KEY,
    readQueue: readMetaQueue,
    enqueue,
    flushQueue,
    bindAutoFlush,
    sendWithOfflineFallback,
    isOnline,
    pendingCount() {
      return readMetaQueue().length;
    },
  };
})(typeof window !== "undefined" ? window : globalThis);
