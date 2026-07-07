/**
 * Shared admin E2E helpers for index.html, contracts.html, ai-command-center.
 */
(function (global) {
  const WP = global.WorkPassStorage;
  const wpGet = (key) => (WP?.getItem ? WP.getItem(key) : localStorage.getItem(key));

  function e2eT(key) {
    if (typeof global.E2EI18n?.t === "function") {
      const lang = typeof global.getCurrentLang === "function" ? global.getCurrentLang() : "";
      return global.E2EI18n.t(key, lang);
    }
    return key;
  }

  function getAdminUserId() {
    try {
      const fromStorage = String(JSON.parse(wpGet(WP?.KEYS?.ADMIN_USER || "workpass-admin-user") || "{}").id || "").trim();
      if (fromStorage) return fromStorage;
    } catch {
      // ignore parse errors
    }
    try {
      return String(
        global.state?.currentUser?.id
        || global.getCurrentUser?.()?.id
        || ""
      ).trim();
    } catch {
      return "";
    }
  }

  function getAdminCompanyId() {
    try {
      const preview = String(
        wpGet(WP?.KEYS?.PREVIEW_COMPANY_ID || "workpass-preview-company-id")
        || ""
      ).trim();
      if (preview) return preview;
      const storedUser = JSON.parse(wpGet(WP?.KEYS?.ADMIN_USER || "workpass-admin-user") || "{}");
      return String(
        storedUser?.preview_company_id
        || storedUser?.company_id
        || storedUser?.companyId
        || wpGet(WP?.KEYS?.ADMIN_COMPANY || "workpass-admin-company")
        || ""
      ).trim();
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
      const companyId = getAdminCompanyId();
      const registerBody = { publicKeySpkiB64: identity.publicKeySpkiB64 };
      if (companyId) {
        registerBody.company_id = companyId;
        registerBody.companyId = companyId;
      }
      const response = await fetch("/api/e2e/identity/admin/me", {
        method: "PUT",
        headers: authHeaders({ "Content-Type": "application/json" }),
        credentials: "include",
        body: JSON.stringify(registerBody),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        const err = new Error(body.error || `HTTP ${response.status}`);
        err.code = body.error || "";
        throw err;
      }
      identityReady = true;
      keyCache.clear();
      return true;
    } catch (error) {
      console.warn("[E2E] Admin identity bootstrap failed:", error?.message || error);
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

  function securityPanelHtml() {
    return `
      <div class="e2e-security-card">
        <div class="e2e-security-card-head">
          <div class="e2e-security-icon" aria-hidden="true">🔐</div>
          <div>
            <p class="e2e-security-kicker" data-e2e-i18n="e2eSecurityEyebrow">Verschlüsselung</p>
            <h4 data-e2e-i18n="e2eSecurityTitle">E2E-Sicherheit</h4>
            <p class="e2e-security-subtitle" data-e2e-i18n="e2eSecuritySubtitle"></p>
          </div>
        </div>
        <div class="e2e-security-badges">
          <span class="e2e-security-badge is-secure" data-e2e-i18n="e2eSecurityBadgeLocal"></span>
          <span class="e2e-security-badge is-secure" data-e2e-i18n="e2eSecurityBadgeAlgo"></span>
          <span class="e2e-security-badge is-secure" data-e2e-i18n="e2eSecurityBadgeServer"></span>
        </div>
        <div id="e2ePinLockBanner" class="e2e-security-lock-banner hidden"></div>
        <details class="e2e-security-advanced">
          <summary data-e2e-i18n="e2eSecurityAdvancedTitle">Erweitert (optional)</summary>
          <div class="e2e-security-pin-row">
            <input type="password" id="e2ePinInput" autocomplete="off" data-e2e-i18n-placeholder="e2eSecurityPinPlaceholder" />
            <button type="button" class="ghost small-btn" data-e2e-action="pin-set" data-e2e-i18n="e2eSecurityBtnPinSet"></button>
            <button type="button" class="ghost small-btn" data-e2e-action="pin-unlock" data-e2e-i18n="e2eSecurityBtnPinUnlock"></button>
          </div>
          <p class="e2e-security-subtitle" style="padding:0 16px 10px;margin:0;" data-e2e-i18n="e2eSecurityPinHint"></p>
        </details>
        <div class="e2e-security-actions">
          <button type="button" class="ghost small-btn" data-e2e-action="recovery-export" data-e2e-i18n="e2eSecurityBtnRecovery"></button>
          <button type="button" class="ghost small-btn" data-e2e-action="rotate" data-e2e-i18n="e2eSecurityBtnRotate"></button>
          <button type="button" class="ghost small-btn" data-e2e-action="qr-export" data-e2e-i18n="e2eSecurityBtnQrExport"></button>
          <button type="button" class="ghost small-btn" data-e2e-action="qr-import" data-e2e-i18n="e2eSecurityBtnQrImport"></button>
        </div>
        <pre id="e2eSecurityOutput" class="e2e-security-output"></pre>
        <textarea id="e2eQrImportInput" class="e2e-security-import" data-e2e-i18n-placeholder="e2eSecurityQrPlaceholder"></textarea>
      </div>
    `;
  }

  async function refreshPinBanner(host) {
    const banner = host.querySelector("#e2ePinLockBanner");
    if (!banner || !global.E2ECrypto?.isDevicePinEnabled) return;
    const enabled = await global.E2ECrypto.isDevicePinEnabled();
    if (!enabled) {
      banner.classList.add("hidden");
      return;
    }
    banner.classList.remove("hidden");
    const unlocked = global.E2ECrypto.isDevicePinUnlocked?.();
    banner.classList.toggle("is-unlocked", unlocked);
    banner.textContent = unlocked ? e2eT("e2eSecurityLockUnlocked") : e2eT("e2eSecurityLockLocked");
  }

  function mountSecurityPanel(host, { entityType = "user", entityId = "", companyId = "" } = {}) {
    if (!host || !cryptoReady()) return;
    const id = entityId || getAdminUserId();
    host.innerHTML = securityPanelHtml();
    global.E2EI18n?.applyDom?.(host);
    const out = host.querySelector("#e2eSecurityOutput");
    const importBox = host.querySelector("#e2eQrImportInput");
    const pinInput = host.querySelector("#e2ePinInput");
    void refreshPinBanner(host);

    host.querySelector('[data-e2e-action="pin-set"]')?.addEventListener("click", async () => {
      try {
        const pin = pinInput?.value || "";
        if (pin.length < 6) {
          out.textContent = e2eT("e2eSecurityStatusPinShort");
          return;
        }
        await global.E2ECrypto.setDevicePin(pin);
        if (pinInput) pinInput.value = "";
        out.textContent = e2eT("e2eSecurityStatusPinSet");
        void refreshPinBanner(host);
      } catch (e) {
        out.textContent = String(e.message || e);
      }
    });

    host.querySelector('[data-e2e-action="pin-unlock"]')?.addEventListener("click", async () => {
      try {
        await global.E2ECrypto.unlockDevicePin(pinInput?.value || "");
        if (pinInput) pinInput.value = "";
        out.textContent = e2eT("e2eSecurityStatusPinOk");
        identityReady = false;
        await ensureIdentity();
        void refreshPinBanner(host);
      } catch (e) {
        out.textContent = e2eT("e2eSecurityStatusPinBad");
      }
    });

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
        out.textContent = e2eT("e2eSecurityStatusRotated");
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
      if (!importBox) return;
      importBox.style.display = importBox.style.display === "none" ? "block" : "none";
      if (importBox.style.display === "block") {
        importBox.onblur = async () => {
          try {
            await global.E2ECrypto.importIdentityQrPayload(importBox.value.trim(), entityType, id);
            await global.E2ECrypto.registerPublicKey("/api/e2e/identity/admin/me", (await global.E2ECrypto.ensureLocalIdentity(entityType, id)).publicKeySpkiB64, {
              headers: authHeaders({ "Content-Type": "application/json" }),
              credentials: "include",
            });
            out.textContent = e2eT("e2eSecurityStatusImported");
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
