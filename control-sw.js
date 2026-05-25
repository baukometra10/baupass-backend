const SHELL_CACHE = "baupass-control-shell-v78";
const RUNTIME_CACHE = "baupass-control-runtime-v78";
const SHELL_ASSETS = [
  "/",
  "/index.html",
  "/index.html?v=20260524l",
  "/app.js",
  "/app.js?v=20260524l",
  "/styles.css",
  "/styles.css?v=20260524l",
  "/desktop/renderer.js",
  "/desktop/renderer.js?v=20260524l",
  "/control-manifest.json",
  "/branding/baukometra-logo.svg",
  "/branding/baukometra-alt-logo.svg",
  "/worker-icon-192.png",
  "/worker-icon-512.png",
  "/worker-icon-192.svg",
  "/worker-icon-512.svg",
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
  const isSameOrigin = url.origin === self.location.origin;
  const isNavigation = request.mode === "navigate";
  const isCriticalShell = isSameOrigin && (
    url.pathname === "/" ||
    url.pathname.endsWith("/index.html") ||
    url.pathname.endsWith("/app.js") ||
    url.pathname.endsWith("/styles.css") ||
    url.pathname.endsWith("/control-manifest.json")
  );
  const isStaticShell = isSameOrigin && (
    url.pathname === "/" ||
    url.pathname.endsWith("/index.html") ||
    url.pathname.endsWith("/app.js") ||
    url.pathname.endsWith("/styles.css") ||
    url.pathname.endsWith(".svg") ||
    url.pathname.endsWith(".png") ||
    url.pathname.endsWith(".json")
  );
  const isJsDelivr = url.origin === "https://cdn.jsdelivr.net";

  if (isNavigation) {
    event.respondWith(
      networkFirst(request).catch(async () => (
        (await caches.match(request)) ||
        (await caches.match("/index.html?v=20260524b")) ||
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
