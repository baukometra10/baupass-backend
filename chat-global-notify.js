/**
 * SUPPIX chat global notify — sound + desktop alerts on non-chat admin pages and via SW push.
 */
(function initSuppixChatGlobalNotify(global) {
  let adminRealtimeStop = null;

  function wpGet(key) {
    const WP = global.WorkPassStorage;
    return WP ? WP.getItem(key) : global.localStorage.getItem(key);
  }

  function getAdminCredentials() {
    const TOKEN_KEY = global.WorkPassStorage?.KEYS?.ADMIN_TOKEN || "workpass-admin-token";
    const USER_KEY = global.WorkPassStorage?.KEYS?.ADMIN_USER || "workpass-admin-user";
    const COMPANY_KEY = global.WorkPassStorage?.KEYS?.ADMIN_COMPANY || "workpass-admin-company";
    const token = String(wpGet(TOKEN_KEY) || "").trim();
    let companyId = String(wpGet(COMPANY_KEY) || "").trim();
    if (!companyId) {
      try {
        const user = JSON.parse(wpGet(USER_KEY) || "{}");
        companyId = String(user.company_id || user.companyId || "").trim();
      } catch {
        companyId = "";
      }
    }
    return { token, companyId };
  }

  function isAdminChatPage() {
    const path = String(global.location?.pathname || "");
    return /\/admin-v2\/chat\.html$/i.test(path) || /\/chat\.html$/i.test(path);
  }

  function isWorkerChatSection() {
    const hash = String(global.location?.hash || "");
    return hash === "#chat" || hash.startsWith("#chat");
  }

  function notifyWorkerIncoming(data = {}) {
    const onChat = isWorkerChatSection();
    const focused = Boolean(global.document?.hasFocus?.());
    const dedupeKey = String(data.messageId || data.message_id || data.tag || "")
      ? `worker-push:${data.messageId || data.message_id || data.tag}:${String(data.body || data.preview || "").slice(0, 40)}`
      : "";
    if (dedupeKey && global.SUPPIXChatRealtime?.claimChatNotifyKey && !global.SUPPIXChatRealtime.claimChatNotifyKey(dedupeKey)) {
      return;
    }
    if (!(focused && onChat)) {
      global.SUPPIXChatRealtime?.playWorkerMessageSound?.();
    }
    if (focused && onChat) return;
    if (!global.Notification || Notification.permission !== "granted") return;
    try {
      new global.Notification(data.title || "Neue Nachricht vom Arbeitgeber", {
        body: data.body || data.preview || "",
        tag: data.tag || "worker-chat",
        icon: "/branding/suppix-icon-192.png",
      });
    } catch {
      /* ignore */
    }
  }

  async function handleAdminVoiceCallPush(data = {}) {
    const callId = String(data.callId || data.call_id || "").trim();
    if (callId && global.SUPPIXChatRealtime?.claimChatNotifyKey) {
      if (!global.SUPPIXChatRealtime.claimChatNotifyKey(`voice-call:${callId}`)) {
        return;
      }
    }
    const workerId = String(data.workerId || data.worker_id || "").trim();
    const workerName = String(data.workerName || data.title || "Mitarbeiter").trim() || "Mitarbeiter";
    const companyId = String(data.companyId || data.company_id || getAdminCredentials().companyId || "").trim();
    const call = {
      id: callId,
      callId,
      workerId,
      worker_id: workerId,
      callerName: workerName,
      companyId,
      status: "ringing",
    };
    // Prefer live incoming payload when possible.
    try {
      const { token } = getAdminCredentials();
      if (token) {
        const res = await fetch("/api/chat/calls/incoming", {
          headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
          credentials: "include",
        });
        const body = await res.json().catch(() => ({}));
        if (res.ok && body?.call) {
          global.SUPPIXAdminIncomingCall?.announceIncomingCall?.(body.call, {
            forceNotification: true,
            labels: { body: "Eingehender Anruf vom Mitarbeiter" },
          });
          return;
        }
      }
    } catch {
      /* fall through */
    }
    if (callId) {
      global.SUPPIXAdminIncomingCall?.announceIncomingCall?.(call, {
        forceNotification: true,
        labels: { body: "Eingehender Anruf vom Mitarbeiter" },
      });
    } else {
      global.SUPPIXChatRealtime?.playWorkerMessageSound?.();
    }
  }

  function handleSwPush(data = {}) {
    const tag = String(data.tag || data.logicalTag || "");
    const isAdminSurface = data.role === "admin"
      || /\/admin-v2\//i.test(String(global.location?.pathname || ""));
    if (tag === "voice-call") {
      if (isAdminSurface) {
        void handleAdminVoiceCallPush(data);
        return;
      }
      const callId = String(data.callId || data.call_id || "").trim();
      if (callId) {
        global.SUPPIXWorkerVoiceCall?.wakeForCallId?.(callId);
      } else {
        void global.SUPPIXWorkerVoiceCall?.pollIncomingOnce?.();
      }
      notifyWorkerIncoming({
        title: data.title || "Eingehender Anruf",
        body: data.body || data.preview || "Ihr Arbeitgeber ruft an",
        tag: "voice-call",
        messageId: callId || data.messageId,
      });
      return;
    }
    if (tag === "conference-invite") {
      if (!isAdminSurface) {
        void global.SUPPIXWorkerVoiceCall?.pollIncomingOnce?.();
        notifyWorkerIncoming({
          title: data.title || "Konferenz-Einladung",
          body: data.body || data.preview || "Tippen zum Beitreten",
          tag: "conference-invite",
          messageId: data.inviteId || data.messageId,
        });
      }
      return;
    }
    const isChatTag = tag === "admin-chat" || tag === "worker-chat" || tag.includes("chat");
    if (!isChatTag) return;

    if (data.role === "admin" || tag === "admin-chat") {
      if (global.SUPPIXChatRealtime?.notifyAdminWorkerMessage) {
        global.SUPPIXChatRealtime.notifyAdminWorkerMessage({
          type: "chat.message_created",
          id: data.eventId || data.id || "",
          payload: {
            senderType: "worker",
            workerId: data.workerId || data.worker_id || "",
            workerName: data.workerName || data.title || "",
            preview: data.body || data.preview || "",
            threadId: data.threadId || data.thread_id || "",
            messageId: data.messageId || data.message_id || "",
          },
        }, { workerMessageTitle: data.title || "Neue Mitarbeiter-Nachricht" });
      } else if (global.SUPPIXChatRealtime?.claimChatNotifyKey?.(
        `chat-msg:${data.messageId || data.message_id || data.threadId || "push"}`
      )) {
        global.SUPPIXChatRealtime?.playWorkerMessageSound?.();
      }
      return;
    }
    notifyWorkerIncoming(data);
  }

  function handleAdminRealtimeEvent(evt) {
    const type = String(evt?.type || "");
    // chat.message_created is already handled (sound) inside startAdminChatRealtime —
    // only voice-call events need extra handling here (avoid double beep / false alerts).
    if (!(type.startsWith("voice_call.") || type.startsWith("chat.voice_call"))) {
      return;
    }
    if (type.includes("incoming")) {
      void handleAdminVoiceCallPush({
        callId: evt?.payload?.callId || evt?.payload?.call_id,
        workerId: evt?.payload?.workerId || evt?.payload?.worker_id,
        companyId: evt?.payload?.companyId || evt?.payload?.company_id,
        workerName: evt?.payload?.workerName || evt?.payload?.callerName,
        tag: "voice-call",
      });
      return;
    }
    if (type.includes("ended") || type.includes("missed") || type.includes("declined")) {
      const callId = String(evt?.payload?.callId || evt?.payload?.call_id || "").trim();
      global.SUPPIXAdminIncomingCall?.dismissDesktopIncomingCall?.(callId);
    }
  }

  function startAdminGlobalRealtime() {
    if (adminRealtimeStop || isAdminChatPage()) return;
    const { token, companyId } = getAdminCredentials();
    if (!token || !companyId || !global.SUPPIXChatRealtime?.startAdminChatRealtime) return;
    global.SUPPIXChatRealtime.requestDesktopNotifyPermission?.();
    void global.SUPPIXChatRealtime.startAdminChatRealtime({
      companyId,
      getHeaders: () => (token ? { Authorization: `Bearer ${token}` } : {}),
      labels: { workerMessageTitle: "Neue Mitarbeiter-Nachricht" },
      onChatEvent: handleAdminRealtimeEvent,
    }).then((stop) => {
      adminRealtimeStop = typeof stop === "function" ? stop : null;
    });
  }

  function bindServiceWorkerMessages() {
    if (!("serviceWorker" in global.navigator) || global.__suppixChatSwBound) return;
    global.__suppixChatSwBound = true;
    global.navigator.serviceWorker.addEventListener("message", (event) => {
      if (event?.data?.type === "SUPPIX_CHAT_PUSH") {
        handleSwPush(event.data);
      }
    });
  }

  function init(options = {}) {
    bindServiceWorkerMessages();
    const role = String(options.role || "").trim();
    if (role === "admin" || /\/admin-v2\//i.test(String(global.location?.pathname || ""))) {
      startAdminGlobalRealtime();
      global.SUPPIXAdminVoiceCallGlobal?.init?.();
    }
  }

  global.SUPPIXChatGlobalNotify = {
    init,
    handleSwPush,
    startAdminGlobalRealtime,
    notifyWorkerIncoming,
    handleAdminVoiceCallPush,
  };
})(typeof window !== "undefined" ? window : globalThis);
