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
})(window);
