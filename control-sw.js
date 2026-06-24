const BUILD = "20260621contrast1";
const SHELL_CACHE = `baupass-control-shell-${BUILD}`;
const RUNTIME_CACHE = `baupass-control-runtime-${BUILD}`;
const SHELL_ASSETS = [
  "/",
  "/index.html",
  `/index.html?v=${BUILD}`,
  `/app.js?v=${BUILD}`,
  `/styles.css?v=${BUILD}`,
  `/platform-health.css?v=${BUILD}`,
  "/control-manifest.json",
  "/branding/suppix-ai-logo.svg",
  "/branding/suppix-ai-logo-dark.svg",
  "/branding/suppix-ai-invoice.svg",
  "/branding/suppix-ai-mark.svg",
  "/branding/suppix-icon-192.png",
  "/branding/suppix-icon-512.png",
  "/branding/suppix-ai-mark.svg",
  "/branding/suppix-ai-mark.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.map((key) => caches.delete(key))))
      .then(() => self.registration.unregister())
      .then(() => self.clients.claim())
  );
});

async function staleWhileRevalidate(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  const cached = await cache.match(request);
  const networkPromise = fetch(request)
    .then((response) => {
      if (response && response.ok) {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch(() => cached);
  return cached || networkPromise;
}

async function networkFirst(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) {
      return cached;
    }
    throw new Error("network_unavailable");
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  const isSameOrigin = url.origin === self.location.origin;
  const isNavigation = request.mode === "navigate";
  const isCriticalShell = isSameOrigin && (
    url.pathname === "/" ||
    url.pathname.endsWith("/index.html") ||
    url.pathname.endsWith("/app.js") ||
    url.pathname.endsWith("/styles.css") ||
    url.pathname.endsWith("/platform-health.css") ||
    url.pathname.endsWith("/control-manifest.json")
  );
  const isStaticShell = isSameOrigin && (
    url.pathname === "/" ||
    url.pathname.endsWith("/index.html") ||
    url.pathname.endsWith("/app.js") ||
    url.pathname.endsWith("/styles.css") ||
    url.pathname.endsWith("/platform-health.css") ||
    url.pathname.endsWith(".svg") ||
    url.pathname.endsWith(".png") ||
    url.pathname.endsWith(".json")
  );
  const isJsDelivr = url.origin === "https://cdn.jsdelivr.net";

  if (isNavigation) {
    event.respondWith(
      networkFirst(request).catch(async () => (
        (await caches.match(request)) ||
        (await caches.match(`/index.html?v=${BUILD}`)) ||
        (await caches.match("/index.html"))
      ))
    );
    return;
  }

  if (isCriticalShell) {
    event.respondWith(networkFirst(request));
    return;
  }

  if (isStaticShell || isJsDelivr) {
    event.respondWith(staleWhileRevalidate(request));
  }
});
