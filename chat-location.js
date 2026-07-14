/**
 * SUPPIX chat location messages — encode/decode, capture GPS, render map card.
 */
(function initSuppixChatLocation(global) {
  const PREFIX = "@location|";

  function escapePart(value) {
    return encodeURIComponent(String(value ?? "").trim());
  }

  function unescapePart(value) {
    try {
      return decodeURIComponent(String(value || ""));
    } catch {
      return String(value || "");
    }
  }

  function encodeLocationBody({ lat, lng, accuracy, label } = {}) {
    const latitude = Number(lat);
    const longitude = Number(lng);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      throw new Error("location_invalid");
    }
    const parts = [
      `lat=${latitude.toFixed(6)}`,
      `lng=${longitude.toFixed(6)}`,
    ];
    const acc = Number(accuracy);
    if (Number.isFinite(acc) && acc > 0) parts.push(`acc=${Math.round(acc)}`);
    const cleanLabel = String(label || "").trim();
    if (cleanLabel) parts.push(`label=${escapePart(cleanLabel)}`);
    return `${PREFIX}${parts.join("|")}`;
  }

  function parseLocationBody(text) {
    const raw = String(text || "").trim();
    if (!raw.startsWith(PREFIX)) return null;
    const meta = {};
    raw.slice(PREFIX.length).split("|").forEach((part) => {
      const idx = part.indexOf("=");
      if (idx <= 0) return;
      meta[part.slice(0, idx)] = unescapePart(part.slice(idx + 1));
    });
    const lat = Number(meta.lat);
    const lng = Number(meta.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    return {
      lat,
      lng,
      accuracy: Number(meta.acc) || 0,
      label: String(meta.label || "").trim(),
    };
  }

  function isLocationBody(text) {
    return parseLocationBody(text) !== null;
  }

  function mapsUrl(loc) {
    if (!loc) return "#";
    return `https://www.openstreetmap.org/?mlat=${loc.lat}&mlon=${loc.lng}#map=16/${loc.lat}/${loc.lng}`;
  }

  function staticMapUrl(loc) {
    if (!loc) return "";
    const lat = loc.lat.toFixed(6);
    const lng = loc.lng.toFixed(6);
    return `https://staticmap.openstreetmap.de/staticmap.php?center=${lat},${lng}&zoom=15&size=280x160&markers=${lat},${lng}`;
  }

  function formatLocationPreview(labels = {}) {
    return labels.location || labels.preview || "📍 Standort";
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderLocationBubbleHtml(loc, labels = {}, options = {}) {
    if (!loc) return "";
    const side = options.side === "mine" ? "is-mine" : "is-them";
    const title = escapeHtml(loc.label || formatLocationPreview(labels));
    const accuracy = loc.accuracy
      ? `<span class="chat-location-acc">${escapeHtml((labels.accuracy || "±{m} m").replace("{m}", String(Math.round(loc.accuracy))))}</span>`
      : "";
    const coords = `${loc.lat.toFixed(5)}, ${loc.lng.toFixed(5)}`;
    const mapSrc = staticMapUrl(loc);
    const href = mapsUrl(loc);
    const openLabel = escapeHtml(labels.openMaps || "In Karte öffnen");
    return `<div class="chat-location-card ${side}">
      <a class="chat-location-map-link" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">
        <img class="chat-location-map" src="${escapeHtml(mapSrc)}" alt="${title}" loading="lazy" width="280" height="160" />
      </a>
      <div class="chat-location-meta">
        <strong class="chat-location-title">${title}</strong>
        <span class="chat-location-coords">${escapeHtml(coords)}</span>
        ${accuracy}
        <a class="chat-location-open" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${openLabel}</a>
      </div>
    </div>`;
  }

  async function captureChatLocation(options = {}) {
    const onProgress = options.onProgress;
    onProgress?.(options.capturingLabel || "Standort wird ermittelt…");
    if (typeof global.capturePointGeolocation === "function") {
      const point = await global.capturePointGeolocation({ maxWaitMs: 5000, onProgress });
      return {
        lat: point.latitude,
        lng: point.longitude,
        accuracy: point.accuracy,
        label: options.label || "",
      };
    }
    if (!global.navigator?.geolocation) {
      const error = new Error("geolocation_unsupported");
      error.code = 0;
      throw error;
    }
    const point = await new Promise((resolve, reject) => {
      global.navigator.geolocation.getCurrentPosition(
        (pos) => resolve({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        }),
        (err) => reject(err),
        { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 },
      );
    });
    return { ...point, label: options.label || "" };
  }

  global.SUPPIXChatLocation = {
    PREFIX,
    encodeLocationBody,
    parseLocationBody,
    isLocationBody,
    formatLocationPreview,
    renderLocationBubbleHtml,
    captureChatLocation,
    mapsUrl,
    staticMapUrl,
  };
})(typeof window !== "undefined" ? window : globalThis);
