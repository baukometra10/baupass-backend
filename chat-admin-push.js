/**
 * SUPPIX admin chat push — VAPID web push for employer PWA/mobile browser.
 */
(function initSuppixAdminPush(global) {
  function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = global.atob(base64);
    const output = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; ++i) output[i] = raw.charCodeAt(i);
    return output;
  }

  function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    bytes.forEach((b) => { binary += String.fromCharCode(b); });
    return global.btoa(binary);
  }

  async function ensureAdminSw() {
    if (!("serviceWorker" in global.navigator)) return null;
    try {
      let registration = await global.navigator.serviceWorker.getRegistration("/admin-sw.js");
      if (!registration) {
        registration = await global.navigator.serviceWorker.register("/admin-sw.js", { scope: "/" });
      }
      await global.navigator.serviceWorker.ready;
      return registration;
    } catch {
      return null;
    }
  }

  async function subscribeAdminPush({ api, companyId } = {}) {
    if (!api || !companyId) return false;
    if (!("Notification" in global) || !("PushManager" in global)) return false;
    if (Notification.permission === "denied") return false;
    if (Notification.permission === "default") {
      const perm = await Notification.requestPermission();
      if (perm !== "granted") return false;
    }
    const registration = await ensureAdminSw();
    if (!registration) return false;

    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      const vapidRes = await api("/api/push-vapid-key");
      const vapidKey = String(vapidRes?.vapidPublicKey || vapidRes?.publicKey || "").trim();
      if (!vapidKey) return false;
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey),
      });
    }

    await api("/api/chat/push-subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        endpoint: subscription.endpoint,
        p256dh: arrayBufferToBase64(subscription.getKey("p256dh")),
        auth: arrayBufferToBase64(subscription.getKey("auth")),
        company_id: companyId,
      }),
    });
    return true;
  }

  function initAdminChatPush({ api, companyId, prompt = true } = {}) {
    if (!prompt || !api || !companyId) return;
    if (!("Notification" in global)) return;
    if (Notification.permission === "granted") {
      void subscribeAdminPush({ api, companyId });
      return;
    }
    if (Notification.permission === "default") {
      global.document?.addEventListener("visibilitychange", () => {
        if (global.document.visibilityState === "visible") {
          void subscribeAdminPush({ api, companyId });
        }
      }, { once: true });
    }
  }

  global.SUPPIXAdminChatPush = {
    ensureAdminSw,
    subscribeAdminPush,
    initAdminChatPush,
  };
})(typeof window !== "undefined" ? window : globalThis);
