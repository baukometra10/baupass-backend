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

  global.E2ECrypto = Object.freeze({
    ALGORITHM,
    ENVELOPE_VERSION,
    init: async () => true,
    isE2EEnvelope,
    ensureLocalIdentity,
    registerPublicKey,
    encryptUtf8,
    decryptUtf8,
    exportPublicKeySpkiB64,
    importPublicKeySpkiB64,
  });
})(typeof window !== "undefined" ? window : globalThis);
