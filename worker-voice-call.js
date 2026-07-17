/**
 * Worker PWA voice call — incoming poll + full-screen overlay (uses chat-voice-call.js).
 */
(function initWorkerVoiceCall(global) {
  const POLL_MS = 2200;

  function t(key, fallback) {
    try {
      const v = typeof global.t === "function" ? global.t(key) : "";
      if (v && v !== key) return v;
    } catch (_) {
      /* ignore */
    }
    return fallback || key;
  }

  function formatDuration(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    const m = String(Math.floor(total / 60)).padStart(2, "0");
    const s = String(total % 60).padStart(2, "0");
    return `${m}:${s}`;
  }

  function ensureOverlay() {
    let overlay = document.getElementById("workerVoiceCallOverlay");
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.id = "workerVoiceCallOverlay";
    overlay.className = "worker-voice-call-overlay hidden";
    overlay.setAttribute("role", "dialog");
    overlay.innerHTML = `
      <div class="worker-voice-call-stage">
        <div class="worker-voice-call-badge">🔒 ${t("voiceCallSecure", "Sicherer Sprachkanal")}</div>
        <div class="worker-voice-call-avatar" id="workerVoiceCallAvatar">AG</div>
        <h4 id="workerVoiceCallTitle">${t("voiceCallTitle", "Sprachanruf")}</h4>
        <p id="workerVoiceCallStatus">${t("voiceCallRinging", "Eingehender Anruf…")}</p>
        <p id="workerVoiceCallTimer" class="worker-voice-call-timer hidden">00:00</p>
        <div id="workerVoiceCallLiveWave" class="worker-voice-call-live-wave"></div>
        <div class="worker-voice-call-meters">
          <div class="worker-voice-call-meter"><span>${t("voiceCallMicLabel", "Sie")}</span><div><i id="workerVoiceCallMicFill"></i></div></div>
          <div class="worker-voice-call-meter"><span>${t("voiceCallRemoteLabel", "Arbeitgeber")}</span><div><i id="workerVoiceCallRemoteFill"></i></div></div>
        </div>
        <div class="worker-voice-call-controls incoming-only">
          <button type="button" id="workerVoiceCallDeclineBtn" class="danger">${t("voiceCallDecline", "Ablehnen")}</button>
          <button type="button" id="workerVoiceCallAcceptBtn" class="primary">${t("voiceCallAccept", "Annehmen")}</button>
        </div>
        <div class="worker-voice-call-controls active-only hidden">
          <button type="button" id="workerVoiceCallMuteBtn">${t("voiceCallMute", "Stumm")}</button>
          <button type="button" id="workerVoiceCallSpeakerBtn">${t("voiceCallSpeaker", "Lautsprecher")}</button>
          <button type="button" id="workerVoiceCallHangupBtn" class="danger">${t("voiceCallHangup", "Auflegen")}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    if (!document.getElementById("workerVoiceCallStyles")) {
      const style = document.createElement("style");
      style.id = "workerVoiceCallStyles";
      style.textContent = `
.worker-voice-call-overlay{position:fixed;inset:0;z-index:14000;display:flex;flex-direction:column;justify-content:space-between;padding:0;background:radial-gradient(ellipse 120% 80% at 50% -10%,rgba(0,168,132,.22),transparent 55%),radial-gradient(ellipse 60% 40% at 100% 100%,rgba(37,99,235,.12),transparent 50%),linear-gradient(165deg,#071018 0%,#0b141a 45%,#0a1620 100%)}
.worker-voice-call-overlay.hidden{display:none}
.worker-voice-call-overlay.is-conference .worker-voice-call-avatar{width:120px;height:120px;font-size:2.2rem}
.worker-voice-call-stage{width:100%;max-width:520px;margin:0 auto;flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;color:#e9edef;padding:2rem 1.25rem 1rem}
.worker-voice-call-badge{display:inline-flex;padding:.35rem .75rem;border-radius:999px;border:1px solid rgba(0,168,132,.35);font-size:.75rem;margin-bottom:1rem;color:rgba(233,237,239,.85);background:rgba(0,168,132,.12)}
.worker-voice-call-avatar{width:180px;height:180px;margin:0 auto 1.25rem;border-radius:50%;display:grid;place-items:center;font-size:3rem;font-weight:800;background:linear-gradient(145deg,#00a884,#128c7e);color:#e9edef;box-shadow:0 24px 64px rgba(0,168,132,.28)}
.worker-voice-call-stage h4{margin:0 0 .35rem;font-size:2rem;color:#e9edef}
.worker-voice-call-stage p{color:rgba(233,237,239,.72);max-width:22rem;line-height:1.35}
.worker-voice-call-timer.hidden{display:none}
.worker-voice-call-live-wave{display:flex;align-items:flex-end;justify-content:center;gap:3px;height:72px;width:min(320px,88vw);margin:1rem auto}
.worker-voice-call-live-wave span{width:3px;border-radius:999px;height:18%;background:linear-gradient(180deg,#00a884,#128c7e);transition:height .08s linear}
.worker-voice-call-meters{width:min(300px,100%);margin:.5rem auto;display:grid;gap:.45rem;text-align:left}
.worker-voice-call-meter{display:grid;grid-template-columns:4.5rem 1fr;gap:.5rem;align-items:center;font-size:.72rem;text-transform:uppercase;opacity:.8}
.worker-voice-call-meter div{height:8px;border-radius:999px;background:rgba(255,255,255,.12);overflow:hidden}
.worker-voice-call-meter i{display:block;height:100%;width:0%;background:linear-gradient(90deg,#00a884,#128c7e)}
.worker-voice-call-controls{display:flex;gap:1.5rem;justify-content:center;flex-wrap:wrap;padding:1.25rem 1.25rem calc(1.35rem + env(safe-area-inset-bottom,0px));background:linear-gradient(180deg,transparent,rgba(0,0,0,.55))}
.worker-voice-call-controls.hidden{display:none}
.worker-voice-call-controls button{min-width:68px;min-height:68px;width:68px;height:68px;border-radius:50%;border:none;color:#fff;font-weight:600;cursor:pointer;font-size:1.5rem;box-shadow:0 8px 24px rgba(0,0,0,.35)}
.worker-voice-call-controls button.primary{background:#00a884}
.worker-voice-call-controls button.danger{background:#e53935}
.worker-voice-call-controls button.danger#workerVoiceCallHangupBtn{width:76px;height:76px;min-width:76px;min-height:76px}
.worker-voice-call-controls button.is-active{background:rgba(229,57,53,.85)}
#voiceCallVideoGrid{width:min(920px,94vw);margin:.75rem auto 0;display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:.65rem;max-height:36vh;overflow:auto}
.chat-call-log,.worker-chat-call-log{display:inline-flex;align-items:center;gap:.55rem;padding:.45rem .75rem;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(0,168,132,.22)}
.chat-call-log-btn,.worker-chat-call-log-btn{margin-top:.35rem;border-radius:999px;padding:.35rem .75rem;border:1px solid rgba(0,168,132,.35);background:rgba(0,168,132,.18);color:#ecfeff;font-size:.75rem;font-weight:600;cursor:pointer}`;
      document.head.appendChild(style);
    }
    overlay.querySelector("#workerVoiceCallDeclineBtn")?.addEventListener("click", () => controller?.decline());
    overlay.querySelector("#workerVoiceCallAcceptBtn")?.addEventListener("click", () => controller?.accept());
    overlay.querySelector("#workerVoiceCallHangupBtn")?.addEventListener("click", () => controller?.hangup());
    overlay.querySelector("#workerVoiceCallMuteBtn")?.addEventListener("click", () => controller?.toggleMute());
    overlay.querySelector("#workerVoiceCallSpeakerBtn")?.addEventListener("click", () => controller?.toggleSpeaker());
    const wave = overlay.querySelector("#workerVoiceCallLiveWave");
    if (wave && !wave.childElementCount) wave.innerHTML = Array.from({ length: 28 }, () => "<span></span>").join("");
    return overlay;
  }

  let controller = null;
  let pollTimer = null;
  let session = null;
  let timerInterval = null;
  let startedAt = 0;
  let apiFn = null;
  let dismissedCallId = "";

  function setOverlay(visible, statusText, mode) {
    const overlay = ensureOverlay();
    const status = overlay.querySelector("#workerVoiceCallStatus");
    const incoming = overlay.querySelector(".incoming-only");
    const active = overlay.querySelector(".active-only");
    if (status && statusText) status.textContent = statusText;
    overlay.classList.toggle("hidden", !visible);
    incoming?.classList.toggle("hidden", mode !== "incoming");
    active?.classList.toggle("hidden", mode !== "active");
    if (!visible) stopTimer();
  }

  function stopTimer() {
    if (timerInterval) global.clearInterval(timerInterval);
    timerInterval = null;
    startedAt = 0;
    document.getElementById("workerVoiceCallTimer")?.classList.add("hidden");
  }

  function startTimer() {
    stopTimer();
    startedAt = Date.now();
    const el = document.getElementById("workerVoiceCallTimer");
    el?.classList.remove("hidden");
    timerInterval = global.setInterval(() => {
      if (el && startedAt) el.textContent = formatDuration(Date.now() - startedAt);
    }, 1000);
  }

  function updateLevels(local, remote) {
    const mic = document.getElementById("workerVoiceCallMicFill");
    const remoteFill = document.getElementById("workerVoiceCallRemoteFill");
    if (mic) mic.style.width = `${Math.round((local || 0) * 100)}%`;
    if (remoteFill) remoteFill.style.width = `${Math.round((remote || 0) * 100)}%`;
    const wave = document.getElementById("workerVoiceCallLiveWave");
    if (!wave) return;
    const level = Math.max(Number(local || 0), Number(remote || 0));
    wave.querySelectorAll("span").forEach((bar, index) => {
      const phase = (Date.now() / 120 + index * 0.35) % (Math.PI * 2);
      const base = 0.2 + Math.sin(phase) * 0.14;
      bar.style.height = `${Math.max(14, Math.min(100, Math.round((base + level * 0.66) * 100)))}%`;
    });
  }

  function initials(name) {
    return String(name || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part.charAt(0).toUpperCase())
      .join("") || "AG";
  }

  function showIncoming(call) {
    const name = call.callerName || call.caller_name || call.companyName || call.company_name || t("senderCompany", "Arbeitgeber");
    document.getElementById("workerVoiceCallTitle").textContent = name;
    document.getElementById("workerVoiceCallAvatar").textContent = initials(name);
    setOverlay(true, t("voiceCallRinging", "Eingehender Anruf…"), "incoming");
  }

  controller = {
    async accept() {
      if (!session || !global.SUPPIXVoiceCall) return;
      setOverlay(true, t("voiceCallConnected", "Verbunden"), "active");
      try {
        await session.acceptIncoming(session._incomingCall);
        startTimer();
      } catch (_) {
        setOverlay(false);
        session = null;
      }
    },
    async decline() {
      if (!session) return;
      const callId = session.callId;
      try {
        await session.declineIncoming(callId);
      } catch (_) {
        /* ignore */
      }
      if (callId) dismissedCallId = callId;
      session = null;
      setOverlay(false);
    },
    async hangup() {
      if (!session) return;
      await session.end("hangup");
      session = null;
      setOverlay(false);
    },
    toggleMute() {
      if (!session) return;
      const muted = session.toggleMute();
      document.getElementById("workerVoiceCallMuteBtn")?.classList.toggle("is-active", muted);
    },
    toggleSpeaker() {
      if (!session) return;
      const on = session.toggleSpeaker();
      document.getElementById("workerVoiceCallSpeakerBtn")?.classList.toggle("is-active", !on);
    },
  };

  async function handleIncoming(call) {
    if (!call || !call.id || !global.SUPPIXVoiceCall?.isSupported?.()) return;
    if (session || String(call.id) === dismissedCallId) return;
    if (call.status && call.status !== "ringing") return;
    session = global.SUPPIXVoiceCall.createSession({
      api: apiFn,
      role: "worker",
      onAudioLevels: ({ local, remote }) => updateLevels(local, remote),
      onState: (state) => {
        if (state === "connected" || state === "accepted") {
          setOverlay(true, t("voiceCallConnected", "Verbunden"), "active");
          startTimer();
        } else if (state === "ended") {
          dismissedCallId = session?.callId || dismissedCallId;
          session = null;
          setOverlay(false);
          global.dispatchEvent(new CustomEvent("worker-voice-call-ended"));
        }
      },
      onError: () => {
        session = null;
        setOverlay(false);
      },
    });
    session._incomingCall = call;
    session.callId = String(call.id);
    showIncoming(call);
  }

  let conferenceActive = false;

  async function handleConferenceInvite(invite) {
    if (!invite?.id || conferenceActive) return;
    const overlay = ensureOverlay();
    const title = document.getElementById("workerVoiceCallTitle");
    const status = document.getElementById("workerVoiceCallStatus");
    if (title) title.textContent = invite.title || t("conferenceJoined", "Firmenkonferenz");
    if (status) status.textContent = t("voiceCallIncomingRinging", "Einladung zur Konferenz…");
    setOverlay(true, status?.textContent || "", "incoming");
    const accept = document.getElementById("workerVoiceCallAcceptBtn");
    const decline = document.getElementById("workerVoiceCallDeclineBtn");
    const onAccept = async () => {
      accept?.removeEventListener("click", onAccept);
      decline?.removeEventListener("click", onDecline);
      try {
        const data = await apiFn(`/api/worker-app/chat/conferences/${encodeURIComponent(invite.id)}/join`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        });
        conferenceActive = true;
        setOverlay(true, t("conferenceJoined", "In Konferenz"), "active");
        overlay.classList.add("is-conference");
        // Reuse admin video grid if present; else create minimal stage
        if (!document.getElementById("voiceCallVideoGrid")) {
          const stage = overlay.querySelector(".worker-voice-call-stage");
          const grid = document.createElement("div");
          grid.id = "voiceCallVideoGrid";
          grid.className = "voice-call-video-grid";
          stage?.insertBefore(grid, status);
        }
        document.getElementById("voiceCallOverlay")?.classList.add("is-conference");
        await global.SUPPIXConference?.connect?.({
          livekitUrl: data.livekitUrl,
          token: data.token,
          roomId: data.id,
          participants: data.participants || [],
          onDisconnect: async () => {
            conferenceActive = false;
            overlay.classList.remove("is-conference");
            setOverlay(false);
          },
        });
      } catch (error) {
        conferenceActive = false;
        overlay.classList.remove("is-conference");
        const raw = String(error?.message || error || "");
        const msg = /ServerUnreachable|websocket|Internal error/i.test(raw)
          ? t("conferenceNetworkUnreachable", "Konferenz-Server nicht erreichbar (VPN/Netz).")
          : raw;
        setOverlay(false);
        global.showWorkerNotice?.(msg);
      }
    };
    const onDecline = async () => {
      accept?.removeEventListener("click", onAccept);
      decline?.removeEventListener("click", onDecline);
      try {
        await apiFn(`/api/worker-app/chat/conferences/${encodeURIComponent(invite.id)}/leave`, { method: "POST" });
      } catch (_) { /* ignore */ }
      setOverlay(false);
    };
    accept?.addEventListener("click", onAccept, { once: true });
    decline?.addEventListener("click", onDecline, { once: true });
    document.getElementById("workerVoiceCallHangupBtn")?.addEventListener("click", async () => {
      if (!conferenceActive) return;
      try {
        await apiFn(`/api/worker-app/chat/conferences/${encodeURIComponent(invite.id)}/leave`, { method: "POST" });
      } catch (_) { /* ignore */ }
      await global.SUPPIXConference?.disconnect?.();
      conferenceActive = false;
      setOverlay(false);
    }, { once: true });
  }

  function startPolling() {
    stopPolling();
    if (!apiFn) return;
    const tick = async () => {
      if (session || conferenceActive) {
        pollTimer = global.setTimeout(tick, POLL_MS);
        return;
      }
      try {
        if (global.SUPPIXVoiceCall?.isSupported?.()) {
          const data = await apiFn("/api/worker-app/chat/calls/incoming");
          if (data?.call) await handleIncoming(data.call);
        }
        const conf = await apiFn("/api/worker-app/chat/conferences/incoming");
        if (conf?.conference) await handleConferenceInvite(conf.conference);
      } catch (_) {
        /* ignore */
      }
      pollTimer = global.setTimeout(tick, POLL_MS);
    };
    pollTimer = global.setTimeout(tick, 200);
  }

  async function pollIncomingOnce(api) {
    if (typeof api === "function") apiFn = api;
    if (!apiFn || session) return;
    try {
      const data = await apiFn("/api/worker-app/chat/calls/incoming");
      if (data?.call) await handleIncoming(data.call);
    } catch (_) {
      /* ignore */
    }
  }

  function stopPolling() {
    if (pollTimer) global.clearTimeout(pollTimer);
    pollTimer = null;
  }

  function wakeForCallId(callId) {
    const id = String(callId || "").trim();
    if (!id || !apiFn) return;
    void apiFn(`/api/worker-app/chat/calls/${encodeURIComponent(id)}`).then((data) => {
      if (data?.call) void handleIncoming(data.call);
    }).catch(() => {});
  }

  global.SUPPIXWorkerVoiceCall = {
    init(options = {}) {
      apiFn = options.api;
      dismissedCallId = "";
      ensureOverlay();
      if (options.enabled === false) {
        stopPolling();
        return;
      }
      startPolling();
    },
    stop: stopPolling,
    wakeForCallId,
    pollIncomingOnce,
    async startOutgoingCall(api) {
      if (typeof api !== "function" || !global.SUPPIXVoiceCall?.isSupported?.()) {
        return Promise.reject(new Error("voice_call_unsupported"));
      }
      if (session) {
        return Promise.reject(new Error("worker_busy"));
      }
      apiFn = api;
      session = global.SUPPIXVoiceCall.createSession({
        api,
        role: "worker",
        onAudioLevels: ({ local, remote }) => updateLevels(local, remote),
        onState: (state) => {
          if (state === "ringing" || state === "dialing") {
            setOverlay(true, t("voiceCallRinging", "Klingelt…"), "active");
          } else if (state === "connected" || state === "accepted") {
            setOverlay(true, t("voiceCallConnected", "Verbunden"), "active");
            startTimer();
          } else if (state === "ended") {
            session = null;
            setOverlay(false);
            global.dispatchEvent(new CustomEvent("worker-voice-call-ended"));
          }
        },
        onError: () => {
          session = null;
          setOverlay(false);
        },
      });
      const overlayEl = ensureOverlay();
      document.getElementById("workerVoiceCallTitle").textContent = t("senderCompany", "Arbeitgeber");
      document.getElementById("workerVoiceCallAvatar").textContent = "AG";
      setOverlay(true, t("voiceCallDialing", "Wählt…"), "active");
      overlayEl.querySelector(".incoming-only")?.classList.add("hidden");
      overlayEl.querySelector(".active-only")?.classList.remove("hidden");
      try {
        await session.startWorkerOutgoing();
      } catch (error) {
        session = null;
        setOverlay(false);
        throw error;
      }
    },
    requestCallback(api, callId) {
      if (typeof api !== "function") return Promise.reject(new Error("api_required"));
      return api("/api/worker-app/chat/calls/callback-request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(callId ? { call_id: callId } : {}),
      });
    },
    parseCallLogBody(body) {
      const text = String(body || "").trim();
      if (!text.startsWith("@voice-call|")) return null;
      const meta = {};
      text.slice("@voice-call|".length).split("|").forEach((part) => {
        const idx = part.indexOf("=");
        if (idx < 0) return;
        meta[part.slice(0, idx)] = part.slice(idx + 1);
      });
      return meta.status ? meta : null;
    },
    shouldShowCallLogToWorker(meta) {
      const audience = String(meta?.audience || "both").toLowerCase();
      if (audience === "admin") return false;
      return true;
    },
    renderCallLogHtml(meta, options = {}) {
      const status = String(meta?.status || "ended");
      const duration = Number(meta?.duration || 0);
      const map = {
        ended: t("voiceCallLogEnded", "Anruf beendet"),
        declined: t("voiceCallLogDeclined", "Abgelehnt"),
        missed: t("voiceCallLogMissed", "Verpasst"),
        cancelled: t("voiceCallLogCancelled", "Abgebrochen"),
        callback_requested: t("voiceCallLogCallbackRequested", "Rückruf angefordert"),
      };
      let summary = map[status] || map.ended;
      if (duration > 0) summary += ` · ${formatDuration(duration * 1000)}`;
      const callbackBtn = options.showCallback && ["missed", "declined", "ended", "cancelled"].includes(status)
        ? `<button type="button" class="worker-chat-call-log-btn" data-voice-callback="1" data-call-id="${String(meta.callId || "")}">${t("voiceCallRequestCallback", "Rückruf anfordern")}</button>`
        : "";
      return `<div class="worker-chat-call-log"><span aria-hidden="true">📞</span><span>${summary}</span>${callbackBtn}</div>`;
    },
  };
})(window);
