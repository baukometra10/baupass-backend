/** Leaflet geofence picker — click map to set lat/lng, show existing zones. */
export function mountGeofenceMap(containerEl, latInput, lngInput, zones = []) {
  if (!window.L || !containerEl) return null;
  const lat = parseFloat(latInput?.value) || 52.52;
  const lng = parseFloat(lngInput?.value) || 13.405;
  containerEl.innerHTML = "";
  const map = window.L.map(containerEl).setView([lat, lng], 14);
  window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap",
  }).addTo(map);
  const layers = [];
  zones.forEach((z) => {
    if (z.latitude == null || z.longitude == null) return;
    const c = window.L.circle([z.latitude, z.longitude], {
      radius: z.radius_meters || 50,
      color: "#1b7a9e",
      fillOpacity: 0.15,
    }).addTo(map);
    c.bindPopup(z.site_name || "Zone");
    layers.push(c);
  });
  map.on("click", (e) => {
    if (latInput) latInput.value = e.latlng.lat.toFixed(6);
    if (lngInput) lngInput.value = e.latlng.lng.toFixed(6);
  });
  setTimeout(() => map.invalidateSize(), 200);
  return map;
}
