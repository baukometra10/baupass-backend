const WORKER_BUILD = "20260714chat5";
const CACHE_NAME = `baupass-worker-${WORKER_BUILD}`;
const SHELL_NETWORK_FIRST = new Set([
  "/worker-app.js",
  "/chat-voice.js",
  "/chat-realtime.js",
  "/chat-gallery.js",
  "/chat-typing.js",
  "/chat-search.js",
  "/chat-offline-queue.js",
  "/chat-voice-call.js",
  "/worker-voice-call.js",
  "/worker.css",
  "/worker-layout-v2.css",
  "/worker-polish.css",
  "/worker-login.css",
  "/emp-app-manifest.json",
  "/worker-manifest.json",
]);
// worker.html is intentionally excluded from STATIC_FILES so it is always
// fetched from the network (network-first). This ensures Android and iOS
// users always get the latest version without needing to clear the cache.
const STATIC_ASSETS = [
  { path: "/worker.css", rev: WORKER_BUILD },
  { path: "/worker-app.js", rev: WORKER_BUILD },
  { path: "/chat-realtime.js", rev: WORKER_BUILD },
  { path: "/chat-gallery.js", rev: WORKER_BUILD },
  { path: "/chat-typing.js", rev: WORKER_BUILD },
  { path: "/chat-search.js", rev: WORKER_BUILD },
  { path: "/chat-offline-queue.js", rev: WORKER_BUILD },
  { path: "/chat-voice.js", rev: WORKER_BUILD },
  { path: "/chat-voice-call.js", rev: WORKER_BUILD },
  { path: "/worker-voice-call.js", rev: WORKER_BUILD },
  { path: "/emp-app-manifest.json", rev: WORKER_BUILD },
  { path: "/branding/suppix-icon-192.png" },
  { path: "/branding/suppix-icon-512.png" },
  { path: "/branding/suppix-ai-mark.svg" },
  { path: "/branding/suppix-ai-logo.svg" }
];
const STATIC_PATHS = new Set(STATIC_ASSETS.map((asset) => asset.path));
const STATIC_FILES = [...new Set(STATIC_ASSETS.map((asset) => (asset.rev ? `${asset.path}?v=${asset.rev}` : asset.path)))];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_FILES))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

// Allow the app to force-activate a waiting SW immediately.
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

self.addEventListener("fetch", (event) => {
  const requestUrl = new URL(event.request.url);
  if (event.request.method !== "GET") {
    return;
  }
  // API-Requests: Network first, fallback zu Cache (optional)
  if (requestUrl.pathname.startsWith("/api/worker-app/")) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          // Optional: Response cachen
          return response;
        })
        .catch(() => new Response(JSON.stringify({ offline: true }), { status: 503, headers: { "Content-Type": "application/json" } }))
    );
    return;
  }
  // Chat/API downloads must never be cached by the worker shell.
  if (requestUrl.pathname.startsWith("/api/chat/")) {
    event.respondWith(fetch(event.request));
    return;
  }
  // Launcher + app shell: network-only — installed PWA must never stick on old emp-app.html.
  if (requestUrl.pathname === "/worker-install.html" || requestUrl.pathname === "/worker-build.json" || requestUrl.pathname === "/emp-app.html" || requestUrl.pathname === "/worker.html" || requestUrl.pathname === "/") {
    event.respondWith(
      fetch(event.request, { cache: "no-store" })
        .catch(async () => {
          const cachedPage = await caches.match("/emp-app.html", { ignoreSearch: true }) || await caches.match("/worker-install.html", { ignoreSearch: true });
          return cachedPage || new Response("Offline", { status: 503, statusText: "Offline" });
        })
    );
    return;
  }

  // Keep app shell assets current in installed iOS/Android/PWA.
  if (SHELL_NETWORK_FIRST.has(requestUrl.pathname)) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, response.clone())).catch(() => {});
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(event.request, { ignoreSearch: true });
          return cached || new Response("", { status: 504, statusText: "Offline" });
        })
    );
    return;
  }

  // Statische Kern-Dateien: Stale-while-revalidate – Cache sofort, Update im Hintergrund.
  if (STATIC_PATHS.has(requestUrl.pathname)) {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) => {
        return cache.match(event.request, { ignoreSearch: true }).then((cached) => {
          const networkFetch = fetch(event.request).then((response) => {
            cache.put(event.request, response.clone()).catch(() => {});
            return response;
          }).catch(() => cached || new Response("", { status: 504, statusText: "Offline" }));
          return cached || networkFetch;
        });
      })
    );
    return;
  }

  // Sonstige statische Dateien: Cache first
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(event.request).catch(async () => {
        if (event.request.mode === "navigate") {
          return (
            (await caches.match("/emp-app.html", { ignoreSearch: true })) ||
            (await caches.match("/worker.html", { ignoreSearch: true })) ||
            (await caches.match("/index.html")) ||
            new Response("Offline", { status: 503, statusText: "Offline" })
          );
        }
        return new Response("", { status: 504, statusText: "Offline" });
      });
    })
  );
});

