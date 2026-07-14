/**
 * SUPPIX chat location — precise GPS (≤10 m), WhatsApp-style map card, capture overlay.
 */
(function initSuppixChatLocation(global) {
  const PREFIX = "@location|";
  const DEFAULT_MAX_ACCURACY_M = 10;
  const SEND_MAX_ACCURACY_M = 30;
  let overlayEl = null;
  let stylesInjected = false;

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
    return `https://www.openstreetmap.org/?mlat=${loc.lat}&mlon=${loc.lng}#map=18/${loc.lat}/${loc.lng}`;
  }

  function embedMapUrl(loc) {
    if (!loc) return "";
    const lat = Number(loc.lat);
    const lng = Number(loc.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return "";
    const zoom = Number(loc.accuracy) <= DEFAULT_MAX_ACCURACY_M ? 17 : 16;
    const latDelta = zoom >= 17 ? 0.0035 : 0.006;
    const lngDelta = zoom >= 17 ? 0.0055 : 0.009;
    const bbox = [
      lng - lngDelta,
      lat - latDelta,
      lng + lngDelta,
      lat + latDelta,
    ].join(",");
    return `https://www.openstreetmap.org/export/embed.html?bbox=${encodeURIComponent(bbox)}&layer=mapnik&marker=${encodeURIComponent(`${lat},${lng}`)}`;
  }

  function staticMapUrl(loc) {
    if (!loc) return "";
    const lat = loc.lat.toFixed(6);
    const lng = loc.lng.toFixed(6);
    const zoom = Number(loc.accuracy) <= DEFAULT_MAX_ACCURACY_M ? 17 : 15;
    return `https://staticmap.openstreetmap.de/staticmap.php?center=${lat},${lng}&zoom=${zoom}&size=320x180&markers=${lat},${lng}`;
  }

  function ensureLocationStyles() {
    if (stylesInjected || !global.document) return;
    stylesInjected = true;
    const style = global.document.createElement("style");
    style.id = "suppixChatLocationStyles";
    style.textContent = [
      ".chat-location-map-embed{display:block;width:100%;height:180px;border:0;background:#0f172a}",
      ".chat-location-map-fallback{display:grid;place-items:center;min-height:140px;background:linear-gradient(145deg,#0f172a,#1e293b);color:#94a3b8;font-size:.82rem;padding:1rem;text-align:center}",
    ].join("");
    global.document.head.appendChild(style);
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

  function accuracyLabel(loc, labels = {}) {
    const acc = Math.round(Number(loc?.accuracy) || 0);
    if (!acc) return "";
    const tpl = acc <= DEFAULT_MAX_ACCURACY_M
      ? (labels.accuracyGood || "Genauigkeit ±{m} m")
      : (labels.accuracy || "±{m} m");
    return tpl.replace("{m}", String(acc));
  }

  function renderLocationBubbleHtml(loc, labels = {}, options = {}) {
    if (!loc) return "";
    ensureLocationStyles();
    const side = options.side === "mine" ? "is-mine" : "is-them";
    const title = escapeHtml(loc.label || labels.sharedTitle || formatLocationPreview(labels));
    const accText = accuracyLabel(loc, labels);
    const accClass = Number(loc.accuracy) <= DEFAULT_MAX_ACCURACY_M ? "is-precise" : "";
    const embedSrc = embedMapUrl(loc);
    const href = mapsUrl(loc);
    const openLabel = escapeHtml(labels.openMaps || "In Karte öffnen");
    const mapHtml = embedSrc
      ? `<iframe class="chat-location-map-embed" src="${escapeHtml(embedSrc)}" loading="lazy" title="${title}" referrerpolicy="no-referrer-when-downgrade"></iframe>`
      : `<div class="chat-location-map-fallback">${openLabel}</div>`;
    return `<div class="chat-location-card ${side}">
      <div class="chat-location-map-link">
        ${mapHtml}
        <span class="chat-location-map-pin" aria-hidden="true">📍</span>
      </div>
      <div class="chat-location-meta">
        <div class="chat-location-head">
          <span class="chat-location-icon" aria-hidden="true">📍</span>
          <div class="chat-location-text">
            <strong class="chat-location-title">${title}</strong>
            ${accText ? `<span class="chat-location-acc ${accClass}">${escapeHtml(accText)}</span>` : ""}
          </div>
        </div>
        <a class="chat-location-open" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${openLabel}</a>
      </div>
    </div>`;
  }

  function ensureOverlay() {
    if (overlayEl) return overlayEl;
    overlayEl = global.document?.createElement("div");
    if (!overlayEl) return null;
    overlayEl.className = "chat-location-overlay hidden";
    overlayEl.innerHTML = `<div class="chat-location-overlay-card" role="dialog" aria-modal="true" aria-live="polite">
      <div class="chat-location-overlay-pulse" aria-hidden="true">📍</div>
      <strong class="chat-location-overlay-title"></strong>
      <p class="chat-location-overlay-sub"></p>
      <div class="chat-location-overlay-meter"><span class="chat-location-overlay-meter-fill"></span></div>
      <button type="button" class="chat-location-overlay-cancel"></button>
    </div>`;
    global.document.body.appendChild(overlayEl);
    return overlayEl;
  }

  function showCaptureOverlay(labels = {}, onCancel) {
    const host = ensureOverlay();
    if (!host) return { update() {}, hide() {} };
    const titleEl = host.querySelector(".chat-location-overlay-title");
    const subEl = host.querySelector(".chat-location-overlay-sub");
    const fillEl = host.querySelector(".chat-location-overlay-meter-fill");
    const cancelBtn = host.querySelector(".chat-location-overlay-cancel");
    if (titleEl) titleEl.textContent = labels.capturing || "Standort wird ermittelt…";
    if (subEl) subEl.textContent = labels.capturingHint || "Bitte draußen bleiben — Ziel: ±10 m";
    if (cancelBtn) {
      cancelBtn.textContent = labels.cancel || "Abbrechen";
      cancelBtn.onclick = () => {
        hideCaptureOverlay();
        onCancel?.();
      };
    }
    host.classList.remove("hidden");
    return {
      update(progress = {}) {
        const acc = Number(progress.bestAccuracyMeters);
        if (subEl && Number.isFinite(acc)) {
          const tpl = labels.capturingProgress || "Verfeinern… aktuell ±{m} m (Ziel ≤10 m)";
          subEl.textContent = tpl.replace("{m}", String(Math.round(acc)));
        }
        if (fillEl && Number.isFinite(acc)) {
          const pct = Math.max(8, Math.min(100, ((DEFAULT_MAX_ACCURACY_M * 2 - acc) / (DEFAULT_MAX_ACCURACY_M * 2)) * 100));
          fillEl.style.width = `${pct}%`;
        }
      },
      hide: hideCaptureOverlay,
    };
  }

  function hideCaptureOverlay() {
    overlayEl?.classList.add("hidden");
  }

  function locationCaptureErrorMessage(error, labels = {}) {
    const code = String(error?.message || error?.code || "");
    const acc = Number(error?.accuracyMeters);
    if (code === "geolocation_inaccurate" || code === "location_not_precise_enough") {
      const tpl = labels.inaccurate || "GPS zu ungenau (±{m} m). Bitte ins Freie gehen — max. {max} m nötig.";
      return tpl.replace("{m}", String(Math.round(acc || 99))).replace("{max}", String(SEND_MAX_ACCURACY_M));
    }
    if (code === "geolocation_unsupported") return labels.unsupported || "Standort wird auf diesem Gerät nicht unterstützt.";
    if (code === "geolocation_timeout") return labels.timeout || "Standort-Timeout — bitte erneut versuchen.";
    if (Number(error?.code) === 1) return labels.denied || "Standortfreigabe verweigert.";
    return labels.failed || "Standort konnte nicht ermittelt werden.";
  }

  async function captureChatLocation(options = {}) {
    const idealAcc = Number(options.maxAccuracyMeters || DEFAULT_MAX_ACCURACY_M);
    const sendMaxAcc = Number(options.fallbackMaxAccuracyMeters || SEND_MAX_ACCURACY_M);
    const labels = options.labels || {};
    let cancelled = false;
    const overlay = showCaptureOverlay(labels, () => { cancelled = true; });
    const onProgress = (payload) => {
      options.onProgress?.(payload);
      overlay.update(payload);
    };
    try {
      let point = null;
      if (typeof global.captureSiteAnchorGeolocation === "function") {
        point = await global.captureSiteAnchorGeolocation({
          maxAcceptAccuracyMeters: idealAcc,
          fallbackMaxAccuracyMeters: sendMaxAcc,
          hardMaxMs: Number(options.maxWaitMs || 20000),
          onProgress,
        });
      } else if (typeof global.captureMapsGradeGeolocation === "function") {
        point = await global.captureMapsGradeGeolocation({ onProgress, maxWaitMs: 20000 });
      } else if (typeof global.capturePointGeolocation === "function") {
        point = await global.capturePointGeolocation({ maxWaitMs: 12000, onProgress });
      } else if (global.navigator?.geolocation) {
        point = await new Promise((resolve, reject) => {
          global.navigator.geolocation.getCurrentPosition(
            (pos) => resolve({
              latitude: pos.coords.latitude,
              longitude: pos.coords.longitude,
              accuracy: pos.coords.accuracy,
            }),
            reject,
            { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
          );
        });
      } else {
        const error = new Error("geolocation_unsupported");
        error.code = 0;
        throw error;
      }
      if (cancelled) {
        const error = new Error("location_cancelled");
        throw error;
      }
      const accuracy = Number(point?.accuracy);
      if (!Number.isFinite(accuracy) || accuracy > sendMaxAcc) {
        const error = new Error("location_not_precise_enough");
        error.accuracyMeters = accuracy;
        throw error;
      }
      return {
        lat: point.latitude,
        lng: point.longitude,
        accuracy,
        label: options.label || labels.sharedTitle || "",
      };
    } finally {
      overlay.hide();
    }
  }

  global.SUPPIXChatLocation = {
    PREFIX,
    DEFAULT_MAX_ACCURACY_M,
    SEND_MAX_ACCURACY_M,
    encodeLocationBody,
    parseLocationBody,
    isLocationBody,
    formatLocationPreview,
    renderLocationBubbleHtml,
    captureChatLocation,
    locationCaptureErrorMessage,
    mapsUrl,
    staticMapUrl,
  };
})(typeof window !== "undefined" ? window : globalThis);
