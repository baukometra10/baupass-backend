const WORKER_BUILD = "20260516d";
const CACHE_NAME = `baupass-worker-${WORKER_BUILD}`;
// worker.html is intentionally excluded from STATIC_FILES so it is always
// fetched from the network (network-first). This ensures Android and iOS
// users always get the latest version without needing to clear the cache.
const STATIC_ASSETS = [
  { path: "/worker.css", rev: WORKER_BUILD },
  { path: "/worker-app.js", rev: WORKER_BUILD },
  { path: "/emp-app-manifest.json", rev: WORKER_BUILD },
  { path: "/worker-icon-192-20260511f.png" },
  { path: "/worker-icon-512-20260511f.png" },
  { path: "/worker-icon-192-20260511f.svg" },
  { path: "/worker-icon-512-20260511f.svg" }
];
const STATIC_PATHS = new Set(STATIC_ASSETS.map((asset) => asset.path));
const STATIC_FILES = STATIC_ASSETS.map((asset) => (asset.rev ? `${asset.path}?v=${asset.rev}` : asset.path));

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
  // Launcher + app shell: always prefer network so installed apps pull the latest build.
  if (requestUrl.pathname === "/worker-install.html" || requestUrl.pathname === "/worker-build.json" || requestUrl.pathname === "/emp-app.html" || requestUrl.pathname === "/worker.html" || requestUrl.pathname === "/") {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          caches.open(CACHE_NAME).then((c) => c.put(event.request, response.clone())).catch(() => {});
          return response;
        })
        .catch(async () => {
          const cachedPage = await caches.match("/worker-install.html", { ignoreSearch: true }) || await caches.match("/emp-app.html", { ignoreSearch: true });
          return cachedPage || new Response("Offline", { status: 503, statusText: "Offline" });
        })
    );
    return;
  }

  // Keep app shell code current in installed iOS/Android app.
  if (requestUrl.pathname === "/worker-app.js" || requestUrl.pathname === "/worker.css" || requestUrl.pathname === "/emp-app-manifest.json" || requestUrl.pathname === "/worker-manifest.json") {
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
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "BauPass", body: event.data ? event.data.text() : "" };
  }
  const title = data.title || "BauPass";
  const options = {
    body: data.body || "",
    tag: data.tag || "baupass-notification",
    icon: "/worker-icon-192-20260511f.png",
    badge: "/worker-icon-192-20260511f.png",
    vibrate: [200, 100, 200],
    data: { url: data.url || "/worker-install.html?launch=1" },
    actions: data.actions || []
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/worker-install.html?launch=1";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if ((client.url.includes("/emp-app") || client.url.includes("/worker")) && "focus" in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
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
        tag: "checkout-reminder",
        icon: "/worker-icon-192-20260511f.png",
        badge: "/worker-icon-192-20260511f.png",
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
