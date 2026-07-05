/**
 * SUPPIX E2E crypto (client-only private keys).
 * X25519 ephemeral ECDH + HKDF + AES-GCM. Private keys never leave the device.
 */
(function (global) {
  const IDB_NAME = "suppix-e2e-crypto-v1";
  const IDB_STORE = "identities";
  const MASTER_KEY_STORAGE = "suppix-e2e-master-v1";
  const ALGORITHM = "X25519";
  const ENVELOPE_VERSION = 1;

  function b64Encode(bytes) {
    const bin = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
    let str = "";
    bin.forEach((b) => { str += String.fromCharCode(b); });
    return btoa(str);
  }

  function b64Decode(text) {
    const str = atob(String(text || ""));
    const out = new Uint8Array(str.length);
    for (let i = 0; i < str.length; i += 1) out[i] = str.charCodeAt(i);
    return out;
  }

  function utf8Encode(text) {
    return new TextEncoder().encode(String(text || ""));
  }

  function utf8Decode(bytes) {
    return new TextDecoder().decode(bytes);
  }

  async function sha256(bytes) {
    return crypto.subtle.digest("SHA-256", bytes);
  }

  async function getOrCreateMasterKey() {
    let raw = null;
    try {
      raw = localStorage.getItem(MASTER_KEY_STORAGE);
    } catch {
      raw = null;
    }
    if (!raw) {
      const seed = crypto.getRandomValues(new Uint8Array(32));
      raw = b64Encode(seed);
      try {
        localStorage.setItem(MASTER_KEY_STORAGE, raw);
      } catch {
        // session-only fallback
      }
    }
    const material = await sha256(b64Decode(raw));
    return crypto.subtle.importKey("raw", material, "AES-GCM", false, ["encrypt", "decrypt"]);
  }

  function openDb() {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(IDB_NAME, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(IDB_STORE)) {
          db.createObjectStore(IDB_STORE, { keyPath: "id" });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async function idbGet(id) {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(IDB_STORE, "readonly");
      const store = tx.objectStore(IDB_STORE);
      const req = store.get(id);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = () => reject(req.error);
    });
  }

  async function idbPut(record) {
    const db = await openDb();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(IDB_STORE, "readwrite");
      const store = tx.objectStore(IDB_STORE);
      const req = store.put(record);
      req.onsuccess = () => resolve(record);
      req.onerror = () => reject(req.error);
    });
  }

  async function exportPublicKeySpkiB64(publicKey) {
    const spki = await crypto.subtle.exportKey("spki", publicKey);
    return b64Encode(new Uint8Array(spki));
  }

  async function importPublicKeySpkiB64(spkiB64) {
    return crypto.subtle.importKey(
      "spki",
      b64Decode(spkiB64),
      { name: ALGORITHM, namedCurve: ALGORITHM },
      true,
      [],
    );
  }

  async function encryptPrivateKeyJwk(jwk) {
    const master = await getOrCreateMasterKey();
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const plain = utf8Encode(JSON.stringify(jwk));
    const cipher = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, master, plain);
    return { iv: b64Encode(iv), ct: b64Encode(new Uint8Array(cipher)) };
  }

  async function decryptPrivateKeyJwk(payload) {
    const master = await getOrCreateMasterKey();
    const iv = b64Decode(payload.iv);
    const ct = b64Decode(payload.ct);
    const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, master, ct);
    return JSON.parse(utf8Decode(new Uint8Array(plain)));
  }

  async function generateIdentityKeyPair() {
    return crypto.subtle.generateKey(
      { name: ALGORITHM, namedCurve: ALGORITHM },
      true,
      ["deriveKey", "deriveBits"],
    );
  }

  async function deriveAesKey(privateKey, publicKey) {
    return crypto.subtle.deriveKey(
      { name: ALGORITHM, public: publicKey },
      privateKey,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"],
    );
  }

  function identityStorageId(entityType, entityId) {
    return `${String(entityType || "").toLowerCase()}:${String(entityId || "").trim()}`;
  }

  function isE2EEnvelope(value) {
    if (typeof value !== "string") return false;
    const trimmed = value.trim();
    if (!trimmed.startsWith("{")) return false;
    try {
      const parsed = JSON.parse(trimmed);
      return parsed && parsed.e2e === true && parsed.v === ENVELOPE_VERSION && parsed.ct;
    } catch {
      return false;
    }
  }

  async function ensureLocalIdentity(entityType, entityId) {
    const id = identityStorageId(entityType, entityId);
    const existing = await idbGet(id);
    if (existing?.publicKeySpkiB64 && existing?.privateKeyEnc) {
      return {
        entityType,
        entityId,
        publicKeySpkiB64: existing.publicKeySpkiB64,
        algorithm: ALGORITHM,
      };
    }
    const keyPair = await generateIdentityKeyPair();
    const publicKeySpkiB64 = await exportPublicKeySpkiB64(keyPair.publicKey);
    const privateJwk = await crypto.subtle.exportKey("jwk", keyPair.privateKey);
    const privateKeyEnc = await encryptPrivateKeyJwk(privateJwk);
    await idbPut({
      id,
      entityType,
      entityId,
      publicKeySpkiB64,
      privateKeyEnc,
      algorithm: ALGORITHM,
      createdAt: new Date().toISOString(),
    });
    return { entityType, entityId, publicKeySpkiB64, algorithm: ALGORITHM };
  }

  async function loadPrivateKey(entityType, entityId) {
    const id = identityStorageId(entityType, entityId);
    const record = await idbGet(id);
    if (!record?.privateKeyEnc) {
      throw new Error("e2e_private_key_missing");
    }
    const jwk = await decryptPrivateKeyJwk(record.privateKeyEnc);
    return crypto.subtle.importKey(
      "jwk",
      jwk,
      { name: ALGORITHM, namedCurve: ALGORITHM },
      true,
      ["deriveKey", "deriveBits"],
    );
  }

  async function registerPublicKey(url, publicKeySpkiB64, fetchOptions = {}) {
    const response = await fetch(url, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...(fetchOptions.headers || {}),
      },
      credentials: fetchOptions.credentials || "same-origin",
      body: JSON.stringify({
        publicKeySpkiB64,
        algorithm: ALGORITHM,
      }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const err = new Error(body.error || `HTTP ${response.status}`);
      err.code = body.error || "";
      throw err;
    }
    return body;
  }

  async function sealForRecipient(plaintext, recipientPublicKeySpkiB64) {
    const ephemeral = await generateIdentityKeyPair();
    const recipientPublic = await importPublicKeySpkiB64(recipientPublicKeySpkiB64);
    const aesKey = await deriveAesKey(ephemeral.privateKey, recipientPublic);
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ct = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv },
      aesKey,
      utf8Encode(plaintext),
    );
    const epk = await exportPublicKeySpkiB64(ephemeral.publicKey);
    return {
      e2e: true,
      v: ENVELOPE_VERSION,
      alg: "X25519-AES-GCM",
      epk,
      iv: b64Encode(iv),
      ct: b64Encode(new Uint8Array(ct)),
    };
  }

  async function openEnvelope(envelope, privateKey) {
    const epk = await importPublicKeySpkiB64(envelope.epk);
    const aesKey = await deriveAesKey(privateKey, epk);
    const plain = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: b64Decode(envelope.iv) },
      aesKey,
      b64Decode(envelope.ct),
    );
    return utf8Decode(new Uint8Array(plain));
  }

  async function encryptUtf8(plaintext, recipientPublicKeysSpkiB64) {
    const recipients = (recipientPublicKeysSpkiB64 || []).filter(Boolean);
    if (!recipients.length) {
      throw new Error("e2e_recipients_required");
    }
    const envelopes = [];
    for (const pub of recipients) {
      envelopes.push(await sealForRecipient(plaintext, pub));
    }
    if (envelopes.length === 1) {
      return JSON.stringify(envelopes[0]);
    }
    return JSON.stringify({ e2e: true, v: ENVELOPE_VERSION, multi: true, envelopes });
  }

  async function decryptUtf8(storedBody, entityType, entityId) {
    if (!isE2EEnvelope(storedBody)) {
      return storedBody;
    }
    const parsed = JSON.parse(storedBody);
    const privateKey = await loadPrivateKey(entityType, entityId);
    if (parsed.multi && Array.isArray(parsed.envelopes)) {
      for (const envelope of parsed.envelopes) {
        try {
          return await openEnvelope(envelope, privateKey);
        } catch {
          // try next envelope for this recipient
        }
      }
      throw new Error("e2e_decrypt_failed");
    }
    return openEnvelope(parsed, privateKey);
  }

  const RECOVERY_WORDS = [
    "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel",
    "india", "juliet", "kilo", "lima", "mike", "november", "oscar", "papa",
    "quebec", "romeo", "sierra", "tango", "uniform", "victor", "whiskey", "xray",
    "yankee", "zulu", "amber", "bronze", "coral", "drift", "ember", "flint",
  ];

  async function deriveRatchetKey(privateKey, threadId, chainIndex) {
    const seed = await crypto.subtle.exportKey("raw", await deriveAesKey(privateKey, privateKey));
    const material = utf8Encode(`${threadId}:${chainIndex}`);
    const digest = await crypto.subtle.digest("SHA-256", new Uint8Array([...new Uint8Array(seed), ...material]));
    return crypto.subtle.importKey("raw", digest, "AES-GCM", false, ["encrypt", "decrypt"]);
  }

  async function encryptUtf8Ratchet(plaintext, recipientPublicKeysSpkiB64, threadId, chainIndex = 0) {
    const base = await encryptUtf8(plaintext, recipientPublicKeysSpkiB64);
    const parsed = JSON.parse(base);
    const wrap = (env) => ({ ...env, v: 2, alg: "X25519-AES-GCM-RATCHET", ratchet: true, threadId, chainIndex });
    if (parsed.multi && Array.isArray(parsed.envelopes)) {
      return JSON.stringify({ ...parsed, v: 2, envelopes: parsed.envelopes.map(wrap) });
    }
    return JSON.stringify(wrap(parsed));
  }

  async function encryptBlob(fileBytes, recipientPublicKeysSpkiB64, meta = {}) {
    const recipients = (recipientPublicKeysSpkiB64 || []).filter(Boolean);
    if (!recipients.length) throw new Error("e2e_recipients_required");
    const dataKey = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt", "decrypt"]);
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const plain = fileBytes instanceof Uint8Array ? fileBytes : new Uint8Array(fileBytes);
    const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, dataKey, plain);
    const rawKey = await crypto.subtle.exportKey("raw", dataKey);
    const keyB64 = b64Encode(new Uint8Array(rawKey));
    const fileEnvelope = {
      e2e: true,
      v: ENVELOPE_VERSION,
      kind: "attachment",
      alg: "X25519-AES-GCM",
      filename: String(meta.filename || "file.bin"),
      mime: String(meta.mime || "application/octet-stream"),
      iv: b64Encode(iv),
      ct: b64Encode(new Uint8Array(ct)),
    };
    const wrappedKey = await encryptUtf8(keyB64, recipients);
    fileEnvelope.wrappedKey = wrappedKey;
    const keyEnvelopes = [];
    for (const pub of recipients) {
      keyEnvelopes.push(await sealForRecipient(keyB64, pub));
    }
    fileEnvelope.keyEnvelopes = keyEnvelopes.length === 1 ? keyEnvelopes[0] : { multi: true, envelopes: keyEnvelopes };
    return {
      blob: new Uint8Array(ct),
      meta: JSON.stringify(fileEnvelope),
    };
  }

  async function decryptBlob(cipherBytes, metaJson, entityType, entityId) {
    const meta = typeof metaJson === "string" ? JSON.parse(metaJson) : metaJson;
    if (!meta || meta.kind !== "attachment") throw new Error("e2e_attachment_meta_invalid");
    let keyB64 = "";
    if (meta.wrappedKey) {
      keyB64 = await decryptUtf8(typeof meta.wrappedKey === "string" ? meta.wrappedKey : JSON.stringify(meta.wrappedKey), entityType, entityId);
    } else if (meta.keyEnvelopes) {
      const privateKey = await loadPrivateKey(entityType, entityId);
      const env = meta.keyEnvelopes.multi ? meta.keyEnvelopes.envelopes?.[0] : meta.keyEnvelopes;
      keyB64 = await openEnvelope(env, privateKey);
    } else {
      throw new Error("e2e_attachment_key_missing");
    }
    const dataKey = await crypto.subtle.importKey("raw", b64Decode(keyB64), "AES-GCM", false, ["decrypt"]);
    const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: b64Decode(meta.iv) }, dataKey, cipherBytes instanceof Uint8Array ? cipherBytes : new Uint8Array(cipherBytes));
    return {
      bytes: new Uint8Array(plain),
      filename: meta.filename || "download.bin",
      mime: meta.mime || "application/octet-stream",
    };
  }

  async function exportRecoveryPhrase() {
    let raw = null;
    try { raw = localStorage.getItem(MASTER_KEY_STORAGE); } catch { raw = null; }
    if (!raw) throw new Error("e2e_recovery_unavailable");
    const digest = await sha256(b64Decode(raw));
    const view = new DataView(digest);
    const words = [];
    for (let i = 0; i < 12; i += 1) {
      words.push(RECOVERY_WORDS[view.getUint32(i * 4, false) % RECOVERY_WORDS.length]);
    }
    return words.join(" ");
  }

  async function importRecoveryPhrase(phrase) {
    const parts = String(phrase || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (parts.length !== 12) throw new Error("e2e_recovery_invalid");
    const digest = await sha256(utf8Encode(parts.join(" ")));
    const raw = b64Encode(new Uint8Array(digest).slice(0, 32));
    try { localStorage.setItem(MASTER_KEY_STORAGE, raw); } catch { /* session-only */ }
    return true;
  }

  async function rotateIdentity(entityType, entityId, registerUrl, fetchOptions = {}) {
    const id = identityStorageId(entityType, entityId);
    const existing = await idbGet(id);
    if (existing) {
      await idbPut({
        ...existing,
        id: `${id}:archived:${Date.now()}`,
        archivedAt: new Date().toISOString(),
      });
    }
    const keyPair = await generateIdentityKeyPair();
    const publicKeySpkiB64 = await exportPublicKeySpkiB64(keyPair.publicKey);
    const privateJwk = await crypto.subtle.exportKey("jwk", keyPair.privateKey);
    const privateKeyEnc = await encryptPrivateKeyJwk(privateJwk);
    await idbPut({
      id,
      entityType,
      entityId,
      publicKeySpkiB64,
      privateKeyEnc,
      algorithm: ALGORITHM,
      createdAt: new Date().toISOString(),
      rotatedAt: new Date().toISOString(),
    });
    if (registerUrl) {
      await registerPublicKey(registerUrl, publicKeySpkiB64, fetchOptions);
    }
    return { entityType, entityId, publicKeySpkiB64, algorithm: ALGORITHM };
  }

  async function decryptUtf8WithArchive(storedBody, entityType, entityId) {
    try {
      return await decryptUtf8(storedBody, entityType, entityId);
    } catch {
      const db = await openDb();
      const archived = await new Promise((resolve) => {
        const tx = db.transaction(IDB_STORE, "readonly");
        const store = tx.objectStore(IDB_STORE);
        const req = store.getAll();
        req.onsuccess = () => {
          const prefix = `${String(entityType).toLowerCase()}:${String(entityId).trim()}:archived:`;
          const rows = (req.result || []).filter((row) => String(row.id || "").startsWith(prefix));
          resolve(rows);
        };
        req.onerror = () => resolve([]);
      });
      for (const row of archived) {
        try {
          const jwk = await decryptPrivateKeyJwk(row.privateKeyEnc);
          const privateKey = await crypto.subtle.importKey("jwk", jwk, { name: ALGORITHM, namedCurve: ALGORITHM }, true, ["deriveKey", "deriveBits"]);
          const parsed = JSON.parse(storedBody);
          if (parsed.multi && Array.isArray(parsed.envelopes)) {
            for (const envelope of parsed.envelopes) {
              try { return await openEnvelope(envelope, privateKey); } catch { /* next */ }
            }
          } else {
            return await openEnvelope(parsed, privateKey);
          }
        } catch { /* next archive */ }
      }
      throw new Error("e2e_decrypt_failed");
    }
  }

  async function exportIdentityQrPayload(entityType, entityId) {
    const id = identityStorageId(entityType, entityId);
    const record = await idbGet(id);
    if (!record?.privateKeyEnc) throw new Error("e2e_identity_missing");
    const transferKey = crypto.getRandomValues(new Uint8Array(32));
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const master = await crypto.subtle.importKey("raw", transferKey, "AES-GCM", false, ["encrypt", "decrypt"]);
    const plain = utf8Encode(JSON.stringify(record.privateKeyEnc));
    const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, master, plain);
    const payload = {
      v: 1,
      kind: "identity-transfer",
      entityType,
      entityId,
      publicKeySpkiB64: record.publicKeySpkiB64,
      algorithm: ALGORITHM,
      iv: b64Encode(iv),
      ct: b64Encode(new Uint8Array(ct)),
      exp: Date.now() + 5 * 60 * 1000,
    };
    return {
      qrText: JSON.stringify({ ...payload, transferKey: b64Encode(transferKey) }),
      expiresAt: payload.exp,
    };
  }

  async function importIdentityQrPayload(qrText, entityType, entityId) {
    const parsed = JSON.parse(String(qrText || ""));
    if (parsed.kind !== "identity-transfer" || Date.now() > Number(parsed.exp || 0)) {
      throw new Error("e2e_transfer_expired");
    }
    const transferKey = b64Decode(parsed.transferKey);
    const master = await crypto.subtle.importKey("raw", transferKey, "AES-GCM", false, ["decrypt"]);
    const plain = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: b64Decode(parsed.iv) },
      master,
      b64Decode(parsed.ct),
    );
    const privateKeyEnc = JSON.parse(utf8Decode(new Uint8Array(plain)));
    const id = identityStorageId(entityType || parsed.entityType, entityId || parsed.entityId);
    await idbPut({
      id,
      entityType: entityType || parsed.entityType,
      entityId: entityId || parsed.entityId,
      publicKeySpkiB64: parsed.publicKeySpkiB64,
      privateKeyEnc,
      algorithm: parsed.algorithm || ALGORITHM,
      createdAt: new Date().toISOString(),
      importedAt: new Date().toISOString(),
    });
    return true;
  }

  global.E2ECrypto = Object.freeze({
    ALGORITHM,
    ENVELOPE_VERSION,
    init: async () => true,
    isE2EEnvelope,
    ensureLocalIdentity,
    registerPublicKey,
    encryptUtf8,
    decryptUtf8,
    encryptUtf8Ratchet,
    encryptBlob,
    decryptBlob,
    exportRecoveryPhrase,
    importRecoveryPhrase,
    rotateIdentity,
    decryptUtf8WithArchive,
    exportIdentityQrPayload,
    importIdentityQrPayload,
    exportPublicKeySpkiB64,
    importPublicKeySpkiB64,
  });
})(typeof window !== "undefined" ? window : globalThis);
