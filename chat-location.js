/**
 * SUPPIX chat location — WhatsApp-style map card + instant precise GPS.
 */
(function initSuppixChatLocation(global) {
  const PREFIX = "@location|";
  const MAP_W = 280;
  const MAP_H = 160;
  const DEFAULT_MAX_ACCURACY_M = 8;
  const SEND_MAX_ACCURACY_M = 10;
  const MAP_MAX_ACCURACY_M = 10;
  const COARSE_IGNORE_ACCURACY_M = 35;
  const CACHE_MAX_ACCURACY_M = 10;
  const CAPTURE_SEND_MS = 25000;
  const REFINE_MAX_MS = 30000;
  const PREVIEW_TIMEOUT_MS = 35000;
  const RAW_GEO_TIMEOUT_MS = 30000;
  const CACHE_MAX_AGE_MS = 5 * 60 * 1000;
  const WARM_CYCLE_MS = 30000;
  let stylesInjected = false;
  let lastKnownChatGeo = null;
  let warmWatchHandle = null;
  let shareSheetEl = null;
  let shareWatchHandle = null;
  let shareRawWatchId = null;

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

  function encodeLocationBody({ lat, lng, accuracy, note, label } = {}) {
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
    const cleanNote = String(note ?? label ?? "").trim();
    if (cleanNote) parts.push(`note=${escapePart(cleanNote)}`);
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
      note: String(meta.note || meta.label || "").trim(),
    };
  }

  function isLocationBody(text) {
    return parseLocationBody(text) !== null;
  }

  function googleMapsUrl(loc) {
    const lat = Number(loc?.lat);
    const lng = Number(loc?.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return "#";
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${lat},${lng}`)}`;
  }

  function mapZoomForAccuracy(acc) {
    const a = Number(acc) || 999;
    if (a <= 5) return 19;
    if (a <= DEFAULT_MAX_ACCURACY_M) return 18;
    if (a <= 15) return 17;
    return 16;
  }

  function googleMapsEmbedUrl(loc) {
    const lat = Number(loc?.lat);
    const lng = Number(loc?.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return "";
    const zoom = mapZoomForAccuracy(loc?.accuracy);
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
      ".chat-location-card{display:block;width:min(100%,280px);border-radius:10px;overflow:hidden;box-shadow:0 1px 0.5px rgba(0,0,0,.13)}",
      ".chat-location-card.is-mine{background:#005c4b;padding:3px}",
      ".chat-location-card.is-them{background:#202c33;padding:3px}",
      ".chat-location-card.is-mine.admin-theme{background:#0f766e}",
      ".chat-location-map-frame{position:relative;width:100%;height:160px;border-radius:8px;overflow:hidden;background:#e5e3df;line-height:0}",
      ".chat-location-map-embed{display:block;width:100%;height:160px;border:0;margin:0;padding:0;background:#e5e3df}",
      ".chat-location-map-link{position:absolute;inset:0;z-index:2;text-decoration:none;color:transparent}",
      ".chat-location-map-meta{position:absolute;right:7px;bottom:6px;z-index:4;display:inline-flex;align-items:center;gap:3px;padding:2px 7px 2px 8px;border-radius:7px;background:rgba(17,27,33,.62);font-size:.68rem;line-height:1.2;color:#fff;pointer-events:none}",
      ".chat-location-time{font-size:.68rem;color:#fff}",
      ".chat-location-map-meta .chat-ticks,.chat-location-map-meta .worker-chat-ticks{font-size:.74rem;line-height:1;color:rgba(255,255,255,.75)}",
      ".chat-location-map-meta .chat-ticks.is-read,.chat-location-map-meta .worker-chat-ticks.is-read{color:#53bdeb;font-weight:700}",
      ".chat-location-note-strip{padding:.42rem .5rem .48rem;font-size:.84rem;line-height:1.35;color:#e9edef;white-space:pre-wrap;word-break:break-word}",
      ".chat-location-map-fallback{display:grid;place-items:center;width:100%;height:160px;background:#e5e3df;color:#3c4043;font-size:.82rem;padding:1rem;text-align:center}",
      ".chat-location-share-sheet{position:fixed;inset:0;z-index:10000;display:flex;flex-direction:column;background:#0b141a}",
      ".chat-location-share-top{display:flex;align-items:center;justify-content:space-between;padding:.75rem .85rem;color:#e9edef;background:#1f2c34;flex-shrink:0}",
      ".chat-location-share-close{border:none;background:transparent;color:#e9edef;font-size:1.6rem;line-height:1;cursor:pointer;padding:.2rem .45rem}",
      ".chat-location-share-heading{margin:0;font-size:1.02rem;font-weight:600}",
      ".chat-location-share-mapwrap{flex:1;display:flex;flex-direction:column;min-height:0;padding:.75rem .75rem 0}",
      ".chat-location-share-map{position:relative;width:100%;height:min(52vh,360px);min-height:220px;border-radius:12px;overflow:hidden;background:#e5e3df;flex-shrink:0}",
      ".chat-location-share-map .chat-location-map-embed{width:100%;height:100%;min-height:220px}",
      ".chat-location-share-map-loading{position:absolute;inset:0;display:grid;place-items:center;background:rgba(17,27,33,.5);color:#e9edef;font-size:.88rem}",
      ".chat-location-share-map-loading.hidden{display:none}",
      ".chat-location-share-panel{flex-shrink:0;background:#1f2c34;padding:.85rem .85rem calc(.85rem + env(safe-area-inset-bottom,0px));border-top:1px solid rgba(134,150,160,.14)}",
      ".chat-location-share-status{margin:0 0 .55rem;font-size:.8rem;color:#8696a0}",
      ".chat-location-share-status.is-precise{color:#25d366}",
      ".chat-location-share-note{width:100%;min-height:42px;max-height:88px;resize:none;border-radius:10px;border:1px solid rgba(134,150,160,.2);background:#2a3942;color:#e9edef;padding:.6rem .7rem;font:inherit;font-size:.9rem;margin-bottom:.75rem}",
      ".chat-location-share-note::placeholder{color:rgba(233,237,239,.42)}",
      ".chat-location-share-actions{display:flex;justify-content:flex-end}",
      ".chat-location-share-send{min-width:128px;border:none;border-radius:999px;background:#00a884;color:#fff;font:inherit;font-weight:700;font-size:.92rem;padding:.7rem 1.4rem;cursor:pointer}",
      ".chat-location-share-send:disabled{opacity:.4;cursor:not-allowed}",
    ].join("");
    global.document.head.appendChild(style);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function buildMapFrameHtml(point, options = {}) {
    const embedSrc = googleMapsEmbedUrl(point);
    const href = googleMapsUrl(point);
    const openLabel = escapeHtml(options.openLabel || "In Google Maps öffnen");
    const metaHtml = String(options.metaHtml || "").trim();
    if (!embedSrc) {
      return `<div class="chat-location-map-fallback">${openLabel}</div>`;
    }
    return `<div class="chat-location-map-frame">
      <iframe class="chat-location-map-embed" src="${escapeHtml(embedSrc)}" width="${MAP_W}" height="${MAP_H}" loading="eager" title="${openLabel}" referrerpolicy="no-referrer-when-downgrade" allowfullscreen></iframe>
      <a class="chat-location-map-link" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer" aria-label="${openLabel}"></a>
      ${metaHtml ? `<div class="chat-location-map-meta">${metaHtml}</div>` : ""}
    </div>`;
  }

  function renderLocationBubbleHtml(loc, labels = {}, options = {}) {
    if (!loc) return "";
    ensureLocationStyles();
    const side = options.side === "mine" ? "is-mine" : "is-them";
    const themeClass = options.theme === "admin" ? " admin-theme" : "";
    const noteHtml = loc.note
      ? `<div class="chat-location-note-strip">${escapeHtml(loc.note)}</div>`
      : "";
    const mapHtml = buildMapFrameHtml(loc, {
      metaHtml: options.metaHtml,
      openLabel: labels.openMaps || "In Google Maps öffnen",
    });
    return `<div class="chat-location-card ${side}${themeClass}">${mapHtml}${noteHtml}</div>`;
  }

  function isValidReading(reading) {
    return Boolean(
      reading
      && Number.isFinite(Number(reading.latitude))
      && Number.isFinite(Number(reading.longitude)),
    );
  }

  function isPreciseEnoughForMap(reading) {
    return Number(reading?.accuracy) <= MAP_MAX_ACCURACY_M;
  }

  function isCoarseNetworkReading(reading) {
    return Number(reading?.accuracy) > COARSE_IGNORE_ACCURACY_M;
  }

  function pickBetterReading(current, next) {
    if (!isValidReading(next)) return current;
    if (isCoarseNetworkReading(next)) return current;
    if (!isValidReading(current)) return next;
    return Number(next.accuracy) < Number(current.accuracy) ? next : current;
  }

  function rememberReading(reading) {
    if (!isValidReading(reading)) return;
    const accuracy = Number(reading.accuracy) || 999;
    if (accuracy > 25) return;
    if (
      lastKnownChatGeo
      && Number(lastKnownChatGeo.accuracy) < accuracy
      && Date.now() - Number(lastKnownChatGeo.capturedAt || 0) < 20000
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

  function getPreciseCachedLastKnown() {
    if (!lastKnownChatGeo) return null;
    const age = Date.now() - Number(lastKnownChatGeo.capturedAt || 0);
    if (age > CACHE_MAX_AGE_MS) return null;
    if (Number(lastKnownChatGeo.accuracy) > CACHE_MAX_ACCURACY_M) return null;
    return lastKnownChatGeo;
  }

  function rejectImpreciseReading(reading, maxAccuracyMeters) {
    const acc = Number(reading?.accuracy) || 999;
    if (!isValidReading(reading) || acc > maxAccuracyMeters) {
      const error = new Error("location_not_precise_enough");
      error.accuracyMeters = acc;
      throw error;
    }
    return reading;
  }

  function getGeolocationReading(options) {
    if (typeof global.getCurrentGeolocationReading === "function") {
      return global.getCurrentGeolocationReading(options || {});
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
        options || {},
      );
    });
  }

  function stopShareWatch() {
    if (shareRawWatchId != null) {
      try { global.navigator.geolocation.clearWatch(shareRawWatchId); } catch { /* ignore */ }
      shareRawWatchId = null;
    }
    if (shareWatchHandle) {
      try { shareWatchHandle.stop?.(); } catch { /* ignore */ }
      shareWatchHandle = null;
    }
  }

  function applyReading(reading, onReading) {
    if (!isValidReading(reading)) return;
    if (isCoarseNetworkReading(reading)) {
      onReading(null, null, { weakSignal: true });
      return;
    }
    rememberReading(reading);
    onReading(reading);
  }

  function readingFromPosition(position) {
    return {
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
      accuracy: Number(position.coords.accuracy) || 0,
      capturedAt: Date.now(),
    };
  }

  async function captureForSend(onProgress) {
    let reading = null;
    if (typeof global.capturePreciseGeolocation === "function") {
      reading = await global.capturePreciseGeolocation({
        preset: "maps",
        maxWaitMs: CAPTURE_SEND_MS,
        targetAccuracyMeters: 8,
        acceptAccuracyMeters: 8,
        minSamples: 3,
        stableThresholdMeters: 3,
        onProgress: (payload) => {
          onProgress?.({
            bestAccuracyMeters: payload?.bestAccuracyMeters,
            phase: "send",
          });
        },
      });
    } else if (typeof global.captureSiteAnchorGeolocation === "function") {
      reading = await global.captureSiteAnchorGeolocation({
        maxAcceptAccuracyMeters: 8,
        fallbackMaxAccuracyMeters: SEND_MAX_ACCURACY_M,
        hardMaxMs: CAPTURE_SEND_MS,
        quickReturnMs: 800,
        onProgress,
      });
    } else {
      reading = await getGeolocationReading({
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: CAPTURE_SEND_MS,
      });
    }
    return rejectImpreciseReading(reading, SEND_MAX_ACCURACY_M);
  }

  async function captureBestReadingFast(onProgress) {
    if (typeof global.capturePreciseGeolocation === "function") {
      try {
        return await global.capturePreciseGeolocation({
          preset: "chat",
          maxWaitMs: REFINE_MAX_MS,
          targetAccuracyMeters: 8,
          acceptAccuracyMeters: 8,
          onProgress: (payload) => {
            onProgress?.({
              bestAccuracyMeters: payload?.bestAccuracyMeters,
              phase: "refine",
            });
          },
        });
      } catch (error) {
        if (Number(error?.code) === 1) throw error;
      }
    }
    try {
      return await getGeolocationReading({
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: 10000,
      }).then((reading) => (isCoarseNetworkReading(reading) ? null : reading));
    } catch (error) {
      if (Number(error?.code) === 1) throw error;
      return null;
    }
  }

  function startShareLocationWatch(onReading) {
    stopShareWatch();
    if (!global.navigator?.geolocation) return;

    const instant = getPreciseCachedLastKnown();
    if (instant) applyReading(instant, onReading);

    shareRawWatchId = global.navigator.geolocation.watchPosition(
      (position) => applyReading(readingFromPosition(position), onReading),
      (error) => {
        if (Number(error?.code) === 1) onReading(null, error);
      },
      {
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: RAW_GEO_TIMEOUT_MS,
      },
    );

    void captureBestReadingFast()
      .then((reading) => {
        if (reading) applyReading(reading, onReading);
      })
      .catch((error) => {
        if (Number(error?.code) === 1) onReading(null, error);
      });

    if (typeof global.startPreciseLocationWatch !== "function") return;
    shareWatchHandle = global.startPreciseLocationWatch({
      preset: "chat",
      maxWaitMs: REFINE_MAX_MS,
      onProgress: (payload) => {
        applyReading(payload?.reading, onReading);
      },
      onError: (error) => {
        if (Number(error?.code) === 1) onReading(null, error);
      },
    });
  }

  function canEnableSend(reading) {
    if (!isValidReading(reading)) return false;
    return Number(reading.accuracy) <= SEND_MAX_ACCURACY_M;
  }

  function ensureBackgroundGeoWarm() {
    if (!global.navigator?.geolocation || warmWatchHandle) return;
    if (typeof global.startPreciseLocationWatch !== "function") return;
    const startCycle = () => {
      if (warmWatchHandle) return;
      warmWatchHandle = global.startPreciseLocationWatch({
        preset: "chat",
        maxWaitMs: WARM_CYCLE_MS,
        onProgress: (payload) => {
          if (isValidReading(payload?.reading)) rememberReading(payload.reading);
        },
        onDone: (reading) => {
          warmWatchHandle = null;
          if (isValidReading(reading)) rememberReading(reading);
          global.setTimeout(startCycle, 300);
        },
        onError: () => {
          warmWatchHandle = null;
          global.setTimeout(startCycle, 800);
        },
      });
    };
    startCycle();
  }

  function shareStatusText(reading, labels = {}, meta = {}) {
    if (meta?.weakSignal) {
      return labels.weakSignal || labels.capturingHint || "GPS-Signal schwach — bitte ans Fenster oder ins Freie";
    }
    const acc = Math.round(Number(reading?.accuracy) || 0);
    if (!acc) return labels.capturingHint || "Präzises GPS wird gesucht…";
    if (acc <= DEFAULT_MAX_ACCURACY_M) {
      return (labels.accuracyGood || "Genauigkeit ±{m} m").replace("{m}", String(acc));
    }
    if (acc <= SEND_MAX_ACCURACY_M) {
      return (labels.ready || "Standort bereit · ±{m} m").replace("{m}", String(acc));
    }
    const tpl = labels.capturingProgress || "GPS verfeinert… ±{m} m";
    return tpl.replace("{m}", String(acc));
  }

  function readingToResult(reading, options = {}) {
    const accuracy = Number(reading?.accuracy);
    return {
      lat: reading.latitude,
      lng: reading.longitude,
      accuracy: Number.isFinite(accuracy) ? accuracy : 0,
      note: String(options.note || "").trim(),
    };
  }

  function mountMapInHost(host, point, metaHtml) {
    if (!host || !point) return;
    host.innerHTML = buildMapFrameHtml(point, { metaHtml });
    host.querySelector(".chat-location-share-map-loading")?.classList.add("hidden");
  }

  function closeShareSheet() {
    stopShareWatch();
    shareSheetEl?.remove();
    shareSheetEl = null;
  }

  function openShareSheet(options = {}) {
    ensureLocationStyles();
    ensureBackgroundGeoWarm();
    const labels = options.labels || {};
    if (!global.navigator?.geolocation) {
      return Promise.reject(new Error("geolocation_unsupported"));
    }
    closeShareSheet();

    const cached = getPreciseCachedLastKnown();
    const cachedPoint = cached ? readingToResult(cached) : null;
    const cachedSendReady = cached ? canEnableSend(cached) : false;

    return new Promise((resolve, reject) => {
      let settled = false;
      let bestReading = cached || null;
      let previewTimeout = null;
      const finish = (error, result) => {
        if (settled) return;
        settled = true;
        if (previewTimeout) global.clearTimeout(previewTimeout);
        closeShareSheet();
        if (error) reject(error);
        else resolve(result);
      };

      const sheet = global.document.createElement("div");
      sheet.className = "chat-location-share-sheet";
      sheet.innerHTML = `<div class="chat-location-share-top">
          <button type="button" class="chat-location-share-close" aria-label="${escapeHtml(labels.cancel || "Abbrechen")}">×</button>
          <h3 class="chat-location-share-heading">${escapeHtml(labels.shareTitle || "Standort senden")}</h3>
          <span style="width:2rem"></span>
        </div>
        <div class="chat-location-share-mapwrap">
          <div class="chat-location-share-map">
            ${cachedPoint ? buildMapFrameHtml(cachedPoint) : `<div class="chat-location-share-map-loading">${escapeHtml(labels.capturing || "Standort wird ermittelt…")}</div>`}
          </div>
        </div>
        <div class="chat-location-share-panel">
          <p class="chat-location-share-status${cachedPoint && Number(cachedPoint.accuracy) <= DEFAULT_MAX_ACCURACY_M ? " is-precise" : ""}">${escapeHtml(cachedPoint ? shareStatusText(cached, labels) : (labels.capturingHint || "Standort wird ermittelt…"))}</p>
          <textarea class="chat-location-share-note" rows="2" maxlength="500" placeholder="${escapeHtml(labels.notePlaceholder || "Hinweis hinzufügen…")}"></textarea>
          <div class="chat-location-share-actions">
            <button type="button" class="chat-location-share-send"${cachedSendReady ? "" : " disabled"}>${escapeHtml(labels.send || "Senden")}</button>
          </div>
        </div>`;
      global.document.body.appendChild(sheet);
      shareSheetEl = sheet;

      const mapHost = sheet.querySelector(".chat-location-share-map");
      const statusEl = sheet.querySelector(".chat-location-share-status");
      const sendBtn = sheet.querySelector(".chat-location-share-send");
      const noteInput = sheet.querySelector(".chat-location-share-note");

      const onReading = (reading, error, meta) => {
        if (error && Number(error?.code) === 1) {
          if (statusEl) statusEl.textContent = locationCaptureErrorMessage(error, labels);
          if (sendBtn) sendBtn.disabled = true;
          return;
        }
        if (meta?.weakSignal) {
          if (statusEl) statusEl.textContent = shareStatusText(null, labels, meta);
          if (sendBtn) sendBtn.disabled = true;
          return;
        }
        if (!reading) return;
        bestReading = pickBetterReading(bestReading, reading);
        const displayReading = bestReading || reading;
        const acc = Number(displayReading.accuracy) || 999;
        if (statusEl) {
          statusEl.textContent = shareStatusText(displayReading, labels);
          statusEl.classList.toggle("is-precise", acc <= DEFAULT_MAX_ACCURACY_M);
        }
        if (isPreciseEnoughForMap(displayReading)) {
          mountMapInHost(mapHost, readingToResult(displayReading));
        }
        if (sendBtn) sendBtn.disabled = !canEnableSend(bestReading);
      };

      previewTimeout = global.setTimeout(() => {
        if (settled) return;
        if (bestReading && isPreciseEnoughForMap(bestReading)) {
          onReading(bestReading);
          return;
        }
        if (statusEl) {
          statusEl.textContent = locationCaptureErrorMessage(
            { message: "location_not_precise_enough", accuracyMeters: Number(bestReading?.accuracy) || 99 },
            labels,
          );
        }
        if (sendBtn) sendBtn.disabled = true;
      }, PREVIEW_TIMEOUT_MS);

      if (global.navigator.permissions?.query) {
        void global.navigator.permissions.query({ name: "geolocation" }).then((state) => {
          if (settled || state?.state !== "denied") return;
          if (statusEl) statusEl.textContent = locationCaptureErrorMessage({ code: 1 }, labels);
          if (sendBtn) sendBtn.disabled = true;
        }).catch(() => {});
      }

      sheet.querySelector(".chat-location-share-close")?.addEventListener("click", () => {
        finish(new Error("location_cancelled"));
      });
      sendBtn?.addEventListener("click", () => {
        void (async () => {
          if (sendBtn.disabled) return;
          sendBtn.disabled = true;
          sendBtn.textContent = labels.sending || "…";
          if (statusEl) statusEl.textContent = labels.capturingHint || "GPS wird ermittelt…";
          try {
            const finalized = await captureForSend((payload) => {
              const acc = Number(payload?.bestAccuracyMeters);
              if (statusEl && Number.isFinite(acc)) {
                statusEl.textContent = shareStatusText({ accuracy: acc }, labels);
              }
            });
            if (!isValidReading(finalized)) throw new Error("geolocation_timeout");
            rememberReading(finalized);
            finish(null, readingToResult(finalized, { note: noteInput?.value || "" }));
          } catch (error) {
            sendBtn.disabled = !canEnableSend(bestReading);
            sendBtn.textContent = labels.send || "Senden";
            if (statusEl) statusEl.textContent = locationCaptureErrorMessage(error, labels);
          }
        })();
      });

      startShareLocationWatch(onReading);
    });
  }

  function warmChatGeolocation() {
    ensureBackgroundGeoWarm();
    const cached = getPreciseCachedLastKnown();
    if (cached) return Promise.resolve(cached);
    return captureBestReadingFast().then((reading) => {
      rememberReading(reading);
      return reading;
    }).catch(() => null);
  }

  function locationCaptureErrorMessage(error, labels = {}) {
    const code = String(error?.message || error?.code || "");
    const acc = Number(error?.accuracyMeters);
    if (code === "geolocation_inaccurate" || code === "location_not_precise_enough" || Number(error?.code) === 4) {
      const tpl = labels.inaccurate || "GPS zu ungenau (±{m} m). Bitte kurz ins Freie gehen.";
      return tpl.replace("{m}", String(Math.round(acc || 99))).replace("{max}", String(SEND_MAX_ACCURACY_M));
    }
    if (code === "geolocation_unsupported") return labels.unsupported || "Standort wird auf diesem Gerät nicht unterstützt.";
    if (code === "geolocation_timeout") return labels.timeout || "Standort-Timeout — bitte erneut versuchen.";
    if (Number(error?.code) === 1) return labels.denied || "Standortfreigabe verweigert.";
    return labels.failed || "Standort konnte nicht ermittelt werden.";
  }

  function peekCachedChatLocation(options = {}) {
    const cached = getPreciseCachedLastKnown();
    if (!cached) return null;
    return readingToResult(cached, options);
  }

  global.SUPPIXChatLocation = {
    PREFIX,
    DEFAULT_MAX_ACCURACY_M,
    encodeLocationBody,
    parseLocationBody,
    isLocationBody,
    renderLocationBubbleHtml,
    openShareSheet,
    captureChatLocation: openShareSheet,
    peekCachedChatLocation,
    warmChatGeolocation,
    ensureBackgroundGeoWarm,
    locationCaptureErrorMessage,
    googleMapsUrl,
    googleMapsEmbedUrl,
    mapsUrl,
    staticMapUrl,
  };
})(typeof window !== "undefined" ? window : globalThis);
