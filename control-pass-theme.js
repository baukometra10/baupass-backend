/**
 * Control Pass window theme (light / dark) — shared across app.js, admin-v2, embeds.
 */
(function initControlPassTheme(global) {
  const STORAGE_KEY = "baupass-system-theme";
  const WHITE = "white";
  const BLACK = "black";

  function normalizeMode(value) {
    if (value === BLACK) return BLACK;
    if (value === "system") {
      try {
        return global.matchMedia("(prefers-color-scheme: dark)").matches ? BLACK : WHITE;
      } catch {
        return WHITE;
      }
    }
    return WHITE;
  }

  function getStoredMode() {
    try {
      return normalizeMode(global.localStorage.getItem(STORAGE_KEY));
    } catch {
      return WHITE;
    }
  }

  function applyAdminPalette(effective) {
    const root = document.documentElement;
    if (effective === BLACK) {
      root.style.setProperty("--bg", "#050816");
      root.style.setProperty("--panel", "rgba(10, 16, 30, 0.92)");
      root.style.setProperty("--panel-2", "rgba(16, 24, 44, 0.92)");
      root.style.setProperty("--text", "#eef6ff");
      root.style.setProperty("--muted", "#8ea4c0");
      root.style.setProperty("--border", "rgba(120, 156, 255, 0.16)");
      root.style.setProperty("--input-bg", "#0f1419");
      root.style.setProperty("--shadow", "0 22px 55px rgba(0, 0, 0, 0.46)");
      root.style.setProperty("--window-color", "#050816");
      root.style.setProperty("--theme-grid-opacity", "0.45");
    } else {
      root.style.setProperty("--bg", "#f1f5f9");
      root.style.setProperty("--panel", "#ffffff");
      root.style.setProperty("--panel-2", "#f8fafc");
      root.style.setProperty("--text", "#0f172a");
      root.style.setProperty("--muted", "#64748b");
      root.style.setProperty("--border", "rgba(15, 23, 42, 0.12)");
      root.style.setProperty("--input-bg", "#ffffff");
      root.style.setProperty("--shadow", "0 16px 40px rgba(15, 23, 42, 0.08)");
      root.style.setProperty("--window-color", "#ffffff");
      root.style.setProperty("--theme-grid-opacity", "0.08");
    }
  }

  function apply(mode, { persist = true, broadcast = true } = {}) {
    const selected = normalizeMode(mode);
    const effective = selected === BLACK ? BLACK : WHITE;
    document.body.classList.remove("theme-black", "theme-white");
    document.body.classList.add(effective === BLACK ? "theme-black" : "theme-white");
    document.body.style.setProperty("--window-color", effective === BLACK ? "#000000" : "#ffffff");
    applyAdminPalette(effective);
    if (persist) {
      try {
        global.localStorage.setItem(STORAGE_KEY, selected);
      } catch {
        // ignore
      }
    }
    const metaTheme = document.querySelector('meta[name="theme-color"]');
    if (metaTheme) {
      metaTheme.setAttribute("content", effective === BLACK ? "#050816" : "#ffffff");
    }
    if (broadcast) {
      try {
        global.dispatchEvent(new CustomEvent("baupass-theme-changed", { detail: { mode: selected, effective } }));
        if (global.parent && global.parent !== global) {
          global.parent.postMessage({ type: "baupass-theme-changed", mode: selected }, global.location.origin);
        }
        document.querySelectorAll("iframe").forEach((frame) => {
          try {
            frame.contentWindow?.postMessage({ type: "baupass-sync-theme", mode: selected }, global.location.origin);
          } catch {
            // ignore
          }
        });
      } catch {
        // ignore
      }
    }
    return { mode: selected, effective };
  }

  function toggle() {
    const next = getStoredMode() === WHITE ? BLACK : WHITE;
    return apply(next);
  }

  function init() {
    apply(getStoredMode(), { persist: false, broadcast: false });
    global.addEventListener("storage", (event) => {
      if (event.key === STORAGE_KEY && event.newValue) {
        apply(event.newValue, { persist: false, broadcast: false });
      }
    });
    global.addEventListener("message", (event) => {
      if (!event?.data || event.origin !== global.location.origin) return;
      if (event.data.type === "baupass-sync-theme" && event.data.mode) {
        apply(event.data.mode, { persist: false, broadcast: false });
      }
    });
  }

  global.BaupassTheme = {
    STORAGE_KEY,
    WHITE,
    BLACK,
    getStoredMode,
    apply,
    toggle,
    init,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window);
