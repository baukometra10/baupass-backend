/**
 * Shared admin E2E helpers for index.html, contracts.html, ai-command-center.
 */
(function (global) {
  const WP = global.WorkPassStorage;
  const wpGet = (key) => (WP?.getItem ? WP.getItem(key) : localStorage.getItem(key));

  function getAdminUserId() {
    try {
      return String(JSON.parse(wpGet(WP?.KEYS?.ADMIN_USER || "workpass-admin-user") || "{}").id || "");
    } catch {
      return "";
    }
  }

  function getToken() {
    return wpGet(WP?.KEYS?.ADMIN_TOKEN || "workpass-admin-token")
      || wpGet(WP?.KEYS?.SESSION_TOKEN || "workpass-session-token")
      || "";
  }

  function authHeaders(extra = {}) {
    const token = getToken();
    return {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...extra,
    };
  }

  let identityReady = false;
  const keyCache = new Map();

  function cryptoReady() {
    return typeof global.E2ECrypto !== "undefined" && Boolean(getAdminUserId());
  }

  async function ensureIdentity() {
    const adminUserId = getAdminUserId();
    if (!cryptoReady()) {
      identityReady = false;
      return false;
    }
    try {
      const identity = await global.E2ECrypto.ensureLocalIdentity("user", adminUserId);
      await global.E2ECrypto.registerPublicKey("/api/e2e/identity/admin/me", identity.publicKeySpkiB64, {
        headers: authHeaders({ "Content-Type": "application/json" }),
        credentials: "include",
      });
      identityReady = true;
      return true;
    } catch {
      identityReady = false;
      return false;
    }
  }

  async function fetchPublicKeys(workerId, companyId) {
    if (!cryptoReady()) return [];
    if (!identityReady) await ensureIdentity();
    const cacheKey = `${companyId || ""}:${workerId || ""}`;
    if (keyCache.has(cacheKey)) return keyCache.get(cacheKey);
    const qs = new URLSearchParams();
    if (companyId) qs.set("company_id", companyId);
    if (workerId) qs.set("worker_id", workerId);
    try {
      const res = await fetch(`/api/e2e/identity/admin/public-keys?${qs.toString()}`, {
        headers: authHeaders(),
        credentials: "include",
      });
      const data = await res.json().catch(() => ({}));
      const keys = (data.publicKeys || [])
        .map((row) => String(row.publicKeySpkiB64 || row.public_key_spki_b64 || "").trim())
        .filter(Boolean);
      keyCache.set(cacheKey, keys);
      return keys;
    } catch {
      return keyCache.get(cacheKey) || [];
    }
  }

  async function decryptField(storedBody) {
    const text = String(storedBody || "");
    if (!text || !cryptoReady() || !global.E2ECrypto.isE2EEnvelope(text)) return text;
    try {
      return await global.E2ECrypto.decryptUtf8WithArchive(text, "user", getAdminUserId());
    } catch {
      return "[E2E — Entschlüsselung fehlgeschlagen]";
    }
  }

  async function encryptField(plaintext, workerId, companyId) {
    const text = String(plaintext || "");
    if (!text || global.E2ECrypto?.isE2EEnvelope?.(text)) return text;
    if (!cryptoReady()) throw new Error("e2e_crypto_unavailable");
    const keys = await fetchPublicKeys(workerId, companyId);
    if (!keys.length) throw new Error("e2e_keys_missing");
    return global.E2ECrypto.encryptUtf8(text, keys);
  }

  async function decryptLeaveRequests(rows) {
    if (!Array.isArray(rows) || !cryptoReady()) return rows || [];
    const out = [];
    for (const row of rows) {
      const copy = { ...row };
      if (copy.note) copy.note = await decryptField(copy.note);
      if (copy.review_note) copy.review_note = await decryptField(copy.review_note);
      out.push(copy);
    }
    return out;
  }

  async function encryptDocumentUpload(file, workerId, companyId) {
    const keys = await fetchPublicKeys(workerId, companyId);
    if (!keys.length) throw new Error("e2e_keys_missing");
    const buffer = await file.arrayBuffer();
    return global.E2ECrypto.encryptBlob(new Uint8Array(buffer), keys, {
      filename: file.name || "upload.bin",
      mime: file.type || "application/octet-stream",
    });
  }

  async function encryptNotesField(notes, workerId, companyId) {
    const text = String(notes || "").trim();
    if (!text) return "";
    return encryptField(text, workerId, companyId);
  }

  function mountSecurityPanel(host, { entityType = "user", entityId = "", companyId = "" } = {}) {
    if (!host || !cryptoReady()) return;
    const id = entityId || getAdminUserId();
    host.innerHTML = `
      <div class="e2e-security-panel" style="margin-top:0.75rem;padding:0.65rem;border:1px solid var(--border,#334);border-radius:10px;">
        <strong style="display:block;margin-bottom:0.35rem;">E2E-Sicherheit</strong>
        <p class="muted" style="font-size:0.75rem;margin:0 0 0.5rem;">Schlüssel, Recovery und Gerätetransfer — Private Keys verlassen nie den Server.</p>
        <div style="display:flex;flex-wrap:wrap;gap:0.35rem;">
          <button type="button" class="ghost small-btn" data-e2e-action="recovery-export">Recovery-Phrase anzeigen</button>
          <button type="button" class="ghost small-btn" data-e2e-action="rotate">Schlüssel rotieren</button>
          <button type="button" class="ghost small-btn" data-e2e-action="qr-export">QR-Transfer (export)</button>
          <button type="button" class="ghost small-btn" data-e2e-action="qr-import">QR-Transfer (import)</button>
        </div>
        <pre id="e2eSecurityOutput" class="muted" style="font-size:0.68rem;white-space:pre-wrap;margin:0.5rem 0 0;max-height:120px;overflow:auto;"></pre>
        <textarea id="e2eQrImportInput" placeholder="QR-/Transfer-JSON einfügen…" style="display:none;margin-top:0.35rem;font-size:0.72rem;min-height:64px;"></textarea>
      </div>
    `;
    const out = host.querySelector("#e2eSecurityOutput");
    const importBox = host.querySelector("#e2eQrImportInput");
    host.querySelector('[data-e2e-action="recovery-export"]')?.addEventListener("click", async () => {
      try {
        await ensureIdentity();
        out.textContent = await global.E2ECrypto.exportRecoveryPhrase();
      } catch (e) {
        out.textContent = String(e.message || e);
      }
    });
    host.querySelector('[data-e2e-action="rotate"]')?.addEventListener("click", async () => {
      try {
        await global.E2ECrypto.rotateIdentity(entityType, id, "/api/e2e/identity/admin/me", {
          headers: authHeaders({ "Content-Type": "application/json" }),
          credentials: "include",
        });
        identityReady = true;
        keyCache.clear();
        out.textContent = "Schlüssel rotiert und Public Key registriert.";
      } catch (e) {
        out.textContent = String(e.message || e);
      }
    });
    host.querySelector('[data-e2e-action="qr-export"]')?.addEventListener("click", async () => {
      try {
        await ensureIdentity();
        const payload = await global.E2ECrypto.exportIdentityQrPayload(entityType, id);
        out.textContent = payload.qrText;
      } catch (e) {
        out.textContent = String(e.message || e);
      }
    });
    host.querySelector('[data-e2e-action="qr-import"]')?.addEventListener("click", () => {
      importBox.style.display = importBox.style.display === "none" ? "block" : "none";
      if (importBox.style.display === "block") {
        importBox.onchange = null;
        importBox.onblur = async () => {
          try {
            await global.E2ECrypto.importIdentityQrPayload(importBox.value.trim(), entityType, id);
            await global.E2ECrypto.registerPublicKey("/api/e2e/identity/admin/me", (await global.E2ECrypto.ensureLocalIdentity(entityType, id)).publicKeySpkiB64, {
              headers: authHeaders({ "Content-Type": "application/json" }),
              credentials: "include",
            });
            out.textContent = "Identität importiert.";
            importBox.value = "";
            importBox.style.display = "none";
          } catch (e) {
            out.textContent = String(e.message || e);
          }
        };
      }
    });
  }

  global.E2EAdminBridge = Object.freeze({
    getAdminUserId,
    authHeaders,
    ensureIdentity,
    fetchPublicKeys,
    decryptField,
    encryptField,
    decryptLeaveRequests,
    encryptDocumentUpload,
    encryptNotesField,
    mountSecurityPanel,
    cryptoReady,
  });
})(typeof window !== "undefined" ? window : globalThis);
