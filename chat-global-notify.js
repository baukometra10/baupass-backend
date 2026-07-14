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
    global.SUPPIXChatRealtime?.playWorkerMessageSound?.();
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

  function handleSwPush(data = {}) {
    const tag = String(data.tag || data.logicalTag || "");
    const isChatTag = tag === "admin-chat" || tag === "worker-chat" || tag === "voice-call" || tag.includes("chat");
    if (!isChatTag) return;

    if (data.role === "admin" || tag === "admin-chat" || tag === "voice-call") {
      if (global.SUPPIXChatRealtime?.notifyAdminWorkerMessage) {
        global.SUPPIXChatRealtime.notifyAdminWorkerMessage({
          type: "chat.message_created",
          payload: {
            senderType: "worker",
            workerId: data.workerId || data.worker_id || "",
            workerName: data.workerName || data.title || "",
            preview: data.body || data.preview || "",
            threadId: data.threadId || data.thread_id || "",
          },
        }, { workerMessageTitle: data.title || "Neue Mitarbeiter-Nachricht" });
      } else {
        global.SUPPIXChatRealtime?.playWorkerMessageSound?.();
      }
      return;
    }
    notifyWorkerIncoming(data);
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
    }
  }

  global.SUPPIXChatGlobalNotify = {
    init,
    handleSwPush,
    startAdminGlobalRealtime,
    notifyWorkerIncoming,
  };
})(typeof window !== "undefined" ? window : globalThis);
