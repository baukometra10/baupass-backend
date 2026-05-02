const CACHE_NAME = "baupass-worker-v12";
const STATIC_FILES = [
  "/worker.html",
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
  // Statische Kern-Dateien: Stale-while-revalidate – Cache sofort, Update im Hintergrund.
  if (STATIC_FILES.includes(requestUrl.pathname)) {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) => {
        return cache.match(event.request).then((cached) => {
          const networkFetch = fetch(event.request).then((response) => {
            cache.put(event.request, response.clone()).catch(() => {});
            return response;
          }).catch(() => cached);
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
      return fetch(event.request);
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
    data: { url: data.url || "/worker.html" },
    actions: data.actions || []
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/worker.html";
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