// ── Push-Benachrichtigungen ───────────────────────────────────────────
const PUSH_TAG_URLS = {
  "deployment-plan": "/emp-app.html#einsatzplan",
  "payroll-document": "/emp-app.html#documents",
  "worker-document": "/emp-app.html#documents",
  "leave-request-status": "/emp-app.html#leave",
  "leave-approved": "/emp-app.html#leave",
  "leave-denied": "/emp-app.html#leave",
  "worker-chat": "/emp-app.html#chat",
  "voice-call": "/emp-app.html#chat",
  "contract-sign": "/emp-app.html#documents",
};

function resolvePushTargetUrl(data, tag) {
  const directUrl = String(data?.url || "").trim();
  if (directUrl) {
    return directUrl;
  }
  if (PUSH_TAG_URLS[tag]) {
    return PUSH_TAG_URLS[tag];
  }
  const route = String(data?.route || data?.deeplink || "").trim();
  if (route.startsWith("baupass://app/")) {
    const routeMap = {
      chat: "/emp-app.html#chat",
      "voice-call": "/emp-app.html#chat",
      deployment: "/emp-app.html#einsatzplan",
      documents: "/emp-app.html#documents",
      tasks: "/emp-app.html#leave",
      profile: "/emp-app.html",
      shifts: "/emp-app.html",
      attendance: "/emp-app.html",
      ai: "/emp-app.html",
      "contract-sign": "/emp-app.html#documents",
    };
    const routeKey = route.slice("baupass://app/".length).split("?")[0];
    if (routeMap[routeKey]) {
      return routeMap[routeKey];
    }
  }
  return "/emp-app.html";
}

function buildPushNotificationOptions(data, tag, targetUrl) {
  const displayTag = String(data.notificationTag || data.tag || `baupass-${Date.now()}`).trim();
  const logicalTag = String(data.tag || tag || "baupass-notification").trim();
  return {
    body: data.body || "",
    tag: displayTag,
    icon: "/branding/suppix-icon-192.png",
    badge: "/branding/suppix-icon-192.png",
    lang: "de",
    dir: "auto",
    silent: false,
    renotify: true,
    requireInteraction: logicalTag === "worker-chat" || logicalTag === "voice-call" || logicalTag.startsWith("leave-"),
    vibrate: [200, 100, 200],
    timestamp: Number(data.timestamp) || Date.now(),
    data: { url: targetUrl, tag: logicalTag },
  };
}

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "SUPPIX", body: event.data ? event.data.text() : "" };
  }
  const title = data.title || "SUPPIX";
  const tag = data.tag || "baupass-notification";
  const defaultUrl = resolvePushTargetUrl(data, tag);
  const options = buildPushNotificationOptions(data, tag, defaultUrl);
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/worker-install.html?launch=1";
  const absoluteUrl = new URL(targetUrl, self.location.origin).href;
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(async (windowClients) => {
      for (const client of windowClients) {
        if (client.url.includes("/emp-app") || client.url.includes("/worker")) {
          if ("focus" in client) {
            await client.focus();
          }
          client.postMessage({ type: "NAVIGATE_WORKER_APP", url: absoluteUrl });
          return;
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(absoluteUrl);
      }
    })
  );
});

// ── Background Sync – Offline-Queue senden ────────────────────────────
self.addEventListener("sync", (event) => {
  if (event.tag === "baupass-offline-queue") {
    event.waitUntil(flushOfflineQueueFromSW());
  }
});

async function flushOfflineQueueFromSW() {
  // Benachrichtige alle offenen Tabs dass sie die Queue synchronisieren sollen
  const allClients = await clients.matchAll({ type: "window", includeUncontrolled: true });
  for (const client of allClients) {
    client.postMessage({ type: "SW_FLUSH_OFFLINE_QUEUE" });
  }
}

// ── Checkout-Reminder (lokale Benachrichtigung, kein Server noetig) ──
self.addEventListener("message", (event) => {
  if (!event.data) return;
  if (event.data.type === "SCHEDULE_CHECKOUT_REMINDER") {
    const { workerName, checkoutTime, delayMs } = event.data;
    if (!delayMs || delayMs < 0) return;
    setTimeout(() => {
      self.registration.showNotification("Vergessen auszustempeln?", {
        body: `${workerName || "Hallo"} – deine Schicht endet gleich. Bitte auschecken!`,
        tag: `checkout-reminder-${Date.now()}`,
        icon: "/branding/suppix-icon-192.png",
        badge: "/branding/suppix-icon-192.png",
        silent: false,
        renotify: true,
        vibrate: [300, 150, 300],
        data: { url: "/worker-install.html?launch=1" }
      });
    }, delayMs);
  }
  if (event.data.type === "CANCEL_CHECKOUT_REMINDER") {
    // Nichts zu tun – der setTimeout kann nicht abgebrochen werden,
    // aber der Worker kann die Notification schliessen wenn er online bleibt
  }
});
