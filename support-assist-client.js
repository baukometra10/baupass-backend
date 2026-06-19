(function initBaupassSupportAssist(global) {
  const STORAGE_KEY = "baupass-support-assist-watch";
  let pollTimer = null;
  let publicWatchTimer = null;
  let publicWatchCompanyId = "";
  let lastSeq = 0;
  let bannerEl = null;
  let cursorEl = null;
  let statusEl = null;
  let viewChipEl = null;
  let isSpectator = false;
  let isAgent = false;
  let spectatorAllowLogin = false;

  function readWatchState() {
    try {
      const raw = global.sessionStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  function writeWatchState(state) {
    try {
      if (!state) {
        global.sessionStorage.removeItem(STORAGE_KEY);
        return;
      }
      global.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // ignore
    }
  }

  function apiBase() {
    return String(global.API_BASE || global.location.origin || "").replace(/\/+$/, "");
  }

  function isLoginTarget(target) {
    if (!target || !target.closest) return false;
    return Boolean(
      target.closest(
        "#authOverlay, .auth-panel, .auth-form, #loginForm, #loginUsername, #loginPassword, "
        + "#loginSubmitButton, #loginOtpCode, #loginScope, #loginSetupEmail, .auth-lang-field, "
        + "#loginSupportNotice, .server-auth-shell, #f",
      ),
    );
  }

  function ensureBanner() {
    if (bannerEl) return bannerEl;
    bannerEl = document.createElement("div");
    bannerEl.id = "supportAssistSpectatorBanner";
    bannerEl.className = "support-assist-spectator hidden";
    bannerEl.innerHTML = `
      <div class="support-assist-spectator-card support-assist-spectator-compact">
        <div class="support-assist-live-row">
          <span class="support-assist-live-dot" aria-hidden="true"></span>
          <strong id="supportAssistSpectatorTitle">Live-Support</strong>
          <span id="supportAssistSpectatorView" class="support-assist-view-chip"></span>
        </div>
        <p id="supportAssistSpectatorStatus" class="support-assist-status"></p>
      </div>
    `;
    statusEl = bannerEl.querySelector("#supportAssistSpectatorStatus");
    viewChipEl = bannerEl.querySelector("#supportAssistSpectatorView");
    document.body.appendChild(bannerEl);

    cursorEl = document.createElement("div");
    cursorEl.id = "supportAssistRemoteCursor";
    cursorEl.className = "support-assist-remote-cursor hidden";
    cursorEl.innerHTML = `<span class="support-assist-remote-cursor-label">Support</span>`;
    document.body.appendChild(cursorEl);

    document.addEventListener("mousedown", blockSpectatorInput, true);
    document.addEventListener("keydown", blockSpectatorInput, true);
    document.addEventListener("touchstart", blockSpectatorInput, true);
    document.addEventListener("click", blockSpectatorInput, true);
    return bannerEl;
  }

  function blockSpectatorInput(event) {
    if (!isSpectator) return;
    const target = event.target;
    if (target && target.closest && target.closest("#supportAssistSpectatorBanner")) {
      return;
    }
    if (spectatorAllowLogin && isLoginTarget(target)) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    return false;
  }

  function setSpectatorMode(active, actorName, message, options) {
    const opts = options || {};
    isSpectator = Boolean(active);
    spectatorAllowLogin = Boolean(opts.allowLogin);
    const banner = ensureBanner();
    banner.classList.toggle("hidden", !active);
    banner.classList.toggle("support-assist-spectator-login-ready", spectatorAllowLogin);
    document.body.classList.toggle("support-assist-spectator-active", active);
    document.body.classList.toggle("support-assist-spectator-login-ready", spectatorAllowLogin);
    const title = banner.querySelector("#supportAssistSpectatorTitle");
    if (title) {
      title.textContent = actorName ? `${actorName} übernimmt` : "Support ist aktiv";
    }
    if (statusEl && message) {
      statusEl.textContent = message;
    }
    if (!active && cursorEl) {
      cursorEl.classList.add("hidden");
    }
    if (!active) {
      global.document.body.classList.remove("support-assist-mirror-auth");
      if (global.BaupassSession?.clearSupportAssistLoginMirror) {
        try { global.BaupassSession.clearSupportAssistLoginMirror(); } catch { /* ignore */ }
      }
    }
    if (spectatorAllowLogin && global.BaupassSession?.focusLoginInput) {
      global.setTimeout(() => {
        try { global.BaupassSession.focusLoginInput({ force: true }); } catch { /* ignore */ }
      }, 120);
    }
  }

  function mirrorAgentView(payload) {
    const view = String(payload?.view || "").trim();
    if (!view || !global.BaupassSession?.setView) return;
    try {
      global.BaupassSession.setView(view);
    } catch {
      // ignore mirror failures
    }
  }

  function updateSpectatorBanner(uiState) {
    if (!bannerEl) return;
    const actor = uiState?.actorName || "";
    const title = bannerEl.querySelector("#supportAssistSpectatorTitle");
    if (title) {
      title.textContent = actor ? `${actor} — Live` : "Live-Support";
    }
    if (viewChipEl) {
      const label = String(uiState?.viewLabel || uiState?.view || "").trim();
      viewChipEl.textContent = label;
      viewChipEl.classList.toggle("hidden", !label);
    }
    if (!statusEl) return;
    if (uiState?.authVisible && !uiState?.loggedIn) {
      const user = String(uiState.loginUsername || "").trim();
      statusEl.textContent = user
        ? `Anmeldung: Benutzername „${user}" — Passwort verborgen`
        : "Support ist auf dem Anmeldebildschirm — Passwort bleibt verborgen";
      return;
    }
    const label = String(uiState?.viewLabel || uiState?.view || "").trim();
    statusEl.textContent = label
      ? `Sie sehen live dieselbe Seite: ${label}`
      : "Sie sehen live mit, was Support gerade tut";
  }

  function applyUiState(payload, actorName) {
    const uiState = { ...(payload || {}), actorName: payload?.actorName || actorName };
    if (global.BaupassSession?.applySupportAssistUiState) {
      global.BaupassSession.applySupportAssistUiState(uiState);
    } else {
      mirrorAgentView(uiState);
    }
    updateSpectatorBanner(uiState);
  }

  function moveRemoteCursor(payload) {
    if (!cursorEl || !payload) return;
    const x = Number(payload.x);
    const y = Number(payload.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    cursorEl.style.left = `${Math.max(0, Math.min(100, x))}vw`;
    cursorEl.style.top = `${Math.max(0, Math.min(100, y))}vh`;
    cursorEl.classList.remove("hidden");
    const label = cursorEl.querySelector(".support-assist-remote-cursor-label");
    if (label && payload.actorName) {
      label.textContent = payload.actorName;
    }
  }

  function messageForEvent(type, payload, actorName) {
    const actor = payload?.actorName || actorName || "Support";
    switch (type) {
      case "session_start":
        return `${actor} startet eine Support-Sitzung. Sie sehen live mit, was geöffnet wird.`;
      case "force_logout":
        return payload?.message || "Support übernimmt — bitte zuschauen, Eingaben sind gesperrt.";
      case "logout":
        return payload?.message || `${actor} hat sich abgemeldet. Sie können sich jetzt anmelden.`;
      case "login_screen":
        return `${actor} ist auf dem Anmeldebildschirm. Sie können sich anmelden, sobald Support fertig ist.`;
      case "logging_in":
        return `${actor} meldet sich an…`;
      case "logged_in":
        return `${actor} ist angemeldet — Sie sehen dieselbe Oberfläche live.`;
      case "view":
        return `${actor} öffnet: ${payload?.viewLabel || payload?.view || "Ansicht"}`;
      case "ui_state":
        return payload?.viewLabel ? `Seite: ${payload.viewLabel}` : "Live-Ansicht wird übertragen…";
      case "session_end":
        return "Support-Sitzung beendet — Sie können sich wieder anmelden.";
      default:
        return payload?.message || "Support ist aktiv — bitte zuschauen.";
    }
  }

  function handleAssistEvents(events, actorName) {
    (events || []).forEach((evt) => {
      const type = String(evt?.type || "");
      const payload = evt?.payload || {};
      if (Number(evt?.seq || 0) > lastSeq) {
        lastSeq = Number(evt.seq);
      }
      if (type === "mouse") {
        moveRemoteCursor({ ...payload, actorName });
        return;
      }
      if (type === "ui_state" || type === "view" || type === "logging_in") {
        applyUiState(payload, actorName);
        setSpectatorMode(true, actorName, messageForEvent(type === "view" ? "view" : "ui_state", payload, actorName));
        return;
      }
      if (type === "force_logout") {
        applyUiState({ authVisible: true, loggedIn: false, viewLabel: "Anmeldung", view: "dashboard" }, actorName);
        setSpectatorMode(true, actorName, messageForEvent(type, payload, actorName));
        if (global.BaupassSession?.refreshAll) {
          try { global.BaupassSession.refreshAll(); } catch { /* ignore */ }
        }
        return;
      }
      if (type === "logout" || type === "login_screen") {
        applyUiState({ authVisible: true, loggedIn: false, ...(payload || {}) }, actorName);
        setSpectatorMode(true, actorName, messageForEvent(type, payload, actorName), { allowLogin: true });
        if (global.BaupassSession?.refreshAll) {
          try { global.BaupassSession.refreshAll(); } catch { /* ignore */ }
        }
        return;
      }
      if (type === "logged_in") {
        applyUiState({ ...(payload || {}), loggedIn: true, authVisible: false }, actorName);
        setSpectatorMode(true, actorName, messageForEvent(type, payload, actorName));
        if (global.BaupassSession?.refreshAll) {
          try { global.BaupassSession.refreshAll(); } catch { /* ignore */ }
        }
        return;
      }
      if (type === "session_end") {
        setSpectatorMode(false);
        writeWatchState(null);
        stopPolling();
        if (global.BaupassSession?.refreshAll) {
          try { global.BaupassSession.refreshAll(); } catch { /* ignore */ }
        }
        return;
      }
      setSpectatorMode(true, actorName, messageForEvent(type, payload, actorName));
    });
  }

  async function pollOnce() {
    const state = readWatchState();
    if (!state?.companyId || !state?.watchToken) {
      return;
    }
    const q = new URLSearchParams({
      company_id: state.companyId,
      watch_token: state.watchToken,
      since_seq: String(lastSeq || 0),
    });
    try {
      const res = await fetch(`${apiBase()}/api/public/support-assist/poll?${q.toString()}`, {
        credentials: "include",
        cache: "no-store",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data?.active) {
        if (lastSeq > 0) {
          setSpectatorMode(false);
          writeWatchState(null);
          stopPolling();
          if (global.BaupassSession?.refreshAll) {
            try { global.BaupassSession.refreshAll(); } catch { /* ignore */ }
          }
        }
        return;
      }
      handleAssistEvents(data.events || [], data.actorName || state.actorName);
    } catch {
      // ignore transient network errors
    }
  }

  function startPolling(state) {
    writeWatchState(state);
    lastSeq = 0;
    ensureBanner();
    setSpectatorMode(true, state?.actorName, "Support verbindet…");
    stopPolling();
    pollOnce();
    pollTimer = global.setInterval(pollOnce, 900);
  }

  function stopPolling() {
    if (pollTimer) {
      global.clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function fetchPublicActive(companyId) {
    if (!companyId) return null;
    try {
      const res = await fetch(
        `${apiBase()}/api/public/support-assist/active?company_id=${encodeURIComponent(companyId)}`,
        { credentials: "include", cache: "no-store" },
      );
      if (!res.ok) return null;
      const data = await res.json();
      return data?.active && data?.watchToken ? data : null;
    } catch {
      return null;
    }
  }

  async function checkActiveForCompanyAdmin(companyId, token) {
    if (!companyId) return;
    let data = null;
    if (token) {
      try {
        const res = await fetch(`${apiBase()}/api/support-assist/active?company_id=${encodeURIComponent(companyId)}`, {
          headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
          credentials: "include",
          cache: "no-store",
        });
        if (res.ok) {
          data = await res.json();
        }
      } catch {
        // fall back to public active lookup
      }
    }
    if (!data?.active || !data?.watchToken) {
      data = await fetchPublicActive(companyId);
    }
    if (!data?.active || !data?.watchToken) return;
    startPolling({
      companyId,
      watchToken: data.watchToken,
      actorName: data.actorName,
    });
  }

  async function publicWatchOnce(companyId) {
    const cid = String(companyId || "").trim();
    if (!cid) return;
    const data = await fetchPublicActive(cid);
    if (!data) return;
    startPolling({
      companyId: cid,
      watchToken: data.watchToken,
      actorName: data.actorName,
    });
  }

  function startPublicSpectatorWatch(companyId) {
    const cid = String(companyId || "").trim();
    if (!cid) return;
    if (publicWatchCompanyId === cid && publicWatchTimer) return;
    stopPublicSpectatorWatch();
    publicWatchCompanyId = cid;
    publicWatchOnce(cid);
    publicWatchTimer = global.setInterval(() => publicWatchOnce(cid), 1800);
  }

  function stopPublicSpectatorWatch() {
    if (publicWatchTimer) {
      global.clearInterval(publicWatchTimer);
      publicWatchTimer = null;
    }
    publicWatchCompanyId = "";
  }

  let agentMoveTimer = null;
  let pendingMouse = null;

  function flushAgentMouse(state) {
    if (!pendingMouse || !state?.companyId || !state?.watchToken) return;
    const payload = pendingMouse;
    pendingMouse = null;
    const headers = { "Content-Type": "application/json", Accept: "application/json" };
    const token = global.localStorage?.getItem("baupass-control-token") || "";
    if (token) headers.Authorization = `Bearer ${token}`;
    fetch(`${apiBase()}/api/support-assist/pulse`, {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify({
        companyId: state.companyId,
        watchToken: state.watchToken,
        type: "mouse",
        payload,
      }),
    }).catch(() => {});
  }

  function startAgentBroadcast(state) {
    if (!state?.companyId || !state?.watchToken) return;
    isAgent = true;
    setSpectatorMode(false);
    writeWatchState({ companyId: state.companyId, watchToken: state.watchToken, actorName: state.actorName, agent: true });
    const onMove = (event) => {
      pendingMouse = {
        x: (event.clientX / Math.max(global.innerWidth, 1)) * 100,
        y: (event.clientY / Math.max(global.innerHeight, 1)) * 100,
        actorName: state.actorName,
      };
      if (!agentMoveTimer) {
        agentMoveTimer = global.setTimeout(() => {
          agentMoveTimer = null;
          flushAgentMouse(state);
        }, 120);
      }
    };
    global.document.addEventListener("mousemove", onMove, { passive: true });
    global.__baupassSupportAssistMoveHandler = onMove;
    global.BaupassSession?.startSupportAssistAgentUiCapture?.();
  }

  function stopAgentBroadcast(state) {
    isAgent = false;
    global.BaupassSession?.stopSupportAssistAgentUiCapture?.();
    if (global.__baupassSupportAssistMoveHandler) {
      global.document.removeEventListener("mousemove", global.__baupassSupportAssistMoveHandler);
      global.__baupassSupportAssistMoveHandler = null;
    }
    if (agentMoveTimer) {
      global.clearTimeout(agentMoveTimer);
      agentMoveTimer = null;
    }
    if (state?.companyId && state?.watchToken) {
      const headers = { "Content-Type": "application/json", Accept: "application/json" };
      const token = global.localStorage?.getItem("baupass-control-token") || "";
      if (token) headers.Authorization = `Bearer ${token}`;
      fetch(`${apiBase()}/api/support-assist/end`, {
        method: "POST",
        credentials: "include",
        headers,
        body: JSON.stringify({ companyId: state.companyId, watchToken: state.watchToken }),
      }).catch(() => {});
    }
    writeWatchState(null);
  }

  async function pulse(state, type, payload) {
    if (!state?.companyId || !state?.watchToken) return;
    const headers = { "Content-Type": "application/json", Accept: "application/json" };
    const token = global.localStorage?.getItem("baupass-control-token") || "";
    if (token) headers.Authorization = `Bearer ${token}`;
    await fetch(`${apiBase()}/api/support-assist/pulse`, {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify({
        companyId: state.companyId,
        watchToken: state.watchToken,
        type,
        payload: { ...(payload || {}), actorName: state.actorName },
      }),
    }).catch(() => {});
  }

  async function startAssistSession(companyId, actorName) {
    const headers = { "Content-Type": "application/json", Accept: "application/json" };
    const token = global.localStorage?.getItem("baupass-control-token") || "";
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(`${apiBase()}/api/support-assist/start`, {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify({ companyId, actorName }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data?.error || `http_${res.status}`);
    }
    const state = {
      companyId: data.companyId || companyId,
      watchToken: data.watchToken,
      actorName: data.actorName || actorName,
    };
    startAgentBroadcast(state);
    await pulse(state, "session_start", {});
    return state;
  }

  function resumeAgentFromUrl() {
    try {
      const url = new URL(global.location.href);
      const companyId = String(url.searchParams.get("supportCompanyId") || "").trim();
      const watchToken = String(url.searchParams.get("supportAssistWatchToken") || "").trim();
      const actorName = String(url.searchParams.get("supportActorName") || "Support").trim() || "Support";
      if (!companyId || !watchToken) return null;
      url.searchParams.delete("supportAssistWatchToken");
      global.history.replaceState({}, document.title, url.toString());
      return { companyId, watchToken, actorName, agent: true };
    } catch {
      return null;
    }
  }

  function resumeIfNeeded() {
    const urlState = resumeAgentFromUrl();
    if (urlState) {
      startAgentBroadcast(urlState);
      return;
    }
    const state = readWatchState();
    if (!state?.companyId || !state?.watchToken) return;
    if (state.agent) {
      startAgentBroadcast(state);
      return;
    }
    startPolling(state);
  }

  global.BaupassSupportAssist = {
    startAssistSession,
    startAgentBroadcast,
    stopAgentBroadcast,
    startPolling,
    stopPolling,
    startPublicSpectatorWatch,
    stopPublicSpectatorWatch,
    pulse,
    checkActiveForCompanyAdmin,
    fetchPublicActive,
    resumeIfNeeded,
    readWatchState,
    writeWatchState,
    setSpectatorMode,
    updateSpectatorBanner,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", resumeIfNeeded);
  } else {
    resumeIfNeeded();
  }
})(window);
