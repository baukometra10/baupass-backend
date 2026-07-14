/**
 * Worker PWA voice call — incoming poll + full-screen overlay (uses chat-voice-call.js).
 */
(function initWorkerVoiceCall(global) {
  const POLL_MS = 2200;

  function t(key, fallback) {
    try {
      return global.t?.(key) || fallback || key;
    } catch (_) {
      return fallback || key;
    }
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
.worker-voice-call-overlay{position:fixed;inset:0;z-index:14000;display:grid;place-items:center;background:linear-gradient(180deg,#020617,#0b1220 45%,#000);padding:1rem}
.worker-voice-call-overlay.hidden{display:none}
.worker-voice-call-stage{width:min(420px,100%);text-align:center;color:#f8fafc}
.worker-voice-call-badge{display:inline-flex;padding:.35rem .75rem;border-radius:999px;border:1px solid rgba(94,234,212,.35);font-size:.75rem;margin-bottom:1rem}
.worker-voice-call-avatar{width:112px;height:112px;margin:0 auto 1rem;border-radius:50%;display:grid;place-items:center;font-size:2rem;font-weight:800;background:linear-gradient(145deg,#06b6d4,#0e7490);color:#ecfeff}
.worker-voice-call-timer.hidden{display:none}
.worker-voice-call-live-wave{display:flex;align-items:flex-end;justify-content:center;gap:3px;height:38px;margin:1rem auto}
.worker-voice-call-live-wave span{width:3px;border-radius:999px;height:18%;background:linear-gradient(180deg,#67e8f9,#14b8a6);transition:height .08s linear}
.worker-voice-call-meters{width:min(300px,100%);margin:.5rem auto;display:grid;gap:.45rem;text-align:left}
.worker-voice-call-meter{display:grid;grid-template-columns:4.5rem 1fr;gap:.5rem;align-items:center;font-size:.72rem;text-transform:uppercase;opacity:.8}
.worker-voice-call-meter div{height:8px;border-radius:999px;background:rgba(255,255,255,.12);overflow:hidden}
.worker-voice-call-meter i{display:block;height:100%;width:0%;background:linear-gradient(90deg,#22d3ee,#2dd4bf)}
.worker-voice-call-controls{display:flex;gap:.65rem;justify-content:center;flex-wrap:wrap;margin-top:1.1rem}
.worker-voice-call-controls.hidden{display:none}
.worker-voice-call-controls button{min-width:96px;border-radius:999px;padding:.65rem .9rem;border:1px solid rgba(255,255,255,.14);background:#1f2937;color:#fff;font-weight:600;cursor:pointer}
.worker-voice-call-controls button.primary{background:#059669;border-color:#34d399}
.worker-voice-call-controls button.danger{background:#b91c1c;border-color:#ef4444}
.worker-voice-call-controls button.is-active{background:rgba(127,29,29,.55)}
.chat-call-log,.worker-chat-call-log{display:inline-flex;align-items:center;gap:.55rem;padding:.45rem .75rem;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(94,234,212,.22)}
.chat-call-log-btn,.worker-chat-call-log-btn{margin-top:.35rem;border-radius:999px;padding:.35rem .75rem;border:1px solid rgba(94,234,212,.35);background:rgba(6,182,212,.18);color:#ecfeff;font-size:.75rem;font-weight:600;cursor:pointer}`;
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

  function startPolling() {
    stopPolling();
    if (!apiFn || !global.SUPPIXVoiceCall?.isSupported?.()) return;
    const tick = async () => {
      if (session) {
        pollTimer = global.setTimeout(tick, POLL_MS);
        return;
      }
      try {
        const data = await apiFn("/api/worker-app/chat/calls/incoming");
        if (data?.call) await handleIncoming(data.call);
      } catch (_) {
        /* ignore */
      }
      pollTimer = global.setTimeout(tick, POLL_MS);
    };
    pollTimer = global.setTimeout(tick, POLL_MS);
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
