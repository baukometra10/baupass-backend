/**
 * BauPass — one-time Signotec bridge setup per PC (signoPAD-API/Web, port 49494).
 * Library is served from BauPass; bridge software runs locally on each machine with USB pad.
 */
(function initSignotecBridgeSetup(global) {
  const SESSION_HIDE = "baupass-signotec-bridge-hide-session";
  const OK_KEY = "baupass-signotec-bridge-ok";

  function panel() {
    return global.document.getElementById("signotecBridgeSetup");
  }

  function setStepState(stepId, state) {
    const el = global.document.getElementById(stepId);
    if (!el) return;
    el.dataset.state = state;
  }

  async function probeBridge() {
    const signotec = global.BaupassSignotec;
    if (!signotec) {
      return { lib: false, bridge: false, reason: "signotec_lib_missing" };
    }
    try {
      await signotec.loadLib();
    } catch {
      return { lib: false, bridge: false, reason: "signotec_lib_missing" };
    }
    const lib = signotec.isAvailable?.();
    if (!lib) {
      return { lib: false, bridge: false, reason: "signotec_lib_missing" };
    }
    try {
      const conn = await signotec.probeConnection();
      if (conn?.ok) {
        return { lib: true, bridge: true, reason: "", serverVersion: conn.serverVersion || "" };
      }
      return { lib: true, bridge: false, reason: conn?.reason || "signotec_ws_unreachable" };
    } catch (err) {
      return {
        lib: true,
        bridge: false,
        reason: String(err?.message || err || "signotec_ws_unreachable"),
      };
    }
  }

  function isFirefoxBrowser() {
    return /firefox/i.test(String(global.navigator?.userAgent || ""));
  }

  function updateFirefoxHint(state) {
    const hint = global.document.getElementById("signotecBridgeFirefoxHint");
    if (!hint) return;
    const show = isFirefoxBrowser() && state?.lib && !state?.bridge;
    hint.classList.toggle("hidden", !show);
  }

  async function refreshPanelState() {
    const root = panel();
    if (!root || root.classList.contains("hidden")) return null;
    const state = await probeBridge();
    setStepState("signotecBridgeStepLib", state.lib ? "ok" : "pending");
    setStepState("signotecBridgeStepInstall", state.bridge ? "ok" : state.lib ? "pending" : "idle");
    setStepState("signotecBridgeStepTrust", state.bridge ? "ok" : state.lib ? "pending" : "idle");
    setStepState("signotecBridgeStepReady", state.bridge ? "ok" : "idle");
    updateFirefoxHint(state);
    const status = global.document.getElementById("signotecBridgeStatus");
    if (status) {
      if (state.bridge) {
        status.textContent = "";
      } else if (typeof global.signotecBridgeStatusText === "function") {
        status.textContent = global.signotecBridgeStatusText(state);
      }
    }
    if (state.bridge) {
      try {
        global.localStorage.setItem(OK_KEY, "1");
      } catch {
        // ignore
      }
      hidePanel();
    }
    return state;
  }

  function showPanel(force) {
    const root = panel();
    if (!root) return;
    if (!force) {
      try {
        if (global.sessionStorage.getItem(SESSION_HIDE) === "1") return;
        if (global.localStorage.getItem(OK_KEY) === "1") return;
      } catch {
        // ignore
      }
    } else {
      try {
        global.sessionStorage.removeItem(SESSION_HIDE);
        global.localStorage.removeItem(OK_KEY);
      } catch {
        // ignore
      }
    }
    root.classList.remove("hidden");
    void refreshPanelState();
  }

  function hidePanel() {
    panel()?.classList.add("hidden");
  }

  function dismissPanel() {
    try {
      global.sessionStorage.setItem(SESSION_HIDE, "1");
    } catch {
      // ignore
    }
    hidePanel();
  }

  function apiBase() {
    try {
      return String(global.location?.origin || "").replace(/\/$/, "");
    } catch {
      return "";
    }
  }

  function downloadUrl(path) {
    const base = apiBase();
    return base ? `${base}${path}` : path;
  }

  function wirePanel() {
    const root = panel();
    if (!root || root.dataset.wired === "1") return;
    root.dataset.wired = "1";

    global.document.getElementById("signotecBridgeDownloadBtn")?.addEventListener("click", () => {
      global.open(downloadUrl("/api/signotec/installer"), "_blank", "noopener,noreferrer");
    });

    global.document.getElementById("signotecBridgeSetupScriptBtn")?.addEventListener("click", () => {
      global.open(downloadUrl("/api/signotec/setup-helper.bat"), "_blank", "noopener,noreferrer");
    });

    global.document.getElementById("signotecBridgeTrustBtn")?.addEventListener("click", () => {
      try {
        global.open("https://localhost:49494/", "_blank", "noopener,noreferrer");
      } catch {
        // ignore
      }
    });

    global.document.getElementById("signotecBridgeStartBtn")?.addEventListener("click", () => {
      global.open(downloadUrl("/api/signotec/start-bridge.bat"), "_blank", "noopener,noreferrer");
    });

    global.document.getElementById("signotecBridgeRetestBtn")?.addEventListener("click", () => {
      void refreshPanelState();
    });

    global.document.getElementById("signotecBridgeDismissBtn")?.addEventListener("click", () => {
      dismissPanel();
    });
  }

  async function maybeAutoShow() {
    if (global.navigator?.platform && !/win/i.test(global.navigator.platform)) return;
    let ok = false;
    try {
      ok = global.localStorage.getItem(OK_KEY) === "1";
    } catch {
      // ignore
    }
    if (ok) return;
    const state = await probeBridge();
    if (!state.bridge && state.lib) showPanel(false);
  }

  global.BaupassSignotecBridge = {
    probeBridge,
    showPanel,
    hidePanel,
    refreshPanelState,
    maybeAutoShow,
    wire: wirePanel,
  };
})(window);
