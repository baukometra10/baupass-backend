/**
 * SUPPIX chat location — WhatsApp-style Google Maps card + accurate GPS when sharing.
 */
(function initSuppixChatLocation(global) {
  const PREFIX = "@location|";
  const DEFAULT_MAX_ACCURACY_M = 10;
  const INSTANT_MAX_ACCURACY_M = 25;
  const TARGET_ACCURACY_M = 18;
  const SEND_MAX_ACCURACY_M = 50;
  const LAST_KNOWN_MAX_AGE_MS = 10 * 60 * 1000;
  const REFINE_MAX_MS = 6500;
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

  function googleMapsUrl(loc) {
    if (!loc) return "#";
    const lat = Number(loc.lat);
    const lng = Number(loc.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return "#";
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${lat},${lng}`)}`;
  }

  function googleMapsEmbedUrl(loc) {
    const lat = Number(loc?.lat);
    const lng = Number(loc?.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return "";
    const acc = Number(loc?.accuracy) || 999;
    const zoom = acc <= DEFAULT_MAX_ACCURACY_M ? 18 : acc <= 35 ? 17 : 16;
    const q = encodeURIComponent(`${lat},${lng}`);
    return `https://maps.google.com/maps?q=${q}&hl=de&z=${zoom}&output=embed`;
  }

  function mapsUrl(loc) {
    return googleMapsUrl(loc);
  }

  function embedMapUrl(loc) {
    return googleMapsEmbedUrl(loc);
  }

  function staticMapUrl(loc) {
    return googleMapsEmbedUrl(loc);
  }

  function ensureLocationStyles() {
    if (stylesInjected || !global.document) return;
    stylesInjected = true;
    const style = global.document.createElement("style");
    style.id = "suppixChatLocationStyles";
    style.textContent = [
      ".chat-location-card{max-width:min(100%,300px);border-radius:10px;overflow:hidden;background:#1f2c34;box-shadow:0 1px 2px rgba(0,0,0,.22)}",
      ".chat-location-card.is-mine,.chat-location-card.is-them{border:1px solid rgba(134,150,160,.16)}",
      ".chat-location-map-hit{display:block;text-decoration:none;color:inherit}",
      ".chat-location-map-frame{position:relative;height:140px;overflow:hidden;background:#dadce0}",
      ".chat-location-map-embed{position:absolute;left:50%;top:50%;width:118%;height:220px;border:0;pointer-events:none;transform:translate(-50%,-52%) scale(1.12)}",
      ".chat-location-map-frame::after{content:\"\";position:absolute;inset:auto 0 0 0;height:42px;background:linear-gradient(180deg,transparent,rgba(31,44,52,.92));pointer-events:none}",
      ".chat-location-map-caption{display:flex;flex-direction:column;gap:.1rem;padding:.55rem .65rem .62rem;background:#1f2c34}",
      ".chat-location-caption-title{font-size:.84rem;font-weight:600;color:#e9edef;line-height:1.25}",
      ".chat-location-caption-acc{font-size:.72rem;color:rgba(233,237,239,.58)}",
      ".chat-location-caption-acc.is-precise{color:#25d366;font-weight:600}",
      ".chat-location-caption-acc.is-warn{color:#fbbf24}",
      ".chat-location-map-fallback{display:grid;place-items:center;min-height:148px;background:linear-gradient(160deg,#dadce0,#bdc1c6);color:#3c4043;font-size:.82rem;padding:1rem;text-align:center}",
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
    if (!acc || acc <= 15) return "";
    if (acc <= DEFAULT_MAX_ACCURACY_M) {
      return (labels.accuracyGood || "Genauigkeit ±{m} m").replace("{m}", String(acc));
    }
    if (acc <= 35) {
      return (labels.accuracy || "±{m} m").replace("{m}", String(acc));
    }
    return (labels.accuracyApprox || "Standort ungefähr · ±{m} m").replace("{m}", String(acc));
  }

  function accuracyClass(loc) {
    const acc = Number(loc?.accuracy) || 0;
    if (acc <= DEFAULT_MAX_ACCURACY_M) return "is-precise";
    if (acc > 50) return "is-warn";
    return "";
  }

  function renderLocationBubbleHtml(loc, labels = {}, options = {}) {
    if (!loc) return "";
    ensureLocationStyles();
    const side = options.side === "mine" ? "is-mine" : "is-them";
    const title = escapeHtml(loc.label || labels.sharedTitle || formatLocationPreview(labels));
    const accText = accuracyLabel(loc, labels);
    const accClass = accuracyClass(loc);
    const embedSrc = googleMapsEmbedUrl(loc);
    const href = googleMapsUrl(loc);
    const openLabel = escapeHtml(labels.openMaps || "In Google Maps öffnen");
    const mapHtml = embedSrc
      ? `<div class="chat-location-map-frame"><iframe class="chat-location-map-embed" src="${escapeHtml(embedSrc)}" loading="eager" title="${title}" allowfullscreen referrerpolicy="no-referrer-when-downgrade"></iframe></div>`
      : `<div class="chat-location-map-fallback">${openLabel}</div>`;
    return `<div class="chat-location-card ${side}">
      <a class="chat-location-map-hit" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer" aria-label="${openLabel}">
        ${mapHtml}
        <div class="chat-location-map-caption">
          <span class="chat-location-caption-title">${title}</span>
          ${accText ? `<span class="chat-location-caption-acc ${accClass}">${escapeHtml(accText)}</span>` : ""}
        </div>
      </a>
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
    const accuracy = Number(reading.accuracy) || 999;
    if (
      lastKnownChatGeo
      && Number(lastKnownChatGeo.accuracy) < accuracy
      && Date.now() - Number(lastKnownChatGeo.capturedAt || 0) < 30000
    ) {
      return;
    }
    lastKnownChatGeo = {
      latitude: Number(reading.latitude),
      longitude: Number(reading.longitude),
      accuracy,
      capturedAt: Date.now(),
    };
  }

  function getFreshLastKnown(maxAccuracy = INSTANT_MAX_ACCURACY_M) {
    if (!lastKnownChatGeo) return null;
    if (Date.now() - Number(lastKnownChatGeo.capturedAt || 0) > LAST_KNOWN_MAX_AGE_MS) {
      return null;
    }
    if (Number(lastKnownChatGeo.accuracy) > maxAccuracy) {
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

  function watchBestAccuracy(maxMs = REFINE_MAX_MS, onProgress) {
    return new Promise((resolve, reject) => {
      if (!global.navigator?.geolocation) {
        reject(new Error("geolocation_unsupported"));
        return;
      }
      let settled = false;
      let best = null;
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
        if (best) finish(null, best);
        else {
          const error = new Error("geolocation_timeout");
          error.code = 3;
          finish(error);
        }
      }, maxMs);
      watchId = global.navigator.geolocation.watchPosition(
        (position) => {
          const reading = {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracy: Number(position.coords.accuracy) || 999,
            capturedAt: Date.now(),
          };
          if (!best || reading.accuracy < best.accuracy) {
            best = reading;
            onProgress?.({ bestAccuracyMeters: reading.accuracy, phase: "refine" });
          }
          if (reading.accuracy <= TARGET_ACCURACY_M) {
            finish(null, reading);
          }
        },
        (error) => {
          if (Number(error?.code) === 1) finish(error);
          else if (best) finish(null, best);
        },
        { enableHighAccuracy: true, maximumAge: 0, timeout: maxMs },
      );
    });
  }

  async function captureAccurateGeolocationForChat({ onProgress, maxWaitMs = REFINE_MAX_MS } = {}) {
    if (!global.navigator?.geolocation) {
      const error = new Error("geolocation_unsupported");
      error.code = 0;
      throw error;
    }
    const instant = getFreshLastKnown(INSTANT_MAX_ACCURACY_M);
    if (instant) return instant;

    if (typeof global.captureSiteAnchorGeolocation === "function") {
      const reading = await global.captureSiteAnchorGeolocation({
        maxAcceptAccuracyMeters: TARGET_ACCURACY_M,
        fallbackMaxAccuracyMeters: SEND_MAX_ACCURACY_M,
        hardMaxMs: maxWaitMs,
        quickReturnMs: 700,
        onProgress: (payload) => {
          onProgress?.({
            bestAccuracyMeters: payload.bestAccuracyMeters,
            phase: payload.phase || "refine",
          });
        },
      });
      rememberReading(reading);
      return reading;
    }

    try {
      const quick = await getGeolocationReading({
        enableHighAccuracy: true,
        maximumAge: 15000,
        timeout: Math.min(1200, maxWaitMs),
      });
      if (isValidReading(quick) && Number(quick.accuracy) <= INSTANT_MAX_ACCURACY_M) {
        rememberReading(quick);
        return quick;
      }
    } catch (error) {
      if (Number(error?.code) === 1) throw error;
    }

    const reading = await watchBestAccuracy(maxWaitMs, onProgress);
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
    const good = getFreshLastKnown(INSTANT_MAX_ACCURACY_M);
    if (good) return Promise.resolve(good);
    if (warmInFlight) return warmInFlight;
    const capture = typeof global.captureSiteAnchorGeolocation === "function"
      ? global.captureSiteAnchorGeolocation({
        maxAcceptAccuracyMeters: TARGET_ACCURACY_M,
        fallbackMaxAccuracyMeters: SEND_MAX_ACCURACY_M,
        hardMaxMs: 5000,
        quickReturnMs: 600,
      })
      : watchBestAccuracy(5000);
    warmInFlight = capture
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
    if (code === "geolocation_inaccurate" || code === "location_not_precise_enough" || Number(error?.code) === 4) {
      const tpl = labels.inaccurate || "GPS zu ungenau (±{m} m). Bitte kurz ins Freie gehen — max. {max} m.";
      return tpl.replace("{m}", String(Math.round(acc || 99))).replace("{max}", String(SEND_MAX_ACCURACY_M));
    }
    if (code === "geolocation_unsupported") return labels.unsupported || "Standort wird auf diesem Gerät nicht unterstützt.";
    if (code === "geolocation_timeout") return labels.timeout || "Standort-Timeout — bitte erneut versuchen.";
    if (Number(error?.code) === 1) return labels.denied || "Standortfreigabe verweigert.";
    return labels.failed || "Standort konnte nicht ermittelt werden.";
  }

  function peekCachedChatLocation(options = {}) {
    const cached = getFreshLastKnown(INSTANT_MAX_ACCURACY_M);
    if (!cached) return null;
    return readingToResult(cached, options);
  }

  async function captureChatLocation(options = {}) {
    const sendMaxAcc = Number(options.fallbackMaxAccuracyMeters || SEND_MAX_ACCURACY_M);
    const labels = options.labels || {};
    let overlay = null;
    let overlayTimer = null;
    let cancelled = false;
    const onProgress = (payload) => {
      options.onProgress?.(payload);
      overlay?.update?.(payload);
    };
    overlayTimer = global.setTimeout(() => {
      if (cancelled) return;
      overlay = showCaptureOverlay(labels, () => { cancelled = true; });
    }, 500);

    try {
      const instant = getFreshLastKnown(INSTANT_MAX_ACCURACY_M);
      const reading = instant || await captureAccurateGeolocationForChat({
        onProgress,
        maxWaitMs: Number(options.maxWaitMs || REFINE_MAX_MS),
      });
      if (cancelled) {
        const error = new Error("location_cancelled");
        throw error;
      }
      rememberReading(reading);
      const accuracy = Number(reading?.accuracy);
      if (Number.isFinite(accuracy) && accuracy > sendMaxAcc) {
        const error = new Error("location_not_precise_enough");
        error.accuracyMeters = accuracy;
        throw error;
      }
      return readingToResult(reading, options);
    } finally {
      if (overlayTimer) global.clearTimeout(overlayTimer);
      overlay?.hide?.();
      hideCaptureOverlay();
    }
  }

  let overlayEl = null;

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
    if (subEl) subEl.textContent = labels.capturingHint || "GPS verfeinern…";
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
          const tpl = labels.capturingProgress || "Aktuell ±{m} m";
          subEl.textContent = tpl.replace("{m}", String(Math.round(acc)));
        }
        if (fillEl && Number.isFinite(acc)) {
          const pct = Math.max(10, Math.min(100, ((SEND_MAX_ACCURACY_M - acc) / SEND_MAX_ACCURACY_M) * 100));
          fillEl.style.width = `${pct}%`;
        }
      },
      hide: hideCaptureOverlay,
    };
  }

  function hideCaptureOverlay() {
    overlayEl?.classList.add("hidden");
  }

  global.SUPPIXChatLocation = {
    PREFIX,
    DEFAULT_MAX_ACCURACY_M,
    INSTANT_MAX_ACCURACY_M,
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
    googleMapsUrl,
    googleMapsEmbedUrl,
    mapsUrl,
    staticMapUrl,
  };
})(typeof window !== "undefined" ? window : globalThis);
