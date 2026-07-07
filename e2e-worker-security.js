/**
 * Worker PWA E2E security panel (recovery, rotation, QR transfer, device PIN).
 */
(function (global) {
  function e2eT(key) {
    if (typeof global.E2EI18n?.t === "function") {
      const lang = global.WorkerI18N?.getCurrentLang?.() || "de";
      return global.E2EI18n.t(key, lang);
    }
    return key;
  }

  function panelHtml() {
    return `
      <div class="e2e-security-card worker-e2e-panel">
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
        <div id="workerE2ePinLockBanner" class="e2e-security-lock-banner hidden"></div>
        <div class="e2e-security-pin-row">
          <input type="password" id="workerE2ePinInput" autocomplete="off" data-e2e-i18n-placeholder="e2eSecurityPinPlaceholder" />
          <button type="button" class="ghost small-btn" data-worker-e2e="pin-set" data-e2e-i18n="e2eSecurityBtnPinSet"></button>
          <button type="button" class="ghost small-btn" data-worker-e2e="pin-unlock" data-e2e-i18n="e2eSecurityBtnPinUnlock"></button>
        </div>
        <p class="e2e-security-subtitle" style="padding:0 16px 10px;margin:0;" data-e2e-i18n="e2eSecurityPinHint"></p>
        <div class="e2e-security-actions">
          <button type="button" class="ghost small-btn" data-worker-e2e="recovery" data-e2e-i18n="e2eSecurityBtnRecovery"></button>
          <button type="button" class="ghost small-btn" data-worker-e2e="rotate" data-e2e-i18n="e2eSecurityBtnRotate"></button>
          <button type="button" class="ghost small-btn" data-worker-e2e="qr-export" data-e2e-i18n="e2eSecurityBtnQrExport"></button>
          <button type="button" class="ghost small-btn" data-worker-e2e="qr-import" data-e2e-i18n="e2eSecurityBtnQrImport"></button>
        </div>
        <pre id="workerE2eSecurityOut" class="e2e-security-output"></pre>
        <textarea id="workerE2eQrImport" class="e2e-security-import" data-e2e-i18n-placeholder="e2eSecurityQrPlaceholder"></textarea>
      </div>
    `;
  }

  async function refreshPinBanner(host) {
    const banner = host.querySelector("#workerE2ePinLockBanner");
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

  function mountWorkerE2ESecurityPanel(host) {
    if (!host || typeof global.E2ECrypto === "undefined") return;
    host.innerHTML = panelHtml();
    global.E2EI18n?.applyDom?.(host);
    const out = host.querySelector("#workerE2eSecurityOut");
    const importBox = host.querySelector("#workerE2eQrImport");
    const pinInput = host.querySelector("#workerE2ePinInput");
    void refreshPinBanner(host);

    const getCtx = () => {
      const workerId = String(global.lastWorkerPayload?.worker?.id || "").trim();
      return { workerId, headersFn: global.buildWorkerAuthHeaders || (() => ({})) };
    };

    host.querySelector('[data-worker-e2e="pin-set"]')?.addEventListener("click", async () => {
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

    host.querySelector('[data-worker-e2e="pin-unlock"]')?.addEventListener("click", async () => {
      try {
        await global.E2ECrypto.unlockDevicePin(pinInput?.value || "");
        if (pinInput) pinInput.value = "";
        out.textContent = e2eT("e2eSecurityStatusPinOk");
        void refreshPinBanner(host);
        void global.ensureWorkerE2EIdentity?.();
      } catch {
        out.textContent = e2eT("e2eSecurityStatusPinBad");
      }
    });

    host.querySelector('[data-worker-e2e="recovery"]')?.addEventListener("click", async () => {
      try {
        out.textContent = await global.E2ECrypto.exportRecoveryPhrase();
      } catch (e) {
        out.textContent = String(e.message || e);
      }
    });
    host.querySelector('[data-worker-e2e="rotate"]')?.addEventListener("click", async () => {
      const { workerId, headersFn } = getCtx();
      if (!workerId) return;
      try {
        await global.E2ECrypto.rotateIdentity("worker", workerId, `${global.API_BASE || "/api"}/e2e/identity/me`, {
          headers: headersFn({ "Content-Type": "application/json" }),
          credentials: "include",
        });
        out.textContent = e2eT("e2eSecurityStatusRotated");
      } catch (e) {
        out.textContent = String(e.message || e);
      }
    });
    host.querySelector('[data-worker-e2e="qr-export"]')?.addEventListener("click", async () => {
      const { workerId } = getCtx();
      if (!workerId) return;
      try {
        const payload = await global.E2ECrypto.exportIdentityQrPayload("worker", workerId);
        out.textContent = payload.qrText;
      } catch (e) {
        out.textContent = String(e.message || e);
      }
    });
    host.querySelector('[data-worker-e2e="qr-import"]')?.addEventListener("click", () => {
      if (!importBox) return;
      importBox.style.display = importBox.style.display === "none" ? "block" : "none";
    });
    importBox?.addEventListener("blur", async () => {
      const { workerId, headersFn } = getCtx();
      const text = importBox.value.trim();
      if (!text || !workerId) return;
      try {
        await global.E2ECrypto.importIdentityQrPayload(text, "worker", workerId);
        const identity = await global.E2ECrypto.ensureLocalIdentity("worker", workerId);
        await global.E2ECrypto.registerPublicKey(`${global.API_BASE || "/api"}/e2e/identity/me`, identity.publicKeySpkiB64, {
          headers: headersFn({ "Content-Type": "application/json" }),
          credentials: "include",
        });
        out.textContent = e2eT("e2eSecurityStatusImported");
        importBox.value = "";
        importBox.style.display = "none";
      } catch (e) {
        out.textContent = String(e.message || e);
      }
    });
  }

  global.WorkerE2ESecurity = Object.freeze({ mountWorkerE2ESecurityPanel });
})(typeof window !== "undefined" ? window : globalThis);
