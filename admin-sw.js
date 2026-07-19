/* SUPPIX admin service worker — web push for employer chat. */
const ADMIN_SW_BUILD = "20260719chat45";

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

function resolveAdminPushUrl(data) {
  const direct = String(data?.url || data?.actionUrl || "").trim();
  if (direct) return direct;
  const companyId = String(data?.companyId || data?.company_id || "").trim();
  const workerId = String(data?.workerId || data?.worker_id || "").trim();
  const callId = String(data?.callId || data?.call_id || "").trim();
  let url = "/admin-v2/chat.html";
  const params = new URLSearchParams();
  if (companyId) params.set("company_id", companyId);
  if (workerId) params.set("worker_id", workerId);
  if (callId) params.set("call_id", callId);
  const qs = params.toString();
  if (qs) url += `?${qs}`;
  return url;
}

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "SUPPIX", body: event.data ? event.data.text() : "" };
  }
  const title = data.title || "SUPPIX Chat";
  const tag = data.tag || "admin-chat";
  const targetUrl = resolveAdminPushUrl(data);
  event.waitUntil(
    Promise.all([
      self.registration.showNotification(title, {
        body: data.body || "",
        tag,
        icon: "/branding/suppix-icon-192.png",
        badge: "/branding/suppix-icon-192.png",
        data: {
          url: targetUrl,
          tag,
          callId: data.callId || data.call_id || "",
          workerId: data.workerId || data.worker_id || "",
          companyId: data.companyId || data.company_id || "",
        },
        renotify: true,
        requireInteraction: tag === "admin-chat" || tag === "voice-call",
      }),
      clients.matchAll({ type: "window", includeUncontrolled: true }).then((windowClients) => {
        windowClients.forEach((client) => {
          client.postMessage({
            type: "SUPPIX_CHAT_PUSH",
            role: "admin",
            tag,
            title,
            body: data.body || "",
            workerId: data.workerId || data.worker_id || "",
            workerName: data.workerName || "",
            threadId: data.threadId || data.thread_id || "",
            callId: data.callId || data.call_id || "",
            companyId: data.companyId || data.company_id || "",
            preview: data.preview || data.body || "",
            url: targetUrl,
          });
        });
      }),
    ]),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/admin-v2/chat.html";
  const absoluteUrl = new URL(targetUrl, self.location.origin).href;
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(async (windowClients) => {
      for (const client of windowClients) {
        if (client.url.includes("/admin-v2/")) {
          if ("focus" in client) await client.focus();
          client.postMessage({ type: "NAVIGATE_ADMIN_CHAT", url: absoluteUrl });
          return;
        }
      }
      if (clients.openWindow) return clients.openWindow(absoluteUrl);
    }),
  );
});

self.addEventListener("sync", (event) => {
  if (event.tag === "baupass-offline-queue") {
    event.waitUntil(
      clients.matchAll({ type: "window", includeUncontrolled: true }).then((allClients) => {
        allClients.forEach((client) => client.postMessage({ type: "SW_FLUSH_OFFLINE_QUEUE" }));
      }),
    );
  }
});
