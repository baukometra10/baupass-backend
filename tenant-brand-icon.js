/**
 * Tenant app icon helpers — initials-based PNG icons for white-label tenants.
 */
(function initTenantBrandIcon(global) {
  const iconCache = new Map();
  const ACCENT_CSS_PROPS = [
    "--accent",
    "--accent-dark",
    "--accent-soft",
    "--accent-hover",
    "--accent-on",
    "--brand-accent",
    "--company-accent",
    "--corp-primary",
    "--worker-card-accent",
  ];

  function deriveBrandInitials(name) {
    const cleaned = String(name || "").trim().replace(/\s+/g, " ");
    if (!cleaned) return "MI";
    const parts = cleaned.split(/[\s\-–—]+/).filter(Boolean);
    if (parts.length >= 2) {
      return `${parts[0][0] || ""}${parts[1][0] || ""}`.toUpperCase();
    }
    const word = parts[0];
    if (word.length >= 2) return word.slice(0, 2).toUpperCase();
    return word[0].toUpperCase();
  }

  function normalizeAccent(color, fallback) {
    const raw = String(color || "").trim();
    return /^#[0-9a-f]{6}$/i.test(raw) ? raw.toLowerCase() : fallback;
  }

  function shadeHexColor(hex, amount) {
    const normalized = normalizeAccent(hex, "");
    if (!normalized) return "";
    const channel = normalized.slice(1);
    const parts = [channel.slice(0, 2), channel.slice(2, 4), channel.slice(4, 6)].map((part) => {
      const value = parseInt(part, 16);
      const next = Math.min(255, Math.max(0, value + amount));
      return next.toString(16).padStart(2, "0");
    });
    return `#${parts.join("")}`;
  }

  function hexRelativeLuminance(hex) {
    const normalized = normalizeAccent(hex, "");
    if (!normalized) return 0;
    const channels = [1, 3, 5].map((start) => {
      const value = parseInt(normalized.slice(start, start + 2), 16) / 255;
      return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
  }

  function contrastOnAccent(hex) {
    return hexRelativeLuminance(hex) > 0.55 ? "#111827" : "#ffffff";
  }

  function applyAccentVariables(el, accent) {
    const root = el || (typeof document !== "undefined" ? document.documentElement : null);
    if (!root || !root.style) return;
    const color = normalizeAccent(accent, "");
    if (!color) {
      clearAccentVariables(root);
      return;
    }
    const dark = shadeHexColor(color, -35);
    const soft = shadeHexColor(color, 40);
    const hover = shadeHexColor(color, 28);
    const on = contrastOnAccent(color);
    root.style.setProperty("--accent", color);
    root.style.setProperty("--accent-dark", dark);
    root.style.setProperty("--accent-soft", soft);
    root.style.setProperty("--accent-hover", hover);
    root.style.setProperty("--accent-on", on);
    root.style.setProperty("--brand-accent", color);
    root.style.setProperty("--company-accent", color);
    root.style.setProperty("--corp-primary", color);
    root.style.setProperty("--worker-card-accent", color);
  }

  function clearAccentVariables(el) {
    const root = el || (typeof document !== "undefined" ? document.documentElement : null);
    if (!root || !root.style) return;
    ACCENT_CSS_PROPS.forEach((prop) => root.style.removeProperty(prop));
  }

  function generateTenantIconDataUrl({ initials, accentColor, size } = {}) {
    const letters = String(initials || "MI").slice(0, 2).toUpperCase();
    const accent = normalizeAccent(accentColor, "#0a57c0");
    const px = Math.max(64, Number(size) || 192);
    const cacheKey = `${letters}|${accent}|${px}`;
    if (iconCache.has(cacheKey)) return iconCache.get(cacheKey);

    if (typeof document === "undefined") return "";

    const canvas = document.createElement("canvas");
    canvas.width = px;
    canvas.height = px;
    const ctx = canvas.getContext("2d");
    if (!ctx) return "";

    const radius = px * 0.22;
    ctx.fillStyle = accent;
    ctx.beginPath();
    if (typeof ctx.roundRect === "function") {
      ctx.roundRect(0, 0, px, px, radius);
    } else {
      ctx.rect(0, 0, px, px);
    }
    ctx.fill();

    const grad = ctx.createLinearGradient(0, 0, px, px);
    grad.addColorStop(0, "rgba(255,255,255,0.2)");
    grad.addColorStop(1, "rgba(0,0,0,0.14)");
    ctx.fillStyle = grad;
    ctx.fill();

    ctx.fillStyle = contrastOnAccent(accent);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const fontSize = Math.round(px * (letters.length > 1 ? 0.36 : 0.42));
    ctx.font = `700 ${fontSize}px Manrope, system-ui, -apple-system, sans-serif`;
    ctx.fillText(letters, px / 2, px / 2 + px * 0.02);

    const url = canvas.toDataURL("image/png");
    iconCache.set(cacheKey, url);
    return url;
  }

  function resolveTenantIconHref({ brandTitle, logoData, accentColor, size } = {}) {
    const logo = String(logoData || "").trim();
    if (logo) return logo;
    const initials = deriveBrandInitials(brandTitle);
    return generateTenantIconDataUrl({ initials, accentColor, size }) || "";
  }

  global.TenantBrandIcon = {
    deriveBrandInitials,
    shadeHexColor,
    contrastOnAccent,
    applyAccentVariables,
    clearAccentVariables,
    generateTenantIconDataUrl,
    resolveTenantIconHref,
  };
})(typeof window !== "undefined" ? window : globalThis);
