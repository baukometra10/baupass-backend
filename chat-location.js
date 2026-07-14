/**
 * SUPPIX chat location — WhatsApp-style share sheet, map card, optional note.
 */
(function initSuppixChatLocation(global) {
  const PREFIX = "@location|";
  const DEFAULT_MAX_ACCURACY_M = 10;
  const REFINE_MAX_MS = 8000;
  const LAST_KNOWN_MAX_AGE_MS = 10 * 60 * 1000;
  let stylesInjected = false;
  let lastKnownChatGeo = null;
  let warmInFlight = null;
  let shareSheetEl = null;
  let shareWatchId = null;
  let shareWatchTimer = null;

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
    const zoom = acc <= DEFAULT_MAX_ACCURACY_M ? 18 : acc <= 35 ? 17 : acc <= 80 ? 16 : 15;
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
      ".chat-location-map-caption{display:flex;flex-direction:column;gap:.18rem;padding:.55rem .65rem .62rem;background:#1f2c34}",
      ".chat-location-caption-title{font-size:.84rem;font-weight:600;color:#e9edef;line-height:1.25}",
      ".chat-location-caption-note{font-size:.82rem;color:#e9edef;line-height:1.35;white-space:pre-wrap;word-break:break-word}",
      ".chat-location-caption-acc{font-size:.72rem;color:rgba(233,237,239,.58)}",
      ".chat-location-caption-acc.is-precise{color:#25d366;font-weight:600}",
      ".chat-location-caption-acc.is-warn{color:#fbbf24}",
      ".chat-location-map-fallback{display:grid;place-items:center;min-height:140px;background:linear-gradient(160deg,#dadce0,#bdc1c6);color:#3c4043;font-size:.82rem;padding:1rem;text-align:center}",
      ".chat-location-share-sheet{position:fixed;inset:0;z-index:10000;display:flex;flex-direction:column;background:rgba(5,8,16,.78)}",
      ".chat-location-share-sheet.hidden{display:none}",
      ".chat-location-share-top{display:flex;align-items:center;justify-content:space-between;padding:.85rem 1rem;color:#e9edef}",
      ".chat-location-share-close{border:none;background:transparent;color:#e9edef;font-size:1.5rem;line-height:1;cursor:pointer;padding:.25rem .45rem;border-radius:8px}",
      ".chat-location-share-close:hover{background:rgba(255,255,255,.08)}",
      ".chat-location-share-heading{margin:0;font-size:1rem;font-weight:600}",
      ".chat-location-share-mapwrap{position:relative;flex:1;min-height:0;display:flex;flex-direction:column;padding:0 1rem 1rem}",
      ".chat-location-share-map{position:relative;flex:1;min-height:220px;border-radius:14px;overflow:hidden;background:#dadce0;box-shadow:0 8px 28px rgba(0,0,0,.35)}",
      ".chat-location-share-map .chat-location-map-embed{position:absolute;left:50%;top:50%;width:120%;height:130%;border:0;transform:translate(-50%,-50%) scale(1.08);pointer-events:none}",
      ".chat-location-share-map-loading{position:absolute;inset:0;display:grid;place-items:center;background:rgba(17,27,33,.55);color:#e9edef;font-size:.88rem;gap:.5rem}",
      ".chat-location-share-map-loading.hidden{display:none}",
      ".chat-location-share-panel{background:#1f2c34;border-radius:18px 18px 0 0;padding:1rem 1rem calc(1rem + env(safe-area-inset-bottom,0px));box-shadow:0 -8px 32px rgba(0,0,0,.35)}",
      ".chat-location-share-status{margin:0 0 .65rem;font-size:.82rem;color:#8696a0}",
      ".chat-location-share-note{width:100%;min-height:44px;max-height:96px;resize:none;border-radius:12px;border:1px solid rgba(134,150,160,.22);background:#2a3942;color:#e9edef;padding:.65rem .75rem;font:inherit;font-size:.92rem;margin-bottom:.85rem}",
      ".chat-location-share-note::placeholder{color:rgba(233,237,239,.45)}",
      ".chat-location-share-actions{display:flex;justify-content:flex-end;gap:.55rem}",
      ".chat-location-share-send{min-width:120px;border:none;border-radius:999px;background:#00a884;color:#fff;font:inherit;font-weight:700;font-size:.92rem;padding:.72rem 1.35rem;cursor:pointer}",
      ".chat-location-share-send:disabled{opacity:.45;cursor:not-allowed}",
      ".chat-location-share-send:not(:disabled):hover{background:#06cf9c}",
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
    if (acc <= DEFAULT_MAX_ACCURACY_M) {
      return (labels.accuracyGood || "Genauigkeit ±{m} m").replace("{m}", String(acc));
    }
    if (acc <= 50) {
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
    const title = escapeHtml(labels.sharedTitle || "Standort geteilt");
    const noteHtml = loc.note
      ? `<span class="chat-location-caption-note">${escapeHtml(loc.note)}</span>`
      : "";
    const accText = accuracyLabel(loc, labels);
    const accClass = accuracyClass(loc);
    const embedSrc = googleMapsEmbedUrl(loc);
    const href = googleMapsUrl(loc);
    const openLabel = escapeHtml(labels.openMaps || "In Google Maps öffnen");
    const mapHtml = embedSrc
      ? `<div class="chat-location-map-frame"><iframe class="chat-location-map-embed" src="${escapeHtml(embedSrc)}" loading="lazy" title="${title}" allowfullscreen referrerpolicy="no-referrer-when-downgrade"></iframe></div>`
      : `<div class="chat-location-map-fallback">${openLabel}</div>`;
    return `<div class="chat-location-card ${side}">
      <a class="chat-location-map-hit" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer" aria-label="${openLabel}">
        ${mapHtml}
        <div class="chat-location-map-caption">
          <span class="chat-location-caption-title">${title}</span>
          ${noteHtml}
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

  function getAnyFreshLastKnown() {
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

  function stopShareWatch() {
    if (shareWatchTimer) {
      global.clearTimeout(shareWatchTimer);
      shareWatchTimer = null;
    }
    if (shareWatchId != null && global.navigator?.geolocation) {
      try { global.navigator.geolocation.clearWatch(shareWatchId); } catch { /* ignore */ }
      shareWatchId = null;
    }
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

  function updateShareSheetMap(sheet, point) {
    if (!sheet || !point) return;
    const mapHost = sheet.querySelector(".chat-location-share-map");
    const loading = sheet.querySelector(".chat-location-share-map-loading");
    if (!mapHost) return;
    const embedSrc = googleMapsEmbedUrl(point);
    let iframe = mapHost.querySelector("iframe");
    if (!iframe && embedSrc) {
      iframe = global.document.createElement("iframe");
      iframe.className = "chat-location-map-embed";
      iframe.setAttribute("loading", "eager");
      iframe.setAttribute("referrerpolicy", "no-referrer-when-downgrade");
      iframe.setAttribute("allowfullscreen", "");
      mapHost.appendChild(iframe);
    }
    if (iframe && embedSrc && iframe.src !== embedSrc) {
      iframe.src = embedSrc;
    }
    loading?.classList.add("hidden");
  }

  function updateShareSheetStatus(sheet, reading, labels = {}) {
    const statusEl = sheet.querySelector(".chat-location-share-status");
    if (!statusEl || !reading) return;
    const acc = Math.round(Number(reading.accuracy) || 0);
    if (!acc) {
      statusEl.textContent = labels.sharedTitle || "Standort geteilt";
      return;
    }
    statusEl.textContent = accuracyLabel(
      { accuracy: acc },
      labels,
    ) || (labels.sharedTitle || "Standort geteilt");
  }

  function startShareLocationWatch(onReading, maxMs = REFINE_MAX_MS) {
    stopShareWatch();
    if (!global.navigator?.geolocation) return;
    let best = null;
    const push = (reading) => {
      if (!isValidReading(reading)) return;
      if (!best || Number(reading.accuracy) < Number(best.accuracy)) {
        best = reading;
        rememberReading(reading);
        onReading(reading);
      }
    };
    const cached = getAnyFreshLastKnown();
    if (cached) push(cached);

    const attempts = [
      { enableHighAccuracy: false, maximumAge: 120000, timeout: 1800 },
      { enableHighAccuracy: true, maximumAge: 30000, timeout: 2500 },
      { enableHighAccuracy: true, maximumAge: 0, timeout: 3500 },
    ];
    void (async () => {
      for (const attempt of attempts) {
        try {
          const reading = await getGeolocationReading(attempt);
          push(reading);
          if (Number(reading.accuracy) <= 25) return;
        } catch (error) {
          if (Number(error?.code) === 1) onReading(null, error);
        }
      }
    })();

    shareWatchId = global.navigator.geolocation.watchPosition(
      (position) => {
        push({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: Number(position.coords.accuracy) || 999,
          capturedAt: Date.now(),
        });
      },
      (error) => {
        if (Number(error?.code) === 1) onReading(null, error);
      },
      { enableHighAccuracy: true, maximumAge: 0, timeout: maxMs },
    );
    shareWatchTimer = global.setTimeout(() => {
      stopShareWatch();
    }, maxMs);
  }

  function closeShareSheet() {
    stopShareWatch();
    shareSheetEl?.classList.add("hidden");
    shareSheetEl?.remove();
    shareSheetEl = null;
  }

  function openShareSheet(options = {}) {
    ensureLocationStyles();
    const labels = options.labels || {};
    if (!global.navigator?.geolocation) {
      return Promise.reject(new Error("geolocation_unsupported"));
    }
    closeShareSheet();

    return new Promise((resolve, reject) => {
      let settled = false;
      let bestReading = null;
      const finish = (error, result) => {
        if (settled) return;
        settled = true;
        closeShareSheet();
        if (error) reject(error);
        else resolve(result);
      };

      const sheet = global.document.createElement("div");
      sheet.className = "chat-location-share-sheet";
      sheet.innerHTML = `<div class="chat-location-share-top">
          <button type="button" class="chat-location-share-close" aria-label="${escapeHtml(labels.cancel || "Abbrechen")}">×</button>
          <h3 class="chat-location-share-heading">${escapeHtml(labels.shareTitle || labels.sharedTitle || "Standort senden")}</h3>
          <span style="width:2rem"></span>
        </div>
        <div class="chat-location-share-mapwrap">
          <div class="chat-location-share-map">
            <div class="chat-location-share-map-loading">${escapeHtml(labels.capturing || "Standort wird ermittelt…")}</div>
          </div>
        </div>
        <div class="chat-location-share-panel">
          <p class="chat-location-share-status">${escapeHtml(labels.capturingHint || "GPS wird ermittelt…")}</p>
          <textarea class="chat-location-share-note" rows="2" maxlength="500" placeholder="${escapeHtml(labels.notePlaceholder || "Hinweis hinzufügen…")}"></textarea>
          <div class="chat-location-share-actions">
            <button type="button" class="chat-location-share-send" disabled>${escapeHtml(labels.send || "Senden")}</button>
          </div>
        </div>`;
      global.document.body.appendChild(sheet);
      shareSheetEl = sheet;

      const closeBtn = sheet.querySelector(".chat-location-share-close");
      const sendBtn = sheet.querySelector(".chat-location-share-send");
      const noteInput = sheet.querySelector(".chat-location-share-note");

      const onReading = (reading, error) => {
        if (error && Number(error?.code) === 1) {
          finish(error);
          return;
        }
        if (!reading) return;
        bestReading = reading;
        updateShareSheetMap(sheet, readingToResult(reading));
        updateShareSheetStatus(sheet, reading, labels);
        if (sendBtn) sendBtn.disabled = false;
      };

      closeBtn?.addEventListener("click", () => {
        finish(new Error("location_cancelled"));
      });
      sendBtn?.addEventListener("click", () => {
        if (!bestReading) return;
        finish(null, readingToResult(bestReading, { note: noteInput?.value || "" }));
      });
      global.document.addEventListener("keydown", function escHandler(event) {
        if (event.key !== "Escape") return;
        global.document.removeEventListener("keydown", escHandler);
        finish(new Error("location_cancelled"));
      });

      try {
        startShareLocationWatch(onReading, Number(options.maxWaitMs || REFINE_MAX_MS));
      } catch (error) {
        finish(error);
      }
    });
  }

  function warmChatGeolocation() {
    if (!global.navigator?.geolocation) return Promise.resolve(null);
    if (warmInFlight) return warmInFlight;
    warmInFlight = (async () => {
      const attempts = [
        { enableHighAccuracy: false, maximumAge: 120000, timeout: 1500 },
        { enableHighAccuracy: true, maximumAge: 30000, timeout: 2500 },
        { enableHighAccuracy: true, maximumAge: 0, timeout: 3500 },
      ];
      for (const attempt of attempts) {
        try {
          const reading = await getGeolocationReading(attempt);
          rememberReading(reading);
          return reading;
        } catch (error) {
          if (Number(error?.code) === 1) return null;
        }
      }
      return getAnyFreshLastKnown();
    })().finally(() => {
      warmInFlight = null;
    });
    return warmInFlight;
  }

  function locationCaptureErrorMessage(error, labels = {}) {
    const code = String(error?.message || error?.code || "");
    const acc = Number(error?.accuracyMeters);
    if (code === "geolocation_inaccurate" || code === "location_not_precise_enough" || Number(error?.code) === 4) {
      const tpl = labels.inaccurate || "GPS zu ungenau (±{m} m). Bitte kurz ins Freie gehen.";
      return tpl.replace("{m}", String(Math.round(acc || 99))).replace("{max}", "150");
    }
    if (code === "geolocation_unsupported") return labels.unsupported || "Standort wird auf diesem Gerät nicht unterstützt.";
    if (code === "geolocation_timeout") return labels.timeout || "Standort-Timeout — bitte erneut versuchen.";
    if (Number(error?.code) === 1) return labels.denied || "Standortfreigabe verweigert.";
    return labels.failed || "Standort konnte nicht ermittelt werden.";
  }

  async function captureChatLocation(options = {}) {
    const point = await openShareSheet(options);
    return point;
  }

  function peekCachedChatLocation(options = {}) {
    const cached = getAnyFreshLastKnown();
    if (!cached) return null;
    return readingToResult(cached, options);
  }

  global.SUPPIXChatLocation = {
    PREFIX,
    DEFAULT_MAX_ACCURACY_M,
    encodeLocationBody,
    parseLocationBody,
    isLocationBody,
    formatLocationPreview,
    renderLocationBubbleHtml,
    openShareSheet,
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
