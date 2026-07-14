/**
 * SUPPIX chat realtime — platform events for admin + worker chat.
 */
(function initSuppixChatRealtime(global) {
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
    return type === "chat.message_created" || type === "chat.typing" || type.startsWith("chat.voice_call");
  }

  function previewLabel(payload) {
    const preview = String(payload?.preview || "").trim();
    if (!preview || preview === "encrypted") return "Verschlüsselte Nachricht";
    if (preview === "voice") return "Sprachnachricht";
    if (preview === "photo") return "Foto";
    return preview.slice(0, 120);
  }

  function requestDesktopNotifyPermission() {
    try {
      if (!global.Notification || Notification.permission !== "default") return;
      void Notification.requestPermission();
    } catch {
      /* ignore */
    }
  }

  function maybeDesktopNotify(evt, labels = {}) {
    if (String(evt?.type || "") !== "chat.message_created") return;
    if (String(evt?.payload?.senderType || "") !== "worker") return;
    if (global.document?.hasFocus?.()) return;
    if (!global.Notification || Notification.permission !== "granted") return;
    const title = labels.workerMessageTitle || "Neue Mitarbeiter-Nachricht";
    try {
      new global.Notification(title, {
        body: previewLabel(evt.payload),
        tag: `chat-${evt.payload?.threadId || "thread"}`,
        icon: "/branding/suppix-icon-192.png",
      });
    } catch {
      /* ignore */
    }
  }

  async function startAdminChatRealtime({ companyId, onChatEvent, onMode, labels } = {}) {
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
      onMode,
      onEvent: (raw) => {
        const evt = normalizeEvent(raw);
        if (!isChatEvent(evt)) return;
        onChatEvent?.(evt);
        maybeDesktopNotify(evt, labels);
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
        /* retry */
      }
      if (!stopped) timer = global.setTimeout(poll, pollMs);
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
    maybeDesktopNotify,
    startAdminChatRealtime,
    startWorkerChatRealtime,
  };
})(typeof window !== "undefined" ? window : globalThis);
