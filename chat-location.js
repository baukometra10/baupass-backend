/**
 * SUPPIX chat location — blink-fast share (memory + cached GPS), WhatsApp-style map card.
 */
(function initSuppixChatLocation(global) {
  const PREFIX = "@location|";
  const DEFAULT_MAX_ACCURACY_M = 10;
  const SEND_MAX_ACCURACY_M = 120;
  const LAST_KNOWN_MAX_AGE_MS = 15 * 60 * 1000;
  const FAST_CAPTURE_MAX_MS = 1200;
  let overlayEl = null;
  let stylesInjected = false;
  let lastKnownChatGeo = null;
  let warmInFlight = null;

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

  function isValidReading(reading) {
    return Boolean(
      reading
      && Number.isFinite(Number(reading.latitude))
      && Number.isFinite(Number(reading.longitude)),
    );
  }

  function rememberReading(reading) {
    if (!isValidReading(reading)) return;
    lastKnownChatGeo = {
      latitude: Number(reading.latitude),
      longitude: Number(reading.longitude),
      accuracy: Number(reading.accuracy) || 0,
      capturedAt: Date.now(),
    };
  }

  function getFreshLastKnown() {
    if (!lastKnownChatGeo) return null;
    if (Date.now() - Number(lastKnownChatGeo.capturedAt || 0) > LAST_KNOWN_MAX_AGE_MS) {
      return null;
    }
    return lastKnownChatGeo;
  }

  function getGeolocationReading(options) {
    const opts = options || {};
    if (typeof global.getCurrentGeolocationReading === "function") {
      return global.getCurrentGeolocationReading(opts);
    }
    return new Promise((resolve, reject) => {
      global.navigator.geolocation.getCurrentPosition(
        (position) => resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: Number(position.coords.accuracy) || 0,
          capturedAt: Date.now(),
        }),
        reject,
        opts,
      );
    });
  }

  function raceGeolocationAttempts(attempts) {
    return new Promise((resolve, reject) => {
      if (!attempts.length) {
        reject(new Error("geolocation_timeout"));
        return;
      }
      let pending = attempts.length;
      let settled = false;
      let lastError = null;
      attempts.forEach((attempt) => {
        getGeolocationReading(attempt)
          .then((reading) => {
            if (settled || !isValidReading(reading)) return;
            settled = true;
            resolve(reading);
          })
          .catch((error) => {
            lastError = error;
            pending -= 1;
            if (!settled && pending === 0) {
              reject(lastError || new Error("geolocation_timeout"));
            }
          });
      });
    });
  }

  function firstWatchFix(maxMs = 1200) {
    return new Promise((resolve, reject) => {
      if (!global.navigator?.geolocation) {
        reject(new Error("geolocation_unsupported"));
        return;
      }
      let settled = false;
      let watchId = null;
      const finish = (error, reading) => {
        if (settled) return;
        settled = true;
        global.clearTimeout(timer);
        if (watchId != null) {
          try { global.navigator.geolocation.clearWatch(watchId); } catch { /* ignore */ }
        }
        if (error) reject(error);
        else resolve(reading);
      };
      const timer = global.setTimeout(() => {
        const error = new Error("geolocation_timeout");
        error.code = 3;
        finish(error);
      }, maxMs);
      watchId = global.navigator.geolocation.watchPosition(
        (position) => {
          finish(null, {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracy: Number(position.coords.accuracy) || 0,
            capturedAt: Date.now(),
          });
        },
        (error) => {
          if (Number(error?.code) === 1) finish(error);
        },
        { enableHighAccuracy: true, maximumAge: 0, timeout: maxMs },
      );
    });
  }

  async function captureFastGeolocationForChat({ maxWaitMs = FAST_CAPTURE_MAX_MS } = {}) {
    if (!global.navigator?.geolocation) {
      const error = new Error("geolocation_unsupported");
      error.code = 0;
      throw error;
    }
    const cached = getFreshLastKnown();
    if (cached) return cached;

    const budget = Math.max(600, Number(maxWaitMs) || FAST_CAPTURE_MAX_MS);
    try {
      const reading = await raceGeolocationAttempts([
        { enableHighAccuracy: false, maximumAge: LAST_KNOWN_MAX_AGE_MS, timeout: Math.min(320, budget) },
        { enableHighAccuracy: false, maximumAge: 300000, timeout: Math.min(450, budget) },
        { enableHighAccuracy: false, maximumAge: 60000, timeout: Math.min(650, budget) },
      ]);
      rememberReading(reading);
      return reading;
    } catch (error) {
      if (Number(error?.code) === 1) throw error;
    }

    const remaining = Math.max(400, budget - 200);
    const reading = await firstWatchFix(remaining);
    rememberReading(reading);
    return reading;
  }

  function readingToResult(reading, options = {}) {
    const labels = options.labels || {};
    const accuracy = Number(reading?.accuracy);
    return {
      lat: reading.latitude,
      lng: reading.longitude,
      accuracy: Number.isFinite(accuracy) ? accuracy : 0,
      label: options.label || labels.sharedTitle || "",
    };
  }

  function warmChatGeolocation() {
    if (!global.navigator?.geolocation) return Promise.resolve(null);
    if (getFreshLastKnown()) return Promise.resolve(getFreshLastKnown());
    if (warmInFlight) return warmInFlight;
    warmInFlight = captureFastGeolocationForChat({ maxWaitMs: 900 })
      .then((reading) => {
        rememberReading(reading);
        return reading;
      })
      .catch(() => null)
      .finally(() => {
        warmInFlight = null;
      });
    return warmInFlight;
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

  function peekCachedChatLocation(options = {}) {
    const cached = getFreshLastKnown();
    if (!cached) return null;
    return readingToResult(cached, options);
  }

  async function captureChatLocation(options = {}) {
    const sendMaxAcc = Number(options.fallbackMaxAccuracyMeters || SEND_MAX_ACCURACY_M);
    const cached = getFreshLastKnown();
    const reading = cached || await captureFastGeolocationForChat({
      maxWaitMs: Number(options.maxWaitMs || FAST_CAPTURE_MAX_MS),
    });
    rememberReading(reading);
    const accuracy = Number(reading?.accuracy);
    if (Number.isFinite(accuracy) && accuracy > sendMaxAcc) {
      const error = new Error("location_not_precise_enough");
      error.accuracyMeters = accuracy;
      throw error;
    }
    return readingToResult(reading, options);
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
    peekCachedChatLocation,
    warmChatGeolocation,
    locationCaptureErrorMessage,
    mapsUrl,
    staticMapUrl,
  };
})(typeof window !== "undefined" ? window : globalThis);
