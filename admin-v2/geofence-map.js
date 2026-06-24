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
    if (typeof globalThis.captureInstantGeolocation === "function") {
      position = await globalThis.captureInstantGeolocation();
    } else if (typeof globalThis.getCurrentGeolocationReading === "function") {
      position = await globalThis.getCurrentGeolocationReading({
        enableHighAccuracy: true,
        timeout: 12000,
        maximumAge: 30000,
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
          { enableHighAccuracy: true, timeout: 1000, maximumAge: 15000 },
        );
      });
    }
    const { latitude, longitude } = position || {};
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
    onStatus?.("ok");
  } catch (error) {
    const code = Number(error?.code);
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
