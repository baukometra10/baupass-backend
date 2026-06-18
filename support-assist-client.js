(function initBaupassSupportAssist(global) {
  const STORAGE_KEY = "baupass-support-assist-watch";
  let pollTimer = null;
  let publicWatchTimer = null;
  let publicWatchCompanyId = "";
  let lastSeq = 0;
  let overlayEl = null;
  let cursorEl = null;
  let statusEl = null;
  let isSpectator = false;
  let isAgent = false;

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

  function ensureOverlay() {
    if (overlayEl) return overlayEl;
    overlayEl = document.createElement("div");
    overlayEl.id = "supportAssistSpectatorOverlay";
    overlayEl.className = "support-assist-spectator hidden";
    overlayEl.innerHTML = `
      <div class="support-assist-spectator-card">
        <p class="support-assist-kicker">Live-Support</p>
        <h2 id="supportAssistSpectatorTitle">Support ist aktiv</h2>
        <p id="supportAssistSpectatorStatus" class="support-assist-status">Bitte zuschauen — Eingaben sind gesperrt.</p>
      </div>
    `;
    statusEl = overlayEl.querySelector("#supportAssistSpectatorStatus");
    document.body.appendChild(overlayEl);

    cursorEl = document.createElement("div");
    cursorEl.id = "supportAssistRemoteCursor";
    cursorEl.className = "support-assist-remote-cursor hidden";
    cursorEl.innerHTML = `<span class="support-assist-remote-cursor-label">Support</span>`;
    document.body.appendChild(cursorEl);

    document.addEventListener("mousemove", blockSpectatorInput, true);
    document.addEventListener("mousedown", blockSpectatorInput, true);
    document.addEventListener("keydown", blockSpectatorInput, true);
    document.addEventListener("touchstart", blockSpectatorInput, true);
    document.addEventListener("click", blockSpectatorInput, true);
    return overlayEl;
  }

  function blockSpectatorInput(event) {
    if (!isSpectator) return;
    const target = event.target;
    if (target && target.closest && target.closest("#supportAssistSpectatorOverlay")) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    return false;
  }

  function setSpectatorMode(active, actorName, message) {
    isSpectator = Boolean(active);
    const overlay = ensureOverlay();
    overlay.classList.toggle("hidden", !active);
    document.body.classList.toggle("support-assist-spectator-active", active);
    const title = overlay.querySelector("#supportAssistSpectatorTitle");
    if (title) {
      title.textContent = actorName ? `${actorName} übernimmt` : "Support ist aktiv";
    }
    if (statusEl && message) {
      statusEl.textContent = message;
    }
    if (!active && cursorEl) {
      cursorEl.classList.add("hidden");
    }
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
        return `${actor} startet eine Support-Sitzung.`;
      case "force_logout":
        return payload?.message || "Sie wurden abgemeldet — Support übernimmt.";
      case "logout":
        return `${actor} meldet sich ab…`;
      case "login_screen":
        return `${actor} ist auf dem Anmeldebildschirm.`;
      case "logging_in":
        return `${actor} meldet sich an…`;
      case "logged_in":
        return `${actor} ist angemeldet.`;
      case "view":
        return `${actor} öffnet: ${payload?.view || "Ansicht"}`;
      case "session_end":
        return "Support-Sitzung beendet.";
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
      if (type === "force_logout") {
        setSpectatorMode(true, actorName, messageForEvent(type, payload, actorName));
        if (global.clearSession) {
          try { global.clearSession(); } catch { /* ignore */ }
        }
        if (global.refreshAll) {
          try { global.refreshAll(); } catch { /* ignore */ }
        }
        return;
      }
      if (type === "session_end") {
        setSpectatorMode(false);
        writeWatchState(null);
        stopPolling();
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
    ensureOverlay();
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
  }

  function stopAgentBroadcast(state) {
    isAgent = false;
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
    await pulse(state, "logout", { message: "Support meldet sich ab…" });
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
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", resumeIfNeeded);
  } else {
    resumeIfNeeded();
  }
})(window);
