/**
 * Same-origin iframe embed: add embed=1 to links and optional parent navigation (SUPPIX).
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

  const INDEX_HASH_VIEWS = {
    workers: "workers",
    access: "access",
    leave: "leave",
    admin: "admin",
    devices: "devices",
    invoices: "invoices",
    documents: "documents",
    badge: "badge",
    dashboard: "dashboard",
    "deployment-plan": "deployment-plan",
    einsatzplan: "deployment-plan",
  };

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
      if (p === "/" || p.endsWith("/index.html")) {
        const hash = (u.hash || "").replace(/^#/, "").trim();
        if (hash && INDEX_HASH_VIEWS[hash]) return INDEX_HASH_VIEWS[hash];
      }
    } catch {
      // no-op
    }
    return "";
  }

  function navigateFromEmbed(href, extraParams) {
    const url = withEmbed(href, extraParams);
    const view = viewFromHref(href);
    if (isEmbedMode() && global.parent && global.parent !== global && view) {
      let focusEinsatzplan = false;
      try {
        const u = new URL(href, global.location.origin);
        const p = u.pathname.toLowerCase();
        focusEinsatzplan =
          u.searchParams.get("einsatzplan") === "1" ||
          (p.includes("admin-v2") && u.searchParams.get("tab") === "workers") ||
          view === "deployment-plan";
      } catch {
        focusEinsatzplan = view === "deployment-plan";
      }
      global.parent.postMessage(
        { type: "baupass-navigate", view, url, focusEinsatzplan },
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

  function ensureEmbedFallback(shell, frame, title) {
    let fb = shell.querySelector(".embed-frame-fallback");
    if (fb) return fb;
    fb = document.createElement("div");
    fb.className = "embed-frame-fallback hidden";
    fb.setAttribute("role", "alert");
    fb.innerHTML = `
      <div class="embed-frame-fallback-card">
        <p class="embed-frame-fallback-eyebrow">SUPPIX</p>
        <h3 class="embed-frame-fallback-title">${title || "Modul"}</h3>
        <p class="embed-frame-fallback-msg" data-embed-fallback-msg>
          Verbindung zum Server fehlgeschlagen. Bitte prüfen Sie, ob die Anwendung auf Railway läuft, oder öffnen Sie das Modul im Vollbild.
        </p>
        <div class="embed-frame-fallback-actions">
          <button type="button" class="primary-button" data-embed-retry>Erneut laden</button>
          <a class="ghost-button" data-embed-open target="_blank" rel="noopener noreferrer">Im Vollbild öffnen</a>
        </div>
      </div>`;
    shell.appendChild(fb);
    return fb;
  }

  function bindEnterpriseIframe(frameId, options = {}) {
    const frame = global.document.getElementById(frameId);
    const shell = frame?.closest(".enterprise-embed-shell");
    if (!frame || !shell) return;
    if (frame.dataset.embedBound === "1") {
      const url = options.openUrl || frame.getAttribute("src") || "";
      if (url && frame.getAttribute("src") !== url) {
        frame.__baupassEmbedLoad?.(url);
      }
      return;
    }
    frame.dataset.embedBound = "1";

    const title = options.title || frame.getAttribute("title") || "Modul";
    const fallback = ensureEmbedFallback(shell, frame, title);
    const msgEl = fallback.querySelector("[data-embed-fallback-msg]");
    const openLink = fallback.querySelector("[data-embed-open]");
    const retryBtnFixed = fallback.querySelector("[data-embed-retry]");

    let pendingUrl = options.openUrl || frame.getAttribute("src") || "";

    const showFallback = (reason) => {
      frame.classList.add("is-hidden");
      fallback.classList.remove("hidden");
      if (msgEl) {
        if (reason === "timeout") {
          msgEl.textContent =
            "Das Modul antwortet nicht (Timeout). Railway-Deployment prüfen oder Vollbild öffnen.";
        } else {
          msgEl.textContent =
            "Die eingebettete Oberfläche konnte nicht geladen werden (Verbindung abgelehnt oder Server offline).";
        }
      }
      if (openLink && pendingUrl) openLink.href = pendingUrl;
    };

    const hideFallback = () => {
      fallback.classList.add("hidden");
      frame.classList.remove("is-hidden");
    };

    const probeLoaded = () => {
      try {
        const win = frame.contentWindow;
        if (!win) return false;
        const href = win.location?.href || "";
        if (!href || href === "about:blank") return false;
        const doc = win.document;
        if (!doc?.body) return false;
        const text = (doc.body.innerText || "").toLowerCase();
        if (text.includes("verbindung abgelehnt") || text.includes("refused to connect")) {
          return false;
        }
        return doc.body.childElementCount > 0;
      } catch {
        return true;
      }
    };

    const armLoadWatch = () => {
      hideFallback();
      let settled = false;
      const finish = (ok) => {
        if (settled) return;
        settled = true;
        global.clearTimeout(timer);
        if (ok) hideFallback();
        else showFallback("error");
      };
      const timer = global.setTimeout(() => finish(probeLoaded()), 10000);
      const onLoad = () => {
        global.setTimeout(() => finish(probeLoaded()), 400);
      };
      frame.addEventListener("load", onLoad, { once: true });
    };

    const loadUrl = (url) => {
      pendingUrl = url || pendingUrl;
      if (openLink && pendingUrl) openLink.href = pendingUrl;
      if (!pendingUrl) return;
      armLoadWatch();
      frame.setAttribute("src", pendingUrl);
    };

    retryBtnFixed?.addEventListener("click", () => loadUrl(pendingUrl));
    frame.__baupassEmbedLoad = loadUrl;
    if (pendingUrl) {
      if (frame.getAttribute("src") !== pendingUrl) {
        loadUrl(pendingUrl);
      } else {
        armLoadWatch();
      }
    }
  }

  global.BaupassEmbed = {
    isEmbedMode,
    withEmbed,
    viewFromHref,
    navigateFromEmbed,
    wireEmbedNav,
    bindEnterpriseIframe,
  };

  const TOKEN_KEYS = ["baupass-control-token", "baupass-admin-v2-token"];
  const COMPANY_STORAGE_KEYS = ["baupass-preview-company-id", "baupass-admin-v2-company"];

  function readStoredCompanyId() {
    for (const key of COMPANY_STORAGE_KEYS) {
      try {
        const val = (localStorage.getItem(key) || "").trim();
        if (val) return val;
      } catch {
        // ignore
      }
    }
    return "";
  }

  function resolveCompanyIdFromUser(user) {
    const qs = (new URLSearchParams(global.location.search).get("company_id") || "").trim();
    if (qs) return qs;
    const role = String(user?.role || "");
    if (role === "company-admin") {
      return String(user?.company_id || "").trim() || readStoredCompanyId();
    }
    if (role === "superadmin") {
      return String(user?.preview_company_id || "").trim() || readStoredCompanyId();
    }
    return String(user?.company_id || "").trim() || readStoredCompanyId();
  }

  function persistCompanyId(companyId) {
    const cid = String(companyId || "").trim();
    if (!cid) return;
    try {
      localStorage.setItem("baupass-preview-company-id", cid);
    } catch {
      // ignore
    }
  }

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

  function readCsrfToken() {
    try {
      const match = global.document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
      return match ? decodeURIComponent(match[1]) : "";
    } catch {
      return "";
    }
  }

  function authHeaders(extra = {}) {
    const headers = { ...(extra || {}) };
    const token = getSessionToken();
    if (token && !headers.Authorization) {
      headers.Authorization = `Bearer ${token}`;
    }
    const csrf = readCsrfToken();
    if (csrf && !headers["X-CSRF-Token"]) {
      headers["X-CSRF-Token"] = csrf;
    }
    return headers;
  }

  async function fetchApi(path, opts = {}) {
    const method = String(opts.method || "GET").toUpperCase();
    const headers = authHeaders(opts.headers || {});
    if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    let body = opts.body;
    if (!["GET", "HEAD", "OPTIONS"].includes(method) && body === undefined) {
      body = {};
    }
    const res = await fetch(path, {
      credentials: "include",
      ...opts,
      method,
      headers,
      body:
        body === undefined
          ? undefined
          : typeof body === "string"
            ? body
            : JSON.stringify(body),
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

  function applyTenantBranding(branding) {
    if (!branding || typeof branding !== "object") return;
    const preset = String(branding.preset || branding.brandingPreset || "construction").trim().toLowerCase();
    if (["construction", "industry", "premium"].includes(preset)) {
      document.body.setAttribute("data-branding-preset", preset);
    }
    const accent = String(
      branding.accent || branding.brandingAccentColor || branding.accentColor || "",
    ).trim();
    const primary = String(branding.primaryColor || accent || "").trim();
    if (/^#[0-9a-f]{6}$/i.test(accent)) {
      document.documentElement.style.setProperty("--accent", accent);
      document.documentElement.style.setProperty("--company-accent", accent);
    }
    if (/^#[0-9a-f]{6}$/i.test(primary)) {
      document.documentElement.style.setProperty("--brand-primary", primary);
      document.documentElement.style.setProperty("--teal", primary);
      document.documentElement.style.setProperty("--teal-soft", primary);
      document.documentElement.style.setProperty("--foreman-primary", primary);
    }
    const displayName = String(
      branding.portalDisplayName || branding.companyName || branding.platformName || branding.portal_display_name || "",
    ).trim();
    if (displayName) {
      document.body.setAttribute("data-portal-display-name", displayName);
    }
    const logoData = String(branding.logoData || branding.brandingLogoData || "").trim();
    const chipFallback = "/branding/suppix-ai-mark.svg";
    const resolvedLogo = logoData || "/branding/suppix-ai-logo.svg";
    const resolvedSidebarLogo = logoData
      ? (logoData.includes("suppix-ai-logo") && !logoData.includes("-dark") && !logoData.startsWith("data:")
        ? "/branding/suppix-ai-logo-dark.svg"
        : logoData)
      : "/branding/suppix-ai-logo-dark.svg";
    applyTenantFavicon({ logoData: resolvedLogo, title: displayName });
    document.querySelectorAll("[data-tenant-logo]").forEach((img) => {
      const useChip = img.classList.contains("tenant-logo-chip")
        || img.classList.contains("foreman-header-logo")
        || img.classList.contains("tenant-logo-img");
      const fallback = useChip ? chipFallback : resolvedSidebarLogo;
      const nextSrc = logoData ? logoData : fallback;
      img.src = nextSrc;
      img.classList.remove("hidden");
      img.onerror = function onTenantLogoError() {
        this.onerror = null;
        if (this.src !== fallback) this.src = fallback;
        this.classList.remove("hidden");
      };
    });
    document.querySelectorAll(".website-logo-auth, .website-logo-sync.website-logo-auth").forEach((img) => {
      img.src = resolvedLogo;
      img.classList.remove("hidden");
    });
    document.querySelectorAll("[data-tenant-brand-title]").forEach((el) => {
      if (displayName) el.textContent = displayName;
    });
    if (displayName) {
      document.querySelectorAll("#loginPlatformName, [data-tenant-login-platform]").forEach((el) => {
        el.textContent = displayName;
        el.setAttribute("data-tenant-branded", "1");
      });
      document.querySelectorAll(".website-logo-sync.website-logo-sidebar").forEach((img) => {
        img.src = resolvedSidebarLogo;
        img.classList.remove("hidden");
      });
      if (branding.tenantMatched || branding.companyId) {
        document.body.classList.add("tenant-white-label");
        document.title = displayName;
        const metaAppTitle = document.querySelector('meta[name="apple-mobile-web-app-title"]');
        if (metaAppTitle) metaAppTitle.setAttribute("content", displayName);
      } else if (displayName) {
        document.title = displayName;
      }
    }
    const foremanHeader = document.querySelector(".foreman-header");
    if (foremanHeader && /^#[0-9a-f]{6}$/i.test(primary || accent)) {
      const c1 = primary || accent;
      const c2 = accent || primary;
      foremanHeader.style.background = `linear-gradient(135deg, ${c1}, ${c2})`;
    }
    const opsTitle = document.getElementById("opsTitle");
    if (opsTitle && displayName && (branding.tenantMatched || branding.companyId)) {
      opsTitle.textContent = displayName;
    }
    const mapTitle = document.getElementById("opsMapTitle");
    if (mapTitle && displayName && (branding.tenantMatched || branding.companyId)) {
      mapTitle.textContent = displayName;
    }
  }

  function ensureBrandingLink(selector, relValue) {
    let link = document.querySelector(selector);
    if (!link) {
      link = document.createElement("link");
      link.rel = relValue;
      document.head.appendChild(link);
    }
    return link;
  }

  function applyTenantFavicon({ logoData, title } = {}) {
    const iconHref = String(logoData || "").trim() || new URL("/branding/suppix-icon-192.png", global.location.origin).href;
    const appFavicon = ensureBrandingLink("#appFavicon", "icon");
    appFavicon.id = "appFavicon";
    appFavicon.type = "image/png";
    appFavicon.sizes = "192x192";
    appFavicon.href = iconHref;

    document.querySelectorAll('link[rel="icon"], link[rel="shortcut icon"]').forEach((link) => {
      link.href = iconHref;
    });
    document.querySelectorAll('link[rel="apple-touch-icon"]').forEach((link) => {
      link.href = iconHref;
    });

    if (title) {
      const metaAppTitle = document.querySelector('meta[name="apple-mobile-web-app-title"]');
      if (metaAppTitle) metaAppTitle.setAttribute("content", title);
      const metaAppName = document.querySelector('meta[name="application-name"]');
      if (metaAppName) metaAppName.setAttribute("content", title);
    }
  }

  async function loadPublicTenantBranding(opts = {}) {
    const host = String(opts.host || global.location.hostname || "").trim();
    const companyId = String(
      opts.companyId || readStoredCompanyId() || new URLSearchParams(global.location.search).get("company_id") || "",
    ).trim();
    let query = `?host=${encodeURIComponent(host)}`;
    if (companyId) query += `&company_id=${encodeURIComponent(companyId)}`;
    try {
      const res = await fetch(`/api/public/tenant-branding${query}`, { credentials: "include" });
      if (!res.ok) return null;
      const data = await res.json();
      applyTenantBranding(data);
      return data;
    } catch {
      return null;
    }
  }

  async function resolveTenantBranding(opts = {}) {
    const companyId = String(
      opts.companyId || readStoredCompanyId() || new URLSearchParams(global.location.search).get("company_id") || "",
    ).trim();
    if (getSessionToken()) {
      try {
        const authBranding = await loadTenantBranding(companyId || undefined);
        if (authBranding) return authBranding;
      } catch {
        // fall through to public tenant branding
      }
    }
    return loadPublicTenantBranding({ host: opts.host, companyId });
  }

  async function loadTenantBranding(companyId) {
    const cid = String(companyId || readStoredCompanyId() || "").trim();
    const q = cid ? `?company_id=${encodeURIComponent(cid)}` : "";
    try {
      const branding = await fetchApi(`/api/companies/current/branding${q}`);
      applyTenantBranding(branding);
      return branding;
    } catch {
      return null;
    }
  }

  function clearEmbeddedSession() {
    try {
      global.localStorage.removeItem("baupass-control-token");
      global.localStorage.removeItem("baupass-admin-v2-token");
      global.localStorage.removeItem("baupass-admin-v2-user");
    } catch {
      // ignore
    }
    global.dispatchEvent(new CustomEvent("baupass-session-cleared"));
  }

  window.addEventListener("message", (event) => {
    if (!event?.data || event.origin !== global.location.origin) return;
    if (event.data.type === "baupass-clear-session") {
      clearEmbeddedSession();
      return;
    }
    if (event.data.type === "baupass-sync-token") {
      if (event.data.token) {
        persistSessionToken(event.data.token);
      }
      const cid = String(event.data.companyId || "").trim();
      if (cid) {
        persistCompanyId(cid);
        global.dispatchEvent(new CustomEvent("baupass-company-sync", { detail: { companyId: cid } }));
      }
      const lang = String(event.data.lang || "").trim().slice(0, 2);
      if (lang) {
        try {
          global.localStorage.setItem("baupass-ui-lang", lang);
        } catch {
          // ignore
        }
        global.dispatchEvent(new CustomEvent("baupass-lang-sync", { detail: { lang } }));
      }
    }
    if (event.data.type === "baupass-sync-lang") {
      const lang = String(event.data.lang || "").trim().slice(0, 2);
      if (!lang) return;
      try {
        global.localStorage.setItem("baupass-ui-lang", lang);
      } catch {
        // ignore
      }
      global.dispatchEvent(new CustomEvent("baupass-lang-sync", { detail: { lang } }));
    }
  });

  global.BaupassAuth = {
    getSessionToken,
    persistSessionToken,
    authHeaders,
    fetchApi,
    bootstrapSession,
    applyTenantBranding,
    applyTenantFavicon,
    loadTenantBranding,
    loadPublicTenantBranding,
    resolveTenantBranding,
    readStoredCompanyId,
    resolveCompanyIdFromUser,
    persistCompanyId,
  };
})(window);
