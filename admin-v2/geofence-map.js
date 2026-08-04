/** Leaflet geofence picker — click map to set lat/lng, show existing zones. */
export function mountGeofenceMap(containerEl, latInput, lngInput, zones = []) {
  if (!window.L || !containerEl) return null;

  const prev = containerEl._baupassLeafletMap;
  if (prev) {
    try {
      prev._baupassResizeObserver?.disconnect();
      prev._baupassIntersectionObserver?.disconnect();
      prev.remove();
    } catch {
      // no-op
    }
    containerEl._baupassLeafletMap = null;
  }

  const lat = parseFloat(latInput?.value) || 52.52;
  const lng = parseFloat(lngInput?.value) || 13.405;
  containerEl.innerHTML = "";
  containerEl.style.width = "100%";
  containerEl.style.height = "280px";
  containerEl.style.minHeight = "280px";
  containerEl.style.position = "relative";
  containerEl.style.overflow = "hidden";

  const map = window.L.map(containerEl, {
    preferCanvas: false,
    zoomControl: true,
  }).setView([lat, lng], 14);

  window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap",
  }).addTo(map);

  zones.forEach((z) => {
    if (z.latitude == null || z.longitude == null) return;
    const c = window.L.circle([z.latitude, z.longitude], {
      radius: z.radius_meters || 50,
      color: "#1b7a9e",
      fillOpacity: 0.15,
    }).addTo(map);
    c.bindPopup(z.site_name || "Zone");
  });

  const setMarker = (latVal, lngVal) => {
    if (map._baupassMarker) {
      try {
        map._baupassMarker.remove();
      } catch {
        // no-op
      }
    }
    map._baupassMarker = window.L.marker([latVal, lngVal]).addTo(map);
  };

  const applyCoords = (latVal, lngVal, { center = false } = {}) => {
    if (latInput) latInput.value = latVal.toFixed(6);
    if (lngInput) lngInput.value = lngVal.toFixed(6);
    setMarker(latVal, lngVal);
    if (center) map.setView([latVal, lngVal], Math.max(map.getZoom(), 15));
  };

  map.on("click", (e) => {
    applyCoords(e.latlng.lat, e.latlng.lng);
  });

  map._baupassApplyCoords = applyCoords;

  const invalidate = () => {
    try {
      map.invalidateSize({ animate: false, pan: false });
    } catch {
      // no-op
    }
  };

  containerEl._baupassLeafletMap = map;
  map._baupassInvalidate = invalidate;

  map.whenReady(() => {
    applyCoords(lat, lng);
    invalidate();
    setTimeout(invalidate, 50);
    setTimeout(invalidate, 300);
  });

  if (typeof ResizeObserver !== "undefined") {
    const ro = new ResizeObserver(() => invalidate());
    ro.observe(containerEl);
    map._baupassResizeObserver = ro;
  }

  if (typeof IntersectionObserver !== "undefined") {
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) invalidate();
      },
      { threshold: 0.05 },
    );
    io.observe(containerEl);
    map._baupassIntersectionObserver = io;
  }

  return map;
}

/** Wait until the map container has real dimensions (tab visible, layout done). */
export function mountGeofenceMapWhenReady(containerEl, latInput, lngInput, zones = []) {
  if (!containerEl) return null;
  let attempts = 0;
  const tryMount = () => {
    const rect = containerEl.getBoundingClientRect();
    const visible = rect.width > 48 && rect.height > 48 && containerEl.offsetParent !== null;
    if (visible) {
      return mountGeofenceMap(containerEl, latInput, lngInput, zones);
    }
    if (++attempts < 120) {
      requestAnimationFrame(tryMount);
    }
    return null;
  };
  tryMount();
  return containerEl._baupassLeafletMap || null;
}

export function refreshGeofenceMap() {
  const map = document.getElementById("geofenceMap")?._baupassLeafletMap;
  map?._baupassInvalidate?.();
}

