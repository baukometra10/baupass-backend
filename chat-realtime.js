/**
 * SUPPIX chat realtime — platform events for admin + worker chat.
 */
(function initSuppixChatRealtime(global) {
  let notifyAudioCtx = null;

  function normalizeEvent(raw) {
    const evt = raw || {};
    let payload = evt.payload;
    if (typeof payload === "string") {
      try {
        payload = JSON.parse(payload);
      } catch {
        payload = {};
      }
    }
    return {
      id: String(evt.id || ""),
      type: String(evt.type || evt.event_type || ""),
      payload: payload && typeof payload === "object" ? payload : {},
      created_at: evt.created_at || evt.at || "",
    };
  }

  function isChatEvent(evt) {
    const type = String(evt?.type || "");
    return type === "chat.message_created" || type === "chat.typing" || type.startsWith("chat.voice_call") || type.startsWith("voice_call.");
  }

  function previewLabel(payload) {
    const preview = String(payload?.preview || "").trim();
    if (!preview || preview === "encrypted") return "Verschlüsselte Nachricht";
    if (preview === "voice") return "Sprachnachricht";
    if (preview === "photo") return "Foto";
    if (preview === "location") return "📍 Standort";
    return preview.slice(0, 120);
  }

  function isAdminChatPage() {
    const path = String(global.location?.pathname || "");
    return /\/admin-v2\/chat\.html$/i.test(path) || /\/chat\.html$/i.test(path);
  }

  function playWorkerMessageSound() {
    try {
      // Prefer soft chime asset when available; warmer multi-tone fallback otherwise.
      const audio = new global.Audio("/sounds/admin-message-chime.mp3");
      audio.volume = 0.72;
      const play = audio.play();
      if (play && typeof play.then === "function") {
        play.catch(() => playWorkerMessageSynth());
        return;
      }
    } catch {
      /* fall through */
    }
    playWorkerMessageSynth();
  }

  function playWorkerMessageSynth() {
    try {
      const Ctx = global.AudioContext || global.webkitAudioContext;
      if (!Ctx) return;
      if (!notifyAudioCtx) notifyAudioCtx = new Ctx();
      const ctx = notifyAudioCtx;
      if (ctx.state === "suspended") {
        void ctx.resume();
      }
      const now = ctx.currentTime;
      const master = ctx.createGain();
      master.gain.setValueAtTime(0.0001, now);
      master.gain.exponentialRampToValueAtTime(0.22, now + 0.02);
      master.gain.exponentialRampToValueAtTime(0.0001, now + 0.55);
      master.connect(ctx.destination);
      // Soft major triad: C6 → E6 → G6 (message pop, not ringtone).
      const notes = [1046.5, 1318.5, 1568.0];
      notes.forEach((hz, i) => {
        const osc = ctx.createOscillator();
        const g = ctx.createGain();
        osc.type = "triangle";
        osc.frequency.value = hz;
        const t = now + i * 0.07;
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(0.16, t + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.22);
        osc.connect(g);
        g.connect(master);
        osc.start(t);
        osc.stop(t + 0.24);
      });
    } catch {
      /* ignore */
    }
  }

  function requestDesktopNotifyPermission() {
    try {
      if (!global.Notification || Notification.permission !== "default") return;
      void Notification.requestPermission();
    } catch {
      /* ignore */
    }
  }

  function notifyAdminWorkerMessage(evt, labels = {}) {
    if (String(evt?.type || "") !== "chat.message_created") return;
    if (String(evt?.payload?.senderType || "") !== "worker") return;
    const workerId = String(evt?.payload?.workerId || "");
    const companyId = String(global.__adminChatCompanyId || "");
    if (workerId && companyId && global.SUPPIXChatThreadPrefs?.isMuted?.(companyId, workerId)) {
      return;
    }
    playWorkerMessageSound();
    const onChatPage = isAdminChatPage();
    const focused = Boolean(global.document?.hasFocus?.());
    if (focused && onChatPage) return;
    if (!global.Notification || Notification.permission !== "granted") return;
    const workerName = String(evt?.payload?.workerName || "").trim();
    const title = workerName
      ? `${labels.workerMessageTitle || "Neue Mitarbeiter-Nachricht"} — ${workerName}`
      : (labels.workerMessageTitle || "Neue Mitarbeiter-Nachricht");
    try {
      new global.Notification(title, {
        body: previewLabel(evt.payload),
        tag: `chat-${evt.payload?.threadId || workerId || "thread"}`,
        icon: "/branding/suppix-icon-192.png",
      });
    } catch {
      /* ignore */
    }
  }

  async function startAdminChatRealtime({ companyId, onChatEvent, onMode, labels, getHeaders } = {}) {
    if (global.__adminChatCompanyId !== companyId) {
      global.__adminChatCompanyId = companyId;
    }
    if (!global.SUPPIXOpsRealtime?.start) {
      return () => {};
    }
    let socketScript = null;
    if (typeof global.io !== "function") {
      await new Promise((resolve) => {
        socketScript = global.document.createElement("script");
        socketScript.src = "https://cdn.jsdelivr.net/npm/socket.io-client@4.7.5/dist/socket.io.min.js";
        socketScript.crossOrigin = "anonymous";
        socketScript.onload = resolve;
        socketScript.onerror = resolve;
        global.document.head.appendChild(socketScript);
      });
    }
    return global.SUPPIXOpsRealtime.start({
      companyId,
      feedEl: null,
      getHeaders,
      onMode,
      onEvent: (raw) => {
        const evt = normalizeEvent(raw);
        if (!isChatEvent(evt)) return;
        notifyAdminWorkerMessage(evt, labels);
        onChatEvent?.(evt);
      },
    });
  }

  function startWorkerChatRealtime({ headers, onChatEvent, pollMs = 2200 } = {}) {
    let stopped = false;
    let timer = null;
    let sinceId = "";
    const seen = new Set();

    const poll = async () => {
      if (stopped) return;
      let url = "/api/worker-app/chat/events/recent?limit=25";
      if (sinceId) url += `&since_id=${encodeURIComponent(sinceId)}`;
      try {
        const response = await fetch(url, {
          credentials: "include",
          headers: typeof headers === "function" ? headers() : headers || {},
        });
        if (!response.ok) {
          timer = global.setTimeout(poll, pollMs);
          return;
        }
        const data = await response.json();
        const events = Array.isArray(data?.events) ? data.events : [];
        events.forEach((raw) => {
          const evt = normalizeEvent(raw);
          if (!evt.id || seen.has(evt.id) || !isChatEvent(evt)) return;
          seen.add(evt.id);
          sinceId = evt.id;
          onChatEvent?.(evt);
        });
      } catch {
        /* ignore */
      }
      timer = global.setTimeout(poll, pollMs);
    };

    poll();
    return () => {
      stopped = true;
      if (timer) global.clearTimeout(timer);
    };
  }

  global.SUPPIXChatRealtime = {
    normalizeEvent,
    isChatEvent,
    previewLabel,
    requestDesktopNotifyPermission,
    notifyAdminWorkerMessage,
    playWorkerMessageSound,
    startAdminChatRealtime,
    startWorkerChatRealtime,
  };
})(typeof window !== "undefined" ? window : globalThis);
