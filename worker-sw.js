const CACHE_NAME = "baupass-worker-v24";
// worker.html is intentionally excluded from STATIC_FILES so it is always
// fetched from the network (network-first). This ensures Android and iOS
// users always get the latest version without needing to clear the cache.
const STATIC_FILES = [
  "/worker.css",
  "/worker-app.js",
  "/worker-manifest.json",
  "/worker-icon-192.png",
  "/worker-icon-512.png",
  "/worker-icon-192.svg",
  "/worker-icon-512.svg"
];

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
  // worker.html: Network-first so every load gets the latest version.
  if (requestUrl.pathname === "/worker.html" || requestUrl.pathname === "/") {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          caches.open(CACHE_NAME).then((c) => c.put(event.request, response.clone())).catch(() => {});
          return response;
        })
        .catch(async () => (await caches.match("/worker.html")) || new Response("Offline", { status: 503, statusText: "Offline" }))
    );
    return;
  }
  // Statische Kern-Dateien: Stale-while-revalidate – Cache sofort, Update im Hintergrund.
  if (STATIC_FILES.includes(requestUrl.pathname)) {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) => {
        return cache.match(event.request).then((cached) => {
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
      return fetch(event.request).catch(() => {
        if (event.request.mode === "navigate") {
          return caches.match("/worker.html");
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
    icon: "/worker-icon-192.png",
    badge: "/worker-icon-192.png",
    vibrate: [200, 100, 200],
    data: { url: data.url || "/worker.html?view=card" },
    actions: data.actions || []
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/worker.html?view=card";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((windowClients) => {
      for (const client of windowClients) {
        if (client.url.includes("/worker") && "focus" in client) {
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
        icon: "/worker-icon-192.png",
        badge: "/worker-icon-192.png",
        vibrate: [300, 150, 300],
        data: { url: "/worker.html" }
      });
    }, delayMs);
  }
  if (event.data.type === "CANCEL_CHECKOUT_REMINDER") {
    // Nichts zu tun – der setTimeout kann nicht abgebrochen werden,
    // aber der Worker kann die Notification schliessen wenn er online bleibt
  }
});