/** Geocode a place query and move geofence map + marker to the first result. */
export async function searchGeofencePlace(query, mapEl, latInput, lngInput, { onStatus, language } = {}) {
  const raw = String(query || "").trim();
  if (!raw) {
    onStatus?.("empty");
    return null;
  }
  const map = mapEl?._baupassLeafletMap || document.getElementById("geofenceMap")?._baupassLeafletMap;
  if (!map) {
    onStatus?.("failed");
    return null;
  }

  onStatus?.("loading");
  try {
    const lang = String(language || "en").slice(0, 8);
    const params = new URLSearchParams({
      q: raw,
      format: "jsonv2",
      limit: "5",
      addressdetails: "1",
      "accept-language": lang,
    });
    const res = await fetch(`https://nominatim.openstreetmap.org/search?${params.toString()}`, {
      headers: {
        Accept: "application/json",
      },
    });
    if (!res.ok) {
      onStatus?.("failed");
      return null;
    }
    const rows = await res.json();
    const list = Array.isArray(rows)
      ? rows
        .map((r) => ({
          label: String(r?.display_name || "").trim(),
          lat: Number(r?.lat),
          lng: Number(r?.lon),
        }))
        .filter((r) => r.label && Number.isFinite(r.lat) && Number.isFinite(r.lng))
      : [];
    const hit = list[0] || null;
    const lat = Number(hit?.lat);
    const lng = Number(hit?.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      onStatus?.("notFound");
      return null;
    }

    if (map?._baupassApplyCoords) {
      map._baupassApplyCoords(lat, lng, { center: true });
    } else {
      if (latInput) latInput.value = lat.toFixed(6);
      if (lngInput) lngInput.value = lng.toFixed(6);
      map.setView([lat, lng], Math.max(map.getZoom(), 15));
    }

    const label = String(hit?.label || raw).trim();
    onStatus?.("ok", { label, lat, lng, count: list.length });
    return { label, lat, lng, results: list };
  } catch {
    onStatus?.("failed");
    return null;
  }
}

/** Fill lat/lng from browser geolocation and center the map. */
export async function useGeofenceCurrentLocation(latInput, lngInput, mapEl, { onStatus } = {}) {
  const map = mapEl?._baupassLeafletMap || document.getElementById("geofenceMap")?._baupassLeafletMap;
  if (!navigator.geolocation) {
    onStatus?.("unsupported");
    return;
  }
  onStatus?.("loading");
  try {
    let position = null;
    if (typeof globalThis.capturePointGeolocation === "function") {
      position = await globalThis.capturePointGeolocation({
        maxWaitMs: 5000,
        earlyBestMs: 3000,
      });
    } else if (typeof globalThis.captureInstantGeolocation === "function") {
      position = await globalThis.captureInstantGeolocation();
    } else if (typeof globalThis.getCurrentGeolocationReading === "function") {
      position = await globalThis.getCurrentGeolocationReading({
        enableHighAccuracy: true,
        timeout: 20000,
        maximumAge: 0,
      });
    } else {
      position = await new Promise((resolve, reject) => {
        navigator.geolocation.getCurrentPosition(
          (pos) =>
            resolve({
              latitude: pos.coords.latitude,
              longitude: pos.coords.longitude,
              accuracy: pos.coords.accuracy,
            }),
          reject,
          { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 },
        );
      });
    }
    const { latitude, longitude, accuracy } = position || {};
    if (!Number.isFinite(Number(latitude)) || !Number.isFinite(Number(longitude))) {
      onStatus?.("failed");
      return;
    }
    if (map?._baupassApplyCoords) {
      map._baupassApplyCoords(latitude, longitude, { center: true });
    } else {
      if (latInput) latInput.value = latitude.toFixed(6);
      if (lngInput) lngInput.value = longitude.toFixed(6);
    }
    onStatus?.("ok", { accuracyMeters: accuracy });
  } catch (error) {
    const code = Number(error?.code);
    if (code === 4 || error?.message === "geolocation_inaccurate") {
      onStatus?.("inaccurate", { accuracyMeters: error?.accuracyMeters });
      return;
    }
    if (code === 1) {
      onStatus?.("denied");
      return;
    }
    if (code === 3) {
      onStatus?.("timeout");
      return;
    }
    onStatus?.("failed");
  }
}
