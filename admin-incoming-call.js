/**
 * SUPPIX admin incoming call helpers — Desktop always-on-top + browser Notification.
 */
(function initAdminIncomingCallNotify(global) {
  let activeCallId = "";
  let activeNotification = null;

  function callPayloadFrom(call = {}) {
    return {
      callId: String(call.id || call.callId || call.call_id || "").trim(),
      workerName: String(
        call.callerName || call.caller_name || call.workerName || call.worker_name || "Mitarbeiter"
      ).trim() || "Mitarbeiter",
      workerId: String(call.workerId || call.worker_id || "").trim(),
      companyId: String(call.companyId || call.company_id || "").trim(),
    };
  }

  function showDesktopIncomingCall(call) {
    const payload = callPayloadFrom(call);
    if (!payload.callId || !global.baupassDesktop?.showIncomingCall) return false;
    activeCallId = payload.callId;
    try {
      void global.baupassDesktop.showIncomingCall(payload);
      return true;
    } catch (_) {
      return false;
    }
  }

  function dismissDesktopIncomingCall(callId) {
    const id = String(callId || activeCallId || "").trim();
    if (id && activeCallId && id !== activeCallId) return;
    activeCallId = "";
    try {
      void global.baupassDesktop?.dismissIncomingCall?.();
    } catch (_) {
      /* ignore */
    }
    try {
      activeNotification?.close?.();
    } catch (_) {
      /* ignore */
    }
    activeNotification = null;
  }

  function showBrowserIncomingNotification(call, labels = {}) {
    const payload = callPayloadFrom(call);
    if (!payload.callId) return false;
    if (!global.Notification || Notification.permission !== "granted") return false;
    if (global.document?.hasFocus?.()) return false;
    try {
      activeNotification?.close?.();
    } catch (_) {
      /* ignore */
    }
    try {
      const title = payload.workerName;
      const body = labels.body
        || (typeof global.adminChatT === "function" && global.adminChatT("voiceCallIncomingFromWorker"))
        || "Eingehender Anruf vom Mitarbeiter";
      const n = new global.Notification(title, {
        body,
        tag: `voice-call-${payload.callId}`,
        requireInteraction: true,
        renotify: true,
        icon: "/branding/suppix-icon-192.png",
      });
      n.onclick = () => {
        try { global.focus?.(); } catch (_) { /* ignore */ }
        try { n.close(); } catch (_) { /* ignore */ }
        const params = new URLSearchParams();
        if (payload.companyId) params.set("company_id", payload.companyId);
        if (payload.workerId) params.set("worker_id", payload.workerId);
        params.set("call_id", payload.callId);
        const url = `/admin-v2/chat.html?${params.toString()}`;
        try {
          if (String(global.location?.pathname || "").includes("/admin-v2/chat.html")) {
            global.dispatchEvent(new CustomEvent("suppix:admin-incoming-call", { detail: payload }));
          } else {
            global.location.href = url;
          }
        } catch (_) {
          try { global.location.href = url; } catch (__) { /* ignore */ }
        }
      };
      activeNotification = n;
      return true;
    } catch (_) {
      return false;
    }
  }

  function announceIncomingCall(call, options = {}) {
    const payload = callPayloadFrom(call);
    if (!payload.callId) return { desktop: false, notification: false };
    const desktop = showDesktopIncomingCall(payload);
    const notification = options.forceNotification || !global.document?.hasFocus?.()
      ? showBrowserIncomingNotification(payload, options.labels || {})
      : false;
    return { desktop, notification, callId: payload.callId };
  }

  global.SUPPIXAdminIncomingCall = {
    announceIncomingCall,
    showDesktopIncomingCall,
    dismissDesktopIncomingCall,
    showBrowserIncomingNotification,
    callPayloadFrom,
  };
})(typeof window !== "undefined" ? window : globalThis);
