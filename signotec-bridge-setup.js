/**
 * SUPPIX — Signotec one-page setup (single download flow).
 */
(function initSignotecBridgeSetup(global) {
  const SETUP_PAGE = "/signotec-setup.html";
  const SETUP_BAT = "/api/signotec/setup.bat";

  function panel() {
    return global.document.getElementById("signotecBridgeSetup");
  }

  async function probeBridge() {
    const signotec = global.BaupassSignotec;
    if (!signotec) return { lib: false, bridge: false };
    try { await signotec.loadLib(); } catch { return { lib: false, bridge: false }; }
    if (!signotec.isAvailable?.()) return { lib: false, bridge: false };
    try {
      const conn = await signotec.probeConnection();
      return { lib: true, bridge: Boolean(conn?.ok) };
    } catch {
      return { lib: true, bridge: false };
    }
  }

  function showPanel() {
    const root = panel();
    if (!root) {
      global.open(SETUP_PAGE, "_blank", "noopener,noreferrer");
      return;
    }
    root.classList.remove("hidden");
  }

  function hidePanel() {
    panel()?.classList.add("hidden");
  }

  function wirePanel() {
    const root = panel();
    if (!root || root.dataset.wired === "1") return;
    root.dataset.wired = "1";

    global.document.getElementById("signotecBridgeOpenGuideBtn")?.addEventListener("click", () => {
      global.open(SETUP_PAGE, "_blank", "noopener,noreferrer");
    });

    global.document.getElementById("signotecBridgeDownloadBtn")?.addEventListener("click", () => {
      global.open(SETUP_BAT, "_blank", "noopener,noreferrer");
    });

    global.document.getElementById("signotecBridgeRetestBtn")?.addEventListener("click", async () => {
      const state = await probeBridge();
      if (state.bridge) hidePanel();
      else showPanel();
    });
  }

  async function maybeAutoShow() {
    if (global.navigator?.platform && !/win/i.test(global.navigator.platform)) return;
    const state = await probeBridge();
    if (!state.bridge && state.lib) showPanel();
  }

  global.BaupassSignotecBridge = {
    probeBridge,
    showPanel,
    hidePanel,
    maybeAutoShow,
    wire: wirePanel,
    setupPage: SETUP_PAGE,
    setupBat: SETUP_BAT,
  };
})(window);
