/**
 * Tenant app icon helpers — initials-based PNG icons for white-label tenants.
 */
(function initTenantBrandIcon(global) {
  const iconCache = new Map();

  function deriveBrandInitials(name) {
    const cleaned = String(name || "").trim().replace(/\s+/g, " ");
    if (!cleaned) return "WP";
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

  function generateTenantIconDataUrl({ initials, accentColor, size } = {}) {
    const letters = String(initials || "WP").slice(0, 2).toUpperCase();
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

    ctx.fillStyle = "#ffffff";
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
    generateTenantIconDataUrl,
    resolveTenantIconHref,
  };
})(typeof window !== "undefined" ? window : globalThis);
