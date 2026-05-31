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

  map.on("click", (e) => {
    if (latInput) latInput.value = e.latlng.lat.toFixed(6);
    if (lngInput) lngInput.value = e.latlng.lng.toFixed(6);
  });

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
