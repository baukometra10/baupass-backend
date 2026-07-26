/**
 * Docs offline draft queue — IndexedDB primary, localStorage fallback + migration.
 * Sync policy is applied by docs-app (server-wins on conflict).
 */
(function initDocsOfflineQueue(global) {
  const DB_NAME = "suppix-docs-offline";
  const DB_VERSION = 1;
  const STORE = "drafts";
  const LS_PREFIX = "baupass-docs-offline:";
  const MAX_DRAFTS = 40;

  let dbPromise = null;

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
      dbPromise = new Promise((resolve) => {
        try {
          const req = idb.open(DB_NAME, DB_VERSION);
          req.onupgradeneeded = (event) => {
            const db = event.target.result;
            if (!db.objectStoreNames.contains(STORE)) {
              const store = db.createObjectStore(STORE, { keyPath: "key" });
              store.createIndex("companyId", "companyId", { unique: false });
              store.createIndex("pendingSync", "pendingSync", { unique: false });
            }
          };
          req.onsuccess = () => resolve(req.result);
          req.onerror = () => resolve(null);
        } catch {
          resolve(null);
        }
      });
    }
    return dbPromise;
  }

  function draftKey(companyId, docId) {
    const cid = String(companyId || "none").trim() || "none";
    const id = String(docId || "new").trim() || "new";
    return `${cid}:${id}`;
  }

  function normalizeDraft(raw, fallbackKey) {
    if (!raw || typeof raw !== "object") return null;
    const companyId = String(raw.companyId || "").trim();
    const docId = String(raw.docId || "").trim();
    const key = String(raw.key || fallbackKey || draftKey(companyId, docId || "new"));
    const html = String(raw.html || "");
    const ts = Number(raw.ts || 0);
    if (!html || !ts) return null;
    return {
      key,
      companyId,
      docId,
      clientId: String(raw.clientId || `c-${ts}`),
      ts,
      baseUpdatedAt: String(raw.baseUpdatedAt || ""),
      title: String(raw.title || ""),
      mode: String(raw.mode || "general"),
      html,
      headerHtml: raw.headerHtml != null ? String(raw.headerHtml) : "",
      footerHtml: raw.footerHtml != null ? String(raw.footerHtml) : "",
      layout: raw.layout && typeof raw.layout === "object" ? raw.layout : null,
      pendingSync: Boolean(raw.pendingSync),
      syncStatus: String(raw.syncStatus || (raw.pendingSync ? "pending" : "idle")),
      conflict: Boolean(raw.conflict),
      serverUpdatedAt: String(raw.serverUpdatedAt || ""),
    };
  }

  function lsGet(key) {
    try {
      return global.localStorage?.getItem(`${LS_PREFIX}${key}`) || null;
    } catch {
      return null;
    }
  }

  function lsSet(key, draft) {
    try {
      global.localStorage?.setItem(`${LS_PREFIX}${key}`, JSON.stringify(draft));
    } catch {
      /* quota */
    }
  }

  function lsRemove(key) {
    try {
      global.localStorage?.removeItem(`${LS_PREFIX}${key}`);
    } catch {
      /* ignore */
    }
  }

  function idbPut(db, draft) {
    return new Promise((resolve) => {
      try {
        const tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).put(draft);
        tx.oncomplete = () => resolve(true);
        tx.onerror = () => resolve(false);
      } catch {
        resolve(false);
      }
    });
  }

  function idbGet(db, key) {
    return new Promise((resolve) => {
      try {
        const tx = db.transaction(STORE, "readonly");
        const req = tx.objectStore(STORE).get(key);
        req.onsuccess = () => resolve(req.result || null);
        req.onerror = () => resolve(null);
      } catch {
        resolve(null);
      }
    });
  }

  function idbDelete(db, key) {
    return new Promise((resolve) => {
      try {
        const tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).delete(key);
        tx.oncomplete = () => resolve(true);
        tx.onerror = () => resolve(false);
      } catch {
        resolve(false);
      }
    });
  }

  function idbAll(db) {
    return new Promise((resolve) => {
      try {
        const tx = db.transaction(STORE, "readonly");
        const req = tx.objectStore(STORE).getAll();
        req.onsuccess = () => resolve(Array.isArray(req.result) ? req.result : []);
        req.onerror = () => resolve([]);
      } catch {
        resolve([]);
      }
    });
  }

  async function putDraft(input) {
    const draft = normalizeDraft(input);
    if (!draft) return null;
    draft.pendingSync = Boolean(input.pendingSync ?? true);
    draft.syncStatus = String(input.syncStatus || (draft.pendingSync ? "pending" : draft.syncStatus));
    const db = await openDb();
    if (db) await idbPut(db, draft);
    lsSet(draft.key, draft);
    // Cap localStorage mirror loosely
    try {
      const keys = [];
      for (let i = 0; i < (global.localStorage?.length || 0); i += 1) {
        const k = global.localStorage.key(i);
        if (k && k.startsWith(LS_PREFIX)) keys.push(k);
      }
      if (keys.length > MAX_DRAFTS) {
        keys
          .map((k) => {
            try {
              return { k, ts: Number(JSON.parse(global.localStorage.getItem(k) || "{}").ts || 0) };
            } catch {
              return { k, ts: 0 };
            }
          })
          .sort((a, b) => a.ts - b.ts)
          .slice(0, keys.length - MAX_DRAFTS)
          .forEach((row) => global.localStorage.removeItem(row.k));
      }
    } catch {
      /* ignore */
    }
    return draft;
  }

  async function getDraft(companyId, docId) {
    const key = draftKey(companyId, docId);
    const db = await openDb();
    if (db) {
      const row = normalizeDraft(await idbGet(db, key), key);
      if (row) return row;
    }
    try {
      const raw = lsGet(key);
      return raw ? normalizeDraft(JSON.parse(raw), key) : null;
    } catch {
      return null;
    }
  }

  async function deleteDraft(companyId, docId) {
    const key = draftKey(companyId, docId);
    const db = await openDb();
    if (db) await idbDelete(db, key);
    lsRemove(key);
    if (docId && docId !== "new") {
      const orphan = draftKey(companyId, "new");
      if (db) await idbDelete(db, orphan);
      lsRemove(orphan);
    }
  }

  async function listDrafts(companyId) {
    const cid = String(companyId || "").trim();
    const out = [];
    const db = await openDb();
    if (db) {
      const rows = await idbAll(db);
      rows.forEach((row) => {
        const d = normalizeDraft(row);
        if (!d) return;
        if (cid && d.companyId !== cid) return;
        out.push(d);
      });
    }
    try {
      const prefix = LS_PREFIX + (cid ? `${cid}:` : "");
      for (let i = 0; i < (global.localStorage?.length || 0); i += 1) {
        const k = global.localStorage.key(i);
        if (!k || !k.startsWith(LS_PREFIX)) continue;
        if (cid && !k.startsWith(prefix)) continue;
        const key = k.slice(LS_PREFIX.length);
        if (out.some((d) => d.key === key)) continue;
        try {
          const d = normalizeDraft(JSON.parse(global.localStorage.getItem(k) || "null"), key);
          if (d) out.push(d);
        } catch {
          /* ignore */
        }
      }
    } catch {
      /* ignore */
    }
    return out.sort((a, b) => b.ts - a.ts);
  }

  async function listPending(companyId) {
    const rows = await listDrafts(companyId);
    return rows.filter((d) => d.pendingSync || d.syncStatus === "pending" || d.conflict);
  }

  async function migrateFromLocalStorage() {
    const migrated = [];
    try {
      for (let i = 0; i < (global.localStorage?.length || 0); i += 1) {
        const k = global.localStorage.key(i);
        if (!k || !k.startsWith(LS_PREFIX)) continue;
        const key = k.slice(LS_PREFIX.length);
        try {
          const raw = JSON.parse(global.localStorage.getItem(k) || "null");
          const draft = normalizeDraft(
            {
              ...raw,
              key,
              companyId: raw?.companyId || key.split(":")[0],
              docId: raw?.docId || key.split(":").slice(1).join(":") || "new",
              pendingSync: raw?.pendingSync !== false,
              syncStatus: raw?.syncStatus || "pending",
            },
            key,
          );
          if (draft) {
            await putDraft(draft);
            migrated.push(draft.key);
          }
        } catch {
          /* ignore bad rows */
        }
      }
    } catch {
      /* ignore */
    }
    return migrated;
  }

  async function markSynced(companyId, docId, { newDocId } = {}) {
    const oldKey = draftKey(companyId, docId || "new");
    const db = await openDb();
    let draft = null;
    if (db) draft = normalizeDraft(await idbGet(db, oldKey), oldKey);
    if (!draft) {
      try {
        draft = normalizeDraft(JSON.parse(lsGet(oldKey) || "null"), oldKey);
      } catch {
        draft = null;
      }
    }
    await deleteDraft(companyId, docId || "new");
    if (newDocId && draft) {
      const next = {
        ...draft,
        key: draftKey(companyId, newDocId),
        docId: newDocId,
        pendingSync: false,
        syncStatus: "synced",
        conflict: false,
      };
      // Drop after successful sync — no need to keep body.
      await deleteDraft(companyId, newDocId);
      return next;
    }
    return draft;
  }

  async function markConflict(companyId, docId, serverUpdatedAt) {
    const draft = await getDraft(companyId, docId);
    if (!draft) return null;
    draft.conflict = true;
    draft.pendingSync = false;
    draft.syncStatus = "conflict";
    draft.serverUpdatedAt = String(serverUpdatedAt || "");
    return putDraft(draft);
  }

  global.DocsOfflineQueue = {
    LS_PREFIX,
    draftKey,
    putDraft,
    getDraft,
    deleteDraft,
    listDrafts,
    listPending,
    migrateFromLocalStorage,
    markSynced,
    markConflict,
  };
})(typeof window !== "undefined" ? window : globalThis);
