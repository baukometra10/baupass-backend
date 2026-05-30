/**
 * Same-origin iframe embed: add embed=1 to links and optional parent navigation (Control Pass).
 */
(function initBaupassEmbedHelpers(global) {
  function isEmbedMode() {
    try {
      if (new URLSearchParams(global.location.search).get("embed") === "1") return true;
      return global.self !== global.top;
    } catch {
      return false;
    }
  }

  function withEmbed(href, extraParams) {
    if (!href || href.startsWith("mailto:") || href.startsWith("tel:")) return href;
    try {
      const u = new URL(href, global.location.origin);
      if (isEmbedMode()) {
        u.searchParams.set("embed", "1");
      }
      const params = extraParams || {};
      Object.keys(params).forEach((key) => {
        const val = params[key];
        if (val != null && String(val).trim() !== "") {
          u.searchParams.set(key, String(val).trim());
        }
      });
      return u.pathname + u.search + u.hash;
    } catch {
      return href;
    }
  }

  function viewFromHref(href) {
    try {
      const u = new URL(href, global.location.origin);
      const p = u.pathname.toLowerCase();
      if (p.includes("ai-command-center")) return "ai-assistant";
      if (p.includes("ops-command-center") || p.includes("ops-live-map")) return "ops-center";
      if (p.includes("enterprise-hub") || p === "/enterprise") return "enterprise-hub";
      if (p.includes("admin-v2")) return "admin-v2";
      const view = u.searchParams.get("view");
      if (view) return view;
    } catch {
      // no-op
    }
    return "";
  }

  function navigateFromEmbed(href, extraParams) {
    const url = withEmbed(href, extraParams);
    const view = viewFromHref(href);
    if (isEmbedMode() && global.parent && global.parent !== global && view) {
      global.parent.postMessage(
        { type: "baupass-navigate", view, url },
        global.location.origin,
      );
      return;
    }
    global.location.href = url;
  }

  function wireEmbedNav(selector, extraParams) {
    global.document.querySelectorAll(selector).forEach((el) => {
      const href = el.getAttribute("href");
      if (!href || href.startsWith("http") || href.startsWith("mailto:") || href.startsWith("tel:")) {
        return;
      }
      const next = withEmbed(href, extraParams);
      el.setAttribute("href", next);
      if (isEmbedMode()) {
        el.removeAttribute("target");
        el.addEventListener("click", (ev) => {
          const v = viewFromHref(href);
          if (!v) return;
          ev.preventDefault();
          navigateFromEmbed(href, extraParams);
        });
      }
    });
  }

  global.BaupassEmbed = {
    isEmbedMode,
    withEmbed,
    viewFromHref,
    navigateFromEmbed,
    wireEmbedNav,
  };

  const TOKEN_KEYS = ["baupass-control-token", "baupass-admin-v2-token"];

  function getSessionToken() {
    for (const key of TOKEN_KEYS) {
      const val = (localStorage.getItem(key) || "").trim();
      if (val) return val;
    }
    return "";
  }

  function persistSessionToken(token) {
    const val = String(token || "").trim();
    if (!val) return;
    TOKEN_KEYS.forEach((key) => {
      try {
        localStorage.setItem(key, val);
      } catch {
        // ignore
      }
    });
  }

  function authHeaders(extra = {}) {
    const headers = { ...(extra || {}) };
    const token = getSessionToken();
    if (token && !headers.Authorization) {
      headers.Authorization = `Bearer ${token}`;
    }
    return headers;
  }

  async function fetchApi(path, opts = {}) {
    const res = await fetch(path, {
      credentials: "include",
      ...opts,
      headers: authHeaders(opts.headers || {}),
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) {
      const err = new Error("auth");
      err.status = 401;
      err.payload = data;
      throw err;
    }
    if (!res.ok) {
      const err = new Error(data.hint || data.error || res.statusText);
      err.payload = data;
      err.status = res.status;
      throw err;
    }
    return data;
  }

  async function bootstrapSession() {
    const data = await fetchApi("/api/session/bootstrap");
    if (
      data?.authenticated === false ||
      !data?.user?.role ||
      ["unauthorized", "invalid_session", "session_expired"].includes(String(data?.error || ""))
    ) {
      const err = new Error("auth");
      err.payload = data;
      throw err;
    }
    if (data.token) {
      persistSessionToken(data.token);
    }
    return data;
  }

  window.addEventListener("message", (event) => {
    if (!event?.data || event.origin !== global.location.origin) return;
    if (event.data.type === "baupass-sync-token" && event.data.token) {
      persistSessionToken(event.data.token);
    }
  });

  global.BaupassAuth = {
    getSessionToken,
    persistSessionToken,
    authHeaders,
    fetchApi,
    bootstrapSession,
  };
})(window);
