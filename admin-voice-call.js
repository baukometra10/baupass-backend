/**
 * SUPPIX admin voice-call poll — keeps incoming worker calls visible on any admin-v2 page.
 */
(function initAdminVoiceCallGlobal(global) {
  let pollTimer = null;
  let lastCallId = "";
  let dismissedId = "";

  function wpGet(key) {
    const WP = global.WorkPassStorage;
    return WP ? WP.getItem(key) : global.localStorage.getItem(key);
  }

  function getAdminAuth() {
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

  async function apiGet(path) {
    const { token, companyId } = getAdminAuth();
    if (!token) throw new Error("auth_missing");
    let url = path;
    if (companyId && !/[?&]company(_?[iI]d)=/i.test(path)) {
      url += (path.includes("?") ? "&" : "?") + "company_id=" + encodeURIComponent(companyId);
    }
    const headers = { Authorization: `Bearer ${token}`, Accept: "application/json" };
    if (companyId) headers["X-Company-Id"] = companyId;
    const res = await fetch(url, {
      headers,
      credentials: "include",
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || data.message || `HTTP ${res.status}`);
    return data;
  }

  async function tick() {
    if (isAdminChatPage()) return;
    const { token, companyId } = getAdminAuth();
    if (!token) return;
    // Superadmin without selected company: skip poll (backend would have nothing to scope).
    try {
      const userRaw = wpGet(global.WorkPassStorage?.KEYS?.ADMIN_USER || "workpass-admin-user");
      const user = JSON.parse(userRaw || "{}");
      if (String(user.role || "").toLowerCase() === "superadmin" && !companyId) return;
    } catch {
      /* continue */
    }
    try {
      const data = await apiGet("/api/chat/calls/incoming");
      const call = data?.call || null;
      if (!call?.id) {
        if (lastCallId) {
          global.SUPPIXAdminIncomingCall?.dismissDesktopIncomingCall?.(lastCallId);
          lastCallId = "";
        }
        return;
      }
      const callId = String(call.id);
      if (callId === dismissedId) return;
      if (String(call.status || "ringing") !== "ringing") {
        global.SUPPIXAdminIncomingCall?.dismissDesktopIncomingCall?.(callId);
        return;
      }
      if (callId === lastCallId) return;
      lastCallId = callId;
      global.SUPPIXAdminIncomingCall?.announceIncomingCall?.(call, { forceNotification: true });
    } catch (_) {
      /* ignore transient — do not rethrow (avoids unhandled rejection noise) */
    }
  }

  function start() {
    if (pollTimer) return;
    void tick();
    pollTimer = global.setInterval(() => { void tick(); }, 1200);
  }

  function stop() {
    if (pollTimer) global.clearInterval(pollTimer);
    pollTimer = null;
  }

  function bindDesktopActions() {
    // Chat page owns accept/decline via its own IPC listener — avoid double decline.
    if (isAdminChatPage()) return;
    if (!global.baupassDesktop?.onIncomingCallAction || global.__adminVoiceCallDesktopBound) return;
    global.__adminVoiceCallDesktopBound = true;
    global.baupassDesktop.onIncomingCallAction((payload) => {
      const action = String(payload?.action || "").toLowerCase();
      const callId = String(payload?.callId || "").trim();
      const path = String(payload?.path || "").trim();
      if (action === "decline" && callId) {
        dismissedId = callId;
        const { token } = getAdminAuth();
        if (token) {
          void fetch(`/api/chat/calls/${encodeURIComponent(callId)}/decline`, {
            method: "POST",
            headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
            credentials: "include",
            body: "{}",
          }).catch(() => {});
        }
        global.SUPPIXAdminIncomingCall?.dismissDesktopIncomingCall?.(callId);
        return;
      }
      if (path) {
        try {
          global.location.href = path;
        } catch (_) {
          try { global.location.href = path || "/admin-v2/chat.html"; } catch (__) { /* ignore */ }
        }
      }
    });
  }

  function init() {
    bindDesktopActions();
    if (!isAdminChatPage()) start();
  }

  global.SUPPIXAdminVoiceCallGlobal = { init, start, stop, tick };
})(typeof window !== "undefined" ? window : globalThis);
