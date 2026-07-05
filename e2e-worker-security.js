/**
 * Worker PWA E2E security panel (recovery, rotation, QR transfer).
 */
(function (global) {
  function mountWorkerE2ESecurityPanel(host) {
    if (!host || typeof global.E2ECrypto === "undefined") return;
    host.innerHTML = `
      <div class="e2e-security-panel worker-e2e-panel">
        <p class="muted-info" style="font-size:0.78rem;margin:0 0 0.5rem;">Ende-zu-Ende-Schlüssel — nur auf diesem Gerät.</p>
        <div class="worker-e2e-actions" style="display:flex;flex-wrap:wrap;gap:0.35rem;">
          <button type="button" class="ghost small-btn" data-worker-e2e="recovery">Recovery-Phrase</button>
          <button type="button" class="ghost small-btn" data-worker-e2e="rotate">Schlüssel erneuern</button>
          <button type="button" class="ghost small-btn" data-worker-e2e="qr-export">QR exportieren</button>
          <button type="button" class="ghost small-btn" data-worker-e2e="qr-import">QR importieren</button>
        </div>
        <pre id="workerE2eSecurityOut" class="muted-info" style="font-size:0.68rem;white-space:pre-wrap;margin:0.5rem 0 0;max-height:100px;overflow:auto;"></pre>
        <textarea id="workerE2eQrImport" placeholder="Transfer-JSON…" style="display:none;width:100%;margin-top:0.35rem;font-size:0.72rem;min-height:56px;"></textarea>
      </div>
    `;
    const out = host.querySelector("#workerE2eSecurityOut");
    const importBox = host.querySelector("#workerE2eQrImport");
    const getCtx = () => {
      const workerId = String(global.lastWorkerPayload?.worker?.id || "").trim();
      return { workerId, headersFn: global.buildWorkerAuthHeaders || (() => ({})) };
    };
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
        out.textContent = "Schlüssel erneuert.";
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
        out.textContent = "Identität importiert.";
        importBox.value = "";
        importBox.style.display = "none";
      } catch (e) {
        out.textContent = String(e.message || e);
      }
    });
  }

  global.WorkerE2ESecurity = Object.freeze({ mountWorkerE2ESecurityPanel });
})(typeof window !== "undefined" ? window : globalThis);
